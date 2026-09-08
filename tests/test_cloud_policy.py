# -*- coding: utf-8 -*-
"""I-1 出域开关（cloud_policy: full|embedding_only|off）测试。

三层覆盖：
1. resolve_cloud_policy 解析：客户级 > 全局 > 默认 full；非法值回退；无客户名恒 full
2. _cloud_llm 熔断：embed/embed_batch/chat/rerank/siliconflow_rerank
   对 off 客户返回 None；embedding_only 客户 Chat/Rerank 熔断、Embedding 放行
3. recall() 降级联动：off 客户 BM25-only + degraded（_embedding_recall 零调用）；
   embedding_only 客户跳过 rerank

monkeypatch 注意：recall() 内函数级 import，打模块属性：
- 出域解析统一走 _cloud_llm.resolve_cloud_policy（recall 与云端层同源）
- _embedding_recall 是 _recall 模块全局引用，打 _recall._embedding_recall
"""

import pytest

CLIENT = "测试云策略客户"


@pytest.fixture
def cloud_env(tmp_path, monkeypatch):
    """可控的客户目录 + 全局配置目录。"""
    import _cloud_llm
    clients_dir = tmp_path / "clients"
    (clients_dir / CLIENT).mkdir(parents=True)
    monkeypatch.setattr(_cloud_llm, "CLIENTS_DIR", str(clients_dir))
    monkeypatch.setattr(_cloud_llm, "SCRIPT_DIR", str(tmp_path))
    return clients_dir


def _write_client_policy(clients_dir, policy):
    (clients_dir / CLIENT / "cloud_policy.yml").write_text(
        f"cloud_policy: {policy}\n", encoding="utf-8")


def _write_global(cloud_env, policy):
    (cloud_env.parent / "recall_config.yml").write_text(
        f"cloud_policy: {policy}\n", encoding="utf-8")


def _known_config():
    return {
        "rrf": {"k": 10, "fallback_threshold": 0.05},
        "embedding": {"threshold": 0.1, "top_k": 20},
        "bm25": {"top_k": 20},
        "rerank": {"top_k": 5},
        "dedup": {"enabled": True, "max_per_doc": 1},
    }


def _bm25_mock(results):
    return lambda query_text, top_k=20, client_filter=None: results


class TestResolveCloudPolicy:
    def test_default_full_when_no_config(self, cloud_env):
        import _cloud_llm
        assert _cloud_llm.resolve_cloud_policy(CLIENT) == "full"

    def test_client_override(self, cloud_env):
        import _cloud_llm
        _write_client_policy(cloud_env, "off")
        assert _cloud_llm.resolve_cloud_policy(CLIENT) == "off"
        _write_client_policy(cloud_env, "embedding_only")
        assert _cloud_llm.resolve_cloud_policy(CLIENT) == "embedding_only"

    def test_global_fallback(self, cloud_env):
        import _cloud_llm
        _write_global(cloud_env, "embedding_only")
        assert _cloud_llm.resolve_cloud_policy(CLIENT) == "embedding_only"

    def test_invalid_client_value_falls_back_global(self, cloud_env):
        import _cloud_llm
        _write_client_policy(cloud_env, "banana")
        _write_global(cloud_env, "off")
        assert _cloud_llm.resolve_cloud_policy(CLIENT) == "off"

    def test_no_client_name_always_full(self, cloud_env):
        import _cloud_llm
        _write_client_policy(cloud_env, "off")
        assert _cloud_llm.resolve_cloud_policy(None) == "full"
        assert _cloud_llm.resolve_cloud_policy("") == "full"


