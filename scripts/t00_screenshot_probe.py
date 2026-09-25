#!/usr/bin/env python3
"""Local T00 probe. Output contains private transcript; keep under ignored data/."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.screenshots.mapper import map_screenshot

parser = argparse.ArgumentParser()
parser.add_argument('image', type=Path)
parser.add_argument('transcript', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--source-id', default='t00-local-screenshot')
args = parser.parse_args()
started = time.perf_counter()
draft = map_screenshot(args.transcript.read_text(encoding='utf-8'), args.image, args.source_id)
draft['elapsed_seconds'] = round(time.perf_counter() - started, 3)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: draft[k] for k in ('matched_count', 'candidate_count', 'unknown_count', 'candidate_color_counts', 'elapsed_seconds')}))
