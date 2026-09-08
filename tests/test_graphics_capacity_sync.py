# -*- coding: utf-8 -*-
import pytest
"""C-1 文档-代码对账：graphics.md §2 容量上限数字必须与 _renderer/schema.py 的
*_WARN 常量一致（常量单一事实源=_renderer/budget_consts.py，schema.py 经 import
re-export，graphics.md 为写作侧镜像）。

C-1 终态双层制（D7-2，S10-3d）：graphics.md §2 = 写作预算层（standard 档，
= 告警阈值-1）；行内「机检告警 N（CONST）」注记 = 机检告警层（= *_WARN 常量）。
两组断言并跑，保证「写作预算 vs 告警阈值」互标不漂移。
"""

import re
from pathlib import Path

from _renderer import schema

GRAPHICS_MD = (Path(__file__).resolve().parent.parent
               / ".folio" / "skills" / "visual-craft-guide"
               / "references" / "graphics.md")


def _capacity_section():
    text = GRAPHICS_MD.read_text(encoding="utf-8")
    sec = text.split("## 2. 容量预算", 1)
    assert len(sec) == 2, "graphics.md 缺 §2 容量预算节"
    return sec[1].split("## 3.", 1)[0]


def _capacity_row(element):
    """取元素行的预算单元格（第一个 | 前的内容，dense 档列不参与匹配）。"""
    sec = _capacity_section()
    m = re.search(rf"^\| {re.escape(element)} \| ([^|]+)\|", sec, re.M)
    assert m, f"graphics.md §2 缺 {element} 容量行"
    return m.group(1)


def test_table_capacity_matches_schema():
    """写作预算层：table 行「写作预算 ≤N 行」= P07_TABLE_ROWS_WARN - 1（差 1 档缓冲）。"""
    row = _capacity_row("table")
    m = re.search(r"写作预算 ≤(\d+) 行", row)
    assert m, "table 容量行缺「写作预算 ≤N 行」表述"
    assert int(m.group(1)) == schema.P07_TABLE_ROWS_WARN - 1


def test_timeline_horizontal_capacity_matches_schema():
    """写作预算层：timeline/horizontal「写作预算 ≤N 个 milestones」= 常量 - 1。"""
    row = _capacity_row("timeline/horizontal")
    m = re.search(r"写作预算 ≤(\d+) 个 milestones", row)
    assert m, "timeline/horizontal 容量行缺「写作预算 ≤N 个 milestones」表述"
    assert int(m.group(1)) == schema.TIMELINE_HORIZONTAL_CARDS_WARN - 1


def test_dual_layer_notation_and_warn_numbers_match_schema():
    """机检告警层：§2 存在「写作预算」「告警阈值」双层表述注记（grep 关键字），
    且 table 行「机检告警 N」数字（该行第二个数，紧随写作预算）与
    P07_TABLE_ROWS_WARN 一致；timeline 两行同理。保证互标不漂移。"""
    sec = _capacity_section()
    assert "写作预算" in sec, "graphics.md §2 缺「写作预算」双层表述注记"
    assert "告警阈值" in sec, "graphics.md §2 缺「告警阈值」双层表述注记"
    row = _capacity_row("table")
    m = re.search(r"机检告警 (\d+)", row)
    assert m, "table 容量行缺「机检告警 N」注记"
    assert int(m.group(1)) == schema.P07_TABLE_ROWS_WARN
    assert schema.P07_TABLE_ROWS_WARN == 12  # 裁决锚点：写作预算 11 vs 告警 12
    row_h = _capacity_row("timeline/horizontal")
    m = re.search(r"机检告警 (\d+)", row_h)
    assert m and int(m.group(1)) == schema.TIMELINE_HORIZONTAL_CARDS_WARN
    row_v = _capacity_row("timeline/vertical")
    m = re.search(r"机检告警 (\d+)", row_v)
    assert m and int(m.group(1)) == schema.TIMELINE_VERTICAL_CARDS_WARN


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
