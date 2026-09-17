import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_URL = "postgresql+psycopg://localhost/acies"


def database_url():
    return os.environ.get("ACIES_DATABASE_URL", DEFAULT_URL)


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), future=True, pool_pre_ping=True)
    return _engine


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def session():
    return SessionLocal(bind=engine())
