# -*- coding: utf-8 -*-
"""R-3 回归：architecture.py hex 主题化 + veil 默认色单点 + 封面白字槽位。

锚定 enterprise/corporate_navy 下逐字节不变（mix 派生精确复现原硬编码值），
并钉住 veil/白字的单一事实源引用关系。
"""

import yaml

from _pptd_gen import _build_cover_page
from _renderer.diagram import render_diagram_pptd
from _renderer.theme import DEFAULT_PPTD_SLOTS, DEFAULT_VEIL, WHITE


def _deploy_elem():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "deployment",
            "title": "部署",
            "zones": [{"name": "入口", "nodes": [{"name": "用户", "desc": "外部"}]},
                      {"name": "核心", "nodes": [{"name": "e-filing"}]}],
            "links": [{"from": "入口.用户", "to": "核心.e-filing", "mode": "sync"}]}


def test_deployment_enterprise_byte_anchor():
    """corporate_navy（enterprise 映射）下主题化取值与原硬编码逐值相等。"""
    elems, h = render_diagram_pptd(_deploy_elem(), 192, 130, 1048, style="corporate_navy")
    assert h > 0
    node = next(el for el in elems if el["elementId"].endswith("dep-z-0-n0"))
    assert node["fill"]["color"] == "#1E3A8A"
    assert node["border"]["color"] == "#101F4A"
    name_t = next(el for el in elems if el["elementId"].endswith("dep-z-0-n0-t"))
    assert name_t["content"]["color"] == "#1A1A1A"
    desc_t = next(el for el in elems if el["elementId"].endswith("dep-z-0-n0-d"))
    assert desc_t["content"]["color"] == "#525252"
    icon_t = next(el for el in elems if el["elementId"].endswith("dep-z-0-n0-i"))
    assert icon_t["content"]["color"] == WHITE == "#FFFFFF"


def test_veil_single_source():
    """veil 默认色：theme.DEFAULT_VEIL 为唯一事实源，pptd 槽位表与封面兜底同源。"""
    assert DEFAULT_PPTD_SLOTS["veil"] == DEFAULT_VEIL == "#0A1540"
    page = yaml.safe_load(_build_cover_page(
        {"document": {"title": "T", "cover": {}}}, None, None))
    assert page["background"]["color"] == DEFAULT_VEIL


def test_cover_white_text_slots():
    """封面白字走 theme.WHITE（hex8 alpha 由 WHITE 派生，不写 #FFFFFF 字面量）。"""
    page = yaml.safe_load(_build_cover_page(
        {"document": {"title": "T", "subtitle": "S", "cover": {"confidential": "机密"}},
         "author": "A", "date": "2026-09-07"}, None, None))
    by_id = {el["elementId"]: el for el in page["elements"]}
    assert by_id["title"]["content"]["color"] == WHITE
    assert by_id["subtitle"]["content"]["color"] == f"{WHITE}D9"
    assert by_id["author"]["content"]["color"] == f"{WHITE}A6"
    assert by_id["confidential"]["content"]["color"] == f"{WHITE}CC"
