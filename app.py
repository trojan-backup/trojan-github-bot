# trojan-github-bot
# Copyright (C) 2019 Trojan Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from flask import Flask, request
import requests
import jwt
import os
import time
import json
import re
from datetime import datetime
import sqlite3

app = Flask(__name__)

repo = None
install_id = None

app_id = os.environ["APP_ID"]
client_id = os.environ["CLIENT_ID"]
client_secret = os.environ["CLIENT_SECRET"]


bug_template = [
    "[x] I certify that I acknowledge if I don't follow the format below, or I'm using an old version of trojan, or I apparently fail to provide sufficient information (such as logs, specific numbers), or I don't check this box, my issue will be closed immediately without any notice.",
    ]
bug_version_regex = re.compile(r"\*\*Trojan Version\*\*.*(\d+\.\d+\.\d+).*\*\*Describe the bug\*\*", re.S)
feature_template = [
    "[x] I certify that I acknowledge if I don't follow the format below or I don't check this box, my issue will be closed immediately without any notice.",
    ]

jwt_cache = ("", 0)
token_cache = ("", 0)

@app.route('/')
def index():
    return '200 OK'

@app.route("/event", methods=["POST"])
def webhook():
    global repo, install_id
    data = request.json
    if request.headers["X-GitHub-Event"] == "issues" and data["action"] == "opened":
        body = data["issue"]["body"]
        num = data["issue"]["number"]
        # and mode
        bug = True
        feature = True
        for l in bug_template:
            if l not in body:
                bug = False
                break
        if bug:
            # check version
            latest = get_latest_version()
            if latest is None:
                return ""
            match = bug_version_regex.search(body)
            if match:
                provided = match.group(1)
                if provided != latest:
                    close(num)
            else:
                close(num)
            return ""
        # bug ends here
        for l in feature_template:
            if l not in body:
                feature = False
                break
        if not feature:
            close(num)
    elif request.headers["X-GitHub-Event"] == "installation" and data["action"] == "created":
        repos = data["repositories"]
        for r in repos:
            if r["full_name"] == "trojan-gfw/trojan":
                repo = r["full_name"]
                install_id = data["installation"]["id"]
                conn = sqlite3.connect("install.db")
                c = conn.cursor()
                c.execute("INSERT INTO data VALUES (?, ?)", (install_id, repo))
                conn.commit()
                conn.close()
    return ""

def close(number):
    h = {
        "user-agent": "Trojan-Issue-Automod",
        "accept": "application/vnd.github.machine-man-preview+json",
        "authorization": "token %s" % get_token()
    }
    requests.patch(
        "https://api.github.com/repos/%s/issues/%s" % (repo, number),
        data=json.dumps({"state": "closed"}),
        headers=h
    )
    return ""

def get_latest_version():
    h = {
        "user-agent": "Trojan-Issue-Automod",
        "accept": "application/vnd.github.machine-man-preview+json",
        "authorization": "token %s" % get_token()
    }
    r = requests.get("https://api.github.com/repos/%s/releases/latest" % repo, headers=h)
    if r.ok:
        data = r.json()
        tag = data.get("tag_name", "None")
        if tag is None:
            return None
        return tag.replace("v", "")
    else :
        return None

def get_token():
    global token_cache
    now = int(time.time())
    if now < token_cache[1]:
        return token_cache[0]
    h = {
        "accept": "application/vnd.github.machine-man-preview+json",
        "authorization": "Bearer %s" % get_jwt()
    }
    r = requests.post("https://api.github.com/app/installations/%s/access_tokens" % install_id, headers=h)
    data = r.json()
    token = data["token"]
    expire = int(datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ").timestamp())
    token_cache = (token, expire)
    return token

def get_jwt():
    global jwt_cache
    now = int(time.time())
    if now < jwt_cache[1]:
        return jwt_cache[0]
    sk = open("sk.pem").read()
    h = {
        "iss": app_id,
        "iat": now,
        "exp": now + 300
    }
    res = jwt.encode(h, sk, algorithm='RS256').decode("utf8")
    jwt_cache = (res, now + 300)
    return res

def main():
    global repo, install_id
    conn = sqlite3.connect("install.db")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data'")
    row = c.fetchone()
    if row is None:
        c.execute("CREATE TABLE data (install_id INTEGER PRIMARY KEY, repo VARCHAR(255))")
        conn.commit()
    else:
        c.execute("SELECT install_id, repo FROM data ORDER BY install_id DESC LIMIT 1")
        row = c.fetchone()
        if row is not None:
            install_id = row[0]
            repo = row[1]
    conn.close()
    app.run(port=50000)

if __name__ == '__main__':
    main()
