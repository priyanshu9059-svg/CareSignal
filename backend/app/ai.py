"""CPU inference: domain lexicon + optional TF-IDF models + acoustic emotion proxy.

Third-party corpora (SentiMix, GoEmotions, CREMA-D, …) are never downloaded here.
Train optional JSON artifacts with ai/train_text.py after local preprocessing.
"""
import io
import json
import logging
import math
import re
import wave
from datetime import datetime
import numpy as np
from scipy.fft import dct
from .config import AI_MODE, MODEL_PATH, WEIGHTS, THRESHOLDS

# Domain lexicon expanded for atrocity / justice / rehab check-ins (EN + HI + Hinglish).
# Inspired by gaps vs SentiMix/IndicSentiment/GoEmotions — authored phrases, not copied corpora.
LEXICON = {
 'threat': ['threat', 'threatened', 'threatening', 'dhamki', 'dhamaka', 'धमकी', 'धमका', 'intimidat', 'dabav', 'pressure dal', 'jaan se maarne', 'maar dunga'],
 'court_stress': ['court', 'hearing', 'adalat', 'अदालत', 'सुनवाई', 'kachahri', 'vakalat', 'next date', 'tareekh'],
 'sleep_issue': ['not slept', 'cannot sleep', "haven't slept", "haven’t slept", 'neend nahi', 'neend nahi aa', 'नींद नहीं', 'sleep poorly', 'raat bhar jaaga', 'insomnia'],
 'family_safety': ['brother', 'sister', 'family', 'bhai', 'behen', 'parivar', 'भाई', 'बहन', 'परिवार', 'bachche', 'children', 'maa', 'papa'],
 'fear': ['scared', 'afraid', 'fear', 'terrified', 'anxious', 'panic', 'darr', 'dar lag', 'drarta', 'डर', 'भय', 'ghhabra', 'ghabrahat'],
 'social_isolation': ['alone', 'isolated', 'akela', 'अकेला', 'kisi se baat nahi', 'ostraci', 'boycott', 'samaj se door'],
 'hopelessness_like_language': ['hopeless', 'no hope', 'बेबस', 'ummeed nahi', 'khatam', 'sab khatam', 'koi raasta nahi', 'helpless'],
 'financial_hardship': ['money', 'financial', 'paise', 'पैसे', 'income', 'rozgar', 'naukri gayi', 'kharcha', 'debt', 'udhaar'],
 'compensation_delay': ['compensation pending', 'compensation delay', 'muawza', 'मुआवजा', 'rahat nahi', 'relief pending'],
 'investigation_delay': ['investigation delay', 'जांच में देरी', 'jaanch der', 'fir pending', 'charge sheet delay', 'police kuch nahi'],
 'avoidance': ['avoiding', 'avoid', 'बाहर नहीं', 'bahar nahi', 'ghar se nahi', 'nahi jaana chahta'],
 'support_request': ['help', 'support', 'madad', 'मदद', 'please call', 'sahaayata'],
 'legal_support_request': ['lawyer', 'legal help', 'vakil', 'वकील', 'free legal', 'legal aid'],
 'relocation_request': ['relocate', 'relocation', 'move away', 'स्थानांतरण', 'safe house', 'kahin aur'],
 'rehabilitation_request': ['rehabilitation', 'housing', 'पुनर्वास', 'job training', 'skill', 'punarvas'],
 'urgent_safety': ['kill myself', 'end my life', 'hurt myself', 'suicide', 'आत्महत्या', 'marna chahta', 'jaan se maar', 'self harm'],
 'intimidation': ['witness dabav', 'gawah', 'dont speak', 'mat bolna', 'zabaan band', 'hush money'],
 'caste_violence_context': ['jaati', 'caste', 'atrocity', 'atrocities', 'sc/st', 'dalit'],
}

POSITIVE_CUES = ['feeling better', 'feel safe', 'doing well', 'improving', 'joyful', 'grateful', 'happy', 'relieved',
                 'achha', 'achchha', 'बेहतर', 'सुरक्षित', 'theek hoon', 'thik hun', 'support mila', 'thank you', 'thanks']
