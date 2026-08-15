# -*- coding: utf-8 -*-
"""视觉规范 v2.0 schema/elements 扩展测试（dev_plan_visual_v2_2026-07-25 §5/§6，T2）。

覆盖：10 种 v2 页面构件校验与 normalize、flow_rows 第 28 种子类型、
theme 双形态（str 主题名 / dict colors 覆盖）、hex 防线（仅 v2 spec）、
P01-P11 版式目录必需构件/顺序/容量。
"""
from _renderer import elements as proto
from _renderer.schema import (
    PAGE_LAYOUTS, validate_element, validate_element_warnings,
    validate_layout_errors, validate_layout_warnings, validate_spec,
)


def _ok(elem):
    assert validate_element(elem) == []


# ---- v2 元素：合法样例零错误 ----

def test_v2_elements_valid():
    _ok({"type": "hero", "title": "大标题", "eyebrow": "SECTION 0",
         "subtitle": "副标题", "meta": ["v3", "2026-07-25"],
         "stats": [{"value": "202", "unit": "功能点", "label": "全量替换"}]})
    _ok({"type": "section_tag", "index": "SECTION 1", "label": "业务背景"})
    _ok({"type": "action_title",
         "segments": [{"t": "点亮 "}, {"t": "74%", "hl": "yellow"}, {"t": "。"}],
         "sub": "口径说明"})
    _ok({"type": "stat_cards",
         "cards": [{"value": "149", "unit": "74%", "label": "已点亮", "tone": "lit"}]})
    _ok({"type": "kpi_cards",
         "cards": [{"label": "预算拦截率", "from": "0%", "to": "100%"}]})
    _ok({"type": "pain_cards",
         "cards": [{"title": "印章/电子签", "level": "P1", "impact": "4 部门",
                    "body": "..."}]})
    _ok({"type": "info_cards",
         "cards": [{"title": "缺口 15 项", "items": ["a", "b"]}]})
    _ok({"type": "legend_bar",
         "items": [{"swatch": "lit", "label": "已点亮"},
                   {"swatch": "role_biz", "label": "业务"}]})
    _ok({"type": "qa_block", "items": [{"q": "为什么", "a": "因为"}]})
    _ok({"type": "topnav", "brand": "瓴寓国际", "brand_sub": "私有化 OA 平台"})


# ---- v2 元素：必填与枚举 ----

def test_v2_elements_required():
    assert validate_element({"type": "hero"})
    assert validate_element({"type": "section_tag", "index": "S1"})
    assert validate_element({"type": "action_title"})
    assert validate_element({"type": "stat_cards"})
    assert validate_element({"type": "kpi_cards"})
    assert validate_element({"type": "pain_cards"})
    assert validate_element({"type": "info_cards"})
    assert validate_element({"type": "legend_bar"})
    assert validate_element({"type": "qa_block"})
    assert validate_element({"type": "topnav"})


def test_v2_elements_enum_errors():
    errs = validate_element({"type": "action_title",
                             "segments": [{"t": "x", "hl": "blue"}]})
    assert any("hl" in e for e in errs)
    errs = validate_element({"type": "stat_cards",
                             "cards": [{"value": "1", "tone": "red"}]})
    assert any("tone" in e for e in errs)
    errs = validate_element({"type": "pain_cards",
                             "cards": [{"title": "x", "level": "P9"}]})
    assert any("level" in e for e in errs)
    errs = validate_element({"type": "legend_bar",
                             "items": [{"swatch": "pink", "label": "x"}]})
    assert any("swatch" in e for e in errs)
    # 合法枚举值不误报
    _ok({"type": "action_title", "segments": [{"t": "x", "hl": "green"}]})


# ---- flow_rows ----

def _flow_rows(**kw):
    elem = {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
            "title": "合同管理 TO-BE 主流程",
            "roles": {"biz": {"label": "业务"}, "legal": {"label": "法务"}},
            "rows": [
                {"label": "相对方", "group": "blue",
                 "cards": [{"badge": "1", "label": "准入申请", "role": "biz"},
                           {"badge": "2", "label": "资格审核", "role": "legal"}]},
                {"arrow": "down"},
                {"label": "用印", "style": "dashed_opt",
                 "cards": [{"label": "纸质用印", "role": "biz", "dim": True}]},
            ]}
    elem.update(kw)
    return elem


