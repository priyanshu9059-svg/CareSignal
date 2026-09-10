import hashlib
import hmac
import secrets
from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .database import User, get_db, now
from .config import JWT_SECRET

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + value

def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split(':')
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(expected, actual)

def token(user: User) -> str:
    return jwt.encode({'sub': user.id, 'exp': now() + timedelta(hours=8), 'iat': now(), 'iss': 'caresignal'}, JWT_SECRET, algorithm='HS256')

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get('session')
    if request.headers.get('authorization', '').startswith('Bearer '):
        raw = request.headers['authorization'][7:]
    try:
        payload = jwt.decode(raw or '', JWT_SECRET, algorithms=['HS256'], issuer='caresignal')
        user = db.get(User, payload['sub'])
        if user is None:
            raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(401, 'Please sign in again')

def roles(*allowed):
    def dependency(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, 'This role cannot perform this action')
        return user
    return dependency