ANGER_CUES = ['angry', 'anger', 'furious', 'gussa', 'गुस्सा', 'ghussa', 'nafrat', 'injustice', 'anyay']
SADNESS_CUES = ['sad', 'cry', 'crying', 'tears', 'udaas', 'उदास', 'rona', 'dukhi', 'heartbroken', 'grief']

_TEXT_MODEL = None
_VOICE_MODEL = None

def _load_json_model(name):
    path = MODEL_PATH / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError):
        return None

def _tfidf_vector(tokens, vocabulary, idf):
    # Match sklearn TfidfVectorizer defaults: raw TF * idf, then L2 norm
    counts = {}
    for tok in tokens:
        if tok in vocabulary:
            counts[tok] = counts.get(tok, 0) + 1
    vec = np.zeros(len(vocabulary), dtype=float)
    for tok, c in counts.items():
        idx = vocabulary[tok]
        vec[idx] = c * idf[idx]
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec

def _tokenize(text: str):
    return re.findall(r'[\w\u0900-\u097f]+', text.lower())

def _predict_text_model(clean: str):
    """Optional TF-IDF logistic trained via ai/train_text.py (SentiMix/GoEmotions/Kaggle JSONL)."""
    global _TEXT_MODEL
    if _TEXT_MODEL is None:
        _TEXT_MODEL = _load_json_model('text_sentiment.json')
    model = _TEXT_MODEL
    if not model:
        return None
    try:
        tokens = _tokenize(clean)
        x = _tfidf_vector(tokens, model['vocabulary'], np.array(model['idf']))
        classes = model['classes']
        scores = {}
        for i, label in enumerate(classes):
            z = float(np.dot(x, model['coef'][i]) + model['intercept'][i])
            scores[label] = z
        # softmax
        mx = max(scores.values())
        exps = {k: math.exp(v - mx) for k, v in scores.items()}
        denom = sum(exps.values()) or 1
        probs = {k: exps[k] / denom for k in exps}
        best = max(probs, key=probs.get)
        # normalize to negative intensity for CareSignal sentiment.score
        neg = probs.get('negative', 0) + .5 * probs.get('fear', 0) + .4 * probs.get('sadness', 0)
        pos = probs.get('positive', 0) + .5 * probs.get('joy', 0)
        if best in ('negative', 'fear', 'sadness', 'anger', 'disgust'):
            label = 'negative'
            score = round(min(1., neg), 2)
        elif best in ('positive', 'joy'):
            label = 'positive'
            score = round(min(1., max(pos, .55)), 2)
        else:
            label = 'neutral'
            score = 0
        emotions = {
            'fear': round(probs.get('fear', probs.get('negative', 0) * .5), 2),
            'sadness': round(probs.get('sadness', probs.get('negative', 0) * .4), 2),
            'anger': round(probs.get('anger', 0), 2),
            'joy': round(probs.get('joy', probs.get('positive', 0)), 2),
            'neutral': round(probs.get('neutral', 1 if label == 'neutral' else 0), 2),
        }
        return {'sentiment': {'label': label, 'score': score}, 'emotions': emotions,
                'probs': {k: round(v, 3) for k, v in probs.items()},
                'method': model.get('version', 'tfidf-logistic'), 'fallback': False}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

