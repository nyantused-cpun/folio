# -*- coding: utf-8 -*-
"""B3 报价回归：折扣百分比标签舍入 + 区块溢出行口径。

缺陷背景：
1. 折扣标签 int(x*100) 在 IEEE754 下截断（0.29→"28%"、0.57→"56%"），
   客户可见；修为 Decimal(str(x)) 四舍五入（0.285→"29%"）。
2. 区块行数超模板上限时超出行被静默丢弃但仍计入合计/汇总区（非公式模式）；
   修为丢弃行不计入区块合计与汇总区（公式/非公式同口径），并打印告警。
"""

import pytest
import openpyxl
from openpyxl.styles import Font


# ============================================================
# 缺陷 1：折扣百分比标签
# ============================================================

class TestDiscountPctLabel:
    """0.85/0.9/0.29/0.57/0.285 边界实测表（round 银行家舍入对 0.285 失效）。"""

    @pytest.mark.parametrize("ratio,expected", [
        (0.85, "85%"),
        (0.9, "90%"),
        (0.29, "29%"),   # int 截断曾得 "28%"
        (0.57, "57%"),   # int 截断曾得 "56%"
        (0.285, "29%"),  # 28.499999... 边界，四舍五入应为 29%
        (1, "100%"),
        (0, "0%"),
    ])
    def test_numeric_discount_label(self, ratio, expected):
        from _quote_data import normalize_discount
        _, is_gift, display = normalize_discount(ratio)
        assert display == expected
        assert not is_gift

    def test_global_discount_label(self):
        """空折扣继承全局折扣，标签同语义。"""
        from _quote_data import normalize_discount
        _, _, display = normalize_discount(None, global_discount=0.57)
        assert display == "57%"

    @pytest.mark.parametrize("raw,expected", [
        ("57%", "57%"),      # 百分号字符串回显
        ("28.5%", "29%"),    # 字符串路径同样过 .5 边界
        ("0.57", "57%"),     # 纯数字字符串
    ])
    def test_string_discount_label(self, raw, expected):
        from _quote_data import normalize_discount
        _, is_gift, display = normalize_discount(raw)
        assert display == expected
        assert not is_gift

    def test_gift_untouched(self):
        """赠送路径不受本次改动影响。"""
        from _quote_data import normalize_discount
        d, is_gift, display = normalize_discount("赠送")
        assert is_gift and d == 0 and display == "赠送"

    def test_section_discount_summary(self):
        """汇总区折扣摘要（discount_summary）走同一标签语义。"""
        from _quote_data import Section, Item
        sec = Section("模块费用", ["编号", "名称"])
        sec.items.append(Item(index=1, name="A", unit_price=100,
                              discount=0.29, quantity=1, amount=29))
        assert sec.discount_summary == "29%"


# ============================================================
# 缺陷 2：区块溢出行口径
# ============================================================

CAPACITY = 5   # data_start=5, data_end=9


