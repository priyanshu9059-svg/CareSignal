import json
from collections import Counter, defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import Alert, Assessment, AuditLog, Case, District, FollowUp, Intervention, State, User, get_db, now
from .auth import current_user, roles
from .services import audit, alert_response_minutes, case_summary, serialize, scope, submit_assessment
from .config import MODEL_PATH, AI_MODE, DEMO_ENABLED
from .schemas import AssessmentInput, Responses

router = APIRouter()

@router.get('/dashboard/{level}')
def dashboard(level: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {'district': ['officer', 'counsellor', 'admin'], 'state': ['state', 'admin'], 'national': ['national', 'admin']}
    if level not in allowed or user.role not in allowed[level]:
        raise HTTPException(403, 'Dashboard outside your role')
    query = select(Case).join(District)
    if level == 'district' and user.role != 'admin':
        query = query.where(Case.district_id == user.district_id)
    if level == 'district' and user.role == 'counsellor':
        query = query.where(Case.assigned_to == user.id)
    if level == 'state' and user.role != 'admin':
        query = query.where(District.state_id == user.state_id)
    cases = list(db.scalars(query))
    ids = [c.id for c in cases]
    summaries = [case_summary(db, c) for c in cases]
    distribution = Counter(c['priority'] for c in summaries)
    interventions = list(db.scalars(select(Intervention).where(Intervention.case_id.in_(ids))))
    followups = list(db.scalars(select(FollowUp).where(FollowUp.case_id.in_(ids))))
    alerts = list(db.scalars(select(Alert).where(Alert.case_id.in_(ids))))
    grouped = defaultdict(list)
    for c in summaries:
        grouped[c['district_id']].append(c)
    districts = []
    for id, items in grouped.items():
        district = db.get(District, id)
        districts.append({'name': district.name, 'state': db.get(State, district.state_id).name, 'count': len(items), 'high': sum(c['priority'] in ['High', 'Critical'] for c in items),
                          'lat': district.latitude, 'lng': district.longitude, 'mean_distress': round(sum((c['scores'] or {}).get('distress', 0) for c in items) / len(items), 1)})
    days = defaultdict(list)
    for a in db.scalars(select(Assessment).where(Assessment.case_id.in_(ids))):
        days[a.created_at.date().isoformat()].append(a.data['scores']['distress'])
    timing = alert_response_minutes(alerts)
    audit(db, user, 'view aggregate dashboard', level)
    db.commit()
    return {'level': level, 'synthetic': True, 'kpis': {'Active cases': len(cases), 'High risk': distribution['High'], 'Critical': distribution['Critical'],
        'Escalated today': sum(a.created_at.date() == now().date() for a in alerts), 'Pending follow-up': sum(f.status == 'Scheduled' for f in followups),
        'Interventions in progress': sum(i.status == 'In Progress' for i in interventions)},
        'risk_distribution': [{'name': k, 'value': v} for k, v in distribution.items()], 'districts': districts,
        'trend': [{'date': day, 'distress': round(sum(values) / len(values), 1)} for day, values in sorted(days.items())],
        'intervention_status': [{'name': k, 'value': v} for k, v in Counter(i.status for i in interventions).items()],
        'trajectories': [{'name': k, 'value': v} for k, v in Counter(c['trend'].get('direction', 'Unknown') for c in summaries).items()],
        'case_stages': [{'name': k, 'value': v} for k, v in Counter(c['stage'] for c in summaries).items()],
        'response_time': timing['avg_minutes'], 'response_time_note': timing['note']}

@router.get('/research')
def research(user: User = Depends(roles('admin')), db: Session = Depends(get_db)):
    path = MODEL_PATH / 'metrics.json'
    metrics = json.loads(path.read_text()) if path.exists() else {'status': 'No trained model available; rule fallback active'}
    assessments = list(db.scalars(select(Assessment)))
    predictions = Counter(a.data.get('prediction', {}).get('method', 'unknown') for a in assessments)
    return {'mode': AI_MODE, 'metrics': metrics, 'prediction_distribution': dict(predictions),
            'fallback_usage': sum(a.data.get('prediction', {}).get('fallback', False) for a in assessments),
            'bias_evaluation': {'language': 'Not evaluated on representative human language data', 'gender': 'Not collected in this prototype',
                               'speaker_group': 'No validated speech emotion model', 'source': 'Synthetic trajectories only'},
            'limitation': 'Synthetic-data metrics are prototype metrics, not clinical validation.',
            'metrics_framing': 'Percentages below are synthetic holdout scores for this prototype only — not field or clinical performance.'}

@router.get('/audit-logs')
def logs(user: User = Depends(roles('admin')), db: Session = Depends(get_db)):
    return [serialize(a) for a in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200))]

@router.post('/demo/scenario/{name}')
def scenario(name: str, user: User = Depends(roles('victim')), db: Session = Depends(get_db)):
    if not DEMO_ENABLED:
        raise HTTPException(404, 'Demo mode disabled')
    choices = {'stable': (0, False, True, 'I am feeling better and feel safe.'), 'gradual': (2, False, True, 'Court is approaching and I feel afraid.'),
             'threat': (4, True, False, 'Mujhe bahut darr lag raha hai. Unhone mere bhai ko dhamki di. Court jaane se dar lag raha hai. Neend nahi aati.'),
             'critical': (4, True, False, 'They threatened to hurt my family. I am scared and cannot sleep.'),
             'improvement': (1, False, True, 'I am feeling better with support.')}
    if name not in choices:
        raise HTTPException(404, 'Unknown scenario')
    case = scope(db, user)[0]
    score, threat, safe, text = choices[name]
    payload = AssessmentInput(case_id=case.id, text=text, language='hinglish' if name == 'threat' else 'en', responses=Responses(feeling=score, fear=score, sleep=score, daily=score, avoidance=score, legal=score, threat=threat, safe=safe, support=True))
    result = submit_assessment(db, user, payload)
    return {'assessment_id': result['assessment_id'], 'message': 'Synthetic scenario saved as a new check-in', 'recommendations': result['recommendations']}
