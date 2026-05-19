from __future__ import annotations

"""HTTP API schemas for Agent Gateway."""

from typing import Any, Literal

from pydantic import BaseModel, Field


Role = Literal["guest", "public", "user", "employee", "finance", "hr", "it", "admin"]
Route = Literal["direct", "rag", "tool", "reject"]


class ChatRequest(BaseModel):
    """Request body for /chat."""

    user_id: str | None = Field(default=None, description="兼容旧客户端；服务端实际使用登录用户 ID")
    role: Role | None = Field(default=None, description="兼容旧客户端；服务端实际使用登录用户角色")
    query: str = Field(..., min_length=1, description="用户原始问题")
    session_id: str | None = Field(default=None, description="多轮会话 ID；为空时不保存会话")
    kb_ids: list[str] | None = Field(default=None, description="请求访问的知识库；为空则使用该角色可访问的全部知识库")
    stream: bool = Field(default=False, description="是否请求流式输出；当前版本返回非流式响应")
    retrieval_mode: Literal["hybrid", "vector"] | None = Field(default=None, description="检索模式")
    enable_rerank: bool | None = Field(default=None, description="是否启用 rerank；为空时使用配置默认值")
    override_now: str | None = Field(default=None, description="可选请求级固定时间，仅用于评测或可复现调试")


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    route: str | None = None
    used_kbs: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_trace: dict[str, Any] | None = None
    node_trace: list[dict[str, Any]] = Field(default_factory=list)
    mainline_log: list[dict[str, Any]] = Field(default_factory=list)
    mainline_log_text: str = ""
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    message: str


class TraceStep(BaseModel):
    node: str
    latency_ms: float | int | None = None
    status: str = "ok"
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class TraceResponse(BaseModel):
    trace_id: str
    user_id: str | None = None
    role: str | None = None
    session_id: str | None = None
    query: str | None = None
    route: str | None = None
    total_latency_ms: float | int | None = None
    used_kbs: list[str] = Field(default_factory=list)
    steps: list[TraceStep] = Field(default_factory=list)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    mainline_log: list[dict[str, Any]] = Field(default_factory=list)
    mainline_log_text: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    raw_trace_path: str | None = None


class EvalRunRequest(BaseModel):
    questions_path: str | None = Field(default=None, description="Optional JSONL question file path")
    mode: Literal["rag_eval", "retrieval_ablation"] = Field(
        default="rag_eval",
        description="Deprecated API modes. Use scripts/agent_eval_suite.py for the current evaluation mainline.",
    )


class EvalRunResponse(BaseModel):
    mode: str
    question_count: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None
    output_md_path: str | None = None
    error: str | None = None


class KnowledgeBaseListResponse(BaseModel):
    kbs: list[dict[str, Any]]


class KnowledgeBaseDocumentImportRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="写入 data/kbs/<kb_id>/ 下的文件名，支持 .md/.markdown/.txt")
    content: str = Field(..., min_length=1, description="Markdown/text 文档内容")
    overwrite: bool = Field(default=False, description="同名文件存在时是否覆盖")


class KnowledgeBaseDocumentResponse(BaseModel):
    document: dict[str, Any]


class KnowledgeBaseReindexRequest(BaseModel):
    reset: bool = Field(default=False, description="是否清空 Chroma 和 manifest 后重建")


class KnowledgeBaseReindexResponse(BaseModel):
    result: dict[str, Any]


class ToolListResponse(BaseModel):
    tools: list[dict[str, Any]]


class AuditListResponse(BaseModel):
    items: list[dict[str, Any]]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class MeResponse(BaseModel):
    username: str
    role: str
    allowed_kbs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[dict[str, Any]] = Field(default_factory=list)


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: Role = "employee"
    enabled: bool = True


class UserUpdateRequest(BaseModel):
    role: Role | None = None
    enabled: bool | None = None
    password: str | None = None


class UserListResponse(BaseModel):
    users: list[dict[str, Any]]


class RolePolicyUpdateRequest(BaseModel):
    role: Role
    allowed_kbs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class RolePolicyListResponse(BaseModel):
    roles: list[dict[str, Any]]
