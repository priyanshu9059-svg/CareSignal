import uuid
from fastapi import HTTPException
from sqlalchemy import select
from .database import *
from .ai import calculate

def uid(prefix):
    return prefix + '-' + uuid.uuid4().hex[:12]

def audit(db, user, action, resource):
    db.add(AuditLog(id=uid('AUD'), user_id=user.id, action=action, resource=resource))

def consent_for(db, user):
    return db.scalars(select(Consent).where(Consent.user_id==user.id).order_by(Consent.created_at.desc())).first()

def require_consent(db, user, voice=False):
    consent = consent_for(db,user)
    if not consent or not consent.wellbeing or (voice and not consent.voice):
        raise HTTPException(403, 'Please provide consent before this optional collection')
    return consent

def scope(db, user):
    query = select(Case)
    if user.role=='victim':
        query = query.join(Victim).where(Victim.user_id==user.id)
    elif user.role=='counsellor':
        query = query.where(Case.assigned_to==user.id)
    elif user.role=='officer':
        query = query.where(Case.district_id==user.district_id)
    elif user.role in ['state','national']:
        raise HTTPException(403,'This role has aggregate access only')
    return list(db.scalars(query))

def access_case(db, user, case_id):
    case = next((c for c in scope(db,user) if c.id==case_id),None)
    if not case:
        raise HTTPException(404,'Case not found in your authorized scope')
    return case

def public_user(user):
    return {k:getattr(user,k) for k in ['id','name','email','role','district_id','state_id']}

def rows(db, cls, case_id):
    return list(db.scalars(select(cls).where(cls.case_id==case_id).order_by(cls.created_at)))

def serialize(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}

def history_for(db, case_id):
    return [{'id':a.id,'at':a.created_at.isoformat(), 'score':a.data['scores']['distress'], **a.data['scores'],
             'priority':a.data['priority']} for a in rows(db,Assessment,case_id)]

def notify(db, user_id, title, case_id):
    from .integrations import MockSMSAdapter, MockNotificationAdapter
    db.add(Notification(id=uid('N'),user_id=user_id,data={'title':title,'case_id':case_id,
        'channels':{'in_app':'delivered','email':'simulated','sms':'simulated'},
        'receipts':[MockSMSAdapter().submit(case_id,'SMS'),MockNotificationAdapter().submit(case_id,'Email')]}))

def case_summary(db, case):
    assessments = rows(db,Assessment,case.id)
    latest = assessments[-1].data if assessments else None
    district = db.get(District,case.district_id)
    return {'id':case.id,'stage':case.stage,'case_type':case.case_type,'district':district.name,
            'district_id':district.id,'assigned_to':case.assigned_to,'conditions':case.conditions,
            'scores':latest['scores'] if latest else None,'priority':latest['priority'] if latest else 'Unassessed',
            'trend':latest.get('trend',{}) if latest else {}, 'last_checkin':assessments[-1].created_at if assessments else None}

