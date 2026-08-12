#!/usr/bin/env python3
"""Canonicalize transient declaration-offset aliases before bundling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from manifest import sha256_file, write_json


parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", "-o", type=Path)
args = parser.parse_args()

source = args.source.resolve(strict=True)
pattern = re.compile(r"alias-(?:[0-9]+-)+[0-9]+")
targets = [
    source / "packages/playground/blueprints/public/blueprint-schema.json",
    source / "packages/playground/blueprints/public/blueprint-v2-schema-validator.js",
]
files = []
total_aliases = 0
for target in targets:
    before_sha = sha256_file(target)
    code = target.read_text()
    aliases: dict[str, str] = {}

    def stable_alias(match: re.Match[str]) -> str:
        alias = match.group(0)
        if alias not in aliases:
            aliases[alias] = f"alias-wenpai-{len(aliases) + 1:04d}"
        return aliases[alias]

    normalized = pattern.sub(stable_alias, code)
    existing = set(re.findall(r"alias-wenpai-[0-9]{4}", code))
    if not aliases and not existing:
        raise SystemExit(f"BLOCKED {target.name} contains no governed aliases")
    if aliases:
        target.write_text(normalized)
    if pattern.search(target.read_text()):
        raise SystemExit(f"FAIL numeric Blueprint aliases remain in {target.name}")
    samples = len(aliases) or len(existing)
    total_aliases += samples
    files.append({
        "path": target.relative_to(source).as_posix(),
        "result": "normalized" if aliases else "already-normalized",
        "alias_samples": samples,
        "before_sha256": before_sha,
        "after_sha256": sha256_file(target),
    })

report = {
    "schema": "wenpai-blueprint-validator-normalization/v1",
    "status": "PASS",
    "result": "normalized" if any(item["result"] == "normalized" for item in files) else "already-normalized",
    "file_samples": len(files),
    "alias_samples": total_aliases,
    "files": files,
    "contract": "first-seen stable alias sequence; every definition/reference token is rewritten together",
}
if args.output:
    write_json(args.output, report)
print(json.dumps(report, sort_keys=True))
print(f"PASS blueprint-validator-normalization files={len(files)} "
      f"aliases={report['alias_samples']} result={report['result']}")
