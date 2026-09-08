# -*- coding: utf-8 -*-
"""B3-A4 回归：P1-V1 gantt 版心钳位 + P1-13 宽容校验器加固与缓存 fail-closed。

- P1-V1（视觉二轮实渲染目检实测 70px）：gantt 几何按内容列宽计算未对版心
  钳位——超宽 spec（start/span 超列数、负 start）任务条右边界必须 ≤ 版心
  右界，HTML 容器宽 = 版心宽，pptd 元素全部落在内容区内（双端同几何）。
- P1-13：宽容校验器对 LLM 混入的非 dict 元素拒绝而非裸崩（AttributeError）；
  quadrant 收紧为恰好 4 象限（对齐 schema QUADRANT_QUADS 硬校验）；图形 role
  校验不过的结果不得入提取缓存（缓存键查询为空，重跑可自愈）。
- P2-V1：全景冒烟覆盖面 = schema 全集（防冒烟面落后 schema 再漂移）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _diagram_extract as DX  # noqa: E402
import gen_panorama_spec as GP  # noqa: E402
from _renderer.schema import DIAGRAM_SCHEMA  # noqa: E402
from _renderer.diagram import timeline  # noqa: E402

EPS = 0.01


# ---------------------------------------------------------------------------
# P1-V1：gantt 版心钳位
# ---------------------------------------------------------------------------

# 超宽 spec：start+span 超列数冲右界、负 start 压左标签列（schema 只 warn
# 任务数不限跨列，此类 spec 合法可达渲染器）
_OVERWIDE_MSG = {
    "type": "diagram", "diagram_type": "timeline",
    "subtype": "milestone_gantt", "title": "超宽路线图",
    "columns": ["W1", "W2", "W3", "W4"],
    "tasks": [{"name": "冲右界", "start": 3, "span": 9},
              {"name": "负start", "start": -2, "span": 2},
              {"name": "正常", "start": 0, "span": 4}],
    "markers": [{"col": 9, "label": "越列里程碑"}],
}

_OVERWIDE_MG = {
    "type": "diagram", "diagram_type": "timeline",
    "subtype": "module_gantt", "title": "超宽排期",
    "columns": ["Q1", "Q2", "Q3"],
    "markers": [{"col": 2, "label": "上线"}],
    "groups": [{"name": "C. 核心域",
                "modules": [{"label": "C1", "col": 0}, {"label": "C2", "col": 2}]}],
}


def test_gantt_content_width_is_version_core():
    """容器宽 = 版心宽 1060（body 1200 − 页壳边框内边距 − section 边框内边距，
    实测 dg-body 1060.4；修复前写死 1200 即越界 70px）。"""
    assert timeline._GANTT_W == 1060.0
    assert timeline._msg_geometry(_OVERWIDE_MSG)["W"] == timeline._GANTT_W
    assert timeline._mg_geometry(_OVERWIDE_MG)["W"] == timeline._GANTT_W


def test_milestone_gantt_bars_within_content_right():
    """超宽任务条右边界 ≤ 版心右界（gx1），且不压左标签列。"""
    g = timeline._msg_geometry(_OVERWIDE_MSG)
    # gx1 不入几何 dict（消费方只用 gx0/col_w），由网格推导并锚定版心常量
    gx1 = g["gx0"] + g["n"] * g["col_w"]
    assert gx1 == timeline._GANTT_X1
    assert g["rows"], "任务行不应为空"
    for r in g["rows"]:
        assert r["bar_x"] + r["bar_w"] <= gx1 + EPS, "任务条冲出版心右界"
        assert r["bar_x"] >= g["gx0"] - EPS, "任务条压进左标签列"


def test_module_gantt_chips_within_content_right():
    """module_gantt 列头/chip 右边界 ≤ 版心右界。"""
    g = timeline._mg_geometry(_OVERWIDE_MG)
    gx1 = g["gx0"] + g["n"] * g["col_w"]
    assert gx1 == timeline._GANTT_X1
    for r in g["rows"]:
        for c, _labels in r["stacks"].items():
            assert 0 <= c < g["n"]
            chip_right = g["gx0"] + c * g["col_w"] + (g["col_w"] - 16)
            assert chip_right <= gx1 + EPS


def test_gantt_html_container_within_content():
    """HTML 容器与 SVG 覆盖层宽度均为版心宽（不再出现 1200 满幅）。"""
    msg_html = timeline.render_html(_OVERWIDE_MSG)
    mg_html = timeline.render_html(_OVERWIDE_MG)
    for html in (msg_html, mg_html):
        assert f'width:{timeline._GANTT_W:.0f}px' in html
        assert "width:1200px" not in html


def test_gantt_pptd_bounds_within_content_area():
    """pptd 端全部元素 bounds 落在内容区 [x, x+w]（viewBox 版心宽换算）。"""
    x, y, w = 80.0, 130.0, 1120.0
    for spec in (_OVERWIDE_MSG, _OVERWIDE_MG):
        elems, _h = timeline.render_pptd(spec, x, y, w)
        assert elems
        for el in elems:
            bx, _, bw, _ = el["bounds"]
            assert bx >= x - EPS, f"{el['elementId']} 越左界"
            assert bx + bw <= x + w + EPS, f"{el['elementId']} 越右界"


# ---------------------------------------------------------------------------
# P1-13：宽容校验器加固 + 缓存 fail-closed
# ---------------------------------------------------------------------------

def test_cbm_rejects_nondict_rows():
    """cbm rows 混入字符串/null：拒绝（None）而非 AttributeError 裸崩。"""
    bad = {"rows": ["决策层字符串", None,
                    {"level": "决策", "capabilities": [{"name": "战略"}]}]}
    assert DX._valid_cbm(bad) is None
    good = {"rows": [{"level": "决策", "capabilities": [{"name": "战略", "heat": "strong"}]},
                     {"level": "执行", "capabilities": ["报表"]}]}
    assert DX._valid_cbm(good) is not None


def test_capability_map_rejects_nondict_sections():
    """capability_map sections 混入非 dict：拒绝而非裸崩。"""
    bad = {"sections": ["字符串section", None,
                        {"name": "s1", "capabilities": ["a"]}]}
    assert DX._valid_capability_map(bad) is None
    good = {"sections": [{"name": "s1", "capabilities": [{"name": "a"}]}]}
    assert DX._valid_capability_map(good) is not None


def test_module_gantt_rejects_nondict_groups():
    """module_gantt groups 混入非 dict：拒绝而非裸崩。"""
    bad = {"columns": ["Q1"], "groups": [None, "字符串组"]}
    assert DX._valid_module_gantt(bad) is None
    good = {"columns": ["Q1"], "groups": [{"name": "g", "modules": [{"label": "m"}]}]}
    assert DX._valid_module_gantt(good) is not None


def test_quadrant_requires_exactly_four_quads():
    """quadrant 收紧为恰好 4 象限：3/5 象限拒绝（放行会 verify FAIL），4 通过。"""
    axes = {"x": "紧急度", "y": "影响面"}

    def _quads(n):
        return [{"title": f"象限{i}", "items": ["a"]} for i in range(n)]

    assert DX._valid_quadrant({"axes": axes, "quads": _quads(3)}) is None
    assert DX._valid_quadrant({"axes": axes, "quads": _quads(5)}) is None
    ok = DX._valid_quadrant({"axes": axes, "quads": _quads(4)})
    assert ok is not None and len(ok["quads"]) == 4


def test_malformed_diagram_result_not_cached():
    """P1-13 fail-closed：图形 role 校验不过的结果不得入缓存（缓存键查询为空），
    合法结果照常入缓存。调用方契约：_outline_to_spec 缓存写入处仅当
    diagram_result_cacheable 为真才 _cache_put。"""
    section = {"section": "方案总览", "role": "solution_overview"}
    bad = {"rows": ["字符串而非dict", None]}          # cbm 校验不过
    good = {"rows": [{"level": "决策", "capabilities": ["战略"]}]}
    assert DX.diagram_result_cacheable(section, bad) is False
    assert DX.diagram_result_cacheable(section, good) is True

    cache = {}

    def _cache_put(key, section_name, result):       # _cache_put 同签名替身
        cache[key] = {"section": section_name, "result": result}

    for i, result in enumerate((bad, good)):
        if DX.diagram_result_cacheable(section, result):
            _cache_put(f"k{i}", section["section"], result)
    assert not any(v["result"] is bad for v in cache.values())
    assert "k1" in cache                             # 合法结果入缓存

    # 非图形 role 恒可缓存（缓存语义不变）
    assert DX.diagram_result_cacheable({"role": "overview"}, bad) is True


# ---------------------------------------------------------------------------
# P2-V1：全景冒烟覆盖面 = schema 全集
# ---------------------------------------------------------------------------

def test_panorama_covers_all_schema_subtypes():
    """gen_panorama_spec 覆盖 schema 全部子类型（bar/waterfall/harvey_balls/infra
    曾缺席——冒烟面落后 schema 的漂移由此钉死）。"""
    covered = {p["elements"][0]["diagram_type"] + "/" + p["elements"][0]["subtype"]
               for p in GP.build_pages()}
    expected = {f"{family}/{st}" for family, subs in DIAGRAM_SCHEMA.items()
                for st in subs}
    assert covered == expected
