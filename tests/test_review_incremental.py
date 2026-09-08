# -*- coding: utf-8 -*-
"""WP-A5 增量审查测试（2026-09-08 R1 波）。

覆盖：页切分与退化 / 基线选页 / 注入文本组装与预算降级 /
review_incremental 集成（首轮全量→增量→3 轮全量→ERROR 不刷快照）/
review_log review_mode 落账 / resolve_review_fn 分派。
"""
import json

import pytest

import _paths
import _review
import _review_incremental as ri

TWO_PAGE_HTML = """<html><head><style>body{color:red}</style></head><body>
<div class="ppt-page cover-page"><h1>第一页标题</h1><p>甲内容独特词组alpha</p></div>
<div class="ppt-page"><h1>第二页标题</h1><p>乙内容独特词组beta</p></div>
</body></html>"""

PASS_PAYLOAD = json.dumps({"verdict": "PASS", "issues": [],
                           "scores": {"设计": 4, "原创": 4, "工艺": 4,
                                      "功能": 4, "结构": 4, "总分": 20},
                           "summary": "ok"}, ensure_ascii=False)


def _write_deck(tmp_path, body_beta="乙内容独特词组beta", name="deck.html"):
    html = TWO_PAGE_HTML.replace("乙内容独特词组beta", body_beta)
    out = tmp_path / name
    out.write_text(html, encoding="utf-8")
    return str(out)


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """隔离三件：LLM 捕获 / review_log+快照路径 / budget 路径（wave1 先例）。"""
    import _cloud_llm
    captured = {"prompts": []}

    def fake_chat(**kwargs):
        captured["prompts"].append(kwargs.get("prompt", ""))
        return PASS_PAYLOAD

    monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
    monkeypatch.setattr(_paths, "REVIEW_LOG", str(tmp_path / "review_log.json"))
    monkeypatch.setattr(_review, "_review_budget_path",
                        lambda: tmp_path / "review_budget.json")
    return captured, tmp_path


class TestSplitPages:
    def test_two_page_deck_splits(self, tmp_path):
        pages = ri.split_pages(_write_deck(tmp_path))
        assert pages is not None and len(pages) == 2
        assert [pk for pk, _ in pages] == ["p01", "p02"]
        assert "alpha" in pages[0][1] and "style" not in pages[0][1]

    def test_single_page_and_non_html_degrade(self, tmp_path):
        out = tmp_path / "single.html"
        out.write_text('<div class="ppt-page">only</div>', encoding="utf-8")
        assert ri.split_pages(str(out)) is None
        assert ri.split_pages("_review.py") is None
        assert ri.split_pages(str(tmp_path / "missing.html")) is None


class TestSelectAndCompose:
    def test_select_pages_by_hash(self, tmp_path):
        pages = ri.split_pages(_write_deck(tmp_path))
        baseline = {pk: ri.page_hash(t) for pk, t in pages}
        # p02 文本变了 → changed；p01 未变 → unchanged
        pages2 = ri.split_pages(_write_deck(tmp_path, body_beta="乙改丙了"))
        changed, unchanged = ri.select_pages(pages2, baseline, force_full=False)
        assert [pk for pk, _ in changed] == ["p02"]
        assert [pk for pk, _ in unchanged] == ["p01"]
        # force_full → 全部算变更
        changed_full, unchanged_full = ri.select_pages(pages2, baseline, True)
        assert len(changed_full) == 2 and unchanged_full == []

    def test_deleted_page_drops_out(self, tmp_path):
        pages2 = ri.split_pages(_write_deck(tmp_path))
        baseline = {f"p{i:02d}": ri.page_hash(t) for i, (p, t) in enumerate(pages2, 1)}
        baseline["p09"] = "stale"  # 基线里的页在新文件被删
        changed, unchanged = ri.select_pages(pages2, baseline, False)
        assert "p09" not in [pk for pk, _ in changed + unchanged]

    def test_compose_marks_changed_full_and_digest_zone(self, tmp_path):
        pages = ri.split_pages(_write_deck(tmp_path, body_beta="乙改丙了"))
        changed = [p for p in pages if p[0] == "p02"]
        unchanged = [p for p in pages if p[0] == "p01"]
        text = ri.compose_llm_text(changed, unchanged)
        assert "本轮变更·全文" in text and "乙改丙了" in text
        assert "未变更页概览" in text and "p01" in text

    def test_compose_budget_downgrades(self):
        # 两个大页吃光合计预算后，第三个变更页降级为摘要（PAGE_TEXT_MAX_CHARS
        # 先行截断单页，合计预算决定第 N 页装不装得下）
        big1 = ("p01", "字" * ri.PAGE_TEXT_MAX_CHARS)
        big2 = ("p02", "字" * ri.PAGE_TEXT_MAX_CHARS)
        text = ri.compose_llm_text([big1, big2, ("p03", "第三页内容")],
                                   [("p04", "未变更页")])
        assert "超预算降级摘要" in text and "第三页内容" in text


