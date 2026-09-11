"""Idempotent, fictional demonstration data only."""
import os
import random
from datetime import timedelta
from .config import DEMO_ENABLED
from .database import (
    Alert, Assessment, AssessmentResponse, Base, Case, CaseEvent, District, FollowUp,
    Intervention, RiskExplanation, RiskScore, Role, SessionLocal, State, User, Victim,
    engine, now,
)
from .auth import hash_password
from .ai import calculate, category

def seed(db):
    if not DEMO_ENABLED:
        return
    if db.get(User, 'U-victim'):
        return
    rng = random.Random(26094)
    for role in ['victim', 'counsellor', 'officer', 'state', 'national', 'admin']:
        db.add(Role(id=role, name=role))
    for id, name in [('S1', 'Madhya Pradesh'), ('S2', 'Rajasthan'), ('S3', 'Maharashtra')]:
        db.add(State(id=id, name=name))
    db.flush()
    districts = [('D1', 'Bhopal', 'S1', 23.25, 77.41), ('D2', 'Indore', 'S1', 22.72, 75.85), ('D3', 'Jaipur', 'S2', 26.91, 75.79), ('D4', 'Ajmer', 'S2', 26.45, 74.64), ('D5', 'Pune', 'S3', 18.52, 73.86), ('D6', 'Nagpur', 'S3', 21.15, 79.09)]
    for id, name, state, lat, lon in districts:
        db.add(District(id=id, name=name, state_id=state, latitude=lat, longitude=lon))
    db.flush()
    password = hash_password(os.getenv('DEMO_PASSWORD', 'Demo@123'))
    for role, name in [('counsellor', 'Ananya Mehta'), ('officer', 'District Support Officer'), ('state', 'State Programme Lead'), ('national', 'National Programme Lead'), ('admin', 'System Administrator')]:
        db.add(User(id='U-' + role, email=role + '@demo.com', name=name, role=role, password_hash=password, district_id='D1', state_id='S1'))
    for d, _, state, _, _ in districts[1:]:
        for role in ['counsellor', 'officer']:
            db.add(User(id=f'U-{role}-{d}', email=f'{role}.{d.lower()}@demo.com', name=f'Demo {role} {d}', role=role, password_hash=password, district_id=d, state_id=state))
    for i in range(50):
        district = districts[i % 6]
        db.add(User(id='U-victim' if i == 0 else f'U-victim-{i}', email='victim@demo.com' if i == 0 else f'victim{i}@demo.com', name=f'Participant {i+1:03}', role='victim', password_hash=password, district_id=district[0], state_id=district[2]))
    db.flush()
    for i in range(50):
        db.add(Victim(id=f'V-{i}', user_id='U-victim' if i == 0 else f'U-victim-{i}', alias=f'Participant {i+1:03}'))
    db.flush()
    for i in range(50):
        d = districts[i % 6][0]
        db.add(Case(id='AT-20481' if i == 0 else f'AT-{21000+i}', victim_id=f'V-{i}', district_id=d, assigned_to='U-counsellor' if d == 'D1' else f'U-counsellor-{d}', stage=['Investigation', 'Court proceedings', 'Rehabilitation'][i % 3], conditions={'court_event': i % 4 == 0, 'compensation_delay': i % 5 == 0, 'missed_checkins': i % 3}))
    db.flush()
    today = now()
    for i in range(50):
        case = db.get(Case, 'AT-20481' if i == 0 else f'AT-{21000+i}')
        history = []
        base = rng.randint(12, 70)
        for week in range(12):
            if i == 0:
                score = [27, 29, 30, 31, 32, 39, 47, 58, 74, 78, 63, 49][week]
            else:
                pattern = i % 9
                change = [0, week * 3, 25 if week > 7 else 0, 35 if week > 8 else 0, week * 2, week * 2, week, -week * 2 if week > 5 else week * 3, week * 4][pattern]
                score = max(5, min(97, base + change + rng.randint(-4, 4)))
            stamp = today - timedelta(weeks=11 - week, days=1)
            responses = {'feeling': min(4, round(score / 25)), 'fear': min(4, round(score / 25)), 'sleep': min(4, round(score / 25)), 'daily': min(4, round(score / 25)), 'threat': score > 70, 'safe': score < 85}
            result = calculate(responses, 'Synthetic historical check-in', 'en', history, case.conditions, stamp)
            result['scores']['distress'] = score
            result['priority'] = category(max(result['scores'].values()))
            result['explanation'] = [{'factor': 'Synthetic trajectory value', 'impact': score, 'source': 'Synthetic seed'}]
            result['synthetic_seed'] = True
            result['trend']['direction'] = 'Improving' if history and score < history[-1]['score'] else 'Worsening' if history and score > history[-1]['score'] else 'Stable'
            id = f'ASM-{i}-{week}'
            db.add(Assessment(id=id, case_id=case.id, created_at=stamp, data={**result, 'assessment_id': id}))
            db.flush()
            db.add(AssessmentResponse(id=f'AR-{i}-{week}', assessment_id=id, created_at=stamp, data={'responses': responses, 'text': 'Synthetic historical check-in'}))
            db.add(RiskScore(id=f'RS-{i}-{week}', assessment_id=id, created_at=stamp, data=result['scores']))
            db.add(RiskExplanation(id=f'RE-{i}-{week}', assessment_id=id, created_at=stamp, data={'items': result['explanation']}))
            history.append({'at': stamp.isoformat(), 'score': score})
        for j, title in enumerate(['Complaint registered', 'Court hearing scheduled', 'Counselling completed']):
            db.add(CaseEvent(id=f'EV-{i}-{j}', case_id=case.id, created_at=today - timedelta(days=70 - j * 30), data={'title': title, 'notes': 'Fictional demonstration event', 'kind': 'general'}))
        for j in range(2):
            db.add(Intervention(id=f'INT-{i}-{j}', case_id=case.id, author_id='U-officer' if case.district_id == 'D1' else 'U-officer-' + case.district_id, assigned_to=case.assigned_to, status='Completed' if j == 0 else 'In Progress', created_at=today - timedelta(days=13 if j == 0 else 4), data={'kind': 'Counsellor follow-up' if j == 0 else 'Legal support review', 'notes': 'Synthetic internal note', 'outcome': 'Contact recorded' if j == 0 else ''}))
        db.add(FollowUp(id=f'FU-{i}', case_id=case.id, assigned_to=case.assigned_to, due_at=today + timedelta(days=1 + i % 5), data={'notes': 'Routine follow-up'}))
        if result['priority'] in ['Moderate', 'High', 'Critical']:
            db.add(Alert(id=f'ALT-{i}', case_id=case.id, assigned_to=case.assigned_to, data={'priority': result['priority'], 'scores': result['scores'], 'explanation': result['explanation'], 'trigger': result['what_changed'], 'recommendations': result['recommendations']}))
    db.commit()

if __name__ == '__main__':
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    print('Synthetic demo data ready: 50 cases, 600 assessments, 150 events, 100 interventions.')
