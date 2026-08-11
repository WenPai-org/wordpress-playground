#!/usr/bin/env python3
"""Fail-closed third-party notice and generated-asset audit."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path


REQUIRED_SOURCE_CATEGORIES = {
    "root_license": "LICENSE",
    "wordpress_archives": "packages/playground/wordpress-builds/public/wp-*/wordpress-static.zip",
    "php_wasm": "packages/php-wasm/web-builds/*/*/*/*.wasm",
    "fonts": "packages/playground/**/*.[wWtT][oOtT][fF]*",
    "sqlite_archives": "packages/playground/wordpress-builds/src/sqlite-database-integration/*.zip",
    "wp_cli": "packages/playground/**/fixtures/wp-cli.phar",
    "license_files": "packages/playground/**/[Ll][Ii][Cc][Ee][Nn][Ss][Ee]*",
}
RUNTIME_EXTENSIONS = {
    ".css", ".html", ".js", ".json", ".mjs", ".png", ".svg", ".ttf",
    ".wasm", ".woff", ".woff2", ".zip",
}
ALLOWED_BUILD_GENERATED_CHANGES = {
    "packages/playground/blueprints/public/blueprint-schema.json",
    "packages/playground/blueprints/public/blueprint-v2-schema-validator.js",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def files_for(root: Path, pattern: str) -> list[Path]:
    return sorted(
        (Path(p) for p in glob.glob(str(root / pattern), recursive=True)),
        key=lambda p: p.as_posix().encode("utf-8"),
    )


def rollup(root: Path, paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            continue
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(bytes.fromhex(sha256(path)))
        h.update(b"\n")
    return h.hexdigest()


def record_rollup(records: list[dict]) -> str:
    h = hashlib.sha256()
    for item in sorted(records, key=lambda value: value["path"].encode("utf-8")):
        h.update(item["path"].encode())
        h.update(b"\0")
        h.update(bytes.fromhex(item["sha256"]))
        h.update(b"\n")
    return h.hexdigest()


def collect_runtime_records(runtime: Path | None, runtime_archive: Path | None) -> list[dict]:
    """Collect exact runtime payload records without extracting an archive."""
    records = []
    if runtime:
        root = runtime.resolve()
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.suffix.lower() in RUNTIME_EXTENSIONS:
                records.append({"path": path.relative_to(root).as_posix(),
                                "name": path.name, "suffix": path.suffix.lower(),
                                "sha256": sha256(path)})
    elif runtime_archive:
        with tarfile.open(runtime_archive.resolve(strict=True), "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.startswith("runtime/"):
                    continue
                relative = member.name.removeprefix("runtime/")
                suffix = Path(relative).suffix.lower()
                if suffix not in RUNTIME_EXTENSIONS:
                    continue
                stream = archive.extractfile(member)
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                records.append({"path": relative, "name": Path(relative).name,
                                "suffix": suffix, "sha256": digest.hexdigest()})
    return sorted(records, key=lambda item: item["path"].encode("utf-8"))


def audit_runtime_patterns(component: dict, records: list[dict]) -> tuple[list[dict], list[str]]:
    """Verify every explicit component/runtime relationship independently."""
    results, failures = [], []
    component_id = component.get("id")
    patterns = component.get("runtime_patterns")
    if not isinstance(patterns, list) or not patterns:
        return [], [f"component {component_id} required in runtime but has no runtime_patterns"]
    for rule in patterns:
        if not isinstance(rule, dict) or not rule.get("pattern"):
            failures.append(f"component {component_id} has malformed runtime pattern")
            continue
        pattern = rule["pattern"]
        minimum = rule.get("min_samples")
        if not isinstance(minimum, int) or minimum < 1:
            failures.append(f"component {component_id} pattern {pattern} has invalid min_samples")
            continue
        matches = [item for item in records if fnmatch.fnmatchcase(item["path"], pattern)]
        expected_hashes = sorted(rule.get("sha256", []))
        actual_hashes = sorted(item["sha256"] for item in matches)
        if len(matches) < minimum:
            failures.append(
                f"component {component_id} runtime pattern {pattern} matched "
                f"{len(matches)} < {minimum} files"
            )
        if expected_hashes and actual_hashes != expected_hashes:
            failures.append(f"component {component_id} runtime pattern {pattern} SHA-256 mismatch")
        results.append({"pattern": pattern, "min_samples": minimum,
                        "samples": len(matches), "sha256": actual_hashes,
                        "sha256_rollup": record_rollup(matches)})
    return results, failures


def git_head(source: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git_tracked_changes(source: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        text=True, capture_output=True, check=False,
    )
    return result.stdout.splitlines() if result.returncode == 0 else ["git-status-unavailable"]


def node_notice(source: Path, inventory: dict) -> tuple[dict, list[str]]:
    lock = json.loads((source / "package-lock.json").read_text())
    exceptions = inventory.get("node_license_exceptions", {})
    packages = []
    unknown = []
    for package_path, item in sorted(lock.get("packages", {}).items()):
        if not package_path:
            continue
        if item.get("link") or package_path.startswith("packages/"):
            packages.append({"path": package_path, "version": None,
                             "license": "GPL-2.0-or-later", "basis": "workspace-link"})
            continue
        version = item.get("version")
        license_value = item.get("license")
        key_path = package_path.removeprefix("node_modules/")
        key = f"{key_path}@{version}"
        basis = "package-lock"
        if not license_value and key in exceptions:
            license_value = exceptions[key]
            basis = "reviewed-exception"
        if not license_value:
            unknown.append(key)
            license_value = "UNKNOWN"
        packages.append({"path": package_path, "version": version,
                         "license": license_value, "basis": basis,
                         "resolved": item.get("resolved"), "integrity": item.get("integrity")})
    counts = Counter(item["license"] for item in packages)
    return {
        "schema": "wenpai-node-license-notices/v1",
        "lockfile_version": lock.get("lockfileVersion"),
        "package_samples": len(packages),
        "license_counts": dict(sorted(counts.items())),
        "packages": packages,
    }, unknown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    runtime_group = parser.add_mutually_exclusive_group()
    runtime_group.add_argument("--runtime", type=Path)
    runtime_group.add_argument("--runtime-archive", type=Path,
                               help="product tar.gz; scans regular members below runtime/")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--notices", type=Path,
                        help="human-readable notices; defaults beside inventory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-notices", type=Path, required=True)
    parser.add_argument("--allow-tracked-generated", action="store_true",
                        help="allow only the two known Blueprint build-generated files")
    args = parser.parse_args()
    source = args.source.resolve()
    inventory = json.loads(args.inventory.read_text())
    failures: list[str] = []
    if inventory.get("review_status") != "PASS":
        blockers = inventory.get("review_blockers") or ["unspecified inventory review blocker"]
        failures.append("third-party inventory review is not PASS: " + "; ".join(blockers))
    notices_path = args.notices or args.inventory.with_name("THIRD_PARTY_NOTICES.md")
    if not notices_path.is_file():
        failures.append(f"human-readable notices missing: {notices_path}")
        human_notices = ""
    else:
        human_notices = notices_path.read_text()
    license_text_dir = args.inventory.parent / "texts"
    license_text_results = []
    expected_license_text_hashes = inventory.get("policy", {}).get("license_text_sha256", {})
    for license_id in inventory.get("policy", {}).get("required_license_texts", []):
        path = license_text_dir / f"{license_id}.txt"
        present = path.is_file() and path.stat().st_size > 0
        license_text_results.append({"id": license_id, "present": present,
                                     "sha256": sha256(path) if present else None})
        if not present:
            failures.append(f"required license text missing: {license_id}")
        elif expected_license_text_hashes.get(license_id) != sha256(path):
            failures.append(f"required license text SHA-256 mismatch: {license_id}")

    head = git_head(source)
    tracked_changes = git_tracked_changes(source)
    if head != args.expected_commit:
        failures.append(f"source commit {head!r} != {args.expected_commit}")
    if inventory.get("upstream_commit") != args.expected_commit:
        failures.append("inventory upstream_commit does not match expected commit")
    changed_paths = {line[3:] for line in tracked_changes if len(line) > 3}
    unapproved_changes = changed_paths - (ALLOWED_BUILD_GENERATED_CHANGES
                                          if args.allow_tracked_generated else set())
    if unapproved_changes:
        failures.append("source has unapproved tracked modifications; audit a clean exact checkout")
    php_next_lock = inventory.get("external_assets", {}).get("php_next", {})
    for field in ("repository", "ref", "commit", "php_version", "php_ref", "built_at",
                  "readme_sha256", "manifest_sha256", "wasm_sha256"):
        if not php_next_lock.get(field):
            failures.append(f"php-next external lock missing {field}")
    if len(php_next_lock.get("wasm_sha256", {})) != 2:
        failures.append("php-next external lock must contain asyncify and jspi WASM hashes")

    runtime_present = args.runtime is not None or args.runtime_archive is not None
    runtime_records = collect_runtime_records(args.runtime, args.runtime_archive)
    component_results = []
    for component in inventory.get("components", []):
        missing_fields = [field for field in ("id", "name", "version", "license", "source",
                                               "asset_patterns", "notice", "redistribution")
                          if not component.get(field)]
        matched = []
        for pattern in component.get("asset_patterns", []):
            matched.extend(files_for(source, pattern))
        matched = sorted({p for p in matched if p.is_file()})
        required_in = component.get("required_in", "source")
        required = required_in == "source" or (required_in in {"runtime", "php-next"} and runtime_present)
        if missing_fields:
            failures.append(f"component {component.get('id')} missing {','.join(missing_fields)}")
        if component.get("redistribution") != "PASS":
            failures.append(f"component {component.get('id')} is not reviewed PASS")
        for notice_field in ("name", "license", "source", "notice"):
            value = component.get(notice_field)
            if value and value not in human_notices:
                failures.append(
                    f"component {component.get('id')} {notice_field} missing from human notices"
                )
        if required and not matched and required_in == "source":
            failures.append(f"component {component.get('id')} matched zero source files")
        runtime_pattern_results = []
        if required_in in {"runtime", "php-next"}:
            if not isinstance(component.get("runtime_patterns"), list) or not component["runtime_patterns"]:
                failures.append(
                    f"component {component.get('id')} required in runtime but has no runtime_patterns"
                )
            if not component.get("runtime_notice"):
                failures.append(f"component {component.get('id')} missing runtime_notice linkage")
            elif component["runtime_notice"] != component.get("notice"):
                failures.append(f"component {component.get('id')} runtime_notice differs from notice")
            if runtime_present:
                runtime_pattern_results, pattern_failures = audit_runtime_patterns(
                    component, runtime_records
                )
                failures.extend(pattern_failures)
        component_results.append({"id": component.get("id"), "matched_source_files": len(matched),
                                  "required": required,
                                  "runtime_patterns": runtime_pattern_results})

    categories = {}
    for name, pattern in REQUIRED_SOURCE_CATEGORIES.items():
        matched = [p for p in files_for(source, pattern) if p.is_file()]
        categories[name] = {"samples": len(matched), "sha256_rollup": rollup(source, matched)}
        if not matched:
            failures.append(f"required source category {name} has zero samples")

    notices, unknown_node = node_notice(source, inventory)
    if unknown_node:
        failures.append(f"unknown external Node licenses: {', '.join(unknown_node)}")
    args.node_notices.parent.mkdir(parents=True, exist_ok=True)
    args.node_notices.write_text(json.dumps(notices, ensure_ascii=False, indent=2) + "\n")

    runtime_report = {"provided": runtime_present, "samples": 0, "by_extension": {},
                      "sha256_rollup": None, "php_next_wasm_samples": 0,
                      "php_next_wasm_sha256": [], "php_next_metadata": {}}
    if runtime_present:
        php_next_wasm = sorted(
            (item for item in runtime_records if item["name"] == "php_8_6.wasm"),
            key=lambda item: item["path"].encode("utf-8"),
        )
        php_next_hashes = sorted(item["sha256"] for item in php_next_wasm)
        php_next_metadata = {}
        for filename, lock_field in (("README.md", "readme_sha256"),
                                     ("manifest.json", "manifest_sha256")):
            matches = [item for item in runtime_records
                       if item["name"] == filename and "php-next" in item["path"]]
            php_next_metadata[filename] = sorted(item["sha256"] for item in matches)
            expected = inventory.get("external_assets", {}).get("php_next", {}).get(lock_field)
            # Vite does not publish README.md. Its exact hash is covered by the
            # locked generated-assets source manifest; runtime must publish the
            # machine-readable manifest and both WASM payloads.
            if not matches and filename == "manifest.json":
                failures.append(f"runtime php-next {filename} is missing")
            elif matches and expected not in php_next_metadata[filename]:
                failures.append(f"runtime php-next {filename} SHA-256 does not match lock")
        runtime_report = {
            "provided": True,
            "samples": len(runtime_records),
            "by_extension": dict(sorted(Counter(item["suffix"] for item in runtime_records).items())),
            "sha256_rollup": record_rollup(runtime_records),
            "php_next_wasm_samples": len(php_next_wasm),
            "php_next_wasm_sha256": php_next_hashes,
            "php_next_metadata": php_next_metadata,
        }
        if not runtime_records:
            failures.append("runtime was provided but contains zero generated assets")
        if not any(item["suffix"] == ".wasm" for item in runtime_records):
            failures.append("runtime contains zero WASM assets")
        if not any(item["name"] in {"index.html", "playground.html"} for item in runtime_records):
            failures.append("runtime contains neither index.html nor playground.html")
        php_next = inventory.get("external_assets", {}).get("php_next", {})
        expected_php_next = sorted(php_next.get("wasm_sha256", {}).values())
        if len(php_next_wasm) == 0:
            failures.append("runtime contains zero PHP 8.6 php-next WASM assets")
        elif php_next_hashes != expected_php_next:
            failures.append("runtime PHP 8.6 WASM SHA-256 set does not match php-next lock")

    report = {
        "schema": "wenpai-license-notice-audit/v1",
        "status": "PASS" if not failures else "FAIL",
        "expected_commit": args.expected_commit,
        "actual_commit": head,
        "tracked_source_changes": tracked_changes,
        "allowed_tracked_generated": args.allow_tracked_generated and bool(tracked_changes),
        "inventory_sha256": sha256(args.inventory),
        "human_notices_sha256": sha256(notices_path) if notices_path.is_file() else None,
        "license_texts": license_text_results,
        "inventory_components": len(inventory.get("components", [])),
        "component_results": component_results,
        "source_categories": categories,
        "node_package_samples": notices["package_samples"],
        "node_unknown_licenses": unknown_node,
        "runtime": runtime_report,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
