#!/usr/bin/env python3
"""Materialize immutable generated assets declared by upstream-lock.json."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from manifest import normalized_manifest, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True,
                    help="exact upstream checkout whose website/public tree receives the assets")
parser.add_argument("--lock", type=Path, default=ROOT / "upstream-lock.json")
parser.add_argument("--report", type=Path)
args = parser.parse_args()

source = args.source.resolve(strict=True)
locked = json.loads(args.lock.read_text())["generated_assets"]["php_next"]
canonical_repository = locked["repository"]
repository = locked.get("mirror_repository", canonical_repository)
branch = locked["branch"]
commit = locked["commit"]
mirror_ref = locked.get("mirror_ref", commit)
target = source / "packages/playground/website/public/php-next"


def run(command: list[str], *, stdout=None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=source, check=True, stdout=stdout,
                          stderr=subprocess.PIPE)


with tempfile.TemporaryDirectory(prefix="wenpai-php-next-", dir=source.parent) as temporary:
    temporary = Path(temporary)
    bare = temporary / "assets.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # Consume the immutable commit, not the moving branch head. The latter is
    # observed for candidate/watcher reporting only and must not invalidate an
    # already locked, still reachable release input.
    fetch = subprocess.run(
        ["git", "-C", str(bare), "fetch", "--depth=1", repository, commit],
        text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if fetch.returncode:
        detail = fetch.stderr.strip().splitlines()[-1] if fetch.stderr.strip() else "no diagnostic"
        raise SystemExit(f"BLOCKED php-next exact commit fetch failed: {detail}")
    resolved = subprocess.check_output(["git", "-C", str(bare), "rev-parse", "FETCH_HEAD"],
                                       text=True).strip()
    if resolved != commit:
        raise SystemExit(f"BLOCKED php-next exact commit mismatch expected={commit} actual={resolved}")
    mirror_line = subprocess.check_output(
        ["git", "ls-remote", repository, mirror_ref], text=True
    ).strip()
    mirror_head = mirror_line.split()[0] if mirror_line else None
    if mirror_head != commit:
        raise SystemExit(
            f"BLOCKED php-next mirror ref mismatch expected={commit} actual={mirror_head}"
        )
    archive = subprocess.check_output(["git", "-C", str(bare), "archive", commit])
    extracted = temporary / "tree"
    extracted.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise SystemExit(f"BLOCKED unsafe generated asset path: {member.name}")
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise SystemExit(f"BLOCKED unsupported generated asset member: {member.name}")
            destination = extracted.joinpath(*path.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                destination.chmod(member.mode & 0o777)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(member) as input_file, destination.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)
            destination.chmod(member.mode & 0o777)

    manifest = normalized_manifest(extracted)
    if manifest["entry_count"] != locked["manifest_entries"]:
        raise SystemExit("BLOCKED php-next manifest entry count mismatch")
    if manifest["manifest_sha256"] != locked["manifest_sha256"]:
        raise SystemExit("BLOCKED php-next normalized manifest mismatch")
    wasm = {
        "asyncify": extracted / "asyncify/8_6_0-dev/php_8_6.wasm",
        "jspi": extracted / "jspi/8_6_0-dev/php_8_6.wasm",
    }
    wasm_hashes = {}
    for flavor, path in wasm.items():
        actual = sha256_file(path)
        wasm_hashes[flavor] = actual
        if actual != locked["wasm_sha256"][flavor]:
            raise SystemExit(f"BLOCKED php-next {flavor} WASM mismatch")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(extracted, target)

report = {
    "schema": "wenpai-generated-assets-sync/v1",
    "status": "PASS",
    "asset": "php-next",
    "canonical_repository": canonical_repository,
    "repository": repository,
    "branch": branch,
    "mirror_ref": mirror_ref,
    "mirror_ref_head": mirror_head,
    "commit": commit,
    "target": target.relative_to(source).as_posix(),
    "manifest_entries": manifest["entry_count"],
    "manifest_sha256": manifest["manifest_sha256"],
    "wasm_sha256": wasm_hashes,
}
if args.report:
    write_json(args.report, report)
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
print(f"PASS generated-assets samples={manifest['entry_count']} wasm={len(wasm)} commit={commit}")
