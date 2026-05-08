# Day 4：LangGraph 状态机 Agent 完整详细规划

> 适用目标：准备应聘 AI Agent / Agent Infra / Agent 开发框架相关实习岗位。  
> 当前基础：Day 1 已补齐 LLM 基础，Day 2 已完成 RAG 工程化链路，Day 3 已完成 Tool Calling / Tool Registry。  
> 今日核心目标：把前两天的 RAG 和工具调用，放进一个显式可控的 Agent 状态机中，让项目从“脚本式 Agent”升级为“可观测、可恢复、可扩展的 Agent 工作流”。

---

## 一、Day 4 总目标

今天结束时，你需要完成 5 个产出：

```text
1. langgraph_agent.md
2. agent/state.py
3. agent/nodes.py
4. agent/router.py
5. agent/graph.py
```

如果时间充足，再补充：

```text
6. agent/prompts.py
7. 一个可运行的 langgraph_demo.py
8. README 中的 Agent 架构图
```

今天学完后，你至少要能回答：

```text
1. 为什么 Agent 不应该只是简单 while-loop？
2. LangGraph 解决了什么问题？
3. State 在 Agent 中有什么作用？
4. Node 和 Edge 分别是什么？
5. Conditional Edge 解决什么问题？
6. Checkpoint 为什么重要？
7. Human-in-the-loop 适合什么场景？
8. 多 Agent 和状态机有什么区别？
9. 如何防止 Agent 死循环？
10. 如何把 RAG 和 Tool Calling 放进 LangGraph？
```

---

## 二、今日学习时间安排

假设今天可以学习 9-10 小时。

```text
09:00 - 09:30  复盘 Day 3 + 明确 LangGraph 今日目标
09:30 - 10:30  为什么需要状态机式 Agent
10:30 - 11:30  LangGraph 核心概念：State、Node、Edge、Graph
11:30 - 12:00  AgentState 设计
12:00 - 13:30  午休

13:30 - 14:30  Router Node 与条件分支
14:30 - 15:30  RAG Node / Tool Node / Final Node 设计
15:30 - 16:30  Reflection Node、循环控制与失败处理
16:30 - 17:30  Checkpoint、Human-in-the-loop、Trace 思路

19:00 - 20:00  实现 agent/state.py 和 agent/router.py
20:00 - 21:00  实现 agent/nodes.py
21:00 - 22:00  实现 agent/graph.py 并跑通 Demo
22:00 - 22:30  整理 langgraph_agent.md
22:30 - 23:00  当日复盘 + 明天衔接 FastAPI / 权限 / 服务化
```

---

# 09:00 - 09:30：复盘 Day 3 + 明确今日目标

## 1. 快速复盘 Day 3

你要能用 5 句话讲清 Tool Calling：

```text
Agent 不是简单聊天机器人，而是可以调用工具完成任务的系统。
Tool Calling 是模型提出工具名和参数，程序侧负责校验、权限检查和执行。
工具 schema 用来约束参数和帮助模型理解工具用途。
Tool Registry 用来统一注册、查找、校验和执行工具。
危险工具必须做权限控制、沙箱隔离和审计日志。
```

如果这几句话还讲不顺，先花 10 分钟回看 `tool_calling.md`。

---

## 2. 今日目标

昨天你的系统大概是：

```text
用户输入
-> 手动或模型决定工具
-> Tool Registry 执行工具
-> 返回结果
```

今天要升级成：

```text
User Input
-> Router Node
-> RAG Node / Tool Node
-> Reflection Node
-> Final Node
```

也就是说，从今天开始，你的 Agent 不再是一个脚本，而是一个明确的工作流图。

---

## 3. 今日最终项目目录

建议新增：

