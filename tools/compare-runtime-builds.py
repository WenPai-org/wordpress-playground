#!/usr/bin/env python3
"""Fail closed unless two independent runtime builds and artifacts are exact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from manifest import sha256_file, write_json


parser = argparse.ArgumentParser()
parser.add_argument("--manifest-a", type=Path, required=True)
parser.add_argument("--manifest-b", type=Path, required=True)
parser.add_argument("--artifact-a", type=Path)
parser.add_argument("--artifact-b", type=Path)
parser.add_argument("--output", "-o", type=Path)
args = parser.parse_args()

a = json.loads(args.manifest_a.read_text())
b = json.loads(args.manifest_b.read_text())
for label, manifest in (("a", a), ("b", b)):
    if manifest.get("entry_count", 0) <= 0 or not manifest.get("entries"):
        raise SystemExit(f"FAIL build {label} has zero runtime samples")

entries_a = {entry["path"]: entry for entry in a["entries"]}
entries_b = {entry["path"]: entry for entry in b["entries"]}
only_a = sorted(set(entries_a) - set(entries_b))
only_b = sorted(set(entries_b) - set(entries_a))
changed = sorted(path for path in set(entries_a) & set(entries_b)
                 if entries_a[path] != entries_b[path])

artifact = None
if bool(args.artifact_a) != bool(args.artifact_b):
    raise SystemExit("FAIL both artifacts are required for byte comparison")
if args.artifact_a:
    digest_a = sha256_file(args.artifact_a)
    digest_b = sha256_file(args.artifact_b)
    artifact = {
        "a_sha256": digest_a,
        "b_sha256": digest_b,
        "a_size": args.artifact_a.stat().st_size,
        "b_size": args.artifact_b.stat().st_size,
        "byte_identical": digest_a == digest_b and
                          args.artifact_a.stat().st_size == args.artifact_b.stat().st_size,
    }

exact = not only_a and not only_b and not changed and (
    artifact is None or artifact["byte_identical"]
)
result = {
    "schema": "wenpai-build-determinism/v1",
    "status": "PASS" if exact else "FAIL",
    "build_a": {"entry_count": a["entry_count"],
                "manifest_sha256": a["manifest_sha256"]},
    "build_b": {"entry_count": b["entry_count"],
                "manifest_sha256": b["manifest_sha256"]},
    "differences": {"only_a": only_a, "only_b": only_b, "changed": changed},
    "artifact": artifact,
}
if args.output:
    write_json(args.output, result)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
if not exact:
    raise SystemExit("FAIL independent runtime builds are not byte-identical")
print(f"PASS build-determinism samples={a['entry_count']} artifacts={1 if artifact else 0}")
