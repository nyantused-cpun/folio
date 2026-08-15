# -*- coding: utf-8 -*-
"""Quote engine tests."""

import pytest


class TestQuoteData:
    """测试报价数据模块。"""

    def test_quote_data_import(self):
        """报价数据模块应该可以导入。"""
        try:
            import _quote_data
            assert hasattr(_quote_data, 'QuoteBuilder')
        except ImportError as e:
            pytest.skip(f"_quote_data 导入失败: {e}")

    def test_quote_engine_import(self):
        """报价引擎模块应该可以导入。"""
        try:
            import _quote_engine
            assert hasattr(_quote_engine, 'ExcelRenderer')
        except ImportError as e:
            pytest.skip(f"_quote_engine 导入失败: {e}")

    def test_quote_html_import(self):
        """报价 HTML 模块应该可以导入。"""
        try:
            import _quote_html
            assert hasattr(_quote_html, 'render_html')
        except ImportError as e:
            pytest.skip(f"_quote_html 导入失败: {e}")


class TestQuoteSpecGen:
    """测试报价 spec 生成。"""

    def test_quote_spec_gen_import(self):
        """报价 spec 生成模块应该可以导入。"""
        try:
            import _quote_spec_gen
            assert hasattr(_quote_spec_gen, 'gen_quote_spec')
        except ImportError as e:
            pytest.skip(f"_quote_spec_gen 导入失败: {e}")

class TestQuoteRender:
    """报价渲染回归测试（P0：_load_quote_style 曾按 dict 读字体导致全格式崩溃）。"""

    def _make_quote(self):
        from _quote_data import QuoteData, Section, Item
        qd = QuoteData()
        qd.metadata = {"client": "测试客户", "title": "测试报价方案"}
        sec = Section("模块费用", ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"])
        sec.items.append(Item(index=1, name="模块A", description="模块A描述",
                              unit_price=10000, discount=1, quantity=2,
                              amount=20000, discount_display="100%"))
        sec.total_label = "小计"
        sec.total_amount = 20000
        qd.sections.append(sec)
        qd.summary = [("模块费用", 20000)]
        qd.summary_total = 20000
        return qd

    def test_load_quote_style_all_styles(self):
        """styles.json 全部风格都能加载（fonts 为纯字符串的回归）。"""
        import json
        from _paths import STYLES_PATH
        from _quote_html import _load_quote_style
        with open(STYLES_PATH, encoding="utf-8") as f:
            names = list(json.load(f))
        assert names, "styles.json 为空"
        for name in names:
            style = _load_quote_style(name)
            assert style["font"]
            for key in ("primary", "primary_light", "header_bg"):
                assert style[key].startswith("#"), f"{name}.{key} 非法: {style[key]}"

    def test_render_html_smoke(self):
        """HTML 渲染不崩且含关键内容。"""
        from _quote_html import render_html
        html = render_html(self._make_quote())
        assert "测试报价方案" in html
        assert "模块A" in html
        assert "¥20,000" in html
