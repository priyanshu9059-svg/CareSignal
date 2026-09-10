"""CPU baseline inference; heuristics are explicitly identified, never calibrated confidence."""
import io
import json
import re
import wave
from datetime import datetime
import numpy as np
from scipy.fft import dct
from .config import AI_MODE, MODEL_PATH, WEIGHTS, THRESHOLDS

LEXICON = {
 'threat': ['threat', 'dhamki', 'धमकी', 'intimidat', 'धमका'],
 'court_stress': ['court', 'hearing', 'adalat', 'अदालत', 'सुनवाई'],
 'sleep_issue': ['not slept', 'cannot sleep', "haven’t slept", "haven't slept", 'neend nahi', 'नींद नहीं', 'sleep poorly'],
 'family_safety': ['brother', 'family', 'bhai', 'parivar', 'भाई', 'परिवार'],
 'fear': ['scared', 'afraid', 'fear', 'darr', 'dar lag', 'डर', 'भय'],
 'social_isolation': ['alone', 'isolated', 'akela', 'अकेला'],
 'hopelessness_like_language': ['hopeless', 'no hope', 'बेबस', 'ummeed nahi'],
 'financial_hardship': ['money', 'financial', 'paise', 'पैसे', 'income'],
 'compensation_delay': ['compensation pending', 'compensation delay', 'muawza', 'मुआवजा'],
 'investigation_delay': ['investigation delay', 'जांच में देरी', 'jaanch der'],
 'avoidance': ['avoiding', 'avoid', 'बाहर नहीं', 'bahar nahi'],
 'support_request': ['help', 'support', 'madad', 'मदद'],
 'legal_support_request': ['lawyer', 'legal help', 'vakil', 'वकील'],
 'relocation_request': ['relocate', 'relocation', 'move away', 'स्थानांतरण'],
 'rehabilitation_request': ['rehabilitation', 'housing', 'पुनर्वास'],
 'urgent_safety': ['kill myself', 'end my life', 'hurt myself', 'suicide', 'आत्महत्या', 'marna chahta', 'jaan se maar'],
}

def analyze_text(text: str, language: str = 'en') -> dict:
    clean = re.sub(r'\s+', ' ', text.lower()).strip()
    evidence = []
    signals = {}
    for signal, phrases in LEXICON.items():
        found = []
        for phrase in phrases:
            for match in re.finditer(re.escape(phrase), clean):
                before = clean[max(0, match.start()-24):match.start()]
                after = clean[match.end():match.end()+18]
                negated = bool(re.search(r'(?:no|not|never|without)\s+(?:\w+\s+){0,2}$', before))
                negated |= bool(re.match(r'\s+(?:nahi|nahin|नहीं)', after))
                if not negated:
                    found.append(phrase)
        signals[signal] = bool(found)
        if found:
            evidence.append({'signal': signal, 'phrases': sorted(set(found)), 'source': 'AI-inferred', 'confidence': None})
    signals['family_safety'] = signals['family_safety'] and (signals['threat'] or signals['fear'])
    negative = min(1., sum(signals[k] for k in ['fear','threat','sleep_issue','social_isolation','hopelessness_like_language']) / 3)
    positive = any(s in clean for s in ['feeling better','feel safe','doing well','achha','बेहतर','सुरक्षित'])
    label = 'negative' if negative else ('positive' if positive else 'neutral')
    return {'language': 'hi' if re.search('[\u0900-\u097f]', clean) else language,
            'sentiment': {'label': label, 'score': round(negative if negative else (.6 if positive else 0), 2)},
            'emotions': {'fear': .8 if signals['fear'] else 0, 'sadness': .7 if signals['hopelessness_like_language'] else 0,
                         'anger': .6 if any(s in clean for s in ['angry','gussa','गुस्सा']) else 0, 'neutral': 0 if negative else 1},
            'signals': signals, 'evidence': evidence, 'method': 'multilingual-context-rules',
            'mode': AI_MODE, 'fallback': AI_MODE != 'demo', 'confidence_note': 'Heuristic intensities, not validated probabilities'}