def analyze_text(text: str, language: str = 'en') -> dict:
    clean = re.sub(r'\s+', ' ', text.lower()).strip()
    evidence = []
    signals = {}
    hit_counts = {}
    for signal, phrases in LEXICON.items():
        found = []
        for phrase in phrases:
            for match in re.finditer(re.escape(phrase), clean):
                before = clean[max(0, match.start() - 24):match.start()]
                after = clean[match.end():match.end() + 18]
                negated = bool(re.search(r'(?:no|not|never|without)\s+(?:\w+\s+){0,2}$', before))
                negated |= bool(re.match(r'\s+(?:nahi|nahin|नहीं)', after))
                if not negated:
                    found.append(phrase)
        signals[signal] = bool(found)
        hit_counts[signal] = len(set(found))
        if found:
            evidence.append({'signal': signal, 'phrases': sorted(set(found)), 'source': 'AI-inferred', 'confidence': None})
    signals['family_safety'] = signals['family_safety'] and (signals['threat'] or signals['fear'] or signals['intimidation'])

    # Graded intensities (GoEmotions-inspired mapping → CareSignal core emotions)
    def intensity(base, count, boost=0):
        if count <= 0 and boost <= 0:
            return 0.0
        return round(min(1.0, base + 0.12 * max(count - 1, 0) + boost), 2)

    anger_hits = sum(1 for c in ANGER_CUES if c in clean) + hit_counts.get('intimidation', 0)
    sadness_hits = sum(1 for c in SADNESS_CUES if c in clean) + hit_counts.get('hopelessness_like_language', 0)
    fear_hits = hit_counts.get('fear', 0) + hit_counts.get('threat', 0) + hit_counts.get('urgent_safety', 0)

    emotions = {
        'fear': intensity(0.72, fear_hits),
        'sadness': intensity(0.65, sadness_hits, 0.15 if signals['hopelessness_like_language'] else 0),
        'anger': intensity(0.6, anger_hits),
        'neutral': 0.0,
    }
    if max(emotions.values()) == 0:
        emotions['neutral'] = 1.0

    distress_signals = ['fear', 'threat', 'sleep_issue', 'social_isolation', 'hopelessness_like_language', 'intimidation', 'urgent_safety']
    negative = min(1., sum(1 for k in distress_signals if signals[k]) / 3.5)
    positive = any(s in clean for s in POSITIVE_CUES)
    label = 'negative' if negative else ('positive' if positive else 'neutral')
    sentiment = {'label': label, 'score': round(negative if negative else (.6 if positive else 0), 2)}
    method = 'multilingual-context-rules+graded-emotions'
    model_out = _predict_text_model(clean) if clean else None
    fallback = True
    if model_out:
        # Domain lexicon wins on safety-critical cues; trained head fills gaps / polarity otherwise
        strong_distress = any(signals[k] for k in ['urgent_safety', 'threat', 'fear', 'intimidation', 'hopelessness_like_language'])
        if strong_distress and negative >= 0.3:
            sentiment = {'label': 'negative', 'score': round(max(negative, model_out['sentiment']['score'] if model_out['sentiment']['label'] == 'negative' else 0), 2)}
        elif positive:
            sentiment = {'label': 'positive', 'score': round(max(0.6, model_out['emotions'].get('joy', 0), model_out['sentiment']['score'] if model_out['sentiment']['label'] == 'positive' else 0.6), 2)}
        else:
            sentiment = model_out['sentiment']
        for key in ('fear', 'sadness', 'anger'):
            emotions[key] = round(max(emotions[key], model_out['emotions'].get(key, 0)), 2)
        if 'joy' in model_out['emotions']:
            emotions['joy'] = model_out['emotions']['joy']
        emotions['neutral'] = model_out['emotions'].get('neutral', emotions['neutral'])
        method = f"{model_out['method']}+domain-lexicon"
        fallback = False
        evidence.append({'signal': 'trained_text_model', 'phrases': [model_out['method']], 'source': 'AI-inferred', 'confidence': None})

    return {'language': 'hi' if re.search('[\u0900-\u097f]', clean) else language,
            'sentiment': sentiment, 'emotions': emotions, 'signals': signals, 'evidence': evidence,
            'method': method, 'mode': AI_MODE, 'fallback': fallback or AI_MODE != 'demo',
            'confidence_note': 'Graded heuristic and/or TF-IDF intensities — not calibrated clinical probabilities'}

