# -*- coding: utf-8 -*-
"""P3 检索/召回组 6 项修复的回归测试（全库审查报告 2026-09-06 §五）。

覆盖：
- P3-1 _aliases.detect_client_in_query 客户名长度降序匹配
- P3-2 _recall._read_snippet 方法论 #h{i}#w{wi} 锚点携带窗口号（含保守回退）
- P3-3 _recall_eval.detect_fallback 降级标记覆盖三条「关键词模式」路径
- P3-4 _fact_guard 中文数字链（万亿）合成与「百分之X」幽灵数字守卫
- P3-5 _embed_index 坏向量（维度/NaN/inf）写入与加载两侧 fail-closed
- P3-6 _graph/_snippet/_bm25 索引原子写（tmp + os.replace）

纪律：全程 monkeypatch/tmp_path，零联网、零真实 API。
"""

import json
import os
import re

import numpy as np
import pytest

import _aliases
import _bm25
import _cloud_llm
import _embed_index
import _fact_guard
import _graph
import _paths
import _recall
import _recall_eval
import _snippet


# ===== P3-1：detect_client_in_query 长度降序匹配 =====

class TestDetectClientInQuery:
    def _patch(self, monkeypatch, tmp_path, clients):
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(tmp_path))  # isdir 哨兵
        monkeypatch.setattr(_aliases, "_list_clients", lambda: clients)
        monkeypatch.setattr(_aliases, "get_client_aliases", lambda c: [])

    def test_longest_client_name_wins(self, tmp_path, monkeypatch):
        """前缀客户名（蓝海/蓝海v2）必须长名优先，不能让目录序的短名先命中。"""
        self._patch(monkeypatch, tmp_path, ["蓝海", "蓝海v2"])
        assert _aliases.detect_client_in_query("蓝海v2项目排期查询") == "蓝海v2"

    def test_short_name_still_matches(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path, ["蓝海v2", "蓝海"])
        assert _aliases.detect_client_in_query("蓝海的预算口径") == "蓝海"

    def test_no_match_returns_none(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path, ["蓝海v2", "蓝海"])
        assert _aliases.detect_client_in_query("无关查询") is None


# ===== P3-2：#h{i}#w{wi} 锚点携带窗口号（保守回退） =====

class TestReadSnippetWindowAnchor:
    @pytest.fixture()
    def method_doc(self, tmp_path):
        """一章含两个超长段落的方法论文档：滑动窗口必然多窗（与切片侧同参）。"""
        p = tmp_path / "方法论.md"
        para1 = "".join(chr(0x4E00 + (i % 500)) for i in range(900))
        para2 = "".join(chr(0x4E00 + ((i * 7) % 500)) for i in range(900))
        p.write_text("# 文档\n\n## 章一\n\n" + para1 + "\n\n" + para2 + "\n",
                     encoding="utf-8")
        return str(p)

    def test_window_anchor_returns_matched_window(self, method_doc):
        whole = _recall._read_snippet(method_doc + "#h1", 10000)
        wins = _embed_index._sliding_window_chunks(whole, chunk_size=800, overlap=200)
        assert len(wins) >= 2  # 前提：确有多窗
        # 窗口还原必须与切片侧窗口一致，而不是整章从头截断
        assert _recall._read_snippet(method_doc + "#h1#w0", 10000) == wins[0][:10000]
        assert _recall._read_snippet(method_doc + "#h1#w1", 10000) == wins[1][:10000]

    def test_window_anchor_differs_from_whole_chunk(self, method_doc):
        w0 = _recall._read_snippet(method_doc + "#h1#w0", 10000)
        whole = _recall._read_snippet(method_doc + "#h1", 10000)
        assert w0 != whole

    def test_window_anchor_out_of_range_falls_back(self, method_doc):
        """窗口号越界/非法 → 回退整章旧行为（保守回退约束）。"""
        whole = _recall._read_snippet(method_doc + "#h1", 10000)
        assert _recall._read_snippet(method_doc + "#h1#w99", 10000) == whole
        assert _recall._read_snippet(method_doc + "#h1#wxx", 10000) == whole

    def test_plain_h_anchor_unchanged(self, method_doc):
        """不带窗口号的 #h{i} 行为保持不变。"""
        content = open(method_doc, encoding="utf-8").read()
        chunks = re.split(r'(?=\n##\s)', content)
        assert _recall._read_snippet(method_doc + "#h1", 25) == chunks[1][:25]


# ===== P3-3：降级标记覆盖三条「关键词模式」路径 =====

