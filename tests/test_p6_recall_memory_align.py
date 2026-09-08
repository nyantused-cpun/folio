# -*- coding: utf-8 -*-
"""P6-1/2 切片/召回与记忆真源对齐测试。

覆盖：
- _embed_index._split_decision_chunks：三格式切分 + 跳过 conflict: pending / 已废弃 块
- _embed_index._decision_block_meta：切分前提取 persistence/scope（子块继承）
- _recall._read_snippet / read_chunk 的 #d{i} 锚点：跳过废弃/冲突块的块级读取
- _recall._extract_scope / _extract_persistence 缺省向后兼容
- recall(..., permanent_only=True) 只回 permanent 决策；decision 结果含 persistence/scope

全部用 tmp_path 造假文件，绝不读写真实 _knowledge/。
"""

import _bm25
import _embed_index
import _recall
from _recall import _extract_persistence, _extract_scope


def _known_config():
    return {
        "rrf": {"k": 10, "fallback_threshold": 0.05},
        "embedding": {"threshold": 0.1, "top_k": 20},
        "bm25": {"top_k": 20},
        "rerank": {"top_k": 5},
        "dedup": {"enabled": False, "max_per_doc": 1},
    }


# ============================================================
# _split_decision_chunks：三格式 + 跳过废弃/冲突块
# ============================================================
class TestSplitDecisionChunks:
    def test_three_formats_and_skip(self):
        content = (
            "# 测试客户 决策记录\n"
            "### D-001 · 以正式招标文件为铁律\n"
            "- **决策**: 以招标文件为准\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "\n"
            "## 决策 2：系统一体化切换\n"
            "- **决策**: 不分阶段切换\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "\n"
            "## [2026-08-29] 会话决策 2026-08-29 #sess\n"
            "- **决策**: 报价口径 100 万\n"
            "- **persistence**: task\n"
            "- **scope**: task\n"
            "\n"
            "## [2026-07-01] 废弃铁律\n"
            "- **决策**: 旧口径\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "- **状态**: 已废弃\n"
            "\n"
            "### D-005 · 冲突铁律\n"
            "- **决策**: 冲突口径\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "<!-- conflict: pending -->\n"
        )
        chunks = _embed_index._split_decision_chunks(content)
        idxs = [i for i, _ in chunks]
        texts = [t for _, t in chunks]
        # 三个有效块（D-NNN / ## 决策 N / ## [日期]），跳过已废弃与冲突 pending
        assert len(chunks) == 3, texts
        assert idxs == [0, 1, 2]
        assert "以正式招标文件为铁律" in texts[0]
        assert "系统一体化切换" in texts[1]
        assert "报价口径 100 万" in texts[2]
        assert not any("废弃铁律" in t for t in texts)
        assert not any("冲突铁律" in t for t in texts)

    def test_empty_and_no_blocks(self):
        assert _embed_index._split_decision_chunks("") == []
        assert _embed_index._split_decision_chunks("# 只有文件头\n") == []


# ============================================================
# _decision_block_meta：切分前提取（子块继承）
# ============================================================
class TestDecisionBlockMeta:
    def test_explicit_fields(self):
        block = (
            "## [2026-08-29] 会话决策 2026-08-29 #sess\n"
            "- **决策**: x\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
        )
        meta = _embed_index._decision_block_meta(block)
        assert meta == {"persistence": "task", "scope": "task"}

    def test_missing_defaults(self):
        block = "## [2026-06-01] 旧铁律\n- **决策**: y\n"
        meta = _embed_index._decision_block_meta(block)
        assert meta == {"persistence": "permanent", "scope": "client"}


# ============================================================
# _extract_scope / _extract_persistence
# ============================================================
class TestExtractMeta:
    def test_scope_extraction(self):
        assert _extract_scope("x\n- **scope**: task\n") == "task"
        assert _extract_scope("x\n- **scope**: client\n") == "client"
        assert _extract_scope("无字段") == "client"  # 缺省向后兼容

    def test_persistence_extraction(self):
        assert _extract_persistence("x\n- **persistence**: permanent\n") == "permanent"
        assert _extract_persistence("无字段") == "permanent"


