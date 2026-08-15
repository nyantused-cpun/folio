# -*- coding: utf-8 -*-
"""视觉规范 v2.0 pptd 映射测试（dev_plan_visual_v2 §7/§8.5，T5）。

覆盖：9 构件 pptd 原生形状映射、flow_rows pptd（卡/箭头/可选项/legend）、
build_deck 端到端（v2 主题取色 + elementId 唯一化 + topnav 降级）。
"""
import yaml

from _renderer.diagram import pptd_emit as pe
from _renderer.elements import normalize_element


def _norm(elem):
    return normalize_element(elem)[1]


def _ids(elems):
    return [e["elementId"] for e in elems]


def _types(elems):
    return [e["elementType"] for e in elems]


def _fills(elems):
    return [e.get("fill", {}).get("color") for e in elems if "fill" in e]


# ---- 构件 pptd 映射 ----

def test_hero_pptd():
    elems, h = pe.emit_chrome_pptd("hero", _norm({
        "type": "hero", "eyebrow": "S0", "title": "大标题", "subtitle": "副",
        "meta": ["v3", "2026-07-25"],
        "stats": [{"value": "202", "unit": "功能点", "label": "全量替换"}]}),
        80, 130, 1120, theme_name="consulting_kpmg")
    assert h > 100
    bg = [e for e in elems if e["elementId"] == "hero-bg"][0]
    assert bg["elementType"] == "shape"
    assert bg["fill"]["color"] == "#00338D"  # hero_to（kpmg）
    eb = [e for e in elems if e["elementId"] == "hero-eb"][0]
    assert eb["fill"]["color"] == "#FFE600"  # accent
    assert len(_ids(elems)) == len(set(_ids(elems)))


def test_section_tag_pptd():
    elems, h = pe.emit_chrome_pptd("section_tag", _norm(
        {"type": "section_tag", "index": "SECTION 1", "label": "业务背景"}),
        80, 130, 1120)
    assert h == 22
    texts = [e for e in elems if e["elementType"] == "text"]
    assert "SECTION 1 · 业务背景" in texts[0]["content"]["text"]


def test_action_title_pptd_hl_degrades_to_bold():
    """PPT 侧 hl 降格整段加粗（荧光笔无原生对应）。"""
    elems, h = pe.emit_chrome_pptd("action_title", _norm({
        "type": "action_title",
        "segments": [{"t": "点亮 "}, {"t": "74%", "hl": "yellow"}],
        "sub": "口径"}), 80, 130, 1120, theme_name="consulting_kpmg")
    t = [e for e in elems if e["elementId"] == "at-t"][0]
    assert "<strong>" in t["content"]["text"]
    assert "点亮 74%" in t["content"]["text"]
    assert t["content"]["color"] == "#0F172A"


def test_stat_cards_pptd_tone():
    elems, h = pe.emit_chrome_pptd("stat_cards", _norm({
        "type": "stat_cards", "cards": [
            {"value": "149", "unit": "74%", "label": "已点亮", "tone": "lit"},
            {"value": "15", "label": "缺口", "tone": "gap"}]}),
        80, 130, 1120, theme_name="consulting_kpmg")
    bars = [e for e in elems if e["elementId"].startswith("stc-bar")]
    assert bars[0]["fill"]["color"] == "#059669"  # lit
    assert bars[1]["fill"]["color"] == "#DC2626"  # gap
    assert h == 64.0


