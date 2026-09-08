# -*- coding: utf-8 -*-
"""S9 阶段 2 后验门回归（2a 截图对抗审视 + 2d crafted×review 组合门禁）。

全程 monkeypatch：playwright / VLM / LLM 一律打桩，不真实外呼；
日志与预算状态文件 monkeypatch 到 tmp_path，不触真实 .folio/logs。

2a 覆盖：3 轮上限判定函数、预算熔断联动、playwright/VLM 缺失显式降级、
三秒测试主门 FAIL/PASS 判定、CLI --screenshot 接线。
2d 覆盖：组合路由四态（crafted+无记录→deliver 阻断 / crafted+PASS→放行 /
非 crafted→不受影响 / 独立 build→warn 不阻断）。
"""

import json
import os
import sys

import pytest
import yaml

import _paths
import _review
import _review_gate
import _review_screenshot


# ---------------------------------------------------------------------------
# 公共夹具：日志/预算 tmp 隔离 + 产物构造
# ---------------------------------------------------------------------------

def _isolate(monkeypatch, tmp_path):
    """review_log 与 review_budget 全部指向 tmp（对齐 test_review_wave1._isolate）。"""
    monkeypatch.setattr(_paths, "REVIEW_LOG", str(tmp_path / "review_log.json"))
    monkeypatch.setattr(_review, "_review_budget_path",
                        lambda: str(tmp_path / "review_budget.json"))


def _make_html(tmp_path, crafted=False, name="deck.html"):
    """构造产物 HTML；crafted=True 时带 data-track 边界标记（1c 口径）。"""
    marker = ' data-track="crafted"' if crafted else ""
    out = tmp_path / name
    out.write_text(
        f"<html><body><div{marker}>定制页</div><p>正文</p></body></html>",
        encoding="utf-8")
    return str(out)


def _make_spec(tmp_path, crafted=True, name="spec.yml"):
    """构造 spec；crafted=True 时含 raw_html 元素页（collect_crafted_pages 硬信号）。"""
    element = ({"type": "raw_html", "content": "<div>核心图</div>"}
               if crafted else {"type": "text", "content": "普通文字"})
    spec = {"theme": "generic", "pages": [
        {"id": "p1", "title": "封面", "elements": [{"type": "text", "content": "x"}]},
        {"id": "p2", "title": "核心页", "elements": [element]},
    ]}
    path = tmp_path / name
    path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(path)


def _write_pass_entry(monkeypatch, output_path, mode="adversarial"):
    """向（已隔离的）review_log 写一条该产物的 PASS 记录。"""
    result = {"verdict": "PASS", "issues": [], "summary": "ok", "mode": mode}
    _review.write_review_log(result, output_path, "客户甲")


