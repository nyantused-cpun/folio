# -*- coding: utf-8 -*-
"""Step 5：ui_mock 元素测试（schema/三端渲染/decor 标记）。"""

from _renderer import elements
from _renderer import schema


def _spec(mock):
    return {"pages": [{"id": "p1", "title": "界面示意",
                       "elements": [{"type": "ui_mock", **mock}]}]}


def _valid_mock():
    return {
        "variant": "document",
        "title": "合同管理相对方统一台账",
        "sections": [{"subtitle": "历史合同信息", "bars": [90, 75, 60]}],
        "seal": {"text": "合同专用章", "company": "XX科技有限公司"},
        "caption": "电子签署能力",
    }


def test_normalize_defaults():
    _, n = elements.normalize_element({
        "type": "ui_mock",
        "variant": "console",
        "title": "台账",
        "sections": [{"bars": [80]}],
    })
    assert n["frame"] == "browser"
    assert n["tabs"] == []
    assert n["sections"][0]["bars"] == [80]


def test_schema_valid():
    assert schema.validate_spec(_spec(_valid_mock())) == []


def test_schema_requires_variant_and_title_sections():
    errs = schema.validate_spec(_spec({"variant": "console", "title": "t"}))
    assert any("缺 sections" in e for e in errs)
    errs = schema.validate_spec(_spec({"title": "t", "sections": [{"bars": [50]}]}))
    assert any("variant" in e for e in errs)
    errs = schema.validate_spec(_spec({"variant": "console", "sections": [{"bars": [50]}]}))
    assert any("缺 title" in e for e in errs)


def test_schema_bars_range_and_count():
    errs = schema.validate_spec(_spec({
        "variant": "console", "title": "t", "sections": [{"bars": [5, 150]}],
    }))
    assert any("不在 10-100" in e for e in errs)
    errs = schema.validate_spec(_spec({
        "variant": "console", "title": "t",
        "sections": [{"bars": list(range(9))}],
    }))
    assert any("超过上限 8" in e for e in errs)


def test_schema_seal_only_document():
    errs = schema.validate_spec(_spec({
        "variant": "console", "title": "t",
        "sections": [{"bars": [80]}], "seal": {"text": "章"},
    }))
    assert any("seal 仅 document" in e for e in errs)


def test_render_html_no_svg():
    from _renderer.page_chrome import render_ui_mock
    _, n = elements.normalize_element({"type": "ui_mock", **_valid_mock()})
    html = render_ui_mock(n)
    assert "ui-mock" in html
    assert "ui-mock-seal" in html
    assert "电子签署能力" in html
    assert "<svg" not in html


def test_pptd_emit_native_shapes_and_decor():
    from _renderer.diagram import pptd_emit
    _, n = elements.normalize_element({"type": "ui_mock", **_valid_mock()})
    elems, h = pptd_emit.emit_ui_mock_pptd(n, 80, 130, 1120,
                                           pptd_emit._v2c("consulting_kpmg"))
    assert h > 0
    assert any(e.get("elementType") == "shape" for e in elems)
    assert any(e.get("decor") is True for e in elems if e.get("elementType") == "shape")


def test_docx_degrade_text():
    text = elements.degrade_text(
        "ui_mock",
        {"title": "合同台账", "caption": "电子签署能力"},
        "docx")
    assert text == "[界面示意：合同台账] 电子签署能力"
