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
import shutil
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
parser.add_argument("--notice-audit", type=Path, action="append", default=[],
                    help="validated license-notice audit JSON to embed; repeatable")
parser.add_argument("--node-notices", type=Path,
                    help="validated Node license notice JSON to embed")
parser.add_argument("--max-attachment-bytes", type=int, default=2_000_000_000,
                    help="split the compressed tar when it exceeds the Forgejo attachment ceiling")
parser.add_argument("--enforce-generated-assets", action="store_true",
                    help="verify immutable PHP-next and WP-CLI payloads from upstream-lock.json")
args = parser.parse_args()

source = args.source.resolve(strict=True)
if args.command:
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(args.source_date_epoch), TZ="UTC", LC_ALL="C")
    subprocess.run(shlex.split(args.command), cwd=source, env=environment, check=True)
runtime = args.runtime_dir if args.runtime_dir.is_absolute() else source / args.runtime_dir
runtime = runtime.resolve(strict=True)
if source not in runtime.parents and source != runtime:
    raise SystemExit("FAIL runtime-dir must be contained in transformed source")

if args.enforce_generated_assets:
    generated_assets = json.loads((repo / "upstream-lock.json").read_text()).get("generated_assets", {})
    php_next = generated_assets.get("php_next")
    wp_cli = generated_assets.get("wp_cli")
    if not php_next or not wp_cli:
        raise SystemExit("BLOCKED immutable php_next/wp_cli generated-asset locks are required")
    php_wasm = {
        "asyncify": runtime / "php-next/asyncify/8_6_0-dev/php_8_6.wasm",
        "jspi": runtime / "php-next/jspi/8_6_0-dev/php_8_6.wasm",
    }
    for flavor, path in php_wasm.items():
        if not path.is_file() or sha256_file(path) != php_next["wasm_sha256"][flavor]:
            raise SystemExit(f"BLOCKED runtime php-next {flavor} does not match the lock")
    wp_cli_path = runtime / "wp-cli.phar"
    if not wp_cli_path.is_file() or sha256_file(wp_cli_path) != wp_cli["sha256"]:
        raise SystemExit("BLOCKED runtime wp-cli.phar does not match the lock")
    wp_cli_gzip_path = runtime / "wp-cli.phar.gz"
    if not wp_cli_gzip_path.is_file() or sha256_file(wp_cli_gzip_path) != wp_cli["gzip_sha256"]:
        raise SystemExit("BLOCKED runtime wp-cli.phar.gz does not match the deterministic lock")

source_runtime_manifest = normalized_manifest(runtime)
if not (runtime / "index.html").is_file():
    raise SystemExit("BLOCKED upstream runtime entrypoint index.html is missing")
if (runtime / "playground.html").exists():
    raise SystemExit("BLOCKED runtime already contains playground.html; entrypoint mapping would collide")

# The public site owns /index.html.  The immutable product artifact therefore
# maps the upstream runtime entrypoint before archiving, rather than renaming a
# file ad hoc during deployment.
entrypoint_mapping = {"index.html": "playground.html"}
runtime_entries = []
for entry in source_runtime_manifest["entries"]:
    mapped = dict(entry)
    mapped["path"] = entrypoint_mapping.get(entry["path"], entry["path"])
    runtime_entries.append(mapped)
runtime_entries.sort(key=lambda item: item["path"].encode("utf-8"))
canonical_entries = json.dumps(runtime_entries, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
runtime_manifest = {
    **{key: value for key, value in source_runtime_manifest.items()
       if key not in {"entries", "entry_count", "manifest_sha256"}},
    "entry_count": len(runtime_entries),
    "manifest_sha256": hashlib.sha256(canonical_entries).hexdigest(),
    "entrypoint_mapping": entrypoint_mapping,
    "entries": runtime_entries,
}
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
            "entrypoints": {"website": "playground.html", "remote": "remote.html"},
            "entrypoint_mapping": entrypoint_mapping,
            "artifact_sha256_semantics": "null inside artifact; authoritative value is sidecar"}