class TestCloudFuse:
    def test_embed_off_client_returns_none(self, cloud_env, monkeypatch):
        import _cloud_llm
        _write_client_policy(cloud_env, "off")
        monkeypatch.setattr(_cloud_llm, "current_embed_provider",
                            lambda: ("zhipu", "embedding-3-pro"))
        assert _cloud_llm.embed("x", client_name=CLIENT) is None

    def test_embed_embedding_only_client_allowed(self, cloud_env, monkeypatch):
        import _cloud_llm
        _write_client_policy(cloud_env, "embedding_only")
        monkeypatch.setattr(_cloud_llm, "current_embed_provider",
                            lambda: ("zhipu", "embedding-3-pro"))
        monkeypatch.setattr(_cloud_llm, "_post_json",
                            lambda *a, **k: ({"data": [{"index": 0, "embedding": [0.1, 0.2]}]}, None))
        assert _cloud_llm.embed("x", client_name=CLIENT) == [0.1, 0.2]

    def test_chat_off_and_embedding_only_blocked(self, cloud_env):
        import _cloud_llm
        for policy in ("off", "embedding_only"):
            _write_client_policy(cloud_env, policy)
            assert _cloud_llm.chat("hi", client_name=CLIENT) is None

    def test_rerank_off_and_embedding_only_blocked(self, cloud_env, monkeypatch):
        import _cloud_llm
        for policy in ("off", "embedding_only"):
            _write_client_policy(cloud_env, policy)
            cands = [(CLIENT, 0.9, "C:/x/方案.html", "snippet")]
            assert _cloud_llm.rerank("q", cands, client_name=CLIENT) is None
            assert _cloud_llm.siliconflow_rerank("q", cands, client_name=CLIENT) is None

    def test_full_allows_and_no_client_unrestricted(self, cloud_env, monkeypatch):
        import _cloud_llm
        # 无 client_name：不受限（向后兼容），rerank 走到真实逻辑前先被空 candidates 短路
        assert _cloud_llm.rerank("q", [], client_name=None) == []
        assert _cloud_llm.siliconflow_rerank("q", [], client_name=None) == []


class TestRecallPolicy:
    def test_off_client_bm25_only_degraded(self, monkeypatch):
        import _bm25
        import _recall
        import _cloud_llm
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: [CLIENT])
        monkeypatch.setattr(
            _cloud_llm, "resolve_cloud_policy",
            lambda client, **k: "off" if client == CLIENT else "full")
        monkeypatch.setattr(
            _bm25, "query_bm25",
            _bm25_mock([("C:/repo/_knowledge/clients/测试云策略客户/方案_v8.html#h1", 12.0)]))

        calls = {"embedding": 0}
        def spy_emb(*a, **k):
            calls["embedding"] += 1
            return None
        monkeypatch.setattr(_recall, "_embedding_recall", spy_emb)

        results = _recall.recall(
            "zzI1q7788", client_name=CLIENT, rerank=True, use_embedding=True,
            return_results=True)
        assert calls["embedding"] == 0, "off 客户不得调用 embedding 路"
        assert results, "BM25 单路应有结果"
        assert results[0]["mode"] == "BM25"
        assert results[0]["degraded"] is True

    def test_embedding_only_client_skips_rerank(self, monkeypatch):
        import _bm25
        import _recall
        import _cloud_llm
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: [CLIENT])
        monkeypatch.setattr(
            _cloud_llm, "resolve_cloud_policy",
            lambda client, **k: "embedding_only" if client == CLIENT else "full")
        monkeypatch.setattr(
            _recall, "_embedding_recall",
            lambda q, top_k=20, client_filter=None, client_name=None:
                [("C:/repo/_knowledge/clients/测试云策略客户/需求分析_v2.html#p3", 0.92)])
        monkeypatch.setattr(
            _bm25, "query_bm25",
            _bm25_mock([("C:/repo/_knowledge/clients/测试云策略客户/方案_v8.html#h1", 15.0)]))

        rerank_called = {"n": 0}
        def spy_rerank(*a, **k):
            rerank_called["n"] += 1
            return [("c", 1.0, "p", "s")]
        monkeypatch.setattr(_cloud_llm, "siliconflow_rerank", spy_rerank)

        results = _recall.recall(
            "zzI1q7788", client_name=CLIENT, rerank=True, use_embedding=True,
            return_results=True)
        assert rerank_called["n"] == 0, "embedding_only 客户不得调用 rerank"
        assert results
        assert results[0]["mode"] == "BM25 + Embedding RRF"
