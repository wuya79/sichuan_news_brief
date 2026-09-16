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
# 2026-09-16修复: -z 解析(中文路径转义bug, 同 api_push.py)
rawz = subprocess.run(["git", "ls-tree", "-r", "-z", local_tree],
                      capture_output=True, cwd=CWD).stdout
for ent in rawz.split(b"\0"):
    if not ent:
        continue
    meta, _path = ent.split(b"\t", 1)
    mode, typ, sha = meta.decode().split()
    if typ == "blob":
        _p = _path.decode("utf-8")
        local_blobs[_p] = sha
        local_modes[_p] = mode
print(f"Local files: {len(local_blobs)}")
# 保险(2026-09-16): 空解析 → abort (防误写)
if not local_blobs:
    raise SystemExit("本地文件解析为空, abort")

# Upload all blobs
print(f"\nUploading {len(local_blobs)} blobs...")
for i, (path, sha) in enumerate(local_blobs.items()):
    r = subprocess.run(f"git cat-file -p {sha}", capture_output=True, shell=True, cwd=CWD)
    if r.returncode != 0:
        raise SystemExit(f"cat-file失败 {path}, abort")
    raw = r.stdout
    try:
        text = raw.decode("utf-8")
        blob = api("POST", "git/blobs", {"content": text, "encoding": "utf-8"})
    except UnicodeDecodeError:
        b64 = base64.b64encode(raw).decode()
        blob = api("POST", "git/blobs", {"content": b64, "encoding": "base64"})
    if not blob or blob.get("sha") != sha:
        raise SystemExit(f"blob校验失败 {path}: {blob and blob.get('sha')}, abort")
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