def test_kpi_pain_info_legend_qa_pptd():
    cases = [
        ("kpi_cards", {"type": "kpi_cards", "cards": [
            {"label": "预算拦截率", "from": "0%", "to": "100%", "note": "强控"}]}),
        ("pain_cards", {"type": "pain_cards", "cards": [
            {"title": "印章", "level": "P1", "impact": "4 部门", "body": "正文"},
            {"title": "无徽章"}]}),
        ("info_cards", {"type": "info_cards", "cards": [
            {"title": "缺口 15 项", "items": ["a", "b"]}]}),
        ("legend_bar", {"type": "legend_bar", "items": [
            {"swatch": "lit", "label": "已点亮"},
            {"swatch": "role_biz", "label": "业务"},
            {"swatch": "gap", "label": "缺口"}]}),
        ("qa_block", {"type": "qa_block", "items": [{"q": "为何", "a": "因为"}]}),
    ]
    for etype, elem in cases:
        elems, h = pe.emit_chrome_pptd(etype, _norm(elem), 80, 130, 1120,
                                       theme_name="consulting_kpmg")
        assert elems and h > 0, etype
        assert len(_ids(elems)) == len(set(_ids(elems))), etype
        assert all(e["elementType"] in ("shape", "text") for e in elems), etype
    # pain 徽章：P1 朱橙；缺 level 不出徽章
    elems, _ = pe.emit_chrome_pptd("pain_cards", _norm(cases[1][1]),
                                   80, 130, 1120, theme_name="consulting_kpmg")
    badges = [e for e in elems if e["elementId"].startswith("pain-b")
              and e["elementId"].endswith("t")]
    assert len(badges) == 1
    fill = [e for e in elems if e["elementId"] == "pain-b0"][0]["fill"]["color"]
    assert fill == "#EA580C"
    # legend swatch：角色实底 / 三态浅底深边 / gap 虚线边
    elems, _ = pe.emit_chrome_pptd("legend_bar", _norm(cases[3][1]),
                                   80, 130, 1120, theme_name="consulting_kpmg")
    sw = {e["elementId"]: e for e in elems if e["elementId"].startswith("lgb-sw")}
    assert sw["lgb-sw0"]["fill"]["color"] == "#ECFDF5"
    assert sw["lgb-sw1"]["fill"]["color"] == "#00338D"
    assert sw["lgb-sw2"]["border"]["style"] == "dash"


def test_emit_chrome_pptd_unknown():
    assert pe.emit_chrome_pptd("topnav", {}, 80, 130, 1120) == ([], 0)
    assert pe.emit_chrome_pptd("foo", {}, 80, 130, 1120) == ([], 0)


# ---- flow_rows pptd ----

def _fr_elem():
    return {
        "type": "diagram", "diagram_type": "flow", "subtype": "flow_rows",
        "title": "合同管理 TO-BE 主流程",
        "roles": {"biz": {"label": "业务"}, "legal": {"label": "法务"},
                  "sys": {"label": "平台"}},
        "rows": [
            {"label": "相对方", "label_sub": "准入即风控", "group": "blue",
             "cards": [{"badge": "1", "label": "准入申请", "role": "biz",
                        "desc": "信息录入"},
                       {"badge": "2", "label": "资格审核", "role": "legal"}]},
            {"arrow": "down"},
            {"style": "dashed_opt",
             "cards": [{"label": "纸质用印", "dim": True, "badge": "3"}]},
        ],
    }


def test_flow_rows_pptd_native_shapes():
    elems, h = pe.render_flow_rows_pptd(_fr_elem(), 80, 130, 1120,
                                        theme_name="consulting_kpmg")
    assert h > 0
    names = [e.get("shapeName") for e in elems if e["elementType"] == "shape"]
    # 卡 roundRect + 顶条 rect + badge ellipse + 底色 rect/roundRect
    assert "roundRect" in names and "rect" in names and "ellipse" in names
    # 箭头全为原生连接符 straightConnector1（零图像化）
    connectors = [e for e in elems if e.get("shapeName") == "straightConnector1"]
    assert len(connectors) >= 2  # 行内 → + 行间 ↓
    assert all("arrow" in e for e in connectors)
    # dashed_opt 行：dash 边框 + part 浅底
    opt = [e for e in elems if e["elementId"] == "fr-optbg2"][0]
    assert opt["border"]["style"] == "dash"
    assert opt["border"]["color"] == "#EA580C"
    assert opt["fill"]["color"] == "#FFF7ED"
    # 可选项不编号（badge 抑制）
    assert not any(e["elementId"].startswith("fr-c2-0-num") for e in elems)
    # 主行 badge 保留
    assert any(e["elementId"].startswith("fr-c0-0-num") for e in elems)
    # 行级底色垫底（先 emit）
    grp_idx = next(i for i, e in enumerate(elems) if e["elementId"] == "fr-bg0")
    card_idx = next(i for i, e in enumerate(elems) if e["elementId"] == "fr-c0-0")
    assert grp_idx < card_idx
    # roles>2 自动 legend
    assert any(e["elementId"] == "lgb-bg" for e in elems)
    # ID 唯一
    assert len(_ids(elems)) == len(set(_ids(elems)))


