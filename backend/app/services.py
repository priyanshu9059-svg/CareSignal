import uuid
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from .database import (
    Alert, Assessment, AssessmentResponse, AuditLog, BehaviourFeature, Case, CaseEvent,
    Consent, District, FollowUp, Intervention, NLPResult, Notification, RiskExplanation,
    RiskScore, SupportRequest, User, Victim, VoiceFeature, VoiceSession, now,
)
from .ai import calculate
from .config import STORAGE_PATH

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
    history=[]
    for a in rows(db,Assessment,case_id):
        scores=(a.data or {}).get('scores') or {}
        distress=scores.get('distress')
        if distress is None:
            continue
        history.append({'id':a.id,'at':a.created_at.isoformat(),'score':distress,**scores,
                        'priority':(a.data or {}).get('priority','Unassessed'),
                        'has_voice':bool((a.data or {}).get('voice')),
                        'sentiment':((a.data or {}).get('sentiment') or {}).get('label')})
    return history

def checkin_rows(db, case_id):
    """Staff-facing chronological check-ins including linked voice summary."""
    items=[]
    for a in rows(db,Assessment,case_id):
        data=a.data or {}
        scores=data.get('scores') or {}
        voice=data.get('voice')
        items.append({
            'id':a.id,'at':a.created_at.isoformat(),'priority':data.get('priority','Unassessed'),
            'scores':scores,'sentiment':data.get('sentiment'),'emotions':data.get('emotions'),
            'what_changed':data.get('what_changed') or [],'recommendations':data.get('recommendations') or [],
            'has_voice':bool(voice),
            'voice_session_id':data.get('voice_session_id'),
            'voice_playable':bool(data.get('voice_playable') or (isinstance(voice,dict) and (voice.get('stored') or voice.get('audio_path')))),
            'voice_summary':({k:voice.get(k) for k in ['duration','energy','pause_ratio','pitch_mean','pitch_variability','baseline_deviation','emotion','stress_score','note','method'] if voice.get(k) is not None}
                             if isinstance(voice,dict) else None),
            'prediction':data.get('prediction'),'assessment_id':data.get('assessment_id',a.id)})
    return list(reversed(items))

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

def _voice_path(session: VoiceSession) -> Path:
    data = session.data or {}
    rel = data.get('audio_path')
    return (STORAGE_PATH / rel) if rel else (STORAGE_PATH / 'voices' / session.case_id / f'{session.id}.wav')

def erase_optional_data(db, user, *, erase_voice=False, erase_checkins=False):
    """Delete optional wellbeing artifacts for the participant's own cases."""
    cases = scope(db, user)
    summary = {'voice_files_removed': 0, 'voice_sessions_redacted': 0, 'checkins_redacted': 0}
    for case in cases:
        if erase_voice:
            for session in rows(db, VoiceSession, case.id):
                path = _voice_path(session)
                try:
                    if path.is_file():
                        path.unlink()
                        summary['voice_files_removed'] += 1
                except OSError:
                    pass
                features = list(db.scalars(select(VoiceFeature).where(VoiceFeature.voice_session_id == session.id)))
                for feature in features:
                    db.delete(feature)
                data = dict(session.data or {})
                data.pop('audio_path', None)
                data['stored'] = False
                data['erased_at'] = now().isoformat()
                data['note'] = 'Recording removed after privacy erasure request'
                session.data = data
                summary['voice_sessions_redacted'] += 1
            for assessment in rows(db, Assessment, case.id):
                data = dict(assessment.data or {})
                if data.get('voice') or data.get('voice_session_id'):
                    data['voice'] = None
                    data['voice_playable'] = False
                    data['voice_session_id'] = None
                    data['voice_erased'] = True
                    assessment.data = data
        if erase_checkins:
            for assessment in rows(db, Assessment, case.id):
                response = db.scalars(select(AssessmentResponse).where(AssessmentResponse.assessment_id == assessment.id)).first()
                if response:
                    response.data = {'responses': (response.data or {}).get('responses') or {}, 'text': '', 'language': (response.data or {}).get('language', 'en'), 'erased_at': now().isoformat()}
                nlp = db.scalars(select(NLPResult).where(NLPResult.assessment_id == assessment.id)).first()
                if nlp:
                    nlp.data = {'sentiment': None, 'emotions': {}, 'signals': {}, 'method': 'erased', 'fallback': True, 'erased_at': now().isoformat()}
                data = dict(assessment.data or {})
                data['text_erased'] = True
                data['sentiment'] = None
                data['emotions'] = {}
                data['evidence'] = []
                data['signals'] = {}
                assessment.data = data
                summary['checkins_redacted'] += 1
    return summary

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
        result_voice_id=payload.voice_session_id
    else:
        result_voice_id=None
    timestamp=at or now()
    history=history_for(db,case.id)
    conditions=dict(case.conditions)
    if history:
        last=datetime.fromisoformat(history[-1]['at']).replace(tzinfo=None)
        conditions['missed_checkins']=max(0,(timestamp.replace(tzinfo=None)-last).days//7-1)
    result=calculate(payload.responses.model_dump(),payload.text,payload.language,history,conditions,timestamp,voice)
    if result_voice_id:
        result['voice_session_id']=result_voice_id
        result['voice_playable']=bool((voice or {}).get('stored') or (voice or {}).get('audio_path'))
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
    recipients=[]
    if case.assigned_to:
        assigned=db.get(User,case.assigned_to)
        if assigned: recipients.append(assigned)
    if result['priority'] in ['Moderate','High','Critical']:
        alert=Alert(id=uid('ALT'),case_id=case.id,assigned_to=case.assigned_to,data={
            'assessment_id':assessment.id,'priority':result['priority'],'scores':result['scores'],
            'explanation':result['explanation'],'trigger':result['what_changed'],
            'recommendations':result['recommendations'],'has_voice':bool(voice)})
        db.add(alert)
        recipients.extend(list(db.scalars(select(User).where(User.role=='officer',User.district_id==case.district_id))))
        title=f'{case.id}: {result["priority"]} — human review requested'
    else:
        title=f'{case.id}: new check-in ({result["priority"]}) — open case to review'
    seen=set()
    for recipient in recipients:
        if not recipient or recipient.id in seen: continue
        seen.add(recipient.id)
        notify(db,recipient.id,title,case.id)
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
    checkins=checkin_rows(db,case.id)
    voice_sessions=[]
    for v in reversed(rows(db,VoiceSession,case.id)):
        data=v.data or {}
        path=_voice_path(v)
        playable=path.exists() and path.is_file()
        voice_sessions.append({'id':v.id,'at':v.created_at.isoformat(),'playable':playable,
                     'audio_url':f'/ai/voice/{v.id}/audio' if playable else None,
                     **{k:data.get(k) for k in ['duration','energy','pause_ratio','pitch_mean','pitch_variability','speech_rate','baseline_deviation','emotion','stress_score','note','method']}})
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
    return {**summary,'history':history,'checkins':checkins,'voice_sessions':voice_sessions,
            'latest':assessments[-1].data if assessments else None,
            'events':events,
            'interventions':[serialize(i) for i in interventions], 'follow_ups':[serialize(f) for f in followups],
            'support_requests':[serialize(s) for s in supports], 'effects':effects}
