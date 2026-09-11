"""Convert downloaded raw datasets into processed JSONL for ai/train_text.py."""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
PROC = ROOT / 'data' / 'processed'
PROC.mkdir(parents=True, exist_ok=True)

GOEMO_PRIORITY = [
    'fear', 'sadness', 'anger', 'joy', 'neutral',
    'nervousness', 'grief', 'annoyance', 'disgust', 'optimism', 'love', 'amusement',
]


def write_jsonl(path: Path, rows: list[dict]):
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'Wrote {len(rows)} -> {path}')


def prepare_goemotions():
    folder = RAW / 'goemotions'
    files = sorted(folder.glob('goemotions_*.csv'))
    if not files:
        print('skip goemotions (not downloaded)')
        return
    # Column names are emotion indicators 0/1 plus 'text'
    rows = []
    for path in files:
        with path.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                text = (row.get('text') or '').strip()
                if not text:
                    continue
                label = None
                for emo in GOEMO_PRIORITY:
                    if row.get(emo) in ('1', '1.0', 1, True, 'true'):
                        label = emo
                        break
                if label is None and row.get('neutral') in ('1', '1.0', 1):
                    label = 'neutral'
                if not label:
                    # any positive emotion bit
                    for key, val in row.items():
                        if key in ('text', 'id', 'author', 'subreddit', 'link_id', 'parent_id', 'created_utc', 'rater_id', 'example_very_unclear'):
                            continue
                        if val in ('1', '1.0', 1):
                            label = key
                            break
                if label:
                    rows.append({'text': text, 'label': label, 'language': 'en'})
    write_jsonl(PROC / 'goemotions.jsonl', rows)


def prepare_indic():
    csv_path = RAW / 'indic_sentiment' / 'indic_sentiment.csv'
    if not csv_path.exists():
        print('skip indic_sentiment (not downloaded)')
        return
    rows = []
    with csv_path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            text = (row.get('text') or '').strip()
            label = (row.get('label') or '').strip().lower()
            if text and label:
                rows.append({'text': text, 'label': label, 'language': row.get('language') or 'hi'})
    write_jsonl(PROC / 'indic_sentiment.jsonl', rows)


def prepare_sentimix():
    folder = RAW / 'sentimix'
    paths = list(folder.rglob('Hinglish*conll*.txt')) + list(folder.rglob('Hinglish*train*.txt')) + list(folder.rglob('Hinglish*dev*.txt'))
    # Prefer train+dev labeled CoNLL
    labeled = [p for p in folder.rglob('*') if p.is_file() and 'Hinglish' in p.name and 'unalbel' not in p.name.lower() and 'unlabel' not in p.name.lower() and 'test_labels' not in p.name.lower() and p.suffix.lower() == '.txt']
    rows = []
    for path in labeled:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if 'meta' not in text:
            continue
        chunks = re.split(r'\n(?=meta\t)', text)
        for chunk in chunks:
            m = re.match(r'meta\t(\S+)\t(positive|negative|neutral)\s*', chunk, re.I)
            if not m:
                continue
            label = m.group(2).lower()
            tokens = []
            for line in chunk.splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\t+', line)
                if parts and parts[0].lower() != 'meta':
                    tokens.append(parts[0])
            tweet = ' '.join(tokens).strip()
            if tweet:
                rows.append({'text': tweet, 'label': label, 'language': 'hinglish'})
    if rows:
        write_jsonl(PROC / 'sentimix.jsonl', rows)
    else:
        print('sentimix files present but no parseable rows yet — check data/raw/sentimix')


def prepare_kaggle():
    folder = RAW / 'kaggle_emotion'
    emotion_csv = next(folder.rglob('combined_emotion.csv'), None)
    sentiment_csv = next(folder.rglob('combined_sentiment_data.csv'), None)
    rows = []
    if emotion_csv and emotion_csv.exists():
        with emotion_csv.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            fields = {k.lower(): k for k in (reader.fieldnames or [])}
            text_k = fields.get('sentence') or fields.get('text') or fields.get('content') or list(fields.values())[0]
            label_k = fields.get('emotion') or fields.get('label') or fields.get('sentiment') or list(fields.values())[-1]
            for row in reader:
                t = (row.get(text_k) or '').strip()
                lab = (row.get(label_k) or '').strip().lower()
                if t and lab:
                    rows.append({'text': t, 'label': lab, 'language': 'en'})
        write_jsonl(PROC / 'kaggle_emotion.jsonl', rows)
    rows = []
    if sentiment_csv and sentiment_csv.exists():
        with sentiment_csv.open(encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            fields = {k.lower(): k for k in (reader.fieldnames or [])}
            text_k = fields.get('sentence') or fields.get('text') or list(fields.values())[0]
            label_k = fields.get('sentiment') or fields.get('label') or list(fields.values())[-1]
            for row in reader:
                t = (row.get(text_k) or '').strip()
                lab = (row.get(label_k) or '').strip().lower()
                if t and lab:
                    rows.append({'text': t, 'label': lab, 'language': 'en'})
        write_jsonl(PROC / 'kaggle_sentiment.jsonl', rows)
    if not emotion_csv and not sentiment_csv:
        print('skip kaggle (not downloaded) — see DOWNLOAD_GUIDE.md section 2')


def main():
    prepare_goemotions()
    prepare_indic()
    prepare_sentimix()
    prepare_kaggle()
    print('\nProcessed files in', PROC)
    print('Train with:')
    print(r'  .\.venv\Scripts\python.exe ai\train_text.py data\processed\goemotions.jsonl data\processed\indic_sentiment.jsonl data\processed\sentimix.jsonl data\processed\kaggle_emotion.jsonl --bootstrap')


if __name__ == '__main__':
    main()
