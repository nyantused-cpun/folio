# -*- coding: utf-8 -*-
"""skills-sync 孤儿报告测试：目标端存在、事实源没有的技能必须可见（防影子技能静默累积）。"""
import os

from _skills_sync import sync_skills


def _make_skill(base, name, body="x"):
    sub = os.path.join(str(base), name)
    os.makedirs(sub, exist_ok=True)
    with open(os.path.join(sub, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(body)
    return sub


def test_orphans_reported_when_no_prune(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _make_skill(src, "alpha")
    _make_skill(dst, "alpha")
    _make_skill(dst, "shadow-a")
    _make_skill(dst, "shadow-b")

    report = sync_skills(str(src), str(dst), prune=False)

    assert report["orphans"] == ["shadow-a", "shadow-b"]
    # 孤儿不被删除（只可见，不静默清理）
    assert os.path.isdir(os.path.join(str(dst), "shadow-a"))
    assert os.path.isdir(os.path.join(str(dst), "shadow-b"))


def test_no_orphans_when_prune_cleans(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _make_skill(src, "alpha")
    _make_skill(dst, "alpha")
    _make_skill(dst, "shadow-a")

    report = sync_skills(str(src), str(dst), prune=True)

    assert report["pruned"] == ["shadow-a"]
    assert report["orphans"] == []
    assert not os.path.exists(os.path.join(str(dst), "shadow-a"))
