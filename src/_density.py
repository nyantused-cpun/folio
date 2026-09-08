# -*- coding: utf-8 -*-
"""渲染后密度/可读性检查（A-5，观察模式 + 表达模式硬事实阻断）。升级条件: 基线页数值快照积累足量 → 定阈值分档转 warn（盘点#12；标准页误报率数据在案后逐维升 warn，盘点#2）
用 playwright 无头浏览器（系统 Chrome，channel=chrome）渲染 HTML，
检查三类问题：文字溢出/裁切、无意义大空白、对比度不足、元素重叠、字号层级。

表达模式（crafted）页：带 ``data-track="crafted"`` 边界标记的容器被视为定制页，
其美学硬事实（字号底线/溢出/重叠/对比度）已升为阻断级；信息密度与观感
维度保持观察。

视口策略：
- ``gate="verify"``（默认）：单视口 1280×720，与现状兼容。
- ``gate="deliver"``：全视口集（桌面 1280×720 + 1920×1080），逐视口截图存档
  到 ``_tmp/density_shots/YYYYMMDD/``。

playwright/系统 Chrome 不可用时降级为单条提示，不抛异常。
选型决策：无头浏览器（用户拍板 2026-08-12），见 decisions.md A-5 条目。
"""
import os
from datetime import datetime

from _paths import SCRIPT_DIR


# 视口集：至少桌面 1280×720 + 一个更大桌面视口（C-F2）
_VIEWPORTS = [
    {"width": 1280, "height": 720, "name": "desktop_hd"},
    {"width": 1920, "height": 1080, "name": "desktop_fhd"},
]

# 字号底线（px）：crafted 页硬事实阻断阈值（C-G1）
_CRAFTED_MIN_FONT_SIZE = 12

# 阻断级 finding 类别（crafted 页）
_CRAFTED_BLOCK_CATEGORIES = ("字号底线", "溢出", "重叠", "低对比度")

# 观察级 finding 类别（标准页/ crafted 页观感维度）升级条件: 基线页数值快照积累足量 → 定阈值分档转 warn（盘点#12）
_OBSERVATION_CATEGORIES = ("大空白", "字号层级")


class DensityResult(list):
    """密度检查结果容器。

    行为上仍是一个 finding 字符串列表，保证既有调用方（遍历/切片/len）
    向后兼容；同时携带结构化字段供新消费方区分 warn/FAIL 级。
    """

    def __init__(self, findings, level="ok", blocked=False,
                 blocked_findings=None, screenshots=None, metrics=None):
        super().__init__(findings)
        self.level = level
        self.blocked = blocked
        self.blocked_findings = blocked_findings or []
        self.screenshots = screenshots or []
        self.metrics = metrics or {}


