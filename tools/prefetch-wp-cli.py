#!/usr/bin/env python3
"""Fetch the exact locked WP-CLI payload before expensive website builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from manifest import write_json


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--report", type=Path)
parser.add_argument("--lock", type=Path, default=ROOT / "upstream-lock.json")
args = parser.parse_args()

lock = json.loads(args.lock.read_text())
wp_cli = lock["generated_assets"]["wp_cli"]
required = ("repository", "commit", "url", "sha256", "gzip_sha256")
missing = [field for field in required if not wp_cli.get(field)]
if missing:
    raise SystemExit(f"BLOCKED incomplete wp_cli lock fields={','.join(missing)}")
commit = wp_cli["commit"]
if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
    raise SystemExit(f"BLOCKED wp_cli commit is not an exact lowercase SHA: {commit}")
if commit not in wp_cli["url"]:
    raise SystemExit("BLOCKED wp_cli URL is not pinned to the locked commit")

output = args.output.resolve()
output.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
os.close(fd)
temporary_path = Path(temporary)
try:
    subprocess.run([
        "curl", "--fail", "--location", "--silent", "--show-error",
        "--retry", "5", "--retry-all-errors", "--retry-delay", "5",
        "--connect-timeout", "30", "--max-time", "600",
        "--user-agent", "WenPai-Release/1", "--output", str(temporary_path),
        wp_cli["url"],
    ], check=True)
    payload_sha = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
    if payload_sha != wp_cli["sha256"]:
        raise SystemExit(
            f"BLOCKED pinned WP-CLI payload mismatch expected={wp_cli['sha256']} actual={payload_sha}"
        )
    os.chmod(temporary_path, 0o644)
    os.replace(temporary_path, output)
finally:
    temporary_path.unlink(missing_ok=True)

report = {
    "schema": "wenpai-prefetched-wp-cli/v1",
    "status": "PASS",
    "repository": wp_cli["repository"],
    "commit": commit,
    "url": wp_cli["url"],
    "sha256": wp_cli["sha256"],
    "bytes": output.stat().st_size,
    "gzip_sha256": wp_cli["gzip_sha256"],
    "consumer": "normalize-runtime.py --wp-cli-payload",
}
if args.report:
    write_json(args.report, report)
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
print(f"PASS prefetched-wp-cli samples=1 bytes={report['bytes']} sha256={report['sha256']}")