def voice_emotion_proxy(features: dict) -> dict:
    """Heuristic emotion/stress from acoustics (inspired by SER feature cues; not a trained CREMA/RAVDESS net)."""
    global _VOICE_MODEL
    energy = features.get('energy') or 0
    pause = features.get('pause_ratio') or 0
    pitch = features.get('pitch_mean')
    pvar = features.get('pitch_variability') or 0
    # Optional trained sklearn-style linear model on [energy, pause, pitch_mean, pitch_var, centroid]
    if _VOICE_MODEL is None:
        _VOICE_MODEL = _load_json_model('voice_emotion.json')
    if _VOICE_MODEL and pitch is not None:
        try:
            x = np.array([
                energy, pause, pitch or 0, pvar,
                features.get('spectral_centroid') or 0,
                *list((features.get('mfccs') or [0] * 5)[:5])
            ], dtype=float)
            # pad/truncate to model size
            n = len(_VOICE_MODEL['mean'])
            if len(x) < n:
                x = np.pad(x, (0, n - len(x)))
            x = x[:n]
            z = (x - np.array(_VOICE_MODEL['mean'])) / np.array(_VOICE_MODEL['scale'])
            classes = _VOICE_MODEL['classes']
            logits = {}
            for i, label in enumerate(classes):
                logits[label] = float(np.dot(z, _VOICE_MODEL['coef'][i]) + _VOICE_MODEL['intercept'][i])
            mx = max(logits.values())
            exps = {k: math.exp(v - mx) for k, v in logits.items()}
            denom = sum(exps.values()) or 1
            probs = {k: round(exps[k] / denom, 3) for k in exps}
            label = max(probs, key=probs.get)
            stress = round(min(1., probs.get('fear', 0) + probs.get('anger', 0) + .5 * probs.get('sadness', 0)), 3)
            return {'emotion': label, 'probs': probs, 'stress_score': stress,
                    'method': _VOICE_MODEL.get('version', 'voice-linear'), 'note': 'Trained acoustic proxy; acted-speech domain shift possible'}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            logging.getLogger('caresignal.ai').warning('Voice emotion model failed; using heuristic proxy: %s', type(exc).__name__)

    # Rule proxy grounded in common SER acoustic tendencies (high arousal → fear/anger; low energy+pause → sadness)
    if pitch is None:
        return {'emotion': None, 'stress_score': round(min(1., energy * 2 + pause), 3),
                'method': 'acoustic-heuristic', 'note': 'Pitch unavailable; stress from energy/pauses only'}
    arousal = min(1., (energy / 0.15) * 0.45 + (pvar / 80) * 0.35 + (max(0, pitch - 160) / 120) * 0.2)
    withdrawal = min(1., pause * 0.7 + max(0, 0.08 - energy) * 4)
    if arousal >= 0.55 and pitch >= 190:
        label = 'fear' if pause < 0.45 else 'anger'
    elif withdrawal >= 0.45:
        label = 'sadness'
    elif arousal < 0.25 and pause < 0.35:
        label = 'neutral'
    else:
        label = 'fear' if arousal > withdrawal else 'sadness'
    stress = round(min(1., 0.65 * arousal + 0.45 * withdrawal), 3)
    return {'emotion': label, 'stress_score': stress, 'arousal': round(arousal, 3), 'withdrawal': round(withdrawal, 3),
            'method': 'acoustic-heuristic-v2',
            'note': 'Heuristic proxy inspired by SER feature patterns (RAVDESS/CREMA-D literature); not a validated classifier'}

