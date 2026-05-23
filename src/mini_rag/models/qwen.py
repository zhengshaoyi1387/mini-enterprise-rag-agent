from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from mini_rag.config import Settings


def model_name_for(settings: Settings, purpose: str) -> str:
    purpose_key = str(purpose or "").strip().lower()
    if purpose_key == "planner":
        return settings.planner_model or settings.qwen_control_model or settings.qwen_chat_model
    if purpose_key == "rag_judge":
        return settings.rag_judge_model or settings.qwen_control_model or settings.qwen_chat_model
    if purpose_key == "rag_reflect":
        return settings.rag_reflect_model or settings.qwen_control_model or settings.qwen_chat_model
    if purpose_key == "answer":
        return settings.answer_model or settings.qwen_chat_model
    if purpose_key == "control":
        return settings.qwen_control_model or settings.qwen_chat_model
    return settings.qwen_chat_model


def build_qwen_chat_model(settings: Settings, model: str | None = None, *, max_tokens: int | None = None) -> ChatOpenAI:
    """构造 Qwen 聊天模型。

    关键点：
    - 阿里云百炼支持 OpenAI 兼容接口。
    - LangChain 的 ChatOpenAI 可以通过 `base_url` 指向兼容接口。
    - API Key 使用 DASHSCOPE_API_KEY。
    """
    return ChatOpenAI(
        model=model or settings.qwen_chat_model,
        api_key=settings.require_api_key(),
        base_url=settings.qwen_base_url,
        temperature=settings.temperature,
        max_tokens=max_tokens,
    )


def build_qwen_control_model(settings: Settings) -> ChatOpenAI:
    """构造默认控制节点模型。"""
    return build_qwen_chat_model(settings, model=model_name_for(settings, "control"))


def build_qwen_planner_model(settings: Settings) -> ChatOpenAI:
    """构造 Planner 模型；默认继承控制模型以保持行为稳定。"""
    return build_qwen_chat_model(
        settings,
        model=model_name_for(settings, "planner"),
        max_tokens=settings.planner_max_tokens,
    )


def build_qwen_rag_judge_model(settings: Settings) -> ChatOpenAI:
    """构造 RAG Evidence Judge 模型；可独立切换为更快模型。"""
    return build_qwen_chat_model(
        settings,
        model=model_name_for(settings, "rag_judge"),
    )


def build_qwen_rag_reflect_model(settings: Settings) -> ChatOpenAI:
    """构造 RAG Reflect 模型；可独立切换为更快模型。"""
    return build_qwen_chat_model(
        settings,
        model=model_name_for(settings, "rag_reflect"),
    )


def build_qwen_answer_model(settings: Settings) -> ChatOpenAI:
    """构造最终回答模型；默认继承 QWEN_CHAT_MODEL。"""
    return build_qwen_chat_model(settings, model=model_name_for(settings, "answer"))


def build_qwen_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """构造 Qwen / 百炼文本向量模型。"""
    return OpenAIEmbeddings(
        model=settings.qwen_embedding_model,
        api_key=settings.require_api_key(),
        base_url=settings.qwen_base_url,
        # DashScope 的 OpenAI 兼容 embedding 接口要求 input.contents 是 str 或 list[str]。
        # langchain_openai 默认会为了官方 OpenAI 接口做上下文长度检查，并可能把文本切成 token id 列表。
        # token id 列表发到 DashScope 会触发：
        # "contents is neither str nor list of str.: input.contents"
        # 所以这里显式关闭 token 化路径，让请求保持原始字符串列表。
        check_embedding_ctx_length=False,
        tiktoken_enabled=False,
    )
