from __future__ import annotations

"""FastAPI Gateway for Mini Enterprise RAG Agent.

P0 engineering goals implemented here:
- Keep legacy ``/query`` for compatibility.
- Add production-style ``/chat`` with API-key authentication and role metadata.
- Reuse heavy Agent/RAG objects instead of constructing them per request.
- Save trace_id-based raw traces and expose a readable ``/traces/{trace_id}`` API.
"""

import time
import json
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from mini_rag.api.schemas import (
    AuditListResponse,
    ChatRequest,
    ChatResponse,
    EvalRunRequest,
    EvalRunResponse,
    KnowledgeBaseListResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RolePolicyListResponse,
    RolePolicyUpdateRequest,
    ToolListResponse,
    TraceResponse,
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
)
from mini_rag.config import Settings, get_settings
from mini_rag.observability.trace import save_trace
from mini_rag.observability.audit_logger import read_recent_audit_events, write_audit_event
from mini_rag.observability.request_logger import RequestLoggerMiddleware
from mini_rag.observability.trace_store import build_readable_trace, extract_latest_retrieval_trace, load_trace
from mini_rag.schemas import HealthResponse, QueryRequest, QueryResponse
from mini_rag.security.auth_store import AuthUser, SQLiteAuthStore
from mini_rag.security.permissions import TOOL_PERMISSIONS, check_endpoint_permission, get_allowed_kbs, knowledge_base_permission_summary, normalize_role
from mini_rag.security.safety import looks_dangerous
from mini_rag.tools.office_tools import build_default_tool_registry

app = FastAPI(
    title="Mini Enterprise RAG Agent",
    description="Agentic RAG + FastAPI Gateway + Auth + Trace for interview-ready Agent Infra demos",
    version="0.2.0",
)

settings = get_settings()
app.add_middleware(RequestLoggerMiddleware, settings=settings)

FRONTEND_DIR = Path("frontend")
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")


@app.get("/", include_in_schema=False)
def frontend_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Mini Enterprise RAG Agent", "ui": "/ui"}

# Lazily initialized singletons. We do not build LLM/retriever at import time,
# because docs/tests may import the FastAPI app without model credentials. The
# first real request creates each object once and later requests reuse it.
_AGENT_INSTANCE: object | None = None
_RAG_INSTANCE: object | None = None


def get_agent() -> object:
    """Return a process-level Agent singleton.

    Creating the Agent can initialize model clients, retrievers and vector-store
    handles. Doing that per request wastes latency and makes performance harder
    to reason about. A singleton is enough for this local demo; in production the
    same principle would be implemented with FastAPI lifespan + DI container.
    """

    global _AGENT_INSTANCE
    if _AGENT_INSTANCE is None:
        # Lazy import keeps /health, auth tests and documentation tooling usable
        # even before optional LangChain runtime dependencies are installed.
        from mini_rag.agent.agent import EnterpriseKnowledgeAgent

        _AGENT_INSTANCE = EnterpriseKnowledgeAgent(settings)
    return _AGENT_INSTANCE


def get_rag_chain() -> object:
    """Return a process-level plain RAG chain singleton for legacy /query."""

    global _RAG_INSTANCE
    if _RAG_INSTANCE is None:
        from mini_rag.rag.chain import RAGQuestionAnswerer

        _RAG_INSTANCE = RAGQuestionAnswerer(settings)
    return _RAG_INSTANCE


def get_auth_store() -> SQLiteAuthStore:
    return SQLiteAuthStore(settings.auth_db_path)


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


def require_current_user(token: str = Depends(bearer_token)) -> AuthUser:
    user = get_auth_store().authenticate_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return user


def require_admin_user(user: AuthUser = Depends(require_current_user)) -> AuthUser:
    decision = check_endpoint_permission(user.role, "admin_kbs")
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


