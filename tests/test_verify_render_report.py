# -*- coding: utf-8 -*-
"""verify 消费 RenderReport 的语义测试（重构 Phase 1，§6.3）。

run_single(path, client_name, render_report)：
- skipped 非空 → 结果 FAIL，原因列出被跳过元素（页面/序号/类型/原因）
- degraded 非空 → 不降级结果，降级明细并入警告部分打印
- 只有元素级 skip 触发 FAIL：schema 校验进的 warnings 不影响结果
- render_report=None（缺省）→ 行为与之前完全一致（向后兼容）
"""

import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

import _verify_hook
from _renderer.elements import RenderReport


@pytest.fixture
def target(monkeypatch, tmp_path):
    """隔离 run_single 的钩子副作用（日志/task_history/片段库），
    L1 检查 mock 为通过，返回一个伪 HTML 路径。"""
    monkeypatch.setattr(_verify_hook, "write_log", lambda *a, **k: None)
    monkeypatch.setattr(_verify_hook, "update_task_history", lambda *a, **k: None)
    monkeypatch.setattr(_verify_hook, "_auto_snippet_capture", lambda *a, **k: None)
    monkeypatch.setattr("_verify.auto_verify", lambda path, client_name="": (True, "L1 格式检查通过"))
    return str(tmp_path / "out.html")


class TestSkippedFailsVerify:
    """skipped 非空 → FAIL，即使 L1 格式检查本身通过。"""

    def test_skipped_fails_with_details(self, target, capsys):
        report = RenderReport()
        report.skip("p3", 1, "tree", "HTML 端不支持")
        report.skip("p5", 0, "foo_bar", "HTML 端不支持")

        ok = _verify_hook.run_single(target, render_report=report)

        assert ok is False
        out = capsys.readouterr().out
        assert "FAIL" in out
        # 原因列出被跳过元素（页面/序号/类型/原因）
        assert "p3 elements[1] tree: HTML 端不支持" in out
        assert "p5 elements[0] foo_bar: HTML 端不支持" in out

    def test_l1_fail_plus_skipped_still_fails(self, target, monkeypatch):
        monkeypatch.setattr("_verify.auto_verify",
                            lambda path, client_name="": (False, "HTML 缺少 title"))
        report = RenderReport()
        report.skip("p3", 1, "tree", "HTML 端不支持")

        ok = _verify_hook.run_single(target, render_report=report)

        assert ok is False


class TestDegradedWarnsOnly:
    """degraded 非空 → 不降级结果，降级明细进警告输出。"""

    def test_degraded_passes_with_warning(self, target, capsys):
        report = RenderReport()
        report.degrade("p9", 1, "diagram", "docx", "[架构图：演进图] 请见 HTML/PPT 版")

        ok = _verify_hook.run_single(target, render_report=report)

        assert ok is True
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "[降级] p9 elements[1] diagram -> docx: [架构图：演进图] 请见 HTML/PPT 版" in out


class TestWarningsDoNotFail:
    """schema 校验进的 warnings 不触发 FAIL（只有元素级 skip 才触发）。"""

    def test_schema_warnings_ignored(self, target):
        report = RenderReport()
        report.warn("[spec校验] pages[0].elements[1] 未知元素类型: tree")

        ok = _verify_hook.run_single(target, render_report=report)

        assert ok is True

    def test_empty_report_passes(self, target):
        assert _verify_hook.run_single(target, render_report=RenderReport()) is True


class TestBackwardCompat:
    """render_report 缺省/None → 行为与改造前完全一致。"""

    def test_no_report_l1_pass(self, target, capsys):
        ok = _verify_hook.run_single(target)
        assert ok is True
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "降级" not in out

    def test_no_report_l1_fail(self, target, monkeypatch):
        monkeypatch.setattr("_verify.auto_verify",
                            lambda path, client_name="": (False, "HTML 缺少 title"))
        assert _verify_hook.run_single(target) is False
