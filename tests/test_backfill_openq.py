# -*- coding: utf-8 -*-
import pytest
"""W1-8（#49①）C5 生成器-检查器代沟修复回归。

覆盖：
- 模板产出 context.md 能过 _context_health C5（直接调 run_context_health）；
- _scratch/backfill_openq.py 幂等（二次跑零变更）、插入位置=标题区后而非文末、
  只插段不动其余内容（CRLF/LF 字节级）、--dry-run 不写盘、无标题行跳过。
"""
import importlib.util
import shutil
from pathlib import Path

import _context_health as ch

_ROOT = Path(__file__).resolve().parents[1]

_TEMPLATE = _ROOT / "_knowledge" / "clients" / "_template" / "context.md"


def _load_backfill():
    spec = importlib.util.spec_from_file_location(
        "backfill_openq", _ROOT / "_scratch" / "backfill_openq.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SAMPLE = (
    "# 项目上下文记录\n"
    "\n"
    "> 本文件是此客户项目的\"活记忆\"。\n"
    "\n"
    "## 项目基础信息\n"
    "- 客户名称: 甲\n"
    "\n"
    "## 会话历史\n"
    "（尾部内容）\n"
)

_SECTION = (
    "## 待澄清问题（open_questions）\n"
    "（暂无——新问题出现时在此追加，客户确认后移入 decisions.md）\n"
)


def _make_client(tmp_path, name="甲客户", text=_SAMPLE):
    cdir = tmp_path / "clients" / name
    cdir.mkdir(parents=True)
    (cdir / "context.md").write_text(text, encoding="utf-8", newline="")
    return cdir / "context.md"


# ---------- 模板 → C5 检查 ----------

def test_template_context_passes_c5(tmp_path, monkeypatch):
    """模板新产出的 context.md 直接过 C5：不再出现 25/25 全 WARN 的代沟。"""
    cdir = tmp_path / "clients" / "模板客户"
    cdir.mkdir(parents=True)
    shutil.copyfile(_TEMPLATE, cdir / "context.md")
    monkeypatch.setattr(ch, "CLIENTS_DIR", str(tmp_path / "clients"))
    monkeypatch.setattr(ch, "_load_state", lambda name: {})
    monkeypatch.setattr(ch, "_save_state", lambda name, **kw: {})
    monkeypatch.setattr(ch, "_append_log", lambda *a, **kw: None)
    result = ch.run_context_health("模板客户")
    c5 = next(c for c in result["checks"] if c["id"] == "C5")
    assert c5["status"] == "ok", c5["detail"]


# ---------- 补段脚本 ----------

def test_backfill_idempotent(tmp_path):
    """幂等：首跑插入，二次跑零变更（内容逐字节不变）。"""
    bf = _load_backfill()
    ctx = _make_client(tmp_path)
    before = ctx.read_bytes()
    s1 = bf.backfill_clients(str(tmp_path / "clients"))
    assert s1["inserted"] == ["甲客户"]
    after_first = ctx.read_bytes()
    assert after_first != before
    s2 = bf.backfill_clients(str(tmp_path / "clients"))
    assert s2["inserted"] == [] and s2["skipped"] == ["甲客户"]
    assert ctx.read_bytes() == after_first  # 二次跑零变更


def test_insert_position_after_title_not_end(tmp_path):
    """插入位置=标题区（标题+引言块）后、第一个正文小节前，而非文末。"""
    bf = _load_backfill()
    new_text, status = bf.insert_openq_section(_SAMPLE)
    assert status == "inserted"
    assert new_text.index("## 待澄清问题") < new_text.index("## 项目基础信息")
    # 原尾部内容仍在插入段之后（证明不是 append 到文末）
    assert new_text.index("## 会话历史") > new_text.index("## 待澄清问题")
    assert new_text.endswith("（尾部内容）\n")


def test_insert_right_after_title_without_quote(tmp_path):
    """无引言块的文件：段紧跟标题行（段与标题之间补一个空行）。"""
    bf = _load_backfill()
    new_text, status = bf.insert_openq_section("# 标题\n## 项目基础信息\n")
    assert status == "inserted"
    assert new_text.startswith("# 标题\n\n## 待澄清问题（open_questions）\n（暂无")
    assert new_text.endswith("\n\n## 项目基础信息\n")


def test_insert_preserves_bytes_crlf(tmp_path):
    """只插段不动其余内容：CRLF 文件除插入块外逐字节不变，段内换行跟随原文件。"""
    bf = _load_backfill()
    crlf = _SAMPLE.replace("\n", "\r\n")
    new_text, status = bf.insert_openq_section(crlf)
    assert status == "inserted"
    # 插入块 = 段标题 + 段说明 + 段后空行（换行跟随原文件 CRLF）
    block = bf.SECTION_TITLE + "\r\n" + bf.SECTION_BODY + "\r\n\r\n"
    assert block in new_text
    assert new_text.replace(block, "", 1) == crlf


def test_dry_run_no_write(tmp_path):
    """--dry-run 只报告不写盘。"""
    bf = _load_backfill()
    ctx = _make_client(tmp_path)
    before = ctx.read_bytes()
    s = bf.backfill_clients(str(tmp_path / "clients"), dry_run=True)
    assert s["inserted"] == ["甲客户"]
    assert ctx.read_bytes() == before


def test_no_title_skip(tmp_path):
    """找不到 H1 标题行：不猜测插入点，跳过且内容不变。"""
    bf = _load_backfill()
    ctx = _make_client(tmp_path, name="乙客户", text="没有标题的正文\n")
    before = ctx.read_bytes()
    s = bf.backfill_clients(str(tmp_path / "clients"))
    assert s["no_title"] == ["乙客户"]
    assert ctx.read_bytes() == before


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
