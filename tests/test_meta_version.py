# -*- coding: utf-8 -*-
import pytest
"""#50 防再发：context.md meta_version 结构版本标记。

覆盖三层防线：
- 模板产物自带标记（首行 HTML 注释，与 H2 白名单/会话块正则无冲突）；
- save 对存量无标记 context.md 打 WARN（不阻断）；
- _scratch/backfill_meta_version.py 回填脚本幂等 + dry-run + 只加标记不动内容。
"""
import importlib.util
from pathlib import Path

import _context
import _session

_SCRIPT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE = _SCRIPT_DIR / "_knowledge" / "clients" / "_template" / "context.md"


def _setup_save(tmp_path, monkeypatch):
    """save_session 测试基座（同 test_session_upsert 口径，tmp 隔离 + 重副作用桩）。"""
    import _aliases
    import _theme_guard

    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
    monkeypatch.setattr(_session, "update_outputs_index", lambda *a, **kw: 0)
    return clients


class TestTemplateMarker:
    def test_template_first_line_has_marker(self):
        lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
        assert _context.CONTEXT_META_VERSION_LINE in lines[0]

    def test_fallback_init_writes_marker(self, tmp_path, monkeypatch):
        """模板缺失降级最小头也带标记（不产生新的无标记存量）。"""
        clients = tmp_path / "clients"
        cdir = clients / "新客户"
        cdir.mkdir(parents=True)
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        assert _context._init_context_file(str(cdir)) is True
        first = (cdir / "context.md").read_text(encoding="utf-8").splitlines()[0]
        assert _context.CONTEXT_META_VERSION_LINE in first

    def test_has_meta_version(self):
        assert _context.has_meta_version("<!-- meta_version: 1 -->\n# 标题")
        assert not _context.has_meta_version("# 标题\n\n正文")
        # 标记只认头部 5 行，正文深处出现不算
        body = "# 标题\n" + "\n" * 10 + "<!-- meta_version: 1 -->"
        assert not _context.has_meta_version(body)


class TestSaveWarn:
    def test_save_warns_on_legacy_context_without_marker(self, tmp_path, monkeypatch, capsys):
        clients = _setup_save(tmp_path, monkeypatch)
        cdir = clients / "测试客户MV"
        cdir.mkdir()
        (cdir / "context.md").write_text(
            "# 项目上下文记录\n\n## 会话历史\n", encoding="utf-8")

        assert _session.save_session("测试客户MV", input_desc="x", light=True) is True
        out = capsys.readouterr().out
        assert "[warn]" in out and "meta_version" in out
        # 不阻断：会话照常落账
        assert "会话已保存: 测试客户MV" in out

    def test_save_no_warn_when_marker_present(self, tmp_path, monkeypatch, capsys):
        clients = _setup_save(tmp_path, monkeypatch)
        cdir = clients / "测试客户MV"
        cdir.mkdir()
        (cdir / "context.md").write_text(
            "<!-- meta_version: 1 -->\n# 项目上下文记录\n\n## 会话历史\n",
            encoding="utf-8")

        assert _session.save_session("测试客户MV", input_desc="x", light=True) is True
        out = capsys.readouterr().out
        assert "meta_version 标记" not in out


class TestBackfillScript:
    def _load_script(self):
        script = _SCRIPT_DIR / "_scratch" / "backfill_meta_version.py"
        spec = importlib.util.spec_from_file_location("backfill_meta_version", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_dry_run_then_backfill_idempotent(self, tmp_path, monkeypatch, capsys):
        mod = self._load_script()
        clients = tmp_path / "clients"
        d1 = clients / "客户甲"
        d1.mkdir(parents=True)
        (d1 / "context.md").write_text("# 项目上下文记录\n\n既有内容不动\n",
                                       encoding="utf-8")
        monkeypatch.setattr(mod, "CLIENTS_DIR", str(clients))

        # dry-run：计数但不写盘
        patched, _, _ = mod.backfill(dry_run=True)
        assert patched == 1
        assert "meta_version" not in (d1 / "context.md").read_text(encoding="utf-8")

        # 实跑：首行加标记，其余内容原样
        patched, _, _ = mod.backfill(dry_run=False)
        assert patched == 1
        text = (d1 / "context.md").read_text(encoding="utf-8")
        assert text.splitlines()[0] == mod.CONTEXT_META_VERSION_LINE
        assert "既有内容不动" in text

        # 幂等：再跑只计已有标记，零改动
        patched, marked, _ = mod.backfill(dry_run=False)
        assert patched == 0 and marked == 1

    def test_covers_internal_ledger_clients(self, tmp_path, monkeypatch):
        mod = self._load_script()
        clients = tmp_path / "clients"
        d1 = clients / "_internal" / "通用"
        d1.mkdir(parents=True)
        (d1 / "context.md").write_text("# 项目上下文记录\n", encoding="utf-8")
        monkeypatch.setattr(mod, "CLIENTS_DIR", str(clients))

        patched, _, missing = mod.backfill(dry_run=False)
        assert patched == 1 and missing == 0
        assert "meta_version" in (d1 / "context.md").read_text(encoding="utf-8")


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
