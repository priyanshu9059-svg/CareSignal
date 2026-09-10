"""Offline inference against a structured assessment JSON file."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.ai import calculate
parser=argparse.ArgumentParser()
parser.add_argument('input',type=Path,help='JSON containing responses, text, language, history and conditions')
args=parser.parse_args()
payload=json.loads(args.input.read_text(encoding='utf-8'))
print(json.dumps(calculate(payload.get('responses',{}),payload.get('text',''),payload.get('language','en'),payload.get('history',[]),payload.get('conditions',{}),datetime.now(timezone.utc)),ensure_ascii=False,indent=2))