_VLM_PASS_JSON = json.dumps({
    "three_second": "PASS", "three_second_conclusion": "云原生降本三成",
    "antipatterns": [], "coherence": [],
    "verdict": "PASS", "issues": [], "summary": "未发现问题",
}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 2a-1：3 轮修正上限判定函数（单一事实源 _review.screenshot_round_decision）
# ---------------------------------------------------------------------------

class TestRoundLimit:
    def test_constant_is_three(self):
        assert _review.SCREENSHOT_MAX_ROUNDS == 3

    def test_below_cap_allows_redispatch(self):
        d0 = _review.screenshot_round_decision(0)
        assert d0["action"] == "allow" and d0["rounds_left"] == 3
        d2 = _review.screenshot_round_decision(2)
        assert d2["action"] == "allow" and d2["rounds_left"] == 1

    def test_at_cap_fuses(self):
        d = _review.screenshot_round_decision(3)
        assert d["action"] == "fuse" and d["rounds_left"] == 0
        assert "3 轮" in d["reason"] and "人工" in d["reason"]

    def test_over_cap_fuses(self):
        assert _review.screenshot_round_decision(5)["action"] == "fuse"

    def test_negative_input_clamped_to_allow(self):
        assert _review.screenshot_round_decision(-1)["action"] == "allow"


# ---------------------------------------------------------------------------
# 2a-2：预算熔断联动（复用 S6 review_budget，mock 预算状态）
# ---------------------------------------------------------------------------

class TestBudgetFuseLinkage:
    def test_budget_fused_no_vlm_call(self, monkeypatch, tmp_path):
        """同日连续 ≥3 次 ERROR → 熔断返回 ERROR，不发起 VLM 调用。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)

        def _boom(*a, **k):
            raise AssertionError("熔断状态下不得发起 VLM 调用")
        monkeypatch.setattr(_review_screenshot, "_vision_chat", _boom)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot", _boom)

        _review._write_budget("客户甲", {"date": _review._budget_date(),
                                        "consecutive_errors": 3})
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert result["verdict"] == "ERROR" and "熔断" in result["summary"]
        assert result["mode"] == "screenshot_adversarial"

    def test_vlm_error_accumulates_budget(self, monkeypatch, tmp_path):
        """VLM 不可得 → ERROR 且预算累加（2→3）。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            lambda p: [str(tmp_path / "shot.png")])
        monkeypatch.setattr(_review_screenshot, "_vision_chat", lambda *a, **k: "")
        _review._write_budget("客户甲", {"date": _review._budget_date(),
                                        "consecutive_errors": 2})
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert result["verdict"] == "ERROR"
        assert _review._read_budget("客户甲")["consecutive_errors"] == 3

    def test_pass_resets_budget(self, monkeypatch, tmp_path):
        """VLM PASS → 预算归零（残留计数清掉）。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            lambda p: [str(tmp_path / "shot.png")])
        monkeypatch.setattr(_review_screenshot, "_vision_chat",
                            lambda *a, **k: _VLM_PASS_JSON)
        _review._write_budget("客户甲", {"date": _review._budget_date(),
                                        "consecutive_errors": 1})
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", spec_path=_make_spec(tmp_path),
            quiet=True)
        assert result["verdict"] == "PASS"
        assert _review._read_budget("客户甲")["consecutive_errors"] == 0


# ---------------------------------------------------------------------------
# 2a-3：playwright / VLM 缺失显式降级（不佯装通过，#43 先例口径）
# ---------------------------------------------------------------------------

class TestDegradation:
    def test_playwright_missing_skips_explicitly(self, monkeypatch, tmp_path):
        """playwright 渲染不可用 → SKIP + 显式降级说明，绝不判 PASS。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)

        def _no_playwright(p):
            raise ImportError("no playwright")
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            _no_playwright)
        monkeypatch.setattr(_review_screenshot, "_vision_chat",
                            lambda *a, **k: "不应被调用")
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert result["verdict"] == "SKIP"
        assert "降级" in result["summary"] and "非通过" in result["summary"]

    def test_vlm_missing_error_not_pass(self, monkeypatch, tmp_path):
        """VLM 不可得（返回空）→ ERROR 显式降级，不产生 PASS/FAIL。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            lambda p: [str(tmp_path / "shot.png")])
        monkeypatch.setattr(_review_screenshot, "_vision_chat", lambda *a, **k: "")
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert result["verdict"] == "ERROR" and "不可得" in result["summary"]

    def test_degradation_does_not_count_as_round(self, monkeypatch, tmp_path):
        """SKIP/ERROR 降级条目不计修正轮（轮次口径：只计 PASS/FAIL）。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)

        def _no_playwright(p):
            raise ImportError("no playwright")
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            _no_playwright)
        _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert _review_screenshot.count_screenshot_rounds(html) == 0


# ---------------------------------------------------------------------------
# 2a-4：三秒测试主门 FAIL/PASS 判定（mock VLM 返回）
# ---------------------------------------------------------------------------

