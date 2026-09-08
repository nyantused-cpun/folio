# -*- coding: utf-8 -*-
"""P1 DSH 工具面替换：session-start 结构化返回体（head_context / tail_checklist / client_index）。

覆盖：
- _session.auto_for_input 返回体带 head_context / tail_checklist / client_index
- cmd_session_start --json 输出透传这三个字段（DSH folio_session_start 消费）
- cmd_session_start 非 JSON 分支打印 === 核心约束刷新 === 与 TAIL 自检（Kimi 等价出口）

全部用 tmp_path + monkeypatch，绝不读写真实 _knowledge/。
"""

import json
from types import SimpleNamespace

import _cli
import _session


def _setup_client(tmp_path, monkeypatch):
    """造假客户目录 + 一条 permanent 铁律，重定向写入目标。"""
    clients = tmp_path / "clients"
    clients.mkdir()
    d = clients / "测试客户P1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.md").write_text(
        "# 测试客户P1 决策记录\n"
        "## [2026-08-01] 核心铁律A\n"
        "- **决策**: 铁律A 内容\n"
        "- **persistence**: permanent\n"
        "- **scope**: client\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
    import _context
    import _theme_guard
    import _aliases
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    # 召回降级为无结果（避免联网/索引依赖）
    monkeypatch.setattr(_session, "recall", lambda *a, **kw: [])
    return clients


class TestAutoForInputStructured:
    def test_returns_head_tail_client_index(self, tmp_path, monkeypatch):
        _setup_client(tmp_path, monkeypatch)
        r = _session.auto_for_input("帮我做方案", client_name="测试客户P1")
        assert "head_context" in r
        assert "tail_checklist" in r
        assert "client_index" in r
        assert "铁律A" in (r.get("head_context") or "")


class TestCmdSessionStartJson:
    def test_json_contains_three_fields(self, tmp_path, monkeypatch, capsys):
        _setup_client(tmp_path, monkeypatch)
        # 直接调 cmd_session_start，client=None 跳过别名/时间戳/交接包副作用
        args = SimpleNamespace(client=None, json=True, input="帮我做方案")
        _cli.cmd_session_start(args)
        out = capsys.readouterr().out
        payload = json.loads(out)
        for key in ("head_context", "tail_checklist", "client_index", "recent_task_decisions"):
            assert key in payload, f"JSON 应含 {key}"

    def test_non_json_prints_head_and_tail(self, tmp_path, monkeypatch, capsys):
        _setup_client(tmp_path, monkeypatch)
        fake = {
            "level": "L4", "mode": "collaborative", "context_summary": "x",
            "client_index": "", "recall": [], "warnings": [],
            "head_context": "=== 核心约束刷新 ===\n[PERMANENT-CLIENT] 铁律A",
            "tail_checklist": "TAIL 自检：确认覆盖铁律A",
        }
        monkeypatch.setattr("_cli_cmds_qa.auto_for_input", lambda *a, **kw: fake)
        args = SimpleNamespace(client=None, json=False, input="帮我做方案")
        _cli.cmd_session_start(args)
        out = capsys.readouterr().out
        assert "=== 核心约束刷新 ===" in out
        assert "TAIL 自检" in out
