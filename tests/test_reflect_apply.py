# -*- coding: utf-8 -*-
"""P3 反思/洞察收敛：reflect --apply 落盘 + insight/diff-record/feedback/diff 废弃。

覆盖：
- reflect_session(..., apply=True) -> decisions.md 落「AI 推断（待确认）」task 条目
- apply=False 只返回提案不落盘
- insight / diff-record / feedback / diff 走 _DEPRECATED -> exit 1 + 提示 reflect
- cmd_memory_health 与 format_report 口径（同源）

全部用 tmp_path + monkeypatch，绝不读写真实 _knowledge/。
"""

import json
import os
import sys

import _cloud_llm
import _reflect
import _theme_guard
import _memory_guard as mg


CTX_BLOCK = """# 项目上下文

### [2026-08-29] 第 1 次会话
#### 本次输入
用户让 AI 做架构图
#### 关键决策
（见 decisions.md：会话决策 2026-08-29 #sess）
#### 产出文件
output/x/方案.html
#### 待办 / 下次要做的
(未记录)
"""


def _setup(tmp_path, monkeypatch, llm_json):
    clients = tmp_path / "clients"
    clients.mkdir()
    d = clients / "测试客户R"
    d.mkdir(parents=True, exist_ok=True)
    (d / "context.md").write_text(CTX_BLOCK, encoding="utf-8")
    monkeypatch.setattr(_reflect, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_reflect, "TASK_HISTORY", str(tmp_path / "task_history.json"))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(mg, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_cloud_llm, "LLM_MODE", "api")
    # P1-5：统一 patch 索引联动，隔离真实 _knowledge 语料（避免 API 调用/写 .cache）
    import _embed_index
    monkeypatch.setattr(_embed_index, "build_embedding_index",
                        lambda **kw: {"vectors": {}, "meta": {}, "model": "", "dim": 0})

    def _fake_chat(*a, **kw):
        return json.dumps(llm_json, ensure_ascii=False)

    monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)
    return d


class TestReflectApply:
    def test_apply_writes_task_decision(self, tmp_path, monkeypatch):
        d = _setup(tmp_path, monkeypatch, [
            {"topic": "AI 推断原则", "decision": "以后报价先确认范围",
             "reason": "用户两次提到范围", "type": "原则",
             "source": "AI 推断", "confidence": 0.6},
        ])
        proposals, warning = _reflect.reflect_session("测试客户R", apply=True)
        assert len(proposals) == 1
        dec = (d / "decisions.md").read_text(encoding="utf-8")
        assert "AI 推断原则" in dec
        assert "以后报价先确认范围" in dec
        assert "**persistence: task**" in dec
        assert "AI 推断（待确认）" in dec
        assert "待确认" in dec

    def test_no_apply_does_not_write(self, tmp_path, monkeypatch):
        d = _setup(tmp_path, monkeypatch, [
            {"topic": "不落盘提案", "decision": "只预览",
             "reason": "", "type": "选择", "source": "AI 推断", "confidence": 0.5},
        ])
        proposals, warning = _reflect.reflect_session("测试客户R", apply=False)
        assert len(proposals) == 1
        assert not (d / "decisions.md").exists()

    def test_apply_triggers_index_increment(self, tmp_path, monkeypatch):
        import _embed_index
        calls = []
        _setup(tmp_path, monkeypatch, [
            {"topic": "索引联动提案", "decision": "写后应能搜到",
             "reason": "", "type": "原则", "source": "AI 推断", "confidence": 0.6},
        ])
        # _setup 已把 build_embedding_index patch 成 no-op；本测试在此覆盖为计数桩
        monkeypatch.setattr(_embed_index, "build_embedding_index",
                            lambda **kw: calls.append(1) or {})
        _reflect.reflect_session("测试客户R", apply=True)
        # P6-5：--apply 成功后触发一次索引增量
        assert len(calls) == 1


class TestDeprecatedCommands:
    def _run(self, argv, monkeypatch):
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

    def test_insight_deprecated(self, monkeypatch, capsys):
        code = self._run(["_cli.py", "insight", "某客户"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "已废弃" in out and "reflect" in out

    def test_diff_record_deprecated(self, monkeypatch, capsys):
        code = self._run(["_cli.py", "diff-record", "某客户", "a", "b"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "已废弃" in out and "reflect" in out

    def test_feedback_deprecated_points_to_reflect(self, monkeypatch, capsys):
        """feedback/diff 不再指向 diff-record（避免二级废弃）。"""
        code = self._run(["_cli.py", "feedback", "某客户"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "reflect" in out and "diff-record" not in out
