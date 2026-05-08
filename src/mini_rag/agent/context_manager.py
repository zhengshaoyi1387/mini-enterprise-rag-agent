from __future__ import annotations

from dataclasses import dataclass, field
import re

from mini_rag.agent.context_store import ConversationTurn
from mini_rag.agent.llm_json import message_content, parse_json_object
from mini_rag.prompts import CONTEXT_MANAGER_SYSTEM_PROMPT, format_context_manager_user_prompt


@dataclass
class ManagedContext:
    """LLM 上下文管理节点的结构化输出。"""

    updated_summary: str
    selected_history: list[ConversationTurn]
    standalone_query: str
    context_reason: str
    raw_response: str = ""
    fallback_used: bool = False
    resolved_entities: list[str] = field(default_factory=list)
    resolved_topic: str = ""


def manage_context(
    llm,
    question: str,
    history: list[ConversationTurn],
    old_summary: str,
) -> ManagedContext:
    """管理多轮上下文。

    关键设计：上下文管理只做“是否需要历史 + 指代消解”。
    - 当前问题不依赖历史时，直接返回原问题，避免无意义 LLM 调用和历史污染。
    - 当前问题依赖历史时，优先用代码从干净历史中解析实体列表。
    - 只有没有明确实体列表时，才允许采用 LLM 给出的保守 standalone_query。

    这样可以避免把“介绍一下”扩写成用户没有要求的“业务价值/白皮书/典型场景”，
    也避免把引用来源里的 source/title_path/chunk_id 当成业务实体。
    """
    if not is_context_dependent_question(question):
        return ManagedContext(
            updated_summary=old_summary,
            selected_history=[],
            standalone_query=compact_line(question, 300),
            context_reason="当前问题不依赖历史，直接使用原问题。",
            fallback_used=False,
            resolved_entities=[],
            resolved_topic="",
        )

    messages = [
        {"role": "system", "content": CONTEXT_MANAGER_SYSTEM_PROMPT},
        {"role": "user", "content": format_context_manager_user_prompt(question, history, old_summary)},
    ]

    raw = message_content(llm.invoke(messages))
    payload = parse_json_object(raw)
    if not payload:
        return fallback_context(question, history, old_summary, raw)

    selected_indexes = payload.get("selected_turn_indexes", [])
    selected_history: list[ConversationTurn] = []
    if isinstance(selected_indexes, list):
        for index in selected_indexes[:3]:
            if isinstance(index, int) and 0 <= index < len(history):
                selected_history.append(history[index])

    selected_history = selected_history or choose_history_for_question(question, history)
    resolved = resolve_question_from_history(question, selected_history, old_summary)
    llm_query = str(payload.get("standalone_query") or "").strip()
    standalone_query = choose_safe_standalone_query(
        question=question,
        llm_query=llm_query,
        resolved_query=resolved["standalone_query"],
        has_entities=bool(resolved["entities"]),
    )
    return ManagedContext(
        updated_summary=str(payload.get("updated_summary") or old_summary),
        selected_history=selected_history,
        standalone_query=standalone_query,
        context_reason=str(payload.get("context_reason") or resolved["reason"]),
        raw_response=raw,
        fallback_used=False,
        resolved_entities=resolved["entities"],
        resolved_topic=resolved["topic"],
    )


def format_context_prompt(question: str, history: list[ConversationTurn], old_summary: str) -> str:
    return format_context_manager_user_prompt(question, history, old_summary)


def fallback_context(question: str, history: list[ConversationTurn], old_summary: str, raw: str = "") -> ManagedContext:
    selected = choose_history_for_question(question, history)
    resolved = resolve_question_from_history(question, selected, old_summary)
    return ManagedContext(
        updated_summary=old_summary,
        selected_history=selected,
        standalone_query=resolved["standalone_query"],
        context_reason="LLM 上下文 JSON 解析失败，使用代码兜底消解指代。",
        raw_response=raw,
        fallback_used=True,
        resolved_entities=resolved["entities"],
        resolved_topic=resolved["topic"],
    )


