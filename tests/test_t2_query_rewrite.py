# -*- coding: utf-8 -*-
"""T2 查询改写模块测试。

覆盖：成功解析、失败回退、配置关闭、置信度边界。
"""

import _query_rewrite


class TestRewriteQuery:
    def test_success_parses_json(self, monkeypatch):
        monkeypatch.setattr(
            _query_rewrite, "chat",
            lambda *a, **kw: '{"rewritten": "智谱 报价 方案", "changes": ["补全客户名"], "confidence": 0.8}',
        )
        result = _query_rewrite.rewrite_query(
            "他们的报价方案", client="智谱", config={"enabled": True}
        )
        assert result["rewritten"] == "智谱 报价 方案"
        assert result["changes"] == ["补全客户名"]
        assert result["confidence"] == 0.8
        assert result["degraded"] == []

    def test_fallback_when_chat_returns_none(self, monkeypatch):
        monkeypatch.setattr(_query_rewrite, "chat", lambda *a, **kw: None)
        result = _query_rewrite.rewrite_query(
            "原查询", config={"enabled": True}
        )
        assert result["rewritten"] == "原查询"
        assert result["confidence"] == 1.0
        assert "REWRITE_FALLBACK" in result["degraded"]

    def test_disabled_returns_original(self, monkeypatch):
        called = {"n": 0}

        def fake_chat(*a, **kw):
            called["n"] += 1
            return "{}"

        monkeypatch.setattr(_query_rewrite, "chat", fake_chat)
        result = _query_rewrite.rewrite_query(
            "原查询", config={"enabled": False}
        )
        assert result["rewritten"] == "原查询"
        assert result["degraded"] == ["REWRITE_DISABLED"]
        assert called["n"] == 0

    def test_confidence_clamped(self, monkeypatch):
        monkeypatch.setattr(
            _query_rewrite, "chat",
            lambda *a, **kw: '{"rewritten": "改写", "changes": [], "confidence": 1.8}',
        )
        result = _query_rewrite.rewrite_query(
            "原查询", config={"enabled": True}
        )
        assert result["confidence"] == 1.0