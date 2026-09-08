# -*- coding: utf-8 -*-
"""BM25 强信号保底席位（_apply_bm25_seats）单测。

机制来源：gq006 型融合挤压治理，golden 消融裁决 2026-09-05
（docs/gq006保底席位消融_实施报告_2026-09-05.md）。
纯函数测试，零 API 调用。
"""

from _recall import _apply_bm25_seats


def _mk(prefix, n, base_score, step=1.0):
    """造 n 个 chunk：prefix#p0..p{n-1}，分数递减。"""
    return [(f"{prefix}#p{i}", base_score - i * step) for i in range(n)]


class TestGate:
    """门控：第 N 席 BM25 分数 < ratio × top1 时零干预。"""

    def test_gate_closed_returns_input_unchanged(self):
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 90.0), ("c.md#p0", 80.0)]
        results = [("x.md#p0", 0.2), ("y.md#p0", 0.15), ("z.md#p0", 0.1)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out == results

    def test_gate_boundary_inclusive(self):
        # 第 3 席分数恰好 == 0.95 × top1 → 门控通过
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 96.0), ("c.md#p0", 95.0)]
        results = [("a.md#p0", 0.2), ("b.md#p0", 0.15), ("z.md#p0", 0.1),
                   ("c.md#p0", 0.05)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out[2][0] == "c.md#p0"

    def test_top1_zero_score_noop(self):
        bm25_leg = [("a.md#p0", 0.0), ("b.md#p0", 0.0), ("c.md#p0", 0.0)]
        results = [("x.md#p0", 0.2)]
        assert _apply_bm25_seats(results, bm25_leg) == results

    def test_fewer_docs_than_top_docs_noop(self):
        bm25_leg = [("a.md#p0", 100.0), ("a.md#p1", 99.0), ("b.md#p0", 98.0)]
        results = [("x.md#p0", 0.2), ("y.md#p0", 0.15)]
        # 去重后只有 2 个文档 < top_docs=3 → 零干预
        assert _apply_bm25_seats(results, bm25_leg, top_docs=3) == results

    def test_empty_inputs(self):
        assert _apply_bm25_seats([], [("a#p0", 1.0)]) == []
        assert _apply_bm25_seats([("a#p0", 1.0)], []) == [("a#p0", 1.0)]
        assert _apply_bm25_seats(None, None) is None


class TestSeatEnforcement:
    """席位保障：门控通过后，缺席文档替换 top_n 内最低位非席位文档。"""

    def test_missing_seat_displaces_lowest_non_seat(self):
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("c.md#p0", 98.0)]
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("z.md#p0", 0.12),
                   ("c.md#p0", 0.05)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert [p for p, _ in out[:3]] == ["a.md#p0", "b.md#p0", "c.md#p0"]
        # 消融语义（P1-4）：被替换项原地丢弃，不再插回顺位后移
        assert not any(p == "z.md#p0" for p, _ in out)

    def test_multiple_missing_seats_all_present_in_top_n(self):
        """P1-4 回归：多席位依次落位时不得互相驱逐（曾因插回 displaced
        使列表变长，把已入席文档挤出 top_n）。断言 seat_docs ⊆ top_n。"""
        bm25_leg = [("s1.md#p0", 100.0), ("s2.md#p0", 99.0), ("s3.md#p0", 98.0)]
        results = [("s1.md#p0", 0.20), ("x1.md#p0", 0.15), ("x2.md#p0", 0.12),
                   ("s2.md#p0", 0.08), ("s3.md#p0", 0.05)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        top_docs = {p.split("#")[0] for p, _ in out[:3]}
        assert top_docs == {"s1.md", "s2.md", "s3.md"}

    def test_seat_already_in_top_n_noop(self):
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("c.md#p0", 98.0)]
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("c.md#p0", 0.12)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out == results

    def test_seat_uses_best_chunk_and_drops_duplicate_anchor(self):
        # 席位文档在 results 中有多个 chunk：用最高位 chunk 入席，
        # 入席位置之后的同文档 chunk 被剔除（防同文档双占位）
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("c.md#p1", 98.0)]
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("z.md#p0", 0.12),
                   ("c.md#p1", 0.06), ("c.md#p5", 0.04)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out[2] == ("c.md#p1", 0.06)
        assert sum(1 for p, _ in out if p.startswith("c.md")) == 1

    def test_seat_doc_not_in_results_skipped(self):
        # BM25 有该文档但融合结果里没有（被过滤），席位无从落实
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("ghost.md#p0", 98.0)]
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("z.md#p0", 0.12)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out == results

    def test_top_docs_1(self):
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 10.0)]
        results = [("x.md#p0", 0.20), ("y.md#p0", 0.15), ("z.md#p0", 0.12),
                   ("a.md#p0", 0.05)]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=1, min_score_ratio=0.95, top_n=3)
        assert out[2] == ("a.md#p0", 0.05)