def audio_features(raw: bytes, transcript: str = '') -> dict:
    try:
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            if audio.getsampwidth() != 2 or audio.getnchannels() not in (1,2):
                raise ValueError('Use 16-bit mono or stereo PCM WAV')
            rate = audio.getframerate()
            if not 8000 <= rate <= 48000 or audio.getnframes() > rate * 90:
                raise ValueError('Use an 8–48 kHz recording of up to 90 seconds')
            values = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(float) / 32768
            if audio.getnchannels() == 2:
                values = values.reshape(-1, 2).mean(axis=1)
    except (wave.Error, EOFError):
        raise ValueError('Invalid WAV recording; text input remains available')
    duration = len(values) / rate
    if duration < .3:
        raise ValueError('Record at least one second')
    frame_len = int(rate * .03)
    frames = [values[i:i+frame_len] for i in range(0, len(values)-frame_len, frame_len)]
    energy = np.array([np.sqrt(np.mean(f*f)) for f in frames])
    threshold = max(.008, float(np.max(energy)) * .1)
    pitches, centroids, mfccs = [], [], []
    for frame, volume in zip(frames, energy):
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(len(frame)), n=2048))**2
        frequencies = np.fft.rfftfreq(2048, 1/rate)
        centroids.append(float(np.sum(frequencies*spectrum)/(np.sum(spectrum)+1e-10)))
        mel = 2595 * np.log10(1+frequencies/700)
        edges = np.linspace(0, mel[-1], 28)
        bands = [np.sum(spectrum * np.maximum(0, np.minimum((mel-edges[j])/(edges[j+1]-edges[j]), (edges[j+2]-mel)/(edges[j+2]-edges[j+1])))) for j in range(26)]
        mfccs.append(dct(np.log(np.array(bands)+1e-10), norm='ortho')[:13])
        if volume > threshold:
            centered = frame-frame.mean()
            corr = np.correlate(centered, centered, mode='full')[len(frame)-1:]
            lo, hi = int(rate/400), min(int(rate/70), len(corr))
            lag = lo+int(np.argmax(corr[lo:hi]))
            if corr[lag] > .3 * corr[0]:
                pitches.append(rate/lag)
    return {'duration': round(duration,2), 'speech_rate': round(len(transcript.split())/duration*60) if transcript.strip() else None,
            'pause_ratio': round(float(np.mean(energy<threshold)),3), 'energy': round(float(np.sqrt(np.mean(values**2))),4),
            'pitch_mean': round(float(np.mean(pitches)),2) if pitches else None,
            'pitch_variability': round(float(np.std(pitches)),2) if pitches else None,
            'mfccs': np.mean(mfccs,axis=0).round(3).tolist(), 'spectral_centroid': round(float(np.mean(centroids)),2),
            'emotion': None, 'note': 'Acoustic measurements only; no validated speech emotion model installed'}

def category(value):
    return next(label for threshold,label in THRESHOLDS if value >= threshold)

def trends(history: list, current: float, at: datetime) -> dict:
    def dated(row):
        return datetime.fromisoformat(str(row['at']).replace('Z','+00:00')).replace(tzinfo=None)
    time = at.replace(tzinfo=None)
    past = sorted([h for h in history if dated(h) <= time], key=dated)
    values = [h['score'] for h in past] + [current]
    result = {'history_count':len(past), 'insufficient_history': len(past)<2}
    for days in (7,14,30):
        candidates = [h for h in past if (time-dated(h)).total_seconds() >= days*86400]
        result[f'change_{days}d'] = round(current-candidates[-1]['score'],1) if candidates else None
    dates = [(dated(h)-time).total_seconds()/86400 for h in past] + [0.]
    slope = float(np.polyfit(dates,values,1)[0]) if len(set(dates))>1 else 0.
    recent = values[-4:]
    result.update(slope=round(slope,2), volatility=round(float(np.std(recent)),2),
                  rapid_escalation=len(values)>1 and current-values[-2]>=15,
                  sustained_deterioration=len(recent)>=3 and all(a<b for a,b in zip(recent,recent[1:])),
                  direction='Improving' if len(values)>1 and current<values[-2]-2 else 'Worsening' if len(values)>1 and current>values[-2]+2 else 'Stable')
    return result