# 页内执行的检查脚本：返回 {is_crafted, findings, metrics}
_DENSITY_JS = r"""
() => {
  const out = [];
  const metrics = {};
  const els = Array.from(document.querySelectorAll('body *'));
  const craftedRoot = document.querySelector('[data-track="crafted"]');
  const isCrafted = !!craftedRoot;

  // ---------- 1. 文字溢出（水平） ----------
  for (const el of els) {
    const t = (el.textContent || '').trim();
    if (!t || el.children.length > 0) continue;
    if (el.scrollWidth > el.clientWidth + 2) {
      out.push('溢出: <' + el.tagName.toLowerCase() + '> 水平溢出 ' +
        (el.scrollWidth - el.clientWidth) + 'px [' + t.slice(0, 30) + ']');
    }
  }

  // ---------- 2. 大空白 ----------
  let maxBottom = 0;
  for (const el of els) {
    const b = el.getBoundingClientRect();
    if (b.height > 0) maxBottom = Math.max(maxBottom, b.bottom);
  }
  const bodyRect = document.body.getBoundingClientRect();
  const gap = document.body.scrollHeight - maxBottom;
  if (gap > 300) {
    out.push('大空白: 底部 ' + Math.round(gap) + 'px 无内容');
  }

  // ---------- 3. 对比度 ----------
  // 标准页阈值 3.0（WCAG 大文字/AA 宽松），crafted 页硬事实阈值 4.5（C-G1）
  const contrastThreshold = isCrafted ? 4.5 : 3.0;
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
  function isTransparent(c) {
    if (!c || c === 'transparent') return true;
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const parts = m[1].split(',').map(s => parseFloat(s.trim()));
      return parts.length === 4 && parts[3] === 0;
    }
    return false;
  }
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
    if (ratio < contrastThreshold && ratio > 0) {
      out.push('低对比度: [' + t.slice(0, 20) + '] 对比度 ' +
        ratio.toFixed(1) + ':1');
    }
  }

  // ---------- 4. 元素重叠 ----------
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

  // ---------- 5. 字号层级 ----------
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

  // ---------- 6. crafted 页硬事实：字号底线（C-G1） ----------
  if (isCrafted) {
    const minSizePx = 12;
    const tooSmall = [];
    for (const el of els) {
      const t = (el.textContent || '').trim();
      if (!t || el.children.length > 0) continue;
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size && size < minSizePx) {
        tooSmall.push('字号底线: <' + el.tagName.toLowerCase() + '> ' +
          size.toFixed(1) + 'px < ' + minSizePx + 'px [' + t.slice(0, 20) + ']');
      }
    }
    // 合并避免刷屏：同类最多报 5 条
    out.push(...tooSmall.slice(0, 5));
  }

  // ---------- 7. visual_intent 指标集（C-G3，观察级） ---------- 升级条件: 基线页数值快照积累足量 → 定阈值分档转 warn（盘点#12）
  // 7.1 留白率：1 - 可见元素 bbox 并集近似 / body 面积
  let coveredArea = 0;
  const seenBoxes = [];
  for (const el of cards) {
    const r = el.getBoundingClientRect();
    const area = r.width * r.height;
    if (area > 0) coveredArea += area;
  }
  const bodyArea = Math.max(bodyRect.width * bodyRect.height, 1);
  metrics.whitespace_ratio = Math.max(0, 1 - coveredArea / bodyArea);

  // 7.2 层级梯度：distinct 字号数 + 字号分布变异系数
  const sizeVals = [];
  for (const el of els) {
    if (el.children.length > 0) continue;
    if (!(el.textContent || '').trim()) continue;
    const v = parseFloat(getComputedStyle(el).fontSize);
    if (v) sizeVals.push(v);
  }
  if (sizeVals.length) {
    const mean = sizeVals.reduce((a, b) => a + b, 0) / sizeVals.length;
    const variance = sizeVals.reduce((a, b) => a + Math.pow(b - mean, 2), 0)
                     / sizeVals.length;
    metrics.hierarchy_gradient = {
      distinct_sizes: sizes.size,
      cv: mean ? Math.sqrt(variance) / mean : 0
    };
  } else {
    metrics.hierarchy_gradient = {distinct_sizes: 0, cv: 0};
  }

  // 7.3 对齐偏差：主要左边缘聚类，计算平均到最近主边缘的偏差
  const lefts = [];
  for (const el of cards) {
    const r = el.getBoundingClientRect();
    if (r.width > 0) lefts.push(r.left);
  }
  if (lefts.length >= 2) {
    lefts.sort((a, b) => a - b);
    // 简单一维 k-means（k=3 主边缘）
    let centers = [lefts[0], lefts[Math.floor(lefts.length / 2)], lefts[lefts.length - 1]];
    for (let it = 0; it < 10; it++) {
      const groups = [[], [], []];
      for (const x of lefts) {
        let best = 0, bestDist = Math.abs(x - centers[0]);
        for (let k = 1; k < 3; k++) {
          const d = Math.abs(x - centers[k]);
          if (d < bestDist) { best = k; bestDist = d; }
        }
        groups[best].push(x);
      }
      for (let k = 0; k < 3; k++) {
        if (groups[k].length) {
          centers[k] = groups[k].reduce((a, b) => a + b, 0) / groups[k].length;
        }
      }
    }
    const deviations = lefts.map(x => Math.min(...centers.map(c => Math.abs(x - c))));
    metrics.alignment_deviation = deviations.reduce((a, b) => a + b, 0) / deviations.length;
  } else {
    metrics.alignment_deviation = 0;
  }

  // 7.4 HSL 和谐：采样主要文本/背景色，计算主导色相离散度
  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0, l = (max + min) / 2;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r: h = (g - b) / d + (g < b ? 6 : 0); break;
        case g: h = (b - r) / d + 2; break;
        case b: h = (r - g) / d + 4; break;
      }
      h /= 6;
    }
    return [h * 360, s, l];
  }
  function parseRgb(c) {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map(s => parseFloat(s.trim()));
    if (parts.length < 3) return null;
    return parts.slice(0, 3);
  }
  const hues = [];
  const saturations = [];
  for (const el of els) {
    const t = (el.textContent || '').trim();
    if (!t) continue;
    const cs = getComputedStyle(el);
    const fg = parseRgb(cs.color);
    const bg = parseRgb(effectiveBg(el));
    for (const c of [fg, bg]) {
      if (!c) continue;
      const [h, s, l] = rgbToHsl(c[0], c[1], c[2]);
      // 忽略无彩色/近白/近黑
      if (s > 0.15 && l > 0.1 && l < 0.9) {
        hues.push(h);
        saturations.push(s);
      }
    }
  }
  if (hues.length >= 2) {
    // 色相环形方差
    const rad = hues.map(h => h * Math.PI / 180);
    const meanX = rad.reduce((a, b) => a + Math.cos(b), 0) / rad.length;
    const meanY = rad.reduce((a, b) => a + Math.sin(b), 0) / rad.length;
    const circularVar = 1 - Math.sqrt(meanX * meanX + meanY * meanY);
    metrics.hsl_harmony = {
      hue_count: hues.length,
      circular_variance: circularVar,
      avg_saturation: saturations.reduce((a, b) => a + b, 0) / saturations.length
    };
  } else {
    metrics.hsl_harmony = {hue_count: hues.length, circular_variance: 0, avg_saturation: 0};
  }

  return {is_crafted: isCrafted, findings: out, metrics: metrics};
}
"""


