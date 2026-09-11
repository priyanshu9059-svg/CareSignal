import os
import tempfile
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp(prefix='caresignal-test-'))/'test.db')
os.environ['JWT_SECRET']='test-only-key-not-for-deployment-123456789'
os.environ['DEMO_ENABLED']='true'
import io
import wave
from datetime import timedelta
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.main import app, requests
from app.database import SessionLocal, Assessment, now
from app.ai import analyze_text, audio_features, calculate, trends

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as client: yield client

def login(client,role):
    client.cookies.clear()
    response=client.post('/auth/login',json={'email':role+'@demo.com','password':'Demo@123'})
    assert response.status_code==200,response.text

def test_auth_and_scope(client):
    assert client.get('/cases').status_code==401
    assert client.post('/auth/login',json={'email':'victim@demo.com','password':'wrong'}).status_code==401
    login(client,'victim')
    assert len(client.get('/cases').json())==1
    assert client.get('/cases/AT-21001').status_code==404
    assert client.get('/alerts').status_code==403
    assert client.get('/cases/AT-20481/explanation').status_code==403
    assert client.post('/auth/register',json={'email':'x@y.com','password':'abcdefghij','name':'X','role':'admin'}).status_code==403
    assert client.post('/consents',json={'wellbeing':True},headers={'Origin':'https://evil.example'}).status_code==403

def test_end_to_end(client):
    login(client,'victim')
    payload={'case_id':'AT-20481','language':'hinglish','text':'Mujhe bahut darr lag raha hai. Mere bhai ko dhamki di. Court jaane se dar lag raha hai. Neend nahi aati.',
             'responses':{'feeling':4,'fear':4,'sleep':4,'daily':4,'avoidance':4,'legal':4,'threat':True,'safe':False}}
    assert client.post('/assessments',json=payload).status_code==403
    assert client.post('/consents',json={'wellbeing':True,'voice':True,'language':'hinglish'}).status_code==200
    result=client.post('/assessments',json=payload)
    assert result.status_code==200,result.text
    id=result.json()['assessment_id']
    assert 'scores' not in result.json()
    login(client,'officer')
    assessment=client.get('/assessments/'+id).json()['data']
    assert assessment['scores']['distress']>=70
    assert assessment['scores']['safety_risk']>=85
    assert assessment['priority']=='Critical'
    assert abs(sum(e['impact'] for e in assessment['explanation'])-assessment['scores']['distress'])<1
    alerts=client.get('/alerts').json()
    alert=next(a for a in alerts if a['data'].get('assessment_id')==id)
    assert client.post('/alerts/'+alert['id']+'/acknowledge').json()['status']=='Acknowledged'
    new=client.post('/interventions',json={'case_id':'AT-20481','kind':'Safety/protection review','assigned_to':'U-counsellor','notes':'INTERNAL PRIVATE NOTE'})
    assert new.status_code==200,new.text
    assert client.patch('/interventions/'+new.json()['id'],json={'status':'Completed','notes':'INTERNAL PRIVATE NOTE','outcome':'Contact completed'}).status_code==200
    follow=client.post('/follow-ups',json={'case_id':'AT-20481','assigned_to':'U-counsellor','due_at':(now()+timedelta(days=2)).isoformat(),'notes':'PRIVATE FOLLOW-UP'})
    assert follow.status_code==200,follow.text
    assert client.post('/case-events',json={'case_id':'AT-20481','title':'Protection concern reviewed','kind':'general'}).status_code==200
    assert client.get('/dashboard/district').json()['kpis']['Active cases']>0
    login(client,'victim')
    journey=client.get('/cases/AT-20481')
    assert 'INTERNAL PRIVATE NOTE' not in journey.text and 'PRIVATE FOLLOW-UP' not in journey.text
    assert any(i['id']==new.json()['id'] for i in journey.json()['interventions'])
    payload.update(text='I am feeling better and feel safe.',responses={'feeling':0,'fear':0,'sleep':0,'daily':0,'threat':False,'safe':True})
    improved=client.post('/assessments',json=payload)
    assert improved.status_code==200
    login(client,'counsellor')
    detail=client.get('/cases/AT-20481').json()
    assert detail['latest']['scores']['distress']<assessment['scores']['distress']
    assert detail['latest']['trend']['direction']=='Improving'
    assert any(c['id']==improved.json()['assessment_id'] for c in detail['checkins'])
    notes=client.get('/notifications').json()
    assert any('AT-20481' in (n['data'].get('title') or '') for n in notes)
    for role in ['state','national']:
        login(client,role)
        result=client.get('/dashboard/'+role)
        assert result.status_code==200,result.text
        assert 'AT-20481' not in result.text and 'Participant' not in result.text
        assert client.get('/cases').status_code==403
    login(client,'admin')
    assert client.get('/research').status_code==200
    assert len(client.get('/audit-logs').json())>0