```text
agent-infra-mini/
├── agent/
│   ├── __init__.py
│   ├── state.py
│   ├── router.py
│   ├── nodes.py
│   ├── graph.py
│   └── prompts.py
├── rag/
│   ├── ingest.py
│   └── retriever.py
├── tools/
│   ├── registry.py
│   ├── schemas.py
│   └── search_kb.py
├── langgraph_demo.py
└── langgraph_agent.md
```

---

# 09:30 - 10:30：为什么需要状态机式 Agent

## 1. 简单 while-loop Agent 的问题

很多入门 Agent 都是这种形式：

```text
while not done:
    LLM 思考
    如果需要工具，调用工具
    把工具结果放回上下文
    继续让 LLM 生成
```

这种方式能跑 demo，但问题很多：

```text
状态隐式藏在 message history 里
工具调用链路难以追踪
复杂任务容易死循环
失败后不好恢复
无法清楚插入人工审批
不好做权限节点
不好记录每一步输入输出
不好替换某个模块
```

---

## 2. 企业级 Agent 需要什么

Agent Infra 岗位关心的不是“能不能调一次工具”，而是：

```text
流程是否可控
状态是否显式
每一步是否可观测
失败是否可恢复
工具是否可治理
权限是否可插入
人工审批是否可加入
多 Agent 是否可编排
```

所以需要状态机或工作流图。

---

## 3. LangGraph 的价值

LangGraph 可以把 Agent 拆成：

```text
State：全局状态
Node：处理节点
Edge：节点之间的流转
Conditional Edge：条件分支
Checkpoint：状态持久化
Human-in-the-loop：人工介入
```

它让 Agent 从“黑盒循环”变成“可控图结构”。

---

## 4. 面试回答模板

问题：**为什么 Agent 不应该只是简单 while-loop？**

回答：

```text
简单 while-loop 可以做 demo，但不适合企业级 Agent。因为状态通常隐式藏在消息历史里，流程不可控，工具调用难以审计，失败后不好恢复，也不方便插入权限检查和人工审批。企业级 Agent 更需要显式状态、节点化流程、条件分支、日志追踪和 checkpoint，因此更适合用 LangGraph 这类==状态机式框架==。
```

---

# 10:30 - 11:30：LangGraph 核心概念

## 1. State

State 是整个 Agent 工作流共享的数据。

例如：

```python
{
    "user_query": "什么是 RAG？",
    "retrieved_docs": [],
    "tool_calls": [],
    "observations": [],
    "final_answer": "",
    "error": None
}
```

所有节点都可以读取 State，并返回 State 的部分更新。

---

## 2. Node

Node 是图中的处理步骤。

常见节点：

```text
router_node：判断任务应该走哪条路径
rag_node：检索知识库
tool_node：调用工具
reflect_node：检查结果是否足够
final_node：生成最终答案
permission_node：检查权限
```

每个 Node 本质上是一个函数：

```python
def rag_node(state):
    ...
    return {"retrieved_docs": docs}
```

---

## 3. Edge

Edge 表示节点之间的连接。

例如：

```text
router_node -> rag_node
rag_node -> final_node
```

---

## 4. Conditional Edge

Conditional Edge 根据状态决定下一步去哪里。

例如：

```text
如果问题需要查资料 -> rag_node
如果问题需要工具 -> tool_node
如果可以直接回答 -> final_node
```

---

## 5. Graph

Graph 是完整工作流。

可以理解成：

```text
节点 + 边 + 状态更新规则
```

---

## 6. 必背回答模板

问题：**LangGraph 的 State、Node、Edge 分别是什么？**

回答：

```text
State 是 Agent 工作流中的共享状态，用来保存用户问题、检索结果、工具调用、记忆、错误和最终答案。Node 是具体处理步骤，比如路由、检索、工具调用和最终生成。Edge 是节点之间的流转关系，Conditional Edge 可以根据当前状态动态决定下一步走哪个节点。
```

---

# 11:30 - 12:00：AgentState 设计

## 1. 为什么 State 设计很重要

State 是 Agent 的“运行时记忆”。

如果 State 设计不好，后面会出现：

