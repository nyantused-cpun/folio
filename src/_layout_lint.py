# -*- coding: utf-8 -*-
"""pptd 工程确定性版式 lint（重构 Phase 2，plan §七 2.8）。

对 pptd 工程（主 .pptd + pages/*.page）做纯几何检查，不依赖截图/VLM——
依据 docs/refactor_plan_spec_pipeline_2026-07-20.md §11.2 第 5 条
（hands-on-deck：确定性 lint 优先于 VLM 回检）。

五类检查：
- out_of_bounds（error）：bounds 越出画布（容差 2px）
- text_overflow（error）：text 元素估算文本高度 > bounds.h × 1.15
  （行数用 _renderer.diagram.pptd_emit.est_text_w 全角/半角估算 × fontSize × 1.3 行距）
- table_row_overflow（error）：table 行数 × 最小行高 36 > bounds.h
  （间距体系 v1 §四 2，table 内部此前零检查）
- overlap（warning）：两元素相交面积 > 较小面积 30%；排除声明式同组配对、
  veil/mask/背景类元素（elementId 含 veil/mask/bg 或 fill 色带透明 alpha）、
  table 元素（内部单元格非独立元素）
- badge_overlap / text_stack_overlap（error，间距体系 v1 §四 1）：
  同组豁免从"同前缀全豁免"收窄为"声明式配对豁免"（shape 与其 text child /
  装饰子元素，如 card-100-1 vs card-100-1-title/desc/bar、num vs numt、
  chip-0 vs chipt-0）；两类 P0 特征模式在同组内也报出——
  ①小 shape（≤30×30，徽章特征）与文本框相交（I-1 徽章压标题）；
  ②同组两个文本框纵向相交（I-2 desc 压 chips）。
  初上线为 warning；I-1/I-2 容器化修复（§3.2，2026-07-21）落地后升 error 阻断

接入点：cmd_html_build pptd 分支 / cmd_pptd_gen（build_deck 后 lint_pptd_files，
error 阻断）；cmd_pptd_build（pptd check 后 lint_pptd_dir，error 阻断）。
与 §七 2.5 溢出防线的关系：防线保证新产出基本无越界，lint 是兜底
（手写 spec / 分页代理改过的 .page 仍可能越界）。
"""

import os
import re
from typing import NamedTuple

import yaml

from _pptd_gen import _CONTENT_Y_MAX as _CLAMP_LINE
from _renderer.diagram.pptd_emit import est_text_w


class Issue(NamedTuple):
    """一条版式问题。kind: out_of_bounds | text_overflow | table_row_overflow
    | overlap | badge_overlap | text_stack_overlap。"""

    page: str        # 页面标识（pages/xx.page 相对路径）
    element_id: str
    kind: str
    message: str
    severity: str    # error | warning


ERROR = "error"
WARNING = "warning"

# 阈值（§七 2.8 口径）
DEFAULT_CANVAS_W = 1280.0
DEFAULT_CANVAS_H = 720.0
BOUNDS_TOL = 2.0          # 越界容差（px）
OVERFLOW_RATIO = 1.15     # 估算文本高 > 框高 × 1.15 判溢出
OVERLAP_RATIO = 0.30      # 相交面积 > 较小元素面积 30% 判重叠
LINE_HEIGHT = 1.3         # 文本高度估算行距
DEFAULT_FONT_SIZE = 14.0  # content 未给 fontSize 且样式查不到时的回退
SMALL_BADGE_SIDE = 30.0   # ≤30×30 的小 shape 视为徽章特征（I-1 检查）
TABLE_MIN_ROW_H = 36.0    # table 最小行高（14pt 字 + padding，同 _pptd_gen._emit_table）

