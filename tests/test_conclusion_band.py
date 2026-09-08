# -*- coding: utf-8 -*-
"""Step 5：conclusion_band 元素测试（schema/红字解析/三端渲染）。"""

import os
import shutil

import pytest

from _renderer import elements
from _renderer import schema


@pytest.fixture
def work_dir():
    path = os.path.join("output", "通用", "_test_conclusion_band")
    os.makedirs(path, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _spec(band):
    return {"pages": [{"id": "p1", "title": "结论",
                       "elements": [{"type": "conclusion_band", **band}]}]}


def test_normalize_default_tone():
    _, n = elements.normalize_element({
        "type": "conclusion_band", "text": "结论文本",
    })
    assert n["tone"] == "primary"


def test_schema_valid():
    assert schema.validate_spec(_spec({"text": "目前北美、南美已经点亮"})) == []


def test_schema_required_and_limits():
    errs = schema.validate_spec(_spec({}))
    assert any("缺 text" in e for e in errs)
    errs = schema.validate_spec(_spec({"text": "长" * 81, "tone": "primary"}))
    assert any("超过上限 80" in e for e in errs)


def test_schema_tone_enum():
    errs = schema.validate_spec(_spec({"text": "t", "tone": "blue"}))
    assert any("tone 非法值" in e for e in errs)


def test_render_html_red_marker():
    from _renderer.page_chrome import render_conclusion_band
    _, n = elements.normalize_element({
        "type": "conclusion_band",
        "text": "已点亮 **北美**，继续推进",
        "tone": "accent",
    })
    html = render_conclusion_band(n)
    assert "conclusion-band" in html
    assert "tone-accent" in html
    assert '<strong class="cb-red">北美</strong>' in html


def test_pptd_emit_band():
    from _renderer.diagram import pptd_emit
    _, n = elements.normalize_element({
        "type": "conclusion_band",
        "text": "目前北美、南美已经点亮",
        "tone": "primary",
    })
    elems, h = pptd_emit.emit_conclusion_band_pptd(
        n, 80, 130, 1120, pptd_emit._v2c("consulting_kpmg"))
    assert h > 0
    assert any(e.get("elementType") == "shape" for e in elems)


def test_docx_paragraph_shaded(tmp_path, work_dir):
    """DOCX 端整段底纹段落（python-docx 验证文本 + w:shd）。"""
    import os
    import yaml
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    from _renderer import Renderer
    spec_path = tmp_path / "spec.yml"
    spec = {
        "confirmed": True,
        "document": {"title": "结论页"},
        "pages": [{"id": "p1", "title": "结论", "elements": [
            {"type": "conclusion_band", "text": "目前北美、南美已经点亮"}],
        }],
    }
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True),
                         encoding="utf-8")
    r = Renderer(str(spec_path))
    out = os.path.join(str(work_dir), "conclusion.docx")
    r.render_docx(out)
    from docx import Document
    doc = Document(out)
    texts = [p.text for p in doc.paragraphs]
    assert "目前北美、南美已经点亮" in texts
    assert any(p._p.xpath(".//w:shd") for p in doc.paragraphs
               if p.text == "目前北美、南美已经点亮")
