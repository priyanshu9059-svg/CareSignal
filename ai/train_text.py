"""Train portable TF-IDF sentiment/emotion JSON from local JSONL (never auto-downloads).

Prepare data with data/preprocess.py from SentiMix, IndicSentiment, GoEmotions (mapped),
or the Kaggle emotion CSV. Also supports --bootstrap to train on an authored domain corpus
so the demo has a real sklearn artifact without third-party redistribution.

Example:
  python ai/train_text.py data/processed/sentimix.jsonl
  python ai/train_text.py --bootstrap
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

ROOT = Path(__file__).resolve().parents[1]

# Map diverse dataset labels into CareSignal-compatible classes
LABEL_MAP = {
    'positive': 'positive', 'pos': 'positive', 'joy': 'joy', 'happy': 'joy', 'love': 'joy', 'optimism': 'joy',
    'negative': 'negative', 'neg': 'negative',
    'neutral': 'neutral', 'neu': 'neutral',
    'fear': 'fear', 'scared': 'fear', 'nervousness': 'fear', 'anxiety': 'fear', 'afraid': 'fear',
    'sadness': 'sadness', 'sad': 'sadness', 'grief': 'sadness', 'disappointment': 'sadness',
    'anger': 'anger', 'angry': 'anger', 'disgust': 'anger', 'annoyance': 'anger',
    'surprise': 'neutral',
}

DOMAIN_BOOTSTRAP = [
    ('I am feeling better and feel safe today', 'positive'),
    ('Doing well with counsellor support', 'positive'),
    ('achha lag raha hai, safer feel kar raha hoon', 'positive'),
    ('मुझे सुरक्षित महसूस हो रहा है', 'positive'),
    ('neutral update, nothing new to report', 'neutral'),
    ('court date next week, waiting', 'neutral'),
    ('I am scared and someone threatened my family', 'fear'),
    ('Mujhe bahut darr lag raha hai, dhamki mili', 'fear'),
    ('मुझे डर लग रहा है धमकी मिली है', 'fear'),
    ('neend nahi aa rahi, ghabrahat ho rahi hai', 'fear'),
    ('I feel hopeless and alone', 'sadness'),
    ('ummeed nahi rahi, akela hoon', 'sadness'),
    ('रोना आ रहा है, बेबस हूँ', 'sadness'),
    ('I am angry about the injustice and delay', 'anger'),
    ('bahut gussa aa raha hai police kuch nahi karti', 'anger'),
    ('compensation pending for months, financial hardship', 'negative'),
    ('investigation delay, fir pending, no hope', 'negative'),
    ('witness intimidation, mat bolna intimidation', 'fear'),
    ('relocation chahiye safe house madad', 'fear'),
    ('feeling better after rehabilitation support', 'positive'),
]


def normalize_label(raw: str) -> str | None:
    key = re.sub(r'\s+', ' ', str(raw).strip().lower())
    return LABEL_MAP.get(key)


def load_jsonl(path: Path):
    texts, labels = [], []
    with path.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            label = normalize_label(row.get('label', ''))
            text = ' '.join(str(row.get('text', '')).split())
            if label and text:
                texts.append(text)
                labels.append(label)
    return texts, labels


def bootstrap_corpus():
    texts, labels = [], []
    for text, label in DOMAIN_BOOTSTRAP:
        texts.append(text)
        labels.append(label)
    # light augmentation by duplication with minor noise tags
    extra = []
    for text, label in zip(texts, labels):
        extra.append((text + ' please help', label if label != 'positive' else 'positive'))
    for t, l in extra:
        texts.append(t)
        labels.append(l)
    return texts, labels


def train(texts, labels, version: str):
    if len(texts) < 12:
        raise SystemExit('Need at least 12 labeled texts')
    # If only few classes, still train
    le = LabelEncoder()
    y = le.fit_transform(labels)
    # Stratify only when every class has >=2 samples
    counts = Counter(labels)
    strat = y if min(counts.values()) >= 2 and len(texts) >= 20 else None
    try:
        x_train, x_test, y_train, y_test = train_test_split(texts, y, test_size=0.25, random_state=26094, stratify=strat)
    except ValueError:
        x_train, x_test, y_train, y_test = train_test_split(texts, y, test_size=0.25, random_state=26094)
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=8000, token_pattern=r'(?u)[\w\u0900-\u097f]+')
    xt = vec.fit_transform(x_train)
    model = LogisticRegression(max_iter=1000, class_weight='balanced', random_state=26094)
    model.fit(xt, y_train)
    pred = model.predict(vec.transform(x_test))
    report = classification_report(y_test, pred, target_names=list(le.classes_), zero_division=0)
    macro = float(f1_score(y_test, pred, average='macro', zero_division=0))
    print(report)
    print('macro_f1', macro)
    # Portable JSON (no pickle)
    vocab = {tok: int(i) for tok, i in vec.vocabulary_.items()}
    # sklearn idf_ aligns with vocabulary indices
    idf = [0.0] * len(vocab)
    for tok, i in vocab.items():
        idf[i] = float(vec.idf_[i])
    coef = model.coef_
    # binary case: sklearn may return shape (1, n)
    if coef.shape[0] == 1 and len(le.classes_) == 2:
        # reconstruct two-class form
        coef_list = [(-coef[0]).tolist(), coef[0].tolist()]
        intercept = [float(-model.intercept_[0]), float(model.intercept_[0])]
    else:
        coef_list = [row.tolist() for row in coef]
        intercept = [float(v) for v in model.intercept_]
    artifact = {
        'version': version,
        'training_date': datetime.now(timezone.utc).isoformat(),
        'classes': list(le.classes_),
        'vocabulary': vocab,
        'idf': idf,
        'coef': coef_list,
        'intercept': intercept,
        'macro_f1_holdout': macro,
        'n_train': len(x_train),
        'n_test': len(x_test),
        'limitations': 'Trained on supplied/bootstrap corpus; domain shift expected vs real victim narratives. Not clinical.',
    }
    out = ROOT / 'ai' / 'models' / 'text_sentiment.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact), encoding='utf-8')
    metrics = {k: artifact[k] for k in ['version', 'macro_f1_holdout', 'n_train', 'n_test', 'classes', 'limitations', 'training_date']}
    (ROOT / 'ai' / 'models' / 'text_sentiment_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print('Wrote', out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('inputs', nargs='*', type=Path, help='JSONL files with text,label')
    parser.add_argument('--bootstrap', action='store_true', help='Include authored domain seed corpus')
    parser.add_argument('--version', default='tfidf-logistic-v1')
    args = parser.parse_args()
    texts, labels = [], []
    for path in args.inputs:
        t, l = load_jsonl(path)
        texts.extend(t)
        labels.extend(l)
        print(f'Loaded {len(t)} from {path}')
    if args.bootstrap or not texts:
        bt, bl = bootstrap_corpus()
        texts.extend(bt)
        labels.extend(bl)
        print(f'Added bootstrap domain corpus ({len(bt)} rows)')
    train(texts, labels, args.version)


if __name__ == '__main__':
    main()
