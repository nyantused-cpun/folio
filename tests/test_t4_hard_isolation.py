# -*- coding: utf-8 -*-
"""T4 硬隔离测试。

覆盖：
- BM25 索引构建期写入结构化 clients 字段，查询按字段过滤
- 融合入口 _hard_filter_client 丢弃跨客户候选并计数
"""

import _recall


class TestBm25StructuredClientFilter:
    def test_query_filters_by_stored_clients(self, tmp_path, monkeypatch):
        import _bm25 as bm25
        monkeypatch.setattr(bm25, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(bm25, "BM25_INDEX_PATH", str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(bm25, "_INDEX_CACHE", None)

        paths = [
            f"{tmp_path}/clients/甲/refs/a.md",
            f"{tmp_path}/clients/甲/context.md",
            f"{tmp_path}/clients/乙/refs/b.md",
            f"{tmp_path}/clients/乙/context.md",
            f"{tmp_path}/docs/method.md",
        ]
        texts = [
            "甲客户 金额 报价 方案",
            "甲客户 历史 记录",
            "乙客户 完全 不同 内容",
            "乙客户 历史 记录 无关",
            "方法论 完全 无关",
        ]
        bm25.build_bm25_index(paths, texts)

        # 重新加载索引，验证 clients 字段已持久化
        monkeypatch.setattr(bm25, "_INDEX_CACHE", None)
        results = bm25.query_bm25("甲客户", top_k=10, client_filter="甲")
        assert results
        assert all("/clients/甲/" in p for p, _ in results)

        # 旧索引缺少 clients 字段时仍能回退路径过滤（模拟手工构造旧结构）
        from _paths import safe_pickle_load
        data = safe_pickle_load(str(tmp_path / "bm25_index.pkl"))
        data.pop("clients", None)
        from _paths import safe_pickle_dump
        safe_pickle_dump(data, str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(bm25, "_INDEX_CACHE", None)
        results = bm25.query_bm25("甲客户", top_k=10, client_filter="甲")
        assert results
        assert all("/clients/甲/" in p for p, _ in results)


class TestHardFilterClient:
    def test_drops_cross_client_candidates(self, monkeypatch):
        monkeypatch.setattr(_recall, "list_clients", lambda: ["甲", "乙"])
        results = [
            ("_knowledge/clients/甲/context.md#s0", 1.0),
            ("_knowledge/clients/乙/refs/a.md#p0", 0.9),
            ("_knowledge/clients/甲/decisions.md#d0", 0.8),
            ("docs/method.md#h0", 0.7),
        ]
        kept, filtered = _recall._hard_filter_client(results, "甲")
        assert filtered == 2
        assert len(kept) == 2
        assert all("/clients/甲/" in p for p, _ in kept)

    def test_none_and_empty_are_noops(self):
        assert _recall._hard_filter_client(None, "甲") == (None, 0)
        assert _recall._hard_filter_client([], "甲") == ([], 0)
        assert _recall._hard_filter_client([("x", 1.0)], None) == ([("x", 1.0)], 0)