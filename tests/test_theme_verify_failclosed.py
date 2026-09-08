# -*- coding: utf-8 -*-
"""P2 校验 fail-closed 原生化：theme-verify 退出码。

- critical 主题缺失 → exit 2（DSH folio_theme_verify 直接工具失败）
- 非 critical 缺失 → exit 0（warn）
- 无主题 / 读不到文件 → exit 1
"""

import os
import sys

import _theme_guard


def _run_main(argv, monkeypatch):
    """运行 _cli.main()；SystemExit -> 退出码，正常返回（exit 0）-> None。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
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


def _make_client(tmp_path, monkeypatch, decisions_text):
    d = tmp_path / "clients" / "测试客户T"
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.md").write_text(decisions_text, encoding="utf-8")
    out = tmp_path / "out.html"
    out.write_text("<html><body>产出内容</body></html>", encoding="utf-8")
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(tmp_path / "clients"))
    return str(out)


CRITICAL_DECISIONS = (
    "# 测试客户T 决策记录\n"
    "## [2026-08-01] 核心铁律必覆盖\n"
    "- **决策**: 必须出现的关键词\n"
    "- **persistence**: permanent\n"
    "- **scope**: client\n"
    "- **影响**: x\n"
    "- **层级**: L4\n"
    "- **决策内容**: 核心铁律必覆盖\n"
    "## [2026-08-02] 普通主题\n"
    "- **决策**: 普通主题内容\n"
    "- **persistence**: permanent\n"
    "- **scope**: client\n"
)


class TestThemeVerifyFailClosed:
    def test_critical_missing_exits_2(self, tmp_path, monkeypatch):
        # 产出不含 critical 铁律关键词 -> exit 2
        out = _make_client(tmp_path, monkeypatch, CRITICAL_DECISIONS)
        code = _run_main(["_cli.py", "theme-verify", out, "测试客户T"], monkeypatch)
        assert code == 2

    def test_critical_covered_exits_0(self, tmp_path, monkeypatch):
        out = _make_client(tmp_path, monkeypatch, CRITICAL_DECISIONS)
        # 产出补上关键词 -> 全过
        with open(out, "a", encoding="utf-8") as f:
            f.write("核心铁律必覆盖 必须出现的关键词")
        code = _run_main(["_cli.py", "theme-verify", out, "测试客户T"], monkeypatch)
        assert code is None  # 正常返回 = exit 0

    def test_no_themes_exits_1(self, tmp_path, monkeypatch):
        out = _make_client(tmp_path, monkeypatch,
                           "# 测试客户T 决策记录\n## [2026-08-01] 只有 task 决策\n- **决策**: x\n- **persistence**: task\n- **scope**: task\n")
        code = _run_main(["_cli.py", "theme-verify", out, "测试客户T"], monkeypatch)
        assert code == 1

    def test_missing_file_exits_1(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, CRITICAL_DECISIONS)
        code = _run_main(["_cli.py", "theme-verify", "不存在的文件xyz.html", "测试客户T"], monkeypatch)
        assert code == 1
