# -*- coding: utf-8 -*-
"""B4 回归：模板容量截断前移构建层（B3 A7 残余）。

缺陷背景：cmd_quote_build fmt=all 时 HTML 先于 Excel 渲染，容量截断原在
ExcelRenderer.render 内部才执行，HTML 读到截断前的 QuoteData——溢出场景
HTML 与 Excel 两产物数字可能不一致。修为在渲染分叉前、模板已确定
（args.template）处调用模块级 apply_section_capacity，HTML/Excel/汇总区
消费同一份已截断数据；渲染器内同名截断保留为幂等兜底。
"""

import re
from types import SimpleNamespace

import openpyxl


# ============================================================
# 模块级 apply_section_capacity 语义（构建层入口）
# ============================================================

def _make_quote(n_items):
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


def _onepage_slots():
    """一页报价模板 implementation 区块容量 6（data_start=11, total_row=17）。"""
    return {"sections": {"implementation": {
        "data_start": 11, "total_row": 17, "use_formula": True}}}


class TestBuildLayerCapacity:
    """模块级函数与渲染器方法同语义（B3 口径不变，只换调用时点）。"""

    def test_module_function_truncates_and_rewrites(self, capsys):
        from _quote_engine import apply_section_capacity
        qd = _make_quote(8)   # 8 项 > 容量 6
        ret = apply_section_capacity(qd, _onepage_slots())
        assert ret is qd                       # 原地改写并返回同一对象
        sec = qd.sections[0]
        assert len(sec.items) == 6
        assert sec.total_amount == 6000                     # 原 8000，丢弃 2 行
        assert qd.summary == [("二、实施服务报价", 6000)]   # 汇总区/HTML 同源
        assert qd.summary_total == 6000
        assert qd.payments[0]["amount"] == 1800             # 付款金额同步重算
        out = capsys.readouterr().out
        assert "二、实施服务报价" in out and "7~8" in out and "丢弃" in out

    def test_module_function_matches_by_sheet_ref(self, capsys):
        """完整模板按 sheet_ref 匹配区块（多 sheet），构建层同样生效。"""
        from _quote_engine import apply_section_capacity
        qd = _make_quote(8)
        slots = {"sheets": {"实施服务": {
            "data_start": 5, "data_end": 10, "total_row": 11}}}
        apply_section_capacity(qd, slots)
        assert len(qd.sections[0].items) == 6
        assert qd.summary_total == 6000
        assert "丢弃" in capsys.readouterr().out

    def test_idempotent_no_duplicate_warning(self, capsys):
        """幂等：构建层截断后渲染器兜底调用不再重复告警或改写。"""
        from _quote_engine import ExcelRenderer, apply_section_capacity
        qd = _make_quote(8)
        apply_section_capacity(qd, _onepage_slots())
        capsys.readouterr()                       # 清掉第一次的告警
        ExcelRenderer()._apply_section_capacity(qd, _onepage_slots())
        out = capsys.readouterr().out
        assert "超出模板上限" not in out and "丢弃" not in out
        assert qd.summary_total == 6000

    def test_renderer_method_delegates_same_result(self):
        """渲染器方法与模块级函数产出一致（直呼渲染器时兜底口径不变）。"""
        from _quote_engine import ExcelRenderer, apply_section_capacity
        a = _make_quote(8)
        apply_section_capacity(a, _onepage_slots())
        b = _make_quote(8)
        ExcelRenderer()._apply_section_capacity(b, _onepage_slots())
        assert b.summary_total == a.summary_total == 6000
        assert len(b.sections[0].items) == len(a.sections[0].items) == 6

    def test_within_capacity_untouched(self, capsys):
        """未溢出时数据与告警均不变。"""
        from _quote_engine import apply_section_capacity
        qd = _make_quote(5)
        apply_section_capacity(qd, _onepage_slots())
        assert len(qd.sections[0].items) == 5
        assert qd.summary_total == 5000
        assert qd.payments[0]["amount"] == 1500
        assert "丢弃" not in capsys.readouterr().out


# ============================================================
# cmd_quote_build fmt=all 三方一致（端到端，真模板真渲染）
# ============================================================

