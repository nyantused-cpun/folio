# -*- coding: utf-8 -*-
"""C-A1 回归：audit --mode behavior 最小 handler（0907 计划 W1）。

历史缺陷：argparse choices / TECH_SPEC / docstring 三处宣称 behavior 模式，
但 cmd_audit dispatch 无对应分支——选择该值落「未知审计模式」continue，
all_ok 不变，静默 exit 0（脱账实锤）。修复后接 _audit_behavior 最小统计。
"""

import json

import pytest

import _cli_audit
from _cli_audit import _audit_behavior, cmd_audit


class TestAuditBehaviorHandler:
    def test_missing_history_source_degrades_not_fails(self, tmp_path, capsys):
        """无 task_history 数据源：观察级降级标注，不 FAIL（对齐 debt/cost 先例）。"""
        assert _audit_behavior(history_path=str(tmp_path / "nope.json")) is True
        assert "数据源不存在" in capsys.readouterr().out

    def test_with_history_reports_stats(self, tmp_path, capsys):
        """有台账：出条目/项目统计，恒 OK。"""
        p = tmp_path / "task_history.json"
        p.write_text(json.dumps([
            {"date": "2026-09-07", "project": "client:工程", "session": 1},
            {"date": "2026-09-06", "project": "client:工程", "session": 2},
            {"date": "2026-09-05", "project": "client:测试客户", "session": 1},
        ], ensure_ascii=False), encoding="utf-8")
        assert _audit_behavior(history_path=str(p)) is True
        out = capsys.readouterr().out
        assert "3 条任务" in out
        assert "client:工程" in out
        assert "client:测试客户" in out

    def test_corrupted_history_fails(self, tmp_path):
        """解析失败是真问题（非缺数据），FAIL。"""
        p = tmp_path / "task_history.json"
        p.write_text("{broken json", encoding="utf-8")
        assert _audit_behavior(history_path=str(p)) is False

    def test_behavior_mode_dispatched_not_unknown(self, monkeypatch, capsys):
        """"--mode behavior 走 handler，不再落「未知审计模式」continue。"""
        called = {}
        monkeypatch.setattr(_cli_audit, "_audit_behavior",
                            lambda: called.setdefault("hit", True))
        args = type("Args", (), {"mode": "behavior", "client": None})()
        with pytest.raises(SystemExit) as ei:
            cmd_audit(args)
        assert ei.value.code == 0
        assert called.get("hit") is True
        assert "未知审计模式" not in capsys.readouterr().out

    def test_behavior_mode_not_in_all(self):
        """"--mode all 不含 behavior（C-A1 实测约束：加 handler 不影响 all 时长）。"""
        import inspect
        src = inspect.getsource(_cli_audit.cmd_audit)
        assert '"behavior"' not in src.split("modes = [")[1].split("]")[0]

    def test_behavior_handler_lives_in_dedicated_module(self):
        """体量棘轮拆分钉子：handler 外迁独立模块，_cli_audit 引用面保持同对象
        （monkeypatch `_cli_audit._audit_behavior` 的既有测试路径不迁移）。"""
        import _cli_audit
        import _cli_audit_behavior
        assert _cli_audit._audit_behavior is _cli_audit_behavior._audit_behavior
