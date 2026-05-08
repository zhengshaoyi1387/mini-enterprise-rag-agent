from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mini_rag.config import Settings
from mini_rag.observability.request_logger import RequestLoggerMiddleware


def test_request_logger_writes_jsonl(tmp_path: Path):
    settings = Settings(REQUEST_LOG_PATH=str(tmp_path / "requests.jsonl"))
    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware, settings=settings)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")
    content = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert '"path": "/ping"' in content
    assert '"status_code": 200' in content
