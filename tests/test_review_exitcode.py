# -*- coding: utf-8 -*-
"""T11 review fail-closed：cmd_review 退出码语义收紧为 exit 0 ⇔ verdict == "PASS"。

现状漏洞：_review.review 在 LLM 不可用时返回 verdict="ERROR"，cmd_review 只查
"FAIL" → ERROR 走 exit 0 → 工具层 ok:true → 审查静默通过（fail-open）。
修复后：FAIL/ERROR/SKIP 一律 exit 2 —— 判定不可得 ≠ 通过。

cmd_review 内 `from _review import review as _do_review` 是函数内 import，
monkeypatch 必须打 _review.review 模块属性。
"""

import os
import sys

import pytest


def _run_main(argv, monkeypatch):
    """以给定 argv 调用 _cli.main()，断言其抛出 SystemExit 并返回退出码。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    # main() 会置 _PRESALES_CLI_INVOKED=1；手动保存/还原，避免污染其他测试
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        with pytest.raises(SystemExit) as exc_info:
            _cli.main()
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved
    return exc_info.value.code


def _run_main_allow_success(argv, monkeypatch):
    """同 _run_main，但允许成功路径（无 SystemExit 时返回 None）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


class TestReviewFailClosed:
    """审查判定不可得（ERROR/SKIP）与发现实质问题（FAIL）一律 exit 2。"""

    def test_error_verdict_exits_2(self, monkeypatch, tmp_path):
        """LLM 不可用返回 ERROR → exit 2（此前漏洞：exit 0 静默通过）。"""
        out = tmp_path / "a.html"
        out.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(
            "_review.review",
            lambda **kw: {"verdict": "ERROR", "issues": [], "summary": "LLM 调用失败"})
        code = _run_main(["_cli.py", "review", str(out)], monkeypatch)
        assert code == 2

    def test_skip_verdict_exits_2(self, monkeypatch, tmp_path):
        """SKIP（无判定）同样不等于通过 → exit 2。"""
        out = tmp_path / "a.html"
        out.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(
            "_review.review",
            lambda **kw: {"verdict": "SKIP", "issues": [], "summary": "无判定"})
        code = _run_main(["_cli.py", "review", str(out)], monkeypatch)
        assert code == 2

    def test_pass_verdict_exits_0(self, monkeypatch, tmp_path):
        """唯一通过态：verdict == "PASS" → exit 0（不抛或 code==0）。"""
        out = tmp_path / "a.html"
        out.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(
            "_review.review",
            lambda **kw: {"verdict": "PASS", "issues": [], "summary": "ok"})
        code = _run_main_allow_success(["_cli.py", "review", str(out)], monkeypatch)
        assert code in (None, 0)
