#!/usr/bin/env python3
import argparse
from pathlib import Path
from manifest import digest_inputs, write_json

DEFAULTS = ["config", "overlays", "tools/apply-overlay.py", "tools/build-runtime.py",
            "tools/localization_overlay.py", "tools/localization_scan.py",
            "tools/manifest.py", "tools/security-scan.py"]
parser = argparse.ArgumentParser(description="Hash every governed transform/build input")
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--input", action="append", dest="inputs")
parser.add_argument("--output", "-o", type=Path)
args = parser.parse_args()
result = digest_inputs(args.root, args.inputs or DEFAULTS)
if args.output:
    write_json(args.output, result)
print(result["transform_sha256"])
print(f"PASS transform-digest samples={result['input_count']}")