def test_flow_rows_valid():
    _ok(_flow_rows())


def test_flow_rows_errors():
    # rows 必填
    assert validate_element({"type": "diagram", "diagram_type": "flow",
                             "subtype": "flow_rows", "title": "x"})
    # card.role 不在 roles 声明内
    errs = validate_element(_flow_rows(
        rows=[{"cards": [{"label": "x", "role": "ext"}]}]))
    assert any("role" in e and "声明" in e for e in errs)
    # group / style / arrow 非法值
    assert any("group" in e for e in validate_element(
        _flow_rows(rows=[{"group": "red", "cards": [{"label": "x"}]}])))
    assert any("style" in e for e in validate_element(
        _flow_rows(rows=[{"style": "dashed", "cards": [{"label": "x"}]}])))
    assert any("arrow" in e for e in validate_element(
        _flow_rows(rows=[{"arrow": "left"}])))
    # 空行 / arrow 行带 cards / roles 未知键 / card 缺 label
    assert any("空行" in e for e in validate_element(_flow_rows(rows=[{}])))
    assert validate_element(_flow_rows(
        rows=[{"arrow": "down", "cards": [{"label": "x"}]}]))
    assert any("roles" in e for e in validate_element(
        _flow_rows(roles={"boss": {"label": "老板"}},
                   rows=[{"cards": [{"label": "x"}]}])))
    assert validate_element(_flow_rows(rows=[{"cards": [{"badge": "1"}]}]))


def test_flow_rows_warnings():
    # 行数 >8 / 行卡 >6 / dashed_opt 行内 badge
    w = validate_element_warnings(_flow_rows(
        rows=[{"cards": [{"label": str(i)}]} for i in range(9)]))
    assert any("行数" in x for x in w)
    w = validate_element_warnings(_flow_rows(
        rows=[{"cards": [{"label": str(i)} for i in range(7)]}]))
    assert any("卡数" in x for x in w)
    w = validate_element_warnings(_flow_rows(
        rows=[{"style": "dashed_opt",
               "cards": [{"label": "x", "badge": "1"}]}]))
    assert any("badge" in x for x in w)
    # 合法样例无 warning
    assert validate_element_warnings(_flow_rows()) == []


# ---- theme 双形态 + hex 防线 ----

def test_theme_field_dual_form():
    assert validate_spec({"pages": [], "theme": "consulting_kpmg"}) == []
    assert validate_spec({"pages": [], "theme": "legacy_bluegreen"}) == []
    errs = validate_spec({"pages": [], "theme": "swiss_ikb"})
    assert any("theme" in e and "合法值" in e for e in errs)
    errs = validate_spec({"pages": [], "theme": 123})
    assert any("类型非法" in e for e in errs)
    # 旧 dict 形态（colors 覆盖）不校验、不报错
    assert validate_spec({"pages": [],
                          "theme": {"colors": {"heading": "#1A1A1A"}}}) == []


def test_hex_guard_only_for_v2_spec():
    # v2 spec（theme str）含 hex → error
    errs = validate_spec({"theme": "consulting_kpmg", "pages": [
        {"id": "p1", "elements": [
            {"type": "stat_cards", "cards": [{"value": "#00338D"}]}]}]})
    assert any("hex" in e for e in errs)
    # v2 spec（P 系 layout）正文提及 hex → error
    errs = validate_spec({"pages": [
        {"layout": "P01",
         "elements": [{"type": "hero", "title": "主色 #00338D 很好看"}]}]})
    assert any("hex" in e for e in errs)
    # 老 spec（无 v2 声明）：theme.colors hex 与正文 hex 均不报
    assert validate_spec({"pages": [
        {"elements": [{"type": "text", "content": "主色 #2b1810 强调"}]}],
        "theme": {"colors": {"heading": "#1A1A1A"}}}) == []
    # 老 spec 元素内 color 字段 hex（存量 main_visual 形态）不报
    assert validate_spec({"pages": [{"elements": [
        {"type": "text", "content": "x", "color": "#1f6feb"}]}]}) == []


