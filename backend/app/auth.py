import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .database import User, RevokedToken, get_db, now
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
    issued = now()
    return jwt.encode({
        'sub': user.id,
        'jti': secrets.token_urlsafe(16),
        'exp': issued + timedelta(hours=8),
        'iat': issued,
        'iss': 'caresignal',
    }, JWT_SECRET, algorithm='HS256')

def _decode(raw: str) -> dict:
    return jwt.decode(raw or '', JWT_SECRET, algorithms=['HS256'], issuer='caresignal')

def revoke_token(db: Session, raw: str | None, user_id: str | None = None) -> bool:
    if not raw:
        return False
    try:
        payload = _decode(raw)
    except jwt.InvalidTokenError:
        try:
            payload = jwt.decode(raw, JWT_SECRET, algorithms=['HS256'], issuer='caresignal', options={'verify_exp': False})
        except jwt.InvalidTokenError:
            return False
    jti = payload.get('jti')
    if not jti:
        return False
    if db.get(RevokedToken, jti):
        return True
    exp = payload.get('exp')
    expires = datetime.fromtimestamp(exp, timezone.utc) if isinstance(exp, (int, float)) else now() + timedelta(hours=8)
    db.add(RevokedToken(id=jti, user_id=user_id or payload.get('sub'), expires_at=expires))
    return True

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get('session')
    if request.headers.get('authorization', '').startswith('Bearer '):
        raw = request.headers['authorization'][7:]
    try:
        payload = _decode(raw or '')
        jti = payload.get('jti')
        if jti and db.get(RevokedToken, jti):
            raise ValueError('revoked')
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
