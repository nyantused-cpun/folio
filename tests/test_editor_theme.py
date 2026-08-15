# -*- coding: utf-8 -*-
"""editor 主题切换器测试（dev_plan_visual_v2 §9.4，T8）。

v2 产物（含 --t- 变量块）：「配色」→「主题」下拉，切换 = 替换 :root 变量块；
老文档：原配色面板不变。editable 纪律：v2 构件渲染期已标，injector 不破坏。
"""
from _renderer.html_editor_injector import inject


def _write_html(tmp_path, style_block=""):
    p = tmp_path / "doc.html"
    p.write_text(f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>t</title>
<style>{style_block}</style></head>
<body><h1>标题</h1><p>正文</p></body></html>""", encoding="utf-8")
    return str(p)


def test_v2_gets_theme_switcher(tmp_path):
    from _renderer.diagram.theme import theme_tokens_css
    path = _write_html(tmp_path, theme_tokens_css("consulting_kpmg"))
    inject(path, inline=True)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    assert 'data-action="theme-panel">主题<' in html
    assert 'data-action="color-panel"' not in html
    assert "window.__V2_THEMES__" in html
    assert "consulting_kpmg" in html and "legacy_bluegreen" in html
    assert "--t-primary:#00338D" in html  # kpmg 变量块注入
    assert "--t-primary:#1B5E8A" in html  # legacy 变量块注入
    # editor.js 主题逻辑随包注入（inline）
    assert "applyTheme" in html and "THEME_KEY" in html
    assert 'data-action="theme-panel"' in html


def test_legacy_doc_keeps_color_panel(tmp_path):
    path = _write_html(tmp_path, "h1{color:red;}")
    inject(path, inline=True)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    assert 'data-action="color-panel">配色<' in html
    assert 'data-action="theme-panel"' not in html
    # editor.js 源码含 __V2_THEMES__ 读取代码，只能断「数据未注入」
    assert "window.__V2_THEMES__ = {" not in html


def test_editable_marks_preserved(tmp_path):
    """v2 构件渲染期 data-editable 标记经 inject 后保留（幂等补标不破坏）。"""
    from _renderer.diagram.theme import theme_tokens_css
    p = tmp_path / "doc.html"
    p.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{theme_tokens_css()}</style></head>
<body><h2 class="action-title" data-editable="true">点亮 74%</h2>
<div class="fc-label" data-editable="true">准入申请</div></body></html>""",
                 encoding="utf-8")
    inject(str(p), inline=True)
    with open(p, encoding="utf-8") as f:
        html = f.read()
    assert html.count('data-editable="true"') == 2  # 不重复不丢失
