# -*- coding: utf-8 -*-
"""D-122：页面 composition 构图母板字段——Step 3 后仅保留 schema 提示，
不再有 verify 讲法观察（check_composition_fit 已删，12 母板为选型知识）。"""

from _renderer.schema import (
    validate_spec, validate_page_warnings, COMPOSITIONS,
)


def _page(comp, elements):
    p = {"id": "p1", "title": "t", "elements": elements}
    if comp is not None:
        p["composition"] = comp
    return p


class TestCompositionSchema:
    def test_all_twelve_valid(self):
        for c in COMPOSITIONS:
            spec = {"pages": [_page(c, [])]}
            assert validate_spec(spec) == [], c

    def test_unknown_warns_but_no_error(self):
        spec = {"pages": [_page(["bogus"], [])]}
        assert validate_spec(spec) == []
        warns = validate_page_warnings(spec["pages"][0])
        assert any("未知母板" in w for w in warns)

    def test_multi_value_combination_allowed(self):
        spec = {"pages": [_page(["architecture_board", "evidence_ledger"], [])]}
        assert validate_spec(spec) == []

    def test_absent_field_clean(self):
        spec = {"pages": [_page(None, [])]}
        assert validate_spec(spec) == []