def test_flow_rows_pptd_legacy_theme():
    """legacy 主题取 v1.2 蓝绿（F9）。"""
    elems, _ = pe.render_flow_rows_pptd(_fr_elem(), 80, 130, 1120)
    bar = [e for e in elems if e["elementId"] == "fr-c0-0-top"][0]
    assert bar["fill"]["color"] == "#1B5E8A"  # legacy role_biz = BLUE


def test_flow_rows_pptd_row_alignment_no_var_shadowing():
    """回归（label_w 遮蔽 bug）：带行标签的后续行，卡 x 起点与首行一致
    （行标签宽 86 不被卡内 label 文本框宽污染）；行底矩形包含全部卡。"""
    elems, _ = pe.render_flow_rows_pptd(_fr_elem(), 80, 130, 1120,
                                        theme_name="consulting_kpmg")
    by_id = {e["elementId"]: e for e in elems}
    # _fr_elem：行 0（3 卡 label=相对方）+ arrow + 行 2（dashed_opt）
    # 行 0 卡 0 x = 80+86=166（snap 后 164-168）
    assert 160 <= by_id["fr-c0-0"]["bounds"][0] <= 172
    # 再补一行带 label 的 4 卡行，验证污染后 x 仍正确
    elem = _fr_elem()
    elem["rows"].append({"label": "履约", "cards": [
        {"badge": "4", "label": "执行台账", "role": "biz"},
        {"badge": "5", "label": "付款强关联", "role": "biz"},
        {"badge": "6", "label": "发票触发", "role": "biz"},
        {"badge": "7", "label": "变更终止", "role": "biz"}]})
    elems, _ = pe.render_flow_rows_pptd(elem, 80, 130, 1120,
                                        theme_name="consulting_kpmg")
    by_id = {e["elementId"]: e for e in elems}
    # 行 3（4 卡）：cx 起点必须 = 80+86=166（遮蔽 bug 时变成 583）
    assert 160 <= by_id["fr-c3-0"]["bounds"][0] <= 172
    # 4 卡等宽且不超行底右缘（80+1120=1200）
    last = by_id["fr-c3-3"]["bounds"]
    assert last[0] + last[2] <= 1200
    widths = {round(by_id[f"fr-c3-{i}"]["bounds"][2]) for i in range(4)}
    assert len(widths) <= 2  # snap 取整至多 1 格偏差


# ---- build_deck 端到端 ----

def _build(tmp_path, spec):
    import _pptd_gen
    from _renderer import _resolve_style
    spec.setdefault("confirmed", True)
    spec.setdefault("document", {"title": "t"})
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True),
                         encoding="utf-8")
    spec_dict = _pptd_gen.load_spec(str(spec_path))
    style = _resolve_style(spec_dict.get("style", "enterprise"))
    files, _ = _pptd_gen.build_deck(spec_dict, str(spec_path), style, "deck",
                                    str(tmp_path / "out"))
    return files


def test_build_deck_v2_end_to_end(tmp_path):
    spec = {
        "theme": "consulting_kpmg",
        "pages": [
            {"id": "p1", "title": "封面", "layout": "P01", "elements": [
                {"type": "hero", "title": "大标题", "eyebrow": "S0"},
                {"type": "stat_cards", "cards": [
                    {"value": "149", "label": "已点亮", "tone": "lit"}]},
                {"type": "stat_cards", "cards": [  # 同页第二组（ID 唯一化）
                    {"value": "15", "label": "缺口", "tone": "gap"}]},
            ]},
            {"id": "p2", "title": "流程", "layout": "P05", "elements": [
                {"type": "section_tag", "label": "流程"},
                {"type": "action_title", "segments": [{"t": "合同闭环 8 步"}]},
                _fr_elem(),
                {"type": "legend_bar", "items": [{"swatch": "lit",
                                                  "label": "已点亮"}]},
            ]},
            {"id": "p3", "title": "导航页", "elements": [
                {"type": "topnav", "brand": "瓴寓国际"},
            ]},
        ],
    }
    files = _build(tmp_path, spec)
    p1 = yaml.safe_load(files["pages/01_p1.page"])
    ids = [e["elementId"] for e in p1["elements"]]
    assert len(ids) == len(set(ids))  # 同页两组 stat_cards 不撞 ID
    hero_bg = [e for e in p1["elements"] if "hero-bg" in e["elementId"]][0]
    assert hero_bg["fill"]["color"] == "#00338D"  # v2 主题透传
    p2 = yaml.safe_load(files["pages/02_p2.page"])
    fr_cards = [e for e in p2["elements"] if "fr-c0-0" in e["elementId"]]
    assert fr_cards and fr_cards[0]["elementType"] == "shape"
    p3 = yaml.safe_load(files["pages/03_p3.page"])
    texts = " ".join(e.get("content", {}).get("text", "")
                     for e in p3["elements"] if e["elementType"] == "text")
    assert "页首导航" in texts  # topnav 降级页眉文本