def auth_summary(user: AuthUser) -> dict[str, Any]:
    policies = get_auth_store().list_role_policies()
    policy = policies.get(user.role)
    kb_summary = knowledge_base_permission_summary(user.role, role_policies=policies)
    return {
        "username": user.username,
        "role": user.role,
        "allowed_kbs": get_allowed_kbs(user.role, role_policies=policies),
        "allowed_tools": policy.allowed_tools if policy else [],
        "knowledge_bases": kb_summary["knowledge_bases"],
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Service health check.

    Kept unauthenticated because health checks are typically called by local
    scripts, load balancers or orchestration systems.
    """

    return HealthResponse(ok=True, message="Mini Enterprise RAG Agent is running")


@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    result = get_auth_store().login(req.username, req.password)
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return LoginResponse(
        access_token=result.access_token,
        username=result.user.username,
        role=result.user.role,
    )


@app.get("/auth/me", response_model=MeResponse)
def me(user: AuthUser = Depends(require_current_user)) -> MeResponse:
    return MeResponse(**auth_summary(user))


@app.post("/auth/logout")
def logout(token: str = Depends(bearer_token)) -> dict[str, bool]:
    get_auth_store().logout(token)
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: AuthUser = Depends(require_current_user)) -> ChatResponse:
    """Production-style Agent chat endpoint.

    API Gateway responsibilities live here: request metadata, endpoint-level
    permission, trace_id creation, high-level safety block, Agent invocation,
    trace persistence and structured error response.
    """

    start = time.perf_counter()
    trace_id = f"trace_{uuid4().hex}"
    role = normalize_role(user.role)
    user_id = user.username

    endpoint_decision = check_endpoint_permission(role, "chat")
    if not endpoint_decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=endpoint_decision.reason)

    if looks_dangerous(req.query):
        latency_ms = int((time.perf_counter() - start) * 1000)
        trace = {
            "trace_id": trace_id,
            "user_id": user_id,
            "role": role,
            "question": req.query,
            "session_id": req.session_id,
            "requested_kbs": req.kb_ids or [],
            "used_kbs": [],
            "route": "reject",
            "risk_level": "high",
            "answer": "该请求可能涉及密钥、系统提示词或其他敏感信息，已被安全策略拒绝。",
            "error": None,
            "node_trace": [],
            "tool_calls": [],
            "observations": [{"type": "safety_block", "reason": "dangerous_keywords"}],
            "sources": [],
            "audit_events": [{"event": "safety_block", "decision": "blocked", "reason": "dangerous_keywords"}],
            "total_latency_ms": latency_ms,
        }
        save_trace(settings, trace)
        write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, "event": "safety_block", "decision": "blocked", "reason": "dangerous_keywords"})
        return ChatResponse(
            trace_id=trace_id,
            answer=trace["answer"],
            route="reject",
            used_kbs=[],
            audit_events=trace.get("audit_events", []),
            latency_ms=latency_ms,
            error=None,
        )

    try:
        result = get_agent().ask(
            req.query,
            session_id=req.session_id,
            retrieval_mode=req.retrieval_mode,
            enable_rerank=req.enable_rerank,
            user_id=user_id,
            role=role,
            trace_id=trace_id,
            kb_ids=req.kb_ids,
        )
        trace: dict[str, Any] = result["trace"]
        trace.setdefault("trace_id", trace_id)
        trace.setdefault("user_id", user_id)
        trace.setdefault("role", role)
        trace_path = save_trace(settings, trace)
        for event in trace.get("audit_events", []):
            write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, **event})
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ChatResponse(
            trace_id=trace_id,
            answer=result.get("answer", ""),
            route=result.get("route") or trace.get("route"),
            used_kbs=trace.get("used_kbs", []),
            sources=result.get("sources") or trace.get("sources", []),
            tool_calls=trace.get("tool_calls", []),
            retrieval_trace=extract_latest_retrieval_trace(trace),
            node_trace=trace.get("node_trace", []),
            audit_events=trace.get("audit_events", []),
            latency_ms=latency_ms,
            error=trace.get("error"),
        )
    except PermissionError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        trace = {
            "trace_id": trace_id,
            "user_id": user_id,
            "role": role,
            "question": req.query,
            "session_id": req.session_id,
            "requested_kbs": req.kb_ids or [],
            "used_kbs": [],
            "route": "reject",
            "risk_level": "medium",
            "answer": "",
            "error": str(exc),
            "node_trace": [],
            "tool_calls": [],
            "observations": [{"type": "permission_block", "reason": str(exc)}],
            "sources": [],
            "audit_events": [{"event": "permission_block", "decision": "blocked", "reason": str(exc)}],
            "total_latency_ms": latency_ms,
        }
        save_trace(settings, trace)
        write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, "event": "permission_block", "decision": "blocked", "reason": str(exc)})
        return ChatResponse(trace_id=trace_id, answer="", route="reject", used_kbs=[], audit_events=trace.get("audit_events", []), latency_ms=latency_ms, error=str(exc))
    except Exception as exc:
        # Do not leak stack traces to callers. The trace_id lets us find the raw
        # internal trace/log during debugging.
        latency_ms = int((time.perf_counter() - start) * 1000)
        trace = {
            "trace_id": trace_id,
            "user_id": user_id,
            "role": role,
            "question": req.query,
            "session_id": req.session_id,
            "requested_kbs": req.kb_ids or [],
            "used_kbs": [],
            "route": None,
            "answer": "",
            "error": str(exc),
            "node_trace": [],
            "tool_calls": [],
            "observations": [{"type": "exception", "error": str(exc)}],
            "sources": [],
            "audit_events": [{"event": "exception", "decision": "error", "reason": str(exc)}],
            "total_latency_ms": latency_ms,
        }
        save_trace(settings, trace)
        write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, "event": "exception", "decision": "error", "reason": str(exc)})
        return ChatResponse(trace_id=trace_id, answer="", route=None, used_kbs=[], audit_events=trace.get("audit_events", []), latency_ms=latency_ms, error=str(exc))


def ndjson_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, user: AuthUser = Depends(require_current_user)) -> StreamingResponse:
    def event_generator():
        start = time.perf_counter()
        trace_id = f"trace_{uuid4().hex}"
        role = normalize_role(user.role)
        user_id = user.username
        try:
            endpoint_decision = check_endpoint_permission(role, "chat")
            if not endpoint_decision.allowed:
                yield ndjson_event({"event": "error", "error": endpoint_decision.reason, "trace_id": trace_id})
                return

            if looks_dangerous(req.query):
                latency_ms = int((time.perf_counter() - start) * 1000)
                trace = {
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "role": role,
                    "question": req.query,
                    "session_id": req.session_id,
                    "requested_kbs": req.kb_ids or [],
                    "used_kbs": [],
                    "route": "reject",
                    "risk_level": "high",
                    "answer": "该请求可能涉及密钥、系统提示词或其他敏感信息，已被安全策略拒绝。",
                    "error": None,
                    "node_trace": [],
                    "tool_calls": [],
                    "observations": [{"type": "safety_block", "reason": "dangerous_keywords"}],
                    "sources": [],
                    "audit_events": [{"event": "safety_block", "decision": "blocked", "reason": "dangerous_keywords"}],
                    "total_latency_ms": latency_ms,
                }
                save_trace(settings, trace)
                write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, "event": "safety_block", "decision": "blocked", "reason": "dangerous_keywords"})
                yield ndjson_event({"event": "token", "content": trace["answer"]})
                yield ndjson_event({"event": "final", "trace_id": trace_id, "answer": trace["answer"], "route": "reject", "used_kbs": [], "sources": [], "tool_calls": [], "node_trace": [], "audit_events": trace["audit_events"], "latency_ms": latency_ms, "error": None})
                return

            final_payload: dict[str, Any] | None = None
            for event in get_agent().stream(
                req.query,
                session_id=req.session_id,
                retrieval_mode=req.retrieval_mode,
                enable_rerank=req.enable_rerank,
                user_id=user_id,
                role=role,
                trace_id=trace_id,
                kb_ids=req.kb_ids,
            ):
                event_name = event.get("event")
                if event_name == "token":
                    yield ndjson_event({"event": "token", "content": event.get("content", "")})
                elif event_name == "status":
                    yield ndjson_event({"event": "status", "stage": event.get("stage", ""), "message": event.get("message", "")})
                elif event_name == "final":
                    trace = dict(event.get("trace") or {})
                    trace.setdefault("trace_id", trace_id)
                    trace.setdefault("user_id", user_id)
                    trace.setdefault("role", role)
                    save_trace(settings, trace)
                    for audit_event in trace.get("audit_events", []):
                        write_audit_event(settings, {"trace_id": trace_id, "user_id": user_id, "role": role, **audit_event})
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    final_payload = {
                        "event": "final",
                        "trace_id": trace_id,
                        "answer": event.get("answer") or trace.get("answer", ""),
                        "route": event.get("route") or trace.get("route"),
                        "used_kbs": trace.get("used_kbs", []),
                        "sources": event.get("sources") or trace.get("sources", []),
                        "tool_calls": trace.get("tool_calls", []),
                        "retrieval_trace": extract_latest_retrieval_trace(trace),
                        "node_trace": trace.get("node_trace", []),
                        "audit_events": trace.get("audit_events", []),
                        "latency_ms": latency_ms,
                        "error": trace.get("error"),
                    }
                    yield ndjson_event(final_payload)
            if final_payload is None:
                yield ndjson_event({"event": "error", "trace_id": trace_id, "error": "stream ended without final event"})
        except Exception as exc:
            yield ndjson_event({"event": "error", "trace_id": trace_id if "trace_id" in locals() else "", "error": str(exc)})

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@app.get("/traces/{trace_id}", response_model=TraceResponse)
def get_trace(
    trace_id: str,
    user: AuthUser = Depends(require_current_user),
) -> TraceResponse:
    """Read a compact trace view by trace_id.

    Only admin can read traces because traces may contain user questions,
    snippets from internal documents and tool-call metadata.
    """

    endpoint_decision = check_endpoint_permission(user.role, "trace")
    if not endpoint_decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=endpoint_decision.reason)

    loaded = load_trace(settings, trace_id)
    if loaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trace not found: {trace_id}")
    trace, path = loaded
    return TraceResponse(**build_readable_trace(trace, raw_trace_path=str(path)))


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Legacy enterprise knowledge QA endpoint.

    This endpoint remains unauthenticated for backward compatibility with the
    original teaching scripts. New demos and interviews should use ``/chat``.
    """

    if req.use_agent:
        result = get_agent().ask(
            req.question,
            session_id=req.session_id,
            retrieval_mode=req.retrieval_mode,
            enable_rerank=req.enable_rerank,
            user_id="legacy-query",
            role="user",
        )
        trace = result["trace"]
        trace_path = save_trace(settings, trace)
        return QueryResponse(
            answer=result["answer"],
            trace=trace,
            sources=result.get("sources"),
            retrieval_trace=extract_latest_retrieval_trace(trace),
            tool_events=trace.get("tool_events", trace.get("observations", [])),
            route=result.get("route") or trace.get("route"),
            workflow_run_id=result.get("workflow_run_id"),
            checkpoint_thread_id=result.get("checkpoint_thread_id"),
            node_trace=trace.get("node_trace", []),
            trace_path=str(trace_path) if trace_path else None,
        )

    result = get_rag_chain().ask(
        req.question,
        retrieval_mode=req.retrieval_mode,
        enable_rerank=req.enable_rerank,
    )
    trace = result["trace"]
    trace_path = save_trace(settings, trace)
    return QueryResponse(
        answer=result["answer"],
        trace=trace,
        sources=result.get("sources"),
        retrieval_trace=trace.get("retrieval"),
        tool_events=[],
        route=None,
        workflow_run_id=None,
        checkpoint_thread_id=None,
        node_trace=None,
        trace_path=str(trace_path) if trace_path else None,
    )


@app.get("/admin/kbs", response_model=KnowledgeBaseListResponse)
def list_kbs(user: AuthUser = Depends(require_admin_user)) -> KnowledgeBaseListResponse:
    summary = knowledge_base_permission_summary(user.role, role_policies=get_auth_store().list_role_policies())
    return KnowledgeBaseListResponse(kbs=summary["knowledge_bases"])


@app.get("/admin/tools", response_model=ToolListResponse)
def list_tools(user: AuthUser = Depends(require_admin_user)) -> ToolListResponse:
    registry_tools = {tool["name"]: tool for tool in build_default_tool_registry().list_tools()}
    tools = []
    for name in sorted(TOOL_PERMISSIONS):
        item = dict(registry_tools.get(name) or {"name": name, "description": "系统内部工具", "risk_level": "low"})
        item["default_roles"] = TOOL_PERMISSIONS.get(name, [])
        tools.append(item)
    return ToolListResponse(tools=tools)


@app.get("/admin/audit", response_model=AuditListResponse)
def list_audit(limit: int = Query(default=50, ge=1, le=200), user: AuthUser = Depends(require_admin_user)) -> AuditListResponse:
    return AuditListResponse(items=read_recent_audit_events(settings, limit=limit))


@app.get("/admin/users", response_model=UserListResponse)
def list_users(user: AuthUser = Depends(require_admin_user)) -> UserListResponse:
    return UserListResponse(users=get_auth_store().list_users())


@app.post("/admin/users", response_model=MeResponse)
def create_user(req: UserCreateRequest, user: AuthUser = Depends(require_admin_user)) -> MeResponse:
    try:
        created = get_auth_store().create_user(req.username, req.password, req.role, enabled=req.enabled)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    write_audit_event(settings, {"user_id": user.username, "role": user.role, "event": "admin_user_create", "target_user": created.username, "target_role": created.role, "decision": "allowed"})
    return MeResponse(**auth_summary(created))


@app.patch("/admin/users/{username}", response_model=MeResponse)
def update_user(username: str, req: UserUpdateRequest, user: AuthUser = Depends(require_admin_user)) -> MeResponse:
    updated = get_auth_store().update_user(username, role=req.role, enabled=req.enabled, password=req.password)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User not found: {username}")
    write_audit_event(settings, {"user_id": user.username, "role": user.role, "event": "admin_user_update", "target_user": updated.username, "target_role": updated.role, "target_enabled": updated.enabled, "decision": "allowed"})
    return MeResponse(**auth_summary(updated))


@app.get("/admin/roles", response_model=RolePolicyListResponse)
def list_roles(user: AuthUser = Depends(require_admin_user)) -> RolePolicyListResponse:
    policies = get_auth_store().list_role_policies()
    return RolePolicyListResponse(
        roles=[
            {"role": policy.role, "allowed_kbs": policy.allowed_kbs, "allowed_tools": policy.allowed_tools}
            for policy in policies.values()
        ]
    )


@app.patch("/admin/roles", response_model=RolePolicyListResponse)
def update_role_policy(req: RolePolicyUpdateRequest, user: AuthUser = Depends(require_admin_user)) -> RolePolicyListResponse:
    try:
        policy = get_auth_store().update_role_policy(req.role, req.allowed_kbs, req.allowed_tools)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    write_audit_event(settings, {"user_id": user.username, "role": user.role, "event": "admin_role_policy_update", "target_role": policy.role, "allowed_kbs": policy.allowed_kbs, "allowed_tools": policy.allowed_tools, "decision": "allowed"})
    return list_roles(user)

@app.post("/eval/run", response_model=EvalRunResponse)
def run_eval_endpoint(
    req: EvalRunRequest,
    user: AuthUser = Depends(require_current_user),
) -> EvalRunResponse:
    """Run a secured local evaluation job.

    This is deliberately admin-only because eval may be expensive and can read
    internal knowledge-base snippets through normal RAG execution. The endpoint
    is useful in interviews: it proves the project has a quality feedback loop,
    not only a happy-path demo question.
    """

    endpoint_decision = check_endpoint_permission(user.role, "eval")
    if not endpoint_decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=endpoint_decision.reason)

    try:
        if req.mode == "retrieval_ablation":
            from mini_rag.evaluation.retrieval_ablation import run_retrieval_ablation

            report = run_retrieval_ablation(settings, questions_path=req.questions_path)
            # Return mode-level metrics in a compact shape; detailed rows live in the saved report.
            metrics = {item["mode"]: item["metrics"] for item in report.get("modes", [])}
            return EvalRunResponse(
                mode=req.mode,
                question_count=int(report.get("question_count") or 0),
                metrics=metrics,
                output_path=report.get("output_json_path"),
                output_md_path=report.get("output_md_path"),
            )

        from mini_rag.eval import run_eval

        report = run_eval(settings, questions_path=req.questions_path)
        return EvalRunResponse(
            mode=req.mode,
            question_count=int(report.get("question_count") or 0),
            metrics={
                "recall_at_k": report.get("recall_at_k"),
                "citation_hit_rate": report.get("citation_hit_rate"),
                "refusal_hit_rate": report.get("refusal_hit_rate"),
                "avg_latency_ms": report.get("avg_latency_ms"),
                "p95_latency_ms": report.get("p95_latency_ms"),
            },
            output_path=report.get("output_path"),
            output_md_path=report.get("output_md_path"),
        )
    except Exception as exc:
        return EvalRunResponse(mode=req.mode, question_count=0, metrics={}, error=str(exc))
