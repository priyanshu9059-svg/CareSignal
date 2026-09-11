# Dataset analysis for CareSignal ML upgrades (SIH 26094)

This document compares the datasets you listed against CareSignal’s needs (victim wellbeing monitoring, Hinglish/Hindi, distress escalation, voice stress). It is research guidance — not a claim that any third-party data is redistributed in this repo.

## Executive verdict

| Priority for CareSignal | Datasets | Why |
|---|---|---|
| **Use now (high ROI)** | SentiMix Hinglish, IndicSentiment (Hindi), Kaggle 6-emotion / GoEmotions (mapped), CREMA-D + RAVDESS acoustics features | Match language or label space we can train on CPU with sklearn / small models |
| **Use carefully** | MELD, TESS | Useful for emotion labels, but English TV/acted speech ≠ atrocity-case victims |
| **Do not depend on for demo** | DAIC-WOZ, IndicVoices / IndicVoices-R | Access-controlled or huge; wrong claim risk if we imply clinical depression scoring |

**Critical rule:** Sentiment ≠ emotion ≠ clinical distress ≠ future escalation. Mixing labels without a mapping layer invents false accuracy. CareSignal keeps **separate heads**: text sentiment/signals, text emotions, voice acoustics/proxy emotion, distress fusion, escalation logistic.

---

## Text / NLP

### 1. Kaggle — Sentiment and Emotion Analysis (kushagra3204)
- **Size:** ~422k emotion sentences (joy, sadness, anger, surprise, fear, disgust) + ~3.3k binary sentiment.
- **Quality:** Large, easy CSV; often an **aggregate of prior public emotion corpora**, English-heavy, not domain-specific to victims/atrocities.
- **Reported use:** Suitable for BiLSTM / transformer emotion classifiers in student projects; treat published “85%” claims as **non-comparable** unless split/protocol is verified.
- **Fit for us:** Good **optional training corpus** for 6-class emotion head and coarse sentiment. Not Indian-language, not justice-domain.
- **Action:** Download manually → `data/preprocess.py` → `ai/train_text.py`.

### 2. SentiMix / SemEval-2020 Task 9
- **Size:** ~20k Hinglish tweets (+ Spanglish); word-level LID + sentence sentiment (pos/neu/neg).
- **SOTA (official):** ~**75.0 weighted F1** (BERT ensembles); strong systems ~70–73 F1 (mBERT etc.).
- **Fit for us:** **Best public match** for code-mixed victim check-ins (Roman Hindi + English).
- **Gap:** Twitter slang ≠ court/threat/rehab language; still invaluable for Hinglish polarity.
- **Action:** Highest-priority text sentiment upgrade after lexicon enrichment.

### 3. IndicSentiment (AI4Bharat)
- **Content:** Product/service reviews with pos/neg/neu across Indic languages (English + INDIC REVIEW fields).
- **Fit for us:** Strong for **Hindi/Indic polarity** evaluation and light fine-tuning; domain is e-commerce, not trauma.
- **Action:** Evaluate Hindi sentiment; expand lexicon with failure cases; optional train JSONL.

### 4. GoEmotions (Google Research)
- **Size:** ~58k Reddit comments; **27 emotions + neutral** (multi-label).
- **Official BERT:** avg F1 **~0.46** (fine-grained); ~0.64 Ekman-6; ~0.69 sentiment grouping.
- **Fit for us:** Best taxonomy inspiration. Map to CareSignal’s fear / sadness / anger / neutral (+ optional anxiety via nervousness/fear).
- **Honesty:** Fine-grained 27-way is hard; we should report **Ekman-style or CareSignal-4**, not claim GoEmotions SOTA.

### 5. MELD
- **Size:** ~13k utterances from *Friends*; text + audio + video; 7 emotions + sentiment.
- **Typical SER/text:** Conversational models often land ~50–65% depending on setup; multimodal helps but domain is entertainment dialogue.
- **Fit for us:** Secondary; good for multimodal storytelling, weak for victim interviews.

---

## Speech / voice emotion