class TestDetectFallbackMarkers:
    def test_rrf_threshold_marker(self):
        # 路径 1：RRF 最高分 < 阈值
        assert _recall_eval.detect_fallback(
            "[RRF 最高分 0.0300 < 阈值 0.05, 降级到关键词模式]") is True

    def test_missing_index_marker(self):
        # 路径 2：BM25 索引缺失且 Embedding 不可用
        assert _recall_eval.detect_fallback(
            "[BM25 索引不存在且 Embedding 不可用，使用关键词模式]") is True

    def test_missing_dependency_marker(self):
        # 路径 3：ImportError 降级
        assert _recall_eval.detect_fallback(
            "[降级] 缺少依赖 rank_bm25，使用关键词模式") is True

    def test_normal_output_not_flagged(self):
        assert _recall_eval.detect_fallback("[BM25] 索引已保存: x.pkl (3 文档)") is False
        assert _recall_eval.detect_fallback("") is False
        assert _recall_eval.detect_fallback(None) is False

    def test_marker_set_composition(self):
        """标记集合必须同时含旧标志与新覆盖的「使用关键词模式」。"""
        assert _recall_eval.FALLBACK_MARKER in _recall_eval.FALLBACK_MARKERS
        assert "使用关键词模式" in _recall_eval.FALLBACK_MARKERS


# ===== P3-4：中文数字链合成 + 百分比量词守卫 =====

class TestCnNumberChain:
    def test_wan_yi_chain(self):
        """一万亿 = 1e12（旧版把万先落总账，亿乘到 0 算成 10000）。"""
        assert _fact_guard.normalize_num("一万亿") == "1000000000000"
        assert _fact_guard.normalize_num("一万") == "10000"
        assert _fact_guard.normalize_num("一亿") == "100000000"
        assert _fact_guard.normalize_num("一百万") == "1000000"

    def test_mixed_chain(self):
        assert _fact_guard.normalize_num("十二亿三千五百万") == "1235000000"

    def test_regressions(self):
        assert _fact_guard.normalize_num("一百二十三") == "123"
        assert _fact_guard.normalize_num("五十") == "50"
        assert _fact_guard.normalize_num("零") == "0"


class TestGhostPercent:
    def test_no_ghost_from_baifenzhi(self):
        """「百分之五十」不得漏出幽灵「百」(100) / 尾字「十」(10)。"""
        r = _fact_guard.guard_check("占比百分之五十", whitelist=set())
        assert r["numbers"] == []
        assert "50%" in r["normalized_numbers"]
        assert "100" not in r["normalized_numbers"]
        assert "10" not in r["normalized_numbers"]

    def test_percent_with_other_numbers(self):
        """摘掉「百分之X」后，其余真实中文数字仍要正常抽出。"""
        r = _fact_guard.guard_check("占比百分之三十，另投三百", whitelist=set())
        assert "30%" in r["normalized_numbers"]
        assert "300" in r["normalized_numbers"]
        assert "100" not in r["normalized_numbers"]
        assert "30" not in r["normalized_numbers"]


# ===== P3-5：embedding 维度/NaN 防护（写入 + 加载两侧 fail-closed） =====