def calculate(responses: dict, text: str, language: str, history: list, conditions: dict, at: datetime, voice=None) -> dict:
    nlp = analyze_text(text,language)
    s = nlp['signals']
    answered = [responses[k] for k in ['feeling','fear','daily','avoidance','legal'] if responses.get(k) is not None]
    questionnaire = sum(answered)/len(answered)*25 if answered else None
    threat = bool(responses.get('threat') or s['threat'] or conditions.get('threat'))
    unsafe = responses.get('safe') is False or s['urgent_safety']
    safety = min(100, 55*threat + 45*unsafe + 20*s['family_safety'])
    previous = history[-1]['score'] if history else None
    prelim = questionnaire if questionnaire is not None else nlp['sentiment']['score']*100
    trend_signal = max(0,min(100,50+(prelim-previous)*2)) if previous is not None else None
    components = {'questionnaire': questionnaire, 'safety': safety,
                  'nlp': nlp['sentiment']['score']*100 if text.strip() else None,
                  'trend':trend_signal, 'sleep':responses.get('sleep')*25 if responses.get('sleep') is not None else None,
                  'engagement':min(100, conditions.get('missed_checkins',0)*25),
                  'voice':voice.get('baseline_deviation',0)*100 if voice and voice.get('baseline_deviation') is not None else None}
    denominator = sum(WEIGHTS[k] for k,v in components.items() if v is not None)
    explanation = [{'factor':k.replace('_',' ').title(), 'impact':round(value*WEIGHTS[k]/denominator,2),
                    'value':round(value,2), 'source':'Self-reported' if k in ['questionnaire','sleep'] else 'Historical trend' if k in ['trend','engagement'] else 'AI-inferred' if k in ['nlp','voice'] else 'Self-reported / Case-derived'} for k,value in components.items() if value is not None]
    distress = round(sum(e['impact'] for e in explanation))
    trend = trends(history, distress, at)
    features = [distress, previous or distress, trend['change_7d'] or 0, int(threat), int(conditions.get('court_event',False)),
                conditions.get('investigation_delay',0), conditions.get('compensation_delay',0), responses.get('sleep') or 0,
                responses.get('fear') or 0, conditions.get('missed_checkins',0)]
    prediction = predict(features)
    escalation = prediction['score']
    priority = category(max(distress,safety,escalation))
    if s['urgent_safety']:
        priority = 'Critical'
    recommendations = ['Counsellor follow-up'] if distress>=50 else ['Routine wellbeing follow-up']
    if threat or unsafe: recommendations.append('Safety/protection review')
    if s['court_stress'] or responses.get('legal',0): recommendations.append('Legal support review')
    if s['financial_hardship'] or s['compensation_delay']: recommendations.append('Financial assistance review')
    if s['rehabilitation_request']: recommendations.append('Rehabilitation support review')
    if responses.get('support') is False: recommendations.append('Support network follow-up')
    if responses.get('need') and responses['need'] not in recommendations: recommendations.append(responses['need'])
    if priority=='Critical': recommendations.insert(0,'Urgent human assessment')
    return {**nlp, 'voice':voice, 'scores':{'distress':distress,'safety_risk':safety,'escalation_risk':escalation},
            'priority':priority,'recommendations':recommendations,'explanation':explanation,'trend':trend,
            'prediction':prediction, 'missing_inputs':[k for k,v in components.items() if v is None],
            'what_changed': ([{'factor':'Threat reported','source':'Self-reported / Case-derived'}] if threat else []) +
                ([{'factor':f'Distress {distress-previous:+.0f} since previous check-in','source':'Historical trend'}] if previous is not None else []) +
                [{'factor':e['signal'].replace('_',' ').title(),'source':e['source']} for e in nlp['evidence']],
            'baseline':{'distress':round(float(np.mean([h['score'] for h in history[:3]])),1)} if len(history)>=3 else None,
            'limitations':'Prototype estimates, not clinically validated. Human review required.'}

def predict(features):
    path = MODEL_PATH / 'logistic.json'
    if path.exists():
        try:
            model = json.loads(path.read_text())
            z = (np.array(features)-np.array(model['mean'])) / np.array(model['scale'])
            score = round(float(100/(1+np.exp(-np.clip(np.dot(z,model['coef'])+model['intercept'],-30,30)))))
            return {'score':score,'method':'logistic-regression-synthetic','version':model['version'], 'fallback':False}
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            pass
    score = round(min(100,max(0,.65*features[0]+max(0,features[2])*.8+features[3]*20+features[4]*8+features[9]*4)))
    return {'score':score,'method':'rule-based escalation index (not probability)','fallback':True}
