from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """API /query 请求体。"""

    question: str = Field(description="用户问题")
    use_agent: bool = Field(default=True, description="是否使用 Agent 版本；false 时使用普通 RAG Chain")
    session_id: str | None = Field(default=None, description="多轮会话 ID；为空时不保存会话")
    retrieval_mode: str | None = Field(default=None, description="检索模式：hybrid 或 vector")
    enable_rerank: bool | None = Field(default=None, description="是否启用 Qwen rerank；为空时使用配置默认值")


class QueryResponse(BaseModel):
    """API /query 响应体。"""

    answer: str
    trace: dict
    sources: list[dict] | None = None
    retrieval_trace: dict | None = None
    tool_events: list[dict] | None = None
    route: str | None = None
    workflow_run_id: str | None = None
    checkpoint_thread_id: str | None = None
    node_trace: list[dict] | None = None
    trace_path: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    ok: bool
    message: str