class TestVectorGuard:
    def test_vector_defect_flags(self):
        assert _embed_index._vector_defect([0.1, 0.2]) is None
        assert _embed_index._vector_defect(None) is not None
        assert "NaN" in _embed_index._vector_defect([0.1, float("nan")])
        assert "inf" in _embed_index._vector_defect([0.1, float("inf")])
        assert "维度不一致" in _embed_index._vector_defect([0.1, 0.2], expected_dim=3)
        assert _embed_index._vector_defect([0.1, 0.2], expected_dim=2) is None
        assert _embed_index._vector_defect([]) is not None
        assert _embed_index._vector_defect("不是向量") is not None

    def _patch_cache_paths(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_embed_index, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(_embed_index, "EMBED_MATRIX_PATH", str(tmp_path / "m.npy"))
        monkeypatch.setattr(_embed_index, "EMBED_INDEX_PATH", str(tmp_path / "i.json"))
        monkeypatch.setattr(_embed_index, "EMBED_CACHE_PATH", str(tmp_path / "old.pkl"))

    def test_build_rejects_bad_vectors(self, tmp_path, monkeypatch):
        """构建批内坏向量 fail-closed：NaN/维度不一致不入索引，好向量照常。"""
        self._patch_cache_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(
            _embed_index, "scan_corpus",
            lambda: [("a#h1", "文本甲"), ("b#h1", "文本乙"), ("c#h1", "文本丙")])

        def fake_embed(texts):
            assert len(texts) == 3
            return [[0.1, 0.2, 0.3, 0.4],   # 合格，定维度基准 4
                    [float("nan")] * 4,      # NaN → 拒绝
                    [0.5, 0.6, 0.7]]         # 维度不一致 → 拒绝

        monkeypatch.setattr(_cloud_llm, "embed_batch", fake_embed)
        monkeypatch.setattr(_cloud_llm, "current_embed_provider",
                            lambda: ("zhipu", "test-model"))

        result = _embed_index.build_embedding_index(batch_size=10, force=True)
        assert set(result["vectors"].keys()) == {"a#h1"}
        # 落盘索引与内存一致（坏向量不得静默写入）
        with open(_embed_index.EMBED_INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
        assert index["paths"] == ["a#h1"]

    def test_load_npy_rejects_nan_rows(self, tmp_path, monkeypatch):
        """加载侧 NaN 行拒绝并告警，好行保留。"""
        self._patch_cache_paths(monkeypatch, tmp_path)
        mat = np.array([[0.1, 0.2], [float("nan"), 0.3], [0.4, 0.5]],
                       dtype=np.float32)
        np.save(_embed_index.EMBED_MATRIX_PATH, mat)
        with open(_embed_index.EMBED_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"paths": ["a#h1", "b#h1", "c#h1"],
                       "model": "m", "dim": 2, "meta": {}}, f)
        vectors, _meta, model = _embed_index._load_npy()
        assert set(vectors) == {"a#h1", "c#h1"}
        assert model == "m"

    def test_load_npy_rejects_dim_mismatch(self, tmp_path, monkeypatch):
        """声明维度与矩阵实际维度不一致 → 整体拒绝（fail-closed）。"""
        self._patch_cache_paths(monkeypatch, tmp_path)
        np.save(_embed_index.EMBED_MATRIX_PATH,
                np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32))
        with open(_embed_index.EMBED_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"paths": ["a#h1", "b#h1"],
                       "model": "m", "dim": 7, "meta": {}}, f)
        vectors, _meta, _model = _embed_index._load_npy()
        assert vectors == {}

    def test_load_npy_dim_absent_backcompat(self, tmp_path, monkeypatch):
        """旧索引缺 dim 字段时不误杀（向后兼容）。"""
        self._patch_cache_paths(monkeypatch, tmp_path)
        np.save(_embed_index.EMBED_MATRIX_PATH,
                np.array([[0.1, 0.2]], dtype=np.float32))
        with open(_embed_index.EMBED_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"paths": ["a#h1"], "model": "m", "meta": {}}, f)
        vectors, _meta, _model = _embed_index._load_npy()
        assert set(vectors) == {"a#h1"}


# ===== P3-6：索引原子写（tmp + os.replace） =====

class TestAtomicIndexWrites:
    def test_bm25_index_atomic(self, tmp_path, monkeypatch):
        """bm25 pkl：tmp+replace 落盘，HMAC 校验仍通过，无 .tmp 残片。"""
        from _paths import safe_pickle_load
        index_path = str(tmp_path / "bm25_index.pkl")
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", index_path)
        _bm25.build_bm25_index(["a#h1"], ["蓝海多工厂排产问题"])
        assert os.path.exists(index_path)
        cache = safe_pickle_load(index_path)
        assert cache is not None
        assert cache["paths"] == ["a#h1"]
        assert cache["clients"] == [""]
        assert not os.path.exists(index_path + ".tmp")

    def test_snippet_index_atomic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snippet, "SNIPPETS_DIR", str(tmp_path / "snippets"))
        monkeypatch.setattr(_snippet, "INDEX_PATH",
                            str(tmp_path / "snippets" / "index.json"))
        assert _snippet.save_snippet("测试卡", "card", "<p>正文</p>", client="客户甲")
        with open(_snippet.INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
        assert index["snippets"][0]["name"] == "测试卡"
        assert not os.path.exists(_snippet.INDEX_PATH + ".tmp")

    def test_graph_write_atomic(self, tmp_path):
        """_write_graph 走 _atomic_write_json：内容可解析、无 .tmp 残片。"""
        gpath = tmp_path / "客户甲" / "client_graph.json"
        _graph._write_graph({"client": "客户甲", "nodes": [], "edges": []},
                            lambda c: str(gpath), lambda c: "", "客户甲")
        with open(gpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["client"] == "客户甲"
        assert not os.path.exists(str(gpath) + ".tmp")

    def test_add_graph_node_atomic(self, tmp_path, monkeypatch):
        """add_graph_node（手动节点写点）同样原子落盘。"""
        gpath = tmp_path / "client_graph.json"
        gpath.write_text(
            json.dumps({"client": "客户甲", "nodes": [], "edges": []},
                       ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "client_graph_path", lambda c: str(gpath))
        res = _graph.add_graph_node("客户甲", "decision", "手工节点", "摘要")
        assert res["node"]["id"].startswith("m")
        with open(gpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["nodes"]) == 1
        assert not os.path.exists(str(gpath) + ".tmp")

    def test_atomic_write_json_replaces_existing(self, tmp_path):
        """重复写入覆盖旧内容（os.replace 语义）。"""
        p = tmp_path / "x.json"
        _graph._atomic_write_json(str(p), {"v": 1})
        _graph._atomic_write_json(str(p), {"v": 2})
        with open(p, "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 2}