def choose_history_for_question(question: str, history: list[ConversationTurn]) -> list[ConversationTurn]:
    """只有当前问题确实依赖上下文时，才携带历史。"""
    if not history:
        return []
    if is_context_dependent_question(question):
        return history[-3:]
    return []


def resolve_question_from_history(question: str, selected_history: list[ConversationTurn], summary: str = "") -> dict:
    """把追问解析成干净的独立问题。

    返回值包括：
    - standalone_query：给 Router / 检索规划使用的干净问题。
    - entities：从历史列表中解析出的对象，供多对象检索直接使用。
    - topic：对象所属主题，例如“智能客服平台”。
    """
    question = compact_line(question, 300)
    if not selected_history or not is_context_dependent_question(question):
        return {"standalone_query": question, "entities": [], "topic": "", "reason": "当前问题不依赖历史。"}

    last_turn = selected_history[-1]
    entities = extract_entities_from_turns(selected_history)
    entities = select_entities_by_question(question, entities)
    topic = infer_topic(last_turn, summary)

    if entities:
        action = infer_action(question)
        topic_part = f"{topic}的" if topic else ""
        return {
            "standalone_query": f"{action}{topic_part}以下对象：{'、'.join(entities)}",
            "entities": entities,
            "topic": topic,
            "reason": "从相关历史中解析出被指代的对象列表。",
        }

    # 没有解析出明确列表时，保守拼接最短上下文，而不是塞入完整历史答案。
    history_hint = compact_line(summary or last_turn.standalone_query or last_turn.question, 120)
    return {
        "standalone_query": f"围绕“{history_hint}”，{question}",
        "entities": [],
        "topic": topic,
        "reason": "未解析出明确对象，使用上一轮主题作为短上下文。",
    }


def choose_safe_standalone_query(question: str, llm_query: str, resolved_query: str, has_entities: bool) -> str:
    """在 LLM 改写和代码保守改写之间选择更安全的 standalone_query。

    多实体追问优先用代码解析结果，避免 LLM 擅自增加业务价值、案例、白皮书等维度。
    非实体类短追问可以采用 LLM 的补全结果，但必须短、干净、不是原样复读。
    """
    question = compact_line(question, 300)
    llm_query = compact_line(llm_query, 180)
    resolved_query = compact_line(resolved_query or question, 300)
    if has_entities:
        return resolved_query
    if is_safe_llm_query(question, llm_query):
        return llm_query
    return resolved_query


def is_safe_llm_query(question: str, llm_query: str) -> bool:
    if not llm_query or llm_query == question:
        return False
    if len(llm_query) > 160:
        return False
    expansion_terms = ["业务价值", "典型场景", "使用场景", "白皮书", "系统功能说明书", "最新版", "量化", "案例", "第3章"]
    for term in expansion_terms:
        if term in llm_query and term not in question:
            return False
    return True

def is_context_dependent_question(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    reference_words = [
        "这个", "这些", "那个", "那些", "它", "它们", "他们", "上述", "上面", "前面",
        "前三", "前两", "前几个", "后几", "第一个", "第二个", "第三个", "继续", "展开", "分别",
        "什么版本", "哪个版本", "版本号", "多少版本", "什么型号",
    ]
    if any(word in text for word in reference_words):
        return True
    # “发票呢？”“什么版本的”这类极短追问没有明确主语，也需要历史。
    return len(text) <= 8 and text.endswith(("呢", "的", "？", "?"))


def extract_entities_from_turns(turns: list[ConversationTurn]) -> list[str]:
    entities: list[str] = []
    for turn in turns:
        entities.extend(extract_list_items(turn.answer))
        entities.extend(extract_list_items(turn.standalone_query))
    return dedupe_strings(entities)


def strip_citation_and_metadata(text: str) -> str:
    """去掉引用来源和 trace 元数据，避免把 source/title_path/chunk_id 抽成业务实体。"""
    raw = str(text or "")
    cut_markers = ["引用来源", "引用：", "Trace 已保存", "source:", "title_path:", "chunk_id:"]
    cut_positions = [raw.find(marker) for marker in cut_markers if raw.find(marker) >= 0]
    if cut_positions:
        raw = raw[: min(cut_positions)]

    kept: list[str] = []
    metadata_line = re.compile(
        r"^\s*(?:[-*+]\s*)?(?:source|title[_ ]?path|chunk[_ ]?id|vector[_ ]?score|bm25[_ ]?score|rerank[_ ]?score|rank|preview)\s*[:：]",
        re.IGNORECASE,
    )
    for line in raw.splitlines():
        if metadata_line.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def extract_list_items(text: str) -> list[str]:
    """从上一轮回答中提取项目列表，兼容 Markdown 列表和压缩成一行的列表。"""
    raw = strip_citation_and_metadata(text)
    items: list[str] = []

    # 多行 Markdown：- 在线会话 / 1. 在线会话：...
    for line in raw.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[-*+]|\d+[.、)])\s+(.+)$", stripped)
        if match:
            item = clean_entity_label(match.group(1))
            if is_valid_entity_label(item):
                items.append(item)

    # 一行压缩列表：... - 在线会话 - 工单管理 - 知识库管理 ...
    for match in re.finditer(r"(?:^|\s)-\s*([^\n-]{1,60}?)(?=\s+-\s+|$)", raw):
        item = clean_entity_label(match.group(1))
        if is_valid_entity_label(item):
            items.append(item)

    return dedupe_strings(items)


