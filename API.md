# API

Interactive, generated contracts: `http://127.0.0.1:8000/docs`; machine-readable OpenAPI: `/openapi.json`. Browser requests use `/api` on the Next.js origin. Dates are ISO 8601; client-facing times use the browser locale. Errors use `{ "detail": "message" }` (Pydantic validation can return a structured list).

Authentication: `POST /auth/login` with `{email,password}` sets an HttpOnly, SameSite=Strict JWT cookie for eight hours. `POST /auth/logout` clears the browser cookie and revokes the JWT `jti` until expiry. `GET /me` returns the user's role and latest consent. Bearer tokens are accepted for programmatic clients, but login does not expose the token to frontend JavaScript. `POST /auth/register` is system-admin-only and creates the linked victim identity when appropriate.

Consent: `POST /consents` accepts `{wellbeing, voice, language, erase_voice?, erase_checkins?}`. Optional erase flags remove stored WAVs and/or redact free-text when withdrawing. `POST /privacy/erase` performs erasure without changing consent. `GET /health` reports database and storage checks.

| Routes | Authorization / behavior |
|---|---|
| POST /consents | Participant; saves a new versioned consent record |
| GET /cases, GET /cases/{id} | Own / assigned / district scope; no state or national access |
| POST /cases | Officer in own district, or admin |
| POST /case-events, GET /cases/{id}/timeline | Authorized case staff |
| POST /assessments, POST /risk/calculate | Consenting participant; calculation is persisted, not a free-standing duplicate preview |
| GET /assessments/{id} | Scoped participant projection or staff detail |
| POST /ai/analyze-text | Participant consent or authorized staff |
| POST /ai/analyze-voice | Consenting participant; multipart case_id, optional transcript, file |
| POST /ai/transcribe | Consent-gated availability/fallback response; no server ASR installed |
| GET /cases/{id}/risk-history, /explanation | Scoped staff only |
| GET /alerts, /alerts/{id} | Scoped staff only |
| POST /alerts/{id}/acknowledge, PATCH /alerts/{id} | Scoped staff; status/optional assignment |
| POST /interventions, GET /interventions, PATCH /interventions/{id} | Human staff authorization, same-district assignee |
| POST /follow-ups, PATCH /follow-ups/{id} | Scoped staff; future time required for scheduling |
| GET /follow-ups | Scoped; no internal notes for participant |
| POST /support-requests | Participant's own case; available after optional consent withdrawal |
| PATCH /support-requests/{id} | Scoped staff; progress and internal notes |
| GET /directory | System administrator; users, regions and participants awaiting a case |
| GET /notifications, PATCH /notifications/{id}/read | Owner only |
| GET /dashboard/district | Officer, assigned counsellor, system administrator |
| GET /dashboard/state | State administrator's state, system administrator |
| GET /dashboard/national | National or system administrator |
| GET /research, GET /audit-logs | System administrator |
| POST /chat | Consenting participant; confirmation needed to report safety concern |
| POST /demo/scenario/{name} | Consenting participant, demo enabled only |

Assessment example:

```json
{"case_id":"AT-20481","language":"hinglish","text":"Mujhe darr lag raha hai. Mere bhai ko dhamki di.","responses":{"feeling":3,"fear":4,"sleep":3,"daily":2,"avoidance":2,"legal":3,"threat":true,"safe":false,"support":true,"need":"Counselling"}}
```

Scale values are 0–4, with greater values indicating more difficulty. Null means skipped. All-skipped submissions are rejected. Voice session IDs must belong to the same case. Unknown fields are rejected. Participant submission returns an assessment ID, support recommendations and detected concern labels, not an alarming score dashboard. Authorized staff can retrieve full scores, evidence and trends.

Voice accepts at most 10 MB, 90 seconds, 8–48 kHz, 16-bit PCM WAV. Invalid recordings return 422 and do not invalidate text. Acoustic features and the source WAV are stored under `STORAGE_PATH` so authorized staff can replay via `GET /ai/voice/{id}/audio` (also available under `/api/...` on static/Render deploys). Responses may include a disclosed heuristic emotion/stress proxy when models or acoustics allow.

Framework references: [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) and [Next.js rewrites](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites).