def make_audio():
    signal=(np.sin(np.arange(16000)*2*np.pi*180/16000)*12000).astype('<i2')
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(signal.tobytes())
    return buffer.getvalue()

def test_voice_and_consent(client):
    login(client,'victim')
    for i in range(4):
        result=client.post('/ai/analyze-voice',data={'case_id':'AT-20481','transcript':'I feel safe today'},files={'file':('voice.wav',make_audio(),'audio/wav')})
        assert result.status_code==200,result.text
    assert result.json()['baseline'] is not None
    assert len(result.json()['mfccs'])==13
    assert abs(result.json()['pitch_mean']-180)<10
    assert result.json().get('emotion') is not None or result.json().get('stress_score') is not None
    assert result.json().get('stored') is True
    voice_id=result.json()['voice_session_id']
    login(client,'counsellor')
    audio=client.get('/ai/voice/'+voice_id+'/audio')
    assert audio.status_code==200,audio.text
    assert audio.headers.get('content-type','').startswith('audio/')
    login(client,'victim')
    assert client.post('/ai/analyze-voice',data={'case_id':'AT-20481'},files={'file':('bad.wav',b'garbage','audio/wav')}).status_code==422
    assert client.post('/ai/transcribe').json()['available'] is False
    client.post('/consents',json={'wellbeing':False,'voice':False})
    assert client.post('/ai/analyze-text',json={'text':'hello'}).status_code==403
    assert client.post('/ai/analyze-voice',data={'case_id':'AT-20481'},files={'file':('voice.wav',make_audio(),'audio/wav')}).status_code==403
    assert client.post('/support-requests',json={'case_id':'AT-20481','kind':'Safety concern','message':'Please contact me'}).status_code==200

def test_validation_case_creation(client):
    login(client,'admin')
    new=client.post('/auth/register',json={'email':'new@demo.com','password':'long-password-123','name':'New synthetic participant','role':'victim','district_id':'D1','state_id':'S1'})
    assert new.status_code==200,new.text
    created=client.post('/cases',json={'victim_id':new.json()['victim_id'],'district_id':'D1'})
    assert created.status_code==200,created.text
    login(client,'officer')
    assert client.get('/cases/AT-21001').status_code==404
    assert client.post('/interventions',json={'case_id':'AT-20481','kind':'Counselling','assigned_to':'U-counsellor-D2'}).status_code==422
    login(client,'victim')
    assert client.post('/assessments',json={'case_id':'AT-20481','text':'','responses':{'fear':8}}).status_code==422
    assert client.post('/assessments',json={'case_id':'AT-20481','text':'','responses':{}}).status_code==422

@pytest.mark.parametrize('text,signal',[('I am scared','fear'),('Mujhe dhamki di','threat'),('मुझे डर लग रहा है','fear'),('नींद नहीं आती','sleep_issue')])
def test_multilingual(text,signal):
    assert analyze_text(text)['signals'][signal]

def test_negation_and_fallback():
    assert not analyze_text('I am not afraid and no threats')['signals']['fear']
    assert not analyze_text('dhamki nahi')['signals']['threat']
    with pytest.raises(ValueError): audio_features(b'invalid')
    result=calculate({'feeling':1},'','en',[],{},now())
    assert 0<=result['scores']['distress']<=100
    assert result['trend']['insufficient_history']
    assert 'voice' in result['missing_inputs']
    trend=trends([{'at':(now()-timedelta(days=8)).isoformat(),'score':20}],50,now())
    assert trend['change_7d']==30 and trend['rapid_escalation']
