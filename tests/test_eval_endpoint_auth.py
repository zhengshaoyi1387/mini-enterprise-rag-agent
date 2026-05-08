from fastapi.testclient import TestClient

import mini_rag.api.app as app_module
from mini_rag.config import Settings


def configure_app(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "settings",
        Settings(DASHSCOPE_API_KEY="test-key", AUTH_DB_PATH=tmp_path / "auth.sqlite3", _env_file=None),
    )


def login(client: TestClient, username: str = "employee", password: str = "employee123") -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_eval_run_requires_api_key():
    client = TestClient(app_module.app)
    response = client.post("/eval/run", json={"mode": "rag_eval"})
    assert response.status_code == 401


def test_eval_run_requires_admin_role(tmp_path, monkeypatch):
    configure_app(tmp_path, monkeypatch)
    client = TestClient(app_module.app)
    token = login(client)
    response = client.post(
        "/eval/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "rag_eval"},
    )
    assert response.status_code == 403