# ---- P01-P11 版式目录 ----

def test_layout_unknown():
    errs = validate_layout_errors({"layout": "P99", "elements": []})
    assert any("未知版式" in e for e in errs)
    # 无 layout → 自由流不校验
    assert validate_layout_errors({"elements": []}) == []


def test_layout_required_components():
    # P05 缺 legend_bar → error（§13.1-4 验收场景）
    page = {"layout": "P05", "elements": [
        {"type": "section_tag", "label": "流程"},
        {"type": "action_title", "segments": [{"t": "合同流程 8 步"}]},
        {"type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
         "title": "x", "rows": [{"cards": [{"label": "a"}]}]},
    ]}
    errs = validate_layout_errors(page)
    assert any("legend_bar" in e for e in errs)
    # 补齐后零错误
    page["elements"].append({"type": "legend_bar",
                             "items": [{"swatch": "lit", "label": "已点亮"}]})
    assert validate_layout_errors(page) == []
    # P10 二选一：table 或 info_cards 任一满足
    assert validate_layout_errors({"layout": "P10", "elements": [
        {"type": "section_tag", "label": "x"},
        {"type": "action_title", "segments": [{"t": "风险 3 项"}]},
        {"type": "info_cards", "cards": [{"title": "a", "items": ["i"]}]},
    ]}) == []


def test_layout_order_and_capacity_warnings():
    # 乱序 → warning
    page = {"layout": "P02", "elements": [
        {"type": "action_title", "segments": [{"t": "x"}]},
        {"type": "section_tag", "label": "y"},
    ]}
    assert any("顺序" in w for w in validate_layout_warnings(page))
    # P05 双图 → warning
    page = {"layout": "P05", "elements": [
        {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
         "title": "a", "steps": [{"label": "1"}]},
        {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
         "title": "b", "steps": [{"label": "1"}]},
    ]}
    assert any("单图" in w for w in validate_layout_warnings(page))
    # P07 table >12 行 → warning
    page = {"layout": "P07", "elements": [
        {"type": "table", "headers": ["a"], "rows": [["x"]] * 13}]}
    assert any("12" in w for w in validate_layout_warnings(page))
    # P02 双 info_cards → warning
    page = {"layout": "P02", "elements": [
        {"type": "info_cards", "cards": [{"title": "a", "items": []}]},
        {"type": "info_cards", "cards": [{"title": "b", "items": []}]},
    ]}
    assert any("info_cards" in w for w in validate_layout_warnings(page))


def test_v2_element_capacity_warnings():
    assert validate_element_warnings(
        {"type": "hero", "title": "x",
         "stats": [{"value": str(i)} for i in range(5)]})
    assert validate_element_warnings(
        {"type": "kpi_cards", "cards": [{"label": str(i)} for i in range(5)]})
    assert validate_element_warnings(
        {"type": "pain_cards", "cards": [{"title": str(i)} for i in range(10)]})
    assert validate_element_warnings(
        {"type": "info_cards", "cards": [{"title": "only"}]})  # <2 联
    assert validate_element_warnings(
        {"type": "info_cards", "cards": [{"title": str(i)} for i in range(5)]})


# ---- normalize / 空载荷 / 能力矩阵 ----

def test_normalize_v2():
    _, n = proto.normalize_element({"type": "hero", "title": "T",
                                    "meta": "not-a-list", "stats": [{"value": 1}]})
    assert n["meta"] == [] and n["stats"][0]["value"] == "1"
    _, n = proto.normalize_element({"type": "action_title",
                                    "segments": [{"t": "a"}, "bare"]})
    assert n["segments"][0]["hl"] == ""
    assert n["segments"][1]["t"] == "bare"  # 裸字符串段归一为 {t: 原文}
    _, n = proto.normalize_element({"type": "topnav"})
    assert n == {"brand": "", "brand_sub": "",
                 "logo": "", "logo_position": ""}


def test_empty_payload_v2():
    assert proto.is_empty_payload("hero", proto.normalize_hero({}))
    assert not proto.is_empty_payload(
        "hero", proto.normalize_hero({"title": "x"}))
    assert proto.is_empty_payload(
        "action_title", proto.normalize_action_title({"segments": []}))
    assert proto.is_empty_payload("topnav", proto.normalize_topnav({}))
    assert proto.is_empty_payload("qa_block", proto.normalize_qa_block({}))


