# -*- coding: utf-8 -*-
"""叙事设计单 schema 校验测试（阶段 2-1/2-3，视觉生产线重构计划 §2.1/§2.3）。

覆盖：validate_narrative 正反例（必填/枚举/唯一性/graphic 格式）、
load_and_validate 文件级错误（不存在/坏 YAML/空文件）、
spec 顶层 narrative_ref 字段校验（schema.py 阶段 2-3 改动）。
"""

import os
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.narrative_schema import load_and_validate, validate_narrative
from _renderer.schema import validate_spec


def _page(**over):
    base = {"page": "p01_pain", "beat": "现状发现",
            "讲法": "data_narrative", "layout": "P04"}
    base.update(over)
    return base


def _doc(**over):
    base = {
        "audience": "CIO 与信息化委员会，季度规划评审会",
        "reading": "scroll",
        "page_budget": 12,
        "arc": "现状多痛→蓝图多好→怎么走到",
        "page_map": [_page()],
    }
    base.update(over)
    return base


# ---- 正例 ----

def test_valid_minimal():
    assert validate_narrative(_doc()) == []


def test_valid_full_with_graphic_and_scene():
    doc = _doc(scene="整体信息化规划", page_map=[
        _page(),
        _page(page="p03_gap", beat="差距分析",
              讲法="comparison_matrix", layout="P08", graphic="matrix/fit_gap"),
    ])
    assert validate_narrative(doc) == []


def test_graphic_null_valid():
    assert validate_narrative(_doc(page_map=[_page(graphic=None)])) == []


def test_scene_absent_valid():
    assert "scene" not in _doc()
    assert validate_narrative(_doc()) == []


def test_reading_all_containers_valid():
    for reading in ("scroll", "chapters", "stage", "report"):
        assert validate_narrative(_doc(reading=reading)) == []


# ---- 必填字段 ----

def test_missing_audience():
    doc = _doc()
    del doc["audience"]
    errors = validate_narrative(doc)
    assert any(e.startswith("audience") for e in errors)


def test_empty_audience():
    assert any(e.startswith("audience")
               for e in validate_narrative(_doc(audience="  ")))


def test_missing_arc():
    doc = _doc()
    del doc["arc"]
    assert any(e.startswith("arc") for e in validate_narrative(doc))


def test_non_dict_doc():
    assert validate_narrative(["not", "a", "dict"])


# ---- reading 枚举 ----

def test_reading_invalid():
    errors = validate_narrative(_doc(reading="flip"))
    assert any("reading" in e and "flip" in e for e in errors)


def test_reading_missing():
    doc = _doc()
    del doc["reading"]
    assert any(e.startswith("reading") for e in validate_narrative(doc))


# ---- page_budget ----

def test_page_budget_zero_and_negative():
    assert any("page_budget" in e for e in validate_narrative(_doc(page_budget=0)))
    assert any("page_budget" in e for e in validate_narrative(_doc(page_budget=-3)))


def test_page_budget_non_int():
    assert any("page_budget" in e
               for e in validate_narrative(_doc(page_budget="12")))
    assert any("page_budget" in e
               for e in validate_narrative(_doc(page_budget=12.5)))


def test_page_budget_bool_rejected():
    # bool 是 int 子类，但 True/False 不是合法页数预算
    assert any("page_budget" in e for e in validate_narrative(_doc(page_budget=True)))


# ---- scene ----

def test_scene_non_str():
    assert any("scene" in e for e in validate_narrative(_doc(scene=123)))


# ---- page_map ----

def test_page_map_missing_and_empty():
    doc = _doc()
    del doc["page_map"]
    assert any("page_map" in e for e in validate_narrative(doc))
    assert any("page_map" in e for e in validate_narrative(_doc(page_map=[])))


def test_page_map_item_not_dict():
    errors = validate_narrative(_doc(page_map=["just a string"]))
    assert any("page_map[0]" in e for e in errors)


def test_page_duplicate():
    errors = validate_narrative(_doc(page_map=[_page(), _page()]))
    assert any("重复" in e for e in errors)


def test_page_missing_and_empty():
    assert any("page" in e for e in validate_narrative(_doc(page_map=[_page(page="")])))
    item = _page()
    del item["page"]
    assert any("page" in e for e in validate_narrative(_doc(page_map=[item])))


def test_beat_missing():
    item = _page()
    del item["beat"]
    assert any("beat" in e for e in validate_narrative(_doc(page_map=[item])))


def test_composition_invalid():
    errors = validate_narrative(_doc(page_map=[_page(讲法="story_time")]))
    assert any("讲法" in e and "story_time" in e for e in errors)