### 6–8. RAVDESS, CREMA-D, TESS
| Dataset | Nature | Scale | Typical in-domain SER* |
|---|---|---|---|
| RAVDESS | Acted speech/song | ~7k files, 24 actors | Often ~80–97% (setup-dependent) |
| CREMA-D | Acted, 91 actors | 7,442 clips | Often ~68–90%+ |
| TESS | Acted, 2 actresses | 2,800 | Often near-ceiling (~100% in some papers) |

\*In-domain numbers **collapse under cross-corpus tests**. Literature (Interspeech 2024 SER benchmark) shows models do **not** generalize cleanly across SER datasets.

**Fit for us:**
- Train a small acoustic classifier **only if** we keep emotion as `proxy` / `acted-speech-trained`, never “true victim emotion.”
- Immediate win without GB downloads: use pitch, energy, pause, MFCC stats as a **disclosed heuristic stress/emotion proxy** (already partially implemented), then optionally train sklearn on downloaded CREMA-D/RAVDESS features.

### 9. IndicVoices / IndicVoices-R
- **Scale:** Tens of thousands of hours, 22 languages (ASR/TTS focused).
- **Fit for us:** Future **ASR robustness** for Hindi/vernacular — not emotion labels. Too large for SIH training loop; cite as roadmap.

---

## Distress / mental-health

### 10. DAIC-WOZ
- **Content:** ~189 clinical interviews (audio, video, transcripts) + PHQ-style labels; **academic access only**.
- **Reality check:** Many published MAEs look strong but recent reviews warn of **subject leakage**, interviewer-text contamination, and models that **fail to beat a mean predictor** under clean protocols.
- **Fit for us:** Conceptual inspiration (interview → distress score). **Do not** claim DAIC-trained depression detection in the SIH demo without access + clean evaluation. Wrong domain ethically if presented as atrocity-victim clinical AI.

---

## Mapping onto CareSignal architecture

```
Check-in text ──► Lexicon signals (domain) ──┐
               └► Sentiment model (SentiMix/Indic/Kaggle) ─┼─► NLP block
               └► Emotion head (GoEmotions→fear/sad/anger) ─┘
Voice WAV ────► Acoustics + optional SER proxy ───────────► voice block
Questionnaire + case conditions + trends ─────────────────► distress fusion
History features ─────────────────────────────────────────► escalation logistic (synthetic today)
```

### What we implement in-repo (no illegal redistribution)
1. **Richer multilingual domain lexicon** (authored, justice/wellbeing phrases) — immediate demo lift.
2. **Graded emotion intensities** (evidence density, GoEmotions-inspired mapping).
3. **Voice emotion/stress proxy** from acoustics (disclosed heuristic).
4. **Optional trainers** (`ai/train_text.py`, `ai/train_voice_proxy.py`) that consume **locally downloaded** processed JSONL/CSV under `data/raw/` → write portable JSON models under `ai/models/`.
5. Keep escalation logistic synthetic until/unless DAIC-class data is legally obtained and properly split.

### What judges should hear
- We **evaluated and prioritized** these corpora by language, license, and task fit.
- Production path is **modular heads** trained on public sentiment/emotion/SER data + **domain lexicon** for atrocity-case language.
- Clinical distress prediction requires gated datasets and ethics review; the prototype is **transparent** about synthetic escalation training.

---

## Recommended download order (manual)

1. SentiMix Hinglish train/dev/test (or HF mirrors if licensed for your use)
2. Kaggle emotion CSV **or** GoEmotions TSV from Google Research GitHub
3. IndicSentiment Hindi subset from Hugging Face
4. CREMA-D (easiest multi-speaker SER) then RAVDESS
5. Skip IndicVoices for the hackathon build; mention as ASR future work
6. DAIC-WOZ only if you can get academic approval before finals

Normalize any CSV with:

```powershell
python data/preprocess.py data/raw/my.csv data/processed/my.jsonl --text-column text --label-column label --language hinglish
python ai/train_text.py data/processed/my.jsonl
```
