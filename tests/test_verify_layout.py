# -*- coding: utf-8 -*-
"""verify 版式维测试（dev_plan_visual_v2 §10 六条检查，T7）。

error 阻断 / warning 列出（沿用现有级别语义）；schema 单点复核不重复实现。
"""
import yaml

from _verify import verify_spec_layout_data, auto_verify


def _spec(**kw):
    base = {"confirmed": True, "pages": []}
    base.update(kw)
    return base


def test_clean_v2_spec_passes():
    ok, errors, warnings = verify_spec_layout_data(_spec(
        theme="consulting_kpmg",
        pages=[{"layout": "P03", "elements": [
            {"type": "section_tag", "label": "结论"},
            {"type": "action_title",
             "segments": [{"t": "预算拦截率从 0% 提升至 100%"}]},
            {"type": "kpi_cards",
             "cards": [{"label": "拦截率", "from": "0%", "to": "100%"}]},
        ]}]))
    assert ok and errors == []
    assert warnings == []


def test_check1_layout_illegal_error():
    ok, errors, _ = verify_spec_layout_data(_spec(
        pages=[{"layout": "P99", "elements": []}]))
    assert not ok and any("未知版式" in e for e in errors)


def test_check1_missing_required_error():
    """§13.1-4 验收场景：P05 缺 legend_bar → error。"""
    ok, errors, _ = verify_spec_layout_data(_spec(
        pages=[{"layout": "P05", "elements": [
            {"type": "section_tag", "label": "流程"},
            {"type": "action_title", "segments": [{"t": "合同闭环 8 步"}]},
            {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
             "title": "x", "rows": [{"cards": [{"label": "a"}]}]},
        ]}]))
    assert not ok and any("legend_bar" in e for e in errors)


def test_check2_theme_and_hex_error():
    ok, errors, _ = verify_spec_layout_data(_spec(theme="swiss_ikb", pages=[]))
    assert not ok and any("theme" in e for e in errors)
    ok, errors, _ = verify_spec_layout_data(_spec(
        theme="consulting_kpmg",
        pages=[{"layout": "P01", "elements": [
            {"type": "hero", "title": "主色 #00338D"}]}]))
    assert not ok and any("hex" in e for e in errors)


def test_check3_action_title_warning():
    """§13.1-4 验收场景：action_title 无数字 → warning（不阻断）。"""
    ok, errors, warnings = verify_spec_layout_data(_spec(
        pages=[{"layout": "P02", "elements": [
            {"type": "section_tag", "label": "背景"},
            {"type": "action_title", "segments": [{"t": "业务背景介绍"}]},
        ]}]))
    assert ok and errors == []
    assert any("结论式标题" in w for w in warnings)
    # 短标题（<12 字）也报
    ok, _, warnings = verify_spec_layout_data(_spec(
        pages=[{"layout": "P02", "elements": [
            {"type": "section_tag", "label": "背景"},
            {"type": "action_title", "segments": [{"t": "3 页"}]},
        ]}]))
    assert any("结论式标题" in w for w in warnings)


def test_check4_legend_completeness_error():
    ok, errors, _ = verify_spec_layout_data(_spec(
        pages=[{"layout": "P08", "elements": [
            {"type": "section_tag", "label": "能力"},
            {"type": "action_title", "segments": [{"t": "点亮 74%"}]},
            {"type": "diagram", "diagram_type": "matrix",
             "subtype": "capability_map", "title": "点亮图",
             "sections": [{"name": "域", "items": []}]},
        ]}]))
    assert not ok and any("图例完备" in e or "legend_bar" in e for e in errors)
    # 补 legend_bar 后通过（P08 必需构件含 legend_bar，补齐即全绿）
    ok2, errors2, _ = verify_spec_layout_data(_spec(
        pages=[{"layout": "P08", "elements": [
            {"type": "section_tag", "label": "能力"},
            {"type": "action_title", "segments": [{"t": "点亮 74%"}]},
            {"type": "diagram", "diagram_type": "matrix",
             "subtype": "capability_map", "title": "点亮图",
             "sections": [{"name": "域", "items": []}]},
            {"type": "legend_bar",
             "items": [{"swatch": "lit", "label": "已点亮"}]},
        ]}]))
    assert ok2, errors2


