# -*- coding: utf-8 -*-
"""flow_rows 第 28 种子类型 HTML 渲染测试（dev_plan_visual_v2 §8，T4）。

覆盖：行/分组/角色色条/badge/箭头/dashed_opt 可选项（F6 语义表）、
roles→legend 自动生成、exhibit 图框包装、端到端注入、防注入转义。
"""
import os

from _renderer.diagram.flow import render_flow_rows
from _renderer.diagram import render_diagram_html


def _elem(**kw):
    elem = {
        "type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
        "title": "合同管理 TO-BE 主流程",
        "desc": "行式流程说明",
        "roles": {
            "biz": {"label": "业务 / 采购"},
            "legal": {"label": "法务 / 审批控制"},
            "fin": {"label": "财务 / 履约"},
            "sys": {"label": "平台能力"},
            "ext": {"label": "外部系统 / 可选项"},
        },
        "rows": [
            {"label": "相对方", "label_sub": "准入即风控", "group": "blue",
             "cards": [
                 {"badge": "1", "label": "相对方准入申请",
                  "desc": "信息录入 + 资料附件", "role": "biz"},
                 {"badge": "2", "label": "资格审核", "desc": "不通过即拦截",
                  "role": "legal"}]},
            {"arrow": "down"},
            {"label": "用印", "group": "teal",
             "cards": [{"badge": "9", "label": "电子签用印", "role": "ext"}]},
            {"style": "dashed_opt",
             "cards": [{"label": "纸质用印", "desc": "实体章场景保留",
                        "role": "ext", "dim": True, "badge": "10"}]},
            {"arrow": "up"},
        ],
    }
    elem.update(kw)
    return elem


def test_rows_structure():
    html = render_flow_rows(_elem())
    assert 'class="flow-canvas"' in html
    assert 'class="flow-row g-blue"' in html
    assert 'class="flow-row g-teal"' in html
    assert "相对方" in html and "准入即风控" in html
    assert 'class="num-badge">1<' in html
    assert 'class="flow-card r-biz"' in html
    assert 'class="flow-card r-legal"' in html
    assert "相对方准入申请" in html and "不通过即拦截" in html
    # 行内卡间 →，行间 ↓/↑
    assert '<div class="flow-arrow">→</div>' in html
    assert '<div class="flow-down">↓</div>' in html
    assert '<div class="flow-down">↑</div>' in html


def test_dashed_opt_row():
    """F6：可选项行 = 虚线框 + 竖排标签 + 卡间 ⇢ + 抑制编号。"""
    html = render_flow_rows(_elem())
    assert "dashed-opt" in html
    assert '<span class="opt-tag">可选项</span>' in html
    assert "flow-card r-ext dim" in html
    # badge 抑制（schema 已 warning，渲染层同步）
    assert '<div class="num-badge">10</div>' not in html
    # 主行 badge 保留
    assert '<div class="num-badge">1</div>' in html


def test_dashed_opt_multi_card_arrow():
    elem = _elem(rows=[
        {"style": "dashed_opt",
         "cards": [{"label": "A"}, {"label": "B"}]}])
    html = render_flow_rows(elem)
    assert '<div class="flow-arrow dashed">⇢</div>' in html
    # 带行标签的可选项行：标签 + 可选项 并存
    elem = _elem(rows=[
        {"label": "用印", "style": "dashed_opt", "cards": [{"label": "A"}]}])
    html = render_flow_rows(elem)
    assert "用印" in html and "可选项" in html


def test_roles_legend_autogen():
    """roles >2 色自动生成 legend_bar（§8.1）；≤2 色不生成。"""
    html = render_flow_rows(_elem())
    assert 'class="legend-bar"' in html
    assert "业务 / 采购" in html and "法务 / 审批控制" in html
    assert 'legend-swatch sw-role-biz' in html
    assert 'legend-swatch sw-role-ext' in html
    # ≤2 角色不出 legend
    html = render_flow_rows(_elem(roles={"biz": {"label": "业务"},
                                         "legal": {"label": "法务"}}))
    assert 'class="legend-bar"' not in html
    # 无 roles 不出 legend
    html = render_flow_rows(_elem(roles=None))
    assert 'class="legend-bar"' not in html


def test_injection_safe():
    html = render_flow_rows(_elem(rows=[
        {"label": "<script>x</script>",
         "cards": [{"label": "<img onerror=alert(1)>", "desc": "<b>d</b>"}]}]))
    assert "<script>" not in html and "<img" not in html and "<b>d</b>" not in html
    assert "&lt;script&gt;" in html


def test_exhibit_wrap():
    """exhibit 图框包装（§5.5）：编号 + 标题 + 来源行。"""
    elem = _elem(exhibit={"num": "EXHIBIT 2",
                          "title": "合同管理 TO-BE 主流程（含履约闭环）"},
                 source="来源：分项功能清单 V2.0")
    html = render_diagram_html(elem)
    assert 'class="exhibit"' in html
    assert 'class="exhibit-num">EXHIBIT 2<' in html
    assert 'class="exhibit-title"' in html and "履约闭环" in html
    assert 'class="exhibit-source"' in html and "分项功能清单 V2.0" in html
    assert 'class="flow-canvas"' in html  # 图框内含图
    # 无 exhibit/source 不包装
    html = render_diagram_html(_elem())
    assert 'class="exhibit"' not in html


def test_dispatch_end_to_end(tmp_path):
    """端到端：spec flow_rows → 完整 HTML（tokens + chrome CSS + 图）。"""
    import shutil
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        from _renderer import Renderer
        import yaml
        spec = tmp_path / "spec.yml"
        spec.write_text(yaml.safe_dump({
            "confirmed": True, "theme": "consulting_kpmg",
            "pages": [{"id": "p1", "title": "流程", "layout": "P05",
                       "elements": [
                           {"type": "section_tag", "label": "流程"},
                           {"type": "action_title",
                            "segments": [{"t": "合同五段闭环 8 步"}]},
                           _elem(),
                           {"type": "legend_bar", "items": [
                               {"swatch": "lit", "label": "已点亮"}]},
                       ]}],
        }, allow_unicode=True), encoding="utf-8")
        r = Renderer(str(spec))
        out_dir = os.path.join("output", "通用", "flow_rows_test")
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        try:
            out = os.path.join(out_dir, "out.html")
            r.render_html(out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
        finally:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)
        assert "--t-primary:#00338D" in html
        assert ".flow-canvas" in html
        assert 'class="flow-canvas"' in html
        assert 'class="flow-row g-blue"' in html
        assert "可选项" in html
    finally:
        os.environ.pop("_PRESALES_CLI_INVOKED", None)