def audio_features(raw: bytes, transcript: str = '') -> dict:
    try:
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            if audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2):
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
    frames = [values[i:i + frame_len] for i in range(0, len(values) - frame_len, frame_len)]
    energy = np.array([np.sqrt(np.mean(f * f)) for f in frames])
    threshold = max(.008, float(np.max(energy)) * .1)
    pitches, centroids, mfccs = [], [], []
    for frame, volume in zip(frames, energy):
        spectrum = np.abs(np.fft.rfft(frame * np.hanning(len(frame)), n=2048)) ** 2
        frequencies = np.fft.rfftfreq(2048, 1 / rate)
        centroids.append(float(np.sum(frequencies * spectrum) / (np.sum(spectrum) + 1e-10)))
        mel = 2595 * np.log10(1 + frequencies / 700)
        edges = np.linspace(0, mel[-1], 28)
        bands = [np.sum(spectrum * np.maximum(0, np.minimum((mel - edges[j]) / (edges[j + 1] - edges[j]), (edges[j + 2] - mel) / (edges[j + 2] - edges[j + 1])))) for j in range(26)]
        mfccs.append(dct(np.log(np.array(bands) + 1e-10), norm='ortho')[:13])
        if volume > threshold:
            centered = frame - frame.mean()
            corr = np.correlate(centered, centered, mode='full')[len(frame) - 1:]
            lo, hi = int(rate / 400), min(int(rate / 70), len(corr))
            lag = lo + int(np.argmax(corr[lo:hi]))
            if corr[lag] > .3 * corr[0]:
                pitches.append(rate / lag)
    result = {'duration': round(duration, 2), 'speech_rate': round(len(transcript.split()) / duration * 60) if transcript.strip() else None,
              'pause_ratio': round(float(np.mean(energy < threshold)), 3), 'energy': round(float(np.sqrt(np.mean(values ** 2))), 4),
              'pitch_mean': round(float(np.mean(pitches)), 2) if pitches else None,
              'pitch_variability': round(float(np.std(pitches)), 2) if pitches else None,
              'mfccs': np.mean(mfccs, axis=0).round(3).tolist(), 'spectral_centroid': round(float(np.mean(centroids)), 2)}
    proxy = voice_emotion_proxy(result)
    result.update({'emotion': proxy.get('emotion'), 'stress_score': proxy.get('stress_score'),
                   'emotion_method': proxy.get('method'), 'emotion_probs': proxy.get('probs'),
                   'note': proxy.get('note')})
    return result

def category(value):
    return next(label for threshold, label in THRESHOLDS if value >= threshold)

def trends(history: list, current: float, at: datetime) -> dict:
    def dated(row):
        return datetime.fromisoformat(str(row['at']).replace('Z', '+00:00')).replace(tzinfo=None)
    time = at.replace(tzinfo=None)
    past = sorted([h for h in history if dated(h) <= time], key=dated)
    values = [h['score'] for h in past] + [current]
    result = {'history_count': len(past), 'insufficient_history': len(past) < 2}
    for days in (7, 14, 30):
        candidates = [h for h in past if (time - dated(h)).total_seconds() >= days * 86400]
        result[f'change_{days}d'] = round(current - candidates[-1]['score'], 1) if candidates else None
    dates = [(dated(h) - time).total_seconds() / 86400 for h in past] + [0.]
    slope = float(np.polyfit(dates, values, 1)[0]) if len(set(dates)) > 1 else 0.
    recent = values[-4:]
    result.update(slope=round(slope, 2), volatility=round(float(np.std(recent)), 2),
                  rapid_escalation=len(values) > 1 and current - values[-2] >= 15,
                  sustained_deterioration=len(recent) >= 3 and all(a < b for a, b in zip(recent, recent[1:])),
                  direction='Improving' if len(values) > 1 and current < values[-2] - 2 else 'Worsening' if len(values) > 1 and current > values[-2] + 2 else 'Stable')
    return result

