#!/usr/bin/env python3
"""Idempotent Gitea/FeiCode Release publisher with public SHA readback."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

def request_json(url, token=None, *, data=None, method=None, content_type="application/json"):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    if data is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise

def download_sha(url):
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--api-base", default="https://feicode.com/api/v1")
parser.add_argument("--repo", default="WenPai-org/wordpress-playground")
parser.add_argument("--git-url", default="https://feicode.com/WenPai-org/wordpress-playground.git")
parser.add_argument("--tag", required=True)
parser.add_argument("--commit", required=True)
parser.add_argument("--artifact", type=Path, action="append", required=True)
parser.add_argument("--title")
parser.add_argument("--body", default="Immutable WenPai WordPress Playground runtime release.")
args = parser.parse_args()
token = os.environ.get("FEICODE_TOKEN")
if not token:
    raise SystemExit("BLOCKED FEICODE_TOKEN is absent")

refs = subprocess.check_output(["git", "ls-remote", args.git_url, f"refs/tags/{args.tag}", f"refs/tags/{args.tag}^{{}}"], text=True)
resolved = [line.split()[0] for line in refs.splitlines() if line.strip()]
if not resolved or args.commit not in resolved:
    raise SystemExit(f"FAIL tag {args.tag} does not resolve to exact product commit {args.commit}")

release_url = f"{args.api_base}/repos/{args.repo}/releases/tags/{urllib.parse.quote(args.tag)}"
status, release = request_json(release_url, token)
if status == 404:
    payload = json.dumps({"tag_name": args.tag, "target_commitish": args.commit,
                          "name": args.title or args.tag, "body": args.body,
                          "draft": False, "prerelease": False}).encode()
    _, release = request_json(f"{args.api_base}/repos/{args.repo}/releases", token,
                              data=payload, method="POST")
assets = {asset["name"]: asset for asset in release.get("assets", [])}
for artifact in args.artifact:
    artifact = artifact.resolve(strict=True)
    local = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if artifact.name in assets:
        remote = download_sha(assets[artifact.name]["browser_download_url"])
        if remote != local:
            raise SystemExit(f"FAIL existing asset differs: {artifact.name} local={local} remote={remote}")
        print(f"PASS existing-asset name={artifact.name} sha256={local}")
        continue
    boundary = "----wenpai-release-boundary"
    content_type = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=attachment; filename=\"{artifact.name}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n").encode() + artifact.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    upload = f"{args.api_base}/repos/{args.repo}/releases/{release['id']}/assets?name={urllib.parse.quote(artifact.name)}"
    _, asset = request_json(upload, token, data=body, method="POST",
                            content_type=f"multipart/form-data; boundary={boundary}")
    remote = download_sha(asset["browser_download_url"])
    if remote != local:
        raise SystemExit(f"FAIL public readback differs: {artifact.name} local={local} remote={remote}")
    print(f"PASS uploaded-asset name={artifact.name} sha256={local}")
print(f"PASS release assets={len(args.artifact)} tag={args.tag} commit={args.commit}")