def submit_assessment(db, user, payload, at=None):
    case = access_case(db,user,payload.case_id)
    require_consent(db,user)
    voice = None
    if payload.voice_session_id:
        require_consent(db,user,True)
        session = db.get(VoiceSession,payload.voice_session_id)
        if not session or session.case_id!=case.id:
            raise HTTPException(422,'Voice session does not belong to this case')
        voice=session.data
    timestamp=at or now()
    history=history_for(db,case.id)
    conditions=dict(case.conditions)
    if history:
        last=datetime.fromisoformat(history[-1]['at']).replace(tzinfo=None)
        conditions['missed_checkins']=max(0,(timestamp.replace(tzinfo=None)-last).days//7-1)
    result=calculate(payload.responses.model_dump(),payload.text,payload.language,history,conditions,timestamp,voice)
    if history:
        previous_response=db.scalars(select(AssessmentResponse).where(AssessmentResponse.assessment_id==history[-1]['id'])).first()
        if previous_response:
            old=previous_response.data.get('responses',{})
            for key in ['fear','sleep','daily']:
                current=getattr(payload.responses,key)
                if current is not None and old.get(key) is not None and current!=old[key]:
                    result['what_changed'].append({'factor':f'{key.title()} difficulty {old[key]}/4 → {current}/4','source':'Self-reported / Historical trend'})
    assessment=Assessment(id=uid('ASM'),case_id=case.id,created_at=timestamp,data=result)
    db.add(assessment)
    db.flush()
    result={**result,'assessment_id':assessment.id}
    assessment.data=result
    if payload.responses.need:
        db.add(SupportRequest(id=uid('SUP'),case_id=case.id,data={'kind':payload.responses.need,'message':'Requested during check-in'}))
    for cls,data in [(AssessmentResponse,{'responses':payload.responses.model_dump(),'text':payload.text,'language':payload.language}),
                     (NLPResult,{k:result[k] for k in ['sentiment','emotions','signals','method','fallback']}),
                     (BehaviourFeature,{'trend':result['trend'],'baseline':result['baseline']}),
                     (RiskScore,result['scores']),(RiskExplanation,{'items':result['explanation']})]:
        db.add(cls(id=uid('D'),assessment_id=assessment.id,data=data))
    if result['priority'] in ['Moderate','High','Critical']:
        alert=Alert(id=uid('ALT'),case_id=case.id,assigned_to=case.assigned_to,data={
            'assessment_id':assessment.id,'priority':result['priority'],'scores':result['scores'],
            'explanation':result['explanation'],'trigger':result['what_changed'],
            'recommendations':result['recommendations']})
        db.add(alert)
        recipients=list(db.scalars(select(User).where(User.role=='officer',User.district_id==case.district_id)))
        if case.assigned_to: recipients.append(db.get(User,case.assigned_to))
        for recipient in recipients:
            notify(db,recipient.id,f'{case.id}: {result["priority"]} — human review requested',case.id)
    audit(db,user,'create assessment',assessment.id)
    db.commit()
    return result

def staff_assignment(db,user,case,assigned_to):
    staff=db.get(User,assigned_to)
    if not staff or staff.role not in ['counsellor','officer'] or staff.district_id!=case.district_id:
        raise HTTPException(422,'Select a counsellor or officer from the case district')
    if user.role=='counsellor' and staff.id!=user.id:
        raise HTTPException(403,'Counsellors may assign work only to themselves')
    return staff

def case_detail(db,user,case):
    summary=case_summary(db,case)
    interventions=rows(db,Intervention,case.id)
    followups=rows(db,FollowUp,case.id)
    supports=rows(db,SupportRequest,case.id)
    if user.role=='victim':
        return {'id':case.id,'stage':case.stage,'assigned':bool(case.assigned_to),
                'interventions':[{'id':i.id,'kind':i.data['kind'],'status':i.status} for i in interventions],
                'follow_ups':[{'id':f.id,'due_at':f.due_at,'status':f.status} for f in followups],
                'support_requests':[{'id':s.id,'kind':s.data['kind'],'status':s.status} for s in supports],
                'checkin_count':len(rows(db,Assessment,case.id))}
    assessments=rows(db,Assessment,case.id)
    history=history_for(db,case.id)
    effects=[]
    for i in interventions:
        start=i.created_at.replace(tzinfo=None)
        before=[h for h in history if datetime.fromisoformat(h['at']).replace(tzinfo=None)<=start]
        after=[h for h in history if datetime.fromisoformat(h['at']).replace(tzinfo=None)>start]
        windows={}
        for days in [7,14]:
            matches=[h for h in after if (datetime.fromisoformat(h['at']).replace(tzinfo=None)-start).days>=days]
            windows[f'day_{days}']=matches[0]['score'] if matches else None
        effects.append({'id':i.id,'kind':i.data['kind'],'before':before[-1]['score'] if before else None,**windows,
                       'after':after,'note':'Improvement observed after intervention; causality is not established' if before and after and after[-1]['score']<before[-1]['score'] else 'Further review recommended' if after else 'Awaiting follow-up assessment'})
    events=[]
    for event in rows(db,CaseEvent,case.id):
        before=[h for h in history if datetime.fromisoformat(h['at']).replace(tzinfo=None)<=event.created_at.replace(tzinfo=None)]
        after=[h for h in history if datetime.fromisoformat(h['at']).replace(tzinfo=None)>event.created_at.replace(tzinfo=None)]
        events.append({**serialize(event),'observed_change':after[0]['score']-before[-1]['score'] if before and after else None})
    return {**summary,'history':history,'latest':assessments[-1].data if assessments else None,
            'events':events,
            'interventions':[serialize(i) for i in interventions], 'follow_ups':[serialize(f) for f in followups],
            'support_requests':[serialize(s) for s in supports], 'effects':effects}