# 一页报价模板：implementation 容量 6 行；9 项每项 1000 → 截断后 6000
_SPEC_YAML = """title: 测试报价方案
client: 测试客户
tax_rate: 0.06
global_discount: 1.0
sheets:
  - ref: 实施服务
    sections:
      - id: implementation
        items:
{items}
payment:
  - {{time: 签约后, type: 首款, ratio: "30%"}}
"""

_ITEMS = "\n".join(
    f'          - {{name: 服务{i}, unit_price: 1000, quantity: 1, unit: 项}}'
    for i in range(1, 10))


def _stub_guards(monkeypatch):
    """桩掉与容量截断正交的机械门（确认/门禁/检查/验证/备份/路径白名单）。"""
    import _cli_generate
    import _cli_guards
    import _quote_gate
    import _renderer
    import _verify_hook
    monkeypatch.setattr(_cli_guards, "require_confirmed", lambda *a, **k: None)
    monkeypatch.setattr(_cli_generate, "_run_pre_check",
                        lambda client_name=None: True)
    monkeypatch.setattr(_cli_generate, "backup_before_generate",
                        lambda *a, **k: None)
    monkeypatch.setattr(_cli_generate, "_run_post_check",
                        lambda *a, **k: None)
    monkeypatch.setattr(_quote_gate, "check_build", lambda spec_path: [])
    monkeypatch.setattr(_renderer, "_validate_output_path", lambda p: p)
    monkeypatch.setattr(_verify_hook, "run_single", lambda *a, **k: True)


def _run_quote_build(monkeypatch, tmp_path, fmt):
    import _cli_generate
    _stub_guards(monkeypatch)
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(_SPEC_YAML.format(items=_ITEMS), encoding="utf-8")
    args = SimpleNamespace(
        spec=str(spec_path), template="一页报价模板", format=fmt,
        style="enterprise", client=None,
        output=str(tmp_path / "测试客户_报价_v1.xlsx"))
    _cli_generate.cmd_quote_build(args)
    base = str(tmp_path / "测试客户_报价_v1")
    return base + ".html", base + ".xlsx"


def _html_grand_total(html):
    m = re.search(r"报价总价（RMB）</td><td class=\"amt\">([^<]*)</td>", html)
    assert m, "HTML 汇总区未找到报价总价"
    return float(m.group(1).replace("¥", "").replace(",", ""))


class TestFmtAllThreeWayConsistency:
    """fmt=all：HTML 合计 == Excel 汇总区 == 构建层截断后口径。"""

    def test_html_equals_excel_summary(self, monkeypatch, tmp_path, capsys):
        html_path, xlsx_path = _run_quote_build(monkeypatch, tmp_path, "all")
        out = capsys.readouterr().out

        # 告警保留（区块名+行号），且只来自构建层一次（渲染器兜底幂等）
        assert "二、实施服务报价" in out and "7~9" in out and "丢弃" in out
        assert out.count("超出模板上限") == 1

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        html_total = _html_grand_total(html)

        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb[wb.sheetnames[0]]
        excel_total = ws.cell(row=8, column=8).value       # summary.total_row
        excel_section = ws.cell(row=7, column=7).value     # row_map G 列折后价

        # 三方一致：HTML == Excel 汇总区 == 截断后 6000（原 9000）
        assert html_total == excel_total == excel_section == 6000
        assert "¥9,000" not in html                        # 截断前总价不可见
        assert html.count("服务9") == 0                    # 溢出行不出现在 HTML

    def test_html_only_keeps_all_rows(self, monkeypatch, tmp_path, capsys):
        """fmt=html 无 Excel 模板约束，保持不截断（HTML 无行上限，自身自洽）。"""
        html_path, _ = _run_quote_build(monkeypatch, tmp_path, "html")
        out = capsys.readouterr().out
        assert "超出模板上限" not in out                    # 构建层未截断
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        assert _html_grand_total(html) == 9000
        assert "服务9" in html

    def test_xlsx_only_truncated_at_build_layer(self, monkeypatch, tmp_path,
                                                capsys):
        """fmt=xlsx：截断同样发生在构建层，渲染器兜底不重复告警。"""
        _, xlsx_path = _run_quote_build(monkeypatch, tmp_path, "xlsx")
        out = capsys.readouterr().out
        assert out.count("超出模板上限") == 1
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb[wb.sheetnames[0]]
        assert ws.cell(row=8, column=8).value == 6000
