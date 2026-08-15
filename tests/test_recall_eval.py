# -*- coding: utf-8 -*-
"""recall-eval 评估器单测。

实施依据：docs/dev_plan_recall_eval_tasks_2026-07-19.md Issue 1+2+4
纪律：全程 monkeypatch mock `_session.recall`，零真实 API 调用。
"""

import json
import os

import pytest

from _recall_eval import (
    DEFAULT_TOLERANCES,
    FALLBACK_MARKER,
    compute_metrics,
    compare_baseline,
    detect_fallback,
    estimate_api_calls,
    is_hit,
    load_eval_set,
    normalize_path,
    run_eval,
    save_baseline,
)


# ===== Issue 1：normalize_path =====


class TestNormalizePath:
    def test_backslash_to_slash(self):
        assert normalize_path(r"_knowledge\clients\a\b.docx") == "_knowledge/clients/a/b.docx"

    def test_dot_slash_prefix(self):
        assert normalize_path("./_knowledge/clients/a/b.docx") == "_knowledge/clients/a/b.docx"

    def test_anchor_suffix(self):
        assert normalize_path("_knowledge/clients/a/b.docx#p32") == "_knowledge/clients/a/b.docx"

    def test_anchor_session(self):
        assert normalize_path("refs/x.md#session1#section2") == "refs/x.md"

    def test_case_insensitive(self):
        assert normalize_path("_Knowledge/Clients/A/B.DOCX") == "_knowledge/clients/a/b.docx"

    def test_strip_whitespace(self):
        assert normalize_path("  _knowledge/a.docx  ") == "_knowledge/a.docx"

    def test_empty(self):
        assert normalize_path("") == ""
        assert normalize_path(None) == ""

    def test_double_dot_slash(self):
        # 多重 ./ 前缀也去干净
        assert normalize_path("././_knowledge/a.docx") == "_knowledge/a.docx"

    def test_absolute_path_strips_cwd_prefix(self, monkeypatch, tmp_path):
        """recall() 返回的 path 可能是绝对路径，expect 是相对路径，必须去 cwd 前缀才能匹配。"""
        monkeypatch.chdir(tmp_path)
        # 模拟 Windows 绝对路径
        cwd = str(tmp_path).replace("\\", "/")
        abs_path = cwd + "/_knowledge/clients/a/refs/x.docx#p3"
        assert normalize_path(abs_path) == "_knowledge/clients/a/refs/x.docx"

    def test_absolute_path_matches_relative_expect(self, monkeypatch, tmp_path):
        """端到端：绝对路径命中相对路径 expect。"""
        monkeypatch.chdir(tmp_path)
        cwd = str(tmp_path).replace("\\", "/")
        paths = [cwd + "/_knowledge/clients/蓝海集团/refs/a.docx#p1"]
        expect = ["_knowledge/clients/蓝海集团/refs/a.docx"]
        assert is_hit(paths, expect) == 0


# ===== Issue 1：load_eval_set =====


