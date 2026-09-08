# -*- coding: utf-8 -*-
"""Step 1：type_roles/font_role/simulation/旧 layout 聚合 warn + exit 0 不变。"""

from _renderer.schema import (
    LEGACY_LAYOUTS,
    validate_deprecated_field_warnings,
    validate_spec,
)


def test_deprecated_fields_aggregate_warning():
    spec = {
        "type_roles": {"title": 40},
        "simulation": "static",
        "pages": [{"elements": [
            {"type": "text", "text": "x", "font_role": "title"},
        ]}],
    }
    # 不再进 errors，退出语义不受影响
    assert validate_spec(spec) == []
    warns = validate_deprecated_field_warnings(spec)
    assert len(warns) == 1
    msg = warns[0]
    assert "type_roles" in msg and "simulation" in msg and "font_role" in msg
    assert "已废弃" in msg


def test_legacy_layout_warning():
    for layout in LEGACY_LAYOUTS:
        spec = {"pages": [{"layout": layout, "elements": []}]}
        assert validate_spec(spec) == []
        warns = validate_deprecated_field_warnings(spec)
        assert any("旧 layout 值" in w and layout in w for w in warns), layout


def test_clean_spec_no_deprecated_warning():
    assert validate_spec({"pages": []}) == []
    assert validate_deprecated_field_warnings({"pages": []}) == []


def test_fields_and_legacy_layout_produce_separate_warnings():
    spec = {
        "simulation": "none",
        "pages": [{"layout": "summary", "elements": []}],
    }
    warns = validate_deprecated_field_warnings(spec)
    assert len(warns) == 2
    assert any("simulation" in w for w in warns)
    assert any("旧 layout 值" in w and "summary" in w for w in warns)
