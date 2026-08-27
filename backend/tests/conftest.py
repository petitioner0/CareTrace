from __future__ import annotations

import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:////tmp/caretrace-pytest.db"
os.environ["AI_PROVIDER"] = "fixture"
os.environ["APP_SECRET"] = "caretrace-test-secret"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def token(client):
    def login(role: str) -> str:
        response = client.post(
            "/api/auth/token",
            json={"email": f"{role}@caretrace.demo", "password": "demo123"},
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    return login


@pytest.fixture
def auth(token):
    return lambda role: {"Authorization": f"Bearer {token(role)}"}