```text
节点之间传参混乱
工具结果无法追踪
错误无法定位
权限信息丢失
trace 难以记录
循环不好控制
```

---

## 2. 推荐 State 字段

```python
from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    user_query: str
    user_id: str
    role: str
    route: str
    retrieved_docs: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    memory: Dict[str, Any]
    trace_id: str
    step_count: int
    max_steps: int
    final_answer: str
    error: Optional[str]
```

---

## 3. 字段解释

| 字段 | 作用 |
|---|---|
| user_query | 用户原始问题 |
| user_id | 用户身份 |
| role | 用户角色，用于权限判断 |
| route | 路由结果，例如 rag/tool/direct |
| retrieved_docs | RAG 检索到的文档片段 |
| tool_calls | 工具调用记录 |
| observations | 工具返回结果 |
| memory | 会话记忆或用户记忆 |
| trace_id | 请求追踪 ID |
| step_count | 当前执行步数 |
| max_steps | 最大执行步数，防止死循环 |
| final_answer | 最终答案 |
| error | 错误信息 |

---

## 4. 面试表达

```text
我会把 Agent 的运行状态显式放在 State 中，而不是只依赖 message history。这样每个节点的输入输出都可追踪，也方便做权限检查、错误处理、checkpoint、trace 和 eval。
```

---

# 12:00 - 13:30：午休

午休前你要能说清楚：

```text
为什么 while-loop Agent 不够？
State 是什么？
Node 是什么？
Edge 是什么？
Conditional Edge 有什么用？
AgentState 里应该放哪些字段？
```

---

# 13:30 - 14:30：Router Node 与条件分支

## 1. Router Node 是什么

Router Node 的作用是判断用户问题应该走哪条路径。

常见路由：

```text
rag：需要查知识库
tool：需要调用工具
direct：可以直接回答
reject：存在安全风险，拒绝
```

---

## 2. 简单规则路由

今天可以先用规则判断，不必一上来让 LLM 做 router。

示例：

```python
def route_query(query: str) -> str:
    rag_keywords = ["根据笔记", "知识库", "文档", "资料", "RAG", "LangGraph"]
    tool_keywords = ["生成计划", "计算", "执行", "保存", "读取记忆"]

    if any(k in query for k in tool_keywords):
        return "tool"

    if any(k in query for k in rag_keywords):
        return "rag"

    return "direct"
```

---

## 3. LLM Router

后续可以升级为 LLM Router：

```text
让模型输出：
{
  "route": "rag",
  "reason": "用户问题需要查询本地知识库"
}
```

但今天建议先用规则保证稳定。

---

## 4. Conditional Edge 设计

路由结果决定下一步：

```text
route == "rag" -> rag_node
route == "tool" -> tool_node
route == "direct" -> final_node
route == "reject" -> reject_node
```

---

## 5. 面试回答模板

问题：**Conditional Edge 解决什么问题？**

回答：

```text
Conditional Edge 用来根据当前 State 动态决定下一步执行哪个节点。比如用户问题需要查知识库时走 RAG Node，需要执行动作时走 Tool Node，涉及危险请求时走 Reject 或 Permission Node。这样可以让 Agent 工作流更加可控，而不是所有请求都走同一条固定链路。
```

---

# 14:30 - 15:30：RAG Node / Tool Node / Final Node 设计

## 1. RAG Node

RAG Node 的职责：

```text
读取 state["user_query"]
调用 search_knowledge_base 或 retriever
把结果写入 state["retrieved_docs"]
记录 observation
```

示例：

```python
def rag_node(state):
    query = state["user_query"]
    docs = search_knowledge_base(query=query, top_k=5)

    return {
        "retrieved_docs": docs["results"],
        "observations": state.get("observations", []) + [
            {"type": "rag", "data": docs}
        ]
    }
```

---

## 2. Tool Node

Tool Node 的职责：

