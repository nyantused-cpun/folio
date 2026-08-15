# -*- coding: utf-8 -*-
"""HTML 可编辑能力注入器（D-091，dev plan §7）。

给生成的方案 HTML 注入：
1. 工具条 DOM（编辑切换 / 配色面板 / 导出 / 重置）
2. editor.js + editor.css（默认外部引用 output 同级 _assets/；--inline-editor 内联）
3. 给基础元素补 data-editable 标记（diagram 元素渲染时已自带）

可编辑范围：文字内容（data-editable 元素）+ 配色（editor.js 动态样式表）。
不可编辑：工具条本身、script/style、SVG 图形结构（图内文字 P0 不开放）。
"""

import os
import re

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

_TOOLBAR_HTML = """
<div id="__editor_toolbar">
  <button type="button" data-action="toggle-edit">编辑</button>
  {panel_button}
  <button type="button" data-action="export">导出 HTML</button>
  <button type="button" data-action="reset">重置</button>
</div>
<div id="__editor_color_panel"></div>
"""

_PANEL_BUTTON_COLOR = '<button type="button" data-action="color-panel">配色</button>'
_PANEL_BUTTON_THEME = '<button type="button" data-action="theme-panel">主题</button>'


def _v2_themes_script():
    """v2 主题切换数据（§9.4）：两套主题 tokens 的 :root 变量块注入页面，
    editor.js 切换 = 替换动态样式表内容。非 v2 产物不注入（配色面板不变）。"""
    import json
    from _renderer.diagram.theme import THEMES, theme_tokens_css, bridge_css
    data = {name: theme_tokens_css(name) + "\n" + bridge_css(name)
            for name in THEMES}
    return ("<script>window.__V2_THEMES__ = "
            + json.dumps(data, ensure_ascii=False) + ";</script>")

# 需要补 data-editable 的标签对（渲染器基础产物；diagram 已自带的不重复加）
_EDITABLE_TAGS = [
    (re.compile(r"<h1>(?!\s*<)"), "<h1>"),
    (re.compile(r"<h2>(?!\s*<)"), "<h2>"),
    (re.compile(r'<p class="subtitle">'), '<p class="subtitle">'),
    (re.compile(r'<p class="author">'), '<p class="author">'),
    (re.compile(r'<div class="bullet">'), '<div class="bullet">'),
    (re.compile(r'<div class="card-title">'), '<div class="card-title">'),
    (re.compile(r'<div class="card-body">'), '<div class="card-body">'),
    (re.compile(r'<div class="card-highlight">'), '<div class="card-highlight">'),
    (re.compile(r'<div class="pq-content">'), '<div class="pq-content">'),
    (re.compile(r'<div class="pq-cite">'), '<div class="pq-cite">'),
    (re.compile(r'<div class="phase-label">'), '<div class="phase-label">'),
    (re.compile(r'<div class="phase-goal">'), '<div class="phase-goal">'),
    (re.compile(r"<td>"), "<td>"),
    (re.compile(r"<p>(?!\s*<)"), "<p>"),
]


def _read_asset(name):
    with open(os.path.join(_ASSETS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def _mark_editable(html):
    """给基础元素补 data-editable="true"（幂等：已有标记的跳过）。"""
    for pattern, tag in _EDITABLE_TAGS:
        def _sub(m, tag=tag):
            seg = m.group(0)
            if "data-editable" in seg:
                return seg
            return seg[:-1] + ' data-editable="true">'
        html = pattern.sub(_sub, html)
    return html


def inject(html_path, inline=False):
    """对已生成的 HTML 文件注入可编辑能力。返回注入后的文件路径。

    inline=False：复制 editor.js/css 到 HTML 同级 _assets/，外部引用
    inline=True：样式与脚本内联进 HTML（单文件无依赖）
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = _mark_editable(html)

    # v2 产物（含 --t- 主题变量块）：「配色」按钮换「主题」切换器（§9.4）；
    # 老文档保持原配色面板。v2 构件文字节点渲染期已标 data-editable（§7），
    # _EDITABLE_TAGS 无需补标。
    is_v2 = "--t-primary" in html
    toolbar = _TOOLBAR_HTML.replace(
        "{panel_button}",
        _PANEL_BUTTON_THEME if is_v2 else _PANEL_BUTTON_COLOR)

    if inline:
        head_inject = (f"<style>\n{_read_asset('editor.css')}\n</style>\n"
                       f"<script>\n{_read_asset('editor.js')}\n</script>")
    else:
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(html_path)), "_assets")
        os.makedirs(assets_dir, exist_ok=True)
        for name in ("editor.js", "editor.css"):
            with open(os.path.join(assets_dir, name), "w", encoding="utf-8") as f:
                f.write(_read_asset(name))
        head_inject = ('<link rel="stylesheet" href="_assets/editor.css">\n'
                       '<script src="_assets/editor.js" defer></script>')
    if is_v2:
        head_inject = _v2_themes_script() + "\n" + head_inject

    if "</head>" in html:
        html = html.replace("</head>", head_inject + "\n</head>", 1)
    if "<body>" in html:
        html = html.replace("<body>", '<body data-edit-mode="preview">' + toolbar, 1)
    elif "<body " in html:
        html = re.sub(r"<body([^>]*)>",
                      r'<body\1 data-edit-mode="preview">' + toolbar, html, count=1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path
