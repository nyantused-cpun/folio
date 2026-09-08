# -*- coding: utf-8 -*-
"""Step 6：pptd bbox 机检（只判超出版心，warning 不阻断）。"""

import os

import yaml

from _layout_lint import check_pptd_bbox_margin


def _write_deck(deck_dir, shapes):
    os.makedirs(os.path.join(deck_dir, "pages"), exist_ok=True)
    main = {
        "version": 1,
        "size": [1280, 720],
        "pages": ["pages/p1.page"],
        "theme": {"textStyles": {}},
    }
    with open(os.path.join(deck_dir, "main.pptd"), "w", encoding="utf-8") as f:
        yaml.safe_dump(main, f, allow_unicode=True, sort_keys=False)
    page = {
        "pageType": "content",
        "elements": [{
            "elementId": "shape-1", "elementType": "shape",
            "shapeName": "rect", "bounds": bounds,
        } for bounds in shapes],
    }
    with open(os.path.join(deck_dir, "pages", "p1.page"), "w", encoding="utf-8") as f:
        yaml.safe_dump(page, f, allow_unicode=True, sort_keys=False)


def test_outside_margin_hits_warning(tmp_path):
    deck = str(tmp_path / "deck")
    _write_deck(deck, [[50, 100, 200, 50], [100, 200, 300, 50]])
    issues = check_pptd_bbox_margin(deck)
    assert any(i.kind == "bbox_margin" and i.severity == "warning"
               and "shape-1" in i.element_id for i in issues)
    assert not any("shape-2" in i.element_id for i in issues)


def test_inside_margin_no_false_positive(tmp_path):
    deck = str(tmp_path / "deck")
    _write_deck(deck, [[100, 200, 300, 50], [90, 130, 1000, 400]])
    assert check_pptd_bbox_margin(deck) == []


def test_cover_page_skipped(tmp_path):
    deck = str(tmp_path / "deck")
    os.makedirs(os.path.join(deck, "pages"), exist_ok=True)
    main = {"version": 1, "size": [1280, 720], "pages": ["pages/p1.page"]}
    with open(os.path.join(deck, "main.pptd"), "w", encoding="utf-8") as f:
        yaml.safe_dump(main, f)
    page = {"pageType": "cover", "elements": [
        {"elementId": "bg", "elementType": "shape", "bounds": [0, 0, 1280, 720]},
    ]}
    with open(os.path.join(deck, "pages", "p1.page"), "w", encoding="utf-8") as f:
        yaml.safe_dump(page, f)
    assert check_pptd_bbox_margin(deck) == []
