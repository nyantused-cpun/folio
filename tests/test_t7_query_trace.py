# -*- coding: utf-8 -*-
"""T7 query_trace 模块测试。"""

import _query_trace


class TestQueryTrace:
    def test_write_and_read_roundtrip(self, tmp_path, monkeypatch):
        trace_file = tmp_path / "query_trace.jsonl"
        monkeypatch.setattr(_query_trace, "QUERY_TRACE_PATH", str(trace_file))
        _query_trace.write_query_trace({"query": "q1", "mode": "BM25"})
        _query_trace.write_query_trace({"query": "q2", "mode": "BM25 + Embedding RRF"})
        records = _query_trace.read_query_trace()
        assert len(records) == 2
        assert records[0]["query"] == "q1"
        assert records[0]["ts"]
        assert records[-1]["mode"] == "BM25 + Embedding RRF"

    def test_limit_returns_recent(self, tmp_path, monkeypatch):
        trace_file = tmp_path / "query_trace.jsonl"
        monkeypatch.setattr(_query_trace, "QUERY_TRACE_PATH", str(trace_file))
        for i in range(5):
            _query_trace.write_query_trace({"query": f"q{i}"})
        records = _query_trace.read_query_trace(limit=2)
        assert [r["query"] for r in records] == ["q3", "q4"]

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            _query_trace, "QUERY_TRACE_PATH", str(tmp_path / "no.jsonl")
        )
        assert _query_trace.read_query_trace() == []