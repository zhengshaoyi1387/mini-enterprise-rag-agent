from __future__ import annotations

"""Mock office tools for enterprise daily-use demos.

These tools intentionally generate drafts instead of executing real side effects.
That keeps the Agent safe while still showing enterprise Tool Calling ability.
"""

from typing import Any

from mini_rag.tools.registry import ToolRegistry


def generate_weekly_report(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    return {
        "content": f"""# 周报草稿

## 本周完成
- 根据你的描述整理本周重点工作。
- 跟进项目进展、风险和协作事项。
- 同步关键产出和阶段性结论。

## 下周计划
- 继续推进重点任务。
- 跟进未完成事项。
- 及时同步风险、阻塞和资源依赖。

## 风险与需要支持
- 待补充具体风险、负责人和期望支持。

原始需求：{query}
""".strip()
    }


def draft_email(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    return {
        "content": f"""邮件草稿：

主题：请补充邮件主题

你好，

根据当前需求，我整理如下：

{query}

如需我继续优化语气、压缩篇幅或改成正式通知格式，可以继续补充收件人和背景。

谢谢。
""".strip()
    }


def create_it_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    return {
        "content": f"""IT 工单草稿：

问题描述：
{query}

影响范围：
请补充影响的系统、设备、账号或人员范围。

紧急程度：
请补充 P0/P1/P2/P3 或期望处理时间。

已尝试操作：
请补充重启、换网、截图、报错码等信息。

说明：当前工具只生成工单草稿，不会真实提交。""".strip()
    }


def check_reimbursement_rule(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    return {
        "content": f"""报销规则初步判断：

你的问题是：{query}

请重点确认：
1. 是否属于公司允许报销的业务场景。
2. 是否有有效发票、订单、审批单等凭证。
3. 是否超过对应城市、职级或项目预算标准。
4. 是否需要事前审批。
5. 是否在规定时限内提交。

最终结论应结合财务知识库中的制度条款和你的具体职级/城市标准。""".strip()
    }


def generate_leave_request(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    return {
        "content": f"""请假申请草稿：

请假类型：请补充年假 / 病假 / 事假 / 调休。
请假时间：请补充开始和结束时间。
请假原因：{query}
工作交接：请补充交接人、待处理事项和紧急联系人。

说明：当前工具只生成申请草稿，不会真实提交审批。""".strip()
    }


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("generate_weekly_report", generate_weekly_report, "根据用户描述生成周报草稿", "low")
    registry.register("draft_email", draft_email, "生成邮件草稿", "low")
    registry.register("create_it_ticket", create_it_ticket, "生成 IT 工单草稿", "low")
    registry.register("check_reimbursement_rule", check_reimbursement_rule, "初步判断报销规则并提示需要核对的制度点", "low")
    registry.register("generate_leave_request", generate_leave_request, "生成请假申请草稿", "low")
    return registry


def select_office_tool_by_rule(query: str) -> str | None:
    """Cheap deterministic tool routing before any LLM-heavy decision.

    This avoids spending LLM calls for obvious office-draft tasks and makes demos
    more stable. The LangGraph route node can still use LLM routing for RAG vs
    direct questions.
    """

    q = str(query or "").lower()
    if any(word in q for word in ["周报", "weekly report", "工作总结"]):
        return "generate_weekly_report"
    if any(word in q for word in ["邮件", "email", "通知"]):
        return "draft_email"
    if any(word in q for word in ["it工单", "it 工单", "工单", "电脑", "vpn", "网络", "无法联网"]):
        return "create_it_ticket"
    reimbursement_context = any(word in q for word in ["报销", "发票", "差旅", "住宿", "超标"])
    reimbursement_judgement = any(
        word in q
        for word in [
            "能不能",
            "能否",
            "可以报销",
            "可不可以",
            "是否可以",
            "是否能",
            "能报销",
            "判断",
            "合规吗",
            "是否合规",
            "超标",
            "不予报销",
        ]
    )
    if reimbursement_context and reimbursement_judgement:
        return "check_reimbursement_rule"
    if any(word in q for word in ["请假", "年假", "病假", "调休"]):
        return "generate_leave_request"
    return None
