# -*- coding: utf-8 -*-
"""T9 召回降级可见性测试：recall() 结果追加 source/mode/degraded 三键。

降级判定（_recall.recall 函数内局部 degraded 状态）：
- 请求了 Embedding 但该路返回 None（索引模型不一致 / 无 key / 无索引 / 异常均以
  None 返回）→ degraded=True（双路缺一路 = 质量打折）
- 双路都返回 → degraded=False
- 两路皆失 / RRF 阈值 / 依赖缺失 → _keyword_fallback → mode="关键词降级" degraded=True

monkeypatch 注意：recall() 内 `from _bm25 import query_bm25` 是函数内 import，
必须打 _bm25.query_bm25 模块属性；_embedding_recall 是 _recall 模块全局引用，
打 _recall._embedding_recall。
"""


def _known_config():
    """固定召回参数，避免依赖 recall_config.yml 与真实索引状态。"""
    return {
        "rrf": {"k": 10, "fallback_threshold": 0.05},
        "embedding": {"threshold": 0.1, "top_k": 20},
        "bm25": {"top_k": 20},
        "rerank": {"top_k": 5},
        "dedup": {"enabled": True, "max_per_doc": 1},
    }


def _bm25_mock(results):
    return lambda query_text, top_k=20, client_filter=None: results


def _emb_mock(results):
    return lambda query_text, top_k=20, client_filter=None: results


class TestRecallDegradation:
    """recall() 结果必须携带 source/mode/degraded，且降级路径正确置位。"""

    def test_embedding_none_bm25_ok_degraded(self, monkeypatch):
        """语义路无返回（模拟索引模型不一致等内部降级）→ degraded=True，mode=BM25。"""
        import _bm25
        import _recall
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))
        monkeypatch.setattr(
            _bm25, "query_bm25",
            _bm25_mock([("C:/repo/_knowledge/clients/测试客户/方案_v8.html#h1", 12.0)]))

        results = _recall.recall(
            "zzT9query7788", rerank=False, return_results=True, use_embedding=True)
        assert results, "BM25 单路有结果时应返回结果列表"
        item = results[0]
        # 纯加法：既有键保留
        for key in ("client", "score", "path", "snippet"):
            assert key in item
        assert item["source"] == "客户=测试客户 | 文档=方案_v8.html"
        assert item["mode"] == "BM25"
        assert item["degraded"] is True

    def test_both_legs_ok_not_degraded(self, monkeypatch):
        """BM25 + Embedding 双路都返回 → degraded=False，mode=RRF 融合。"""
        import _bm25
        import _recall
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(
            _recall, "_embedding_recall",
            _emb_mock([("C:/repo/_knowledge/clients/测试客户/需求分析_v2.html#p3", 0.92)]))
        monkeypatch.setattr(
            _bm25, "query_bm25",
            _bm25_mock([("C:/repo/_knowledge/clients/测试客户/方案_v8.html#h1", 15.0)]))

        results = _recall.recall(
            "zzT9query7788", rerank=False, return_results=True, use_embedding=True)
        assert results
        for item in results:
            assert item["source"].startswith("客户=测试客户 | 文档=")
            assert item["mode"] == "BM25 + Embedding RRF"
            assert item["degraded"] is False

    def test_both_legs_lost_keyword_fallback(self, monkeypatch, tmp_path):
        """BM25 索引不存在（query_bm25 返回 None）+ Embedding 无返回 → 关键词降级。"""
        import _bm25
        import _recall
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        ctx = tmp_path / "context.md"
        ctx.write_text("测试客户 报价 数据架构 一期范围确认", encoding="utf-8")
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(_recall, "get_context_path", lambda c: str(ctx))
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_mock(None))
        monkeypatch.setattr(_recall, "_embedding_recall", _emb_mock(None))

        results = _recall.recall(
            "报价", rerank=False, return_results=True, use_embedding=True)
        assert results, "关键词 fallback 应命中 tmp 上下文"
        item = results[0]
        assert item["mode"] == "关键词降级"
        assert item["degraded"] is True
        assert item["source"] == "客户=测试客户 | 文档=context.md"

    def test_bm25_none_emb_ok_degraded(self, monkeypatch):
        """监工补充（对称规则）：BM25 索引缺失（return None）+ Embedding 正常
        -> 单腿 Embedding 结果同样必须标 degraded=True。"""
        import _bm25
        import _recall
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(
            _recall, "_embedding_recall",
            _emb_mock([("C:/repo/_knowledge/clients/测试客户/方案_v8.html#h1", 0.88)]))
        monkeypatch.setattr(_bm25, "query_bm25", _bm25_mock(None))

        results = _recall.recall(
            "zzT9query7788", rerank=False, return_results=True, use_embedding=True)
        assert results, "Embedding 单路有结果时应返回结果列表"
        item = results[0]
        assert item["mode"] == "Embedding"
        assert item["degraded"] is True
