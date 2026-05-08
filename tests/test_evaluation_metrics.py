from mini_rag.evaluation.metrics import aggregate_rows, citation_hit, refusal_hit, source_hit


def test_source_hit_accepts_path_suffixes():
    assert source_hit(["policy.md"], ["data/raw/policy.md"])


def test_citation_hit_requires_expected_source_mentions():
    assert citation_hit(["manual.md"], "答案来自 manual.md 的说明")
    assert not citation_hit(["manual.md"], "答案没有引用来源")


def test_refusal_hit_accepts_reject_route_or_refusal_text():
    assert refusal_hit(True, "", route="reject")
    assert refusal_hit(True, "当前证据不足以回答该问题")
    assert not refusal_hit(True, "这是一个普通回答", route="rag")


def test_aggregate_rows_calculates_rates_and_latency():
    metrics = aggregate_rows(
        [
            {"recall_hit": True, "citation_hit": True, "refusal_hit": True, "latency_ms": 10},
            {"recall_hit": False, "citation_hit": True, "refusal_hit": False, "latency_ms": 30},
        ]
    )
    assert metrics.question_count == 2
    assert metrics.recall_at_k == 0.5
    assert metrics.citation_hit_rate == 1.0
    assert metrics.refusal_hit_rate == 0.5
    assert metrics.avg_latency_ms == 20
