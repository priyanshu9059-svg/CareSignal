# Data layout

- `raw/`: user-supplied, license-approved datasets; ignored by Git.
- `processed/`: normalized JSONL from `preprocess.py`.
- `synthetic/longitudinal.csv`: 2,400 generated weekly records; reproducible with `ai/train.py`.
- `demo/text.json`: authored English/Hindi/Hinglish examples.

Database seeding is separate: `python -m app.seed` from `backend/`. It creates 50 fictional identities and cases, 600 assessments, 150 case events, 100 interventions and 50 follow-ups. It does not load real participants. Seeds are idempotent on a fresh complete database. To create another demonstration database, point DATABASE_URL to a new file rather than deleting an existing database.

See `../DATASETS.md` for source and access instructions. Runtime voice WAVs are stored under project `storage/voices/` (not under `data/`), with acoustic features also persisted in the database.
