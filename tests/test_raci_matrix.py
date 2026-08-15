# -*- coding: utf-8 -*-
"""B-5 角色责任矩阵（raci_matrix）测试。"""

from _renderer import elements
from _renderer import schema


def _spec(roles, tasks):
    return {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "raci_matrix", "roles": roles, "tasks": tasks}]}]}


def test_normalize():
    _, n = elements.normalize_element({
        "type": "raci_matrix",
        "roles": ["甲方", "我方"],
        "tasks": [{"task": "需求调研", "cells": {"甲方": "A", "我方": "R"}}],
    })
    assert n["roles"] == ["甲方", "我方"]
    assert n["tasks"][0]["task"] == "需求调研"
    assert n["tasks"][0]["cells"]["甲方"] == "A"


def test_schema_valid():
    assert schema.validate_spec(_spec(
        ["甲方", "我方"],
        [{"task": "需求调研", "cells": {"甲方": "A", "我方": "R"}}]
    )) == []


def test_schema_missing_roles():
    errs = schema.validate_spec(_spec([], [{"task": "t", "cells": {}}]))
    assert any("缺 roles" in e for e in errs)


def test_schema_missing_tasks():
    errs = schema.validate_spec(_spec(["甲方"], []))
    assert any("缺 tasks" in e for e in errs)


def test_schema_illegal_cell_value():
    errs = schema.validate_spec(_spec(
        ["甲方"], [{"task": "t", "cells": {"甲方": "X"}}]))
    assert any("非法值" in e for e in errs)


def test_schema_cell_role_not_declared():
    errs = schema.validate_spec(_spec(
        ["甲方"], [{"task": "t", "cells": {"乙方": "R"}}]))
    assert any("不在 roles" in e for e in errs)


def test_render_html():
    from _renderer.page_chrome import render_raci_matrix
    _, n = elements.normalize_element({
        "type": "raci_matrix",
        "roles": ["甲方", "我方"],
        "tasks": [{"task": "需求调研", "cells": {"甲方": "A", "我方": "R"}}],
    })
    html = render_raci_matrix(n)
    assert "raci-table" in html
    assert "需求调研" in html
    assert "raci-A" in html