def test_check4_flow_rows_auto_legend_exempt():
    """flow_rows roles>2 走自动 legend（§8.1），不报图例完备。"""
    _, errors, _ = verify_spec_layout_data(_spec(
        pages=[{"elements": [
            {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
             "title": "x",
             "roles": {"biz": {"label": "业务"}, "legal": {"label": "法务"},
                       "fin": {"label": "财务"}},
             "rows": [{"cards": [{"label": "a", "role": "biz"}]}]},
        ]}]))
    assert not any("图例完备" in e for e in errors)


def test_check5_check6_warnings():
    _, _, warnings = verify_spec_layout_data(_spec(
        pages=[{"elements": [
            {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
             "title": "x",
             "rows": [{"style": "dashed_opt",
                       "cards": [{"label": "a", "badge": "1"}]}]},
        ]}]))
    assert any("badge" in w for w in warnings)  # 虚线纪律
    _, _, warnings = verify_spec_layout_data(_spec(
        pages=[{"layout": "P07", "elements": [
            {"type": "section_tag", "label": "对比"},
            {"type": "action_title", "segments": [{"t": "三通道对比 12 项"}]},
            {"type": "table", "headers": ["a"], "rows": [["x"]] * 13},
        ]}]))
    assert any("12" in w for w in warnings)  # 容量阈值


def test_auto_verify_yaml_integration(tmp_path):
    """auto_verify 挂接：spec.yml 版式 error → verify FAIL。"""
    good = tmp_path / "good_spec.yml"
    good.write_text(yaml.safe_dump(_spec(
        theme="consulting_kpmg",
        pages=[{"layout": "P01", "elements": [{"type": "hero",
                                               "title": "大标题"}]}]),
        allow_unicode=True) + " " * 60, encoding="utf-8")
    ok, msg = auto_verify(str(good))
    assert ok, msg
    bad = tmp_path / "bad_spec.yml"
    bad.write_text(yaml.safe_dump(_spec(
        pages=[{"layout": "P05", "elements": [
            {"type": "section_tag", "label": "x"},
            {"type": "action_title", "segments": [{"t": "合同闭环 8 步"}]},
            {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
             "title": "x", "rows": [{"cards": [{"label": "a"}]}]},
        ]}]), allow_unicode=True) + " " * 60, encoding="utf-8")
    ok, msg = auto_verify(str(bad))
    assert not ok and "legend_bar" in msg
    # 非 spec 的 yml（无 pages）不受影响
    plain = tmp_path / "plain.yml"
    plain.write_text("key: value\n" + " " * 60, encoding="utf-8")
    ok, _ = auto_verify(str(plain))
    assert ok


# ============================================================
# v2 修订新增：检查 7（checker 复检）/ 8（穿字）/ 9（AI 配色+嵌套）
# ============================================================

import json

from _verify import verify_pptd_deck


def _write_deck(tmp_path, pages=None, check_report=None):
    deck = tmp_path / "deck"
    (deck / "pages").mkdir(parents=True)
    if check_report is not None:
        (deck / "check_report.json").write_text(
            json.dumps(check_report, ensure_ascii=False), encoding="utf-8")
    for name, elements in (pages or {}).items():
        (deck / "pages" / name).write_text(
            yaml.safe_dump({"elements": elements}, allow_unicode=True),
            encoding="utf-8")
    return str(deck)


def _conn(eid, bounds):
    return {"elementId": eid, "elementType": "shape",
            "shapeName": "straightConnector1", "bounds": bounds}


def _text(eid, bounds):
    return {"elementId": eid, "elementType": "text", "bounds": bounds,
            "content": {"text": "x"}}


def _card(eid, bounds):
    return {"elementId": eid, "elementType": "shape",
            "shapeName": "roundRect", "bounds": bounds}


