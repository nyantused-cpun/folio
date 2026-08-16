# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""路径安全回归测试：输出白名单前缀绕过 + 客户名路径穿越 + BM25 索引签名。"""

import os

import pytest


class TestOutputPathWhitelist:
    """_validate_output_path 必须拒绝前缀兄弟目录（曾用 startswith，被 output_evil 绕过）。"""

    def test_prefix_sibling_dir_rejected(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import _validate_output_path, OutputPathNotAllowedError, SCRIPT_DIR
        with pytest.raises(OutputPathNotAllowedError):
            _validate_output_path(os.path.join(SCRIPT_DIR, "output_evil", "x.html"))

    def test_ppt_workspace_sibling_rejected(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import _validate_output_path, OutputPathNotAllowedError, SCRIPT_DIR
        with pytest.raises(OutputPathNotAllowedError):
            _validate_output_path(os.path.join(SCRIPT_DIR, "ppt_workspace2", "x.pptx"))

    def test_valid_output_allowed(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import _validate_output_path, SCRIPT_DIR
        # 不抛异常即通过
        _validate_output_path(os.path.join(SCRIPT_DIR, "output", "通用", "x.html"))

    @pytest.mark.skipif(os.name != "nt", reason="normcase 大小写归一仅 Windows")
    def test_case_insensitive_on_windows(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import _validate_output_path, SCRIPT_DIR
        _validate_output_path(os.path.join(SCRIPT_DIR, "OUTPUT", "x.html"))


class TestClientNameValidation:
    """客户名路径穿越校验覆盖（_context / _aliases 曾未调用 _validate_client_name）。"""

    def test_ensure_client_dir_rejects_traversal(self):
        import _context
        with pytest.raises(ValueError):
            _context.ensure_client_dir("../../tmp/evil")

    def test_get_context_path_rejects_traversal(self):
        import _context
        with pytest.raises(ValueError):
            _context.get_context_path("..\\..\\evil")

    def test_aliases_import_rejects_malicious_scope(self, tmp_path):
        """Excel 第三列（适用范围）是外部输入，必须校验。"""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["标准词", "别名", "适用范围"])
        ws.append(["测试词", "别名1", "../../evil"])
        xlsx = tmp_path / "aliases.xlsx"
        wb.save(xlsx)
        import _aliases
        with pytest.raises(ValueError):
            _aliases.import_from_excel(str(xlsx))


class TestWritePointWhitelist:
    """§八 3.5：quote-build / spec-gen / outline-to-spec / quote-spec-gen / cite-audit
    的写入点全部过 _validate_output_path（库层兜底 + CLI 层前置提示）。"""

    WL_DIR = os.path.join("output", "通用", "_wl_test")

    def _make_quote(self):
        from _quote_data import QuoteData, Section, Item
        qd = QuoteData()
        qd.metadata = {"client": "测试客户", "title": "测试报价"}
        sec = Section("模块费用", ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"])
        sec.items.append(Item(index=1, name="模块A", description="模块A描述",
                              unit_price=100, discount=1, quantity=1,
                              amount=100, discount_display="100%"))
        sec.total_label = "小计"
        sec.total_amount = 100
        qd.sections.append(sec)
        return qd

    def _wl_path(self, filename):
        from _renderer import SCRIPT_DIR
        out_dir = os.path.join(SCRIPT_DIR, self.WL_DIR)
        os.makedirs(out_dir, exist_ok=True)
        self._cleanup_dir = out_dir
        return os.path.join(out_dir, filename)

    def teardown_method(self):
        import shutil
        d = getattr(self, "_cleanup_dir", None)
        if d and os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)

    def test_quote_html_write_outside_blocked(self, tmp_path):
        from _quote_html import render_html
        from _renderer import OutputPathNotAllowedError
        with pytest.raises(OutputPathNotAllowedError):
            render_html(self._make_quote(), str(tmp_path / "q.html"))

    def test_quote_html_write_inside_allowed(self):
        from _quote_html import render_html
        out = self._wl_path("q.html")
        render_html(self._make_quote(), out)
        assert os.path.exists(out)

    def test_quote_xlsx_write_outside_blocked(self, tmp_path):
        """校验在 render 入口，先于模板复制，无需真实模板即可触发。"""
        from _quote_engine import ExcelRenderer
        from _renderer import OutputPathNotAllowedError
        with pytest.raises(OutputPathNotAllowedError):
            ExcelRenderer().render(self._make_quote(), "一页报价模板",
                                   str(tmp_path / "q.xlsx"))

    def test_quote_xlsx_write_inside_allowed(self):
        """真实模板渲染到白名单内路径（顺带覆盖 B1 修复后的 xlsx 渲染链路）。"""
        import _quote_data
        src = _quote_data.get_template_source("一页报价模板")
        if not os.path.exists(src):
            pytest.skip("一页报价模板 source.xlsx 不存在")
        from _quote_engine import ExcelRenderer
        out = self._wl_path("q.xlsx")
        ExcelRenderer().render(self._make_quote(), "一页报价模板", out)
        assert os.path.exists(out)

    def test_outline_to_spec_outside_blocked_at_entry(self, tmp_path):
        """build_spec_from_outline 入口校验：出名单路径在材料读取/LLM 调用前即抛。"""
        import _outline_to_spec
        from _renderer import OutputPathNotAllowedError
        with pytest.raises(OutputPathNotAllowedError):
            _outline_to_spec.build_spec_from_outline(
                "不存在的场景", ["x.txt"], output_path=str(tmp_path / "spec.yml"))

    def test_quote_spec_gen_outside_blocked_at_entry(self, tmp_path):
        """gen_quote_spec 入口校验：出名单路径在材料读取/LLM 调用前即抛。"""
        import _quote_spec_gen
        from _renderer import OutputPathNotAllowedError
        with pytest.raises(OutputPathNotAllowedError):
            _quote_spec_gen.gen_quote_spec(
                str(tmp_path), output_path=str(tmp_path / "quote_spec.yml"))


class TestBm25SignedIndex:
    """BM25 索引写读签名一致（曾裸 pickle.dump 写、safe_pickle_load 读，每次加载都告警）。"""

    def test_index_roundtrip_without_warning(self, monkeypatch, tmp_path):
        import warnings
        import _bm25
        monkeypatch.setattr(_bm25, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)
        # 语料需够大：BM25 idf=ln((N-n+0.5)/(n+0.5))，2 文档时 idf≈0 分数恒 0
        paths = [f"{c}.md" for c in "abcde"]
        texts = ["测试 文档 一", "另一份 材料", "完全 无关 内容", "报价 单 模板", "客户 需求 清单"]
        _bm25.build_bm25_index(paths, texts)
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            results = _bm25.query_bm25("测试")
        assert results
        assert not any("HMAC" in str(w.message) for w in caught)
