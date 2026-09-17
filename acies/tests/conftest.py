"""測試用資料庫：ACIES_TEST_DATABASE_URL（預設本機 acies_test），每次測試重建全部資料表。"""
import os

import pytest
from sqlalchemy import create_engine

os.environ.setdefault("ACIES_DATABASE_URL", os.environ.get("ACIES_TEST_DATABASE_URL", "postgresql+psycopg://localhost/acies_test"))

from acies.db import models as M  # noqa: E402
from acies.db import session as S  # noqa: E402


@pytest.fixture
def db_engine():
    eng = create_engine(os.environ["ACIES_DATABASE_URL"], future=True)
    M.Base.metadata.drop_all(eng)
    M.Base.metadata.create_all(eng)
    S._engine = eng
    yield eng
    eng.dispose()


@pytest.fixture
def client(db_engine):
    from fastapi.testclient import TestClient
    from acies.api.app import app
    with TestClient(app) as c:
        yield c
