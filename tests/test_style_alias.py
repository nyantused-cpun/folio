# -*- coding: utf-8 -*-
"""Step 3：style-check 别名 → verify --only style 作用域（不跑 Playwright）。"""

from _verify import verify_style_scan


def test_style_scan_clean_ok(tmp_path):
    p = tmp_path / "clean.txt"
    p.write_text("这是一段正常的售前方案文字。", encoding="utf-8")
    ok, msg = verify_style_scan(str(p))
    assert ok
    assert "OK" in msg


def test_style_scan_flags_ai_pattern_as_warning(tmp_path):
    p = tmp_path / "ai.txt"
    p.write_text("综上所述，我们全面提升效率。", encoding="utf-8")
    ok, msg = verify_style_scan(str(p))
    assert ok  # 观察模式不阻断
    assert "style" in msg


def test_style_scan_flags_placeholder(tmp_path):
    p = tmp_path / "ph.txt"
    p.write_text("正文 Lorem ipsum 占位。", encoding="utf-8")
    ok, msg = verify_style_scan(str(p))
    assert ok
    assert "占位符残留" in msg


def test_style_scan_missing_file_false():
    ok, msg = verify_style_scan("不存在的文件.txt")
    assert not ok
    assert "文件不存在" in msg
