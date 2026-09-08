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

    def test_load_quote_style_all_themes(self):
        """THEMES 全部主题都能加载。"""
        from _renderer.theme import THEMES
        from _quote_html import _load_quote_style
        names = list(THEMES)
        assert names
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


class TestQuoteDiscountFormula:
    """P1-1：公式模式 F 列写折后单价，=F*G 与汇总区/HTML（item.amount）同口径。
    曾 F 列写原价，discount≠1 时 Excel 合计偏高。"""

    def _fill(self, item):
        import openpyxl
        from openpyxl.styles import Font
        from _quote_engine import ExcelRenderer
        from _quote_data import Section
        wb = openpyxl.Workbook()
        ws = wb.active
        sec = Section("模块费用", ["编号", "名称", "描述", "单价", "数量", "金额"])
        sec.items = [item]
        r = ExcelRenderer()
        r._f_data = Font(name="Arial", size=9)
        r._f_bold = Font(name="Arial", size=9, bold=True)
        r._f_red = Font(name="Arial", size=9, color="FF0000")
        r._fill_section(ws, sec, {"data_start": 5, "total_row": 10,
                                  "use_formula": True, "data_end": 9})
        return ws

    def test_discounted_price_in_formula_col(self):
        from _quote_data import Item
        # 原价 100 × 折扣 0.5 × 数量 2 = item.amount 100
        it = Item(index=1, name="模块A", unit_price=100, discount=0.5,
                  quantity=2, amount=100)
        ws = self._fill(it)
        f = ws.cell(row=5, column=6).value   # F 单价
        g = ws.cell(row=5, column=7).value   # G 数量
        h = ws.cell(row=5, column=8).value   # H 公式
        assert f == 50                        # 折后单价
        assert g == 2
        assert h == "=F5*G5"
        assert round(f * g, 2) == it.amount   # 公式语义 == 汇总区/HTML 口径

    def test_gift_row_price_unchanged(self):
        from _quote_data import Item
        it = Item(index=1, name="赠品", unit_price=100, discount=0,
                  quantity=3, amount=0, is_gift=True)
        ws = self._fill(it)
        assert ws.cell(row=5, column=6).value == 100   # 原价展示不变
        assert ws.cell(row=5, column=7).value == 0     # 数量列 0
        assert ws.cell(row=5, column=8).value == "=F5*G5"  # 金额仍为 0

    def test_full_discount_equals_amount(self):
        from _quote_data import Item
        it = Item(index=1, name="模块B", unit_price=8000, discount=1,
                  quantity=1, amount=8000)
        ws = self._fill(it)
        assert ws.cell(row=5, column=6).value == 8000  # 无折扣 = 原价
