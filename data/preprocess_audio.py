"""Extract acoustic features from an explicitly supplied local WAV directory."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.ai import audio_features
parser=argparse.ArgumentParser()
parser.add_argument('input',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('w',encoding='utf-8') as dest:
    for path in args.input.glob('**/*.wav'):
        try:
            if path.stat().st_size>10*1024*1024: raise ValueError('Over 10 MB')
            features=audio_features(path.read_bytes())
            dest.write(json.dumps({'file':str(path.relative_to(args.input)),**features})+'\n')
        except ValueError as exc:
            print(f'Skipped {path.name}: {exc}',file=sys.stderr)
