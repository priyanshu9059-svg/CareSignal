# CareSignal — SIH 26094

AI-assisted wellbeing monitoring and human-led support for fictional atrocity-case participants. Existing systems track the case; CareSignal tracks changes in wellbeing alongside the case and connects concerns to support. This is a runnable prototype, not a clinical tool or a government integration.

## Run locally on Windows

Python 3.11+ and Node 24 are used. The working app is in `frontend/` and `backend/`. Original static HTML/CSS/JS lives under `legacy/` as a visual reference only — do not open it to run the application.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe ai/train.py
cd backend
..\.venv\Scripts\python.exe migrate.py
..\.venv\Scripts\python.exe -m app.seed
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from the project root:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:3000**. API docs: **http://127.0.0.1:8000/docs**. The frontend proxies `/api/*` to FastAPI, keeping authentication cookies on the same origin. Do not open files under `legacy/` to run the application.

## Database and environment

With no environment variables, local development uses `backend/demo.db` (SQLite) and a random, process-local JWT key. Restarting the backend invalidates sessions unless you configure a persistent key. Copy `.env.example` to `.env` and set a long random `JWT_SECRET` for persistence. PostgreSQL deployments require `JWT_SECRET`. `DATABASE_URL` accepts PostgreSQL through the `postgresql+psycopg://` driver. The Docker deployment uses PostgreSQL. Never check `.env` or real data into source control.

Docker: set `POSTGRES_PASSWORD` and `JWT_SECRET` in `.env`, then run:

```sh
docker compose up --build
```

The compose stack includes frontend, backend, and PostgreSQL with a persistent voice storage volume. Rate limiting is process-local; this prototype runs synchronously. Demo seeding is skipped when `DEMO_ENABLED=false`. Docker is not required for the SQLite development path. See [DEPLOYMENT.md](DEPLOYMENT.md).

### Public Render deployment

Push the repository to GitHub, sign in to Render, select **New → Blueprint**, connect the repository, and approve its root `render.yaml`. The blueprint creates one public Uvicorn application service plus PostgreSQL, generates the JWT secret, runs migrations, and seeds synthetic demo data. Share the resulting `https://caresignal-sih-26094...onrender.com` address. Review any displayed pricing before approving resources; provider plan availability can change.

## Demo accounts

All listed demo accounts use `Demo@123`. These are intentionally public synthetic demonstration credentials, not production secrets. Seed password can be overridden through `DEMO_PASSWORD` on a fresh database.

| Email | Scope |
|---|---|
| victim@demo.com | Own case AT-20481; no internal notes or risk analytics |
| counsellor@demo.com | Assigned cases in Bhopal |
| officer@demo.com | Bhopal district cases |
| state@demo.com | Madhya Pradesh aggregate dashboard |
| national@demo.com | National aggregate dashboard |
| admin@demo.com | System administration, model metrics, audit log |

## Implemented workflow

Consent → English/Hindi/Hinglish structured check-in → optional text and PCM WAV recording → multilingual contextual signals and acoustic measurements → separate distress/safety/escalation estimates → saved longitudinal assessment and explanation → staff alerts → human-confirmed intervention → scheduled contact → participant support journey → new assessment and observed outcome.

Features include role and case authorization, append-only consent history, notification center with simulated SMS/email status, guided support chat, case-event timeline, filters, charts, Leaflet district markers, demo scenario submissions, measured synthetic model metrics, and scoped aggregate dashboards. Consent withdrawal blocks new optional analyses; support requests remain available.

## Data and models

`python ai/train.py` deterministically generates **2,400 records across 150 synthetic people**, trains a logistic regression, and saves portable JSON coefficients and actual evaluation metrics. The split holds out 30 people. The database seed creates **50 cases, 600 assessments, 150 case events, 100 interventions and 50 follow-ups**. Seeded historical scores are explicitly marked synthetic rather than misrepresented as new model outputs. AT-20481 contains the eight-point flagship trajectory after four earlier baseline records.

`AI_MODE=demo` uses deterministic contextual text rules, actual voice measurements and the synthetic-trained escalation model. `local` uses the same available local artifacts with disclosed NLP fallback. `production` disables demo seeding and requires a JWT key; external NLP/ASR models and government integrations are **not included**. Missing escalation artifacts use a disclosed rule index. No GPU, external key, or dataset download is required.

Dataset sources and optional normalization: [DATASETS.md](DATASETS.md), [data/README.md](data/README.md). No third-party dataset is downloaded or redistributed by this repository.

## Verification

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -q
cd ../frontend
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests need both servers running and use synthetic demo accounts. They submit new demo assessments and interventions. Backend tests use a separate temporary SQLite database. Browser microphone permission and provider-specific speech recognition must also be checked on the presentation machine.

If Chromium download is unavailable and Microsoft Edge is installed, run `$env:PLAYWRIGHT_CHANNEL='msedge'` before `npm run test:e2e` in PowerShell. The browser suite uses a simulated microphone to exercise recording/upload/analysis without recording anyone. `backend/requirements.lock.txt` records the exact tested Python environment; use it instead of `requirements.txt` for a matching Windows Python 3.11 installation.

## Architecture and documentation

Next.js / React / TypeScript / Tailwind, Recharts, Leaflet, Lucide → same-origin proxy → Python FastAPI → SQLAlchemy / PostgreSQL (SQLite local option) → modular analysis and workflow services. See [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md), [AI_PIPELINE.md](AI_PIPELINE.md), [SECURITY.md](SECURITY.md), and [DEMO_GUIDE.md](DEMO_GUIDE.md).

## Limitations and future scope

This implementation has no clinical validation. Text emotion intensities are heuristic. Voice returns a disclosed acoustic emotion/stress proxy when available (optional `voice_emotion.json`), not a validated speech-emotion classifier. Speech recognition depends on browser support; server ASR returns an explicit fallback message. Model accuracy on synthetic data does not establish effectiveness on people. Missing inputs are excluded and weights renormalized. Demo outcomes are observational and do not prove treatment effects.

District maps need internet for OpenStreetMap tiles. Optional voice check-ins store acoustic features and the WAV under `storage/voices/` for authorized staff playback. Outreach defaults to mock/log adapters; configure `EMAIL_PROVIDER` / `SMS_PROVIDER` / webhook for external delivery. Server ASR is optional (`ASR_PROVIDER` + OpenAI or local Whisper). State/national pages have no row-level case access. Operational hardening, representative multilingual evaluation, calibrated confidence, distributed rate limits, field retention/deletion policies, accessibility audits, and government integrations remain future work. The installable manifest/offline page is a minimal PWA shell; check-ins require connectivity and are never silently queued offline.