# text_overflow 豁免线（§七 2.8 裁决 a）：_CLAMP_LINE 与 _pptd_gen._CONTENT_Y_MAX
# 同值（674）。底边恰贴此线（容差 1px）的 text 元素是溢出防线裁剪后的产物——
# 溢出已处置（裁切 + report.warn），不再算未处置溢出。豁免放宽：文本框自身
# 底边贴线，或所属同组容器（shape）底边贴线——卡内 body 底边 = 卡底 - inset，
# 自身口径盖不住整组裁剪产物。盲区：手写元素底边恰在 674 同样豁免，概率低
# 可接受；out_of_bounds / overlap 检查不受影响。
_CLAMP_LINE_TOL = 1.0


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def lint_pptd_files(files):
    """对 build_deck 返回的 files dict（{相对路径: 内容字符串}）跑 lint。

    返回 [Issue, ...]（按页面、元素顺序，确定性）。
    """
    main_doc, text_styles, canvas = None, {}, (DEFAULT_CANVAS_W, DEFAULT_CANVAS_H)
    for path in sorted(files):
        if path.endswith(".pptd"):
            main_doc = _as_dict(yaml.safe_load(files[path]))
            break
    if main_doc:
        canvas = _canvas_size(main_doc)
        text_styles = (main_doc.get("theme") or {}).get("textStyles") or {}

    issues = []
    for path in sorted(files):
        if not path.endswith(".page"):
            continue
        page = _as_dict(yaml.safe_load(files[path]))
        issues.extend(_lint_page(path, page, text_styles, canvas))
    return issues


def lint_pptd_dir(pptd_dir):
    """对落盘 pptd 工程目录（或 .pptd 文件路径）跑 lint。给 pptd-build 用。"""
    if os.path.isfile(pptd_dir) and pptd_dir.lower().endswith(".pptd"):
        main_path = pptd_dir
        root = os.path.dirname(os.path.abspath(main_path))
    else:
        root = pptd_dir
        mains = sorted(f for f in os.listdir(root) if f.endswith(".pptd"))
        if not mains:
            return []
        main_path = os.path.join(root, mains[0])

    with open(main_path, "r", encoding="utf-8") as f:
        main_doc = _as_dict(yaml.safe_load(f))
    canvas = _canvas_size(main_doc)
    text_styles = (main_doc.get("theme") or {}).get("textStyles") or {}

    page_paths = list(main_doc.get("pages") or [])
    if not page_paths:
        pages_dir = os.path.join(root, "pages")
        if os.path.isdir(pages_dir):
            page_paths = [f"pages/{p}" for p in sorted(os.listdir(pages_dir))
                          if p.endswith(".page")]

    issues = []
    for rel in page_paths:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8") as f:
            page = _as_dict(yaml.safe_load(f))
        issues.extend(_lint_page(rel, page, text_styles, canvas))
    return issues


def has_errors(issues):
    return any(i.severity == ERROR for i in issues)


