"""Train a small linear voice-emotion proxy from a features CSV (never auto-downloads audio).

Expected CSV columns (from your own CREMA-D/RAVDESS/TESS feature extraction):
  energy,pause_ratio,pitch_mean,pitch_variability,spectral_centroid,mfcc1..mfcc5,label

Labels mapped to: fear, anger, sadness, joy, neutral

Or use --bootstrap to fit on synthetic acoustic feature rows so the API can load voice_emotion.json.

Example:
  python ai/train_voice_proxy.py data/processed/crema_features.csv
  python ai/train_voice_proxy.py --bootstrap
"""
from __future__ import annotations
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
LABEL_MAP = {
    'fear': 'fear', 'fearful': 'fear', 'anxious': 'fear',
    'anger': 'anger', 'angry': 'anger', 'disgust': 'anger',
    'sad': 'sadness', 'sadness': 'sadness',
    'happy': 'joy', 'happiness': 'joy', 'joy': 'joy',
    'neutral': 'neutral', 'calm': 'neutral',
}
FEATURE_NAMES = ['energy', 'pause_ratio', 'pitch_mean', 'pitch_variability', 'spectral_centroid',
                 'mfcc1', 'mfcc2', 'mfcc3', 'mfcc4', 'mfcc5']


def bootstrap_rows(n=400, seed=26094):
    rng = np.random.default_rng(seed)
    rows = []
    # Roughly separable synthetic clusters inspired by SER acoustics literature
    centers = {
        'fear': dict(energy=0.14, pause=0.25, pitch=220, pvar=55, cent=900),
        'anger': dict(energy=0.18, pause=0.15, pitch=200, pvar=70, cent=1100),
        'sadness': dict(energy=0.05, pause=0.55, pitch=140, pvar=20, cent=500),
        'joy': dict(energy=0.12, pause=0.2, pitch=210, pvar=40, cent=950),
        'neutral': dict(energy=0.08, pause=0.3, pitch=165, pvar=25, cent=700),
    }
    for label, c in centers.items():
        for _ in range(n // len(centers)):
            rows.append([
                float(np.clip(rng.normal(c['energy'], 0.02), 0.01, 0.4)),
                float(np.clip(rng.normal(c['pause'], 0.08), 0.02, 0.9)),
                float(rng.normal(c['pitch'], 15)),
                float(np.clip(rng.normal(c['pvar'], 8), 1, 120)),
                float(rng.normal(c['cent'], 80)),
                *rng.normal(0, 1, 5).tolist(),
                label,
            ])
    return rows


def load_csv(path: Path):
    rows = []
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            label = LABEL_MAP.get(str(row.get('label', '')).strip().lower())
            if not label:
                continue
            try:
                feats = [float(row[k]) for k in FEATURE_NAMES]
            except (KeyError, ValueError):
                continue
            rows.append(feats + [label])
    return rows


def train(rows, version='voice-linear-v1'):
    x = np.array([r[:-1] for r in rows], dtype=float)
    labels = [r[-1] for r in rows]
    le = LabelEncoder()
    y = le.fit_transform(labels)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, random_state=26094, stratify=y)
    scaler = StandardScaler().fit(x_train)
    model = LogisticRegression(max_iter=1000, class_weight='balanced', random_state=26094)
    model.fit(scaler.transform(x_train), y_train)
    pred = model.predict(scaler.transform(x_test))
    macro = float(f1_score(y_test, pred, average='macro'))
    print('macro_f1', macro, 'classes', [str(c) for c in le.classes_])
    artifact = {
        'version': version,
        'training_date': datetime.now(timezone.utc).isoformat(),
        'classes': [str(c) for c in le.classes_],
        'features': FEATURE_NAMES,
        'mean': [float(v) for v in scaler.mean_],
        'scale': [float(v) for v in scaler.scale_],
        'coef': [[float(v) for v in row] for row in model.coef_],
        'intercept': [float(v) for v in model.intercept_],
        'macro_f1_holdout': macro,
        'n_train': int(len(x_train)),
        'n_test': int(len(x_test)),
        'limitations': 'Acoustic proxy; if trained on acted SER (CREMA/RAVDESS/TESS) expect domain shift on victim speech. Not clinical.',
    }
    out = ROOT / 'ai' / 'models' / 'voice_emotion.json'
    out.write_text(json.dumps(artifact), encoding='utf-8')
    (ROOT / 'ai' / 'models' / 'voice_emotion_metrics.json').write_text(
        json.dumps({k: artifact[k] for k in ['version', 'macro_f1_holdout', 'classes', 'n_train', 'n_test', 'limitations', 'training_date']}, indent=2),
        encoding='utf-8')
    print('Wrote', out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', nargs='?', type=Path)
    parser.add_argument('--bootstrap', action='store_true')
    args = parser.parse_args()
    rows = []
    if args.csv:
        rows.extend(load_csv(args.csv))
        print('Loaded', len(rows), 'from', args.csv)
    if args.bootstrap or not rows:
        rows.extend(bootstrap_rows())
        print('Added bootstrap synthetic acoustic rows')
    train(rows)


if __name__ == '__main__':
    main()
