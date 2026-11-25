"""Test setup: a throw-away storage folder and offline mode, set before the app is imported."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="nyayasetu-tests-")
os.environ["NYAYASETU_STORAGE"] = _TMP
os.environ["NYAYASETU_OFFLINE"] = "1"
os.environ["NYAYASETU_MODELS_DIR"] = os.path.join(_TMP, "models")  # never load a model trained on this laptop
os.environ.pop("GROQ_MODEL", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SAMPLES = ROOT / "frontend" / "samples"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/auth/login", json={"email": "demo@nyayasetu.in", "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def new_user(client):
    """A fresh registered user, for tests about one user not seeing another user's data."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"name": "Test User", "email": email, "password": "secret12"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
