#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
from manifest import digest_inputs, write_json

DEFAULTS = [".forgejo/workflows", "config", "overlays", "tests",
            "LICENSE", "NOTICE", "UPSTREAM.md", "ROLLBACK.md", "docs/licenses",
            "tools/apply-overlay.py", "tools/build-runtime.py",
            "tools/localization_overlay.py", "tools/localization_scan.py",
            "tools/manifest.py", "tools/security-scan.py", "tools/license-notice-audit.py",
            "tools/release.py", "tools/stable-watcher.py",
            "tools/sync-generated-assets.py", "tools/compare-runtime-builds.py",
            "tools/restore-upstream-generated-assets.py",
            "tools/prefetch-wp-cli.py",
            "tools/normalize-runtime.py", "tools/normalize-blueprint-validator.py",
            "tools/deterministic-node-build.cjs", "tools/transform-hash.py"]
parser = argparse.ArgumentParser(description="Hash every governed transform/build input")
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--input", action="append", dest="inputs")
parser.add_argument("--output", "-o", type=Path)
args = parser.parse_args()
inputs = args.inputs or DEFAULTS
result = digest_inputs(args.root, inputs)
if args.inputs is None:
    # The lock is itself a governed input, but its downstream digest field is
    # the output of this calculation. Hash a canonical sentinel there to avoid
    # an impossible self-referential fixed point while covering every other
    # upstream/generated-asset/toolchain field.
    lock = json.loads((args.root / "upstream-lock.json").read_text())
    lock["downstream"]["transform_sha256"] = "SELF"
    encoded_lock = json.dumps(lock, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")).encode()
    result["inputs"].append({
        "path": "upstream-lock.json#downstream.transform_sha256=SELF",
        "sha256": hashlib.sha256(encoded_lock).hexdigest(),
    })
    result["inputs"].sort(key=lambda item: item["path"])
    encoded = json.dumps(result["inputs"], sort_keys=True,
                         separators=(",", ":")).encode()
    result["input_count"] = len(result["inputs"])
    result["transform_sha256"] = hashlib.sha256(encoded).hexdigest()
if args.output:
    write_json(args.output, result)
print(result["transform_sha256"])
print(f"PASS transform-digest samples={result['input_count']}")