class TestThreeSecondGate:
    def _run(self, monkeypatch, tmp_path, vlm_json):
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            lambda p: [str(tmp_path / "shot.png")])
        monkeypatch.setattr(_review_screenshot, "_vision_chat",
                            lambda *a, **k: vlm_json)
        return _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)

    def test_three_second_fail_forces_fail(self, monkeypatch, tmp_path):
        vlm = json.dumps({"three_second": "FAIL",
                          "three_second_conclusion": "",
                          "antipatterns": [], "coherence": [],
                          "verdict": "PASS", "issues": [], "summary": "x"},
                         ensure_ascii=False)
        result = self._run(monkeypatch, tmp_path, vlm)
        assert result["verdict"] == "FAIL"
        assert any("三秒测试" in i for i in result["issues"])

    def test_three_second_missing_fails_closed(self, monkeypatch, tmp_path):
        """VLM 返回缺 three_second 字段 → 主门不放行（fail-closed）。"""
        vlm = json.dumps({"verdict": "PASS", "issues": [], "summary": "x"},
                         ensure_ascii=False)
        result = self._run(monkeypatch, tmp_path, vlm)
        assert result["verdict"] == "FAIL"

    def test_pass_rounds_and_fields(self, monkeypatch, tmp_path):
        result = self._run(monkeypatch, tmp_path, _VLM_PASS_JSON)
        assert result["verdict"] == "PASS"
        assert result["screenshot_review_rounds"] == 1
        assert result["max_rounds"] == 3
        assert result["three_second_conclusion"] == "云原生降本三成"

    def test_verdict_fail_respected(self, monkeypatch, tmp_path):
        """三秒过但反模式/连贯性 FAIL → 整体 FAIL。"""
        vlm = json.dumps({"three_second": "PASS", "three_second_conclusion": "x",
                          "antipatterns": ["信息过载 - 中部"], "coherence": [],
                          "verdict": "FAIL", "issues": [], "summary": "y"},
                         ensure_ascii=False)
        result = self._run(monkeypatch, tmp_path, vlm)
        assert result["verdict"] == "FAIL"
        assert any("信息过载" in i for i in result["issues"])

    def test_non_json_returns_fail(self, monkeypatch, tmp_path):
        result = self._run(monkeypatch, tmp_path, "这不是 JSON")
        assert result["verdict"] == "FAIL"

    def test_rounds_accumulate_across_runs(self, monkeypatch, tmp_path):
        """每轮 PASS/FAIL 落 review_log，轮次跨调用累计。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path)
        monkeypatch.setattr(_review_screenshot, "_render_screenshot",
                            lambda p: [str(tmp_path / "shot.png")])
        monkeypatch.setattr(_review_screenshot, "_vision_chat",
                            lambda *a, **k: _VLM_PASS_JSON)
        for expected in (1, 2, 3):
            result = _review_screenshot.review_screenshot_adversarial(
                html, client_name="客户甲", quiet=True)
            assert result["screenshot_review_rounds"] == expected
        # 第 4 次：轮次熔断（不再发起 VLM）
        called = {"n": 0}

        def _count(*a, **k):
            called["n"] += 1
            return _VLM_PASS_JSON
        monkeypatch.setattr(_review_screenshot, "_vision_chat", _count)
        result = _review_screenshot.review_screenshot_adversarial(
            html, client_name="客户甲", quiet=True)
        assert result["verdict"] == "ERROR" and called["n"] == 0


# ---------------------------------------------------------------------------
# 2a-5：CLI --screenshot 接线（parser 面 + dispatch 面，全程 mock）
# ---------------------------------------------------------------------------

class TestScreenshotCliWiring:
    def test_parser_has_screenshot_flag(self):
        from _cli import build_parser
        parser = build_parser()
        sub = next(a for a in parser._actions
                   if hasattr(a, "choices") and a.choices)
        review_parser = sub.choices["review"]
        assert any(a.dest == "screenshot" for a in review_parser._actions)

    def test_cmd_review_screenshot_dispatch(self, monkeypatch, tmp_path):
        """review --screenshot 走 review_screenshot_adversarial；PASS → exit 0。"""
        import _cli
        import _review_screenshot as rs
        html = _make_html(tmp_path)
        seen = {}

        def _fake(output_path, client_name=None, spec_path=None, quiet=False):
            seen["file"] = output_path
            return {"verdict": "PASS", "issues": [], "summary": "ok"}
        monkeypatch.setattr(rs, "review_screenshot_adversarial", _fake)
        monkeypatch.setattr(sys, "argv", ["_cli.py", "review", html,
                                          "--screenshot"])
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            rc = _cli.main()  # PASS → 不抛 SystemExit（exit 0）
        finally:
            if saved is not None:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert rc in (None, 0)
        assert seen["file"] == html


# ---------------------------------------------------------------------------
# 2d：组合路由四态（deliver 阻断 / PASS 放行 / 非 crafted 不受影响 / build warn）
# ---------------------------------------------------------------------------

class TestCraftedReviewGate:
    def test_crafted_without_review_blocks_deliver(self, monkeypatch, tmp_path):
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=True)
        spec = _make_spec(tmp_path, crafted=True)
        with pytest.raises(SystemExit) as exc_info:
            _review_gate.deliver_gate(spec, html)
        assert exc_info.value.code == 1

    def test_crafted_with_pass_review_passes_deliver(self, monkeypatch, tmp_path):
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=True)
        spec = _make_spec(tmp_path, crafted=True)
        _write_pass_entry(monkeypatch, html)
        assert _review_gate.deliver_gate(spec, html) is False

    def test_non_crafted_unaffected(self, monkeypatch, tmp_path):
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=False)
        spec = _make_spec(tmp_path, crafted=False)
        assert _review_gate.deliver_gate(spec, html) is False

    def test_marker_fallback_blocks_when_spec_unreadable(self, monkeypatch,
                                                         tmp_path):
        """spec 读不到 → data-track 硬信号兜底阻断（不因 spec 缺失误放）。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=True)
        with pytest.raises(SystemExit) as exc_info:
            _review_gate.deliver_gate(str(tmp_path / "不存在.yml"), html)
        assert exc_info.value.code == 1

    def test_narrative_crafted_page_triggers_gate(self, monkeypatch, tmp_path):
        """叙事单 expression_mode=crafted（无 raw_html）同样触发阻断。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=False)
        narrative = {"scene": "规划", "page_budget": 5, "page_map": [
            {"page": "p2", "beat": "蓝图", "expression_mode": "crafted",
             "primary_expression": "总图", "static_equivalent": "分页",
             "density": "low"}]}
        (tmp_path / "narrative.yml").write_text(
            yaml.safe_dump(narrative, allow_unicode=True), encoding="utf-8")
        spec_path = tmp_path / "spec_n.yml"
        spec_path.write_text(yaml.safe_dump({
            "theme": "generic", "narrative_ref": "narrative.yml",
            "pages": [{"id": "p1", "title": "封面", "elements": []},
                      {"id": "p2", "title": "核心", "elements": []}],
        }, allow_unicode=True), encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            _review_gate.deliver_gate(str(spec_path), html)
        assert exc_info.value.code == 1

    def test_standalone_build_warns_without_blocking(self, monkeypatch, tmp_path,
                                                     capsys):
        """独立 html-build（run_single 挂载）：warn 不阻断产出。"""
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=True)
        assert _review_gate.warn_crafted_without_review(html) is True
        out = capsys.readouterr().out
        assert "[观察]" in out and "--screenshot" in out

    def test_no_warn_when_passed_or_plain(self, monkeypatch, tmp_path, capsys):
        _isolate(monkeypatch, tmp_path)
        html = _make_html(tmp_path, crafted=True)
        _write_pass_entry(monkeypatch, html)
        assert _review_gate.warn_crafted_without_review(html) is False
        assert _review_gate.warn_crafted_without_review(
            _make_html(tmp_path, crafted=False, name="plain.html")) is False
        assert capsys.readouterr().out == ""

    def test_run_single_mount_warns_not_blocks(self, monkeypatch, tmp_path,
                                               capsys):
        """run_single 集成：verify 通过 + crafted 无记录 → ok 仍为 True + warn。"""
        import _verify
        import _verify_hook
        _isolate(monkeypatch, tmp_path)
        # _verify_hook 模块级 from-import 绑定，需 patch 消费方模块属性
        monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(tmp_path / "logs"))
        monkeypatch.setattr(_verify_hook, "TASK_HISTORY",
                            str(tmp_path / "logs" / "task_history.json"))
        monkeypatch.setattr(_verify, "auto_verify",
                            lambda path, client, density_gate="verify":
                            (True, "OK"))
        monkeypatch.setattr(_verify_hook, "_auto_snippet_capture",
                            lambda path, file_type: None)
        html = _make_html(tmp_path, crafted=True)
        ok = _verify_hook.run_single(html)
        assert ok is True  # warn 不阻断
        assert "[观察]" in capsys.readouterr().out

    def test_review_log_entry_carries_rounds(self, monkeypatch, tmp_path):
        """write_review_log 持久化轮次字段（S9-2a 结构扩展不破兼容）。"""
        _isolate(monkeypatch, tmp_path)
        result = {"verdict": "FAIL", "issues": ["x"], "summary": "s",
                  "mode": "screenshot_adversarial",
                  "screenshot_review_rounds": 2}
        _review.write_review_log(result, str(tmp_path / "a.html"), "客户甲")
        entry = _review.read_review_log()[0]
        assert entry["mode"] == "screenshot_adversarial"
        assert entry["screenshot_review_rounds"] == 2
        assert entry["verdict"] == "FAIL"  # 既有字段不丢
