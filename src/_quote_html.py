# -*- coding: utf-8 -*-
"""报价 HTML 渲染器 — 调试主输出，用户 Ctrl+P 出 PDF。
输入 QuoteData → 输出单文件 HTML（inline CSS，无外部依赖）。
"""
from datetime import datetime

from _renderer.theme import resolve_theme


def _load_quote_style(style_name="enterprise"):
    """报价配色/字体：消费样式单一源 resolve_theme（§七 2.1）。

    primary/primary_light/accent/header_bg 取自风格 5 基色，font 取 fonts.body；
    total_bg/free_color 是报价专属槽（合计行底色/赠送行红字），不进 theme。
    """
    theme = resolve_theme(style_name)
    base = theme.base
    primary = base.get("primary", "#0B1F3A")
    return {
        "primary": primary,
        "primary_light": base.get("secondary", primary),
        "accent": base.get("accent", "#E05252"),
        "header_bg": base.get("secondary", primary),
        "total_bg": "#FFF2CC",
        "free_color": "#FF0000",
        "font": theme.fonts.get("body", "Microsoft YaHei"),
    }


def render_html(quote_data, output_path=None, style_name="enterprise"):
    """渲染 QuoteData → HTML 字符串。如果指定 output_path 则写文件。"""
    html = _build_html(quote_data, style_name)
    if output_path:
        # §八 3.5：报价 HTML 写入过 output/ 白名单
        from _renderer import _validate_output_path
        _validate_output_path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
    return html


def _build_html(qd, style_name="enterprise"):
    style = _load_quote_style(style_name)
    m = qd.metadata
    client = m.get("client", "")
    contact = m.get("contact", "")
    date = m.get("date", "")
    quote_number = m.get("quote_number", "")
    version = m.get("version", "")
    valid_until = m.get("valid_until", "")
    payment_terms = m.get("payment_terms", "")
    # P2：title 为空时用默认值，支持自定义
    title = m.get("title") or "泛微协同管理平台报价方案"

    parts = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="utf-8">',
        f'<title>{_h(title)}</title>',
        _build_css(style),
        '</head>',
        '<body>',
        '<div class="quote-doc">',
        f'<h1>{_h(title)}</h1>',
    ]

    # 客户信息
    parts.append('<div class="info-grid">')
    parts.append(f'<div><span class="label">客户名称：</span>{_h(client)}</div>')
    parts.append(f'<div><span class="label">联系人：</span>{_h(contact)}</div>')
    parts.append(f'<div><span class="label">报价日期：</span>{_h(str(date))}</div>')
    parts.append('</div>')

    # 元信息
    has_meta = quote_number or version or valid_until or payment_terms
    if has_meta:
        parts.append('<div class="info-grid meta">')
        if quote_number:
            parts.append(f'<div><span class="label">报价编号：</span>{_h(quote_number)}</div>')
        if version:
            parts.append(f'<div><span class="label">版本：</span>{_h(version)}</div>')
        if valid_until:
            parts.append(f'<div><span class="label">有效期至：</span>{_h(str(valid_until))}</div>')
        if payment_terms:
            parts.append(f'<div><span class="label">付款条件：</span>{_h(payment_terms)}</div>')
        parts.append('</div>')

    # 汇总区
    if qd.summary:
        parts.append('<div class="section-title">费用汇总</div>')
        parts.append('<table class="summary-table">')
        parts.append('<tr><th>费用项目</th><th class="amt">金额</th></tr>')
        for label, amt in qd.summary:
            parts.append(f'<tr><td>{_h(label)}</td><td class="amt">{_fmt_money(amt)}</td></tr>')
        parts.append('<tr class="total-row"><td>报价总价（RMB）</td>'
                     f'<td class="amt">{_fmt_money(qd.summary_total)}</td></tr>')
        parts.append('</table>')

    # 各区块
    for sec in qd.sections:
        parts.append(f'<div class="section-title">{_h(sec.title)}</div>')
        parts.append('<table class="data-table">')
        # 表头
        parts.append('<tr>')
        for hdr in sec.headers:
            cls = ' class="amt"' if hdr in ("单价", "金额") else ""
            parts.append(f'<th{cls}>{_h(hdr)}</th>')
        parts.append('</tr>')
        # 数据行
        for it in sec.items:
            cls = ' class="gift"' if it.is_gift else ""
            parts.append(f'<tr{cls}>')
            parts.append(f'<td class="idx">{it.index}</td>')
            parts.append(f'<td>{_h(it.name)}</td>')
            parts.append(f'<td class="desc">{_h(it.description[:60])}{"…" if len(it.description) > 60 else ""}</td>')
            parts.append(f'<td class="amt">{_fmt_money(it.unit_price) if it.unit_price else ""}</td>')
            parts.append(f'<td class="center">{_h(it.discount_display)}</td>')
            parts.append(f'<td class="center">{it.quantity}</td>')
            parts.append(f'<td class="amt">{_fmt_money(it.amount) if not it.is_gift else "¥0"}</td>')
            parts.append('</tr>')
        # 合计行
        parts.append(f'<tr class="total-row"><td colspan="6">{_h(sec.total_label)}</td>'
                     f'<td class="amt">{_fmt_money(sec.total_amount)}</td></tr>')
        parts.append('</table>')

    # 页脚
    parts.append(f'<div class="footer">本报价由系统自动生成 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>')
    parts.append('</div>')
    parts.append('</body>')
    parts.append('</html>')

    return '\n'.join(parts)


