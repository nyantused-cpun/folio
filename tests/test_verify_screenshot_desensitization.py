# -*- coding: utf-8 -*-
"""C-E5：截图/图片类元素脱敏提醒（warn 级，不阻断）。"""
import pytest

import _verify


def _html(content):
    # 保证 >500 bytes 且通过 verify_html 基础检查
    padding = "<!-- " + "x" * 500 + " -->"
    return (
        f"<!DOCTYPE html><html><head><style></style></head><body>{content}</body></html>"
        + padding
    )


def test_html_with_img_warns(tmp_path):
    path = tmp_path / "with_img.html"
    path.write_text(_html('<img src="shot.png" alt="截图">'), encoding="utf-8")
    ok, msg = _verify.verify_html(str(path))
    assert ok is True
    assert "确认截图已脱敏" in msg


def test_html_without_img_clean(tmp_path):
    path = tmp_path / "no_img.html"
    path.write_text(_html('<div>纯文字</div>'), encoding="utf-8")
    ok, msg = _verify.verify_html(str(path))
    assert ok is True
    assert "确认截图已脱敏" not in msg


def test_spec_with_image_element_warns(tmp_path):
    """image 是 schema 已注册类型；验证 warn 在 verify_yaml 消息中可见。"""
    path = tmp_path / "with_image.yml"
    path.write_text(
        "document:\n  title: t\npages:\n"
        "  - layout: P01\n    elements:\n"
        "      - type: hero\n        title: 标题\n"
        "      - type: image\n        src: a.png\n",
        encoding="utf-8",
    )
    ok, msg = _verify.verify_yaml(str(path))
    # 截图提醒自身是 warn 级，不阻断；整体验证可能因其他原因 FAIL，但消息里必须带提醒
    assert "确认截图已脱敏" in msg


def test_spec_without_image_element_clean(tmp_path):
    path = tmp_path / "clean.yml"
    path.write_text(
        "document:\n  title: t\npages:\n"
        "  - layout: P01\n    elements:\n"
        "      - type: hero\n        title: 标题\n",
        encoding="utf-8",
    )
    ok, msg = _verify.verify_yaml(str(path))
    assert ok is True
    assert "确认截图已脱敏" not in msg


@pytest.mark.parametrize("etype", ["screenshot", "image", "img"])
def test_warn_helper_triggers_on_all_image_types(etype):
    assert _verify._warn_screenshot_desensitization(
        spec={"pages": [{"elements": [{"type": etype}]}]}
    )


def test_warn_helper_html_and_spec_non_trigger():
    assert not _verify._warn_screenshot_desensitization(html_text="<div></div>")
    assert not _verify._warn_screenshot_desensitization(
        spec={"pages": [{"elements": [{"type": "text"}]}]}
    )
