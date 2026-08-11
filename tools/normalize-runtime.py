#!/usr/bin/env python3
"""Normalize documented build-only entropy and pin fetched runtime assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

from manifest import sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--runtime", type=Path, required=True)
parser.add_argument("--lock", type=Path, default=ROOT / "upstream-lock.json")
parser.add_argument("--output", "-o", type=Path)
args = parser.parse_args()

runtime = args.runtime.resolve(strict=True)
locked = json.loads(args.lock.read_text())["generated_assets"]
toolchain = json.loads(args.lock.read_text())["toolchain"]
wp_cli = locked["wp_cli"]
php_next = locked["php_next"]
if not wp_cli.get("gzip_sha256"):
    raise SystemExit("BLOCKED wp_cli.gzip_sha256 lock is required")
gzip_version = subprocess.run(["gzip", "--version"], check=True,
                              stdout=subprocess.PIPE, text=True).stdout.splitlines()[0].split()[-1]
if gzip_version != toolchain.get("gzip"):
    raise SystemExit(f"BLOCKED gzip version mismatch expected={toolchain.get('gzip')} actual={gzip_version}")

request = urllib.request.Request(wp_cli["url"], headers={"User-Agent": "WenPai-Release/1"})
with urllib.request.urlopen(request, timeout=60) as response:
    payload = response.read()
raw_sha = hashlib.sha256(payload).hexdigest()
if raw_sha != wp_cli["sha256"]:
    raise SystemExit(f"BLOCKED pinned WP-CLI payload mismatch expected={wp_cli['sha256']} actual={raw_sha}")
(runtime / "wp-cli.phar").write_bytes(payload)
compressed = subprocess.run(["gzip", "-n", "-c", "-9"], input=payload,
                            check=True, stdout=subprocess.PIPE).stdout
gzip_sha = hashlib.sha256(compressed).hexdigest()
if gzip_sha != wp_cli["gzip_sha256"]:
    raise SystemExit(f"BLOCKED deterministic WP-CLI gzip mismatch expected={wp_cli['gzip_sha256']} actual={gzip_sha}")
(runtime / "wp-cli.phar.gz").write_bytes(compressed)

wasm_paths = {
    "asyncify": runtime / "php-next/asyncify/8_6_0-dev/php_8_6.wasm",
    "jspi": runtime / "php-next/jspi/8_6_0-dev/php_8_6.wasm",
}
for flavor, path in wasm_paths.items():
    if not path.is_file() or sha256_file(path) != php_next["wasm_sha256"][flavor]:
        raise SystemExit(f"BLOCKED php-next {flavor} runtime payload mismatch")

# Rollup reference IDs are build bookkeeping, but Vite embeds them in
# sourcemap sourcesContent before resolving the corresponding runtime URL.
# They have no executable effect.  Normalize only that exact token form and
# record every touched map; all JS/CSS/WASM/HTML payload bytes remain covered
# by the ordinary runtime manifest comparison.
vite_reference = re.compile(r"__VITE_ASSET__[\w$]+__")
normalized_maps = []
normalized_tokens = 0
for path in sorted(runtime.rglob("*.map"), key=lambda item: item.as_posix().encode()):
    text = path.read_text(errors="strict")
    replaced, count = vite_reference.subn("__VITE_ASSET__NORMALIZED__", text)
    if not count:
        continue
    path.write_text(replaced)
    normalized_maps.append(path.relative_to(runtime).as_posix())
    normalized_tokens += count

report = {
    "schema": "wenpai-runtime-normalization/v1",
    "status": "PASS",
    "wp_cli": {"commit": wp_cli["commit"], "sha256": raw_sha, "gzip_version": gzip_version,
               "gzip_sha256": gzip_sha},
    "php_next": {"commit": php_next["commit"], "wasm_samples": len(wasm_paths)},
    "sourcemap_reference_normalization": {
        "pattern": "__VITE_ASSET__[A-Za-z0-9_$]+__",
        "replacement": "__VITE_ASSET__NORMALIZED__",
        "map_samples": len(normalized_maps),
        "token_samples": normalized_tokens,
        "paths": normalized_maps,
        "scope": "source maps only; executable payloads are not rewritten",
    },
}
if args.output:
    write_json(args.output, report)
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
print(f"PASS runtime-normalization maps={len(normalized_maps)} tokens={normalized_tokens} "
      f"php-next-wasm={len(wasm_paths)} wp-cli=1")
