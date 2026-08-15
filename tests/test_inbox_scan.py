# -*- coding: utf-8 -*-
"""_inbox_scan.py 测试。

覆盖：
- A 高置信自动归档：refs/ 内同名 + 同 size → 归 _trash/
- B 同名但 size 不同 → 仅入清单（不自动归档）
- C 全新文件（无重复）→ 仅入清单
- D 空 inbox → 早退，不写报告
- E dry_run=True → 不移动任何文件
- F 双产物报告（.md + .json）正确生成
- G _uncategorized/ 子目录也被纳入扫描
- H _should_trigger_inbox_scan 时间窗/冷却/task_mode 判断
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from _inbox_scan import (
    classify_inbox_files,
    write_report,
    archive_duplicate,
    _should_trigger_inbox_scan,
    _now_in_window,
    _cooldown_elapsed,
    _write_last_scan,
    DEFAULT_TRASH_DIR,
)


# ---------- fixtures ----------

@pytest.fixture
def fake_workspace(tmp_path, monkeypatch):
    """构造最小化工作目录：inbox/ + _knowledge/clients/蓝海集团/refs/。"""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    knowledge = tmp_path / "_knowledge" / "clients"
    (knowledge / "蓝海集团" / "refs").mkdir(parents=True)

    # 在蓝海集团 refs/ 里放一个已知文件（用于重复检测）
    (knowledge / "蓝海集团" / "refs" / "旧文件.txt").write_bytes(b"hello world" * 10)

    return tmp_path


# ---------- A 高置信自动归档 ----------

def test_archive_duplicate_same_name_same_size(fake_workspace):
    """refs/ 内有同名同大小文件 → 自动归档到 _trash/。"""
    inbox = fake_workspace / "inbox"
    dup = inbox / "旧文件.txt"
    dup.write_bytes(b"hello world" * 10)  # 内容/大小完全一致

    cat = classify_inbox_files(str(fake_workspace))
    archived = archive_duplicate(cat, str(fake_workspace), dry_run=False)

    assert len(archived) == 1
    assert archived[0].filename == "旧文件.txt"
    assert "同名" in archived[0].reason
    assert "_trash" in archived[0].reason  # 归档路径已写入

    trash_dir = fake_workspace / DEFAULT_TRASH_DIR
    assert (trash_dir / "旧文件.txt").exists()
    assert not dup.exists()  # 原文件已移走


# ---------- B 同名但 size 不同 → 仅入清单 ----------

def test_same_name_different_size_only_listed(fake_workspace):
    """refs/ 内有同名但大小不同 → 不自动归档，仅入清单。"""
    inbox = fake_workspace / "inbox"
    dup = inbox / "旧文件.txt"
    dup.write_bytes(b"hello world" * 100)  # 大小不一样

    cat = classify_inbox_files(str(fake_workspace))
    archived = archive_duplicate(cat, str(fake_workspace), dry_run=False)

    assert len(archived) == 0
    assert dup.exists()  # 原文件未动
    assert any(f.filename == "旧文件.txt" for f in cat.pending_review)


# ---------- C 全新文件 → 仅入清单 ----------

def test_unknown_file_listed_not_archived(fake_workspace):
    """全新文件（refs 无同名）→ 仅入清单。"""
    inbox = fake_workspace / "inbox"
    new = inbox / "新文件.docx"
    new.write_bytes(b"some content")

    cat = classify_inbox_files(str(fake_workspace))
    archived = archive_duplicate(cat, str(fake_workspace), dry_run=False)

    assert len(archived) == 0
    assert new.exists()
    assert any(f.filename == "新文件.docx" for f in cat.pending_review)


# ---------- D 空 inbox 早退 ----------

def test_empty_inbox_no_report(fake_workspace):
    """inbox/ 为空（含 _uncategorized/ 也空）→ 返回空报告，不写文件。"""
    cat = classify_inbox_files(str(fake_workspace))
    assert cat.auto_candidate == []
    assert cat.pending_review == []


# ---------- E dry_run 不移动 ----------

def test_dry_run_no_move(fake_workspace):
    """dry_run=True 时不移动任何文件。"""
    inbox = fake_workspace / "inbox"
    dup = inbox / "旧文件.txt"
    dup.write_bytes(b"hello world" * 10)

    cat = classify_inbox_files(str(fake_workspace))
    archived = archive_duplicate(cat, str(fake_workspace), dry_run=True)

    assert len(archived) == 1  # 逻辑上识别为重复
    assert dup.exists()  # 但文件没动
    trash_dir = fake_workspace / DEFAULT_TRASH_DIR
    assert not (trash_dir / "旧文件.txt").exists()


# ---------- F 双产物报告 ----------

def test_write_report_creates_md_and_json(fake_workspace):
    """write_report 同时写 .md 和 .json。"""
    inbox = fake_workspace / "inbox"
    (inbox / "新文件.docx").write_bytes(b"abc")

    cat = classify_inbox_files(str(fake_workspace))
    md_path, json_path = write_report(cat, str(fake_workspace))

    assert md_path.endswith(".md")
    assert json_path.endswith(".json")
    assert os.path.exists(md_path)
    assert os.path.exists(json_path)

    md_content = Path(md_path).read_text(encoding="utf-8")
    assert "# Inbox 扫描报告" in md_content
    assert "新文件.docx" in md_content

    json_content = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert "pending_review" in json_content
    assert any(f["filename"] == "新文件.docx" for f in json_content["pending_review"])


# ---------- G _uncategorized/ 纳入扫描 ----------

def test_uncategorized_dir_scanned(fake_workspace):
    """_uncategorized/ 子目录里的文件也要被识别。"""
    inbox = fake_workspace / "inbox"
    unc = inbox / "_uncategorized"
    unc.mkdir()
    (unc / "未匹配.txt").write_bytes(b"hello")

    cat = classify_inbox_files(str(fake_workspace))
    assert any(f.filename == "未匹配.txt" for f in cat.pending_review)


# ---------- H 时间窗/冷却判断 ----------

def test_now_in_window_true():
    """本地时间在 22:00-22:30 之间 → True。"""
    dt = datetime(2026, 7, 17, 22, 15)
    assert _now_in_window(dt) is True


def test_now_in_window_false_outside():
    """22:30 之外 → False。"""
    dt = datetime(2026, 7, 17, 23, 0)
    assert _now_in_window(dt) is False
    dt = datetime(2026, 7, 17, 21, 59)
    assert _now_in_window(dt) is False


def test_now_in_window_false_at_boundary():
    """边界 22:30 整不命中（30 分钟容差，含头不含尾）。"""
    dt = datetime(2026, 7, 17, 22, 30)
    assert _now_in_window(dt) is False


def test_cooldown_elapsed_no_record(fake_workspace):
    """无记录文件 → 视为已过冷却期（首次部署场景）。"""
    assert _cooldown_elapsed(str(fake_workspace), hours=22) is True


def test_cooldown_elapsed_recent(fake_workspace):
    """最近扫描过 → False（未过冷却期）。"""
    _write_last_scan(str(fake_workspace), datetime.now())
    assert _cooldown_elapsed(str(fake_workspace), hours=22) is False


def test_cooldown_elapsed_old(fake_workspace):
    """超过 22 小时 → True。"""
    old = datetime.now() - timedelta(hours=23)
    _write_last_scan(str(fake_workspace), old)
    assert _cooldown_elapsed(str(fake_workspace), hours=22) is True


def test_should_trigger_all_conditions(fake_workspace, monkeypatch):
    """4 个条件全满足 → True。"""
    inbox = fake_workspace / "inbox"
    (inbox / "新文件.txt").write_bytes(b"x")
    # 强制当前时间到 22:15
    fake_now = datetime(2026, 7, 17, 22, 15)
    monkeypatch.setattr("_inbox_scan._now", lambda: fake_now)

    assert _should_trigger_inbox_scan(
        task_mode="presales",
        project_dir=str(fake_workspace),
    ) is True


def test_should_trigger_engineering_mode(fake_workspace):
    """工程任务模式 → False（不打扰）。"""
    assert _should_trigger_inbox_scan(
        task_mode="engineering",
        project_dir=str(fake_workspace),
    ) is False


def test_should_trigger_empty_inbox(fake_workspace, monkeypatch):
    """inbox 空 → False。"""
    fake_now = datetime(2026, 7, 17, 22, 15)
    monkeypatch.setattr("_inbox_scan._now", lambda: fake_now)

    assert _should_trigger_inbox_scan(
        task_mode="presales",
        project_dir=str(fake_workspace),
    ) is False


def test_should_trigger_cooldown_not_elapsed(fake_workspace, monkeypatch):
    """冷却期未过 → False。"""
    inbox = fake_workspace / "inbox"
    (inbox / "新文件.txt").write_bytes(b"x")
    _write_last_scan(str(fake_workspace), datetime.now())
    fake_now = datetime(2026, 7, 17, 22, 15)
    monkeypatch.setattr("_inbox_scan._now", lambda: fake_now)

    assert _should_trigger_inbox_scan(
        task_mode="presales",
        project_dir=str(fake_workspace),
    ) is False