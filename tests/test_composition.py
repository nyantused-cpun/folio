# -*- coding: utf-8 -*-
"""D-122：页面 composition 构图母板字段——schema 枚举校验 + verify 讲法观察。"""

from _renderer.schema import validate_spec, COMPOSITIONS
from _verify import check_composition_fit


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

    def test_unknown_rejected(self):
        spec = {"pages": [_page(["bogus"], [])]}
        errs = validate_spec(spec)
        assert len(errs) == 1 and "未知母板" in errs[0]

    def test_multi_value_combination_allowed(self):
        spec = {"pages": [_page(["architecture_board", "evidence_ledger"], [])]}
        assert validate_spec(spec) == []

    def test_absent_field_clean(self):
        spec = {"pages": [_page(None, [])]}
        assert validate_spec(spec) == []


class TestCompositionFit:
    def test_data_narrative_without_data_flagged(self):
        spec = {"pages": [_page(["data_narrative"],
                                [{"type": "bullets", "items": ["x"]}])]}
        msgs = check_composition_fit(spec)
        assert len(msgs) == 1 and "data_narrative" in msgs[0]

    def test_data_narrative_with_kpi_ok(self):
        spec = {"pages": [_page(["data_narrative"],
                                [{"type": "kpi_cards",
                                  "cards": [{"label": "x", "to": "1"}]}])]}
        assert check_composition_fit(spec) == []

    def test_architecture_board_needs_arch_diagram(self):
        spec = {"pages": [_page(["architecture_board"],
                                [{"type": "diagram", "diagram_type": "architecture",
                                  "subtype": "4a"}])]}
        assert check_composition_fit(spec) == []
        bad = {"pages": [_page(["architecture_board"],
                               [{"type": "diagram", "diagram_type": "flow",
                                 "subtype": "sequence"}])]}
        msgs = check_composition_fit(bad)
        assert len(msgs) == 1 and "architecture_board" in msgs[0]

    def test_invalid_enum_not_flagged_by_fit(self):
        """非法枚举由 schema error 负责，讲法观察不重复。"""
        spec = {"pages": [_page(["bogus"], [])]}
        assert check_composition_fit(spec) == []