```text
判断要调用哪个工具
构造工具参数
通过 Tool Registry 执行
把工具调用记录写入 state["tool_calls"]
把结果写入 state["observations"]
```

今天可以先写一个简单版本：

```text
如果 query 包含“学习计划” -> 调用 generate_study_plan
如果 query 包含“知识库” -> 调用 search_knowledge_base
```

后续再升级成 LLM 决策工具调用。

---

## 3. Final Node

Final Node 的职责：

```text
基于 user_query、retrieved_docs、observations 生成最终答案
```

今天如果暂时不接 LLM，可以先用模板输出：

```text
根据检索结果，我找到了以下相关内容...
```

接 LLM 后，可以将 context 组装成 prompt。

---

## 4. Final Node Prompt

建议：

```text
你是一个严谨的 Agent 助手。
请根据给定资料和工具观察结果回答用户问题。
如果资料不足，请说明不知道。
回答时尽量标注来源。
```

---

## 5. 面试表达

```text
我会把 RAG、工具调用和最终回答拆成不同节点。这样每个节点职责清晰，便于单独测试和替换，也方便记录每一步的输入输出和错误。
```

---

# 15:30 - 16:30：Reflection Node、循环控制与失败处理

## 1. Reflection Node 是什么

Reflection Node 用来检查当前结果是否足够。

它可以判断：

```text
是否检索到文档
答案是否为空
工具是否失败
是否需要重试
是否超过最大步数
```

---

## 2. 今天的简单 Reflection 逻辑

```text
如果 retrieved_docs 为空 -> final_node 输出不知道
如果 tool 调用失败 -> final_node 说明失败原因
如果 step_count > max_steps -> final_node 停止
否则 -> final_node
```

---

## 3. 防止死循环

Agent 最常见的问题之一是无限循环。

要加：

```text
step_count
max_steps
每次节点执行 step_count + 1
超过 max_steps 直接结束
```

---

## 4. 失败处理

常见失败：

```text
RAG 没检索到内容
工具不存在
工具参数错误
权限不足
工具执行异常
LLM 输出格式错误
```

处理原则：

```text
不要崩溃
写入 error
记录 trace
给用户可理解的回答
```

---

## 5. 面试回答模板

问题：**如何防止 Agent 死循环？**

回答：

```text
我会在 State 中维护 step_count 和 max_steps，每执行一个节点就增加 step_count。如果超过最大步数，工作流会强制进入 final 或 error 节点。同时对工具失败、检索为空和模型输出格式错误做显式处理，避免 Agent 在同一节点之间无限重试。
```

---

# 16:30 - 17:30：Checkpoint、Human-in-the-loop、Trace 思路

## 1. Checkpoint 是什么

Checkpoint 是把 Agent 的中间状态保存下来。

作用：

```text
长任务中断后可以恢复
出错时可以定位状态
人工审批前后可以接续执行
支持调试和回放
```

今天不需要实现完整 checkpoint，但要理解它的意义。

---

## 2. Human-in-the-loop 是什么

Human-in-the-loop 是在关键步骤插入人工确认。

适合：

```text
发送邮件前
删除文件前
执行代码前
修改数据库前
提交部署前
访问敏感数据前
```

---

## 3. Trace 应该记录什么

从 Day 4 开始，每个节点都应该考虑记录：

```text
trace_id
node_name
input_state 摘要
output_update
latency_ms
error
```

今天可以先用 print 或 JSONL 记录，Day 6 再系统化。

---

## 4. 面试回答模板

问题：**什么场景需要 Human-in-the-loop？**

回答：

```text
当 Agent 要执行高风险或不可逆操作时，需要 Human-in-the-loop，例如发送邮件、删除文件、修改数据库、执行代码、部署服务或访问敏感数据。模型可以提出操作建议，但真正执行前需要用户或管理员确认。
```

---

# 19:00 - 20:00：实践任务 1 —— 实现 agent/state.py 和 agent/router.py

