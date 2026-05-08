from mini_rag.config import Settings
from mini_rag.models.qwen import build_qwen_embeddings


def test_qwen_embeddings_keep_dashscope_inputs_as_strings():
    embeddings = build_qwen_embeddings(Settings(DASHSCOPE_API_KEY="test-key"))

    assert embeddings.check_embedding_ctx_length is False
    assert embeddings.tiktoken_enabled is False

