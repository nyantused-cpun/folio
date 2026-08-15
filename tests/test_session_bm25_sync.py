# -*- coding: utf-8 -*-
"""save 内 BM25 同步节流逻辑（D-117/P1-5）：落后检测 + 每自然日一次重建。"""

import os

import _session
import _bm25
import _paths
import _onboard


def _write_file(path, content, mtime):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.utime(path, (mtime, mtime))


class TestBm25Sync:
    def _setup(self, tmp_path, monkeypatch, corpus_mtime, bm25_mtime,
               marker_content=None):
        clients = tmp_path / "clients"
        (clients / "c1").mkdir(parents=True)
        _write_file(clients / "c1" / "context.md", "# hi", corpus_mtime)
        bm25 = tmp_path / "bm25_index.pkl"
        _write_file(bm25, "x", bm25_mtime)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        marker = log_dir / "bm25_rebuild_date.txt"
        if marker_content:
            _write_file(marker, marker_content, 1000000000)
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(bm25))
        calls = []
        monkeypatch.setattr(_onboard, "rebuild_bm25_index_all",
                            lambda: (calls.append(1),
                                     {"indexed_count": 7})[1])
        return str(log_dir), marker, calls

    def test_rebuilds_when_behind(self, tmp_path, monkeypatch):
        log_dir, marker, calls = self._setup(tmp_path, monkeypatch,
                                             corpus_mtime=2000000000,
                                             bm25_mtime=1000000000)
        _session._sync_bm25_if_stale(log_dir, "2026-08-14")
        assert calls == [1]
        with open(marker, encoding="utf-8") as f:
            assert f.read().strip() == "2026-08-14"

    def test_skips_when_index_fresh(self, tmp_path, monkeypatch):
        log_dir, marker, calls = self._setup(tmp_path, monkeypatch,
                                             corpus_mtime=1000000000,
                                             bm25_mtime=2000000000)
        _session._sync_bm25_if_stale(log_dir, "2026-08-14")
        assert calls == []
        assert not os.path.exists(marker)

    def test_skips_second_run_same_day(self, tmp_path, monkeypatch):
        log_dir, marker, calls = self._setup(tmp_path, monkeypatch,
                                             corpus_mtime=2000000000,
                                             bm25_mtime=1000000000,
                                             marker_content="2026-08-14")
        _session._sync_bm25_if_stale(log_dir, "2026-08-14")
        assert calls == []

    def test_runs_next_day_again(self, tmp_path, monkeypatch):
        log_dir, marker, calls = self._setup(tmp_path, monkeypatch,
                                             corpus_mtime=2000000000,
                                             bm25_mtime=1000000000,
                                             marker_content="2026-08-13")
        _session._sync_bm25_if_stale(log_dir, "2026-08-14")
        assert calls == [1]
