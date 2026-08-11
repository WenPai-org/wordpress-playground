#!/usr/bin/env python3
import argparse
from pathlib import Path
from manifest import normalized_manifest, write_json

parser = argparse.ArgumentParser(description="Create a normalized source manifest")
parser.add_argument("root", type=Path)
parser.add_argument("--output", "-o", type=Path, required=True)
parser.add_argument("--allow-internal-symlinks", action="store_true")
args = parser.parse_args()
result = normalized_manifest(args.root, symlinks="internal" if args.allow_internal_symlinks else "reject")
write_json(args.output, result)
print(f"PASS source-manifest samples={result['entry_count']} sha256={result['manifest_sha256']}")