def test_capabilities_v2():
    cap = proto.CAPABILITIES
    assert cap["hero"] == {"html": "render", "docx": "degrade", "pptd": "render"}
    assert cap["topnav"] == {"html": "render", "docx": "degrade", "pptd": "degrade"}
    assert cap["qa_block"]["docx"] == "render"
    assert cap["info_cards"]["docx"] == "render"
    # 三端键齐全
    for t in ("hero", "section_tag", "action_title", "stat_cards", "kpi_cards",
              "pain_cards", "info_cards", "legend_bar", "qa_block", "topnav"):
        assert set(cap[t]) == {"html", "docx", "pptd"}


def test_degrade_text_v2():
    assert "封面横幅" in proto.degrade_text("hero", {"title": "总览"}, "docx")
    assert "页首导航" in proto.degrade_text("topnav", {"brand": "瓴寓"}, "pptd")
    assert "图例条" in proto.degrade_text("legend_bar", {}, "pptd")


def test_page_layouts_frozen_names():
    """P01-P16 命名冻结（F10 + v3.0 T5 扩展，无 P13：与 P02 章节页重叠）。"""
    assert sorted(PAGE_LAYOUTS) == [f"P{i:02d}" for i in range(1, 17)
                                    if i != 13]
    names = [PAGE_LAYOUTS[p]["name"] for p in sorted(PAGE_LAYOUTS)]
    assert names == ["封面", "章节页", "结论摘要", "痛点矩阵", "流程图页",
                     "架构图页", "对比表页", "能力地图页", "路线图页",
                     "风险与待确认页", "收尾页", "目录页", "双栏对比页",
                     "优缺点清单页", "CTA 收尾页"]


# ---- v3.0 scenario 场景字段（dev_plan_visual_v3_2026-08-11，T3）----

def test_scenario_valid():
    assert validate_spec({"pages": [], "scenario": "report"}) == []
    assert validate_spec({"pages": [], "scenario": "product_intro"}) == []


def test_scenario_invalid():
    errs = validate_spec({"pages": [], "scenario": "pitch"})
    assert any("scenario" in e for e in errs)


def test_scenario_default_is_report():
    """缺省 scenario=report（汇报为主场景）。"""
    errs = validate_spec({"pages": []})
    assert errs == []


# ---- v3.0 P12/P14/P15/P16 版式（dev_plan_visual_v3_2026-08-11，T5）----

def test_layout_p12_toc_requires_heading():
    page = {"layout": "P12", "elements": [
        {"type": "section_tag", "label": "目录"},
        {"type": "action_title", "segments": [{"t": "本方案章节"}]},
        {"type": "toc_cards",
         "cards": [{"num": "01", "title": "背景", "desc": "现状"}]}]}
    assert validate_layout_errors(page) == []


def test_layout_p12_missing_required():
    page = {"layout": "P12",
            "elements": [{"type": "section_tag", "label": "目录"}]}
    errs = validate_layout_errors(page)
    assert any("toc_cards" in e for e in errs)


def test_layout_p14_duo_compare_requires_two():
    page = {"layout": "P14",
            "elements": [{"type": "section_tag", "label": "对比"},
                         {"type": "action_title", "segments": [{"t": "方案对比"}]},
                         {"type": "duo_compare",
                          "left": {"title": "方案A", "points": ["a"]},
                          "right": {"title": "方案B", "points": ["b"]}}]}
    assert validate_layout_errors(page) == []


def test_layout_p15_p16_required():
    page = {"layout": "P15",
            "elements": [{"type": "section_tag", "label": "评估"},
                         {"type": "action_title", "segments": [{"t": "方案取舍"}]},
                         {"type": "pros_cons", "pros": ["a"], "cons": ["b"]}]}
    assert validate_layout_errors(page) == []
    page = {"layout": "P16",
            "elements": [{"type": "action_title", "segments": [{"t": "下一步"}]},
                         {"type": "cta_block", "title": "联系我们", "button": "预约演示"}]}
    assert validate_layout_errors(page) == []