def format_issues(issues):
    """打印用明细：一行汇总 + 每条一行。"""
    n_err = sum(1 for i in issues if i.severity == ERROR)
    n_warn = sum(1 for i in issues if i.severity == WARNING)
    lines = [f"[layout-lint] {n_err} error, {n_warn} warning"]
    for i in issues:
        lines.append(f"  [{i.severity}] {i.page} {i.element_id}: "
                     f"{i.kind} - {i.message}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 单页检查
# ---------------------------------------------------------------------------

def _as_dict(doc):
    """yaml.safe_load 结果兜底：非 dict（如裸字符串）按空工程处理。"""
    return doc if isinstance(doc, dict) else {}


def _lint_page(page_path, page, text_styles, canvas):
    elements = [e for e in (page.get("elements") or [])
                if isinstance(e, dict) and _valid_bounds(e)]
    issues = []
    for e in elements:
        hit = _check_out_of_bounds(page_path, e, canvas)
        if hit:
            issues.append(hit)
        if e.get("elementType") == "text":
            hit = _check_text_overflow(page_path, e, text_styles, elements)
            if hit:
                issues.append(hit)
        elif e.get("elementType") == "table":
            hit = _check_table_contents(page_path, e)
            if hit:
                issues.append(hit)
    issues.extend(_check_overlaps(page_path, elements))
    return issues


def _valid_bounds(e):
    b = e.get("bounds")
    if not isinstance(b, (list, tuple)) or len(b) != 4:
        return False
    try:
        [float(v) for v in b]
    except (TypeError, ValueError):
        return False
    return True


def _canvas_size(main_doc):
    size = main_doc.get("size") or []
    if isinstance(size, (list, tuple)) and len(size) == 2:
        try:
            return float(size[0]), float(size[1])
        except (TypeError, ValueError):
            pass
    return DEFAULT_CANVAS_W, DEFAULT_CANVAS_H


# ---------------------------------------------------------------------------
# out_of_bounds（error）
# ---------------------------------------------------------------------------

def _check_out_of_bounds(page_path, e, canvas):
    cw, ch = canvas
    x, y, w, h = [float(v) for v in e["bounds"]]
    if (x < -BOUNDS_TOL or y < -BOUNDS_TOL
            or x + w > cw + BOUNDS_TOL or y + h > ch + BOUNDS_TOL):
        return Issue(page_path, str(e.get("elementId", "?")), "out_of_bounds",
                     f"bounds 越出画布: [{_n(x)}, {_n(y)}, {_n(w)}, {_n(h)}]"
                     f"（画布 {int(cw)}x{int(ch)}，容差 {BOUNDS_TOL:g}px）",
                     ERROR)
    return None


def _n(v):
    """数值紧凑显示（整数不带小数点）。"""
    return f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


# ---------------------------------------------------------------------------
# text_overflow（error）
# ---------------------------------------------------------------------------

def _check_text_overflow(page_path, e, text_styles, elements=None):
    content = e.get("content") or {}
    # wrap=false 不换行，单行不查高度
    if content.get("wrap") is False:
        return None
    raw = content.get("text")
    if raw is None or not str(raw).strip():
        return None
    paragraphs = _plain_paragraphs(str(raw))
    if not any(p.strip() for p in paragraphs):
        return None

    x, y, w, h = [float(v) for v in e["bounds"]]
    if w <= 0 or h <= 0:
        return None
    if abs(y + h - _CLAMP_LINE) <= _CLAMP_LINE_TOL:
        return None  # 底边贴防线裁剪线：已处置的裁剪产物，豁免（§七 2.8 a）
    if elements and _group_container_on_clamp_line(e, elements):
        return None  # 同组容器底边贴线：整组裁剪产物，组内文本框连带豁免（§七 2.8 a）
    font_size = _resolve_font_size(content, text_styles)

    lines = 0
    for seg in paragraphs:
        seg = seg.strip()
        if not seg:
            lines += 1  # 空段占一行（与 _pptd_gen._estimate_text_height 口径一致）
            continue
        lines += max(1, int(-(-est_text_w(seg, font_size) // w)))
    est_h = lines * font_size * LINE_HEIGHT
    if est_h > h * OVERFLOW_RATIO:
        return Issue(page_path, str(e.get("elementId", "?")), "text_overflow",
                     f"估算文本高 {est_h:.0f}px（{lines} 行 × {font_size:g}px × "
                     f"{LINE_HEIGHT}）> 框高 {h:.0f}px × {OVERFLOW_RATIO}",
                     ERROR)
    return None


def _group_container_on_clamp_line(e, elements):
    """同组容器贴线豁免：text 元素所属同组容器（shape）底边贴防线裁剪线。

    卡内 body 底边 = 卡底 - inset（如 672），自身贴线口径盖不住；容器
    （卡片 roundRect / pullquote 竖条等 shape）底边贴线说明整组已被防线
    裁切处置（§七 2.8 a），组内文本框连带豁免。只认 shape——文本框自身
    贴线走 _check_text_overflow 的自身豁免口径。
    """
    eid = str(e.get("elementId", "?"))
    for other in elements:
        if other is e or other.get("elementType") != "shape":
            continue
        if not _same_group(eid, str(other.get("elementId", "?"))):
            continue
        oy, oh = float(other["bounds"][1]), float(other["bounds"][3])
        if abs(oy + oh - _CLAMP_LINE) <= _CLAMP_LINE_TOL:
            return True
    return False


def _plain_paragraphs(raw):
    """content.text -> 纯文本段落列表。

    段落边界：`</p><p>` 或换行；先合并边界再按 \n 切，避免 `</p>` 与原文
    换行双算空段。末尾记录换行（生成器每条文本以 \n 收尾）不算内容行。
    """
    t = re.sub(r"</p\s*>\s*<p[^>]*>", "\n", raw)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return t.rstrip("\n").split("\n")


def _resolve_font_size(content, text_styles):
    """fontSize 解析：content.fontSize > textStyles[style].fontSize > 14。"""
    fs = content.get("fontSize")
    if fs is None:
        style = content.get("style")
        if style:
            fs = (text_styles.get(str(style).lstrip("$")) or {}).get("fontSize")
    try:
        return float(fs)
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE


# ---------------------------------------------------------------------------
# table_row_overflow（error，间距体系 v1 §四 2）
# ---------------------------------------------------------------------------

def _check_table_contents(page_path, e):
    """table 内部检查：行数 × 最小行高（36）> bounds.h -> error。

    rowHeights/columnWidths 在 pptd 方言里是比例（pyz 校验 sum≈1.0），不提供
    绝对行高，故按行数 × TABLE_MIN_ROW_H 估最小所需高度；不足则行被压缩、
    单元格 text 必溢出（table 内部单元格非独立元素，text_overflow 查不到）。
    底边贴防线裁剪线（_CLAMP_LINE ±1px）的 table 是防线高度裁剪后的产物
    （行高等比压缩已处置，同 §七 2.8 a 裁决），豁免。
    """
    rows = e.get("rows") or []
    n_rows = len(rows)
    if n_rows == 0:
        return None
    y, h = float(e["bounds"][1]), float(e["bounds"][3])
    if abs(y + h - _CLAMP_LINE) <= _CLAMP_LINE_TOL:
        return None  # 底边贴防线裁剪线：已处置的裁剪产物，豁免（§七 2.8 a）
    needed = n_rows * TABLE_MIN_ROW_H
    if needed > h + 0.5:
        return Issue(page_path, str(e.get("elementId", "?")), "table_row_overflow",
                     f"{n_rows} 行 × 最小行高 {TABLE_MIN_ROW_H:g}px = {needed:g}px > "
                     f"表高 {h:.0f}px（行被压缩，单元格文本必溢出）", ERROR)
    return None


# ---------------------------------------------------------------------------
# overlap（warning）
# ---------------------------------------------------------------------------

def _check_overlaps(page_path, elements):
    issues = []
    # 徽章标签集合：小 shape（≤30×30）的声明式文本子（num->numt 等）。
    # 徽章标签随徽章压标题时，I-1 已由 badge_overlap 报过一次，不再按
    # text_stack_overlap 重复报（标签骑在徽章上是设计行为）
    badge_label_ids = set()
    elem_ids = {str(e.get("elementId", "?")) for e in elements}
    for e in elements:
        if e.get("elementType") != "shape":
            continue
        _, _, w, h = [float(v) for v in e["bounds"]]
        if w <= SMALL_BADGE_SIDE and h <= SMALL_BADGE_SIDE:
            eid = str(e.get("elementId", "?"))
            badge_label_ids.update(
                t for t in elem_ids
                if t != eid and _is_declared_pair(eid, t))
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            a, b = elements[i], elements[j]
            if a.get("elementType") == "table" or b.get("elementType") == "table":
                continue
            id_a, id_b = str(a.get("elementId", "?")), str(b.get("elementId", "?"))
            if _is_veil_like(a) or _is_veil_like(b):
                continue
            ratio = _intersection_ratio(a["bounds"], b["bounds"])
            if ratio is None or ratio <= OVERLAP_RATIO:
                continue
            # 声明式配对豁免（间距体系 v1 §四 1，先于同组判断——chip×chipt
            # 组键不同（chip/chipt 尾段各异），同组口径盖不住这类父子配对）
            if _is_declared_pair(id_a, id_b):
                continue
            if _same_group(id_a, id_b):
                # 同组内两类 P0 特征模式报 error（I-1/I-2 容器化修复后升级，§3.2）
                pair = _badge_text_pair(a, b)
                if pair is not None:
                    issues.append(Issue(
                        page_path, id_a, "badge_overlap",
                        f"小形状 {pair[0]}（≤{SMALL_BADGE_SIDE:g}×{SMALL_BADGE_SIDE:g}，"
                        f"徽章特征）与文本框 {pair[1]} 相交占较小元素 {ratio:.0%}"
                        f"（I-1 徽章压标题特征）", ERROR))
                    continue
                if (a.get("elementType") == "text"
                        and b.get("elementType") == "text"
                        and id_a not in badge_label_ids
                        and id_b not in badge_label_ids):
                    issues.append(Issue(
                        page_path, id_a, "text_stack_overlap",
                        f"同组文本框与 {id_b} 纵向相交占较小元素 {ratio:.0%}"
                        f"（I-2 desc 压 chips 特征）", ERROR))
                continue
            issues.append(Issue(
                page_path, id_a, "overlap",
                f"与 {id_b} 相交面积占较小元素 {ratio:.0%}"
                f"（阈值 {OVERLAP_RATIO:.0%}）", WARNING))
    return issues


def _intersection_ratio(bounds_a, bounds_b):
    """相交面积 / 较小元素面积；不相交或零面积返回 None。"""
    ax, ay, aw, ah = [float(v) for v in bounds_a]
    bx, by, bw, bh = [float(v) for v in bounds_b]
    inter_w = min(ax + aw, bx + bw) - max(ax, bx)
    inter_h = min(ay + ah, by + bh) - max(ay, by)
    if inter_w <= 0 or inter_h <= 0:
        return None
    area = min(aw * ah, bw * bh)
    if area <= 0:
        return None
    return (inter_w * inter_h) / area


_NUM_SEG = re.compile(r"^\d+(\.\d+)?$")


def _group_key(element_id):
    """elementId -> 组键：从尾部剥掉非纯数字段（角色后缀）。

    card-130-1-title -> card-130-1；pullquote-130-bar -> pullquote-130；
    dg403-tl0-dv -> dg403-tl0；footer-left -> footer。
    不同卡片/阶段（card-130-1 vs card-130-2）键不同，仍互相检查。
    """
    parts = str(element_id).split("-")
    while len(parts) > 1 and not _NUM_SEG.match(parts[-1]):
        parts.pop()
    return "-".join(parts)


def _same_group(id_a, id_b):
    """同组配对排除：组键相等或互为「前缀-」关系（shape 与其 title/body/bar 等）。"""
    ka, kb = _group_key(id_a), _group_key(id_b)
    return ka == kb or ka.startswith(kb + "-") or kb.startswith(ka + "-")


_INDEX_TAIL = re.compile(r"^(.*)-(\d+)$")


def _split_index(element_id):
    """elementId -> (去尾索引的干, 索引)；无数字尾缀索引为 None。

    dg-l0-chip-0 -> ("dg-l0-chip", "0")；eid-num -> ("eid-num", None)。
    """
    m = _INDEX_TAIL.match(str(element_id))
    return (m.group(1), m.group(2)) if m else (str(element_id), None)


def _is_declared_pair(id_a, id_b):
    """声明式配对（同组豁免只认这个，间距体系 v1 §四 1）：容器元素与其直接子元素。

    两种形态：
    - 「父id-角色」：card-100-1 与 card-100-1-title/desc/bar（子元素 id 以
      父 id + "-" 开头）
    - t 后缀文本子：num->numt、chip-0->chipt-0——文本框与它所标注的小形状
      同位叠加是设计行为（修 chip×chipt 每查必误报的配对识别）
    """
    if id_b.startswith(id_a + "-") or id_a.startswith(id_b + "-"):
        return True
    stem_a, idx_a = _split_index(id_a)
    stem_b, idx_b = _split_index(id_b)
    if idx_a == idx_b:
        return stem_a + "t" == stem_b or stem_b + "t" == stem_a
    return False


def _badge_text_pair(a, b):
    """小 shape（≤30×30，徽章特征）× 文本框配对 -> (小形状 id, 文本框 id)；否则 None。"""
    for shape_el, text_el in ((a, b), (b, a)):
        if (shape_el.get("elementType") == "shape"
                and text_el.get("elementType") == "text"):
            _, _, w, h = [float(v) for v in shape_el["bounds"]]
            if w <= SMALL_BADGE_SIDE and h <= SMALL_BADGE_SIDE:
                return (str(shape_el.get("elementId", "?")),
                        str(text_el.get("elementId", "?")))
    return None


_VEIL_ID_TOKENS = ("veil", "mask", "bg")
_ALPHA_HEX = re.compile(r"^#[0-9a-fA-F]{8}$")


def _is_veil_like(e):
    """veil/mask/背景类：elementId 含 veil/mask/bg，或 fill 色为带透明 alpha 的 8 位 hex。"""
    eid = str(e.get("elementId", "")).lower()
    if any(tok in eid for tok in _VEIL_ID_TOKENS):
        return True
    color = str((e.get("fill") or {}).get("color", ""))
    return bool(_ALPHA_HEX.match(color)) and color[7:].upper() != "FF"
