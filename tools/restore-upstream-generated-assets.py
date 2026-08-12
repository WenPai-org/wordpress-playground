#!/usr/bin/env python3
"""Restore export-ignored build inputs from an immutable upstream Git commit.

The destination is normally a tree produced by ``git archive``. Only the seven
hard-coded upstream build asset classes below may be restored. Git tree modes,
paths, sizes and blob payloads are validated before any file is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import BinaryIO

from manifest import safe_relative, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
TAR_ROOT = "packages/playground/wordpress-builds/src/wordpress"
PUBLIC_ROOT = "packages/playground/wordpress-builds/public"
PHP_WEB_ROOT = "packages/php-wasm/web-builds"
PHP_NODE_ROOT = "packages/php-wasm/node-builds"
DEMOS_ROOT = "packages/playground/website/demos"
GROUP_PATTERNS = {
    "wordpress_tar_zst": re.compile(rf"^{re.escape(TAR_ROOT)}/wp-[^/]+\.tar\.zst$"),
    "wordpress_remote_asset_paths": re.compile(rf"^{re.escape(PUBLIC_ROOT)}/wp-[^/]+/wordpress-remote-asset-paths$"),
    "wordpress_static_zip": re.compile(rf"^{re.escape(PUBLIC_ROOT)}/wp-[^/]+/wordpress-static\.zip$"),
    "wordpress_public_tree": re.compile(rf"^{re.escape(PUBLIC_ROOT)}/wp-[^/]+/.+$"),
    "php_wasm_web": re.compile(rf"^{re.escape(PHP_WEB_ROOT)}/.+\.wasm$"),
    "php_wasm_node": re.compile(rf"^{re.escape(PHP_NODE_ROOT)}/.+\.wasm$"),
    "website_demos": re.compile(rf"^{re.escape(DEMOS_ROOT)}/[^/]+$"),
}
LOCK_PATTERNS = {
    "wordpress_tar_zst": f"{TAR_ROOT}/wp-*.tar.zst",
    "wordpress_remote_asset_paths": f"{PUBLIC_ROOT}/wp-*/wordpress-remote-asset-paths",
    "wordpress_static_zip": f"{PUBLIC_ROOT}/wp-*/wordpress-static.zip",
    "wordpress_public_tree": f"{PUBLIC_ROOT}/wp-*/* (excluding the two files above)",
    "php_wasm_web": f"{PHP_WEB_ROOT}/**/*.wasm",
    "php_wasm_node": f"{PHP_NODE_ROOT}/**/*.wasm",
    "website_demos": f"{DEMOS_ROOT}/*",
}


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"BLOCKED upstream generated assets: {message}")


def run_git(repository: Path, arguments: list[str], *, binary: bool = False) -> bytes | str:
    result = subprocess.run(["git", "-C", str(repository), *arguments], check=False,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        fail(f"git {' '.join(arguments)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout if binary else result.stdout.decode().strip()


def classify(path: str) -> str | None:
    if GROUP_PATTERNS["wordpress_tar_zst"].fullmatch(path):
        return "wordpress_tar_zst"
    if GROUP_PATTERNS["wordpress_remote_asset_paths"].fullmatch(path):
        return "wordpress_remote_asset_paths"
    if GROUP_PATTERNS["wordpress_static_zip"].fullmatch(path):
        return "wordpress_static_zip"
    if GROUP_PATTERNS["wordpress_public_tree"].fullmatch(path):
        return "wordpress_public_tree"
    if GROUP_PATTERNS["php_wasm_web"].fullmatch(path):
        return "php_wasm_web"
    if GROUP_PATTERNS["php_wasm_node"].fullmatch(path):
        return "php_wasm_node"
    if GROUP_PATTERNS["website_demos"].fullmatch(path):
        return "website_demos"
    return None


def parse_tree(repository: Path, commit: str) -> dict[str, list[dict]]:
    raw = run_git(repository, ["ls-tree", "-r", "-z", "-l", commit, "--", TAR_ROOT, PUBLIC_ROOT, PHP_WEB_ROOT, PHP_NODE_ROOT, DEMOS_ROOT], binary=True)
    groups: dict[str, list[dict]] = {name: [] for name in GROUP_PATTERNS}
    seen_case: dict[str, str] = {}
    seen_nfc: dict[str, str] = {}
    import unicodedata
    for item in raw.split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        fields = metadata.split()
        if len(fields) != 4:
            fail(f"unexpected git ls-tree record: {metadata!r}")
        mode, kind, object_id, raw_size = (field.decode("ascii") for field in fields)
        path = raw_path.decode("utf-8", "strict")
        safe_relative(path)
        group = classify(path)
        if group is None:
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            fail(f"non-regular tracked entry rejected: {mode} {kind} {path}")
        folded, nfc = path.casefold(), unicodedata.normalize("NFC", path)
        if folded in seen_case and seen_case[folded] != path:
            fail(f"case-insensitive path collision: {seen_case[folded]} / {path}")
        if nfc in seen_nfc and seen_nfc[nfc] != path:
            fail(f"Unicode path collision: {seen_nfc[nfc]} / {path}")
        seen_case[folded], seen_nfc[nfc] = path, path
        groups[group].append({"path": path, "mode": mode, "object": object_id,
                              "bytes": int(raw_size)})
    for name, entries in groups.items():
        entries.sort(key=lambda row: row["path"].encode("utf-8"))
        if not entries:
            fail(f"zero samples for required group {name}")
    return groups


class CatFileBatch:
    def __init__(self, repository: Path):
        self.process = subprocess.Popen(["git", "-C", str(repository), "cat-file", "--batch"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        assert self.process.stdin is not None and self.process.stdout is not None
        self.stdin: BinaryIO = self.process.stdin
        self.stdout: BinaryIO = self.process.stdout

    def read(self, object_id: str, expected_size: int) -> bytes:
        self.stdin.write(object_id.encode("ascii") + b"\n")
        self.stdin.flush()
        header = self.stdout.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[1] != b"blob":
            fail(f"cat-file rejected object {object_id}: {header!r}")
        actual_size = int(header[2])
        if actual_size != expected_size:
            fail(f"blob size drift {object_id}: tree={expected_size} blob={actual_size}")
        payload = self.stdout.read(actual_size)
        if len(payload) != actual_size or self.stdout.read(1) != b"\n":
            fail(f"short or malformed cat-file payload {object_id}")
        return payload

    def close(self) -> None:
        self.stdin.close()
        if self.process.wait() != 0:
            stderr = self.process.stderr.read().decode(errors="replace") if self.process.stderr else ""
            fail(f"cat-file batch failed: {stderr.strip()}")


def inventory(repository: Path, groups: dict[str, list[dict]]) -> dict:
    batch = CatFileBatch(repository)
    result: dict[str, dict] = {}
    try:
        for name, entries in groups.items():
            records = []
            total = 0
            for entry in entries:
                payload = batch.read(entry["object"], entry["bytes"])
                digest = hashlib.sha256(payload).hexdigest()
                entry["sha256"] = digest
                total += len(payload)
                records.append({"path": entry["path"], "mode": entry["mode"],
                                "bytes": len(payload), "sha256": digest})
            canonical = json.dumps(records, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
            result[name] = {
                "path_whitelist": LOCK_PATTERNS[name],
                "entry_count": len(records),
                "total_bytes": total,
                "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            }
    finally:
        batch.close()
    return result


def walk_governed(root: Path, destination: Path):
    if not root.exists() and not root.is_symlink():
        return
    if root.is_symlink():
        fail(f"symlink rejected in destination: {root.relative_to(destination)}")
    if not root.is_dir():
        fail(f"governed root is not a directory: {root.relative_to(destination)}")
    for base, directories, files in os.walk(root, topdown=True, followlinks=False):
        for name in sorted(directories + files):
            candidate = Path(base) / name
            relative = safe_relative(candidate.relative_to(destination).as_posix())
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                fail(f"symlink rejected in destination: {relative}")
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                fail(f"special destination entry rejected: {relative}")
            yield candidate, relative


def assert_no_extra(destination: Path, expected: set[str]) -> None:
    tar_root = destination / TAR_ROOT
    if tar_root.exists() or tar_root.is_symlink():
        if tar_root.is_symlink() or not tar_root.is_dir():
            fail(f"invalid governed root: {TAR_ROOT}")
        for candidate in sorted(tar_root.glob("wp-*.tar.zst")):
            relative = safe_relative(candidate.relative_to(destination).as_posix())
            if candidate.is_symlink():
                fail(f"symlink rejected in destination: {relative}")
            if not candidate.is_file() or relative not in expected:
                fail(f"untracked/extra governed destination file: {relative}")

    public_root = destination / PUBLIC_ROOT
    if public_root.exists() or public_root.is_symlink():
        if public_root.is_symlink() or not public_root.is_dir():
            fail(f"invalid governed root: {PUBLIC_ROOT}")
        for version_root in sorted(public_root.glob("wp-*")):
            version_relative = safe_relative(version_root.relative_to(destination).as_posix())
            if version_root.is_symlink() or not version_root.is_dir():
                fail(f"invalid WordPress public version root: {version_relative}")
            for candidate, relative in walk_governed(version_root, destination):
                if candidate.is_file() and relative not in expected:
                    fail(f"untracked/extra governed destination file: {relative}")

    for raw_root in (PHP_WEB_ROOT, PHP_NODE_ROOT):
        wasm_root = destination / raw_root
        for candidate, relative in walk_governed(wasm_root, destination) or ():
            if candidate.is_file() and relative.endswith(".wasm") and relative not in expected:
                fail(f"untracked/extra governed destination file: {relative}")

    for candidate, relative in walk_governed(destination / DEMOS_ROOT, destination) or ():
        if candidate.is_file() and relative not in expected:
            fail(f"untracked/extra governed destination file: {relative}")


def atomic_write(target: Path, payload: bytes, mode: int, expected_sha256: str) -> None:
    temporary = target.with_name(f".{target.name}.wenpai-restore-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        fail(f"restore temporary path already exists: {temporary.name}")
    try:
        with temporary.open("xb") as output:
            view = memoryview(payload)
            for offset in range(0, len(view), 1024 * 1024):
                output.write(view[offset:offset + 1024 * 1024])
        temporary.chmod(mode)
        if temporary.stat().st_size != len(payload) or sha256_file(temporary) != expected_sha256:
            fail(f"temporary payload verification failed: {target.name}")
        os.replace(temporary, target)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def safe_target(destination: Path, relative: str) -> Path:
    target = destination.joinpath(*PurePosixPath(relative).parts)
    current = destination
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            fail(f"destination parent symlink rejected: {current.relative_to(destination)}")
        if current.exists() and not current.is_dir():
            fail(f"destination parent is not directory: {current.relative_to(destination)}")
    if target.is_symlink():
        fail(f"destination symlink rejected: {relative}")
    if target.exists() and not target.is_file():
        fail(f"destination target is not regular file: {relative}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True,
                        help="exact upstream Git checkout containing the locked commit")
    parser.add_argument("--destination", type=Path,
                        help="git-archive tree to restore; required unless --inventory-output is used")
    parser.add_argument("--lock", type=Path, default=ROOT / "upstream-lock.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--inventory-output", type=Path,
                        help="maintainer-only: emit candidate locked inventory without restoring")
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    lock = json.loads(args.lock.read_text())
    commit = lock["upstream"]["commit"]
    head = run_git(repository, ["rev-parse", "HEAD"])
    resolved = run_git(repository, ["rev-parse", f"{commit}^{{commit}}"])
    if head != commit or resolved != commit:
        fail(f"checkout is not exact locked commit: head={head} locked={commit} resolved={resolved}")
    groups = parse_tree(repository, commit)
    computed = inventory(repository, groups)

    if args.inventory_output:
        write_json(args.inventory_output, {"schema": "wenpai-upstream-export-ignored-assets/v1",
                                           "commit": commit, "groups": computed})
        print(f"PASS candidate-inventory groups={len(computed)} samples={sum(v['entry_count'] for v in computed.values())}")
        return
    if args.destination is None:
        parser.error("--destination is required unless --inventory-output is used")
    locked = lock.get("generated_assets", {}).get("upstream_export_ignored")
    if not locked or locked.get("schema") != "wenpai-upstream-export-ignored-assets/v1":
        fail("missing generated_assets.upstream_export_ignored lock")
    if locked.get("commit") != commit:
        fail(f"generated asset commit mismatch: {locked.get('commit')} != {commit}")
    if locked.get("groups") != computed:
        fail("group count/bytes/path whitelist/normalized manifest drift")

    destination = args.destination.resolve(strict=True)
    expected = {entry["path"] for entries in groups.values() for entry in entries}
    assert_no_extra(destination, expected)
    restored = 0
    already_present = 0
    batch = CatFileBatch(repository)
    try:
        for name in GROUP_PATTERNS:
            for entry in groups[name]:
                relative = entry["path"]
                target = safe_target(destination, relative)
                payload = batch.read(entry["object"], entry["bytes"])
                if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                    fail(f"blob changed between validation and restore: {relative}")
                if target.exists():
                    if target.stat().st_size != len(payload) or sha256_file(target) != entry["sha256"]:
                        fail(f"existing governed file hash drift: {relative}")
                    already_present += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(target, payload, 0o755 if entry["mode"] == "100755" else 0o644,
                             entry["sha256"])
                restored += 1
    finally:
        batch.close()

    # A second complete filesystem pass proves no extra file or symlink appeared.
    assert_no_extra(destination, expected)
    for entries in groups.values():
        for entry in entries:
            target = safe_target(destination, entry["path"])
            if (not target.is_file() or target.stat().st_size != entry["bytes"] or
                    sha256_file(target) != entry["sha256"]):
                fail(f"post-restore payload mismatch: {entry['path']}")

    report = {"schema": "wenpai-upstream-export-ignored-restore/v1", "status": "PASS",
              "commit": commit, "groups": computed, "entry_count": len(expected),
              "restored": restored, "already_present": already_present}
    if args.report:
        write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    print(f"PASS upstream-export-ignored-assets samples={len(expected)} restored={restored} present={already_present}")


if __name__ == "__main__":
    main()
