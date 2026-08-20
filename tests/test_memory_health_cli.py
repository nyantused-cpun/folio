# -*- coding: utf-8 -*-
"""记忆证据健康检查测试（P0 · T4）：_audit_memory + memory-health 命令。

全部用 tmp_path 造假客户目录注入，绝不读写真实 _knowledge/。
"""

import types

import _memory_guard as mg
from _cli_audit import _audit_memory
from _cli import cmd_memory_health


def _make_client(clients_dir, name, context=None, decisions=None, refs=None):
    """造一个假客户目录：context.md / decisions.md / refs/ 按需写入。"""
    cdir = clients_dir / name
    cdir.mkdir(parents=True, exist_ok=True)
    if context is not None:
        (cdir / "context.md").write_text(context, encoding="utf-8")
    if decisions is not None:
        (cdir / "decisions.md").write_text(decisions, encoding="utf-8")
    if refs is not None:
        rdir = cdir / "refs"
        rdir.mkdir(exist_ok=True)
        for fn in refs:
            (rdir / fn).write_text("x", encoding="utf-8")
    return cdir


CTX_HEALTHY = """# 项目上下文

### [2026-08-18] 第 1 次会话
#### 本次输入
测试
#### 关键决策
采用方案 A [来源可靠]
#### 证据
[✓] file:output/x.html
"""

CTX_PENDING = """# 项目上下文

### [2026-08-18] 第 1 次会话
#### 关键决策
定了报价口径（待补证据）
"""

DEC_CONFLICT = """# 决策记录

## [2026-08-17] 报价口径
- **决策**: 按人头计费
- **persistence**: permanent
<!-- conflict: pending -->
"""


class TestAuditMemory:
    def test_healthy_client(self, tmp_path, capsys):
        _make_client(tmp_path, "好客户", context=CTX_HEALTHY,
                     decisions="# 决策记录\n\n## 决策 1：x\n- **决策**: y\n",
                     refs=["材料a.pdf"])
        ok = _audit_memory(None, clients_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert ok is True
        assert "✓ [好客户]" in out
        assert "refs 1 个文件" in out

    def test_pending_and_conflict_warn_not_fail(self, tmp_path, capsys):
        """待补/冲突是警告级：标 ⚠ 但审计仍返回 True（防门禁恒红被忽略）。"""
        _make_client(tmp_path, "债客户", context=CTX_PENDING, decisions=DEC_CONFLICT)
        ok = _audit_memory(None, clients_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert ok is True
        assert "⚠ [债客户]" in out
        assert "待补证据 1" in out
        assert "冲突未决 1" in out

    def test_missing_refs_wording(self, tmp_path, capsys):
        """「没做/读不到」≠「0 条」：无 refs 报「未摄入或未归档」。"""
        _make_client(tmp_path, "空客户", context=CTX_HEALTHY)
        _audit_memory(None, clients_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert "无 refs 目录（未摄入或未归档）" in out

    def test_no_memory_files_skipped(self, tmp_path, capsys):
        """只有空目录的客户跳过，不算问题也不崩。"""
        _make_client(tmp_path, "空壳")
        ok = _audit_memory(None, clients_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert ok is True
        assert "无可扫描客户" in out

    def test_missing_clients_dir_fails(self, tmp_path, capsys):
        ok = _audit_memory(None, clients_dir=str(tmp_path / "不存在"))
        assert ok is False


class TestMemoryHealthCmd:
    def test_cmd_reports_counts(self, tmp_path, capsys, monkeypatch):
        _make_client(tmp_path, "测试客户", context=CTX_PENDING, decisions=DEC_CONFLICT)
        monkeypatch.setattr(mg, "CLIENTS_DIR", str(tmp_path))
        args = types.SimpleNamespace(client="测试客户")
        cmd_memory_health(args)
        out = capsys.readouterr().out
        assert "记忆证据健康: 测试客户" in out
        assert "会话 1 次" in out
        assert "待补 1" in out
        assert "冲突未决 1" in out

    def test_cmd_missing_client_graceful(self, tmp_path, capsys, monkeypatch):
        """客户无任何记忆文件：报不存在，不崩（失败必须可见而不是抛栈）。"""
        monkeypatch.setattr(mg, "CLIENTS_DIR", str(tmp_path))
        args = types.SimpleNamespace(client="没这客户")
        cmd_memory_health(args)
        out = capsys.readouterr().out
        assert "context.md" in out and "不存在" in out