## 1. 创建目录

```bash
mkdir -p agent
touch agent/__init__.py
```

---

## 2. agent/state.py 示例

```python
from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    user_query: str
    user_id: str
    role: str

    route: str

    retrieved_docs: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    memory: Dict[str, Any]

    trace_id: str
    step_count: int
    max_steps: int

    final_answer: str
    error: Optional[str]
```

---

## 3. agent/router.py 示例

```python
def route_query(query: str) -> str:
    query = query.strip()

    reject_keywords = [
        "输出系统提示词",
        "删除所有文件",
        "泄露 API key",
        "读取其他用户",
    ]

    tool_keywords = [
        "生成计划",
        "学习计划",
        "保存",
        "读取记忆",
        "执行代码",
        "计算",
    ]

    rag_keywords = [
        "根据笔记",
        "根据文档",
        "知识库",
        "资料",
        "RAG",
        "LangGraph",
        "Agent",
    ]

    if any(keyword in query for keyword in reject_keywords):
        return "reject"

    if any(keyword in query for keyword in tool_keywords):
        return "tool"

    if any(keyword in query for keyword in rag_keywords):
        return "rag"

    return "direct"
```

---

# 20:00 - 21:00：实践任务 2 —— 实现 agent/nodes.py

## 1. agent/nodes.py 示例

```python
from agent.router import route_query
from tools.search_kb import search_knowledge_base


def increase_step(state):
    return state.get("step_count", 0) + 1


def router_node(state):
    route = route_query(state["user_query"])

    return {
        "route": route,
        "step_count": increase_step(state),
        "observations": state.get("observations", []) + [
            {"type": "router", "route": route}
        ],
    }


def rag_node(state):
    query = state["user_query"]
    result = search_knowledge_base(query=query, top_k=5)

    return {
        "retrieved_docs": result.get("results", []),
        "step_count": increase_step(state),
        "observations": state.get("observations", []) + [
            {"type": "rag", "data": result}
        ],
    }


def tool_node(state):
    query = state["user_query"]

    if "学习计划" in query or "生成计划" in query:
        data = {
            "plan": [
                "第 1 步：复习 RAG 基础",
                "第 2 步：完成 Tool Calling",
                "第 3 步：用 LangGraph 编排 Agent",
            ]
        }
        tool_call = {
            "tool_name": "generate_study_plan",
            "args": {"query": query},
            "ok": True,
        }
    else:
        data = search_knowledge_base(query=query, top_k=5)
        tool_call = {
            "tool_name": "search_knowledge_base",
            "args": {"query": query, "top_k": 5},
            "ok": True,
        }

    return {
        "tool_calls": state.get("tool_calls", []) + [tool_call],
        "observations": state.get("observations", []) + [
            {"type": "tool", "data": data}
        ],
        "step_count": increase_step(state),
    }


def reject_node(state):
    return {
        "final_answer": "这个请求涉及敏感或危险操作，我不能执行。",
        "step_count": increase_step(state),
    }


def reflect_node(state):
    if state.get("step_count", 0) >= state.get("max_steps", 5):
        return {
            "error": "超过最大执行步数，已停止。",
            "step_count": increase_step(state),
        }

    if state.get("route") == "rag" and not state.get("retrieved_docs"):
        return {
            "error": "知识库中没有检索到相关内容。",
            "step_count": increase_step(state),
        }

    return {
        "step_count": increase_step(state)
    }


def final_node(state):
    if state.get("final_answer"):
        return {}

    if state.get("error"):
        return {
            "final_answer": f"无法完成请求：{state['error']}"
        }

    if state.get("retrieved_docs"):
        docs = state["retrieved_docs"]
        lines = ["根据知识库检索结果，找到以下相关内容："]
        for i, doc in enumerate(docs, start=1):
            source = doc.get("file_name") or doc.get("source") or "unknown"
            text = doc.get("text", "")
            lines.append(f"[{i}] 来源：{source}\n{text[:300]}")
        return {
            "final_answer": "\n\n".join(lines)
        }

    if state.get("observations"):
        return {
            "final_answer": f"已完成工具调用，观察结果：{state['observations'][-1]}"
        }

    return {
        "final_answer": "这是一个可以直接回答的问题。后续可以接入 LLM 生成更自然的回复。"
    }
```