class TestGq006Scenario:
    """gq006 融合挤压现场复刻：BM25 前三文档近并列（65.7/64.2/64.1），
    expect 文档被双路支撑的泛词文档挤到融合第 7 → 保底席位拉回 top3。"""

    def test_gq006_like_squeeze_rescued(self):
        bm25_leg = [
            ("需求清单.xlsx#sheet0#row85", 65.7),
            ("慧报账.docx#p1", 64.2),
            ("业务解决方案.docx#p8", 64.1),   # expect
            ("预算模块清单.xlsx#sheet0#row6", 62.7),
        ]
        results = [  # boost+dedup 后的融合序（gq006 实测结构）
            ("需求清单.xlsx#sheet0#row46", 0.1458),
            ("慧报账.docx#p1", 0.1250),
            ("06-17预算编制.docx#p0", 0.1204),
            ("预算模块清单.xlsx#sheet0#row5", 0.1193),
            ("业务解决方案.docx#p8", 0.0769),
        ]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert [p.split("#")[0] for p, _ in out[:3]] == [
            "需求清单.xlsx", "慧报账.docx", "业务解决方案.docx"]

    def test_weak_bm25_signal_no_rescue(self):
        # BM25 头部非并列（强 top1 独大）→ 门控关闭，embedding 路结论不被打扰
        bm25_leg = [
            ("需求清单.xlsx#sheet0#row85", 65.7),
            ("慧报账.docx#p1", 50.0),
            ("业务解决方案.docx#p8", 40.0),
        ]
        results = [
            ("需求清单.xlsx#sheet0#row46", 0.1458),
            ("慧报账.docx#p1", 0.1250),
            ("06-17预算编制.docx#p0", 0.1204),
            ("业务解决方案.docx#p8", 0.0769),
        ]
        out = _apply_bm25_seats(results, bm25_leg,
                                top_docs=3, min_score_ratio=0.95)
        assert out == results


class TestSingleQueryGate:
    """P1-5 回归：席位仅在单查询链路启用，按 len(_queries)==1 判定——
    双查询（低置信改写双路）即使一路空结果也不启用（曾按 len(_groups)==1
    误判为单查询形态）。mock 整条 recall 链，零 API 调用。"""

    _CFG = {
        "bm25_seat": {"enabled": True, "top_docs": 3, "min_score_ratio": 0.95},
        "query_rewrite": {"enabled": False},
        "rrf": {"k": 60},
        "dedup": {"enabled": True, "max_per_doc": 1},
        "rerank": {"top_k": 3},
    }

    @staticmethod
    def _s(results, bm25_leg):
        return {"results": results, "mode": "BM25", "degraded": False,
                "cross_client_filtered": 0, "bm25_leg": bm25_leg}

    def _run_recall(self, monkeypatch, retrieve_results, rewritten=None):
        import _compress
        import _recall
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", self._CFG)
        monkeypatch.setattr(_recall, "_single_query_retrieve",
                            lambda *a, **kw: retrieve_results)
        monkeypatch.setattr(_recall, "_read_snippet", lambda *a, **kw: "")
        monkeypatch.setattr(_compress, "extract_attention", lambda *a, **kw: "")
        if rewritten is not None:
            monkeypatch.setattr(_recall, "_RECALL_CONFIG",
                                dict(self._CFG,
                                     query_rewrite={"enabled": True}))
            import _query_rewrite
            monkeypatch.setattr(_query_rewrite, "rewrite_query",
                                lambda *a, **kw: rewritten)
        return _recall.recall("测试查询", rerank=False, use_embedding=False,
                              use_query_rewrite=rewritten is not None,
                              return_results=True)

    def test_single_query_seats_applied(self, monkeypatch):
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("x.md#p0", 0.12),
                   ("c.md#p0", 0.08)]
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("c.md#p0", 98.0)]
        out = self._run_recall(monkeypatch, self._s(results, bm25_leg))
        top_docs = [e["path"].split("#")[0] for e in out[:3]]
        assert top_docs == ["a.md", "b.md", "c.md"]

    def test_dual_query_one_empty_leg_no_seats(self, monkeypatch):
        """双查询一路空：len(_queries)==2 → 席位跳过，单路结果原序。"""
        results = [("a.md#p0", 0.20), ("b.md#p0", 0.15), ("x.md#p0", 0.12),
                   ("c.md#p0", 0.08)]
        bm25_leg = [("a.md#p0", 100.0), ("b.md#p0", 99.0), ("c.md#p0", 98.0)]
        empty = self._s([], [])
        # 第一路返回完整结果，第二路（改写查询）返回空
        outputs = [self._s(results, bm25_leg), empty]
        import _recall
        monkeypatch.setattr(_recall, "_single_query_retrieve",
                            lambda *a, **kw: outputs.pop(0))
        out = self._run_recall(
            monkeypatch, self._s(results, bm25_leg),
            rewritten={"rewritten": "改写查询", "confidence": 0.3,
                       "changes": [], "degraded": []})
        top_docs = [e["path"].split("#")[0] for e in out[:3]]
        # 席位未启用：融合/单路原序 x.md 仍在 top3，c.md 未被拉入
        assert top_docs == ["a.md", "b.md", "x.md"]