# ---- v3.0 版式构件 pptd 映射（P12/P14/P15/P16） ----

def test_toc_cards_pptd():
    elems, h = pe.emit_chrome_pptd(
        "toc_cards", _norm({"type": "toc_cards", "cards": [
            {"num": "01", "title": "背景", "desc": "现状"},
            {"num": "02", "title": "方案", "desc": ""}]}),
        80, 130, 1120, theme_name="corporate_navy")
    assert elems and h > 0
    assert any("toc-0" in i for i in _ids(elems))
    assert any("toc-n0" in i for i in _ids(elems))


def test_duo_compare_pptd():
    elems, h = pe.emit_chrome_pptd(
        "duo_compare", _norm({"type": "duo_compare",
                              "left": {"title": "A", "points": ["a1"]},
                              "right": {"title": "B", "points": ["b1"]}}),
        80, 130, 1120, theme_name="corporate_navy")
    assert elems and h > 0
    assert "duo-vr" in _ids(elems)  # 中隔线


def test_pros_cons_pptd():
    elems, h = pe.emit_chrome_pptd(
        "pros_cons", _norm({"type": "pros_cons",
                            "pros": ["省时"], "cons": ["成本"]}),
        80, 130, 1120, theme_name="corporate_navy")
    assert elems and h > 0
    assert any("pc-bg0" in i for i in _ids(elems))


def test_cta_block_pptd():
    elems, h = pe.emit_chrome_pptd(
        "cta_block", _norm({"type": "cta_block", "title": "联系我们",
                            "button": "预约演示", "contact": "400"}),
        80, 130, 1120, theme_name="product_charcoal")
    assert elems and h > 0
    assert "cta-btn" in _ids(elems)
    bg = [e for e in elems if e["elementId"] == "cta-bg"][0]
    assert bg["fill"]["color"] == "#1C2644"  # product_charcoal hero_to


# ---- v3.0 版式构件边界测试 ----

def test_toc_cards_empty():
    """空 cards 列表应返回空元素 + 零高度。"""
    elems, h = pe.emit_chrome_pptd(
        "toc_cards", _norm({"type": "toc_cards", "cards": []}),
        80, 130, 1120)
    assert elems == [] and h == 0


def test_toc_cards_single():
    """单卡应占满宽度（cw = w = 1120）。"""
    elems, h = pe.emit_chrome_pptd(
        "toc_cards", _norm({"type": "toc_cards", "cards": [
            {"num": "01", "title": "唯一"}]}),
        80, 130, 1120)
    assert elems and h > 0
    card = [e for e in elems if e["elementId"] == "toc-0"][0]
    assert abs(card["bounds"][2] - 1120) < 2  # 宽度≈1120


def test_toc_cards_three():
    """3 卡应换行（第 3 卡在新行，cur_y 递增）。"""
    elems, h = pe.emit_chrome_pptd(
        "toc_cards", _norm({"type": "toc_cards", "cards": [
            {"num": "01", "title": "A"}, {"num": "02", "title": "B"},
            {"num": "03", "title": "C"}]}),
        80, 130, 1120)
    assert elems and h > 0
    # 第 3 卡应在第二行（y > 130）
    card2 = [e for e in elems if e["elementId"] == "toc-2"][0]
    assert card2["bounds"][1] > 130


