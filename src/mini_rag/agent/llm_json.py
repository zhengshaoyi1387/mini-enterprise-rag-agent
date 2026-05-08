from __future__ import annotations

import json
import re
from typing import Any


def message_content(message: Any) -> str:
    """统一提取 LLM 返回文本。

    LangChain 的真实返回通常有 `.content`；
    单元测试里的 fake LLM 可能直接返回字符串或简单对象。
    这个函数把这些情况统一成 str。
    """
    content = getattr(message, "content", message)
    return str(content)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取 JSON object。

    LLM 偶尔会包一层 ```json 代码块或解释文字，所以这里先尝试直接解析，
    再退化为提取第一段 {...}。
    """
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return parse_json_object(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None
