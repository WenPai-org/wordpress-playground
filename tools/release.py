#!/usr/bin/env python3
"""Fail-closed, idempotent Gitea/FeiCode Release publisher.

Assets are assembled on a draft Release.  The Release is made public only
after every requested attachment has been read back with authentication and
matched byte-for-byte.  Publication is followed by an anonymous readback of
the Release and every attachment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def request_json(url, token=None, *, data=None, method=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return 404, None
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_sha(url: str, token: str | None = None) -> str:
    headers = {"Authorization": f"token {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=1800) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload(**values) -> bytes:
    return json.dumps(values, ensure_ascii=False, sort_keys=True).encode()


def release_assets(release: dict) -> dict[str, dict]:
    assets = release.get("assets", [])
    names = [asset.get("name") for asset in assets]
    if None in names or len(names) != len(set(names)):
        raise SystemExit("FAIL Release contains missing or duplicate asset names")
    return {asset["name"]: asset for asset in assets}


def verify_assets(release: dict, expected: dict[str, tuple[Path, str]], *, token=None) -> None:
    assets = release_assets(release)
    if set(assets) != set(expected):
        missing = sorted(set(expected) - set(assets))
        unexpected = sorted(set(assets) - set(expected))
        raise SystemExit(f"FAIL Release asset set differs missing={missing} unexpected={unexpected}")
    for name, (_, local_sha) in expected.items():
        remote_sha = download_sha(assets[name]["browser_download_url"], token)
        if remote_sha != local_sha:
            raise SystemExit(
                f"FAIL existing asset differs: {name} local={local_sha} remote={remote_sha}"
            )


def patch_release(api_base: str, repo: str, release_id: int, token: str, **changes) -> dict:
    _, updated = request_json(
        f"{api_base}/repos/{repo}/releases/{release_id}", token,
        data=payload(**changes), method="PATCH",
    )
    return updated


def upload_asset(api_base: str, repo: str, release_id: int, token: str, artifact: Path) -> None:
    upload = (
        f"{api_base}/repos/{repo}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(artifact.name)}"
    )
    # curl streams multipart bytes.  The credential is read from a protected
    # stdin config, never placed in argv, the environment, or normal output.
    subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "1800",
         "--config", "-", "-F", f"attachment=@{artifact}", upload],
        input=f'header = "Authorization: token {token}"\n'.encode(),
        check=True, stdout=subprocess.DEVNULL,
    )


def publish(args, token: str) -> None:
    refs = subprocess.check_output(
        ["git", "ls-remote", args.git_url, f"refs/tags/{args.tag}",
         f"refs/tags/{args.tag}^{{}}"], text=True,
    )
    resolved = [line.split()[0] for line in refs.splitlines() if line.strip()]
    if not resolved or args.commit not in resolved:
        raise SystemExit(f"FAIL tag {args.tag} does not resolve to exact product commit {args.commit}")

    artifacts = [path.resolve(strict=True) for path in args.artifact]
    names = [path.name for path in artifacts]
    if len(names) != len(set(names)):
        raise SystemExit("FAIL requested artifacts contain duplicate basenames")
    expected = {path.name: (path, sha256_file(path)) for path in artifacts}
    release_url = (
        f"{args.api_base}/repos/{args.repo}/releases/tags/{urllib.parse.quote(args.tag)}"
    )
    status, release = request_json(release_url, token)
    if status == 404:
        _, release = request_json(
            f"{args.api_base}/repos/{args.repo}/releases", token,
            data=payload(tag_name=args.tag, target_commitish=args.commit,
                         name=args.title or args.tag, body=args.body,
                         draft=True, prerelease=False), method="POST",
        )
    elif not release.get("draft"):
        # A complete public Release is the mutation-free idempotent exit.  A
        # matching subset is closed to draft, completed, and republished;
        # conflicting or unexpected public assets fail closed as draft.
        try:
            public_status, public_release = request_json(release_url, token=None)
            if public_status != 200 or public_release.get("draft"):
                raise SystemExit("FAIL anonymous Release metadata readback failed")
            public_assets = release_assets(public_release)
            unexpected = sorted(set(public_assets) - set(expected))
            if unexpected:
                raise SystemExit(f"FAIL public Release contains unexpected assets: {unexpected}")
            for name, asset in public_assets.items():
                remote = download_sha(asset["browser_download_url"], token=None)
                if remote != expected[name][1]:
                    raise SystemExit(
                        f"FAIL public asset differs: {name} "
                        f"local={expected[name][1]} remote={remote}"
                    )
            if set(public_assets) == set(expected):
                print(f"PASS release-idempotent assets={len(expected)} "
                      f"tag={args.tag} commit={args.commit}")
                return
        except BaseException:
            # Never mutate a public Release without first closing the partial
            # publication window.  Any later failure leaves it draft.
            release = patch_release(args.api_base, args.repo, release["id"], token, draft=True)
            raise
        release = patch_release(args.api_base, args.repo, release["id"], token, draft=True)

    # From here onward the Release must remain draft until the full exact set
    # is present.  Unexpected or conflicting assets fail closed as draft.
    if not release.get("draft"):
        release = patch_release(args.api_base, args.repo, release["id"], token, draft=True)
    existing = release_assets(release)
    unexpected = sorted(set(existing) - set(expected))
    if unexpected:
        raise SystemExit(f"FAIL draft Release contains unexpected assets: {unexpected}")
    for name, asset in existing.items():
        remote = download_sha(asset["browser_download_url"], token)
        if remote != expected[name][1]:
            raise SystemExit(
                f"FAIL existing draft asset differs: {name} local={expected[name][1]} remote={remote}"
            )
    for name, (artifact, _) in expected.items():
        if name not in existing:
            upload_asset(args.api_base, args.repo, release["id"], token, artifact)

    # Refresh, verify the complete draft with auth, then publish atomically.
    _, release = request_json(release_url, token)
    verify_assets(release, expected, token=token)
    release = patch_release(
        args.api_base, args.repo, release["id"], token,
        name=args.title or args.tag, body=args.body, draft=False, prerelease=False,
    )
    if release.get("draft"):
        raise SystemExit("FAIL Release API did not publish the fully verified draft")

    # Both metadata and bytes must now be reachable with no Authorization.
    try:
        public_status, public_release = request_json(release_url, token=None)
        if public_status != 200 or public_release.get("draft"):
            raise SystemExit("FAIL anonymous Release metadata readback failed")
        verify_assets(public_release, expected, token=None)
    except BaseException:
        # Public-but-unreadable is not a completed Release.  Close it again so
        # a CDN/API failure cannot leave a half-verified public object.
        patch_release(args.api_base, args.repo, release["id"], token, draft=True)
        raise
    for name, (_, digest) in expected.items():
        print(f"PASS public-asset name={name} sha256={digest}")
    print(f"PASS release assets={len(expected)} tag={args.tag} commit={args.commit}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="https://feicode.com/api/v1")
    parser.add_argument("--repo", default="WenPai-org/wordpress-playground")
    parser.add_argument("--git-url", default="https://feicode.com/WenPai-org/wordpress-playground.git")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--title")
    parser.add_argument("--body", default="Immutable WenPai WordPress Playground runtime release.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    token = os.environ.get("FEICODE_TOKEN")
    if not token:
        raise SystemExit("BLOCKED FEICODE_TOKEN is absent")
    publish(args, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
