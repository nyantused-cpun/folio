# -*- coding: utf-8 -*-
"""audit --mode track 轨一致性检查（S9 阶段 2b，C-G2）。

独立小模块动因：_cli_audit 体量棘轮 cap 1395 顶满（Q3 产品化重定基后只许
拆小不许加码），按拆分纪律外迁（_cli_audit_behavior 先例）；_cli_audit 顶部
import 保持 `_cli_audit._audit_track` 引用面不变（monkeypatch 路径不迁移）。

轨判定唯一依据 = 产物 HTML 中 `data-track="crafted"` 边界标记（1c 契约，
_renderer/__init__.py raw_html 渲染强制输出）。检查面（开发计划 §四 2b）：
1. 双轨 deck（含 crafted 标记）内 standard 页：游离 hex / 无标记手写 SVG → FAIL
   —— hex 口径对齐 _renderer/_spec_hex._HEX_RE；<style>/<script>/注释豁免
   （主题 token CSS 与 editor.css/editor.js 注入是运行时 sanctioned 面，且
   非产物内联内容）；SVG 在 <section class="diagram"> 容器内豁免
   （diagram 元素渲染出口，_renderer/theme.py section_open）。
2. crafted 产物 review_log 必查（曾审口径：近 N 条有该产物记录即过，含
   FAIL 也算「曾审」）——完全无记录 → FAIL「crafted 产物未经 review 即交付」。
3. crafted 页占比 > 0.5 → ⚠ 警告级（与 _verify_checks 每 deck ≤2 绝对数
   告警互补：绝对数管单 deck 上限，占比管全页过半定制化）。
纯 standard deck 无轨混用面（hex 纪律由 spec 层 _validate_spec_hex 把守、
SVG 由 diagram section 管制、存量产物早于双轨制），只计数不深扫——
audit --mode all 对存量零打扰。

分工边界：本模块只做 audit 时点检查，不做交付阻断（交付门禁在 2d / verify 链）。
"""

import os
import re
from html.parser import HTMLParser

from _cli_infra import SCRIPT_DIR
from _paths import OUTPUT_SKIP_DIRS, REVIEW_LOG as _REVIEW_LOG

# 口径对齐 _renderer/_spec_hex._HEX_RE（{3,8}+\\b）；只扫内联属性与可见文本，
# <style>/<script>/注释三类运行时/说明面豁免（见模块 docstring 白名单）
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
REVIEW_WINDOW = 50        # review_log「近 N 条」曾审窗口
CRAFTED_RATIO_WARN = 0.5  # crafted 页占比告警阈值（过半才告警）
_PAGE_CLASSES = ("v2-page", "page-shell")  # renderer 两种页容器（§html 渲染）


