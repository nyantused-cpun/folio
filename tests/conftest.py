# -*- coding: utf-8 -*-
"""pytest 全局守卫（2026-08-31 工程残留修复）。

背景：测试曾把 verify 日志写进真实 .folio/logs/（08-30 深夜 verify_LOG 出现
pytest-tmp-safe 测试路径；task_history.json 主文件一度丢失导致 audit 溯源
全量 FAIL）。本文件是最后防线：

autouse 守卫 fixture——每条测试前后快照真实 .folio/logs/task_history.json、
verify_LOG_* 文件集与 _knowledge/snippets/，teardown 断言未被触碰；任何测试
直写/删除真实状态立即红灯并点名。

范围刻意收窄：不快照 telemetry/session_stats/soft_anchor 等 DSH 运行时文件
（活会话期间合法追加，会造成误报）。各测试自身的 monkeypatch 隔离不在此重复。
"""
import os

import pytest

_SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _snapshot(path):
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _walk_snapshot(root):
    snap = {}
    if not os.path.isdir(root):
        return snap
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            snap[rel] = _snapshot(full)
    return snap


def _diff_snap(before, after, label, problems):
    for name in sorted(set(before) | set(after)):
        if name not in before:
            problems.append("真实 %s 被测试新增: %s" % (label, name))
        elif name not in after:
            problems.append("真实 %s 被测试删除: %s" % (label, name))
        elif before[name] != after[name]:
            problems.append("真实 %s 被测试修改: %s" % (label, name))


@pytest.fixture(autouse=True)
def _guard_real_state():
    logs_dir = os.path.join(_SCRIPT_DIR, ".folio", "logs")
    real_history = os.path.join(logs_dir, "task_history.json")
    snippets_root = os.path.join(_SCRIPT_DIR, "_knowledge", "snippets")

    before_history = _snapshot(real_history)
    before_logs = {k: v for k, v in _walk_snapshot(logs_dir).items()
                   if os.path.basename(k).startswith("verify_LOG")}
    before_snippets = _walk_snapshot(snippets_root)

    yield

    problems = []
    after_history = _snapshot(real_history)
    if before_history != after_history:
        problems.append("真实 task_history.json 被测试修改: %s -> %s"
                        % (before_history, after_history))

    after_logs = {k: v for k, v in _walk_snapshot(logs_dir).items()
                  if os.path.basename(k).startswith("verify_LOG")}
    _diff_snap(before_logs, after_logs, "verify 日志", problems)
    _diff_snap(before_snippets, _walk_snapshot(snippets_root), "snippets", problems)

    if problems:
        pytest.fail(
            "[pytest 隔离守卫] 测试触碰了真实项目状态（应在 tmp_path 内隔离）:\n  "
            + "\n  ".join(problems),
            pytrace=False)