# ============================================================
# _read_snippet / read_chunk：#d{i} 锚点跳过废弃/冲突块
# ============================================================
class TestReadDecisionAnchor:
    def _make_decisions(self, tmp_path):
        d = tmp_path / "clients" / "测试客户"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "decisions.md"
        p.write_text(
            "# 测试客户 决策记录\n"
            "## [2026-06-01] 铁律A\n"
            "- **决策**: 铁律A内容\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "\n"
            "## [2026-07-01] 废弃铁律\n"
            "- **决策**: 已废弃内容\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "- **状态**: 已废弃\n"
            "\n"
            "## [2026-08-29] 会话决策 2026-08-29 #sess\n"
            "- **决策**: 会话决策内容\n"
            "- **persistence**: task\n"
            "- **scope**: task\n",
            encoding="utf-8",
        )
        return str(p)

    def test_read_snippet_skips_deprecated(self, tmp_path):
        path = self._make_decisions(tmp_path)
        # 原始块索引：d0=铁律A, d1=已废弃(跳过), d2=会话决策
        # 有效块锚点返回对应块内容；被跳过块返回过滤说明
        assert "铁律A内容" in _recall._read_snippet(f"{path}#d0", 2000)
        assert "会话决策内容" in _recall._read_snippet(f"{path}#d2", 2000)
        filtered = _recall._read_snippet(f"{path}#d1", 2000)
        assert "已废弃" in filtered or "未决冲突" in filtered
        assert "已废弃内容" not in filtered

    def test_read_chunk_decision_anchor(self, tmp_path):
        path = self._make_decisions(tmp_path)
        chunk = _recall.read_chunk(f"{path}#d0", 10000)
        assert "铁律A内容" in chunk
        assert "已废弃内容" not in chunk


# ============================================================
# P6-3/4：方法论文档白名单 archive 双路径 + cases 案例卡入索引
# ============================================================
class TestScanCorpusMethodCases:
    def test_archived_methodology_and_cases_scanned(self, tmp_path, monkeypatch):
        import _embed_index
        # 造假工作区：docs/archive（已归档方法论）+ _knowledge/cases + clients（须存在）
        (tmp_path / "_knowledge" / "clients").mkdir(parents=True)
        docs_archive = tmp_path / "docs" / "archive"
        docs_archive.mkdir(parents=True)
        (docs_archive / "视觉规范v3.0_讨论与实施记录_2026-08-11.md").write_text(
            "## 视觉规范 v3.0 讨论\n" + "内容足够长以通过 chunk 过滤。" * 12 + "\n", encoding="utf-8")
        cases = tmp_path / "_knowledge" / "cases"
        cases.mkdir(parents=True)
        (cases / "案例卡A.md").write_text(
            "## 案例卡A\n" + "客户案例内容足够长。" * 12 + "\n", encoding="utf-8")
        monkeypatch.setattr(_embed_index, "SCRIPT_DIR", str(tmp_path))
        corpus, _ = _embed_index.scan_corpus_with_warnings()
        paths = [p for p, _ in corpus]
        assert any("docs" in p and "archive" in p and "视觉规范" in p for p in paths), \
            "已归档方法论应入索引（archive 双路径）"
        assert any("_knowledge" in p and "cases" in p and "案例卡A" in p for p in paths), \
            "cases 案例卡应入索引"


# ============================================================
# P1-2（对抗审查补强）：索引锚点方案版本——升级即全量重建
# ============================================================
class TestAnchorScheme:
    def test_load_npy_anchor_scheme(self, tmp_path, monkeypatch):
        import json as _json
        import _embed_index as ei
        idx = tmp_path / "embeddings_index.json"
        idx.write_text(_json.dumps({"paths": [], "anchor_scheme": ei.ANCHOR_SCHEME}),
                       encoding="utf-8")
        monkeypatch.setattr(ei, "EMBED_INDEX_PATH", str(idx))
        assert ei._load_npy_anchor_scheme() == ei.ANCHOR_SCHEME
        # 缺失（旧索引）→ 返回 ""（触发升级重建判定）
        idx.write_text(_json.dumps({"paths": []}), encoding="utf-8")
        assert ei._load_npy_anchor_scheme() == ""


# ============================================================
# P6-2（审查补强）：permanent_only 在关键词降级路径同样生效
# ============================================================
class TestFallbackPermanentOnly:
    def _make_client(self, tmp_path, monkeypatch):
        import _paths
        clients = tmp_path / "clients"
        d = clients / "测试客户P"
        d.mkdir(parents=True)
        (d / "decisions.md").write_text(
            "## [2026-06-01] 铁律X\n"
            "- **决策**: 铁律X 内容\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "\n"
            "## [2026-08-29] 会话决策 2026-08-29 #s\n"
            "- **决策**: 会话决策内容\n"
            "- **persistence**: task\n"
            "- **scope**: task\n",
            encoding="utf-8",
        )
        (d / "context.md").write_text("会话决策内容 也在 context 里", encoding="utf-8")
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户P"])
        monkeypatch.setattr(_recall, "get_context_path",
                            lambda c: str(clients / c / "context.md"))

    def test_permanent_only_filters_in_fallback(self, tmp_path, monkeypatch):
        self._make_client(tmp_path, monkeypatch)
        results = _recall._keyword_fallback("铁律X", return_results=True, permanent_only=True)
        assert results
        assert results[0]["source_type"] == "decision"
        assert results[0]["persistence"] == "permanent"
        assert "铁律X" in results[0]["snippet"]
        assert "会话决策内容" not in results[0]["snippet"]  # task 决策不参与

    def test_permanent_only_ignores_task_only_query(self, tmp_path, monkeypatch):
        self._make_client(tmp_path, monkeypatch)
        # 「会话决策」只出现在 task 块与 context——permanent-only 下不应命中
        results = _recall._keyword_fallback("会话决策", return_results=True, permanent_only=True)
        assert results == [] or not any("会话决策内容" in r.get("snippet", "") for r in results)


