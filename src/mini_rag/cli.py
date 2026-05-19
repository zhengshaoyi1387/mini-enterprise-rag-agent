from __future__ import annotations

import typer
from rich import print

from mini_rag.agent.agent import EnterpriseKnowledgeAgent
from mini_rag.config import get_settings
from mini_rag.ingestion.build_index import build_index
from mini_rag.observability.trace import save_trace
from mini_rag.rag.chain import RAGQuestionAnswerer

app = typer.Typer(help="Mini Enterprise RAG Agent 命令行工具")


@app.command("build-index")
def build_index_command(
    reset: bool = typer.Option(False, "--reset", help="是否删除旧索引后重建"),
):
    """构建 Chroma 向量索引。"""
    settings = get_settings()
    result = build_index(settings, reset=reset)
    print("[green]索引构建完成：[/green]")
    print(result)


@app.command("ask")
def ask_command(
    question: str = typer.Argument(..., help="你的问题"),
    use_agent: bool = typer.Option(True, "--agent/--no-agent", help="是否使用 Agent 版本"),
    session_id: str | None = typer.Option(None, "--session-id", help="多轮会话 ID"),
    retrieval_mode: str | None = typer.Option(None, "--retrieval-mode", help="检索模式：hybrid 或 vector"),
    no_rerank: bool = typer.Option(False, "--no-rerank", help="关闭 Qwen rerank"),
):
    """向企业知识库提问。"""
    settings = get_settings()

    if use_agent:
        qa = EnterpriseKnowledgeAgent(settings)
        result = qa.ask(
            question,
            session_id=session_id,
            retrieval_mode=retrieval_mode,
            enable_rerank=False if no_rerank else None,
        )
    else:
        qa = RAGQuestionAnswerer(settings)
        result = qa.ask(question, retrieval_mode=retrieval_mode, enable_rerank=False if no_rerank else None)
    trace_path = save_trace(settings, result["trace"])

    print("\n[bold green]答案：[/bold green]")
    print(result["answer"])

    if result.get("route"):
        print(f"\n[bold cyan]Route：[/bold cyan]{result['route']}")

    if result.get("sources"):
        print("\n[bold blue]引用来源：[/bold blue]")
        for item in result["sources"]:
            print(item)

    if trace_path:
        print(f"\n[dim]Trace 已保存：{trace_path}[/dim]")


@app.command("eval")
def eval_command():
    """提示使用当前统一评测脚本。"""
    print("[yellow]旧 mini-rag eval 命令已归档。当前主线请使用：[/yellow]")
    print("python scripts/agent_eval_suite.py --suite all --judge rule --output outputs/eval/full_eval_report")


@app.command("serve")
def serve_command(
    host: str = typer.Option("127.0.0.1", help="服务监听地址"),
    port: int = typer.Option(8000, help="服务端口"),
):
    """启动 FastAPI 服务。"""
    import uvicorn

    uvicorn.run("mini_rag.api.app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
