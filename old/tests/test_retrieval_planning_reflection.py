from langchain_core.documents import Document

from mini_rag.agent.evidence_reflector import assess_evidence
from mini_rag.agent.graph_agent import EnterpriseKnowledgeGraphAgent
from mini_rag.agent.retrieval_planner import plan_retrieval
from mini_rag.config import Settings


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class QueueLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)

    def invoke(self, _messages):
        if self.contents:
            return FakeMessage(self.contents.pop(0))
        return FakeMessage("最终回答")


class RecordingRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, retrieval_mode=None, enable_rerank=None):
        self.queries.append(query)
        return (
            [
                Document(
                    page_content=f"{query} 的功能说明",
                    metadata={
                        "source": "manual.md",
                        "title_path": f"手册 > {query}",
                        "chunk_id": f"chunk-{len(self.queries)}",
                        "rank": len(self.queries),
                    },
                )
            ],
            {
                "query": query,
                "retrieval_engine": "hybrid",
                "result_count": 1,
                "results": [{"source": "manual.md", "chunk_id": f"chunk-{len(self.queries)}"}],
            },
        )


def make_settings(tmp_path):
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        AGENT_RUNTIME="langgraph",
        RERANK_ENABLED=False,
        AGENT_MAX_STEPS=10,
    )


def test_plan_retrieval_splits_multi_module_question():
    llm = QueueLLM(
        [
            """
            {
              "search_queries": [
                "智能客服平台 服务质检 功能说明",
                "智能客服平台 数据报表 功能说明",
                "智能客服平台 系统配置 功能说明"
              ],
              "reason": "问题要求分别介绍三个模块"
            }
            """
        ]
    )

    plan = plan_retrieval(
        llm,
        question="简单介绍一下后三个模块",
        standalone_query="智能客服平台中服务质检、数据报表、系统配置这三个核心模块的功能定义与主要作用是什么？",
        router_decision={"route": "rag"},
    )

    assert plan.search_queries == [
        "智能客服平台 服务质检 功能说明",
        "智能客服平台 数据报表 功能说明",
        "智能客服平台 系统配置 功能说明",
    ]
    assert plan.fallback_used is False


def test_assess_evidence_can_request_followup_queries():
    llm = QueueLLM(
        [
            """
            {
              "is_sufficient": false,
              "reason": "缺少系统配置的独立证据",
              "missing_information": ["系统配置功能说明"],
              "followup_queries": ["智能客服平台 系统配置 功能说明"],
              "can_answer_partial": true
            }
            """
        ]
    )

    assessment = assess_evidence(
        llm,
        question="介绍三个模块",
        standalone_query="介绍服务质检、数据报表、系统配置",
        docs=[Document(page_content="服务质检说明", metadata={"chunk_id": "c1"})],
        retrieval_queries=["智能客服平台 服务质检 功能说明"],
    )

    assert assessment.is_sufficient is False
    assert assessment.followup_queries == ["智能客服平台 系统配置 功能说明"]
    assert assessment.can_answer_partial is True


def test_langgraph_agent_runs_planned_queries_and_reflects_before_final(tmp_path):
    llm = QueueLLM(
        [
            '{"intent":"rag_explain","route":"rag","standalone_query":"智能客服平台中服务质检、数据报表、系统配置这三个模块是什么？",'
            '"topic":"智能客服平台","entities":["服务质检","数据报表","系统配置"],"risk_level":"low","required_tools":[],"tasks":[{"task_id":"rag_1","type":"rag","query":"智能客服平台 服务质检 数据报表 系统配置 功能说明","purpose":"整体检索"}],"reason":"需要查企业知识库"}',
            "服务质检、数据报表、系统配置的简要说明。\n\n引用：manual.md",
        ]
    )
    retriever = RecordingRetriever()
    agent = EnterpriseKnowledgeGraphAgent(make_settings(tmp_path), llm=llm, retriever=retriever)

    result = agent.ask("简单介绍一下后三个模块")

    assert retriever.queries == [
        "智能客服平台 服务质检 数据报表 系统配置 功能说明",
    ]
    assert result["trace"]["executed_queries"] == retriever.queries
    assert result["trace"]["completion_reflect_control"]["ready_to_answer"] is True
