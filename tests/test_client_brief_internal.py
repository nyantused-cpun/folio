# -*- coding: utf-8 -*-
"""E 组遗留：build_client_brief 支持 _internal/ 账本客户回退。

#48 迁移后，账本客户（通用/工程/专家等）落 `_knowledge/clients/_internal/`；
session-start 简报此前只拼顶层路径，导致账本客户误报「客户档案不存在」。
"""
import _paths
import _session
import _theme_guard


def _redirect(tmp_path, monkeypatch):
    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    return clients


def test_brief_reads_internal_ledger_client(tmp_path, monkeypatch):
    clients = _redirect(tmp_path, monkeypatch)
    d = clients / "_internal" / "通用"
    d.mkdir(parents=True)
    (d / "context.md").write_text(
        "# 项目上下文记录\n\n## 待澄清问题（open_questions）\n- 测试问题\n",
        encoding="utf-8")

    brief = _session.build_client_brief("通用")
    assert brief["exists"] is True
    assert "客户档案不存在或未初始化" not in brief["missing"]
    assert "context.md 缺失" not in brief["missing"]


def test_brief_missing_client_still_reported(tmp_path, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    brief = _session.build_client_brief("不存在客户")
    assert brief["exists"] is False
    assert "客户档案不存在或未初始化" in brief["missing"]
