# CareSignal ML Lab (Google Colab / local Jupyter)

Updated for multi-dataset training (`tfidf-logistic-v3-kaggle`).

## Files

| File | Purpose |
|---|---|
| `CareSignal_ML_Lab.ipynb` | Source notebook (run this) |
| `CareSignal_ML_Lab_executed.ipynb` | Last successful local run with outputs |

## Run locally

```powershell
# run from the CareSignal repository root
.\.venv\Scripts\python.exe -m jupyter notebook notebooks\CareSignal_ML_Lab.ipynb
```

Or re-execute headlessly:

```powershell
.\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute notebooks\CareSignal_ML_Lab.ipynb --output CareSignal_ML_Lab_executed.ipynb --ExecutePreprocessor.timeout=300
```

## Run on Colab

1. Upload `CareSignal_ML_Lab.ipynb`
2. Upload zip of the repo (or at least `backend/`, `ai/models/`, optionally `data/processed/`)
3. Runtime → Run all  
   `REPO_ROOT` auto-detects `/content/CareSignal` or the local Windows path.

## What it shows

- Dataset inventory (GoEmotions, SentiMix, IndicSentiment, Kaggle)
- Live sentiment/emotion on EN / Hindi / Hinglish
- Voice stress + emotion proxy
- Distress / safety / escalation score comparison
- Model metrics charts (text F1 ~0.80, voice F1 ~0.90, escalation AUC ~0.70)

See also: [`../DOWNLOAD_GUIDE.md`](../DOWNLOAD_GUIDE.md), [`../DATASET_ANALYSIS.md`](../DATASET_ANALYSIS.md).
