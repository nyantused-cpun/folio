# -*- coding: utf-8 -*-
"""_renderer/diagram/relationship.py 参数化边界测试（S2=V-A 批 T-2）。

9 个 subtype（org_tree / er_conceptual / er_logical / data_flow / value_chain /
biz_capability_tree / process_service_doc_mapping / cross_4a_reconcile /
automation_table）× render_html / render_pptd × 空输入 / None 字段 / 单元素。
chart.py 参数化归 V-B 批，本文件不碰。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.diagram import relationship

SUBTYPES = [
    "org_tree", "er_conceptual", "er_logical", "data_flow", "value_chain",
    "biz_capability_tree", "process_service_doc_mapping",
    "cross_4a_reconcile", "automation_table",
]

# 各 subtype 的内容字段（None 边界用）
NONE_FIELDS = {
    "org_tree": {"root": None},
    "er_conceptual": {"entities": None, "relations": None},
    "er_logical": {"entities": None, "relations": None},
    "data_flow": {"nodes": None, "flows": None},
    "value_chain": {"primary": None, "support": None},
    "biz_capability_tree": {"groups": None},
    "process_service_doc_mapping": {"mappings": None},
    "cross_4a_reconcile": {"terms": None},
    "automation_table": {"tasks": None},
}

# 各 subtype 的最小单元素输入
SINGLE = {
    "org_tree": {"root": {"name": "根节点"}},
    "er_conceptual": {"entities": [{"name": "订单"}]},
    "er_logical": {"entities": [{"name": "订单", "attrs": ["金额"],
                                 "pk": ["订单号"]}]},
    "data_flow": {"nodes": [{"name": "CRM", "type": "source"}]},
    "value_chain": {"primary": ["研发"], "support": ["人力"]},
    "biz_capability_tree": {"groups": [{"name": "营销",
                                        "children": [{"name": "获客",
                                                      "items": ["投放"]}]}]},
    "process_service_doc_mapping": {"mappings": [
        {"process": "下单", "service": "订单服务", "document": "订单"}]},
    "cross_4a_reconcile": {"terms": [{"term": "客户", "ba": "客户",
                                      "aa": "CRM", "da": "客户表",
                                      "ta": "MySQL"}]},
    "automation_table": {"tasks": [{"name": "录入", "current": "人工",
                                    "target": "自动", "saving": "2h",
                                    "roi": "高"}]},
}


def _elem(subtype, **fields):
    return {"subtype": subtype, "title": "测试图", **fields}


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_html_empty_input(subtype):
    html = relationship.render_html(_elem(subtype))
    assert isinstance(html, str) and "diagram" in html


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_html_none_fields(subtype):
    html = relationship.render_html(_elem(subtype, **NONE_FIELDS[subtype]))
    assert isinstance(html, str)


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_html_single_element(subtype):
    html = relationship.render_html(_elem(subtype, **SINGLE[subtype]))
    assert isinstance(html, str) and len(html) > 0


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_pptd_empty_input(subtype):
    elems, h = relationship.render_pptd(_elem(subtype), 80, 130, 1120)
    assert isinstance(elems, list)
    assert isinstance(h, (int, float)) and h >= 0


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_pptd_none_fields(subtype):
    elems, h = relationship.render_pptd(
        _elem(subtype, **NONE_FIELDS[subtype]), 80, 130, 1120)
    assert isinstance(elems, list)
    assert isinstance(h, (int, float))


@pytest.mark.parametrize("subtype", SUBTYPES)
def test_render_pptd_single_element(subtype):
    elems, h = relationship.render_pptd(
        _elem(subtype, **SINGLE[subtype]), 80, 130, 1120)
    assert isinstance(elems, list) and len(elems) > 0
    assert h > 0


def test_unknown_subtype_html_raises():
    with pytest.raises(NotImplementedError):
        relationship.render_html(_elem("bogus_subtype"))


def test_unknown_subtype_pptd_raises():
    with pytest.raises(NotImplementedError):
        relationship.render_pptd(_elem("bogus_subtype"), 80, 130, 1120)
