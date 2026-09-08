# -*- coding: utf-8 -*-
"""C-B3：embed-stats 双路（Embedding + BM25）覆盖率告警。

口径：索引内文档数 vs scan_corpus 应有语料文档数；任一路缺失/落后即 [warn]。
缺数据（语料扫描失败）走降级打印，不阻断统计输出。
"""
import os

import _bm25
import _cli_cmds_idx
import _paths


def _run(capsys):
    _cli_cmds_idx.cmd_embed_stats(None)
    return capsys.readouterr().out


def _patch_common(monkeypatch, corpus_n, embed_stats=None):
    monkeypatch.setattr(_cli_cmds_idx, "scan_corpus",
                        lambda: [("p%d" % i, "t%d" % i) for i in range(corpus_n)])
    if embed_stats is not None:
        monkeypatch.setattr(_cli_cmds_idx, "get_stats", lambda: embed_stats)


def test_full_coverage_no_warn(monkeypatch, capsys):
    """双路都覆盖满语料：统计照常打印，无任何覆盖率 [warn]。"""
    _patch_common(monkeypatch, corpus_n=5,
                  embed_stats={"exists": True, "count": 5, "dim": 2048, "model": "m1"})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (5, None))
    out = _run(capsys)
    assert "Embedding 索引统计" in out and "BM25 索引统计" in out
    assert "向量数: 5" in out and "文档数: 5" in out
    assert "覆盖率" not in out


def test_bm25_missing_warns(monkeypatch, capsys):
    """BM25 索引缺失：打印不存在提示 + 0% 覆盖率告警。"""
    _patch_common(monkeypatch, corpus_n=4,
                  embed_stats={"exists": True, "count": 4, "dim": 2048, "model": "m1"})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (None, None))
    out = _run(capsys)
    assert "BM25 索引不存在" in out
    assert "[warn] BM25 覆盖率 0%" in out
    assert "index-rebuild" in out
    assert "Embedding 覆盖率" not in out  # 满覆盖一路不告警


def test_bm25_behind_corpus_warns_with_pct(monkeypatch, capsys):
    """BM25 落后语料（部分覆盖）：打印百分比告警。"""
    _patch_common(monkeypatch, corpus_n=10,
                  embed_stats={"exists": True, "count": 10, "dim": 2048, "model": "m1"})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (4, None))
    out = _run(capsys)
    assert "[warn] BM25 覆盖率 40%（索引 4 块 / 语料 10 块）" in out


def test_embed_missing_warns(monkeypatch, capsys):
    """Embedding 索引缺失：保留既有提示，并补 0% 覆盖率告警。"""
    _patch_common(monkeypatch, corpus_n=3,
                  embed_stats={"exists": False, "count": 0, "dim": 0})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (3, None))
    out = _run(capsys)
    assert "Embedding 索引不存在" in out
    assert "[warn] Embedding 覆盖率 0%" in out
    assert "embed-rebuild" in out
    assert "[warn] BM25" not in out  # 满覆盖一路不告警


def test_bm25_corrupt_warns(monkeypatch, capsys, tmp_path):
    """BM25 索引存在但读取失败：打印失败提示 + 降级告警，不抛异常。"""
    _patch_common(monkeypatch, corpus_n=2,
                  embed_stats={"exists": True, "count": 2, "dim": 2048, "model": "m1"})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (0, "HMAC 签名校验失败，索引被拒绝加载"))
    out = _run(capsys)
    assert "BM25 索引读取失败" in out
    assert "[warn] BM25 覆盖率 0%" in out


def test_corpus_scan_failure_degrades(monkeypatch, capsys):
    """语料扫描失败：降级打印 [warn]，双路统计照常，不打印覆盖率告警。"""
    def _boom():
        raise RuntimeError("disk gone")
    monkeypatch.setattr(_cli_cmds_idx, "scan_corpus", _boom)
    monkeypatch.setattr(_cli_cmds_idx, "get_stats",
                        lambda: {"exists": True, "count": 8, "dim": 2048, "model": "m1"})
    monkeypatch.setattr(_cli_cmds_idx, "_bm25_index_count", lambda: (8, None))
    out = _run(capsys)
    assert "[warn] 语料扫描失败" in out
    assert "覆盖率检查跳过" in out
    assert "向量数: 8" in out and "文档数: 8" in out
    assert "覆盖率" in out and "[warn] BM25 覆盖率" not in out and "[warn] Embedding 覆盖率" not in out


def test_embed_stats_error_still_exits_1(monkeypatch, capsys):
    """Embedding 索引读取失败：保留既有 exit 1 行为。"""
    import pytest
    _patch_common(monkeypatch, corpus_n=2,
                  embed_stats={"exists": False, "count": 0, "dim": 0, "error": "bad json"})
    with pytest.raises(SystemExit) as exc:
        _run(capsys)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "索引读取失败" in out


def test_bm25_index_count_reads_signed_pkl(monkeypatch, tmp_path):
    """_bm25_index_count 走安全反序列化：正常 pkl 返回文档数，坏文件返回 error。"""
    pkl = tmp_path / "bm25_index.pkl"
    _paths.safe_pickle_dump({"paths": ["a", "b", "c"]}, str(pkl))
    monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(pkl))
    count, err = _cli_cmds_idx._bm25_index_count()
    assert (count, err) == (3, None)

    with open(pkl, "wb") as f:
        f.write(b"not-a-pickle")
    count, err = _cli_cmds_idx._bm25_index_count()
    assert count == 0 and err
    os.remove(pkl)
    count, err = _cli_cmds_idx._bm25_index_count()
    assert (count, err) == (None, None)  # 不存在
