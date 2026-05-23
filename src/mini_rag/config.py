from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目统一配置。

    新手提示：
    - 这里的字段大多可以通过 `.env` 文件覆盖。
    - 例如 `.env` 里写 `QWEN_CHAT_MODEL=qwen-turbo`，代码里就会自动读取。
    - 使用 BaseSettings 的好处是：代码里不需要到处写 os.getenv，配置更集中。
    """

    # pydantic-settings 会自动读取当前目录下的 .env 文件。
    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Agent Gateway API Key。FastAPI /chat 等服务接口会校验 X-API-Key。
    # 开发环境给默认值是为了本地 curl/pytest 方便；生产环境必须用环境变量覆盖。
    agent_api_key: str = Field(default="dev-api-key", alias="AGENT_API_KEY")

    # DashScope / 百炼 API Key。
    # 注意：这里没有默认值，避免你忘记配置 key 还以为代码能正常调用模型。
    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")

    # Qwen OpenAI 兼容模式 base_url。中国内地北京地域默认是这个地址。
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="QWEN_BASE_URL",
    )

    # 聊天模型，默认用于最终回答；你也可以改成 qwen-turbo / qwen-plus / qwen-max。
    qwen_chat_model: str = Field(default="qwen-max", alias="QWEN_CHAT_MODEL")
    # 控制节点模型：用于默认结构化 JSON 任务。
    qwen_control_model: str | None = Field(default="qwen-plus-2025-07-14", alias="QWEN_CONTROL_MODEL")
    # 分层模型配置。默认继承现有模型，确保不设置环境变量时行为不变；
    # 需要提速时可只把 Judge / Reflect 切到更快模型。
    planner_model: str | None = Field(default=None, alias="PLANNER_MODEL")
    rag_judge_model: str | None = Field(default=None, alias="RAG_JUDGE_MODEL")
    rag_reflect_model: str | None = Field(default=None, alias="RAG_REFLECT_MODEL")
    answer_model: str | None = Field(default=None, alias="ANSWER_MODEL")
    planner_max_tokens: int = Field(default=512, alias="PLANNER_MAX_TOKENS")

    # 向量模型。text-embedding-v4 属于 Qwen3-Embedding 系列。
    qwen_embedding_model: str = Field(default="text-embedding-v4", alias="QWEN_EMBEDDING_MODEL")

    # 原始文档目录。
    data_dir: Path = Field(default=Path("data/kbs"), alias="DATA_DIR")

    # Chroma 本地持久化目录。
    chroma_dir: Path = Field(default=Path("storage/chroma"), alias="CHROMA_DIR")

    # 增量索引 manifest，记录每个源文件对应的 chunk ids。
    index_manifest_path: Path = Field(default=Path("storage/index_manifest.json"), alias="INDEX_MANIFEST_PATH")

    # Chroma collection 名称。
    collection_name: str = Field(default="enterprise_kb", alias="COLLECTION_NAME")

    # Chunk 参数。中文文档里 700 字符左右通常比较适合作为起点。
    chunk_size: int = Field(default=700, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=120, alias="CHUNK_OVERLAP")

    # 检索参数。
    top_k: int = Field(default=3, alias="TOP_K")
    candidate_k: int = Field(default=8, alias="CANDIDATE_K")
    retrieval_mode: str = Field(default="hybrid", alias="RETRIEVAL_MODE")

    # Qwen Rerank 参数。默认关闭，避免错误 endpoint/额度问题拖慢主链路。
    # 需要评测证明有收益后再显式打开；外部失败时仍会自动降级到融合排序。
    rerank_enabled: bool = Field(default=False, alias="RERANK_ENABLED")
    qwen_rerank_model: str = Field(default="gte-rerank-v2", alias="QWEN_RERANK_MODEL")
    qwen_rerank_endpoint: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
        alias="QWEN_RERANK_ENDPOINT",
    )
    rerank_top_n: int = Field(default=3, alias="RERANK_TOP_N")
    rrf_k: int = Field(default=60, alias="RRF_K")

    session_max_turns: int = Field(default=6, alias="SESSION_MAX_TURNS")
    context_db_path: Path = Field(default=Path("storage/context.sqlite3"), alias="CONTEXT_DB_PATH")
    auth_db_path: Path = Field(default=Path("storage/auth.sqlite3"), alias="AUTH_DB_PATH")
    enterprise_db_path: Path = Field(default=Path("data/enterprise_demo.db"), alias="ENTERPRISE_DB_PATH")
    langgraph_checkpoint_db_path: Path = Field(
        default=Path("storage/langgraph_checkpoints.sqlite3"),
        alias="LANGGRAPH_CHECKPOINT_DB_PATH",
    )
    agent_max_steps: int = Field(default=10, alias="AGENT_MAX_STEPS")

    # Agentic RAG 性能参数。
    # - reflect_max_rounds 控制「检索 -> 反思 -> 补检索」最多循环次数。
    # - retrieval_workers 控制多 query 并发检索，减少多实体问题的总延迟。
    # - max_search_tasks 避免一次问题生成过多检索任务。
    # - entity_top_k/candidate_k 用于多实体解释类问题，减少每个实体的冗余证据。
    agent_reflect_max_rounds: int = Field(default=2, alias="AGENT_REFLECT_MAX_ROUNDS")
    agent_retrieval_workers: int = Field(default=4, alias="AGENT_RETRIEVAL_WORKERS")
    # 多个独立 RAG 子任务的 pipeline 并发数。只并发无依赖的 RAG 读任务；
    # 工具写操作仍由 ReActExecutor 串行执行。
    agent_parallel_rag_tasks: int = Field(default=3, alias="AGENT_PARALLEL_RAG_TASKS")
    agent_max_search_tasks: int = Field(default=3, alias="AGENT_MAX_SEARCH_TASKS")
    agent_max_followup_tasks: int = Field(default=2, alias="AGENT_MAX_FOLLOWUP_TASKS")
    agent_completion_max_replans: int = Field(default=2, alias="AGENT_COMPLETION_MAX_REPLANS")
    agent_enable_retrieval_cache: bool = Field(default=True, alias="AGENT_ENABLE_RETRIEVAL_CACHE")
    agent_entity_top_k: int = Field(default=2, alias="AGENT_ENTITY_TOP_K")
    agent_entity_candidate_k: int = Field(default=6, alias="AGENT_ENTITY_CANDIDATE_K")
    agent_evidence_char_limit: int = Field(default=2200, alias="AGENT_EVIDENCE_CHAR_LIMIT")

    # 评测配置。
    eval_questions_path: Path = Field(default=Path("eval/questions.jsonl"), alias="EVAL_QUESTIONS_PATH")
    eval_runs_dir: Path = Field(default=Path("eval/runs"), alias="EVAL_RUNS_DIR")
    fixed_now: str | None = Field(default=None, alias="AGENT_FIXED_NOW")

    # trace 日志配置。
    save_trace: bool = Field(default=True, alias="SAVE_TRACE")
    trace_dir: Path = Field(default=Path("logs/traces"), alias="TRACE_DIR")
    request_log_path: Path = Field(default=Path("logs/requests.jsonl"), alias="REQUEST_LOG_PATH")
    audit_log_path: Path = Field(default=Path("logs/audit.jsonl"), alias="AUDIT_LOG_PATH")

    # LLM 调试 trace。默认保存每次模型调用的完整 messages 和 raw output，
    # 用于定位 prompt 是否喂全、输出是否覆盖任务、哪些上下文没有用。
    # 生产环境可设 TRACE_LLM_IO=false 关闭；TRACE_LLM_IO_MAX_CHARS>0 时会截断超长字段。
    trace_llm_io: bool = Field(default=True, alias="TRACE_LLM_IO")
    trace_llm_io_max_chars: int = Field(default=0, alias="TRACE_LLM_IO_MAX_CHARS")

    # LLM 生成参数。temperature=0 更适合知识库问答，减少编造。
    temperature: float = Field(default=0.0, alias="TEMPERATURE")

    def require_api_key(self) -> str:
        """获取 API Key；如果没有配置就抛出友好错误。

        这里不直接在初始化时报错，是为了允许某些命令只做本地操作，
        例如查看配置、清理目录等。
        """
        if not self.dashscope_api_key:
            raise RuntimeError(
                "缺少 DASHSCOPE_API_KEY。请复制 .env.example 为 .env，并填写你的百炼 API Key。"
            )
        return self.dashscope_api_key


def get_settings() -> Settings:
    """获取配置对象。

    单独封装一个函数，是为了后续测试时更容易替换配置。
    """
    return Settings()