def _fmt_money(v):
    if v is None or v == "":
        return ""
    try:
        v = float(v)
    except (ValueError, TypeError):
        return str(v)
    if v == 0:
        return "¥0"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v == int(v):
        return f"{sign}¥{int(v):,}"
    return f"{sign}¥{v:,.2f}"


def _h(s):
    """HTML escape"""
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_css(style):
    primary = style["primary"]
    primary_light = style["primary_light"]
    header_bg = style["header_bg"]
    total_bg = style["total_bg"]
    free_color = style["free_color"]
    font = style["font"]
    return f"""<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "{font}", "Microsoft YaHei", sans-serif; font-size: 12px; color: #333; background: #f5f5f5; }}
.quote-doc {{ max-width: 900px; margin: 20px auto; background: #fff; padding: 32px 40px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
h1 {{ font-size: 20px; color: {primary}; text-align: center; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 2px solid {primary}; }}
.info-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px 24px; margin-bottom: 8px; font-size: 12px; }}
.info-grid.meta {{ margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #e0e0e0; }}
.label {{ font-weight: bold; color: #555; }}
.section-title {{ background: {primary_light}; color: #fff; padding: 8px 12px; font-size: 13px; font-weight: bold; margin: 16px 0 0; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
th {{ background: {header_bg}; color: #fff; font-weight: bold; padding: 6px 8px; border: 1px solid #BFBFBF; text-align: center; font-size: 11px; }}
td {{ padding: 5px 8px; border: 1px solid #BFBFBF; font-size: 11px; vertical-align: top; }}
td.idx {{ text-align: center; width: 40px; }}
td.desc {{ color: #666; font-size: 10px; }}
td.amt {{ text-align: right; font-family: Consolas, monospace; white-space: nowrap; }}
td.center {{ text-align: center; }}
tr.gift td {{ color: {free_color}; }}
tr.total-row {{ background: {total_bg}; font-weight: bold; }}
tr.total-row td {{ border-top: 2px solid {primary_light}; }}
.summary-table {{ margin-bottom: 16px; }}
.summary-table th.amt, .summary-table td.amt {{ width: 140px; }}
.footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid #e0e0e0; text-align: center; font-size: 10px; color: #999; }}
@media print {{
    body {{ background: #fff; }}
    .quote-doc {{ box-shadow: none; margin: 0; padding: 20px; max-width: none; }}
    .section-title {{ break-after: avoid; }}
    table {{ break-inside: avoid; }}
}}
</style>"""
