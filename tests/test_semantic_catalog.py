# -*- coding: utf-8 -*-
"""能力目录 schema 校验（子计划1）。"""
from _semantic_catalog import (
    _validate_link_type, _validate_module,
    load_catalog, check_catalog,
)

VALID_MODULE = {
    "module_id": "module_expense",
    "name": "费用报销模块",
    "app_domain": "企业管理平台",
    "level": "APP",
    "description": "报销单、费用科目、成本中心、标准校验",
    "functions": [
        {"function_id": "fn_expense_form", "name": "网上报销流程", "trigger": True, "required": True}
    ],
    "requires": ["module_budget"],
}

VALID_LINK = {
    "name": "REQUIRES",
    "domain": "CapabilityModule",
    "range": "CapabilityModule",
    "cardinality": "MANY_TO_MANY",
    "inverse": "REQUIRED_BY",
    "transitive": True,
    "functional": False,
}


class TestLinkType:
    def test_requires_link_valid(self):
        assert _validate_link_type(VALID_LINK) == []

    def test_missing_inverse_is_error(self):
        link = dict(VALID_LINK)
        link.pop("inverse")
        errors = _validate_link_type(link)
        assert any("inverse" in e for e in errors)

    def test_unknown_cardinality_is_error(self):
        link = dict(VALID_LINK)
        link["cardinality"] = "TOO_MANY"
        errors = _validate_link_type(link)
        assert any("cardinality" in e for e in errors)


class TestModule:
    def test_valid_module_passes(self):
        assert _validate_module(VALID_MODULE) == []

    def test_module_requires_own_id(self):
        mod = dict(VALID_MODULE)
        mod.pop("module_id")
        errors = _validate_module(mod)
        assert any("module_id" in e for e in errors)

    def test_level_must_be_enum(self):
        mod = dict(VALID_MODULE)
        mod["level"] = "SOMETHING_ELSE"
        errors = _validate_module(mod)
        assert any("level" in e for e in errors)


class TestCatalogLoad:
    def test_missing_file_returns_error(self):
        result = load_catalog("/nonexistent/catalog.json")
        assert "error" in result

    def test_check_valid_catalog(self, tmp_path):
        import json
        catalog = {
            "schema_version": "1",
            "object_types": [],
            "link_types": [VALID_LINK],
            "modules": [VALID_MODULE],
        }
        p = tmp_path / "cat.json"
        p.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        result = check_catalog(str(p))
        assert result["valid"] is True
        assert result["errors"] == []