def _install_local_only_route(page):
    """P3 加固（2026-09-06 安全审查）：无头渲染只放行 file:// 本地产物，拦截其余一切请求。

    待检 HTML 由自产 spec 生成，来源内容不完全可信，可能被注入外链资源或远程
    跳转；密度检查不需要任何远程资源，navigation 与子资源一并拦截，保证渲染
    过程零出网。正常本地渲染链路（相对路径引用 _assets 等）不受影响。
    """
    def _only_local(route):
        if (route.request.url or "").startswith("file://"):
            route.continue_()
        else:
            route.abort()

    page.route("**/*", _only_local)


def _shot_dir():
    """C-F2 截图存档目录：``_tmp/density_shots/YYYYMMDD/``。"""
    today = datetime.now().strftime("%Y%m%d")
    return os.path.join(SCRIPT_DIR, "_tmp", "density_shots", today)


def _shot_path(html_path, viewport, seq=0):
    """生成截图文件路径，避免同名文件冲突。"""
    base = os.path.splitext(os.path.basename(html_path))[0]
    stamp = datetime.now().strftime("%H%M%S")
    name = f"{base}_{viewport['name']}_{viewport['width']}x{viewport['height']}_{stamp}_{seq}.png"
    return os.path.join(_shot_dir(), name)


def _categorize(finding):
    """从 finding 字符串提取类别前缀。"""
    for cat in _CRAFTED_BLOCK_CATEGORIES + _OBSERVATION_CATEGORIES:
        if finding.startswith(cat):
            return cat
    return "其他"


