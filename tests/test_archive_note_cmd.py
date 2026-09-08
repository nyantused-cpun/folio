# -*- coding: utf-8 -*-
"""W1-7（#40）archive-note 双 bug 回归。

bug①：--list 分支按 {客户: {文件: ts}} 形状迭代 list_pending()，
       实际返回 {"entries": [...]} → 'list' object has no attribute 'items'。
bug②：登记调用按 folio 版签名 archive_note(client, files) 传参，
       workspace 版实际签名 archive_note(filenames, dest, client_name)
       → 客户串进 filenames、列表进 dest，非法 dest 静默 0 登记。
"""
import argparse

import _cli_cmds_mem as mem
import _inbox_registry as reg


def _patch_registry(tmp_path, monkeypatch):
    """登记表指到 tmp_path，不碰真实 .folio/logs/。"""
    p = tmp_path / "inbox_registry.json"
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(p))
    return p


def _args(**kw):
    return argparse.Namespace(client=kw.get("client"), files=kw.get("files"),
                              list=kw.get("list", False))


def test_list_empty_state_no_crash(tmp_path, monkeypatch, capsys):
    """空登记表 --list：不崩，打印空态提示。"""
    _patch_registry(tmp_path, monkeypatch)
    mem.cmd_archive_note(_args(list=True))
    out = capsys.readouterr().out
    assert "无待归档登记" in out


def test_list_with_entries_no_crash(tmp_path, monkeypatch, capsys):
    """有登记态 --list：不崩，按 [归属] 文件 (ts) 渲染 client 与 general。"""
    _patch_registry(tmp_path, monkeypatch)
    reg.register_entry("示例评估.pptx", "client", client="示例客户")
    reg.register_entry("通用样张.pdf", "general")
    mem.cmd_archive_note(_args(list=True))
    out = capsys.readouterr().out
    assert "[示例客户]  示例评估.pptx" in out
    assert "[general]  通用样张.pdf" in out
    # ts 为登记时刻（isoformat 秒级），必须渲染出来
    assert out.count("(") >= 2


def test_register_roundtrip(tmp_path, monkeypatch, capsys):
    """登记 → pending → 消费 往返：文件落登记表、归属正确、消费后清零。"""
    _patch_registry(tmp_path, monkeypatch)
    mem.cmd_archive_note(_args(client="示例客户", files=["sub/示例评估.pptx", "样张.pdf"]))
    out = capsys.readouterr().out
    assert "已登记 2 个文件归属 示例客户" in out
    # workspace 签名：文件进 filenames（取 basename），客户进 client_name
    pend = reg.pending_entries()
    assert [e["file"] for e in pend] == ["示例评估.pptx", "样张.pdf"]
    assert all(e["dest"] == "client" and e["client"] == "示例客户" for e in pend)
    # 消费（save 自动归档侧 mark_done）→ pending 清零
    for e in list(pend):
        assert reg.mark_done(e["file"]) is True
    assert reg.pending_entries() == []


def test_register_no_invalid_dest_regression(tmp_path, monkeypatch, capsys):
    """回归 bug②：登记结果不得为非法 dest 的静默 0 登记（errors 必须为空）。"""
    _patch_registry(tmp_path, monkeypatch)
    mem.cmd_archive_note(_args(client="示例客户", files=["a.pdf"]))
    out = capsys.readouterr().out
    assert "登记失败" not in out
    assert "已登记 0 个" not in out
    pend = reg.pending_entries()
    assert len(pend) == 1 and pend[0]["dest"] == "client"