def calculate(responses: dict, text: str, language: str, history: list, conditions: dict, at: datetime, voice=None) -> dict:
    nlp = analyze_text(text, language)
    s = nlp['signals']
    answered = [responses[k] for k in ['feeling', 'fear', 'daily', 'avoidance', 'legal'] if responses.get(k) is not None]
    questionnaire = sum(answered) / len(answered) * 25 if answered else None
    threat = bool(responses.get('threat') or s['threat'] or s.get('intimidation') or conditions.get('threat'))
    unsafe = responses.get('safe') is False or s['urgent_safety']
    safety = min(100, 55 * threat + 45 * unsafe + 20 * s['family_safety'])
    previous = history[-1]['score'] if history else None
    # NLP score: blend sentiment with emotion arousal (fear/sadness)
    emotion_boost = max(nlp['emotions'].get('fear', 0), nlp['emotions'].get('sadness', 0), nlp['emotions'].get('anger', 0))
    nlp_score = None
    if text.strip():
        nlp_score = min(100, nlp['sentiment']['score'] * 100 * 0.7 + emotion_boost * 100 * 0.3)
    prelim = questionnaire if questionnaire is not None else (nlp_score or 0)
    trend_signal = max(0, min(100, 50 + (prelim - previous) * 2)) if previous is not None else None
    voice_component = None
    if voice:
        if voice.get('baseline_deviation') is not None:
            voice_component = voice['baseline_deviation'] * 100
        elif voice.get('stress_score') is not None:
            voice_component = voice['stress_score'] * 100
    components = {'questionnaire': questionnaire, 'safety': safety, 'nlp': nlp_score, 'trend': trend_signal,
                  'sleep': responses.get('sleep') * 25 if responses.get('sleep') is not None else None,
                  'engagement': min(100, conditions.get('missed_checkins', 0) * 25), 'voice': voice_component}
    denominator = sum(WEIGHTS[k] for k, v in components.items() if v is not None) or 1
    explanation = [{'factor': k.replace('_', ' ').title(), 'impact': round(value * WEIGHTS[k] / denominator, 2),
                    'value': round(value, 2),
                    'source': 'Self-reported' if k in ['questionnaire', 'sleep'] else 'Historical trend' if k in ['trend', 'engagement'] else 'AI-inferred' if k in ['nlp', 'voice'] else 'Self-reported / Case-derived'}
                   for k, value in components.items() if value is not None]
    distress = round(sum(e['impact'] for e in explanation))
    trend = trends(history, distress, at)
    features = [distress, previous or distress, trend['change_7d'] or 0, int(threat), int(conditions.get('court_event', False)),
                conditions.get('investigation_delay', 0), conditions.get('compensation_delay', 0), responses.get('sleep') or 0,
                responses.get('fear') or 0, conditions.get('missed_checkins', 0)]
    prediction = predict(features)
    escalation = prediction['score']
    priority = category(max(distress, safety, escalation))
    if s['urgent_safety']:
        priority = 'Critical'
    recommendations = ['Counsellor follow-up'] if distress >= 50 else ['Routine wellbeing follow-up']
    if threat or unsafe:
        recommendations.append('Safety/protection review')
    if s['court_stress'] or responses.get('legal', 0):
        recommendations.append('Legal support review')
    if s['financial_hardship'] or s['compensation_delay']:
        recommendations.append('Financial assistance review')
    if s['rehabilitation_request']:
        recommendations.append('Rehabilitation support review')
    if responses.get('support') is False:
        recommendations.append('Support network follow-up')
    if responses.get('need') and responses['need'] not in recommendations:
        recommendations.append(responses['need'])
    if priority == 'Critical':
        recommendations.insert(0, 'Urgent human assessment')
    return {**nlp, 'voice': voice, 'scores': {'distress': distress, 'safety_risk': safety, 'escalation_risk': escalation},
            'priority': priority, 'recommendations': recommendations, 'explanation': explanation, 'trend': trend,
            'prediction': prediction, 'missing_inputs': [k for k, v in components.items() if v is None],
            'what_changed': ([{'factor': 'Threat reported', 'source': 'Self-reported / Case-derived'}] if threat else []) +
            ([{'factor': f'Distress {distress - previous:+.0f} since previous check-in', 'source': 'Historical trend'}] if previous is not None else []) +
            [{'factor': e['signal'].replace('_', ' ').title(), 'source': e['source']} for e in nlp['evidence']],
            'baseline': {'distress': round(float(np.mean([h['score'] for h in history[:3]])), 1)} if len(history) >= 3 else None,
            'limitations': 'Prototype estimates, not clinically validated. Human review required.'}

def predict(features):
    path = MODEL_PATH / 'logistic.json'
    if path.exists():
        try:
            model = json.loads(path.read_text())
            z = (np.array(features) - np.array(model['mean'])) / np.array(model['scale'])
            score = round(float(100 / (1 + np.exp(-np.clip(np.dot(z, model['coef']) + model['intercept'], -30, 30)))))
            return {'score': score, 'method': 'logistic-regression-synthetic', 'version': model['version'], 'fallback': False}
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            logging.getLogger('caresignal.ai').warning('Escalation model failed; using rule fallback: %s', type(exc).__name__)
    score = round(min(100, max(0, .65 * features[0] + max(0, features[2]) * .8 + features[3] * 20 + features[4] * 8 + features[9] * 4)))
    return {'score': score, 'method': 'rule-based escalation index (not probability)', 'fallback': True}
