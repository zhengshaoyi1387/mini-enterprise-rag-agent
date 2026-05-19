from __future__ import annotations

import json

from fastapi.testclient import TestClient

import mini_rag.api.app as app_module
from mini_rag.config import Settings
from mini_rag.security.auth_store import SQLiteAuthStore
from mini_rag.security.permissions import get_allowed_tool_actions


class RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.stream_calls: list[dict] = []

    def ask(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        trace = {
            "trace_id": kwargs.get("trace_id"),
            "user_id": kwargs.get("user_id"),
            "role": kwargs.get("role"),
            "question": query,
            "requested_kbs": kwargs.get("kb_ids") or [],
            "allowed_kbs": ["public"],
            "used_kbs": ["public"],
            "route": "direct",
            "answer": "你好，我可以帮你查询企业知识库。",
            "sources": [],
            "tool_calls": [],
            "node_trace": [],
            "audit_events": [],
            "mainline_log": [
                {
                    "step": 1,
                    "stage": "runtime_context",
                    "title": "构建运行上下文",
                    "summary": "已识别用户身份、权限和当前时间。",
                    "details": ["用户角色：employee"],
                }
            ],
            "mainline_log_text": "1. 构建运行上下文：已识别用户身份、权限和当前时间。",
            "error": None,
        }
        return {"answer": trace["answer"], "route": "direct", "sources": [], "trace": trace}

    def stream(self, query: str, **kwargs):
        self.stream_calls.append({"query": query, **kwargs})
        trace = {
            "trace_id": kwargs.get("trace_id"),
            "user_id": kwargs.get("user_id"),
            "role": kwargs.get("role"),
            "question": query,
            "used_kbs": ["public"],
            "route": "direct",
            "answer": "流式回答",
            "sources": [],
            "tool_calls": [],
            "node_trace": [],
            "audit_events": [],
            "mainline_log": [
                {
                    "step": 1,
                    "stage": "runtime_context",
                    "title": "构建运行上下文",
                    "summary": "已识别用户身份、权限和当前时间。",
                    "details": ["用户角色：employee"],
                }
            ],
            "mainline_log_text": "1. 构建运行上下文：已识别用户身份、权限和当前时间。",
            "error": None,
        }
        yield {"event": "token", "content": "流式"}
        yield {"event": "token", "content": "回答"}
        yield {"event": "final", "answer": "流式回答", "trace": trace}


def configure_app(tmp_path, monkeypatch, agent: RecordingAgent | None = None) -> RecordingAgent:
    settings = Settings(
        DASHSCOPE_API_KEY="test-key",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        TRACE_DIR=tmp_path / "traces",
        AUDIT_LOG_PATH=tmp_path / "audit.jsonl",
        _env_file=None,
    )
    agent = agent or RecordingAgent()
    monkeypatch.setattr(app_module, "settings", settings)
    monkeypatch.setattr(app_module, "_AGENT_INSTANCE", agent)
    return agent


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me_returns_server_side_role_and_permissions(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        token = login(client, "employee", "employee123")
        response = client.get("/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "employee"
    assert payload["role"] == "employee"
    assert "public" in payload["allowed_kbs"]
    assert "finance" not in payload["allowed_kbs"]


def test_chat_ignores_spoofed_request_body_role(tmp_path, monkeypatch) -> None:
    agent = configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        token = login(client, "employee", "employee123")
        response = client.post(
            "/chat",
            headers=auth_header(token),
            json={
                "user_id": "attacker-controlled",
                "role": "admin",
                "query": "你好",
                "kb_ids": ["public"],
            },
        )

    assert response.status_code == 200, response.text
    assert agent.calls
    assert agent.calls[0]["role"] == "employee"
    assert agent.calls[0]["user_id"] == "employee"
    payload = response.json()
    assert payload["mainline_log"][0]["title"] == "构建运行上下文"
    assert "构建运行上下文" in payload["mainline_log_text"]
    assert "messages" not in payload["mainline_log_text"]


def test_admin_can_update_role_kb_permissions(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        admin_token = login(client, "admin", "admin123")
        employee_token = login(client, "employee", "employee123")

        before = client.get("/auth/me", headers=auth_header(employee_token)).json()
        assert "finance" not in before["allowed_kbs"]

        response = client.patch(
            "/admin/roles",
            headers=auth_header(admin_token),
            json={
                "role": "employee",
                "allowed_kbs": ["public", "hr", "it", "product", "finance"],
                "allowed_tools": ["search_knowledge_base", "query_attendance_summary"],
            },
        )
        assert response.status_code == 200, response.text

        after = client.get("/auth/me", headers=auth_header(employee_token)).json()

    assert "finance" in after["allowed_kbs"]


def test_admin_can_update_public_role_policy(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        admin_token = login(client, "admin", "admin123")
        response = client.patch(
            "/admin/roles",
            headers=auth_header(admin_token),
            json={
                "role": "public",
                "allowed_kbs": ["public"],
                "allowed_tools": ["search_knowledge_base", "get_current_datetime"],
            },
        )

    assert response.status_code == 200, response.text
    public_policy = next(item for item in response.json()["roles"] if item["role"] == "public")
    assert public_policy["allowed_tools"] == ["get_current_datetime", "search_knowledge_base"]


def test_role_policy_preserves_action_level_tool_specs(tmp_path) -> None:
    store = SQLiteAuthStore(tmp_path / "auth.sqlite3")
    policy = store.update_role_policy(
        "admin",
        ["public", "hr"],
        ["search_knowledge_base", "manage_company_calendar.query"],
    )
    policies = store.list_role_policies()

    assert policy.allowed_tools == ["manage_company_calendar.query", "search_knowledge_base"]
    assert get_allowed_tool_actions("admin", "manage_company_calendar", role_policies=policies) == {"query"}


def test_regular_user_cannot_access_admin_or_trace_endpoints(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        token = login(client, "employee", "employee123")
        users_response = client.get("/admin/users", headers=auth_header(token))
        roles_response = client.get("/admin/roles", headers=auth_header(token))
        trace_response = client.get("/traces/not-exists", headers=auth_header(token))

    assert users_response.status_code == 403
    assert roles_response.status_code == 403
    assert trace_response.status_code == 403


def test_admin_can_import_list_and_delete_kb_document(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    app_module.settings.data_dir = tmp_path / "kbs"
    with TestClient(app_module.app) as client:
        admin_token = login(client, "admin", "admin123")

        created = client.post(
            "/admin/kbs/finance/documents",
            headers=auth_header(admin_token),
            json={
                "filename": "finance_admin_test.md",
                "content": "# 管理员导入测试\n\n这是一份财务知识库测试文档。",
            },
        )
        listed = client.get("/admin/kbs", headers=auth_header(admin_token))

        assert created.status_code == 200, created.text
        created_doc = created.json()["document"]
        assert created_doc["kb_id"] == "finance"
        assert created_doc["path"] == "finance/finance_admin_test.md"
        assert created_doc["size_bytes"] > 0
        assert created_doc["requires_reindex"] is True
        assert (app_module.settings.data_dir / "finance" / "finance_admin_test.md").exists()

        deleted = client.delete(
            "/admin/kbs/finance/documents/finance_admin_test.md",
            headers=auth_header(admin_token),
        )

    assert listed.status_code == 200, listed.text
    finance = next(kb for kb in listed.json()["kbs"] if kb["kb_id"] == "finance")
    assert any(doc["path"] == "finance/finance_admin_test.md" for doc in finance["documents"])

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["document"]["path"] == "finance/finance_admin_test.md"
    assert not (app_module.settings.data_dir / "finance" / "finance_admin_test.md").exists()


def test_non_admin_cannot_manage_kb_documents(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    app_module.settings.data_dir = tmp_path / "kbs"
    with TestClient(app_module.app) as client:
        employee_token = login(client, "employee", "employee123")
        upload = client.post(
            "/admin/kbs/public/documents",
            headers=auth_header(employee_token),
            json={"filename": "blocked.md", "content": "# blocked"},
        )
        delete = client.delete(
            "/admin/kbs/public/documents/blocked.md",
            headers=auth_header(employee_token),
        )
        reindex = client.post("/admin/kbs/reindex", headers=auth_header(employee_token), json={"reset": False})

    assert upload.status_code == 403
    assert delete.status_code == 403
    assert reindex.status_code == 403


def test_admin_can_trigger_kb_reindex(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    app_module.settings.data_dir = tmp_path / "kbs"
    calls: list[dict] = []

    def fake_build_index(settings: Settings, reset: bool = False) -> dict:
        calls.append({"settings": settings, "reset": reset})
        return {"chunk_count": 3, "changed_source_count": 1, "reset": reset}

    monkeypatch.setattr(app_module, "build_index", fake_build_index, raising=False)
    with TestClient(app_module.app) as client:
        admin_token = login(client, "admin", "admin123")
        response = client.post("/admin/kbs/reindex", headers=auth_header(admin_token), json={"reset": True})

    assert response.status_code == 200, response.text
    assert response.json()["result"]["chunk_count"] == 3
    assert calls == [{"settings": app_module.settings, "reset": True}]


def test_disabling_user_invalidates_existing_token(tmp_path, monkeypatch) -> None:
    configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        admin_token = login(client, "admin", "admin123")
        employee_token = login(client, "employee", "employee123")
        response = client.patch(
            "/admin/users/employee",
            headers=auth_header(admin_token),
            json={"enabled": False},
        )
        assert response.status_code == 200, response.text

        me_response = client.get("/auth/me", headers=auth_header(employee_token))

    assert me_response.status_code == 401


def test_chat_stream_emits_token_and_final_events(tmp_path, monkeypatch) -> None:
    agent = configure_app(tmp_path, monkeypatch)
    with TestClient(app_module.app) as client:
        token = login(client, "employee", "employee123")
        response = client.post(
            "/chat/stream",
            headers=auth_header(token),
            json={"user_id": "ignored", "role": "admin", "query": "你好", "kb_ids": ["public"]},
        )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["event"] for event in events] == ["token", "token", "final"]
    assert events[0]["content"] == "流式"
    assert events[-1]["trace_id"].startswith("trace_")
    assert agent.stream_calls[0]["role"] == "employee"
