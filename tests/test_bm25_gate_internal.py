# -*- coding: utf-8 -*-
"""E 组收口：_sync_bm25_if_stale 的新鲜度扫描剪枝 `_` 前缀内部目录（#48）。

_internal/ 账本件变动不应触发全量 BM25 重建（重建经 scan_corpus 已收口，
节流门扫描此前仍会误判"corpus 落后"）。
"""
import os
import time

import _onboard
import _paths
import _session


def _make_tree(tmp_path, layout):
    """按 {相对路径: 内容} 建 tmp 客户树，文件 mtime 置为未来（必新于真实 bm25 索引）。"""
    clients = tmp_path / "clients"
    for rel, content in layout.items():
        f = clients / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        future = time.time() + 100000
        os.utime(f, (future, future))
    return clients


def _run_gate(tmp_path, monkeypatch, clients, today="2026-09-07"):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    calls = []
    monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_onboard, "rebuild_bm25_index_all",
                        lambda *a, **kw: calls.append(1) or {"indexed_count": 0})
    _session._sync_bm25_if_stale(str(log_dir), today)
    marker = log_dir / "bm25_rebuild_date.txt"
    return calls, marker


def test_internal_change_does_not_trigger_rebuild(tmp_path, monkeypatch):
    clients = _make_tree(tmp_path, {"_internal/通用/context.md": "账本件"})
    calls, marker = _run_gate(tmp_path, monkeypatch, clients)
    assert calls == []  # 内部目录被剪枝，不误判 corpus 落后
    assert not marker.exists()


def test_real_client_change_still_triggers_rebuild(tmp_path, monkeypatch):
    clients = _make_tree(tmp_path, {"客户甲/context.md": "客户件"})
    calls, marker = _run_gate(tmp_path, monkeypatch, clients)
    assert calls == [1]
    assert marker.read_text(encoding="utf-8").strip() == "2026-09-07"  # 当日节流


def test_template_and_cache_also_skipped(tmp_path, monkeypatch):
    clients = _make_tree(tmp_path, {
        "_template/context.md": "脚手架",
        "客户甲/.cache/notes.md": "缓存件",
    })
    calls, _marker = _run_gate(tmp_path, monkeypatch, clients)
    assert calls == []  # _ 前缀顶层目录剪枝 + .cache 件既有跳过，均不触发