def _run_viewport(page, html_path, viewport, save_shot=False, seq=0):
    """在指定视口下执行密度 JS 并可选截图。"""
    page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
    page.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
    page.wait_for_load_state("networkidle")

    shot_path = None
    if save_shot:
        os.makedirs(_shot_dir(), exist_ok=True)
        shot_path = _shot_path(html_path, viewport, seq=seq)
        page.screenshot(path=shot_path, full_page=True)

    result = page.evaluate(_DENSITY_JS)
    return result, shot_path


def _merge_viewport_results(results):
    """合并多视口结果：findings 去重、metrics 取各视口均值/最劣。"""
    if not results:
        return {"is_crafted": False, "findings": [], "metrics": {}}

    is_crafted = any(r["is_crafted"] for r in results)

    # findings 按字符串去重，保留首次出现顺序
    seen = set()
    findings = []
    for r in results:
        for f in r.get("findings", []):
            if f not in seen:
                seen.add(f)
                findings.append(f)

    # metrics：数值标量取平均；嵌套对象取首个（结构一致）
    metrics = {}
    keys = set()
    for r in results:
        keys.update(r.get("metrics", {}).keys())
    for k in keys:
        vals = [r["metrics"][k] for r in results if k in r.get("metrics", {})]
        if vals and isinstance(vals[0], (int, float)):
            metrics[k] = sum(vals) / len(vals)
        elif vals:
            metrics[k] = vals[0]
    return {"is_crafted": is_crafted, "findings": findings, "metrics": metrics}


def check_density_html(html_path, gate="verify"):
    """渲染后密度/可读性检查。

    Args:
        html_path: HTML 文件路径。
        gate: ``"verify"``（日常验证，单视口 1280×720，默认）或
            ``"deliver"``（交付门，全视口 + 截图存档）。

    Returns:
        DensityResult: 可像 list 一样迭代的 finding 列表，并携带：
            - ``level``: ``"ok"`` / ``"warn"`` / ``"fail"``
            - ``blocked``: 是否应被调用方阻断（crafted 页硬事实超标）
            - ``blocked_findings``: 导致阻断的 finding 列表
            - ``screenshots``: 截图存档路径列表
            - ``metrics``: visual_intent 指标集
    """
    if not os.path.exists(html_path):
        return DensityResult([f"文件不存在: {html_path}"])

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return DensityResult(
            ["playwright 未安装，跳过密度检查（pip install playwright）"])

    viewports = _VIEWPORTS if gate == "deliver" else [_VIEWPORTS[0]]
    save_shots = gate == "deliver"

    results = []
    screenshots = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for i, viewport in enumerate(viewports):
                page = browser.new_page()
                _install_local_only_route(page)
                result, shot = _run_viewport(
                    page, html_path, viewport, save_shot=save_shots, seq=i)
                results.append(result)
                if shot:
                    screenshots.append(shot)
                page.close()
            browser.close()
    except Exception as e:
        return DensityResult([f"密度检查执行失败: {e}"])

    merged = _merge_viewport_results(results)
    findings = merged.get("findings", [])
    metrics = merged.get("metrics", {})
    is_crafted = merged.get("is_crafted", False)

    # D-120：几何/结构类优先于低对比度
    _weight = {
        "字号底线": 0, "溢出": 0, "重叠": 0,
        "大空白": 1, "字号层级": 1, "低对比度": 2,
    }
    findings.sort(key=lambda f: next(
        (w for k, w in _weight.items() if f.startswith(k)), 3))

    # 判定 level / blocked
    blocked_findings = []
    if is_crafted:
        for f in findings:
            if _categorize(f) in _CRAFTED_BLOCK_CATEGORIES:
                blocked_findings.append(f)
        level = "fail" if blocked_findings else ("warn" if findings else "ok")
    else:
        level = "warn" if findings else "ok"

    return DensityResult(
        findings,
        level=level,
        blocked=bool(blocked_findings),
        blocked_findings=blocked_findings,
        screenshots=screenshots,
        metrics=metrics,
    )
