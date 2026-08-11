#!/usr/bin/env python3
"""Materialize an exact upstream tree and apply the small downstream overlay."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from manifest import normalized_manifest, write_json

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--upstream", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--overlay", type=Path, default=repo / "overlays")
parser.add_argument("--report", type=Path)
args = parser.parse_args()

upstream = args.upstream.resolve(strict=True)
output = args.output.resolve()
overlay = args.overlay.resolve(strict=True)
if output.exists():
    raise SystemExit(f"FAIL output already exists (refusing overwrite): {output}")
if upstream == output or upstream in output.parents or output in upstream.parents:
    raise SystemExit("FAIL input/output trees must not contain one another")

source = normalized_manifest(upstream, symlinks="internal")
shutil.copytree(upstream, output, symlinks=True, ignore=shutil.ignore_patterns(".git", "node_modules", ".cache"))
changed: list[str] = []

patches = sorted((overlay / "patches").glob("*.patch")) if (overlay / "patches").is_dir() else []
for patch in patches:
    subprocess.run(["git", "apply", "--no-index", "--check", "--whitespace=error-all", str(patch)], cwd=output, check=True)
    subprocess.run(["git", "apply", "--no-index", "--whitespace=error-all", str(patch)], cwd=output, check=True)
    changed.append(f"patch:{patch.name}")

localization_tool = repo / "tools" / "localization_overlay.py"
scan_tool = repo / "tools" / "localization_scan.py"
apply_run = subprocess.run([sys.executable, str(localization_tool), "apply", "--source-root", str(output)],
                           check=True, text=True, capture_output=True)
apply_result = json.loads(apply_run.stdout)
subprocess.run([sys.executable, str(localization_tool), "check", "--source-root", str(output)], check=True)
subprocess.run([sys.executable, str(scan_tool), "--source-root", str(output)], check=True)
changed.extend([f"localization:{index + 1}" for index in range(apply_result["changed"])])
changed.extend([f"overlay-file:{index + 1}" for index in range(apply_result["overlayFiles"])])

result = normalized_manifest(output, symlinks="internal")
report = {"schema": "wenpai-overlay-report/v1", "source_sha256": source["manifest_sha256"],
          "result_sha256": result["manifest_sha256"], "source_entries": source["entry_count"],
          "result_entries": result["entry_count"], "changed": changed, "changed_count": len(changed)}
if args.report:
    write_json(args.report, report)
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
print(f"PASS apply-overlay samples={len(changed)} source_entries={source['entry_count']}")