# ============================================================
# M2-R2：recall 不再依赖图扩展（图扩展已从召回链路移除）
# ============================================================
class TestRecallGraphDelegation:
    def test_no_graph_expansion_symbols(self):
        import _recall
        # M2-R2 后 _recall 不再导入/暴露图扩展函数
        assert not hasattr(_recall, "_expand_graph_2hop")
        assert not hasattr(_recall, "_find_pivot_nodes")


# ============================================================
# recall permanent_only + persistence/scope
# ============================================================
class TestRecallPermanentOnly:
    def _setup_recall(self, tmp_path, monkeypatch, decisions_text, bm25_paths):
        d = tmp_path / "clients" / "测试客户"
        d.mkdir(parents=True, exist_ok=True)
        dec_path = d / "decisions.md"
        dec_path.write_text(decisions_text, encoding="utf-8")

        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        monkeypatch.setattr(
            _recall, "_embedding_recall",
            lambda query_text, top_k=20, client_filter=None, client_name=None:
                [(p, 0.9) for p in bm25_paths])
        monkeypatch.setattr(
            _bm25, "query_bm25",
            lambda query_text, top_k=20, client_filter=None:
                [(p, 12.0) for p in bm25_paths])
        return str(dec_path)

    def test_permanent_only_filters_task(self, tmp_path, monkeypatch):
        decisions_text = (
            "# 测试客户 决策记录\n"
            "## [2026-06-01] 铁律A\n"
            "- **决策**: 铁律A 内容\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "\n"
            "## [2026-08-29] 会话决策 2026-08-29 #sess\n"
            "- **决策**: 会话决策内容\n"
            "- **persistence**: task\n"
            "- **scope**: task\n"
        )
        self._setup_recall(
            tmp_path, monkeypatch, decisions_text,
            [f"{tmp_path}/clients/测试客户/decisions.md#d0",
             f"{tmp_path}/clients/测试客户/decisions.md#d1"],
        )
        results = _recall.recall(
            "zzp6query9988", rerank=False, return_results=True,
            use_embedding=True, permanent_only=True)
        assert results
        # permanent_only：只剩 permanent 决策
        for item in results:
            assert item["source_type"] == "decision"
            assert item["persistence"] == "permanent"
        assert all("会话决策内容" not in (item.get("snippet") or "") for item in results)

    def test_recall_includes_persistence_scope(self, tmp_path, monkeypatch):
        decisions_text = (
            "# 测试客户 决策记录\n"
            "## [2026-06-01] 铁律A\n"
            "- **决策**: 铁律A 内容\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
        )
        self._setup_recall(
            tmp_path, monkeypatch, decisions_text,
            [f"{tmp_path}/clients/测试客户/decisions.md#d0"],
        )
        results = _recall.recall(
            "zzp6query9989", rerank=False, return_results=True,
            use_embedding=True)
        assert results
        item = results[0]
        assert item["source_type"] == "decision"
        assert item["persistence"] == "permanent"
        assert item["scope"] == "client"

    def test_permanent_only_keeps_non_decision(self, tmp_path, monkeypatch):
        # 非决策结果（如 outputs）不受 permanent_only 影响
        d = tmp_path / "clients" / "测试客户" / "outputs"
        d.mkdir(parents=True, exist_ok=True)
        out = d / "方案_v8.md"
        out.write_text("方案内容 数据架构 一期范围", encoding="utf-8")
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", _known_config())
        monkeypatch.setattr(_recall, "list_clients", lambda: ["测试客户"])
        out_path = f"{tmp_path}/clients/测试客户/outputs/方案_v8.md#h0"
        monkeypatch.setattr(
            _recall, "_embedding_recall",
            lambda query_text, top_k=20, client_filter=None, client_name=None:
                [(out_path, 0.9)])
        monkeypatch.setattr(
            _bm25, "query_bm25",
            lambda query_text, top_k=20, client_filter=None: [(out_path, 12.0)])

        results = _recall.recall(
            "zzp6query9990", rerank=False, return_results=True,
            use_embedding=True, permanent_only=True)
        assert results
        assert results[0]["source_type"] == "output"
