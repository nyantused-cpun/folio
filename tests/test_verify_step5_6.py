# -*- coding: utf-8 -*-
"""Step 5/6 附加 verify 检查：capability_map 系统名当芯片 + series 同壳豁免。"""

from _verify import check_capability_map_system_name_as_chip, check_shell_repetition


def test_capability_map_system_name_as_chip_errors():
    spec = {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "diagram", "diagram_type": "matrix", "subtype": "capability_map",
         "title": "能力图", "sections": [
             {"name": "S1", "capabilities": [
                 {"name": "能力A", "items": [{"name": "CRM", "status": "lit"}]},
             ]},
         ],
         "systems_inventory": [{"name": "CRM", "pts": "3", "detail": "客户系统"}]},
    ]}]}
    errors = check_capability_map_system_name_as_chip(spec)
    assert any("CRM" in e and "系统名不能当芯片" in e for e in errors)


def test_capability_map_distinct_names_ok():
    spec = {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "diagram", "diagram_type": "matrix", "subtype": "capability_map",
         "title": "能力图", "sections": [
             {"name": "S1", "capabilities": [
                 {"name": "能力A", "items": [{"name": "客户管理", "status": "lit"}]},
             ]},
         ],
         "systems_inventory": [{"name": "CRM", "pts": "3", "detail": "客户系统"}]},
    ]}]}
    assert check_capability_map_system_name_as_chip(spec) == []


def test_shell_repetition_series_exempt():
    spec = {"pages": [
        {"id": "p1", "title": "步骤1", "layout": "P05", "series": "flow-seq",
         "elements": [{"type": "section_tag"}, {"type": "action_title"},
                      {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
                       "title": "t", "steps": []}]},
        {"id": "p2", "title": "步骤2", "layout": "P05", "series": "flow-seq",
         "elements": [{"type": "section_tag"}, {"type": "action_title"},
                      {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
                       "title": "t", "steps": []}]},
        {"id": "p3", "title": "步骤3", "layout": "P05", "series": "flow-seq",
         "elements": [{"type": "section_tag"}, {"type": "action_title"},
                      {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
                       "title": "t", "steps": []}]},
    ]}
    assert check_shell_repetition(spec) == []
