#!/usr/bin/env python3
"""Build and archive a WenPai runtime from an already transformed source tree."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
from manifest import normalized_manifest, sha256_file, write_json

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True, help="transformed source worktree")
parser.add_argument("--runtime-dir", type=Path, required=True, help="runtime output, relative to source or absolute")
parser.add_argument("--out-dir", type=Path, default=repo / "dist")
parser.add_argument("--version", required=True)
parser.add_argument("--source-sha", required=True)
parser.add_argument("--transform-sha", required=True)
parser.add_argument("--product-commit", default="WORKTREE")
parser.add_argument("--source-date-epoch", type=int, required=True)
parser.add_argument("--command", help="explicit upstream build command; omitted means archive existing runtime-dir")
parser.add_argument("--package-lock", type=Path)
args = parser.parse_args()

source = args.source.resolve(strict=True)
if args.command:
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(args.source_date_epoch), TZ="UTC", LC_ALL="C")
    subprocess.run(shlex.split(args.command), cwd=source, env=environment, check=True)
runtime = args.runtime_dir if args.runtime_dir.is_absolute() else source / args.runtime_dir
runtime = runtime.resolve(strict=True)
if source not in runtime.parents and source != runtime:
    raise SystemExit("FAIL runtime-dir must be contained in transformed source")

runtime_manifest = normalized_manifest(runtime)
sbom_packages = []
lock = args.package_lock
if lock:
    lock = lock if lock.is_absolute() else source / lock
    data = json.loads(lock.read_text())
    for path, package in sorted(data.get("packages", {}).items()):
        if not path or not isinstance(package, dict):
            continue
        sbom_packages.append({"path": path, "name": package.get("name") or path.rsplit("/", 1)[-1],
                              "version": package.get("version", "UNKNOWN"),
                              "license": package.get("license", "UNKNOWN")})
sbom = {"schema": "wenpai-sbom-summary/v1", "format": "npm-package-lock-summary",
        "package_count": len(sbom_packages), "packages": sbom_packages,
        "limitations": "Summary only; transitive license and binary provenance require release audit."}

metadata = {"schema": "wenpai-playground-runtime/v1", "version": args.version,
            "upstream_source_sha256": args.source_sha, "transform_sha256": args.transform_sha,
            "product_commit": args.product_commit, "source_date_epoch": args.source_date_epoch,
            "build_time_semantics": "SOURCE_DATE_EPOCH; not wall-clock time",
            "runtime_manifest_sha256": runtime_manifest["manifest_sha256"],
            "runtime_entry_count": runtime_manifest["entry_count"], "artifact_sha256": None,
            "artifact_sha256_semantics": "null inside artifact; authoritative value is sidecar"}

out = args.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
name = f"wenpai-wordpress-playground-{args.version}.tar.gz"
artifact = out / name
members = [("runtime-manifest.json", json.dumps(runtime_manifest, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n"),
           ("runtime.json", json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n"),
           ("sbom-summary.json", json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n")]
for entry in runtime_manifest["entries"]:
    members.append((f"runtime/{entry['path']}", None))

with artifact.open("wb") as raw:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=args.source_date_epoch, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for arcname, content in sorted(members, key=lambda item: item[0].encode()):
                info = tarfile.TarInfo(arcname)
                info.mtime = args.source_date_epoch
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                if content is not None:
                    info.mode, info.size = 0o644, len(content)
                    archive.addfile(info, io.BytesIO(content))
                    continue
                relative = arcname.removeprefix("runtime/")
                path = runtime / relative
                if path.is_dir():
                    info.type, info.mode, info.size = tarfile.DIRTYPE, 0o755, 0
                    archive.addfile(info)
                else:
                    info.mode, info.size = (0o755 if os.access(path, os.X_OK) else 0o644), path.stat().st_size
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)

digest = sha256_file(artifact)
(out / f"{name}.sha256").write_text(f"{digest}  {name}\n")
write_json(out / "runtime-manifest.json", runtime_manifest)
write_json(out / "runtime.json", metadata | {"artifact_sha256": digest})
write_json(out / "sbom-summary.json", sbom)
print(f"PASS runtime-build samples={runtime_manifest['entry_count']} packages={len(sbom_packages)} artifact={artifact} sha256={digest}")
