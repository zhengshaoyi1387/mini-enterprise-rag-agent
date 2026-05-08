from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from mini_rag.config import Settings


def build_qwen_chat_model(settings: Settings, model: str | None = None) -> ChatOpenAI:
    """构造 Qwen 聊天模型。

    关键点：
    - 阿里云百炼支持 OpenAI 兼容接口。
    - LangChain 的 ChatOpenAI 可以通过 `base_url` 指向兼容接口。
    - API Key 使用 DASHSCOPE_API_KEY。

    新手提示：
    你可以把这个函数理解成“把 Qwen 包装成 LangChain 能调用的聊天模型”。
    """
    return ChatOpenAI(
        model=model or settings.qwen_chat_model,
        api_key=settings.require_api_key(),
        base_url=settings.qwen_base_url,
        temperature=settings.temperature,
    )


def build_qwen_control_model(settings: Settings) -> ChatOpenAI:
    """构造控制节点模型。

    默认使用最终回答同款模型，保持质量优先；如需提速，可通过 QWEN_CONTROL_MODEL
    只替换理解、路由、规划、反思等短 JSON 节点。
    """
    return build_qwen_chat_model(settings, model=settings.qwen_control_model or settings.qwen_chat_model)


def build_qwen_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """构造 Qwen / 百炼文本向量模型。

    text-embedding-v4 属于 Qwen3-Embedding 系列，接口也支持 OpenAI 兼容模式。
    LangChain 的 OpenAIEmbeddings 同样可以通过 base_url 调用兼容接口。
    """
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
        # 注意：这里不强行指定 dimensions。
        # text-embedding-v4 默认维度通常够用；如果你需要降维，可以在后续版本加配置。
    )
