# How to download datasets for CareSignal

This guide is the **source → download → process → train** path. We do **not** ship third-party data in git. Everything lands under `data/raw/` (gitignored) and `data/processed/`.

---

## Quick start (recommended order)

| Step | Dataset | Needs account? | Size | Script / action |
|---|---|---|---|---|
| 1 | **GoEmotions** | No | ~50 MB | `python data/download_open.py --goemotions` |
| 2 | **IndicSentiment** | HF (free, optional) | ~20 MB | `python data/download_open.py --indic-sentiment` |
| 3 | **SentiMix Hinglish** | No (Zenodo) | ~3 MB zip | `python data/download_open.py --sentimix` |
| 4 | **Kaggle emotion CSV** | **Yes — Kaggle** | ~44 MB | Manual / Kaggle CLI (below) |
| 5 | **CREMA-D** (voice) | No (GitHub) | ~600 MB+ | Manual link below |
| 6 | RAVDESS / TESS | Zenodo / Borealis | large | Optional |
| 7 | DAIC-WOZ | Academic form | large | Request only |
| 8 | IndicVoices | HF + huge disk | 100s GB | Skip for SIH |

After downloads:

```powershell
# run from the CareSignal repository root
.\.venv\Scripts\python.exe data\prepare_downloaded.py
.\.venv\Scripts\python.exe ai\train_text.py data\processed\goemotions.jsonl data\processed\indic_sentiment.jsonl data\processed\sentimix.jsonl --bootstrap
.\.venv\Scripts\python.exe ai\train_voice_proxy.py --bootstrap
```

Restart the backend so it reloads `ai/models/text_sentiment.json`.

---

## 1) Open downloads (no Kaggle) — run this first

```powershell
# run from the CareSignal repository root
.\.venv\Scripts\python.exe -m pip install -q datasets huggingface_hub
.\.venv\Scripts\python.exe data\download_open.py --all-open
```

What this does:
- GoEmotions CSV from Google Cloud Storage → `data/raw/goemotions/`
- SentiMix zip from Zenodo → `data/raw/sentimix/`
- IndicSentiment from Hugging Face → `data/raw/indic_sentiment/` (may prompt for HF login if gated; usually public)

---

## 2) Kaggle dataset (your link)

Source: https://www.kaggle.com/datasets/kushagra3204/sentiment-and-emotion-analysis-dataset

### One-time Kaggle setup (Windows)

1. Create / log in at https://www.kaggle.com  
2. Open https://www.kaggle.com/settings → **API** → **Create New Token**  
   This downloads `kaggle.json`  
3. Place it here:

```text
%USERPROFILE%\.kaggle\kaggle.json
# or the newer token file:
%USERPROFILE%\.kaggle\access_token
```

4. Install CLI and download:

```powershell
# run from the CareSignal repository root
.\.venv\Scripts\python.exe -m pip install -q kaggle
.\.venv\Scripts\python.exe -m kaggle datasets download -d kushagra3204/sentiment-and-emotion-analysis-dataset -p data\raw\kaggle_emotion --unzip
```

You should see `combined_emotion.csv` and `combined_sentiment_data.csv`.

---

## 3) Voice datasets (optional but good for the pitch)

### CREMA-D (best first voice set)
- GitHub: https://github.com/CheyneyComputerScience/CREMA-D  
- Follow their README / release assets (AudioWAV).  
- Put WAVs under `data/raw/crema_d/`  
- Then extract features (after download):

```powershell
.\.venv\Scripts\python.exe data\preprocess_audio.py --help
```

### RAVDESS
- Zenodo: https://zenodo.org/records/1188976  
- Download speech-only ZIPs; extract to `data/raw/ravdess/`

### TESS
- https://borealisdata.ca/dataset.xhtml?persistentId=doi:10.5683/SP2/E8H2MF  
- Extract to `data/raw/tess/`

---

## 4) Do **not** block the hackathon on these

| Dataset | Why wait |
|---|---|
| **DAIC-WOZ** | Must request access: https://dcapswoz.ict.usc.edu/ (academic email, DUA) |
| **IndicVoices** | Hundreds of GB; ASR research, not emotion labels |
| **IndicVoices-R** | TTS corpus; same story for SIH |

Mention them in the pitch as **roadmap**, not as trained models.

---

## 5) Official source cheat-sheet

| Dataset | Official source |
|---|---|
| GoEmotions | https://github.com/google-research/google-research/tree/master/goemotions — GCS CSVs |
| SentiMix | https://zenodo.org/records/3974927 — https://ritual-uh.github.io/sentimix2020/ |
| IndicSentiment | https://huggingface.co/datasets/ai4bharat/IndicSentiment |
| Kaggle emotion | https://www.kaggle.com/datasets/kushagra3204/sentiment-and-emotion-analysis-dataset |
| MELD | https://affective-meld.github.io/ |
| CREMA-D | https://github.com/CheyneyComputerScience/CREMA-D |
| RAVDESS | https://zenodo.org/records/1188976 |
| TESS | doi:10.5683/SP2/E8H2MF |
| DAIC-WOZ | https://dcapswoz.ict.usc.edu/ |
| IndicVoices | https://huggingface.co/datasets/ai4bharat/IndicVoices |

License reminder: accept each provider’s terms before use. Do not commit `data/raw/` to git.

---

## 6) After files are on disk — next steps checklist

1. [ ] Run `python data/download_open.py --all-open`  
2. [ ] Set up Kaggle token and download emotion CSV  
3. [ ] Run `python data/prepare_downloaded.py` → builds `data/processed/*.jsonl`  
4. [ ] Run `python ai/train_text.py ... --bootstrap` → updates `ai/models/text_sentiment.json`  
5. [ ] Restart FastAPI / refresh Colab notebook with new model JSON  
6. [ ] Smoke-test: victim check-in in Hinglish → counsellor case detail shows NLP evidence  
7. [ ] (Optional) Download CREMA-D and train `voice_emotion.json` from real features  

If anything fails, note the dataset name + error text and we fix that path next.
