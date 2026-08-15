# -*- coding: utf-8 -*-
"""渲染后密度/可读性检查（A-5，观察模式）。

用 playwright 无头浏览器（系统 Chrome，channel=chrome）渲染 HTML，
检查三类问题：文字溢出/裁切、无意义大空白、对比度不足。

只报告不阻断（观察模式）；playwright 不可用时降级为单条提示，不抛异常。
选型决策：无头浏览器（用户拍板 2026-08-12），见 decisions.md A-5 条目。
"""
import os

# 页内执行的检查脚本：返回 finding 字符串列表（三类：溢出/大空白/低对比度）
_DENSITY_JS = r"""
() => {
  const out = [];
  const els = Array.from(document.querySelectorAll('body *'));

  // 1. 文字溢出（水平）：scrollWidth 超出 clientWidth 且 overflow 未裁剪
  for (const el of els) {
    const t = (el.textContent || '').trim();
    if (!t || el.children.length > 0) continue;
    if (el.scrollWidth > el.clientWidth + 2) {
      out.push('溢出: <' + el.tagName.toLowerCase() + '> 水平溢出 ' +
        (el.scrollWidth - el.clientWidth) + 'px [' + t.slice(0, 30) + ']');
    }
  }

  // 2. 大空白：body 底部最后可见内容之下留白过大
  let maxBottom = 0;
  for (const el of els) {
    const b = el.getBoundingClientRect();
    if (b.height > 0) maxBottom = Math.max(maxBottom, b.bottom);
  }
  const gap = document.body.scrollHeight - maxBottom;
  if (gap > 300) {
    out.push('大空白: 底部 ' + Math.round(gap) + 'px 无内容');
  }

  // 3. 对比度不足：叶子文本 color vs 页面背景亮度（WCAG 简化）
  function lum(c) {
    const m = c.match(/\d+/g);
    if (!m) return 0;
    const [r, g, b] = m.slice(0, 3).map(v => {
      v = v / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function contrast(c1, c2) {
    const a = lum(c1), b = lum(c2);
    const hi = Math.max(a, b), lo = Math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  }
  // 透明/无显式背景 → 回退为浏览器默认白底，避免黑字误报低对比度
  function isTransparent(c) {
    if (!c || c === 'transparent') return true;
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const parts = m[1].split(',').map(s => parseFloat(s.trim()));
      return parts.length === 4 && parts[3] === 0;
    }
    return false;
  }
  // D-120：有效背景 = 向上找最近的非透明背景祖先（按钮/卡片自带底色时
  // 与 body 背景对比是误报，必须与元素自身有效背景比）
  function effectiveBg(el) {
    let n = el;
    while (n && n !== document.body) {
      const c = getComputedStyle(n).backgroundColor;
      if (!isTransparent(c)) return c;
      n = n.parentElement;
    }
    const b = getComputedStyle(document.body).backgroundColor;
    return isTransparent(b) ? 'rgb(255, 255, 255)' : b;
  }
  for (const el of els) {
    const t = (el.textContent || '').trim();
    if (!t || el.children.length > 0) continue;
    const cs = getComputedStyle(el);
    const ratio = contrast(cs.color, effectiveBg(el));
    if (ratio < 3.0 && ratio > 0) {
      out.push('低对比度: [' + t.slice(0, 20) + '] 对比度 ' +
        ratio.toFixed(1) + ':1');
    }
  }

  // 4. 元素重叠（ZSW R6 零穿模/零重叠，D-120）：卡片级 HTML 元素两两边界框相交
  // （父子/包含关系豁免——文字在卡片内是合法层叠；SVG 图内 rect/path 层叠
  // 是图层语义，同样豁免，只查 HTML 卡片级元素）
  const isSvgEl = (el) => el.namespaceURI === 'http://www.w3.org/2000/svg';
  const cards = els.filter(el => {
    if (isSvgEl(el)) return false;
    const r = el.getBoundingClientRect();
    return r.width > 80 && r.height > 40;
  });
  const seenPairs = new Set();
  for (let i = 0; i < cards.length; i++) {
    const el = cards[i];
    const r = el.getBoundingClientRect();
    for (let j = i + 1; j < cards.length; j++) {
      const o = cards[j];
      if (el.contains(o) || o.contains(el)) continue;
      const r2 = o.getBoundingClientRect();
      const ix = Math.min(r.right, r2.right) - Math.max(r.left, r2.left);
      const iy = Math.min(r.bottom, r2.bottom) - Math.max(r.top, r2.top);
      if (ix > 8 && iy > 8) {
        const key = i + '-' + j;
        if (!seenPairs.has(key)) {
          seenPairs.add(key);
          const t1 = (el.textContent || '').trim().slice(0, 12) ||
                     '<' + el.tagName.toLowerCase() + '>';
          const t2 = (o.textContent || '').trim().slice(0, 12) ||
                     '<' + o.tagName.toLowerCase() + '>';
          out.push('重叠: [' + t1 + '] × [' + t2 + '] 相交 ' +
                   Math.round(ix) + 'x' + Math.round(iy) + 'px');
        }
      }
    }
  }

  // 5. 字号层级（ZSW R9 密度 / R13 字号角色，D-120）：
  // 叶子文本 distinct 字号数——1 档 = 无层级对比，>6 档 = 散乱
  const sizes = new Set();
  for (const el of els) {
    if (el.children.length > 0) continue;
    if (!(el.textContent || '').trim()) continue;
    sizes.add(getComputedStyle(el).fontSize);
  }
  if (sizes.size === 1) {
    out.push('字号层级: 全页仅 1 档字号，缺层级对比');
  } else if (sizes.size > 6) {
    out.push('字号层级: ' + sizes.size + ' 档字号，过于散乱');
  }

  return out;
}
"""


def check_density_html(html_path):
    """渲染后密度/可读性检查。返回 finding 字符串列表（不含 [观察] 前缀）。

    playwright/系统 Chrome 不可用时返回单条降级提示，不抛异常。
    """
    if not os.path.exists(html_path):
        return [f"文件不存在: {html_path}"]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["playwright 未安装，跳过密度检查（pip install playwright）"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
            page.wait_for_load_state("networkidle")
            findings = page.evaluate(_DENSITY_JS)
            browser.close()
    except Exception as e:
        return [f"密度检查执行失败: {e}"]

    # D-120：几何/结构类（溢出/重叠/大空白/字号层级）优先于低对比度
    _weight = {"溢出": 0, "重叠": 0, "大空白": 1, "字号层级": 1, "低对比度": 2}
    findings.sort(key=lambda f: next(
        (w for k, w in _weight.items() if f.startswith(k)), 3))
    return findings or []
