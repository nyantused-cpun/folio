# -*- coding: utf-8 -*-
"""C-F1 图级 validate delta 回归（2026-09-07）。

现状盘点：verify 链经 _verify.py verify_spec_layout_data -> schema.validate_spec
（error：类型合法/必填字段/subtype 专项）与 schema.validate_element_warnings
（warning：容量预算）已覆盖大部分图级校验；本文件锁 graphics.md §2 有口径但
verify 链无检查的三条 delta：
  - flow/cross_system 系统列数 ≤6（schema 原只查单列行数 ≤4）
  - architecture/infra zone 数 ≤4、每 zone 节点 ≤4（schema 原无容量检查）
以及 _verify_checks.check_diagram_level 聚合契约 + graphics.md 对账。
"""
import os
import re
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer import schema
from _verify_checks import check_diagram_level

GRAPHICS_MD = (Path(__file__).resolve().parent.parent
               / ".folio" / "skills" / "visual-craft-guide"
               / "references" / "graphics.md")


def _cross_system(n_systems, n_steps_per_system=1, with_systems=True):
    systems = [{"name": f"系统{i}"} for i in range(n_systems)]
    steps = [{"name": f"步骤{s}", "system": f"系统{s % n_systems}"}
             for s in range(n_systems * n_steps_per_system)]
    elem = {"type": "diagram", "diagram_type": "flow",
            "subtype": "cross_system", "title": "跨系统", "steps": steps}
    if with_systems:
        elem["systems"] = systems
    return elem


def _infra(n_zones, n_nodes_per_zone):
    zones = [{"name": f"zone{i}", "nodes": [{"name": f"节点{j}", "icon": "app"}
                                            for j in range(n_nodes_per_zone)]}
             for i in range(n_zones)]
    return {"type": "diagram", "diagram_type": "architecture",
            "subtype": "infra", "title": "部署", "zones": zones}


# ---- delta 1：cross_system 系统列数 ≤6 ----

@pytest.mark.parametrize("n,expect_warn", [
    (6, False), (7, True),
])
def test_cross_system_systems_capacity(n, expect_warn):
    elem = _cross_system(n)
    warns = schema.validate_element_warnings(elem, index=0)
    hit = any("系统列" in w for w in warns)
    assert hit is expect_warn


def test_cross_system_systems_derived_from_steps():
    """systems 列表缺省时按 steps 的 system 字段派生（与行数检查同一口径）。"""
    elem = _cross_system(7, with_systems=False)
    warns = schema.validate_element_warnings(elem, index=0)
    assert any("系统列 7 超过容量上限 6" in w for w in warns)


def test_cross_system_rows_check_unchanged():
    """既有单列行数 ≤4 检查不被新检查取代（不重复造轮子=不丢旧轮子）。"""
    elem = _cross_system(3, n_steps_per_system=5)  # 3 列 × 5 行，列数合规
    warns = schema.validate_element_warnings(elem, index=0)
    assert any("单列行数 5 超过容量上限 4" in w for w in warns)
    assert not any("系统列" in w for w in warns)


# ---- delta 2：infra zone / 节点容量 ----

def test_infra_zones_capacity():
    assert not any("zone" in w for w in
                   schema.validate_element_warnings(_infra(4, 1), index=0))
    warns = schema.validate_element_warnings(_infra(5, 1), index=0)
    assert any("zone 5 超过容量上限 4" in w for w in warns)


def test_infra_zone_nodes_capacity():
    assert not schema.validate_element_warnings(_infra(1, 4), index=0)
    warns = schema.validate_element_warnings(_infra(1, 5), index=0)
    assert any("zones[0] 节点 5 超过容量上限 4" in w for w in warns)


def test_infra_capacity_is_warning_not_error():
    """容量预算保持 warning 级（与 graphics.md「超预算拆页不硬塞」口径一致）。"""
    assert schema.validate_element(_infra(9, 9), index=0) == []


# ---- check_diagram_level 聚合契约 ----

def test_diagram_level_clean_spec():
    spec = {"pages": [{"elements": [_cross_system(3), _infra(2, 2)]}]}
    r = check_diagram_level(spec)
    assert r["diagrams"] == 2
    assert r["errors"] == []
    assert r["warnings"] == []


def test_diagram_level_error_positioning():
    """schema error 经聚合后带 pages[pi]. 前缀，与 validate_spec 报错风格一致。"""
    bad = {"type": "diagram", "diagram_type": "hologram", "subtype": "x",
           "title": "t"}
    spec = {"pages": [{"elements": [bad]}]}
    r = check_diagram_level(spec)
    assert r["diagrams"] == 1
    assert len(r["errors"]) == 1
    assert r["errors"][0].startswith("pages[0].elements[0]: 未知 diagram_type")


def test_diagram_level_ignores_non_diagram():
    spec = {"pages": [{"elements": [
        {"type": "text", "content": "x"},
        {"type": "table", "headers": ["a"], "rows": [["b"]]},
    ]}]}
    r = check_diagram_level(spec)
    assert r == {"diagrams": 0, "errors": [], "warnings": []}


def test_diagram_level_malformed_pages_tolerated():
    r = check_diagram_level({"pages": [None, "x", {"elements": [None, {}]}]})
    assert r["diagrams"] == 0


# ---- graphics.md §2 对账（新三行，沿用 test_graphics_capacity_sync 口径） ----

def _capacity_row(element):
    text = GRAPHICS_MD.read_text(encoding="utf-8")
    sec = text.split("## 2. 容量预算", 1)
    assert len(sec) == 2, "graphics.md 缺 §2 容量预算节"
    m = re.search(rf"^\| {re.escape(element)} \| ([^|]+)\|", sec[1], re.M)
    assert m, f"graphics.md §2 缺 {element} 容量行"
    return m.group(1)


def test_cross_system_capacity_syncs_with_graphics_md():
    row = _capacity_row("flow/cross_system")
    m = re.search(r"≤(\d+) 个系统列", row)
    assert m, "cross_system 容量行缺「≤N 个系统列」表述"
    assert int(m.group(1)) == schema.CROSS_SYSTEM_SYSTEMS_WARN


def test_infra_capacity_syncs_with_graphics_md():
    row = _capacity_row("architecture/infra")
    m = re.search(r"≤(\d+) zone", row)
    assert m, "infra 容量行缺「≤N zone」表述"
    assert int(m.group(1)) == schema.INFRA_ZONES_WARN
    m = re.search(r"每 zone ≤(\d+) 节点", row)
    assert m, "infra 容量行缺「每 zone ≤N 节点」表述"
    assert int(m.group(1)) == schema.INFRA_ZONE_NODES_WARN


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
