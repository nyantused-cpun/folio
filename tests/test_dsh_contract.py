# -*- coding: utf-8 -*-
"""CLI 契约 v1 快照测试（docs/cli_contract_v1.md）。

钉住 DSH 桥接命令的 exit code 语义与 --json 键名，防止实现合并时漂移。
Step 3/6 后按新行为更新本文件断言，不得只改实现不改契约。

当前覆盖：
- style-check：exit 0 成功 / exit 1 文件不存在
- theme-verify：exit 0 覆盖 / exit 1 无主题或无法判定 / exit 2 critical 缺失
- session-start --json：键名快照
- confirm：Step 6 实现后补（见下方 skip 桩）
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest


def _run_main(argv, monkeypatch):
    """调用 _cli.main，断言 SystemExit 并返回退出码；成功路径返回 None。"""
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


class TestStyleCheckExit:
    def test_missing_file_exits_1(self, monkeypatch):
        code = _run_main(["_cli.py", "style-check", "不存在的文件xyz.html"],
                         monkeypatch)
        assert code == 1

    def test_clean_file_exits_0(self, monkeypatch, tmp_path, capsys):
        p = tmp_path / "clean.txt"
        p.write_text("这是一段正常的售前方案文字。", encoding="utf-8")
        code = _run_main(["_cli.py", "style-check", str(p)], monkeypatch)
        assert code in (None, 0)
        assert "OK" in capsys.readouterr().out


class TestThemeVerifyExit:
    def _run_theme_verify(self, monkeypatch, themes=None, coverage=None,
                          file_path=None):
        import _theme_guard
        import _cli_audit
        if themes is None:
            themes = []
        monkeypatch.setattr(_theme_guard, "load_active_themes",
                            lambda *a, **kw: themes)
        monkeypatch.setattr(_theme_guard, "check_coverage",
                            lambda *a, **kw: coverage or {
                                "covered": [], "missing": [], "warnings": []})
        args = SimpleNamespace(client="测试客户", file=str(file_path))
        # cmd_theme_verify 内部 from _theme_guard import ... 已打桩
        with pytest.raises(SystemExit) as exc:
            _cli_audit.cmd_theme_verify(args)
        return exc.value.code

    def test_no_theme_exits_1(self, monkeypatch, tmp_path):
        f = tmp_path / "x.html"
        f.write_text("内容", encoding="utf-8")
        assert self._run_theme_verify(monkeypatch, themes=[], file_path=f) == 1

    def test_critical_missing_exits_2(self, monkeypatch, tmp_path):
        f = tmp_path / "x.html"
        f.write_text("内容", encoding="utf-8")
        coverage = {
            "covered": [],
            "missing": [{"theme": "铁律", "priority": "critical"}],
            "warnings": [],
        }
        assert self._run_theme_verify(
            monkeypatch, themes=[{"theme": "铁律", "priority": "critical"}],
            coverage=coverage, file_path=f) == 2

    def test_noncritical_missing_exits_0(self, monkeypatch, tmp_path):
        """非 critical 缺失是 warn，不 fail-closed。"""
        import _theme_guard
        import _cli_audit
        f = tmp_path / "x.html"
        f.write_text("内容", encoding="utf-8")
        themes = [{"theme": "普通", "priority": "high"}]
        coverage = {
            "covered": [],
            "missing": [{"theme": "普通", "priority": "high"}],
            "warnings": [],
        }
        monkeypatch.setattr(_theme_guard, "load_active_themes",
                            lambda *a, **kw: themes)
        monkeypatch.setattr(_theme_guard, "check_coverage",
                            lambda *a, **kw: coverage)
        args = SimpleNamespace(client="测试客户", file=str(f))
        # 成功路径不抛 SystemExit
        _cli_audit.cmd_theme_verify(args)


class TestSessionStartJson:
    CONTRACT_KEYS = {
        "level", "mode", "client", "stage", "context_summary",
        "client_index", "head_context", "tail_checklist",
        "recent_task_decisions", "recall", "recall_degraded",
        "warnings", "usage_summary", "vision_supported",
    }

    def test_json_key_snapshot(self, monkeypatch, capsys):
        import _cli
        import _cloud_llm
        fake = {
            "level": "L4", "mode": "collaborative", "context_summary": "ctx",
            "client_index": "idx", "head_context": "head",
            "tail_checklist": "tail", "recent_task_decisions": [],
            "recall": [], "warnings": [],
        }
        monkeypatch.setattr("_cli_cmds_qa.auto_for_input", lambda *a, **kw: fake)
        monkeypatch.setattr("_cli_cmds_qa.get_state", lambda client: {"stage": "intake"})
        monkeypatch.setattr(_cloud_llm, "get_usage_summary",
                            lambda: {"total_calls": 1})
        args = SimpleNamespace(client=None, json=True, input="帮我做方案")
        _cli.cmd_session_start(args)
        payload = json.loads(capsys.readouterr().out)
        assert self.CONTRACT_KEYS <= set(payload), (
            "session-start --json 缺少契约键: "
            f"{sorted(self.CONTRACT_KEYS - set(payload))}"
        )


def test_folio_confirm_registered_in_dsh_tools():
    """Step 6：DSH 桥注册 folio_confirm（exit 0/2 语义通过 CLI 契约）。"""
    import _cli
    parser = _cli.build_parser()
    subactions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    all_cmds = set(subactions[0].choices.keys()) if subactions else set()
    assert "confirm" in all_cmds
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    defs = os.path.join(root, ".dsh", "folio-tools", "defs.js")
    assert os.path.exists(defs)
    text = open(defs, "r", encoding="utf-8").read()
    assert 'name: "folio_confirm"' in text
    assert '"confirm"' in text


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
