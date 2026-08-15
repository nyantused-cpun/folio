# -*- coding: utf-8 -*-
"""D-2 图形白名单检查测试（verify 观察模式）。

覆盖三类检查：shape preset 白名单 / connector kind 合法 / diagram 无图像化。
"""

from _verify import _diagram_shape_whitelist_warnings


def _shape(name, eid="s1"):
    return {"elementId": eid, "elementType": "shape", "shapeName": name}


def _img(eid):
    return {"elementId": eid, "elementType": "image"}


class TestDiagramShapeWhitelist:
    def test_known_preset_passes(self):
        msgs = _diagram_shape_whitelist_warnings(
            [_shape("roundRect"), _shape("flowChartProcess"),
             _shape("pentagon"), _shape("leftRightArrow")], "p1.page")
        assert msgs == []

    def test_unknown_shape_reports(self):
        msgs = _diagram_shape_whitelist_warnings([_shape("freeform")], "p1.page")
        assert len(msgs) == 1
        assert "[观察]" in msgs[0]
        assert "freeform" in msgs[0]

    def test_unregistered_connector_reports(self):
        msgs = _diagram_shape_whitelist_warnings(
            [_shape("bentConnector2")], "p1.page")
        assert len(msgs) == 1
        assert "bentConnector2" in msgs[0]

    def test_known_connector_passes(self):
        msgs = _diagram_shape_whitelist_warnings(
            [_shape("straightConnector1"), _shape("bentConnector3"),
             _shape("curvedConnector3")], "p1.page")
        assert msgs == []

    def test_diagram_image_reports(self):
        msgs = _diagram_shape_whitelist_warnings([_img("dg42-foo")], "p1.page")
        assert len(msgs) == 1
        assert "图像化" in msgs[0]

    def test_logo_image_passes(self):
        msgs = _diagram_shape_whitelist_warnings(
            [_img("logo"), _img("header-logo")], "p1.page")
        assert msgs == []

    def test_empty_shape_name_skipped(self):
        msgs = _diagram_shape_whitelist_warnings([_shape("")], "p1.page")
        assert msgs == []
