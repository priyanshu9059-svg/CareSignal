import os
import secrets
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT / 'backend' / 'demo.db'))
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
AI_MODE = os.getenv('AI_MODE', 'demo')
if AI_MODE not in {'demo', 'local', 'production'}:
    raise RuntimeError('Invalid AI_MODE')
JWT_SECRET = os.getenv('JWT_SECRET') or secrets.token_urlsafe(48)
if AI_MODE == 'production' and not os.getenv('JWT_SECRET'):
    raise RuntimeError('JWT_SECRET is required in production')
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
DEMO_ENABLED = os.getenv('DEMO_ENABLED', 'true').lower() == 'true' and AI_MODE != 'production'
MODEL_PATH = Path(os.getenv('MODEL_PATH', str(ROOT / 'ai' / 'models')))
STORAGE_PATH = Path(os.getenv('STORAGE_PATH', str(ROOT / 'storage')))
STORAGE_PATH.mkdir(parents=True, exist_ok=True)
(STORAGE_PATH / 'voices').mkdir(parents=True, exist_ok=True)
WEIGHTS = {'questionnaire': .25, 'safety': .20, 'nlp': .15, 'trend': .15,
           'sleep': .10, 'engagement': .05, 'voice': .10}
THRESHOLDS = [(85, 'Critical'), (70, 'High'), (50, 'Moderate'), (30, 'Mild'), (0, 'Low')]
if os.getenv('RISK_WEIGHTS'):
    custom = json.loads(os.environ['RISK_WEIGHTS'])
    if set(custom) != set(WEIGHTS) or any(not isinstance(v,(int,float)) or v<=0 for v in custom.values()):
        raise RuntimeError('RISK_WEIGHTS must supply a positive number for every component')
    WEIGHTS = custom
if os.getenv('RISK_THRESHOLDS'):
    custom = json.loads(os.environ['RISK_THRESHOLDS'])
    if set(custom) != {'Low','Mild','Moderate','High','Critical'} or custom['Low'] != 0 or not (0 < custom['Mild'] < custom['Moderate'] < custom['High'] < custom['Critical'] <= 100):
        raise RuntimeError('Invalid RISK_THRESHOLDS')
    THRESHOLDS = sorted([(value,key) for key,value in custom.items()],reverse=True)
