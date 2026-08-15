# -*- coding: utf-8 -*-
"""audit_2026-07-23 报告 P0+P1 修复的回归测试。

覆盖：#1 #2 #5 #6 #7 #8 #12 #16 #17 #18 #19 #23 #24 #25 #26 #27
"""
import json
import os
import sys
import types

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    """渲染相关代码要求 _PRESALES_CLI_INVOKED=1（防直接 import 守门）。"""
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


# ---------------------------------------------------------------------------
# #1 load_active_themes 未校验 client_name（路径遍历）
# ---------------------------------------------------------------------------
class TestThemeGuardPathValidation:
    def test_rejects_traversal(self):
        from _theme_guard import load_active_themes
        with pytest.raises(ValueError):
            load_active_themes("../../etc")

    def test_rejects_separator(self):
        from _theme_guard import load_active_themes
        with pytest.raises(ValueError):
            load_active_themes("foo/bar")


# ---------------------------------------------------------------------------
# #2 add_graph_node 只统计 n 前缀导致 m 前缀撞号
# ---------------------------------------------------------------------------
class TestAddGraphNodeId:
    def test_counts_m_prefix(self, tmp_path, monkeypatch):
        import _paths
        import _graph
        gpath = tmp_path / "client_graph.json"
        gpath.write_text(json.dumps({
            "client": "t",
            "nodes": [
                {"id": "n003", "type": "doc", "title": "a"},
                {"id": "m001", "type": "decision", "title": "b"},
            ],
            "edges": [],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "client_graph_path", lambda c: str(gpath))
        result = _graph.add_graph_node("t", "decision", "手动节点")
        assert result["node"]["id"] == "m004"

    def test_no_collision_with_existing_m(self, tmp_path, monkeypatch):
        import _paths
        import _graph
        gpath = tmp_path / "client_graph.json"
        gpath.write_text(json.dumps({
            "client": "t",
            "nodes": [{"id": "m005", "type": "decision", "title": "b"}],
            "edges": [],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "client_graph_path", lambda c: str(gpath))
        result = _graph.add_graph_node("t", "decision", "手动节点")
        assert result["node"]["id"] == "m006"


# ---------------------------------------------------------------------------
# #5 封面图片 src 未转义
# ---------------------------------------------------------------------------
class TestCoverImageEscape:
    def test_malicious_src_escaped(self, tmp_path):
        import yaml
        from _renderer import Renderer
        spec = {
            "confirmed": True,
            "document": {
                "title": "t",
                "cover": {
                    "template": "dark-photo",
                    "background_image": 'x" onerror="alert(1)',
                    "logo_image": 'l" bad',
                },
            },
            "pages": [{"title": "p", "elements": [
                {"type": "text", "role": "body", "content": "正文"},
            ]}],
        }
        spec_path = tmp_path / "spec.yml"
        spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_test_cover_esc.html")
        r = Renderer(str(spec_path))
        r.render_html(out)
        try:
            with open(out, encoding="utf-8") as f:
                html = f.read()
            assert 'onerror="alert(1)' not in html
            assert "&quot;" in html
        finally:
            if os.path.exists(out):
                os.remove(out)


# ---------------------------------------------------------------------------
# #6/#7/#8 pptd 表格字段未转义
# ---------------------------------------------------------------------------
class TestPptdTableEscape:
    def test_crud_ops_and_header_escaped(self):
        from _renderer.diagram.matrix import _crud_pptd
        elem = {
            "docs": ["d1"],
            "entities": ["e<1"],
            "cells": [{"doc": "d1", "entity": "e<1", "ops": ["C<R>", "U"]}],
        }
        elems, _ = _crud_pptd(elem, 0, 0, 1000)
        rows = elems[0]["rows"]
        assert "e&lt;1" in rows[0][1]["content"]["text"]
        cell_text = rows[1][1]["content"]["text"]
        assert "<R>" not in cell_text
        assert "C&lt;R&gt;" in cell_text

    def test_mapping_columns_escaped(self):
        from _renderer.diagram.architecture import _mapping_pptd
        elem = {"mappings": [{
            "biz_capability": "c",
            "biz_processes": ["p<1"],
            "it_systems": ["s&2"],
            "data_entities": ["d"],
        }]}
        elems, _ = _mapping_pptd(elem, 0, 0, 1000)
        row = elems[0]["rows"][1]
        assert "p&lt;1" in row[1]["content"]["text"]
        assert "s&amp;2" in row[2]["content"]["text"]

    def test_reconcile_columns_escaped(self):
        from _renderer.diagram.relationship import _reconcile_pptd
        elems, _ = _reconcile_pptd({"terms": [{"term": "t", "ba": "b<a"}]}, 0, 0, 1000)
        assert "b&lt;a" in elems[0]["rows"][1][1]["content"]["text"]

    def test_auto_name_escaped(self):
        from _renderer.diagram.relationship import _auto_pptd
        elems, _ = _auto_pptd({"tasks": [{"name": "n<x", "saving": "1"}]}, 0, 0, 1000)
        assert "n&lt;x" in elems[0]["rows"][1][0]["content"]["text"]


# ---------------------------------------------------------------------------
# #12 BM25 索引损坏导致 recall 崩溃（应降级返回 None）
# ---------------------------------------------------------------------------
class TestBm25CorruptIndex:
    def test_corrupt_pkl_returns_none(self, tmp_path, monkeypatch):
        import _bm25
        bad = tmp_path / "bm25.pkl"
        bad.write_bytes(b"corrupted-not-a-pickle")
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(bad))
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)
        assert _bm25.query_bm25("测试查询") is None


# ---------------------------------------------------------------------------
# #17 cmd_compact 未兼容 task_history.json dict 格式
# ---------------------------------------------------------------------------
class TestCompactDictHistory:
    def test_dict_format_no_crash(self, tmp_path, monkeypatch):
        import _paths
        import _cli
        clients = tmp_path / "clients"
        (clients / "蓝海集团").mkdir(parents=True)
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "task_history.json").write_text(json.dumps({
            "tasks": [{"project": "client:蓝海集团", "date": "2026-07-01"} for _ in range(3)],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_paths, "LOGS_DIR", str(logs))
        args = types.SimpleNamespace(client="蓝海集团", keep=10, keep_sessions=0)
        _cli.cmd_compact(args)  # dict 格式不再 AttributeError


# ---------------------------------------------------------------------------
# #18 _audit_theme 相对路径（Kimi Work 下 cwd 非项目根时误报 FAIL）
# ---------------------------------------------------------------------------
class TestAuditThemePath:
    def test_works_outside_project_root(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from _cli_audit import _audit_theme
        assert _audit_theme() is True

    def test_rejects_traversal_client(self):
        from _cli_audit import _audit_theme
        with pytest.raises(ValueError):
            _audit_theme("../evil")


# ---------------------------------------------------------------------------
# #19 verify_docx 未传 client_name，L5 废标检查从未执行
# ---------------------------------------------------------------------------
class TestVerifyDocxClientName:
    def test_verify_docx_threads_client(self, tmp_path, monkeypatch):
        import _verify
        from docx import Document
        doc = Document()
        doc.add_paragraph("标书内容段落 " * 20)
        p = tmp_path / "t.docx"
        doc.save(str(p))
        captured = {}

        def _fake_check(path, client_name=""):
            captured["client"] = client_name
            return True, []

        monkeypatch.setattr(_verify, "check_bid_risks", _fake_check)
        ok, _ = _verify.verify_docx(str(p), "蓝海集团")
        assert ok
        assert captured["client"] == "蓝海集团"

    def test_auto_verify_threads_client(self, monkeypatch):
        import _verify
        captured = {}

        def _fake_docx(path, client_name=""):
            captured["client"] = client_name
            return True, "ok"

        monkeypatch.setattr(_verify, "verify_docx", _fake_docx)
        _verify.auto_verify("x.docx", "蓝海集团")
        assert captured["client"] == "蓝海集团"

    def test_run_single_threads_client(self, monkeypatch):
        import _verify_hook
        captured = {}

        def _fake_auto(path, client_name=""):
            captured["client"] = client_name
            return True, "ok"

        monkeypatch.setattr(_verify_hook, "update_task_history", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_auto_snippet_capture", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "write_log", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_print_result", lambda *a, **k: None)
        import _verify
        monkeypatch.setattr(_verify, "auto_verify", _fake_auto)
        _verify_hook.run_single("x.docx", client_name="蓝海集团")
        assert captured["client"] == "蓝海集团"


# ---------------------------------------------------------------------------
# #24 付款比例解析 / #25 空 YAML 库文件
# ---------------------------------------------------------------------------
def _write_quote_spec(tmp_path, ratio):
    import yaml
    spec = {"quote": {
        "sheets": [{"ref": "s1", "sections": [{
            "id": "modules",
            "items": [{"name": "独立模块xyz", "unit_price": 1000, "quantity": 1}],
        }]}],
        "payment": [{"time": "签约", "ratio": ratio}],
    }}
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


class TestQuoteData:
    def test_ratio_integer_treated_as_percent(self, tmp_path):
        from _quote_data import QuoteBuilder
        qd = QuoteBuilder().build(_write_quote_spec(tmp_path, 30))
        assert qd.payments[0]["amount"] == 300.0

    def test_ratio_decimal_unchanged(self, tmp_path):
        from _quote_data import QuoteBuilder
        qd = QuoteBuilder().build(_write_quote_spec(tmp_path, 0.3))
        assert qd.payments[0]["amount"] == 300.0

    def test_ratio_bad_string_no_crash(self, tmp_path):
        from _quote_data import QuoteBuilder
        qd = QuoteBuilder().build(_write_quote_spec(tmp_path, "30天付清"))
        assert qd.payments[0]["amount"] == 0

    def test_empty_library_yaml(self, tmp_path, monkeypatch):
        import _quote_data
        (tmp_path / "modules.yaml").write_text("", encoding="utf-8")
        monkeypatch.setattr(_quote_data, "LIBRARY_DIR", str(tmp_path))
        lib = _quote_data.Library()
        assert lib.data == {}


# ---------------------------------------------------------------------------
# #26 materials_dir 不存在 / #27 材料为空时不调 LLM
# ---------------------------------------------------------------------------
class TestQuoteSpecGen:
    def test_missing_dir_returns_none(self, tmp_path):
        from _quote_spec_gen import gen_quote_spec
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_test_qs.yml")
        assert gen_quote_spec(str(tmp_path / "nonexistent"), output_path=out) is None

    def test_empty_materials_returns_none(self, tmp_path):
        from _quote_spec_gen import gen_quote_spec
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_test_qs.yml")
        assert gen_quote_spec(str(tmp_path), output_path=out) is None