class _TrackHTMLParser(HTMLParser):
    """切页/切图容器 + 收集 hex 与 <svg> 位置（<style>/<script>/注释豁免）。

    页容器 = <section class="v2-page|page-shell">；图容器 = <section
    class="diagram...">（theme.section_open）。页含图嵌套用栈配对；
    convert_charrefs=False 保证偏移全程对齐原始文本（转义实体不打漂）。
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._starts = None
        self._stack = []        # [(kind, start, pid)]  kind: 'page' | 'diagram'
        self._cdata = None
        self.pages = []         # [{'id','start','end','crafted'}]
        self.diagram_spans = []  # [(start, end)]
        self.crafted_marks = []  # [offset]
        self.hex_hits = []      # [(offset, value, where)]
        self.svg_hits = []      # [offset]

    def feed_text(self, text):
        self._starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._starts.append(i + 1)
        self.feed(text)
        self.close()
        while self._stack:  # 未闭合 section 兜底（截断/坏 HTML 以文末收口）
            kind, start, pid = self._stack.pop()
            self._close(kind, start, pid, len(text))

    def _abs(self):
        line, col = self.getpos()
        return self._starts[line - 1] + col

    def _close(self, kind, start, pid, end):
        if kind == "page":
            self.pages.append({"id": pid, "start": start, "end": end,
                               "crafted": any(start <= m < end
                                              for m in self.crafted_marks)})
        else:
            self.diagram_spans.append((start, end))

    def handle_starttag(self, tag, attrs):
        pos = self._abs()
        if tag in ("style", "script"):
            self._cdata = tag
        adict = dict(attrs)
        if adict.get("data-track") == "crafted":
            self.crafted_marks.append(pos)
        for k, v in attrs:  # 内联 style/属性裸 hex 嫌疑（归属 standard 页才判）
            if v:
                for m in HEX_RE.finditer(v):
                    self.hex_hits.append((pos, m.group(0), f"<{tag} {k}>"))
        if tag == "svg":
            self.svg_hits.append(pos)
        if tag == "section":
            cls = adict.get("class", "").split()
            if "diagram" in cls:
                self._stack.append(("diagram", pos, ""))
            if any(c in _PAGE_CLASSES for c in cls):
                self._stack.append(("page", pos, adict.get("id", "")))

    def handle_endtag(self, tag):
        if tag == "section" and self._stack:
            kind, start, pid = self._stack.pop()
            self._close(kind, start, pid, self._abs())
        elif tag == self._cdata:
            self._cdata = None

    def handle_data(self, data):
        if self._cdata or not data:  # <style>/<script> 内容是运行时面，豁免
            return
        pos = self._abs()
        for m in HEX_RE.finditer(data):
            self.hex_hits.append((pos, m.group(0), "text"))


def analyze_track(html_text, path="(memory)"):
    """产物 HTML 轨切面分析（纯函数：html 文本进、判定 dict 出，便于直测）。

    返回：has_crafted_mark / total_pages / crafted_pages /
          stray_hex [(page_id, value, where)] / unmarked_svg [page_id]
    crafted 页内 hex/手写 SVG 不判（crafted 轨表达豁免，同 _spec_hex 豁免口径）；
    页容器之外的 hex/svg（封面等文档级区域）不归属 standard 页，不判（宁缺毋滥）。
    """
    p = _TrackHTMLParser()
    p.feed_text(html_text)

    def _page_of(off):
        for pg in p.pages:
            if pg["start"] <= off < pg["end"]:
                return pg
        return None

    stray_hex = [(pg.get("id") or "?", val, where)
                 for off, val, where in p.hex_hits
                 for pg in [_page_of(off)]
                 if pg is not None and not pg["crafted"]]
    unmarked_svg = [pg.get("id") or "?"
                    for off in p.svg_hits
                    if not any(s <= off < e for s, e in p.diagram_spans)
                    for pg in [_page_of(off)]
                    if pg is not None and not pg["crafted"]]
    return {
        "path": path,
        "has_crafted_mark": bool(p.crafted_marks),
        "total_pages": len(p.pages),
        "crafted_pages": sum(1 for pg in p.pages if pg["crafted"]),
        "stray_hex": stray_hex,
        "unmarked_svg": unmarked_svg,
    }


def check_review_record(product_path, entries, window=REVIEW_WINDOW):
    """crafted 产物 review_log 必查（曾审口径）。返回 (reviewed, verdict)。

    近 window 条内出现该产物记录即「曾审」（verdict 含 FAIL 也算——审计只断
    「审没审」，审出的问题由 review/交付链处理）；完全无记录 → (False, '')。
    记录 file 字段绝对/相对不定：basename 相等或归一路径相等即命中。
    """
    fname = os.path.basename(product_path)
    norm = os.path.normcase(os.path.normpath(product_path))
    for e in entries[-window:]:
        if not isinstance(e, dict):
            continue
        f = str(e.get("file") or "")
        if not f:
            continue
        if (os.path.basename(f) == fname
                or os.path.normcase(os.path.normpath(f)) == norm):
            return True, str(e.get("verdict", "?"))
    return False, ""


def _audit_track(output_dir=None, review_log_path=None):
    """S9 2b：轨一致性检查（data-track 标记判定，详见模块 docstring）。

    output_dir / review_log_path 参数供单测注入 tmp 目录
    （audit 测试封闭化先例：keynote/memory clients_dir、behavior history_path）。
    """
    import json
    if output_dir is None:
        output_dir = os.path.join(SCRIPT_DIR, "output")
    if review_log_path is None:
        review_log_path = _REVIEW_LOG

    entries = []
    if os.path.exists(review_log_path):
        try:
            with open(review_log_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception as e:
            print(f"✗ review_log 读取失败: {e}")
            return False
    if not isinstance(entries, list):
        entries = []
    if not os.path.isdir(output_dir):
        print("ℹ output/ 不存在，无产物可扫（轨一致性检查空转通过）")
        return True

    fails = decks = std_files = 0
    for root, dirs, files in os.walk(output_dir):
        dirs[:] = [d for d in sorted(dirs)
                   if not d.startswith(".") and d not in OUTPUT_SKIP_DIRS
                   and not d.startswith("portal-") and not d.endswith("_audit")]
        for fn in sorted(files):
            if not fn.lower().endswith((".html", ".htm")):
                continue
            fpath = os.path.join(root, fn)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            rep = analyze_track(text, path=fpath)
            if not rep["has_crafted_mark"]:
                std_files += 1  # 纯 standard：无轨混用面，不深扫（存量零打扰）
                continue
            decks += 1
            rel = os.path.relpath(fpath, SCRIPT_DIR)
            for pid, val, where in rep["stray_hex"]:
                print(f"✗ [{rel}] standard 页 {pid} 游离 hex {val}（{where}）")
                fails += 1
            for pid in rep["unmarked_svg"]:
                print(f"✗ [{rel}] standard 页 {pid} 无标记手写 SVG"
                      "（不在 diagram 容器内）")
                fails += 1
            reviewed, verdict = check_review_record(fpath, entries)
            if reviewed:
                print(f"  ✓ [{rel}] crafted 产物已审（review_log verdict={verdict}）")
            else:
                print(f"✗ [{rel}] crafted 产物未经 review 即交付"
                      f"（review_log 近 {REVIEW_WINDOW} 条无记录）")
                fails += 1
            if rep["total_pages"] and (rep["crafted_pages"] / rep["total_pages"]
                                       > CRAFTED_RATIO_WARN):
                print(f"  ⚠ [{rel}] crafted 页占比 "
                      f"{rep['crafted_pages']}/{rep['total_pages']} > "
                      f"{CRAFTED_RATIO_WARN:.0%}（核心页稀缺性，警告级）")

    head = "✗ 轨一致性检查" if fails else "✓ 轨一致性检查完成"
    print(f"{head}：产物 {decks + std_files} 个"
          f"（双轨 deck {decks} / 纯 standard {std_files}）")
    return not fails