def clean_entity_label(text: str) -> str:
    item = re.sub(r"[*`#]", "", str(text or "")).strip()
    item = re.split(r"[:：。；;，,（(]", item, maxsplit=1)[0].strip()
    # 上一轮回答常写成“一行列表 + 以上列表...”，最后一个项目后面可能跟解释文字。
    for marker in ["以上", "均", "都", "等"]:
        if marker in item and item.index(marker) > 0:
            item = item.split(marker, 1)[0].strip()
    return item.strip(" -•\t")


def is_valid_entity_label(item: str) -> bool:
    if not item or len(item) > 24:
        return False
    lowered = item.lower().strip()
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", lowered)
    blocked = [
        "source", "titlepath", "chunkid", "vectorscore", "bm25score", "rerankscore",
        "rank", "preview", "trace", "引用", "来源", "引用来源", "证据评估", "当前证据",
    ]
    if any(word in normalized for word in blocked):
        return False
    # 过滤明显不是业务实体的说明性短语。
    if any(word in item for word in ["当前证据", "已有证据", "不足", "引用", "来源"]):
        return False
    return True


def select_entities_by_question(question: str, entities: list[str]) -> list[str]:
    if not entities:
        return []
    text = str(question or "")
    number = parse_chinese_number(text)
    if "前" in text and number:
        return entities[:number]
    if "后" in text and number:
        return entities[-number:]
    ordinal = parse_ordinal(text)
    if ordinal and 1 <= ordinal <= len(entities):
        return [entities[ordinal - 1]]
    return entities


def parse_chinese_number(text: str) -> int | None:
    mapping = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    digit = re.search(r"[前后](\d+)", text)
    if digit:
        return int(digit.group(1))
    for char, value in mapping.items():
        if f"前{char}" in text or f"后{char}" in text:
            return value
    return None


def parse_ordinal(text: str) -> int | None:
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    digit = re.search(r"第(\d+)", text)
    if digit:
        return int(digit.group(1))
    for char, value in mapping.items():
        if f"第{char}" in text:
            return value
    return None


def infer_action(question: str) -> str:
    text = str(question or "")
    if "比较" in text or "区别" in text:
        return "比较"
    if "解释" in text or "说明" in text or "介绍" in text:
        return "介绍"
    if "总结" in text:
        return "总结"
    return "回答关于"


def infer_topic(turn: ConversationTurn, summary: str = "") -> str:
    candidates = [turn.standalone_query, turn.question, summary]
    for candidate in candidates:
        text = compact_line(candidate, 100)
        for suffix in ["包含哪些核心模块", "有哪些核心模块", "包含哪些模块", "有哪些模块", "是什么"]:
            if suffix in text:
                return text.split(suffix, 1)[0].strip(" ：:，,")
    return ""


def compact_line(text: str, max_chars: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result
