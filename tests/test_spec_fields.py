# -*- coding: utf-8 -*-
"""A-1 spec schema 三字段扩展测试（container / simulation / scenario:training）。"""

from _renderer import schema


def _spec(**extra):
    """构造最小合法 spec（空 pages），叠加文档级字段。"""
    s = {"pages": []}
    s.update(extra)
    return s


# ---------------------------------------------------------------------------
# container
# ---------------------------------------------------------------------------
class TestContainer:
    def test_all_legal_values(self):
        for v in schema.CONTAINERS:
            assert schema.validate_spec(_spec(container=v)) == [], \
                f"container={v} 应通过校验"

    def test_illegal_value_reports_error(self):
        errors = schema.validate_spec(_spec(container="flipbook"))
        assert errors, "container=flipbook 应报错"
        assert any("container" in e and "flipbook" in e for e in errors)
        assert any("/".join(schema.CONTAINERS) in e for e in errors), \
            "报错信息应含合法值列表"

    def test_absent_no_error(self):
        assert schema.validate_spec(_spec()) == []


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------
class TestSimulation:
    def test_all_legal_values(self):
        for v in schema.SIMULATIONS:
            assert schema.validate_spec(_spec(simulation=v)) == [], \
                f"simulation={v} 应通过校验"

    def test_illegal_value_reports_error(self):
        errors = schema.validate_spec(_spec(simulation="3d"))
        assert errors, "simulation=3d 应报错"
        assert any("simulation" in e and "3d" in e for e in errors)
        assert any("/".join(schema.SIMULATIONS) in e for e in errors), \
            "报错信息应含合法值列表"

    def test_absent_no_error(self):
        assert schema.validate_spec(_spec()) == []


# ---------------------------------------------------------------------------
# scenario: training
# ---------------------------------------------------------------------------
class TestScenarioTraining:
    def test_training_legal(self):
        assert schema.validate_spec(_spec(scenario="training")) == []

    def test_typo_reports_error(self):
        errors = schema.validate_spec(_spec(scenario="trainig"))
        assert errors, "scenario=trainig 应报错"
        assert any("scenario" in e and "trainig" in e for e in errors)
        assert any("training" in e for e in errors), \
            "报错信息应含合法值 training"

    def test_three_legal_scenarios(self):
        for v in ("report", "product_intro", "training"):
            assert schema.validate_spec(_spec(scenario=v)) == []


# ---------------------------------------------------------------------------
# A-2 type_roles / font_role / 散值统计
# ---------------------------------------------------------------------------
class TestTypeRoles:
    def test_legal_role(self):
        assert schema.validate_spec(_spec(type_roles={"title": 40})) == []

    def test_legal_role_dict_form(self):
        assert schema.validate_spec(
            _spec(type_roles={"title": {"size": 40}})) == []

    def test_unknown_role_reports_error(self):
        errors = schema.validate_spec(_spec(type_roles={"heading": 40}))
        assert errors and any("type_roles" in e and "heading" in e for e in errors)

    def test_non_numeric_size_reports_error(self):
        errors = schema.validate_spec(_spec(type_roles={"title": "大"}))
        assert errors and any("size" in e for e in errors)

    def test_absent_no_error(self):
        assert schema.validate_spec(_spec()) == []


class TestFontRole:
    def _spec_with_elem(self, elem):
        return {"pages": [{"elements": [elem]}]}

    def test_legal_font_role(self):
        assert schema.validate_spec(
            self._spec_with_elem({"type": "text", "text": "x", "font_role": "title"})) == []

    def test_unknown_font_role_reports_error(self):
        errors = schema.validate_spec(
            self._spec_with_elem({"type": "text", "text": "x", "font_role": "banner"}))
        assert errors and any("font_role" in e and "banner" in e for e in errors)


class TestTypeRoleConsistency:
    def _spec_with_sizes(self, sizes):
        elems = [{"type": "text", "text": "x", "fontSize": s} for s in sizes]
        return {"pages": [{"elements": elems}]}

    def test_three_same_sizes_trigger(self):
        from _verify import check_type_role_consistency
        msgs = check_type_role_consistency(self._spec_with_sizes([22, 22, 22]))
        assert len(msgs) == 1
        assert "[观察]" in msgs[0] and "22" in msgs[0]

    def test_two_same_sizes_not_trigger(self):
        from _verify import check_type_role_consistency
        assert check_type_role_consistency(self._spec_with_sizes([22, 22])) == []

    def test_no_fontsize_not_trigger(self):
        from _verify import check_type_role_consistency
        assert check_type_role_consistency(_spec()) == []
