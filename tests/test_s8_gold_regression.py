# -*- coding: utf-8 -*-
"""S8 Wave A · C-E1 screenshot + C-G1 raw_html 的 gold 渲染回归。

覆盖：
- gold spec 文件过 schema.validate_element 零错误
- raw_html HTML 渲染后带 data-track="crafted" 边界标记
- screenshot 在图片缺失时降级为占位文本并进 report.warnings
- screenshot 在图片存在时渲染 <img> + 绝对定位标注层
- PPTD/DOCX 端按能力矩阵降级，不静默跳过
"""
import os
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.elements import CAPABILITIES, DEGRADE
from _renderer.schema import validate_element

GOLD_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "gold_specs")


def _load(name):
    path = os.path.join(GOLD_DIR, name)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_spec(tmp_path, elem, client_name="示例"):
    spec = {
        "confirmed": True,
        "client_name": client_name,
        "document": {"title": "gold 回归"},
        "pages": [{"id": "p1", "title": "gold 页", "elements": [elem]}],
    }
    spec_path = os.path.join(str(tmp_path), "spec.yml")
    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True)
    return spec_path


def _render_html(spec_path):
    from _renderer import Renderer
    r = Renderer(spec_path)
    # 渲染输出白名单只允许 output/ 下（同 _tools/gold_regression.py WORK_DIR 先例）
    work_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_s8_test_work")
    os.makedirs(work_dir, exist_ok=True)
    html_path = os.path.join(work_dir, "out.html")
    r.render_html(html_path)
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    os.remove(html_path)
    try:
        os.rmdir(work_dir)
    except OSError:
        pass
    return r, html


def test_all_golds_covered_by_a_harness():
    """守卫：gold 库每个文件必须落在两套渲染回归之一——
    diagram gold（含 diagram_type）由 test_s6_gold_regression.py 覆盖；
    元素级 gold 由本文件覆盖。防新 gold 漏进两套之间无人验收。"""
    element_golds = {
        # S8 Wave A
        "element__screenshot.yml", "element__raw_html.yml",
        # S8 Wave B（C-E2 三件套）
        "element__sla_block.yml", "element__profile_card.yml",
        "element__logo_wall.yml",
    }
    for fn in sorted(os.listdir(GOLD_DIR)):
        if not fn.endswith(".yml"):
            continue
        with open(os.path.join(GOLD_DIR, fn), encoding="utf-8") as f:
            elem = yaml.safe_load(f)
        is_diagram = isinstance(elem, dict) and bool(elem.get("diagram_type"))
        assert is_diagram or fn in element_golds, \
            f"gold {fn} 既非 diagram gold 也未登记进 S8 元素回归"


def test_gold_specs_schema_clean():
    screenshot = _load("element__screenshot.yml")
    raw_html = _load("element__raw_html.yml")
    assert validate_element(screenshot) == []
    assert validate_element(raw_html) == []
    for name in ("element__sla_block.yml", "element__profile_card.yml",
                 "element__logo_wall.yml"):
        assert validate_element(_load(name)) == [], name


def test_raw_html_html_has_crafted_track(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    elem = _load("element__raw_html.yml")
    r, html = _render_html(_write_spec(tmp_path, elem))
    assert 'data-track="crafted"' in html
    assert not r.report.has_issues()


def test_raw_html_docx_and_pptd_degrade(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _renderer import Renderer
    elem = _load("element__raw_html.yml")
    spec_path = _write_spec(tmp_path, elem)
    r = Renderer(spec_path)
    docx_path = os.path.join(SCRIPT_DIR, "output", "通用", "_s8_test_work",
                             "out.docx")
    os.makedirs(os.path.dirname(docx_path), exist_ok=True)
    r.render_docx(docx_path)
    if os.path.exists(docx_path):
        os.remove(docx_path)
    try:
        os.rmdir(os.path.dirname(docx_path))
    except OSError:
        pass
    assert any(d["type"] == "raw_html" for d in r.report.degraded)
    assert CAPABILITIES["raw_html"]["docx"] == DEGRADE
    assert CAPABILITIES["raw_html"]["pptd"] == DEGRADE


def test_screenshot_missing_asset_degrades(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    elem = _load("element__screenshot.yml")
    r, html = _render_html(_write_spec(tmp_path, elem))
    assert "[截图：" in html
    assert any("图片不存在" in w for w in r.report.warnings)


def test_screenshot_with_asset_renders_image_and_annotations(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL 不可用")
    client = "示例"
    refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client, "refs")
    client_dir = os.path.dirname(refs_dir)
    refs_existed = os.path.isdir(refs_dir)
    client_existed = os.path.isdir(client_dir)
    os.makedirs(refs_dir, exist_ok=True)
    img_path = os.path.join(refs_dir, "审批流程.png")
    if not os.path.exists(img_path):
        img = Image.new("RGB", (640, 360), color=(240, 240, 240))
        img.save(img_path)
    try:
        elem = _load("element__screenshot.yml")
        r, html = _render_html(_write_spec(tmp_path, elem, client_name=client))
        assert "<img" in html
        assert "element-screenshot" in html
        assert "发起入口" in html
        assert "审批节点" in html
        assert not r.report.has_issues()
    finally:
        # 测试夹具全量清退，不在客户库留 示例/ 污染（C5 客户计数契约）
        if os.path.exists(img_path):
            os.remove(img_path)
        if not refs_existed and os.path.isdir(refs_dir):
            os.rmdir(refs_dir)
        if not client_existed and os.path.isdir(client_dir):
            os.rmdir(client_dir)


def test_screenshot_pptd_render_or_degrade(monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _pptd_gen import build_deck
    from _renderer.theme import resolve_theme
    elem = _load("element__screenshot.yml")
    spec = {
        "confirmed": True,
        "client_name": "示例",
        "document": {"title": "gold"},
        "pages": [{"id": "p1", "title": "gold 页", "elements": [elem]}],
    }
    style = resolve_theme("consulting_kpmg")
    files, _ = build_deck(spec, os.path.join(SCRIPT_DIR, "spec.yml"), style,
                          "gold", os.path.join(SCRIPT_DIR, "output", "通用",
                                               "_s8_probe"),
                          client_name="示例")
    page = files["pages/02_p1.page"]
    # 图片缺失 → 降级文本；能跑通即证明分发路径接入
    assert "[截图" in page or "image" in page


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
