# -*- coding: utf-8 -*-
"""Sessione operatore semplice (password singola + cookie firmato)."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import ADMIN_PASSWORD, ADMIN_USER, SECRET_KEY

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="outreach-session")
COOKIE = "outreach_session"
MAX_AGE = 60 * 60 * 24 * 30  # 30 giorni


def check_password(password: str) -> bool:
    return bool(password) and password == ADMIN_PASSWORD


def make_token() -> str:
    return _serializer.dumps({"u": ADMIN_USER})


def read_token(token: str | None):
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