class TestLoadEvalSet:
    def test_load_valid(self, tmp_path):
        f = tmp_path / "q.yml"
        f.write_text(
            "- id: gq001\n"
            '  query: "蓝海集团预算"\n'
            "  client: 蓝海集团\n"
            "  expect:\n"
            '    - "_knowledge/clients/蓝海集团/refs/a.docx"\n'
            '  note: "费用"\n'
            "- id: gq002\n"
            '  query: "负样本"\n'
            "  expect: []\n",
            encoding="utf-8",
        )
        items = load_eval_set(str(f))
        assert len(items) == 2
        assert items[0]["id"] == "gq001"
        assert items[0]["client"] == "蓝海集团"
        assert items[0]["expect"] == ["_knowledge/clients/蓝海集团/refs/a.docx"]
        assert items[1]["client"] is None
        assert items[1]["expect"] == []

    def test_missing_id_raises(self, tmp_path):
        f = tmp_path / "bad.yml"
        f.write_text(
            "- query: 'q'\n  expect: []\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="缺字段 'id'"):
            load_eval_set(str(f))

    def test_missing_query_raises(self, tmp_path):
        f = tmp_path / "bad.yml"
        f.write_text(
            "- id: gq1\n  expect: []\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="缺字段 'query'"):
            load_eval_set(str(f))

    def test_missing_expect_raises(self, tmp_path):
        f = tmp_path / "bad.yml"
        f.write_text(
            "- id: gq1\n  query: 'q'\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="缺字段 'expect'"):
            load_eval_set(str(f))

    def test_expect_not_list_raises(self, tmp_path):
        f = tmp_path / "bad.yml"
        f.write_text(
            "- id: gq1\n  query: 'q'\n  expect: 'not_a_list'\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="expect 必须是 list"):
            load_eval_set(str(f))

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_eval_set(str(tmp_path / "nope.yml"))

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.yml"
        f.write_text("", encoding="utf-8")
        assert load_eval_set(str(f)) == []


# ===== Issue 1：is_hit =====


class TestIsHit:
    def test_hit_at_rank_0(self):
        paths = ["_knowledge/clients/a/refs/x.docx#p1"]
        expect = ["_knowledge/clients/a/refs/x.docx"]
        assert is_hit(paths, expect) == 0

    def test_hit_at_rank_2(self):
        paths = [
            "_knowledge/clients/a/refs/y.docx",
            "_knowledge/clients/a/refs/z.docx",
            "_knowledge/clients/a/refs/x.docx",
        ]
        expect = ["_knowledge/clients/a/refs/x.docx"]
        assert is_hit(paths, expect) == 2

    def test_miss(self):
        paths = ["_knowledge/clients/a/refs/y.docx"]
        expect = ["_knowledge/clients/a/refs/x.docx"]
        assert is_hit(paths, expect) is None

    def test_negative_sample_always_none(self):
        # expect 为空 -> 永远 None
        paths = ["_knowledge/clients/a/refs/y.docx"]
        assert is_hit(paths, []) is None
        assert is_hit(paths, None) is None

    def test_backslash_path_matches(self):
        paths = [r"_knowledge\clients\a\refs\x.docx#p3"]
        expect = ["_knowledge/clients/a/refs/x.docx"]
        assert is_hit(paths, expect) == 0

    def test_case_insensitive_match(self):
        paths = ["_Knowledge/Clients/A/Refs/X.DOCX"]
        expect = ["_knowledge/clients/a/refs/x.docx"]
        assert is_hit(paths, expect) == 0

    def test_multiple_expect_any_match(self):
        paths = ["_knowledge/clients/a/refs/b.docx"]
        expect = ["_knowledge/clients/a/refs/a.docx", "_knowledge/clients/a/refs/b.docx"]
        assert is_hit(paths, expect) == 0

    def test_first_match_wins(self):
        # 同一结果列表中两个 expect 都出现，返回更靠前的排位
        paths = ["a.docx", "b.docx"]
        expect = ["b.docx", "a.docx"]
        assert is_hit(paths, expect) == 0


# ===== Issue 1：detect_fallback =====


class TestDetectFallback:
    def test_positive(self):
        buf = f"[RRF 最高分 0.0300 < 阈值 0.05, {FALLBACK_MARKER}]"
        assert detect_fallback(buf) is True

    def test_negative(self):
        buf = "[recall] 命中 5 条结果"
        assert detect_fallback(buf) is False

    def test_empty(self):
        assert detect_fallback("") is False
        assert detect_fallback(None) is False


# ===== Issue 1：compute_metrics =====


class TestComputeMetrics:
    def test_full_hit_at_1(self):
        per_query = [
            {
                "id": "gq1",
                "query": "q1",
                "expect": ["a.docx"],
                "is_negative": False,
                "results": [{"path": "a.docx"}],
                "hit_rank": 0,
                "fallback": False,
                "error": None,
            },
            {
                "id": "gq2",
                "query": "q2",
                "expect": ["b.docx"],
                "is_negative": False,
                "results": [{"path": "b.docx"}],
                "hit_rank": 0,
                "fallback": False,
                "error": None,
            },
        ]
        m = compute_metrics(per_query)
        assert m["total"] == 2
        assert m["hit_at_1"] == 1.0
        assert m["hit_at_3"] == 1.0
        assert m["mrr"] == 1.0
        assert m["misses"] == []

    def test_partial_hit(self):
        # gq1 rank 0, gq2 rank 2, gq3 miss
        per_query = [
            {"id": "gq1", "query": "q1", "expect": ["a"], "is_negative": False,
             "results": [{"path": "a"}], "hit_rank": 0, "fallback": False, "error": None},
            {"id": "gq2", "query": "q2", "expect": ["b"], "is_negative": False,
             "results": [{"path": "x"}, {"path": "y"}, {"path": "b"}],
             "hit_rank": 2, "fallback": False, "error": None},
            {"id": "gq3", "query": "q3", "expect": ["c"], "is_negative": False,
             "results": [{"path": "z"}], "hit_rank": None, "fallback": False, "error": None},
        ]
        m = compute_metrics(per_query)
        assert m["total"] == 3
        # hit@1 = 1/3
        assert m["hit_at_1"] == round(1 / 3, 4)
        # hit@3 = 2/3（gq1 + gq2）
        assert m["hit_at_3"] == round(2 / 3, 4)
        # MRR = (1/1 + 1/3) / 3
        assert m["mrr"] == round((1.0 + 1.0 / 3) / 3, 4)
        assert len(m["misses"]) == 1
        assert m["misses"][0]["id"] == "gq3"

    def test_negative_samples(self):
        per_query = [
            # 负样本 1：无命中，通过
            {"id": "n1", "query": "q", "expect": [], "is_negative": True,
             "results": [], "hit_rank": None, "fallback": False, "error": None},
            # 负样本 2：触发降级，通过
            {"id": "n2", "query": "q", "expect": [], "is_negative": True,
             "results": [{"path": "x"}], "hit_rank": 0, "fallback": True, "error": None},
            # 负样本 3：有命中且未降级，不通过
            {"id": "n3", "query": "q", "expect": [], "is_negative": True,
             "results": [{"path": "x"}], "hit_rank": 0, "fallback": False, "error": None},
        ]
        m = compute_metrics(per_query)
        assert m["total"] == 0
        assert m["neg_total"] == 3
        assert m["neg_pass_no_hit"] == 1
        assert m["neg_pass_fallback"] == 1
        assert m["neg_fail"] == 1
        assert m["hit_at_1"] == 0.0
        assert m["hit_at_3"] == 0.0

    def test_error_items_skip_metrics(self):
        per_query = [
            {"id": "gq1", "query": "q1", "expect": ["a"], "is_negative": False,
             "results": [{"path": "a"}], "hit_rank": 0, "fallback": False, "error": None},
            {"id": "gq2", "query": "q2", "expect": ["b"], "is_negative": False,
             "results": [], "hit_rank": None, "fallback": False, "error": "RuntimeError: boom"},
        ]
        m = compute_metrics(per_query)
        assert m["total"] == 1  # 失败条目不计入 total
        assert m["hit_at_1"] == 1.0
        assert len(m["misses"]) == 1
        assert m["misses"][0]["error"] == "RuntimeError: boom"


# ===== Issue 2：run_eval =====


class TestRunEval:
    def test_basic_run(self, monkeypatch):
        """mock recall，断言 per_query 结构和 metrics 聚合正确。"""
        eval_set = [
            {"id": "gq1", "query": "q1", "client": "蓝海集团",
             "expect": ["_knowledge/clients/蓝海集团/refs/a.docx"], "note": ""},
            {"id": "gq2", "query": "q2", "client": None, "expect": [], "note": ""},
        ]

        def fake_recall(query, **kwargs):
            if query == "q1":
                return [{"client": "蓝海集团", "score": 0.9,
                         "path": "_knowledge/clients/蓝海集团/refs/a.docx#p1",
                         "snippet": "..."}]
            return None  # 负样本：无命中

        monkeypatch.setattr("_session.recall", fake_recall)

        result = run_eval(eval_set, rerank=False, use_embedding=True)
        assert result["chain"] == "rrf"
        assert result["config"]  # 配置快照非空
        assert len(result["per_query"]) == 2

        entry1 = result["per_query"][0]
        assert entry1["hit_rank"] == 0
        assert entry1["is_negative"] is False
        assert entry1["fallback"] is False
        assert entry1["error"] is None

        entry2 = result["per_query"][1]
        assert entry2["hit_rank"] is None
        assert entry2["is_negative"] is True

        m = result["metrics"]
        assert m["total"] == 1
        assert m["hit_at_1"] == 1.0
        assert m["hit_at_3"] == 1.0
        assert m["mrr"] == 1.0
        assert m["neg_total"] == 1
        assert m["neg_pass_no_hit"] == 1

    def test_negative_pass_via_fallback(self, monkeypatch):
        """负样本触发降级 -> neg_pass_fallback。"""
        eval_set = [{"id": "n1", "query": "q", "client": None,
                     "expect": [], "note": ""}]

        def fake_recall(query, **kwargs):
            print(f"[RRF 最高分 0.0300 < 阈值 0.05, {FALLBACK_MARKER}]")
            return [{"client": "x", "score": 0.03,
                     "path": "x.docx", "snippet": "..."}]

        monkeypatch.setattr("_session.recall", fake_recall)
        result = run_eval(eval_set)
        assert result["per_query"][0]["fallback"] is True
        # 负样本 expect 为空 -> is_hit 永远 None（按设计），不参与 hit_rank 判定
        assert result["per_query"][0]["hit_rank"] is None
        m = result["metrics"]
        assert m["neg_pass_fallback"] == 1
        assert m["neg_pass_no_hit"] == 0

    def test_single_failure_does_not_abort(self, monkeypatch):
        """单条 raise -> error 入列，后续继续。"""
        eval_set = [
            {"id": "gq1", "query": "q1", "client": None,
             "expect": ["a.docx"], "note": ""},
            {"id": "gq2", "query": "q2", "client": None,
             "expect": ["b.docx"], "note": ""},
        ]
        call_count = {"n": 0}

        def fake_recall(query, **kwargs):
            call_count["n"] += 1
            if query == "q1":
                raise RuntimeError("boom")
            return [{"client": "x", "score": 0.9,
                     "path": "b.docx", "snippet": "..."}]

        monkeypatch.setattr("_session.recall", fake_recall)
        result = run_eval(eval_set)
        assert call_count["n"] == 2  # 两条都调过
        assert result["per_query"][0]["error"] == "RuntimeError: boom"
        assert result["per_query"][1]["hit_rank"] == 0

    def test_limit(self, monkeypatch):
        eval_set = [
            {"id": f"gq{i}", "query": f"q{i}", "client": None,
             "expect": ["a.docx"], "note": ""}
            for i in range(5)
        ]
        monkeypatch.setattr(
            "_session.recall", lambda *a, **kw: [{"path": "a.docx"}]
        )
        result = run_eval(eval_set, limit=2)
        assert len(result["per_query"]) == 2

    def test_chain_naming(self, monkeypatch):
        eval_set = [{"id": "gq1", "query": "q", "client": None,
                     "expect": ["a.docx"], "note": ""}]
        monkeypatch.setattr(
            "_session.recall", lambda *a, **kw: [{"path": "a.docx"}]
        )
        assert run_eval(eval_set)["chain"] == "rrf"
        assert run_eval(eval_set, rerank=True)["chain"] == "rerank"
        assert run_eval(eval_set, use_embedding=False)["chain"] == "bm25_only"

    def test_no_real_api_calls(self, monkeypatch):
        """安全网：recall 必须 mock，禁止真实 API 请求。"""
        called = {"n": 0}

        def fake_recall(*a, **kw):
            called["n"] += 1
            return None

        monkeypatch.setattr("_session.recall", fake_recall)
        eval_set = [{"id": "gq1", "query": "q", "client": None,
                     "expect": [], "note": ""}]
        run_eval(eval_set, rerank=True)  # 即便 rerank=True，也只调 recall 一次
        assert called["n"] == 1


# ===== Issue 4：baseline + gate =====


class TestBaseline:
    def test_save_and_compare_pass(self, tmp_path):
        baseline_path = tmp_path / "baseline.json"
        report = {
            "config": {"rrf": {"k": 10}},
            "chains": {
                "rrf": {"hit_at_3": 0.85, "mrr": 0.70},
                "rerank": {"hit_at_3": 0.90, "mrr": 0.80},
            },
        }
        save_baseline(report, path=str(baseline_path))
        assert baseline_path.exists()
        saved = json.loads(baseline_path.read_text(encoding="utf-8"))
        assert saved["chains"]["rrf"]["hit_at_3"] == 0.85
        assert saved["tolerances"]["hit_at_3"] == DEFAULT_TOLERANCES["hit_at_3"]

        # 当前指标轻微下降但在容差内
        current = {
            "rrf": {"hit_at_3": 0.82, "mrr": 0.68},
            "rerank": {"hit_at_3": 0.90, "mrr": 0.80},
        }
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        passed, diffs = compare_baseline(current, baseline)
        assert passed is True
        # 4 项比较（2 链路 × 2 指标）
        assert len(diffs) == 4

    def test_compare_fail_when_beyond_tolerance(self, tmp_path):
        baseline = {
            "tolerances": {"hit_at_3": 0.05, "mrr": 0.05},
            "chains": {
                "rrf": {"hit_at_3": 0.85, "mrr": 0.70},
            },
        }
        # Hit@3 下降 0.10 > 0.05 容差 -> fail
        current = {"rrf": {"hit_at_3": 0.75, "mrr": 0.70}}
        passed, diffs = compare_baseline(current, baseline)
        assert passed is False
        assert any(
            d["metric"] == "hit_at_3" and d["passed"] is False for d in diffs
        )

    def test_baseline_tolerances_override_default(self, tmp_path):
        """baseline.json 自带的 tolerances 优先于默认值。"""
        baseline = {
            "tolerances": {"hit_at_3": 0.20, "mrr": 0.05},  # hit_at_3 容差 0.20
            "chains": {"rrf": {"hit_at_3": 0.85, "mrr": 0.70}},
        }
        # 下降 0.10，默认容差 0.05 会 fail，但 baseline 自带 0.20 应通过
        current = {"rrf": {"hit_at_3": 0.75, "mrr": 0.70}}
        passed, _ = compare_baseline(current, baseline)
        assert passed is True

    def test_missing_chain_skipped(self):
        """baseline 没有的链路跳过，不算回归。"""
        baseline = {"tolerances": {}, "chains": {"rrf": {"hit_at_3": 0.85, "mrr": 0.70}}}
        current = {
            "rrf": {"hit_at_3": 0.85, "mrr": 0.70},
            "rerank": {"hit_at_3": 0.10, "mrr": 0.10},  # baseline 没此链路
        }
        passed, diffs = compare_baseline(current, baseline)
        assert passed is True
        # 只比 rrf 链路 2 项
        assert len(diffs) == 2


# ===== Issue 4：成本守门 helper =====


class TestEstimateApiCalls:
    def test_rrf_chain(self):
        # embedding 调用 = n
        assert estimate_api_calls(10, rerank=False, use_embedding=True) == 10

    def test_rerank_chain(self):
        # embedding + rerank = 2n
        assert estimate_api_calls(10, rerank=True, use_embedding=True) == 20

    def test_bm25_only(self):
        # 0 次
        assert estimate_api_calls(10, rerank=False, use_embedding=False) == 0


# ===== Issue 3：CLI 命令 recall-eval =====


class TestCliRecallEval:
    """CLI recall-eval 命令的错误路径与成本守门。
    run_eval 必须 mock，禁止真实 API 请求。
    """

    def test_parser_registered(self):
        """命令在 parser 与 dispatch 中均注册（TestParserDispatchConsistency 自动覆盖一致性）。"""
        import _cli

        parser = _cli.build_parser()
        sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
        assert "recall-eval" in sub.choices
        assert "recall-eval" in _cli._build_dispatch()

    def test_help_works(self, monkeypatch):
        """--help 能正常打印，证明命令注册完整可被 argparse 接受。"""
        import _cli

        monkeypatch.setattr("sys.argv", ["_cli.py", "recall-eval", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            _cli.main()
        # argparse --help 退出码 0
        assert exc_info.value.code == 0

    def test_missing_eval_file_exits_1(self, monkeypatch, tmp_path):
        import _cli

        # 用不存在的 --file，跳过默认路径查找
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(tmp_path / "nope.yml")],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _cli.main()
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert exc_info.value.code == 1

    def test_empty_eval_set_exits_1(self, monkeypatch, tmp_path):
        """评估集为空 -> exit 1（不是测试无内容，是显式拒绝）。"""
        import _cli

        empty_yml = tmp_path / "empty.yml"
        empty_yml.write_text("[]", encoding="utf-8")
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(empty_yml)],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _cli.main()
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert exc_info.value.code == 1

    def test_cost_guard_exits_1_without_yes(self, monkeypatch, tmp_path):
        """预估 >50 次云端调用且无 --yes -> exit 1。
        构造 26 条 × 2 链路（rrf+rerank）= 52 次 embedding + 26 rerank = 78 次 > 50。
        """
        import _cli

        yml = tmp_path / "q.yml"
        items = []
        for i in range(26):
            items.append(
                f"- id: gq{i}\n  query: q{i}\n  expect:\n    - a{i}.docx\n"
            )
        yml.write_text("".join(items), encoding="utf-8")

        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(yml), "--rerank"],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _cli.main()
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert exc_info.value.code == 1

    def test_cost_guard_passes_with_yes(self, monkeypatch, tmp_path):
        """有 --yes 时通过成本守门，run_eval 被 mock 不会真实调 API。"""
        import _cli

        yml = tmp_path / "q.yml"
        yml.write_text(
            "- id: gq1\n  query: q1\n  expect:\n    - a.docx\n",
            encoding="utf-8",
        )

        # mock run_eval 不实际跑 recall
        def fake_run_eval(eval_set, *, rerank=False, use_embedding=True, limit=None):
            return {
                "chain": "rerank" if rerank else ("bm25_only" if not use_embedding else "rrf"),
                "config": {"rrf": {"k": 10}},
                "per_query": [],
                "metrics": {
                    "total": 0, "hit_at_1": 0.0, "hit_at_3": 0.0, "mrr": 0.0,
                    "neg_total": 0, "neg_pass_no_hit": 0,
                    "neg_pass_fallback": 0, "neg_fail": 0, "misses": [],
                },
            }

        monkeypatch.setattr("_recall_eval.run_eval", fake_run_eval)
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(yml), "--rerank", "--yes"],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            _cli.main()
            code = None
        except SystemExit as e:
            code = e.code
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        # 正常路径允许 0 退出或 None
        assert code in (None, 0)

    def test_bm25_only_no_cost_guard(self, monkeypatch, tmp_path):
        """bm25_only 链路 0 API 调用，但默认 rrf 链路仍跑。
        用 40 条评估集（40 次 embedding < 50）避免 rrf 守门触发，
        专注验证 bm25_only 加跑链路本身不增加成本。
        """
        import _cli

        yml = tmp_path / "q.yml"
        items = [
            f"- id: gq{i}\n  query: q{i}\n  expect:\n    - a{i}.docx\n"
            for i in range(40)
        ]
        yml.write_text("".join(items), encoding="utf-8")

        def fake_run_eval(eval_set, *, rerank=False, use_embedding=True, limit=None):
            return {
                "chain": "bm25_only",
                "config": {},
                "per_query": [],
                "metrics": {
                    "total": 0, "hit_at_1": 0.0, "hit_at_3": 0.0, "mrr": 0.0,
                    "neg_total": 0, "neg_pass_no_hit": 0,
                    "neg_pass_fallback": 0, "neg_fail": 0, "misses": [],
                },
            }

        monkeypatch.setattr("_recall_eval.run_eval", fake_run_eval)
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(yml), "--no-embedding"],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            _cli.main()
            code = None
        except SystemExit as e:
            code = e.code
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        # bm25_only 0 次调用，不应被成本守门拦截
        assert code in (None, 0)
