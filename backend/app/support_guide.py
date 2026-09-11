"""Guided multilingual support prompts — not a counsellor chatbot."""
from __future__ import annotations

def guided_support(text: str, language: str, signals: dict) -> dict:
    lower = (text or '').lower()
    safety = bool(signals.get('threat') or signals.get('urgent_safety') or signals.get('intimidation'))
    legal = bool(signals.get('court_stress') or 'court' in lower or 'adalat' in lower or 'कानून' in text or 'vakalat' in lower)
    money = bool(signals.get('financial_hardship') or signals.get('compensation_delay') or 'money' in lower or 'paise' in lower or 'मुआवजा' in text)
    rehab = bool(signals.get('support_request') and ('rehab' in lower or 'punarvas' in lower or 'rehabilitation' in lower))
    distress = bool(signals.get('fear') or signals.get('sleep_issue') or signals.get('hopelessness_like_language'))

    if safety:
        intent = 'safety'
    elif legal:
        intent = 'legal'
    elif money:
        intent = 'financial'
    elif rehab:
        intent = 'rehabilitation'
    elif distress:
        intent = 'checkin'
    else:
        intent = 'general'

    copy = {
        'en': {
            'safety': 'Thank you for telling us. If you feel unsafe, you can send a safety concern to your support team right away.',
            'legal': 'Legal proceedings can increase stress. You can request legal assistance or start a check-in so your team sees what changed.',
            'financial': 'Financial pressure matters. You can request financial assistance, or share more in a check-in.',
            'rehabilitation': 'Rehabilitation support can be requested below. Your team reviews every request.',
            'checkin': 'It sounds like things have been difficult. A short check-in helps your support team understand what changed.',
            'general': 'What has changed since your last check-in? You can start a check-in or request support below.',
            'disclaimer': 'Guided prompts only — not a live counsellor or chatbot conversation.',
        },
        'hi': {
            'safety': 'बताने के लिए धन्यवाद। यदि आप असुरक्षित महसूस करते हैं, तो तुरंत सुरक्षा संबंधी चिंता भेज सकते हैं।',
            'legal': 'कानूनी प्रक्रिया से तनाव बढ़ सकता है। आप कानूनी सहायता मांग सकते हैं या चेक-इन शुरू कर सकते हैं।',
            'financial': 'आर्थिक दबाव महत्वपूर्ण है। आप वित्तीय सहायता मांग सकते हैं या चेक-इन में और बता सकते हैं।',
            'rehabilitation': 'पुनर्वास सहायता नीचे मांगी जा सकती है। आपकी टीम हर अनुरोध देखती है।',
            'checkin': 'लगता है कठिनाई हो रही है। छोटा चेक-इन सहायता टीम को बदलाव समझने में मदद करता है।',
            'general': 'पिछली बातचीत के बाद क्या बदला है? आप चेक-इन शुरू कर सकते हैं या सहायता मांग सकते हैं।',
            'disclaimer': 'ये निर्देशित संकेत हैं — लाइव परामर्शदाता या चैटबॉट नहीं।',
        },
        'hinglish': {
            'safety': 'Batane ke liye dhanyavaad. Agar aap unsafe feel karte ho, turant safety concern bhej sakte ho.',
            'legal': 'Legal proceedings se stress badh sakta hai. Aap legal assistance maang sakte ho ya check-in shuru kar sakte ho.',
            'financial': 'Paise ka dabav matter karta hai. Aap financial assistance maang sakte ho ya check-in mein bata sakte ho.',
            'rehabilitation': 'Rehabilitation support neeche request kar sakte ho. Team har request review karti hai.',
            'checkin': 'Lagta hai mushkil ho rahi hai. Chhota check-in support team ko badlav samajhne mein madad karta hai.',
            'general': 'Pichhle check-in ke baad kya badla? Aap check-in shuru kar sakte hain ya madad maang sakte hain.',
            'disclaimer': 'Guided prompts only — live counsellor ya chatbot nahi.',
        },
    }
    lang = copy.get(language, copy['en'])
    actions = []
    if intent == 'safety' or safety:
        actions.append({'type': 'safety_report', 'label': 'Send safety concern'})
    if intent in {'checkin', 'general', 'legal', 'financial', 'rehabilitation'} or distress:
        actions.append({'type': 'checkin', 'label': 'Start check-in'})
    kind_map = {
        'legal': ('Legal assistance', 'Request legal assistance'),
        'financial': ('Financial assistance', 'Request financial assistance'),
        'rehabilitation': ('Rehabilitation', 'Request rehabilitation support'),
        'safety': ('Safety concern', 'Request safety support'),
    }
    if intent in kind_map:
        kind, label = kind_map[intent]
        actions.append({'type': 'support_request', 'kind': kind, 'label': label})
    if intent == 'general':
        actions.append({'type': 'support_request', 'kind': 'Counselling', 'label': 'Request counselling'})

    resources = [
        {'title': 'Your assigned support team', 'body': 'Humans review concerns and decide next steps. CareSignal does not diagnose or authorize action.'},
    ]
    if safety:
        resources.append({'title': 'If you are in immediate danger', 'body': 'Contact local emergency services or a trusted person nearby, then notify your support team here.'})

    return {
        'message': lang[intent],
        'intent': intent,
        'suggest_safety_report': safety,
        'actions': actions,
        'resources': resources,
        'method': 'guided multilingual support tree',
        'sent': False,
        'disclaimer': lang['disclaimer'],
    }
