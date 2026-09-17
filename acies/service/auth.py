import hashlib
import secrets

from sqlalchemy import select

from acies.db import models as M


def new_token():
    return secrets.token_urlsafe(24)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def resolve_seat(db, token):
    """權杖 → 席位；找不到回 None。陣營只能由此推得。"""
    if not token:
        return None
    return db.scalar(select(M.Seat).where(M.Seat.token_hash == token_hash(token)))
