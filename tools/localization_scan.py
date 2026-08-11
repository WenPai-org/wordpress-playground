#!/usr/bin/env python3
"""Report stable shell translation coverage and mapped English residuals."""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
from localization_overlay import OverlayError, load_catalog, safe_target, tokens, validate_catalog

def scan(root: Path):
    data=load_catalog(); samples=validate_catalog(data)
    residual=[]; missing=[]; translated=0; categories=Counter()
    for e in data['entries']:
        categories[e['category']] += e['expectedCount']
        p=safe_target(root,e['path'])
        if not p.is_file(): missing.append(e['path']); continue
        text=p.read_text(encoding='utf-8')
        expected=e['expectedCount']; embedded=e['new'].count(e['old'])*expected
        old_count=text.count(e['old']); new_count=text.count(e['new'])
        if old_count != embedded: residual.append({'path':e['path'],'source':e['old'],'count':old_count-embedded})
        if new_count != expected: missing.append(e['path'])
        else: translated += expected
    return {'status':'PASS' if not residual and not missing else 'FAIL','samples':samples,'translated':translated,'categories':dict(categories),'residuals':residual,'missing':sorted(set(missing))}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--source-root',required=True,type=Path); a=p.parse_args()
    try: report=scan(a.source_root)
    except OverlayError as e: print(json.dumps({'status':'FAIL','error':str(e)},ensure_ascii=False)); return 1
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    return 0 if report['status']=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