---

# 21:00 - 22:00：实践任务 3 —— 实现 agent/graph.py 并跑通 Demo

## 1. 安装依赖

```bash
pip install langgraph
```

---

## 2. agent/graph.py 示例

```python
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes import (
    router_node,
    rag_node,
    tool_node,
    reject_node,
    reflect_node,
    final_node,
)


def decide_next_after_router(state: AgentState) -> str:
    route = state.get("route", "direct")

    if route == "rag":
        return "rag"
    if route == "tool":
        return "tool"
    if route == "reject":
        return "reject"

    return "final"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("rag", rag_node)
    graph.add_node("tool", tool_node)
    graph.add_node("reject", reject_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("final", final_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        decide_next_after_router,
        {
            "rag": "rag",
            "tool": "tool",
            "reject": "reject",
            "final": "final",
        },
    )

    graph.add_edge("rag", "reflect")
    graph.add_edge("tool", "reflect")
    graph.add_edge("reflect", "final")
    graph.add_edge("reject", END)
    graph.add_edge("final", END)

    return graph.compile()
```

---

## 3. langgraph_demo.py 示例

```python
from uuid import uuid4
from agent.graph import build_graph


def main():
    app = build_graph()

    state = {
        "user_query": "根据知识库解释什么是 RAG",
        "user_id": "u001",
        "role": "user",
        "trace_id": str(uuid4()),
        "step_count": 0,
        "max_steps": 5,
        "retrieved_docs": [],
        "tool_calls": [],
        "observations": [],
        "memory": {},
    }

    result = app.invoke(state)

    print("Final Answer:")
    print(result.get("final_answer"))

    print("\nRoute:")
    print(result.get("route"))

    print("\nObservations:")
    for obs in result.get("observations", []):
        print(obs)


if __name__ == "__main__":
    main()
```

---

## 4. 运行方式

先确保 Day 2 的 chunks 存在：

```bash
python rag/ingest.py
```

再运行：

```bash
python langgraph_demo.py
```

预期效果：

```text
Final Answer:
根据知识库检索结果，找到以下相关内容：

[1] 来源：rag.md
...

Route:
rag

Observations:
{'type': 'router', 'route': 'rag'}
{'type': 'rag', 'data': ...}
```

---

# 22:00 - 22:30：整理 langgraph_agent.md

## 推荐模板

```md
# LangGraph Agent 学习笔记

## 1. 为什么需要状态机 Agent

简单 while-loop Agent 适合 demo，但状态隐式、流程不可控、失败不好恢复，也不方便插入权限检查和人工审批。

企业级 Agent 更需要显式状态、节点化流程、条件分支、checkpoint、trace 和 eval。

## 2. LangGraph 核心概念

- State：共享状态
- Node：处理步骤
- Edge：节点连接
- Conditional Edge：条件分支
- Checkpoint：状态持久化
- Human-in-the-loop：人工介入

## 3. AgentState 设计

State 中应包含：

- user_query
- user_id
- role
- route
- retrieved_docs
- tool_calls
- observations
- memory
- trace_id
- step_count
- max_steps
- final_answer
- error

## 4. 节点设计

本项目使用以下节点：

1. router_node：判断任务路径
2. rag_node：检索知识库
3. tool_node：执行工具调用
4. reflect_node：检查结果和错误
5. final_node：生成最终答案
6. reject_node：拒绝危险请求

## 5. 条件分支

router_node 根据 route 决定下一步：

- rag -> rag_node
- tool -> tool_node
- direct -> final_node
- reject -> reject_node

## 6. 防止死循环

通过 step_count 和 max_steps 控制最大执行步数，超过限制后进入 final 或 error 处理。

## 7. 为什么适合 Agent Infra

LangGraph 让 Agent 的运行过程可观测、可调试、可恢复，也方便加入权限、安全、人工审批和多 Agent 编排。
```

