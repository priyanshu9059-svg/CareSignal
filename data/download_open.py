"""Download open research datasets into data/raw/ (never commits them).

Usage:
  python data/download_open.py --all-open
  python data/download_open.py --goemotions
  python data/download_open.py --sentimix
  python data/download_open.py --indic-sentiment
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'


def fetch(url: str, dest: Path, timeout: int = 120):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        print('exists', dest)
        return dest
    print('downloading', url)
    req = Request(url, headers={'User-Agent': 'CareSignal-SIH/1.0 (research; local only)'})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print('saved', dest, f'({len(data)} bytes)')
    return dest


def download_goemotions():
    out = RAW / 'goemotions'
    out.mkdir(parents=True, exist_ok=True)
    base = 'https://storage.googleapis.com/gresearch/goemotions/data/full_dataset'
    for name in ('goemotions_1.csv', 'goemotions_2.csv', 'goemotions_3.csv'):
        fetch(f'{base}/{name}', out / name)
    # Also pull emotion label list if present
    try:
        fetch('https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data/emotions.txt', out / 'emotions.txt')
    except Exception as exc:
        print('optional emotions.txt skipped:', exc)
    print('GoEmotions ready under', out)


def download_sentimix():
    out = RAW / 'sentimix'
    out.mkdir(parents=True, exist_ok=True)
    # Zenodo record 3974927 — try common file API endpoints
    candidates = [
        'https://zenodo.org/api/records/3974927/files',
        'https://zenodo.org/records/3974927/files',
    ]
    # Direct known pattern: list files via API
    try:
        req = Request('https://zenodo.org/api/records/3974927', headers={'User-Agent': 'CareSignal-SIH/1.0'})
        with urlopen(req, timeout=60) as resp:
            meta = json.loads(resp.read().decode())
        files = meta.get('files') or []
        if not files:
            raise RuntimeError('No files listed on Zenodo record')
        for f in files:
            url = f.get('links', {}).get('self') or f.get('links', {}).get('download')
            key = f.get('key') or 'sentimix.bin'
            if not url:
                continue
            dest = out / key
            fetch(url, dest)
            if key.lower().endswith('.zip') and dest.exists():
                with zipfile.ZipFile(dest) as zf:
                    zf.extractall(out / 'extracted')
                print('extracted zip to', out / 'extracted')
        print('SentiMix ready under', out)
        return
    except Exception as exc:
        print('Zenodo auto-download failed:', exc)
        print('Manual: open https://zenodo.org/records/3974927 and save files into', out)
        (out / 'README_MANUAL.txt').write_text(
            'Download Hinglish/Spanglish archives from https://zenodo.org/records/3974927\n'
            'Also see https://ritual-uh.github.io/sentimix2020/\n',
            encoding='utf-8')


def download_indic_sentiment():
    out = RAW / 'indic_sentiment'
    out.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'huggingface_hub'])
        from huggingface_hub import hf_hub_download
    rows = []
    langs = ['hi', 'bn', 'ta', 'te', 'mr', 'gu', 'pa', 'or', 'kn', 'ml', 'as', 'ur']
    for split in ('test', 'validation'):
        for lang in langs:
            try:
                path = Path(hf_hub_download('ai4bharat/IndicSentiment', f'data/{split}/{lang}.json', repo_type='dataset'))
            except Exception as exc:
                print(split, lang, 'skip', exc)
                continue
            count = 0
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                label = row.get('LABEL') or row.get('label')
                en = row.get('ENGLISH REVIEW') or row.get('english_review')
                indic = row.get('INDIC REVIEW') or row.get('indic_review')
                for text, language in ((en, 'en'), (indic, lang)):
                    if text and label:
                        rows.append({'text': str(text).replace('\n', ' ').strip(),
                                     'label': str(label).strip().lower(), 'language': language})
                        count += 1
            print(split, lang, count)
    csv_path = out / 'indic_sentiment.csv'
    with csv_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['text', 'label', 'language'])
        writer.writeheader()
        writer.writerows(rows)
    print('Wrote', csv_path, 'rows', len(rows))


def main():
    parser = argparse.ArgumentParser(description='Download open datasets for CareSignal')
    parser.add_argument('--all-open', action='store_true')
    parser.add_argument('--goemotions', action='store_true')
    parser.add_argument('--sentimix', action='store_true')
    parser.add_argument('--indic-sentiment', action='store_true')
    args = parser.parse_args()
    if not any([args.all_open, args.goemotions, args.sentimix, args.indic_sentiment]):
        parser.print_help()
        return
    RAW.mkdir(parents=True, exist_ok=True)
    if args.all_open or args.goemotions:
        download_goemotions()
    if args.all_open or args.sentimix:
        download_sentimix()
    if args.all_open or args.indic_sentiment:
        download_indic_sentiment()
    print('\nNext: python data/prepare_downloaded.py')
    print('Then:  python ai/train_text.py data/processed/*.jsonl --bootstrap')


if __name__ == '__main__':
    main()
