# -*- coding: utf-8 -*-
"""_pptd_parts.py 几何纯函数直测（S2=V-A 批 T-2）。

覆盖 _snap_element / _clamp_bottom / _scale_group_bounds 三个纯几何函数，
边界：空输入、None、单元素、负值/零尺寸、非数值 bounds、children 递归。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _pptd_parts import (
    _snap_element, _clamp_bottom, _scale_group_bounds,
    _CONTENT_Y_MAX,
)


class _Report:
    """report 桩：只收 warn（_clamp_bottom 裁剪路径用）。"""

    def __init__(self):
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(msg)


class TestSnapElement:
    def test_empty_dict_noop(self):
        e = {}
        _snap_element(e)
        assert e == {}

    def test_none_bounds_noop(self):
        e = {"bounds": None}
        _snap_element(e)
        assert e["bounds"] is None

    @pytest.mark.parametrize("bad", [
        "not-a-list", [1, 2, 3], [1, 2, 3, 4, 5],
    ])
    def test_malformed_bounds_noop(self, bad):
        e = {"bounds": bad}
        _snap_element(e)
        assert e["bounds"] == bad

    def test_snaps_to_grid(self):
        e = {"bounds": [81, 131, 100, 50]}
        _snap_element(e)
        # x1=snap(81)=80, y1=snap(131)=132, x2=snap(181)=180, y2=snap(181)=180
        assert e["bounds"] == [80, 132, 100, 48]

    def test_zero_size_floors_to_one(self):
        e = {"bounds": [100, 100, 0, 0]}
        _snap_element(e)
        assert e["bounds"] == [100, 100, 1, 1]

    def test_negative_size_floors_to_one(self):
        e = {"bounds": [100, 100, -8, -4]}
        _snap_element(e)
        # x2=snap(92)=92 < x1=100 → 兜底 1；y 同理
        assert e["bounds"] == [100, 100, 1, 1]

    def test_non_numeric_bounds_zeroed_and_snapped(self):
        e = {"bounds": ["a", "b", "c", "d"]}
        _snap_element(e)
        assert e["bounds"] == [0, 0, 1, 1]

    def test_bottom_on_content_line_preserved(self):
        """底边恰贴 _CONTENT_Y_MAX 是防线裁剪产物：保边不吸附。"""
        y = 600
        e = {"bounds": [80, y, 100, _CONTENT_Y_MAX - y]}
        _snap_element(e)
        assert e["bounds"][1] + e["bounds"][3] == _CONTENT_Y_MAX
        # 对照：非贴线底边正常吸附（672 在网格上不变；用 671 验证吸附发生）
        e2 = {"bounds": [80, 600, 100, 71]}
        _snap_element(e2)
        assert e2["bounds"][1] + e2["bounds"][3] == 672

    def test_children_recursed(self):
        e = {"bounds": [81, 131, 100, 50],
             "children": [{"bounds": [83, 133, 10, 10]}]}
        _snap_element(e)
        assert e["children"][0]["bounds"] == [84, 132, 8, 12]

    def test_children_none_tolerated(self):
        e = {"bounds": [80, 130, 100, 50], "children": None}
        _snap_element(e)
        # round(32.5)=32（银行家舍入）→ y1=128；y2=snap(180)=180 → h=52
        assert e["bounds"] == [80, 128, 100, 52]


class TestClampBottom:
    def test_within_bounds_returns_h(self):
        assert _clamp_bottom("p", "e", 100, 100, _Report()) == 100

    def test_exactly_on_line_returns_h(self):
        assert _clamp_bottom("p", "e", 100, _CONTENT_Y_MAX - 100, _Report()) == _CONTENT_Y_MAX - 100

    def test_zero_height_returns_zero(self):
        assert _clamp_bottom("p", "e", 100, 0, _Report()) == 0

    def test_less_than_one_line_returns_none(self):
        # available=4 < 14*1.3=18.2 → 一行都显示不出，None 交调用方整元素 skip
        assert _clamp_bottom("p", "e", _CONTENT_Y_MAX - 4, 100, _Report()) is None

    def test_start_beyond_line_returns_none(self):
        assert _clamp_bottom("p", "e", _CONTENT_Y_MAX + 10, 10, _Report()) is None

    def test_crops_and_warns(self):
        report = _Report()
        h = _clamp_bottom("p01", "card-1", 600, 200, report)
        assert h == _CONTENT_Y_MAX - 600
        assert len(report.warnings) == 1 and "p01" in report.warnings[0]

    def test_font_size_changes_one_line_threshold(self):
        # font_size=3 → 阈值 3.9；available=4 刚够一行 → 裁剪而非 None
        report = _Report()
        h = _clamp_bottom("p", "e", _CONTENT_Y_MAX - 4, 100, report, font_size=3)
        assert h == 4
        assert len(report.warnings) == 1


class TestScaleGroupBounds:
    def test_empty_group_raises(self):
        # min()/max() 空序列：当前行为是 ValueError，钉住防静默吞掉
        with pytest.raises(ValueError):
            _scale_group_bounds([], 2.0, 0, 0)

    def test_single_element_scale_and_reposition(self):
        e = {"bounds": [100, 100, 50, 50]}
        _scale_group_bounds([e], 2.0, 0, 0)
        assert e["bounds"] == [0, 0, 100, 100]

    def test_single_element_zero_size(self):
        e = {"bounds": [100, 100, 0, 0]}
        _scale_group_bounds([e], 2.0, 0, 0)
        assert e["bounds"] == [0, 0, 0, 0]

    def test_negative_coords_preserved(self):
        e = {"bounds": [-50, -50, 100, 100]}
        _scale_group_bounds([e], 1.0, -50, -50)
        assert e["bounds"] == [-50, -50, 100, 100]

    def test_group_bbox_aligned_to_new_origin(self):
        a = {"bounds": [100, 100, 50, 50]}
        b = {"bounds": [150, 200, 50, 50]}
        _scale_group_bounds([a, b], 0.5, 10, 20)
        # 组 bbox 左上 (100,100) → (10,20)；组内相对位置同比缩放
        assert a["bounds"] == [10, 20, 25, 25]
        assert b["bounds"] == [35, 70, 25, 25]

    def test_scale_font_with_floor(self):
        e = {"bounds": [100, 100, 50, 50], "content": {"fontSize": 20}}
        _scale_group_bounds([e], 0.3, 0, 0, scale_font=True)
        assert e["content"]["fontSize"] == 8  # 20*0.3=6 → 下限 8

    def test_scale_font_off_leaves_font(self):
        e = {"bounds": [100, 100, 50, 50], "content": {"fontSize": 20}}
        _scale_group_bounds([e], 0.5, 0, 0)
        assert e["content"]["fontSize"] == 20

    def test_scale_font_non_numeric_tolerated(self):
        e = {"bounds": [100, 100, 50, 50], "content": {"fontSize": "abc"}}
        _scale_group_bounds([e], 0.5, 0, 0, scale_font=True)
        assert e["content"]["fontSize"] == "abc"

    def test_children_scaled_with_parent(self):
        e = {"bounds": [100, 100, 100, 100],
             "children": [{"bounds": [150, 150, 20, 20],
                           "content": {"fontSize": 10}}]}
        _scale_group_bounds([e], 2.0, 0, 0, scale_font=True)
        assert e["children"][0]["bounds"] == [100, 100, 40, 40]
        assert e["children"][0]["content"]["fontSize"] == 20
