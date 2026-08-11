#!/usr/bin/env python3
"""Apply and audit WenPai's replayable website-shell localization overlay."""
from __future__ import annotations
import argparse, json, re, shutil, sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'overlays/localization/replacements.json'
FILES = ROOT / 'overlays/files'
TOKEN_RE = re.compile(r"\$\{[^}]+\}|\{\{[^}]+\}\}|%(?:\d+\$)?[a-zA-Z]")
TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9.]*)\b")

class OverlayError(RuntimeError): pass

def load_catalog(path: Path = CATALOG):
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 1 or not isinstance(data.get('entries'), list):
        raise OverlayError(f'unsupported catalog schema: {path}')
    return data

def safe_target(root: Path, rel: str) -> Path:
    p=PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts:
        raise OverlayError(f'unsafe overlay path: {rel}')
    target=root.joinpath(*p.parts)
    resolved_parent=target.parent.resolve()
    if root.resolve() != resolved_parent and root.resolve() not in resolved_parent.parents:
        raise OverlayError(f'overlay escapes source root: {rel}')
    return target

def tokens(value: str):
    return sorted(TOKEN_RE.findall(value) + [f'<{name}>' for name in TAG_RE.findall(value)])

def validate_catalog(data) -> int:
    seen=set(); samples=0
    for i,e in enumerate(data['entries']):
        required={'path','old','new','expectedCount','category'}
        missing=required-set(e)
        if missing: raise OverlayError(f'entry {i} missing {sorted(missing)}')
        key=(e['path'],e['old'])
        if key in seen: raise OverlayError(f'duplicate replacement: {key}')
        seen.add(key)
        if not e['old'] or e['old']==e['new'] or e['expectedCount'] < 1:
            raise OverlayError(f'invalid replacement entry {i}')
        if tokens(e['old']) != tokens(e['new']):
            raise OverlayError(f'placeholder/token mismatch at {e["path"]}: {tokens(e["old"])} != {tokens(e["new"])}')
        samples += e['expectedCount']
    if samples < 40: raise OverlayError(f'non-zero coverage gate failed: {samples} < 40')
    return samples

def copy_overlay_files(source_root: Path, *, check=False):
    count=0
    if not FILES.exists(): return count
    for src in sorted(FILES.rglob('*')):
        if not src.is_file(): continue
        rel=src.relative_to(FILES).as_posix(); dst=safe_target(source_root,rel)
        if check:
            if not dst.exists() or dst.read_bytes()!=src.read_bytes():
                raise OverlayError(f'overlay file missing or changed: {rel}')
        else:
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
        count += 1
    return count

def apply(source_root: Path, *, check=False):
    data=load_catalog(); samples=validate_catalog(data)
    changed=0
    for e in data['entries']:
        target=safe_target(source_root,e['path'])
        if not target.is_file(): raise OverlayError(f'missing target: {e["path"]}')
        text=target.read_text(encoding='utf-8')
        old_count=text.count(e['old']); new_count=text.count(e['new'])
        embedded_old_count = e['new'].count(e['old']) * e['expectedCount']
        if check:
            if old_count != embedded_old_count or new_count != e['expectedCount']:
                raise OverlayError(f'residual/missing translation {e["path"]}: old={old_count}, embedded={embedded_old_count}, new={new_count}, expected={e["expectedCount"]}')
        else:
            if old_count == embedded_old_count and new_count == e['expectedCount']:
                continue # idempotent replay
            if old_count != e['expectedCount']:
                raise OverlayError(f'upstream drift {e["path"]}: found={old_count}, expected={e["expectedCount"]}')
            target.write_text(text.replace(e['old'],e['new']),encoding='utf-8')
            changed += e['expectedCount']
    files=copy_overlay_files(source_root,check=check)
    return {'catalogSamples':samples,'changed':changed,'overlayFiles':files,'mode':'check' if check else 'apply'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['apply','check','catalog-check'])
    parser.add_argument('--source-root',type=Path)
    args=parser.parse_args()
    try:
        if args.mode=='catalog-check':
            result={'catalogSamples':validate_catalog(load_catalog()),'mode':'catalog-check'}
        else:
            if not args.source_root: parser.error('--source-root is required')
            result=apply(args.source_root,check=args.mode=='check')
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    except OverlayError as e:
        print(f'FAIL: {e}',file=sys.stderr); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
