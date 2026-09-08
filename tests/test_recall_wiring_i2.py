# -*- coding: utf-8 -*-
"""I-2 一期收口接线测试：T2 查询改写 / T7 query_trace / T5 fact_guard 生成链挂点。

recall() 内函数级 import（from _query_rewrite import rewrite_query 等），
monkeypatch 模块属性即可生效。
"""


def _known_config():
    return {
        "rrf": {"k": 10, "fallback_threshold": 0.05},
        "embedding": {"threshold": 0.1, "top_k": 20},
        "bm25": {"top_k": 20},
        "rerank": {"top_k": 5},
        "dedup": {"enabled": True, "max_per_doc": 1},
        "query_rewrite": {"enabled": True, "confidence_threshold": 0.6},
    }


def _emb_mock(results):
    return lambda query_text, top_k=20, client_filter=None, client_name=None: results


class TestT2QueryRewriteWiring:
    def test_high_confidence_uses_rewritten_single(self, monkeypatch):
        """置信度≥0.6 → 只用改写查询单路。"""
        import _bm25
        import _recall
        import _query_rewrite
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        seen = []
        def _bm25_spy(query_text, top_k=20, client_filter=None):
            seen.append(query_text)
            return [("C:/repo/_knowledge/clients/测试客户/方案.html#h1", 12.0)]
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_spy)
        monkeypatch.setattr(
            _query_rewrite, "rewrite_query",
            lambda *a, **k: {"rewritten": "改写后的蓝海方案", "changes": [],
                             "confidence": 0.9, "degraded": []})

        _recall.recall("蓝海方案", client_name="测试客户", rerank=False,
                       return_results=True, use_embedding=False)
        assert seen == ["改写后的蓝海方案"], f"高置信应只用改写查询，实际 {seen}"

    def test_low_confidence_dual_path(self, monkeypatch):
        """置信度<0.6 → 原查询 0.4 + 改写 0.6 双路（BM25 两次）。"""
        import _bm25
        import _recall
        import _query_rewrite
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        seen = []
        def _bm25_spy(query_text, top_k=20, client_filter=None):
            seen.append(query_text)
            return [("C:/repo/_knowledge/clients/测试客户/方案.html#h1", 12.0)]
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_spy)
        monkeypatch.setattr(
            _query_rewrite, "rewrite_query",
            lambda *a, **k: {"rewritten": "改写后的蓝海方案", "changes": [],
                             "confidence": 0.3, "degraded": []})

        _recall.recall("蓝海方案", client_name="测试客户", rerank=False,
                       return_results=True, use_embedding=False)
        assert len(seen) == 2, f"低置信应双路各查一次，实际 {seen}"
        assert "蓝海方案" in seen and "改写后的蓝海方案" in seen

    def test_rewrite_fallback_uses_original_degraded(self, monkeypatch):
        """改写失败 → 回退原查询，degraded=True。"""
        import _bm25
        import _recall
        import _query_rewrite
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        seen = []
        def _bm25_spy(query_text, top_k=20, client_filter=None):
            seen.append(query_text)
            return [("C:/repo/_knowledge/clients/测试客户/方案.html#h1", 12.0)]
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_spy)
        monkeypatch.setattr(
            _query_rewrite, "rewrite_query",
            lambda *a, **k: {"rewritten": "蓝海方案", "changes": [],
                             "confidence": 1.0, "degraded": ["REWRITE_FALLBACK"]})

        results = _recall.recall("蓝海方案", client_name="测试客户", rerank=False,
                                 return_results=True, use_embedding=False)
        assert seen == ["蓝海方案"]
        assert results and results[0]["degraded"] is True

    def test_disabled_uses_original_no_rewrite_call(self, monkeypatch):
        """use_query_rewrite=False → 原查询，且不调改写。"""
        import _bm25
        import _recall
        import _query_rewrite
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        seen = []
        def _bm25_spy(query_text, top_k=20, client_filter=None):
            seen.append(query_text)
            return [("C:/repo/_knowledge/clients/测试客户/方案.html#h1", 12.0)]
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_spy)
        def _boom(*a, **k):
            raise AssertionError("use_query_rewrite=False 不应调 rewrite_query")
        monkeypatch.setattr(_query_rewrite, "rewrite_query", _boom)

        _recall.recall("蓝海方案", client_name="测试客户", rerank=False,
                       return_results=True, use_embedding=False,
                       use_query_rewrite=False)
        assert seen == ["蓝海方案"]


class TestT7TraceWiring:
    def test_recall_writes_query_trace(self, monkeypatch):
        """recall 返回前自动写 query_trace。"""
        import _bm25
        import _recall
        import _query_trace
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        monkeypatch.setattr(
            _bm25, "query_bm25",
            lambda q, top_k=20, client_filter=None:
                [("C:/repo/_knowledge/clients/测试客户/方案.html#h1", 12.0)])
        records = []
        monkeypatch.setattr(_query_trace, "write_query_trace",
                            lambda entry: records.append(entry))

        _recall.recall("蓝海方案", client_name="测试客户", rerank=False,
                       return_results=True, use_embedding=False,
                       use_query_rewrite=False)
        assert records, "recall 应写 query_trace"
        r = records[0]
        assert r["query"] == "蓝海方案"
        assert r["client"] == "测试客户"
        assert r["mode"] == "BM25"
        assert r["degraded"] in (True, False)
        assert "n_results" in r and "cross_client_filtered" in r


class TestT5FactGuardHook:
    def test_extract_section_runs_guard_and_enqueues(self, monkeypatch):
        """生成链 extract_section_content 调 guard_check，违规入隔离区不阻断。"""
        import _outline_to_spec as ots
        import _cloud_llm
        import _fact_guard
        section = {"section": "现状分析", "role": "overview",
                   "prompt": "x", "children": []}
        monkeypatch.setattr(ots, "_extract_cache_key", lambda *a, **k: "k1")
        monkeypatch.setattr(ots, "_load_extract_cache", lambda: {})
        monkeypatch.setattr(ots, "_gold_demo_block", lambda s: "")
        monkeypatch.setattr(ots, "ARCH_ROLES", set())
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        monkeypatch.setattr(
            _cloud_llm, "chat",
            lambda *a, **k: '{"title":"t","content":"预算 500 万",'
                            '"key_points":["一期 30 天"],"data":["500万"],'
                            '"source_quote":"q"}')
        monkeypatch.setattr(
            _cloud_llm, "_parse_json",
            lambda s: {"title": "t", "content": "预算 500 万",
                       "key_points": ["一期 30 天"], "data": ["500万"],
                       "source_quote": "q"})
        monkeypatch.setattr(_cloud_llm, "_validate_against_source",
                            lambda *a, **k: None)
        monkeypatch.setattr(ots, "_cache_put", lambda *a, **k: None)
        seen = {}
        monkeypatch.setattr(
            _fact_guard, "guard_check",
            lambda text, client=None, whitelist=None: (
                seen.setdefault("text", text),
                {"violations": ["数字不一致: 500"]})[1])
        monkeypatch.setattr(
            _fact_guard, "enqueue_guard_item",
            lambda item: seen.setdefault("enqueued", item))

        res = ots.extract_section_content(section, "材料", client_name="测试客户",
                                          evidence_chunks=None)
        assert res["content"] == "预算 500 万", "生成结果不受 fact_guard 阻断"
        assert seen.get("enqueued", {}).get("stage", "") == \
            "outline_to_spec.extract_section_content"
        assert seen.get("enqueued", {}).get("violations") == ["数字不一致: 500"]