def _make_section(n_items, unit_price=1000):
    """n_items 行、每行金额 1000 的区块。"""
    from _quote_data import Section, Item
    sec = Section("一、软件模块报价",
                  ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"])
    sec.items = [Item(index=i + 1, name=f"模块{i + 1}", unit_price=unit_price,
                      discount=1, quantity=1, amount=unit_price)
                 for i in range(n_items)]
    return sec


def _make_renderer():
    from _quote_engine import ExcelRenderer
    r = ExcelRenderer()
    r._f_data = Font(name="Arial", size=9)
    r._f_bold = Font(name="Arial", size=9, bold=True)
    r._f_red = Font(name="Arial", size=9, color="FF0000")
    return r


class TestOverflowBlockTotal:
    """区块合计只计容量内行（直呼 _fill_section，B1 折扣公式测试同款构造）。"""

    def _fill(self, sec, use_formula):
        ws = openpyxl.Workbook().active
        cfg = {"data_start": 5, "total_row": 10, "data_end": 9,
               "use_formula": use_formula}
        _make_renderer()._fill_section(ws, sec, cfg)
        return ws

    def test_formula_mode_dropped_rows_out_of_total(self, capsys):
        sec = _make_section(7)   # 7 项 > 5 行容量
        ws = self._fill(sec, use_formula=True)
        # 公式合计区间只覆盖容量内行（H10 是合计行，不是第 6 项数据）
        assert ws.cell(row=10, column=8).value == "=SUM(H5:H9)"
        assert ws.cell(row=9, column=8).value == "=F9*G9"
        # 告警含区块名与丢弃信息
        out = capsys.readouterr().out
        assert "一、软件模块报价" in out and "丢弃" in out

    def test_non_formula_mode_dropped_rows_out_of_total(self, capsys):
        sec = _make_section(7)
        ws = self._fill(sec, use_formula=False)
        kept = sum(it.amount for it in sec.items[:CAPACITY])
        dropped = sum(it.amount for it in sec.items[CAPACITY:])
        assert dropped == 2000                          # 2 行 × 1000
        assert ws.cell(row=10, column=8).value == kept  # 不含被丢弃行
        out = capsys.readouterr().out
        assert "丢弃" in out


class TestOverflowCapacityApplied:
    """渲染入口前置截断：丢弃行不计入区块合计/汇总区（HTML 同源）/付款金额。"""

    def _make_quote(self, n_items):
        from _quote_data import QuoteData, Section, Item
        qd = QuoteData()
        sec = Section("二、实施服务报价",
                      ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
                      section_id="implementation", sheet_ref="实施服务")
        sec.items = [Item(index=i + 1, name=f"服务{i + 1}", unit_price=1000,
                          discount=1, quantity=1, amount=1000)
                     for i in range(n_items)]
        sec.total_amount = sec.total_amount_computed
        qd.sections.append(sec)
        qd.summary = [(sec.title, sec.total_amount)]
        qd.summary_total = qd.total_amount()
        qd.payments = [{"time": "签约后", "type": "首款", "ratio": "30%",
                        "ratio_value": 0.3,
                        "amount": round(qd.summary_total * 0.3, 2)}]
        return qd

    def _apply(self, qd, use_formula=True):
        from _quote_engine import ExcelRenderer
        slots = {"sections": {"implementation": {
            "data_start": 11, "total_row": 17, "use_formula": use_formula}}}
        ExcelRenderer()._apply_section_capacity(qd, slots)
        return slots   # 容量 = 17-11 = 6 行

    def test_formula_mode_summary_excludes_dropped(self, capsys):
        qd = self._make_quote(8)   # 8 项 > 容量 6
        self._apply(qd)
        sec = qd.sections[0]
        assert len(sec.items) == 6
        assert sec.total_amount == 6000                     # 原 8000，丢弃 2 行
        assert qd.summary == [("二、实施服务报价", 6000)]   # 汇总区/HTML 同源
        assert qd.summary_total == 6000
        assert qd.payments[0]["amount"] == 1800             # 付款金额同步重算
        out = capsys.readouterr().out
        assert "二、实施服务报价" in out and "7~8" in out and "丢弃" in out

    def test_non_formula_mode_summary_and_body_consistent(self, capsys):
        qd = self._make_quote(8)
        self._apply(qd, use_formula=False)
        assert qd.sections[0].total_amount == 6000
        assert qd.summary_total == 6000
        # 交叉验证：截断后的 items 填表（容量 6 与截断后行数一致），正文合计 == 汇总区
        ws = openpyxl.Workbook().active
        _make_renderer()._fill_section(
            ws, qd.sections[0],
            {"data_start": 5, "total_row": 11, "data_end": 10,
             "use_formula": False})
        assert ws.cell(row=11, column=8).value == qd.summary_total   # H11 = 合计行
        assert ws.cell(row=10, column=8).value == 1000               # 末行数据在容量内
        assert "丢弃" in capsys.readouterr().out

    def test_multi_sheet_capacity_by_sheet_ref(self, capsys):
        """完整模板按 sheet_ref 匹配区块，同样前置截断。"""
        qd = self._make_quote(8)
        from _quote_engine import ExcelRenderer
        slots = {"sheets": {"实施服务": {
            "data_start": 5, "data_end": 10, "total_row": 11}}}
        ExcelRenderer()._apply_section_capacity(qd, slots)
        assert len(qd.sections[0].items) == 6
        assert qd.summary_total == 6000
        assert "丢弃" in capsys.readouterr().out

    def test_within_capacity_untouched(self):
        """未溢出时数据与告警均不变。"""
        qd = self._make_quote(5)
        self._apply(qd)
        assert len(qd.sections[0].items) == 5
        assert qd.sections[0].total_amount == 5000
        assert qd.summary_total == 5000
        assert qd.payments[0]["amount"] == 1500
