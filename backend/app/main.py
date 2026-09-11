import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .database import (
    Alert, Assessment, Base, Case, CaseEvent, Consent, District, FollowUp, Intervention,
    ModelVersion, Notification, SessionLocal, State, SupportRequest, User, Victim,
    VoiceFeature, VoiceSession, engine, get_db, now,
)
from .auth import current_user, roles, token, hash_password, verify_password, revoke_token
from .schemas import (
    AlertUpdate, AssessmentInput, CaseAssign, CaseInput, ChatInput, ConsentInput, EraseInput,
    EventInput, FollowUpInput, FollowUpUpdate, InterventionInput, InterventionUpdate,
    Login, Register, SupportInput, TextInput,
)
from .services import (
    access_case, alert_response_minutes, audit, case_detail, case_summary, consent_for,
    erase_optional_data, history_for, notify, public_user, require_consent, rows, scope,
    serialize, staff_assignment, submit_assessment, uid,
)
from .ai import analyze_text, audio_features
from .asr import asr_status, transcribe_audio
from .support_guide import guided_support
from .config import COOKIE_SECURE, DEMO_ENABLED, MODEL_PATH, AI_MODE, STORAGE_PATH

logger = logging.getLogger('caresignal')

def allowed_origins() -> set[str]:
    allowed = {'http://localhost:3000', 'http://127.0.0.1:3000'}
    primary = os.getenv('APP_ORIGIN', 'http://localhost:3000').strip()
    if primary:
        allowed.add(primary.rstrip('/'))
    extra = os.getenv('APP_ORIGINS', '')
    for item in extra.split(','):
        value = item.strip().rstrip('/')
        if value:
            allowed.add(value)
    host = os.getenv('RENDER_EXTERNAL_HOSTNAME')
    if host:
        allowed.add('https://' + host.rstrip('/'))
    url = os.getenv('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if url:
        allowed.add(url)
    return allowed

@asynccontextmanager
async def lifespan(app):
    # Schema changes go through migrate.py / Alembic; create_all only fills gaps for local/tests.
    Base.metadata.create_all(engine)
    if DEMO_ENABLED:
        from .seed import seed
        with SessionLocal() as db:
            seed(db)
    if (MODEL_PATH / 'metrics.json').exists():
        metrics = json.loads((MODEL_PATH / 'metrics.json').read_text())
        with SessionLocal() as db:
            if not db.get(ModelVersion, metrics['version']):
                db.add(ModelVersion(id=metrics['version'], data=metrics))
                db.commit()
    yield

app = FastAPI(title='CareSignal — SIH 26094', version='1.0.0', lifespan=lifespan)
requests = defaultdict(deque)

@app.middleware('http')
async def security(request: Request, call_next):
    path = request.scope.get('path', '')
    if path == '/api' or path.startswith('/api/'):
        request.scope['path'] = path[4:] or '/'
        request.state.api_prefixed = True
    else:
        request.state.api_prefixed = False
    origin = request.headers.get('origin')
    if request.method not in ['GET', 'HEAD', 'OPTIONS'] and origin and origin.rstrip('/') not in allowed_origins():
        return JSONResponse(status_code=403, content={'detail': 'Origin not allowed'})
    key = (request.client.host if request.client else 'local', 'login' if request.scope.get('path') == '/auth/login' else 'api')
    queue = requests[key]
    tick = time.monotonic()
    while queue and queue[0] < tick - 60:
        queue.popleft()
    if len(queue) >= (30 if key[1] == 'login' else 240):
        return JSONResponse(status_code=429, content={'detail': 'Please wait a minute before trying again'})
    queue.append(tick)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store'})
    return response

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error('Database operation failed: %s', type(exc).__name__)
    return JSONResponse(status_code=503, content={'detail': 'Storage is temporarily unavailable. Please retry.'})

@app.get('/health')
def health(db: Session = Depends(get_db)):
    checks = {'database': False, 'storage': False}
    try:
        db.execute(text('SELECT 1'))
        checks['database'] = True
    except SQLAlchemyError:
        logger.exception('Health database check failed')
    try:
        STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        probe = STORAGE_PATH / '.healthcheck'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        checks['storage'] = True
    except OSError:
        logger.exception('Health storage check failed')
    ok = all(checks.values())
    body = {'status': 'ok' if ok else 'degraded', 'ai_mode': AI_MODE, 'synthetic': DEMO_ENABLED, 'checks': checks}
    return JSONResponse(status_code=200 if ok else 503, content=body)

@app.post('/auth/login')
def login(body: Login, response: Response, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, 'Invalid user ID or password')
    encoded = token(user)
    response.set_cookie('session', encoded, httponly=True, secure=COOKIE_SECURE, samesite='strict', max_age=28800, path='/')
    audit(db, user, 'login', user.id)
    db.commit()
    return {'user': public_user(user)}

@app.post('/auth/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get('session')
    if request.headers.get('authorization', '').startswith('Bearer '):
        raw = request.headers['authorization'][7:]
    revoke_token(db, raw)
    db.commit()
    response.delete_cookie('session', path='/')
    return {'ok': True}

@app.post('/auth/register')
def register(body: Register, user: User = Depends(roles('admin')), db: Session = Depends(get_db)):
    if len(body.password) < 10:
        raise HTTPException(422, 'Password must contain at least 10 characters')
    if db.scalars(select(User).where(User.email == body.email.lower())).first():
        raise HTTPException(409, 'User already exists')
    if body.district_id and not db.get(District, body.district_id):
        raise HTTPException(422, 'Unknown district')
    if body.state_id and not db.get(State, body.state_id):
        raise HTTPException(422, 'Unknown state')
    if body.role in ['victim', 'counsellor', 'officer'] and not body.district_id:
        raise HTTPException(422, 'District is required')
    if body.role == 'state' and not body.state_id:
        raise HTTPException(422, 'State is required')
    new = User(id=uid('U'), email=body.email.lower(), password_hash=hash_password(body.password), name=body.name, role=body.role, district_id=body.district_id, state_id=body.state_id)
    db.add(new)
    db.flush()
    victim_id = None
    if body.role == 'victim':
        victim_id = uid('V')
        db.add(Victim(id=victim_id, user_id=new.id, alias=body.name))
    audit(db, user, 'register', new.id)
    db.commit()
    return {**public_user(new), 'victim_id': victim_id}

@app.get('/me')
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    consent = consent_for(db, user)
    return {**public_user(user), 'consent': serialize(consent) if consent else None, 'demo_enabled': DEMO_ENABLED}

@app.post('/consents')
def consent(body: ConsentInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    payload = body.model_dump()
    erase_voice = payload.pop('erase_voice', False)
    erase_checkins = payload.pop('erase_checkins', False)
    if erase_voice and body.voice:
        raise HTTPException(422, 'Cannot erase voice data while keeping voice consent')
    if erase_checkins and body.wellbeing:
        raise HTTPException(422, 'Cannot erase check-in text while keeping wellbeing consent')
    erasure = None
    if erase_voice or erase_checkins:
        erasure = erase_optional_data(db, user, erase_voice=erase_voice, erase_checkins=erase_checkins)
        audit(db, user, 'privacy erase', json.dumps(erasure))
    row = Consent(id=uid('CON'), user_id=user.id, **payload)
    db.add(row)
    audit(db, user, 'update consent', user.id)
    db.commit()
    result = serialize(row)
    if erasure is not None:
        result['erasure'] = erasure
    return result

@app.post('/privacy/erase')
def privacy_erase(body: EraseInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    erasure = erase_optional_data(db, user, erase_voice=body.erase_voice, erase_checkins=body.erase_checkins)
    audit(db, user, 'privacy erase', json.dumps(erasure))
    db.commit()
    return {'ok': True, 'erasure': erasure}

@app.get('/cases')
def cases(mine: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    values = scope(db, user)
    if mine and user.role in {'counsellor', 'officer'}:
        values = [c for c in values if c.assigned_to == user.id]
    audit(db, user, 'view', 'case list')
    db.commit()
    if user.role == 'victim':
        return [{'id': c.id, 'stage': c.stage} for c in values]
    return sorted([case_summary(db, c) for c in values], key=lambda c: max(c['scores'].values()) if c['scores'] else -1, reverse=True)

@app.post('/cases')
def create_case(body: CaseInput, user: User = Depends(roles('admin', 'officer')), db: Session = Depends(get_db)):
    victim = db.get(Victim, body.victim_id)
    if not victim or not db.get(District, body.district_id):
        raise HTTPException(422, 'Unknown victim or district')
    if user.role == 'officer' and (body.district_id != user.district_id or db.get(User, victim.user_id).district_id != user.district_id):
        raise HTTPException(403, 'District mismatch')
    if db.scalars(select(Case).where(Case.victim_id == victim.id)).first():
        raise HTTPException(409, 'Victim already has a case')
    case = Case(id=uid('AT'), **body.model_dump())
    db.add(case)
    audit(db, user, 'create case', case.id)
    db.commit()
    return case_summary(db, case)

@app.get('/cases/{case_id}')
def detail(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = access_case(db, user, case_id)
    audit(db, user, 'view case', case_id)
    db.commit()
    return case_detail(db, user, case)

@app.patch('/cases/{case_id}/assign')
def assign_case(case_id: str, body: CaseAssign, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    case = access_case(db, user, case_id)
    assigned = db.get(User, body.assigned_to)
    if not assigned or assigned.role not in ['counsellor', 'officer'] or assigned.district_id != case.district_id:
        raise HTTPException(422, 'Select a counsellor or officer from the case district')
    if user.role == 'counsellor' and user.district_id != case.district_id:
        raise HTTPException(403, 'Counsellors may only hand over cases in their district')
    case.assigned_to = assigned.id
    notify(db, assigned.id, f'{case.id}: case handed over to you', case.id, priority='High', body=f'Case {case.id} was assigned to you for follow-up.')
    victim = db.get(Victim, case.victim_id)
    notify(db, victim.user_id, 'Your support contact was updated', case.id, body='A support team member is now assigned to your case.')
    audit(db, user, 'handover case', case.id)
    db.commit()
    return case_summary(db, case)

@app.get('/staff')
def staff(user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    query = select(User).where(User.role.in_(['officer', 'counsellor']))
    if user.role != 'admin':
        query = query.where(User.district_id == user.district_id)
    return [public_user(u) for u in db.scalars(query)]

@app.get('/directory')
def directory(user: User = Depends(roles('admin')), db: Session = Depends(get_db)):
    return {'districts': [serialize(d) for d in db.scalars(select(District))],
            'states': [serialize(s) for s in db.scalars(select(State))],
            'users': [public_user(u) for u in db.scalars(select(User))],
            'unlinked_victims': [serialize(v) for v in db.scalars(select(Victim).where(~Victim.id.in_(select(Case.victim_id))))]}

@app.post('/case-events')
def event(body: EventInput, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    case = access_case(db, user, body.case_id)
    row = CaseEvent(id=uid('EV'), case_id=case.id, data=body.model_dump(exclude={'case_id'}))
    db.add(row)
    if body.kind != 'general':
        case.conditions = {**case.conditions, body.kind: int(body.active)}
    audit(db, user, 'add event', case.id)
    db.commit()
    return serialize(row)

@app.get('/cases/{case_id}/timeline')
def timeline(case_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    access_case(db, user, case_id)
    return {'events': [serialize(e) for e in rows(db, CaseEvent, case_id)], 'assessments': history_for(db, case_id)}

@app.post('/assessments')
def assessment(body: AssessmentInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    result = submit_assessment(db, user, body)
    return {'assessment_id': result['assessment_id'], 'message': 'Your check-in has been recorded. Your support team can review your concerns.',
            'recommendations': result['recommendations'], 'signals': [s.replace('_', ' ') for s, v in result['signals'].items() if v]}

@app.get('/assessments/{assessment_id}')
def get_assessment(assessment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Assessment, assessment_id)
    if not item:
        raise HTTPException(404, 'Assessment not found')
    access_case(db, user, item.case_id)
    if user.role == 'victim':
        return {'id': item.id, 'created_at': item.created_at, 'recommendations': item.data['recommendations']}
    audit(db, user, 'view assessment', item.id)
    db.commit()
    return serialize(item)

@app.post('/risk/calculate')
def risk(body: AssessmentInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    return assessment(body, user, db)

@app.get('/cases/{case_id}/risk-history')
def risk_history(case_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    access_case(db, user, case_id)
    return history_for(db, case_id)

@app.get('/cases/{case_id}/explanation')
def explanation(case_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    access_case(db, user, case_id)
    values = rows(db, Assessment, case_id)
    return values[-1].data if values else None

@app.post('/ai/analyze-text')
def text_analysis(body: TextInput, user: User = Depends(roles('victim', 'officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    if user.role == 'victim':
        require_consent(db, user)
    return analyze_text(body.text, body.language)

@app.post('/ai/analyze-voice')
async def voice(case_id: str = Form(...), transcript: str = Form(''), file: UploadFile = File(...), user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    access_case(db, user, case_id)
    require_consent(db, user, True)
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Maximum recording size is 10 MB')
    if len(transcript) > 10000:
        raise HTTPException(422, 'Transcript too long')
    try:
        features = audio_features(raw, transcript)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    previous = rows(db, VoiceSession, case_id)
    baseline = None
    if len(previous) >= 3:
        import numpy as np
        baseline = {k: float(np.mean([p.data[k] for p in previous[:3] if p.data.get(k) is not None])) for k in ['energy', 'pause_ratio', 'pitch_mean', 'speech_rate'] if any(p.data.get(k) is not None for p in previous[:3])}
        deviations = [abs(features[k] - v) / max(abs(v), .05) for k, v in baseline.items() if features.get(k) is not None]
        features['baseline_deviation'] = round(min(1, float(np.mean(deviations))), 3) if deviations else None
    features['baseline'] = baseline
    features['baseline_note'] = 'Supporting deviation from first three recordings' if baseline else 'At least three earlier recordings are needed for a personal baseline'
    row = VoiceSession(id=uid('VOICE'), case_id=case_id, data=features)
    db.add(row)
    db.flush()
    voice_dir = STORAGE_PATH / 'voices' / case_id
    voice_dir.mkdir(parents=True, exist_ok=True)
    audio_path = voice_dir / f'{row.id}.wav'
    audio_path.write_bytes(raw)
    features = {**features, 'stored': True, 'audio_path': str(audio_path.relative_to(STORAGE_PATH)).replace('\\', '/')}
    row.data = features
    db.add(VoiceFeature(id=uid('VF'), voice_session_id=row.id, data=features))
    audit(db, user, 'create voice features', row.id)
    db.commit()
    return {'voice_session_id': row.id, **features}

@app.get('/ai/voice/{voice_id}/audio')
def voice_audio(voice_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(VoiceSession, voice_id)
    if not item:
        raise HTTPException(404, 'Voice session not found')
    access_case(db, user, item.case_id)
    rel = (item.data or {}).get('audio_path')
    path = (STORAGE_PATH / rel) if rel else (STORAGE_PATH / 'voices' / item.case_id / f'{item.id}.wav')
    if not path.exists() or not path.is_file():
        raise HTTPException(404, 'Recording file is not available (older sessions may only store acoustic features)')
    try:
        path.resolve().relative_to(STORAGE_PATH.resolve())
    except ValueError:
        raise HTTPException(404, 'Recording file is not available')
    audit(db, user, 'play voice recording', item.id)
    db.commit()
    return FileResponse(path, media_type='audio/wav', filename=f'{item.id}.wav')

@app.post('/ai/transcribe')
async def transcribe(
    language: str = Form('en'),
    file: UploadFile | None = File(None),
    user: User = Depends(roles('victim')),
    db: Session = Depends(get_db),
):
    require_consent(db, user, True)
    if file is None:
        return asr_status()
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, 'Maximum recording size is 10 MB')
    if language not in {'en', 'hi', 'hinglish'}:
        language = 'en'
    return transcribe_audio(raw, language)

@app.get('/alerts')
def alerts(mine: bool = False, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    ids = [c.id for c in scope(db, user)]
    query = select(Alert).where(Alert.case_id.in_(ids)).order_by(Alert.created_at.desc())
    items = list(db.scalars(query))
    if mine:
        items = [a for a in items if a.assigned_to == user.id or a.assigned_to is None]
    return [serialize(a) for a in items]

@app.get('/alerts/{alert_id}')
def get_alert(alert_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(Alert, alert_id)
    if not item:
        raise HTTPException(404, 'Alert not found')
    access_case(db, user, item.case_id)
    return serialize(item)

@app.post('/alerts/{alert_id}/acknowledge')
def acknowledge(alert_id: str, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    return update_alert(alert_id, AlertUpdate(status='Acknowledged'), user, db)

@app.patch('/alerts/{alert_id}')
def update_alert(alert_id: str, body: AlertUpdate, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(Alert, alert_id)
    if not item:
        raise HTTPException(404, 'Alert not found')
    case = access_case(db, user, item.case_id)
    data = dict(item.data or {})
    priority = data.get('priority') or 'Moderate'
    if body.status in {'Resolved', 'Closed'} and priority == 'Critical':
        if not data.get('acknowledged_at'):
            raise HTTPException(422, 'Acknowledge this Critical alert before closing it')
        if not (body.close_note or '').strip():
            raise HTTPException(422, 'Add a close note before closing a Critical alert')
        alert_time = item.created_at.replace(tzinfo=None)
        recent = [i for i in rows(db, Intervention, case.id) if i.created_at.replace(tzinfo=None) >= alert_time]
        if not recent:
            raise HTTPException(422, 'Confirm at least one intervention after this alert before closing a Critical alert')
        data['close_note'] = body.close_note
        data['closed_at'] = now().isoformat()
    if body.status == 'Acknowledged' and not data.get('acknowledged_at'):
        data['acknowledged_at'] = now().isoformat()
        data['acknowledged_by'] = user.id
    if body.assigned_to:
        staff_assignment(db, user, case, body.assigned_to)
        item.assigned_to = body.assigned_to
        data['assigned_at'] = now().isoformat()
    item.data = data
    item.status = body.status
    audit(db, user, 'alert ' + body.status, item.id)
    db.commit()
    return serialize(item)

@app.post('/interventions')
def intervention(body: InterventionInput, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    case = access_case(db, user, body.case_id)
    assigned = staff_assignment(db, user, case, body.assigned_to)
    if assigned.role == 'counsellor':
        case.assigned_to = assigned.id
    item = Intervention(id=uid('INT'), case_id=case.id, author_id=user.id, assigned_to=assigned.id, data={'kind': body.kind, 'notes': body.notes, 'outcome': ''})
    db.add(item)
    victim = db.get(Victim, case.victim_id)
    notify(db, victim.user_id, body.kind + ' assigned', case.id, body=f'{body.kind} was assigned for your case.')
    audit(db, user, 'human authorized intervention', item.id)
    db.commit()
    return serialize(item)

@app.get('/interventions')
def interventions(user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    ids = [c.id for c in scope(db, user)]
    return [serialize(i) for i in db.scalars(select(Intervention).where(Intervention.case_id.in_(ids)))]

@app.patch('/interventions/{item_id}')
def update_intervention(item_id: str, body: InterventionUpdate, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(Intervention, item_id)
    if not item:
        raise HTTPException(404, 'Intervention not found')
    access_case(db, user, item.case_id)
    item.status = body.status
    item.data = {**item.data, 'notes': body.notes, 'outcome': body.outcome}
    audit(db, user, 'update intervention', item.id)
    db.commit()
    return serialize(item)

@app.patch('/support-requests/{item_id}')
def update_support(item_id: str, body: InterventionUpdate, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(SupportRequest, item_id)
    if not item:
        raise HTTPException(404, 'Support request not found')
    case = access_case(db, user, item.case_id)
    item.status = body.status
    item.data = {**item.data, 'internal_notes': body.notes, 'outcome': body.outcome}
    notify(db, db.get(Victim, case.victim_id).user_id, item.data['kind'] + ': ' + body.status, case.id)
    audit(db, user, 'update support request', item.id)
    db.commit()
    return serialize(item)

@app.post('/follow-ups')
def followup(body: FollowUpInput, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    case = access_case(db, user, body.case_id)
    staff_assignment(db, user, case, body.assigned_to)
    if body.due_at.replace(tzinfo=None) <= now().replace(tzinfo=None):
        raise HTTPException(422, 'Choose a future follow-up time')
    item = FollowUp(id=uid('FU'), case_id=case.id, assigned_to=body.assigned_to, due_at=body.due_at, data={'notes': body.notes})
    db.add(item)
    notify(db, db.get(Victim, case.victim_id).user_id, 'Follow-up scheduled', case.id)
    audit(db, user, 'schedule follow-up', item.id)
    db.commit()
    return serialize(item)

@app.get('/follow-ups')
def followups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = [c.id for c in scope(db, user)]
    values = list(db.scalars(select(FollowUp).where(FollowUp.case_id.in_(ids)).order_by(FollowUp.due_at)))
    return [{'id': f.id, 'due_at': f.due_at, 'status': f.status, 'case_id': f.case_id} if user.role == 'victim' else serialize(f) for f in values]

@app.patch('/follow-ups/{item_id}')
def update_followup(item_id: str, body: FollowUpUpdate, user: User = Depends(roles('officer', 'counsellor', 'admin')), db: Session = Depends(get_db)):
    item = db.get(FollowUp, item_id)
    if not item:
        raise HTTPException(404, 'Follow-up not found')
    access_case(db, user, item.case_id)
    item.status = body.status
    item.data = {**item.data, 'outcome': body.outcome}
    audit(db, user, 'record follow-up', item.id)
    db.commit()
    return serialize(item)

@app.post('/support-requests')
def support(body: SupportInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    case = access_case(db, user, body.case_id)
    item = SupportRequest(id=uid('SUP'), case_id=case.id, data={'kind': body.kind, 'message': body.message})
    db.add(item)
    if body.kind == 'Safety concern':
        db.add(Alert(id=uid('ALT'), case_id=case.id, assigned_to=case.assigned_to, data={'priority': 'High', 'trigger': [{'factor': 'Direct safety support request', 'source': 'Self-reported'}], 'recommendations': ['Safety/protection review'], 'explanation': []}))
    recipients = list(db.scalars(select(User).where(User.role == 'officer', User.district_id == case.district_id)))
    if case.assigned_to:
        assigned = db.get(User, case.assigned_to)
        if assigned:
            recipients.append(assigned)
    seen = set()
    for staff_user in recipients:
        if not staff_user or staff_user.id in seen:
            continue
        seen.add(staff_user.id)
        notify(db, staff_user.id, body.kind + ' requested', case.id)
    audit(db, user, 'request support', item.id)
    db.commit()
    return serialize(item)

@app.get('/notifications')
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(n) for n in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()))]

@app.patch('/notifications/{item_id}/read')
def read_notification(item_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Notification, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, 'Notification not found')
    item.read = True
    db.commit()
    return {'ok': True}

@app.post('/chat')
def chat(body: ChatInput, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    access_case(db, user, body.case_id)
    require_consent(db, user)
    signals = analyze_text(body.text, body.language)['signals']
    return guided_support(body.text, body.language, signals)

from .analytics import router as analytics_router
app.include_router(analytics_router)

FRONTEND_OUT = Path(__file__).resolve().parents[2] / 'frontend' / 'out'
if FRONTEND_OUT.exists():
    app.mount('/_next', StaticFiles(directory=FRONTEND_OUT / '_next'), name='next-static')

    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str, request: Request):
        if getattr(request.state, 'api_prefixed', False):
            raise HTTPException(404, 'Not found')
        target = FRONTEND_OUT / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_OUT / 'index.html')