def test_duo_compare_asymmetric():
    """右侧无 points 应只渲染标题，高度由左侧决定。"""
    elems, h = pe.emit_chrome_pptd(
        "duo_compare", _norm({"type": "duo_compare",
                              "left": {"title": "A", "points": ["a1", "a2", "a3"]},
                              "right": {"title": "B", "points": []}}),
        80, 130, 1120)
    assert elems and h > 0
    # 右面板应只有标题元素（duo-t1），无正文（duo-b1）
    assert "duo-t1" in _ids(elems)
    assert "duo-b1" not in _ids(elems)


def test_duo_compare_geometry():
    """验证左右面板 x 坐标与中隔线位置。"""
    elems, h = pe.emit_chrome_pptd(
        "duo_compare", _norm({"type": "duo_compare",
                              "left": {"title": "L", "points": ["x"]},
                              "right": {"title": "R", "points": ["y"]}}),
        80, 130, 1120)
    by_id = {e["elementId"]: e for e in elems}
    # 左面板标题 x≈88（_line 有 8px 内部 padding）
    left_t = by_id["duo-t0"]
    assert abs(left_t["bounds"][0] - 88) < 2
    # 中隔线应在两面板中间
    vr = by_id["duo-vr"]
    assert 630 < vr["bounds"][0] < 650  # (80+1120)/2 ≈ 640


def test_pros_cons_one_side_empty():
    """单侧空列表应只渲染另一侧。"""
    elems, h = pe.emit_chrome_pptd(
        "pros_cons", _norm({"type": "pros_cons",
                            "pros": [], "cons": ["成本"]}),
        80, 130, 1120)
    assert elems and h > 0
    # 单侧渲染时 ID 从 0 开始（enumerate(non_empty)）
    # cons 非空 → pc-bg0 存在，标题颜色为橙色（part_text）
    assert "pc-bg0" in _ids(elems)
    by_id = {e["elementId"]: e for e in elems}
    assert by_id["pc-h0"]["content"]["color"] == "#B7791F"  # part_text 橙


def test_pros_cons_color():
    """pros 标题用 lit_text（绿），cons 标题用 part_text（橙）。"""
    elems, h = pe.emit_chrome_pptd(
        "pros_cons", _norm({"type": "pros_cons",
                            "pros": ["a"], "cons": ["b"]}),
        80, 130, 1120, theme_name="corporate_navy")
    by_id = {e["elementId"]: e for e in elems}
    pros_h = by_id["pc-h0"]
    cons_h = by_id["pc-h1"]
    assert pros_h["content"]["color"] == "#00795A"  # lit_text（corporate_navy）
    assert cons_h["content"]["color"] == "#B04900"  # part_text（corporate_navy）


def test_cta_block_minimal():
    """无 button/contact 应只渲染标题 + 背景。"""
    elems, h = pe.emit_chrome_pptd(
        "cta_block", _norm({"type": "cta_block", "title": "仅标题"}),
        80, 130, 1120, theme_name="corporate_navy")
    assert elems and h > 0
    assert "cta-bg" in _ids(elems)
    assert "cta-btn" not in _ids(elems)
    assert "cta-c" not in _ids(elems)


def test_cta_block_button_only():
    """有 button 无 contact 应渲染按钮，无联系方式。"""
    elems, h = pe.emit_chrome_pptd(
        "cta_block", _norm({"type": "cta_block", "title": "标题",
                            "button": "按钮"}),
        80, 130, 1120, theme_name="corporate_navy")
    assert "cta-btn" in _ids(elems)
    assert "cta-c" not in _ids(elems)


def test_cta_block_geometry():
    """验证按钮居中 + 标题颜色。"""
    elems, h = pe.emit_chrome_pptd(
        "cta_block", _norm({"type": "cta_block", "title": "标题",
                            "button": "按钮", "contact": "400"}),
        80, 130, 1120, theme_name="corporate_navy")
    by_id = {e["elementId"]: e for e in elems}
    # 按钮居中：bx = 80 + (1120-160)/2 = 560
    btn = by_id["cta-btn"]
    assert abs(btn["bounds"][0] - 560) < 2
    # 标题颜色 = card（白）
    title = by_id["cta-t"]
    assert title["content"]["color"] == "#FFFFFF"
    # 按钮文字颜色 = hero_from（深）
    btn_t = by_id["cta-bt"]
    assert btn_t["content"]["color"] == "#101F4A"  # corporate_navy hero_from