def test_layout_invalid():
    errors = validate_narrative(_doc(page_map=[_page(layout="P20")]))
    assert any("page_map[0].layout" in e and "P20" in e for e in errors)


# ---- graphic ----

def test_graphic_no_slash():
    errors = validate_narrative(_doc(page_map=[_page(graphic="fit_gap")]))
    assert any("graphic" in e and "族/subtype" in e for e in errors)


def test_graphic_unknown_family():
    errors = validate_narrative(_doc(page_map=[_page(graphic="pie/fit_gap")]))
    assert any("未知族" in e for e in errors)


def test_graphic_unknown_subtype():
    errors = validate_narrative(
        _doc(page_map=[_page(graphic="matrix/no_such_subtype")]))
    assert any("subtype" in e and "matrix" in e for e in errors)


def test_graphic_extra_slash_and_non_str():
    assert any("graphic" in e for e in validate_narrative(
        _doc(page_map=[_page(graphic="a/b/c")])))
    assert any("graphic" in e for e in validate_narrative(
        _doc(page_map=[_page(graphic=123)])))


# ---- load_and_validate ----

def test_load_missing_file(tmp_path):
    doc, errors = load_and_validate(str(tmp_path / "不存在_叙事设计_v1.yml"))
    assert doc is None
    assert any("文件不存在" in e for e in errors)


def test_load_bad_yaml(tmp_path):
    path = tmp_path / "坏_叙事设计_v1.yml"
    path.write_text("audience: [unclosed\n  - {bad", encoding="utf-8")
    doc, errors = load_and_validate(str(path))
    assert doc is None
    assert any("YAML 解析失败" in e for e in errors)


def test_load_empty_file(tmp_path):
    path = tmp_path / "空_叙事设计_v1.yml"
    path.write_text("", encoding="utf-8")
    doc, errors = load_and_validate(str(path))
    assert doc is None
    assert any("为空" in e for e in errors)


def test_load_valid_roundtrip(tmp_path):
    path = tmp_path / "某客户_叙事设计_v1.yml"
    path.write_text(yaml.safe_dump(_doc(), allow_unicode=True),
                    encoding="utf-8")
    doc, errors = load_and_validate(str(path))
    assert errors == []
    assert doc["reading"] == "scroll"
    assert doc["page_map"][0]["讲法"] == "data_narrative"


def test_load_validation_errors_keep_doc(tmp_path):
    path = tmp_path / "某客户_叙事设计_v1.yml"
    path.write_text(yaml.safe_dump(_doc(reading="flip"), allow_unicode=True),
                    encoding="utf-8")
    doc, errors = load_and_validate(str(path))
    assert doc is not None  # 解析成功但校验失败：doc 仍返回供排查
    assert any("reading" in e for e in errors)


# ---- spec 顶层 narrative_ref（阶段 2-3，schema.py）----

def test_spec_narrative_ref_valid_and_absent():
    assert validate_spec({"pages": []}) == []
    assert validate_spec(
        {"narrative_ref": "某客户_叙事设计_v1.yml", "pages": []}) == []


def test_spec_narrative_ref_invalid():
    assert any("narrative_ref" in e
               for e in validate_spec({"narrative_ref": "", "pages": []}))
    assert any("narrative_ref" in e
               for e in validate_spec({"narrative_ref": 123, "pages": []}))


# ---- 表达模式 / crafted 页必填 ----

def test_crafted_requires_primary_expression_static_equivalent_density():
    item = _page(expression_mode="crafted")
    errors = validate_narrative(_doc(page_map=[item]))
    assert any("primary_expression" in e for e in errors)
    assert any("static_equivalent" in e for e in errors)
    assert any("density" in e for e in errors)


def test_crafted_valid():
    item = _page(
        expression_mode="crafted",
        primary_expression="核心愿景图：一页定调",
        static_equivalent="主标题+三要点卡片",
        density="low",
    )
    assert validate_narrative(_doc(page_map=[item])) == []


def test_expression_mode_invalid():
    errors = validate_narrative(_doc(page_map=[_page(expression_mode="creative")]))
    assert any("expression_mode" in e and "creative" in e for e in errors)


def test_depth_and_density_enums():
    assert any("depth" in e for e in validate_narrative(
        _doc(page_map=[_page(depth="verbose")])))
    assert any("density" in e for e in validate_narrative(
        _doc(page_map=[_page(expression_mode="crafted",
                              primary_expression="x",
                              static_equivalent="y",
                              density="huge")])))


def test_standard_ignores_crafted_fields():
    item = _page(expression_mode="standard")
    assert "primary_expression" not in item
    assert validate_narrative(_doc(page_map=[item])) == []