---

# 22:30 - 23:00：当日复盘 + 明天衔接 FastAPI

## 1. 检查今日产出

```text
[ ] langgraph_agent.md 完成
[ ] agent/state.py 完成
[ ] agent/router.py 完成
[ ] agent/nodes.py 完成
[ ] agent/graph.py 完成
[ ] langgraph_demo.py 能运行
[ ] router 能区分 rag/tool/direct/reject
[ ] rag_node 能调用知识库检索
[ ] tool_node 能模拟工具调用
[ ] final_node 能输出结果
```

---

## 2. 用自己的话讲一遍

不要看笔记，口述下面内容：

```text
为什么 while-loop Agent 不够？
LangGraph 的 State 是什么？
Node 和 Edge 是什么？
Conditional Edge 有什么用？
RAG Node 和 Tool Node 怎么设计？
Reflect Node 有什么用？
如何防止 Agent 死循环？
Human-in-the-loop 用在什么场景？
```

---

## 3. 为 Day 5 做准备

明天进入 FastAPI + 权限系统。

你今天完成的是：

```text
一个本地可运行的 LangGraph Agent
```

明天要把它服务化：

```text
POST /chat
GET /health
GET /traces/{trace_id}
POST /upload
```

并加入：

```text
user_id
role
api_key
tool permission
trace_id
异常处理
```

---

# 三、Day 4 最终验收标准

## 1. 基础理解

```text
[ ] 能解释为什么需要状态机 Agent
[ ] 能解释 LangGraph 的 State、Node、Edge
[ ] 能解释 Conditional Edge
[ ] 能解释 AgentState 字段设计
[ ] 能解释 RAG Node / Tool Node / Final Node
[ ] 能解释 Reflection Node
[ ] 能解释 Checkpoint 的意义
[ ] 能解释 Human-in-the-loop 场景
[ ] 能解释如何防止死循环
```

---

## 2. 实践产出

```text
[ ] 完成 langgraph_agent.md
[ ] 完成 agent/state.py
[ ] 完成 agent/router.py
[ ] 完成 agent/nodes.py
[ ] 完成 agent/graph.py
[ ] 完成 langgraph_demo.py
[ ] 能跑通 graph.invoke()
[ ] 能看到 route、observations、final_answer
```

---

## 3. 面试表达

```text
[ ] 能用 1 分钟讲清 while-loop Agent 的问题
[ ] 能用 1 分钟讲清 LangGraph 解决了什么
[ ] 能用 1 分钟讲清 State 设计
[ ] 能用 1 分钟讲清 Router / RAG / Tool / Final 节点
[ ] 能用 1 分钟讲清 checkpoint 和 human-in-the-loop
```

---

# 四、今天不要做什么

```text
不要一上来做复杂多 Agent
不要把所有逻辑都塞进一个 node
不要忽略 State 字段设计
不要让节点返回不可控的大对象
不要忘记 step_count 和 max_steps
不要急着做漂亮 UI
不要一边写 LangGraph 一边重构所有 RAG 代码
不要把权限、安全、日志都堆到今天完成
```

今天只做一件事：

```text
把 RAG 和 Tool Calling 放进一个显式 Agent 状态机中。
```

---

# 五、Day 4 最重要的一句话

```text
LangGraph 的价值不是“让 Agent 更复杂”，而是让 Agent 的状态、流程、分支、错误和工具调用都变得显式、可控、可观测。
```

这句话打通之后，明天把 Agent 接到 FastAPI 网关、权限系统和 Trace 日志时，你就能把项目从本地 Demo 推进到 Agent Infra 小系统。
