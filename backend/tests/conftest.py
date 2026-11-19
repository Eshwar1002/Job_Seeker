import os
import tempfile

# Isolate all persisted state (SQLite + Chroma) before app.config loads.
_TMP = tempfile.mkdtemp(prefix="jobpilot_test_")
os.environ["DATA_DIR"] = _TMP

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import llm, rag
from app.db import Base, get_db
from app.main import app

_engine = create_engine(f"sqlite:///{_TMP}/test.db", connect_args={"check_same_thread": False})
_TestSession = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def _override_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_db


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


@pytest.fixture(autouse=True)
def _no_external_calls(monkeypatch):
    """Keep tests offline and deterministic: no LLM, no Chroma, no network."""
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: None)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: None)
    monkeypatch.setattr(rag, "embed_texts", lambda texts: None)
    monkeypatch.setattr(rag, "index_profile", lambda profile: None)
    monkeypatch.setattr(rag, "index_jobs", lambda jobs: None)
    monkeypatch.setattr(rag, "retrieve_profile_context", lambda query, k=3: [])
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    session = _TestSession()
    yield session
    session.close()


@pytest.fixture()
def clean_db(db):
    from app.models import Application, Job, Profile, SearchRun

    for model in (Application, Job, SearchRun, Profile):
        db.query(model).delete()
    db.commit()
    yield db