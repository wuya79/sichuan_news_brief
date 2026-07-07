#!/usr/bin/env python3
"""First push to empty GitHub repo via REST API."""
import base64, json, subprocess, urllib.request, urllib.error, os

TOKEN = open("/home/ubuntu/.hermes/keys/GITHUB_TOKEN").read().strip()
REPO = "wuya79/sichuan_news_brief"
BRANCH = "master"
CWD = "/home/ubuntu/sichuan_news_brief"

def api(method, endpoint, data=None):
    url = f"https://api.github.com/repos/{REPO}/{endpoint}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
        headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "hermes-push/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read().decode()) if resp.status != 204 else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  HTTP {e.code}: {err[:300]}")
        raise

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, shell=True, cwd=CWD).stdout.strip()

os.chdir(CWD)

# Get local tree
local_tree = sh("git rev-parse HEAD^{tree}")
print(f"Local tree: {local_tree[:8]}")

# Get all blobs from local tree
local_blobs = {}
local_modes = {}
for line in sh(f"git ls-tree -r {local_tree}").split('\n'):
    parts = line.split(None, 3)
    if len(parts) >= 4 and parts[1] == "blob":
        local_blobs[parts[3]] = parts[2]
        local_modes[parts[3]] = parts[0]
print(f"Local files: {len(local_blobs)}")

# Upload all blobs
print(f"\nUploading {len(local_blobs)} blobs...")
for i, (path, sha) in enumerate(local_blobs.items()):
    raw = subprocess.run(f"git cat-file -p {sha}", capture_output=True, shell=True, cwd=CWD).stdout
    if not raw:
        print(f"  skip empty: {path}")
        continue
    try:
        text = raw.decode("utf-8")
        api("POST", "git/blobs", {"content": text, "encoding": "utf-8"})
    except UnicodeDecodeError:
        b64 = base64.b64encode(raw).decode()
        api("POST", "git/blobs", {"content": b64, "encoding": "base64"})
    if (i+1) % 10 == 0:
        print(f"  {i+1}/{len(local_blobs)}")

# Build tree
print("\nBuilding tree...")
tree_entries = [{"path": p, "mode": local_modes.get(p, "100644"), "type": "blob", "sha": local_blobs[p]} for p in local_blobs]
new_tree = api("POST", "git/trees", {"tree": tree_entries})
print(f"Tree: {new_tree['sha'][:8]}")

# Create initial commit
msg = sh("git log --format=%B -1 HEAD")
author_name = sh("git log --format=%an -1 HEAD")
author_email = sh("git log --format=%ae -1 HEAD")
author_date = sh("git log --format=%aI -1 HEAD")

new_commit = api("POST", "git/commits", {
    "message": msg,
    "tree": new_tree["sha"],
    "author": {"name": author_name, "email": author_email, "date": author_date},
    "committer": {"name": author_name, "email": author_email, "date": author_date},
})
print(f"Commit: {new_commit['sha'][:8]}")

# Create or update ref
try:
    api("GET", f"git/refs/heads/{BRANCH}")
    result = api("PATCH", f"git/refs/heads/{BRANCH}", {"sha": new_commit["sha"], "force": True})
    print(f"\n✅ 推送成功！(PATCH)")
except urllib.error.HTTPError:
    result = api("POST", "git/refs", {"ref": f"refs/heads/{BRANCH}", "sha": new_commit["sha"]})
    print(f"\n✅ 首次推送成功！(POST)")
print(f"https://github.com/{REPO}")
