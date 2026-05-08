"""LangGraph Agentic RAG package.

避免在导入 mini_rag.graph.utils 等纯工具模块时立即导入 LangChain/LangGraph 依赖。
需要 workflow 时请显式导入：
    from mini_rag.graph.workflow import AgenticRAGWorkflow
"""

__all__: list[str] = []
