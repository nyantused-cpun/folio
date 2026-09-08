# -*- coding: utf-8 -*-
"""_snapshot_context 快照保留数回归（Wave3 口味调整：5→3）。"""
import os
import time

import _context


def _make_context(tmp_path):
    cdir = tmp_path / "clients" / "测试客户"
    cdir.mkdir(parents=True)
    ctx = cdir / "context.md"
    ctx.write_text("# 项目上下文记录\n", encoding="utf-8")
    return ctx


def test_snapshot_keeps_recent_three(tmp_path):
    ctx = _make_context(tmp_path)
    # 预置 4 个旧快照（mtime 递增，均早于本次新写）
    for i in range(4):
        p = ctx.parent / f"context.md.snapshot.2026090{i}000000"
        p.write_text(f"旧快照{i}", encoding="utf-8")
        os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))

    _context._snapshot_context(str(ctx))

    names = sorted(p.name for p in ctx.parent.glob("context.md.snapshot.*"))
    # 共 5 个 -> 只留最新 3 个（含本次新写），最旧两个被清理
    assert len(names) == 3
    assert not any("20260900" in n or "20260901" in n for n in names)
    assert any("20260903" in n for n in names)  # 次新旧快照保留