class TestReviewIncremental:
    def test_first_round_full_and_snapshot_written(self, isolated):
        captured, tmp_path = isolated
        deck = _write_deck(tmp_path)
        result = ri.review_incremental(deck, quiet=True)
        assert result["verdict"] == "PASS"
        assert result["review_mode"] == "full"
        snap = ri.load_snapshots()[deck]
        assert snap["round"] == 1
        assert set(snap["pages"]) == {"p01", "p02"}

    def test_second_round_incremental_uses_changed_only(self, isolated):
        captured, tmp_path = isolated
        deck = _write_deck(tmp_path)
        ri.review_incremental(deck, quiet=True)
        deck2 = _write_deck(tmp_path, body_beta="乙改丙了")
        result = ri.review_incremental(deck2, quiet=True)
        assert result["review_mode"] == "incremental"
        prompt = captured["prompts"][-1]
        assert "未变更页概览" in prompt        # p01 走轻摘要
        assert "乙改丙了" in prompt            # p02 变更页全文
        assert ri.load_snapshots()[deck2]["round"] == 2

    def test_third_round_forces_full(self, isolated):
        captured, tmp_path = isolated
        deck = _write_deck(tmp_path)
        ri.review_incremental(deck, quiet=True)   # round 1（无基线→全量）
        data = ri.load_snapshots()
        data[deck]["round"] = 2                   # 人为推进到第 3 轮前夜
        ri.save_snapshots(data)
        result = ri.review_incremental(deck, quiet=True)
        assert result["review_mode"] == "full"    # (2+1)%3==0 → 强制全量
        assert ri.load_snapshots()[deck]["round"] == 3

    def test_error_verdict_keeps_snapshot(self, isolated, monkeypatch):
        captured, tmp_path = isolated
        import _cloud_llm

        def boom(**kwargs):
            return None
        monkeypatch.setattr(_cloud_llm, "chat", boom)
        deck = _write_deck(tmp_path)
        result = ri.review_incremental(deck, quiet=True)
        assert result["verdict"] == "ERROR"
        assert deck not in ri.load_snapshots()    # ERROR 不落基线

    def test_review_mode_written_to_review_log(self, isolated):
        captured, tmp_path = isolated
        deck = _write_deck(tmp_path)
        ri.review_incremental(deck, quiet=True)
        entries = json.loads((tmp_path / "review_log.json").read_text(encoding="utf-8"))
        assert entries[-1]["review_mode"] == "full"


class TestResolveDispatch:
    def _args(self, **kw):
        base = {"incremental": False, "screenshot": False,
                "adversarial": False, "parallel": False}
        base.update(kw)

        class A:
            pass
        a = A()
        for k, v in base.items():
            setattr(a, k, v)
        return a

    def test_incremental_priority_and_exclusivity(self):
        fn, notice = _review.resolve_review_fn(self._args(incremental=True, parallel=True))
        assert fn.__name__ == "review_incremental" and "增量" in notice

    def test_default_returns_serial_review(self):
        fn, notice = _review.resolve_review_fn(self._args())
        assert fn.__name__ == "review" and notice is None