out = args.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
name = f"wenpai-wordpress-playground-{args.version}.tar.gz"
artifact = out / name
members = [("runtime-manifest.json", json.dumps(runtime_manifest, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n"),
           ("runtime.json", json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n"),
           ("sbom-summary.json", json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True).encode()+b"\n")]
product_root = Path(__file__).resolve().parents[1]
for notice_name in ("LICENSE", "NOTICE", "UPSTREAM.md", "ROLLBACK.md", "upstream-lock.json"):
    notice_path = product_root / notice_name
    if not notice_path.is_file():
        raise SystemExit(f"BLOCKED required attribution file missing: {notice_name}")
    members.append((notice_name, notice_path.read_bytes()))
license_root = product_root / "docs/licenses"
required_license_files = {
    "README.md", "THIRD_PARTY_NOTICES.md", "third-party-inventory.json",
    "sbom-notice-metadata.json", "LICENSE_TEXTS.sha256",
}
present_license_files = {p.name for p in license_root.iterdir() if p.is_file()} if license_root.is_dir() else set()
missing_license_files = required_license_files - present_license_files
if missing_license_files:
    raise SystemExit(f"BLOCKED required license inventory files missing: {sorted(missing_license_files)}")
license_members = []
for notice_path in sorted((p for p in license_root.rglob("*") if p.is_file()),
                          key=lambda p: p.relative_to(product_root).as_posix().encode()):
    arcname = notice_path.relative_to(product_root).as_posix()
    members.append((arcname, notice_path.read_bytes()))
    license_members.append({"path": arcname, "sha256": sha256_file(notice_path)})
audit_members = []
for audit_path in args.notice_audit:
    audit_path = audit_path.resolve(strict=True)
    audit = json.loads(audit_path.read_text())
    if audit.get("status") != "PASS":
        raise SystemExit(f"BLOCKED notice audit is not PASS: {audit_path}")
    arcname = f"evidence/{audit_path.name}"
    members.append((arcname, audit_path.read_bytes()))
    audit_members.append({"path": arcname, "sha256": sha256_file(audit_path)})
if args.node_notices:
    node_notices_path = args.node_notices.resolve(strict=True)
    node_notices = json.loads(node_notices_path.read_text())
    if not node_notices.get("package_samples"):
        raise SystemExit("BLOCKED Node notice metadata has zero package samples")
    audited_packages = {item["path"]: item for item in node_notices.get("packages", [])}
    for package in sbom_packages:
        audited = audited_packages.get(package["path"])
        if audited:
            package["license"] = audited["license"]
            package["license_basis"] = audited.get("basis", "node-notice-audit")
    unknown = [item["path"] for item in sbom_packages if item["license"] == "UNKNOWN"]
    if unknown:
        raise SystemExit(f"BLOCKED SBOM contains UNKNOWN Node licenses: {unknown[:5]}")
    arcname = f"evidence/{node_notices_path.name}"
    members.append((arcname, node_notices_path.read_bytes()))
    audit_members.append({"path": arcname, "sha256": sha256_file(node_notices_path)})
metadata["license_notice_files"] = license_members
metadata["license_audit_files"] = audit_members
sbom["notice_metadata"] = {
    "inventory": "docs/licenses/third-party-inventory.json",
    "inventory_sha256": sha256_file(license_root / "third-party-inventory.json"),
    "human_notices": "docs/licenses/THIRD_PARTY_NOTICES.md",
    "human_notices_sha256": sha256_file(license_root / "THIRD_PARTY_NOTICES.md"),
    "audits": audit_members,
}
members = [
    (name, json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n")
    if name == "runtime.json" else (name, content)
    for name, content in members
]
members = [
    (name, json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n")
    if name == "sbom-summary.json" else (name, content)
    for name, content in members
]
for entry in source_runtime_manifest["entries"]:
    archive_relative = entrypoint_mapping.get(entry["path"], entry["path"])
    members.append((f"runtime/{archive_relative}", None, entry["path"]))

# Metadata and attribution members do not have a source-relative path.
members = [(item[0], item[1], None) if len(item) == 2 else item for item in members]

with artifact.open("wb") as raw:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=args.source_date_epoch, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for arcname, content, source_relative in sorted(members, key=lambda item: item[0].encode()):
                info = tarfile.TarInfo(arcname)
                info.mtime = args.source_date_epoch
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                if content is not None:
                    info.mode, info.size = 0o644, len(content)
                    archive.addfile(info, io.BytesIO(content))
                    continue
                path = runtime / source_relative
                if path.is_dir():
                    info.type, info.mode, info.size = tarfile.DIRTYPE, 0o755, 0
                    archive.addfile(info)
                else:
                    info.mode, info.size = (0o755 if os.access(path, os.X_OK) else 0o644), path.stat().st_size
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)

digest = sha256_file(artifact)
(out / f"{name}.sha256").write_text(f"{digest}  {name}\n")
artifact_size = artifact.stat().st_size
parts = []
if artifact_size > args.max_attachment_bytes:
    with artifact.open("rb") as source_stream:
        number = 0
        while True:
            chunk = source_stream.read(args.max_attachment_bytes)
            if not chunk:
                break
            number += 1
            part = out / f"{name}.part-{number:04d}"
            part.write_bytes(chunk)
            parts.append({"name": part.name, "size": len(chunk), "sha256": sha256_file(part)})
else:
    parts.append({"name": name, "size": artifact_size, "sha256": digest})
artifact_set = {
    "schema": "wenpai-artifact-set/v1",
    "artifact": name,
    "artifact_size": artifact_size,
    "artifact_sha256": digest,
    "max_attachment_bytes": args.max_attachment_bytes,
    "part_count": len(parts),
    "parts": parts,
    "reassembly": "concatenate parts in listed order; verify artifact_size and artifact_sha256",
}
write_json(out / "artifact-set.json", artifact_set)
write_json(out / "runtime-manifest.json", runtime_manifest)
write_json(out / "runtime.json", metadata | {"artifact_sha256": digest})
write_json(out / "sbom-summary.json", sbom)
for release_notice in ("THIRD_PARTY_NOTICES.md", "third-party-inventory.json",
                       "sbom-notice-metadata.json", "LICENSE_TEXTS.sha256"):
    shutil.copyfile(license_root / release_notice, out / release_notice)
for audit_path in args.notice_audit:
    shutil.copyfile(audit_path, out / audit_path.name)
if args.node_notices:
    shutil.copyfile(args.node_notices, out / args.node_notices.name)
print(f"PASS runtime-build samples={runtime_manifest['entry_count']} packages={len(sbom_packages)} "
      f"artifact={artifact} bytes={artifact_size} parts={len(parts)} sha256={digest}")
