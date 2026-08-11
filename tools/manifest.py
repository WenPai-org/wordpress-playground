#!/usr/bin/env python3
"""Normalized manifests and digests used by the WenPai Playground pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import unicodedata


DEFAULT_EXCLUDES = {".git", ".DS_Store", "node_modules", ".nx", ".cache"}


class UnsafeTree(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(raw: str) -> str:
    path = PurePosixPath(raw.replace(os.sep, "/"))
    if path.is_absolute() or not raw or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeTree(f"unsafe path: {raw!r}")
    return path.as_posix()


def normalized_manifest(root: Path, *, excludes: set[str] | None = None,
                        symlinks: str = "reject") -> dict:
    root = root.resolve(strict=True)
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    entries: list[dict] = []
    casefolded: dict[str, str] = {}
    normalized: dict[str, str] = {}

    for base, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in excludes)
        for name in sorted(directories + files):
            path = Path(base) / name
            relative = safe_relative(path.relative_to(root).as_posix())
            if any(part in excludes for part in PurePosixPath(relative).parts):
                continue
            folded = relative.casefold()
            nfc = unicodedata.normalize("NFC", relative)
            if folded in casefolded and casefolded[folded] != relative:
                raise UnsafeTree(f"case-insensitive collision: {casefolded[folded]!r}, {relative!r}")
            if nfc in normalized and normalized[nfc] != relative:
                raise UnsafeTree(f"Unicode normalization collision: {normalized[nfc]!r}, {relative!r}")
            casefolded[folded], normalized[nfc] = relative, relative

            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                if symlinks == "reject":
                    raise UnsafeTree(f"symlink rejected: {relative}")
                target = os.readlink(path)
                resolved_target = (path.parent / target).resolve()
                if Path(target).is_absolute() or (resolved_target != root and root not in resolved_target.parents):
                    raise UnsafeTree(f"symlink escapes tree: {relative} -> {target}")
                entries.append({"path": relative, "type": "symlink", "executable": False,
                                "sha256": hashlib.sha256(target.encode()).hexdigest(), "target": target})
            elif stat.S_ISDIR(mode):
                entries.append({"path": relative, "type": "directory", "executable": True,
                                "sha256": None})
            elif stat.S_ISREG(mode):
                entries.append({"path": relative, "type": "file",
                                "executable": bool(mode & 0o111), "sha256": sha256_file(path)})
            else:
                raise UnsafeTree(f"device/socket/special file rejected: {relative}")

    entries.sort(key=lambda item: item["path"].encode("utf-8"))
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return {"schema": "wenpai-source-manifest/v1", "algorithm": "sha256",
            "root": ".", "entry_count": len(entries),
            "manifest_sha256": hashlib.sha256(canonical).hexdigest(), "entries": entries}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def digest_inputs(root: Path, inputs: list[str]) -> dict:
    root = root.resolve(strict=True)
    records: list[dict[str, str]] = []
    for raw in sorted(set(inputs)):
        candidate = (root / safe_relative(raw)).resolve(strict=True)
        if root not in candidate.parents and candidate != root:
            raise UnsafeTree(f"transform input escapes repository: {raw}")
        if candidate.is_dir():
            manifest = normalized_manifest(candidate)
            value = manifest["manifest_sha256"]
        elif candidate.is_file() and not candidate.is_symlink():
            value = sha256_file(candidate)
        else:
            raise UnsafeTree(f"unsupported transform input: {raw}")
        records.append({"path": raw, "sha256": value})
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {"schema": "wenpai-transform-digest/v1", "input_count": len(records),
            "transform_sha256": hashlib.sha256(encoded).hexdigest(), "inputs": records}