def test_check7_five_warnings_error(tmp_path):
    deck = _write_deck(tmp_path, check_report={
        "pptd": "deck.pptd", "warnings": {"TextOverflow": 2, "BoundsOutside": 1}})
    ok, errors, _ = verify_pptd_deck(deck)
    assert not ok
    assert any("TextOverflow" in e and "BoundsOutside" in e for e in errors)
    # 无五类 warning → pass；无报告文件（老工程）→ 跳过不报错
    deck2 = _write_deck(tmp_path / "d2", check_report={"warnings": {}})
    assert verify_pptd_deck(deck2)[0]
    deck3 = _write_deck(tmp_path / "d3")
    assert verify_pptd_deck(deck3)[0]


def test_check8_connector_through_text(tmp_path):
    pages = {"02_p.page": [
        _conn("dg-ar", [100, 100, 200, 4]),      # 与文本框相交
        _text("dg-t1", [150, 96, 100, 20]),
        _conn("dg-ar2", [600, 100, 200, 4]),     # 远离，不报
    ]}
    _, _, warnings = verify_pptd_deck(_write_deck(tmp_path, pages))
    assert any("dg-ar" in w and "dg-t1" in w and "穿" in w for w in warnings)
    assert not any("dg-ar2" in w for w in warnings)


def test_check9b_card_nesting(tmp_path):
    pages = {"02_p.page": [
        _card("v2130-stc-0", [80, 130, 200, 64]),
        _card("v2130-stc-1", [90, 140, 100, 40]),   # 被 stc-0 完全包含 → 嵌套
        _card("v2130-stc-bar0", [80, 130, 4, 64]),  # 装饰件（非卡类）不报
        _card("v2130-kpi-0", [600, 130, 200, 76]),  # 独立卡不报
    ]}
    _, _, warnings = verify_pptd_deck(_write_deck(tmp_path, pages))
    assert any("嵌套" in w and "stc-0" in w and "stc-1" in w for w in warnings)
    assert not any("kpi-0" in w for w in warnings)


def test_check9a_ai_colors(tmp_path=None):
    # 语义色 >4 → warning
    _, _, warnings = verify_spec_layout_data(_spec(pages=[{"elements": [
        {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
         "title": "x",
         "roles": {"biz": {"label": "a"}, "legal": {"label": "b"},
                   "fin": {"label": "c"}, "sys": {"label": "d"},
                   "ext": {"label": "e"}},
         "rows": [{"cards": [{"label": "a", "role": "biz"}]}]},
    ]}]))
    assert any("语义色" in w and ">4" in w for w in warnings)
    # 红紫黄绿四色同页 → warning
    _, _, warnings = verify_spec_layout_data(_spec(pages=[{"elements": [
        {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
         "title": "x",
         "roles": {"legal": {"label": "红"}, "sys": {"label": "紫"},
                   "fin": {"label": "绿"}},
         "rows": [{"cards": [{"label": "a", "role": "legal"}]}]},
        {"type": "action_title", "segments": [{"t": "强调 5 处", "hl": "yellow"}]},
    ]}]))
    assert any("四色同页" in w for w in warnings)
    # 三色不齐全不报
    _, _, warnings = verify_spec_layout_data(_spec(pages=[{"elements": [
        {"type": "action_title", "segments": [{"t": "点亮 74%", "hl": "green"}]},
        {"type": "stat_cards", "cards": [{"value": "1", "tone": "lit"}]},
    ]}]))
    assert not any("四色同页" in w or "语义色" in w for w in warnings)


def test_auto_verify_pptd_integration(tmp_path):
    """verify xxx.pptd：格式 + 检查 7 error → FAIL。"""
    deck = _write_deck(tmp_path, pages={"02_p.page": [_text("t", [80, 130, 100, 20])]},
                       check_report={"warnings": {"TextDrift": 3}})
    import os
    pptd_path = os.path.join(deck, "deck.pptd")
    with open(pptd_path, "w", encoding="utf-8") as f:
        f.write(yaml.safe_dump({"title": "t", "size": [1280, 720],
                                "pages": ["pages/02_p.page"]},
                               allow_unicode=True))
    ok, msg = auto_verify(pptd_path)
    assert not ok and "TextDrift" in msg
