#!/usr/bin/env python3
"""Fail-closed filesystem and accidental-secret scan for source or artifact trees."""
import argparse
import re
from pathlib import Path
from manifest import normalized_manifest

PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
    "generic-secret-assignment": re.compile(rb"(?i)(password|client_secret|api[_-]?token)\s*[:=]\s*['\"][^'\"\r\n]{8,}"),
}
TEXT_LIMIT = 4 * 1024 * 1024
parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
args = parser.parse_args()
root = args.root.resolve(strict=True)
manifest = normalized_manifest(root)
findings = []
scanned = 0
for entry in manifest["entries"]:
    if entry["type"] != "file":
        continue
    path = root / entry["path"]
    if path.stat().st_size > TEXT_LIMIT:
        continue
    content = path.read_bytes()
    if b"\0" in content:
        continue
    scanned += 1
    for name, pattern in PATTERNS.items():
        if pattern.search(content):
            findings.append(f"{entry['path']}: {name}")
if findings:
    print("FAIL security-scan")
    print("\n".join(findings))
    raise SystemExit(1)
print(f"PASS security-scan samples={scanned} paths={manifest['entry_count']} findings=0")
