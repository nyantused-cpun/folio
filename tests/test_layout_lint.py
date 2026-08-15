# -*- coding: utf-8 -*-
"""_layout_lint 版式 lint 测试（重构 Phase 2，§七 2.8；间距体系 v1 §四）。

覆盖：
- out_of_bounds / text_overflow / overlap 三类检查的命中、不命中、边界
- overlap 排除项（shape+text 同组配对、veil/mask/bg、table）
- 同组豁免精细化：声明式配对豁免（含 chip×chipt 误报修复）、
  badge_overlap / text_stack_overlap 两类 P0 特征 error
  （初为 warning；I-1/I-2 容器化修复落地后升级，间距体系 v1 §3.2）
- table_row_overflow：行数 × 最小行高 vs bounds.h（含防线裁剪线豁免）
- lint_pptd_dir 落盘工程读取
- CLI 接入：pptd-gen 遇 error 级 exit 1，干净 spec 正常
- 基线回归：6 个冻结 spec build_deck 后 lint 零 error
"""

import os
import shutil
import sys

import pytest
import yaml

from _layout_lint import ERROR, WARNING, lint_pptd_dir, lint_pptd_files


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _files(elements, theme=None, canvas=(1280, 720)):
    """构造最小 files dict（主 pptd + 单页）。"""
    main = {"size": list(canvas), "theme": theme or {}, "pages": ["pages/01.page"]}
    page = {"pageType": "content", "elements": elements}
    return {
        "deck.pptd": yaml.safe_dump(main, allow_unicode=True),
        "pages/01.page": yaml.safe_dump(page, allow_unicode=True),
    }


def _text(eid, bounds, text, **content_kw):
    content = {"text": text}
    content.update(content_kw)
    return {"elementId": eid, "elementType": "text", "bounds": bounds,
            "content": content}


def _shape(eid, bounds, fill_color="$card"):
    return {"elementId": eid, "elementType": "shape", "bounds": bounds,
            "shapeName": "rect", "fill": {"type": "solid", "color": fill_color}}


def _kinds(issues, severity=None):
    return sorted(i.kind for i in issues
                  if severity is None or i.severity == severity)


# ---------------------------------------------------------------------------
# out_of_bounds
# ---------------------------------------------------------------------------

class TestOutOfBounds:
    def test_hit_right_edge(self):
        issues = lint_pptd_files(_files([_shape("s1", [1200, 100, 200, 50])]))
        assert _kinds(issues) == ["out_of_bounds"]
        assert issues[0].severity == ERROR
        assert issues[0].element_id == "s1"

    def test_hit_bottom_edge(self):
        # y+h=730 > 720+2（同基线 arms_v5 table 场景：起点合法、高度顶出画布）
        issues = lint_pptd_files(_files([_shape("s1", [192, 606, 1048, 124])]))
        assert _kinds(issues) == ["out_of_bounds"]

    def test_hit_negative(self):
        issues = lint_pptd_files(_files([_shape("s1", [-3, 0, 100, 100])]))
        assert _kinds(issues) == ["out_of_bounds"]

    def test_within_tolerance_passes(self):
        # x+w=1281.5 在 2px 容差内；y=-1.5 也在容差内
        issues = lint_pptd_files(_files([_shape("s1", [0, -1.5, 1281.5, 721.5])]))
        assert issues == []

    def test_clean_passes(self):
        issues = lint_pptd_files(_files([_shape("s1", [192, 130, 1048, 100])]))
        assert issues == []

    def test_custom_canvas_from_pptd(self):
        # 画布尺寸读主 pptd size
        issues = lint_pptd_files(_files(
            [_shape("s1", [0, 0, 500, 500])], canvas=(800, 600)))
        assert issues == []


# ---------------------------------------------------------------------------
# text_overflow
# ---------------------------------------------------------------------------

class TestTextOverflow:
    def test_hit(self):
        # 30 个全角字 × 14px = 420px，框宽 100 → 5 行 × 14 × 1.3 = 91 > 20×1.15
        long_text = "这是一段用于测试文本溢出检查的长文本内容请继续延伸"
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 0, 100, 20], long_text, fontSize=14)]))
        assert _kinds(issues) == ["text_overflow"]
        assert issues[0].severity == ERROR

    def test_miss_big_box(self):
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 0, 1000, 200], "短文本", fontSize=14)]))
        assert issues == []

    def test_skip_wrap_false(self):
        long_text = "这是一段用于测试文本溢出检查的长文本内容请继续延伸"
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 0, 100, 20], long_text, fontSize=14, wrap=False)]))
        assert issues == []

    def test_skip_empty_text(self):
        issues = lint_pptd_files(_files([
            _text("t1", [0, 0, 100, 20], "", fontSize=14),
            _text("t2", [0, 30, 100, 20], "   ", fontSize=14),
        ]))
        assert issues == []

    def test_fontsize_from_style(self):
        # content.fontSize 缺省时解析 theme textStyles（$big 40px → 溢出）
        theme = {"textStyles": {"big": {"fontSize": 40}}}
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 0, 100, 30], "十个全角字符测试文字", style="$big")],
            theme=theme))
        assert _kinds(issues) == ["text_overflow"]

    def test_paragraphs_not_double_counted(self):
        # <p>• a</p>\n<p>• b</p> 是 2 段不是 4 段（</p> 与换行不双算）
        text = "<p>• 要点一</p>\n<p>• 要点二</p>\n"
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 0, 500, 80], text, fontSize=14)]))
        assert issues == []

    def test_narrow_box_long_text_hit(self):
        # 同基线 saijite_v1 phase desc 场景：89px 宽 70px 高放 40 个全角字
        # （40×13=520px → 6 行 × 13 × 1.3 = 101 > 70×1.15）
        desc = "全角字符占位" * 7
        issues = lint_pptd_files(_files(
            [_text("phase-1-desc", [0, 0, 89.1, 70], desc, fontSize=13)]))
        assert _kinds(issues) == ["text_overflow"]

    def test_exempt_clamp_line_bottom(self):
        # §七 2.8 a：底边恰贴 674（防线裁剪线，容差 1px）豁免 text_overflow——
        # 防线裁剪产物，溢出已处置（裁切 + warn）
        long_text = "全角字符占位" * 10
        issues = lint_pptd_files(_files(
            [_text("t1", [0, 600, 100, 74], long_text, fontSize=14)]))
        assert issues == []

    def test_clamp_line_exemption_tolerance(self):
        # 底边 674.5（距线 ≤1px）豁免；672（距线 >1px）不豁免
        long_text = "全角字符占位" * 10
        near = lint_pptd_files(_files(
            [_text("t1", [0, 600, 100, 74.5], long_text, fontSize=14)]))
        assert near == []
        far = lint_pptd_files(_files(
            [_text("t1", [0, 598, 100, 74], long_text, fontSize=14)]))
        assert _kinds(far) == ["text_overflow"]

    def test_clamp_line_exemption_only_text_overflow(self):
        # 豁免只针对 text_overflow：贴线元素越界仍查 out_of_bounds
        issues = lint_pptd_files(_files(
            [_text("t1", [1200, 600, 200, 74], "文本", fontSize=14)]))
        assert _kinds(issues) == ["out_of_bounds"]


class TestGroupContainerClampExemption:
    """text_overflow 豁免放宽（§七 2.8 a）：文本框自身底边贴线，或所属同组
    容器（shape）底边贴线——卡内 body 底边 = 卡底 - inset（如 672），自身
    贴线口径盖不住的整组裁剪产物由容器贴线连带豁免。"""

    def test_card_body_exempt_when_card_bottom_on_line(self):
        # 卡底 = 620+54 = 674 贴线；body 底 = 672 自身口径盖不住 → 容器贴线豁免
        long_text = "全角字符占位" * 10
        issues = lint_pptd_files(_files([
            _shape("card-620-1", [80, 620, 300, 54]),
            _text("card-620-1-body", [90, 658, 280, 14], long_text, fontSize=13),
        ]))
        assert issues == []

    def test_no_exemption_when_container_off_line(self):
        # 同布局但卡底 = 672 不贴线：body 仍报 text_overflow
        long_text = "全角字符占位" * 10
        issues = lint_pptd_files(_files([
            _shape("card-620-1", [80, 620, 300, 52]),
            _text("card-620-1-body", [90, 658, 280, 14], long_text, fontSize=13),
        ]))
        assert _kinds(issues, ERROR) == ["text_overflow"]

    def test_pullquote_bar_on_line_exempts_quote(self):
        # pullquote 竖条（shape）底边贴线：引文框（同组）裁切产物连带豁免
        long_quote = "全角字符占位" * 10
        issues = lint_pptd_files(_files([
            _shape("pullquote-650-bar", [80, 650, 5, 24]),
            _text("pullquote-650-text", [90, 650, 280, 24], long_quote, fontSize=16),
        ]))
        assert issues == []

    def test_clamped_cards_deck_lint_clean(self, tmp_path):
        """集成：y≈628 起点 cards（max_h≈46，压碎但未达 skip 线）整页 lint 零 error。

        12 块 bullets 推 y≈628；cards 整组裁到 ≈46 + warn，卡底贴 674——
        卡内 body（底≈672/674）由同组容器贴线豁免，不再 text_overflow 阻断。"""
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = {"confirmed": True, "author": "测试", "document": {"title": "T"},
                "pages": [{"id": "p1", "title": "页", "elements": (
                    [{"type": "bullets", "items": [f"要点{i}"]} for i in range(12)]
                    + [{"type": "cards", "cards": [
                        {"title": "卡1", "body": "长文本" * 40},
                        {"title": "卡2", "body": "长文本" * 40}]}])}]}
        spec_path = tmp_path / "spec.yml"
        spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            _pptd_gen.load_spec(str(spec_path)), str(spec_path),
            _resolve_style("enterprise"), "deck", str(tmp_path / "out"), report=report)
        errors = [i for i in lint_pptd_files(files) if i.severity == ERROR]
        assert errors == []
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# overlap
# ---------------------------------------------------------------------------

class TestOverlap:
    def test_hit(self):
        # 两个独立元素 50% 相交（ID 数字尾缀，不同组）
        a = _shape("box-1", [100, 100, 200, 200])
        b = _shape("box-2", [200, 100, 200, 200])
        issues = lint_pptd_files(_files([a, b]))
        assert _kinds(issues) == ["overlap"]
        assert issues[0].severity == WARNING
        assert "box-2" in issues[0].message

    def test_miss_small_intersection(self):
        # 相交 10%（< 30% 阈值）
        a = _shape("box-1", [100, 100, 200, 200])
        b = _shape("box-2", [280, 100, 200, 200])
        assert lint_pptd_files(_files([a, b])) == []

    def test_miss_no_intersection(self):
        a = _shape("box-1", [100, 100, 200, 200])
        b = _shape("box-2", [400, 100, 200, 200])
        assert lint_pptd_files(_files([a, b])) == []

    def test_exclude_shape_text_pair(self):
        # card-100-1 与 card-100-1-title：同组 shape+text 配对不误报
        card = _shape("card-100-1", [192, 130, 300, 100])
        title = _text("card-100-1-title", [214, 140, 260, 24], "标题",
                      fontSize=15, wrap=False)
        assert lint_pptd_files(_files([card, title])) == []

    def test_exclude_bar_inside_card(self):
        # card 与其内部 bar（shape+shape 同组）不误报
        card = _shape("card-100-1", [192, 130, 300, 100])
        bar = _shape("card-100-1-bar", [192, 148, 5, 64], fill_color="$primary")
        assert lint_pptd_files(_files([card, bar])) == []

    def test_exclude_diagram_siblings(self):
        # dg403-tl0-dv 与 dg403-tl0-desc：diagram 内部同组元素不误报
        dv = _shape("dg403-tl0-dv", [200, 300, 200, 40])
        desc = _text("dg403-tl0-desc", [200, 300, 200, 40], "说明", fontSize=12)
        assert lint_pptd_files(_files([dv, desc])) == []

    def test_distinct_cards_still_checked(self):
        # 不同组（card-100-1 vs card-100-2）越界重叠仍要报
        a = _shape("card-100-1", [100, 100, 200, 200])
        b = _shape("card-100-2", [200, 100, 200, 200])
        assert _kinds(lint_pptd_files(_files([a, b]))) == ["overlap"]

    def test_exclude_veil_by_id(self):
        veil = _shape("cover-veil", [0, 0, 1280, 720])
        title = _text("title", [102, 278, 1050, 66], "标题", fontSize=52)
        assert lint_pptd_files(_files([veil, title])) == []

    def test_exclude_veil_by_alpha_fill(self):
        # fill 8 位 hex 且 alpha 非 FF → 透明蒙层
        veil = _shape("mask-layer", [0, 0, 1280, 720], fill_color="#0A1540CC")
        title = _text("title", [102, 278, 1050, 66], "标题", fontSize=52)
        assert lint_pptd_files(_files([veil, title])) == []

    def test_opaque_fill_not_veil(self):
        # 8 位 hex 但 alpha=FF → 不透明，不豁免
        a = _shape("box-1", [100, 100, 200, 200], fill_color="#0A1540FF")
        b = _shape("box-2", [200, 100, 200, 200])
        assert _kinds(lint_pptd_files(_files([a, b]))) == ["overlap"]

    def test_exclude_table(self):
        table = {"elementId": "table-130", "elementType": "table",
                 "bounds": [192, 130, 1048, 144]}
        t = _text("note", [192, 130, 500, 40], "注", fontSize=12)
        assert lint_pptd_files(_files([table, t])) == []


# ---------------------------------------------------------------------------
# 同组豁免精细化（间距体系 v1 §四 1）：声明式配对豁免，P0 特征报 warning
# ---------------------------------------------------------------------------

class TestDeclaredPairExemption:
    """声明式配对（shape 与其 text child / t 后缀文本子）仍豁免。"""

    def test_chip_chipt_pair_not_reported(self):
        """chip 底与 chip 文本同位叠加是设计行为（修复前每查必误报 overlap）。"""
        chip = _shape("dg403-l0-chip-0", [100, 100, 80, 24])
        chipt = _text("dg403-l0-chipt-0", [100, 100, 80, 24], "标签",
                      fontSize=12, wrap=False)
        assert lint_pptd_files(_files([chip, chipt])) == []

    def test_num_numt_pair_not_reported(self):
        """序号徽章底与其数字文本（num/numt）叠加豁免。"""
        num = _shape("dg100-n1-num", [116, 138, 20, 20])
        numt = _text("dg100-n1-numt", [116, 138, 20, 20], "1",
                     fontSize=10, wrap=False)
        assert lint_pptd_files(_files([num, numt])) == []

    def test_shape_text_child_still_exempt(self):
        # card-100-1 与 card-100-1-title：声明式 shape+text 配对不误报
        card = _shape("card-100-1", [192, 130, 300, 100])
        title = _text("card-100-1-title", [214, 140, 260, 24], "标题",
                      fontSize=15, wrap=False)
        assert lint_pptd_files(_files([card, title])) == []

    def test_chip_vs_other_group_text_still_reported(self):
        """chip 底压别的组的文本框仍按通用 overlap 报出。"""
        chip = _shape("dg403-l0-chip-0", [100, 100, 80, 24])
        other = _text("note-1", [100, 100, 200, 24], "注释文字", fontSize=12)
        assert _kinds(lint_pptd_files(_files([chip, other]))) == ["overlap"]


class TestBadgeOverlap:
    """①小 shape（≤30×30，徽章特征）与文本框相交 -> badge_overlap error（I-1）。"""

    def test_badge_on_title_reported(self):
        # dg100-n1-num（20×20 徽章）压 dg100-n1-title：同组非声明配对，报出
        num = _shape("dg100-n1-num", [116, 138, 20, 20])
        title = _text("dg100-n1-title", [100, 140, 200, 20], "步骤标题",
                      fontSize=13, wrap=False)
        issues = lint_pptd_files(_files([num, title]))
        assert _kinds(issues) == ["badge_overlap"]
        assert issues[0].severity == ERROR

    def test_big_shape_on_text_not_badge(self):
        # >30×30 的 shape 压同组文本框不算徽章特征（card bar / 装饰条场景）
        bar = _shape("card-100-1-deco", [192, 148, 5, 64])
        body = _text("card-100-1-body", [192, 148, 260, 60], "正文", fontSize=13)
        assert lint_pptd_files(_files([bar, body])) == []

    def test_badge_small_intersection_passes(self):
        # 徽章与文本框相交 ≤30% 不报（蹭边不算压）
        num = _shape("dg100-n1-num", [100, 100, 20, 20])
        title = _text("dg100-n1-title", [118, 100, 200, 20], "步骤标题",
                      fontSize=13, wrap=False)
        assert lint_pptd_files(_files([num, title])) == []

    def test_badge_overlap_is_error(self):
        # I-1/I-2 容器化修复（§3.2）落地后，P0 特征从 warning 升为 error 阻断
        num = _shape("dg100-n1-num", [116, 138, 20, 20])
        title = _text("dg100-n1-title", [100, 140, 200, 20], "步骤标题",
                      fontSize=13, wrap=False)
        issues = lint_pptd_files(_files([num, title]))
        assert all(i.severity == ERROR for i in issues)

    def test_badge_label_not_double_reported(self):
        # 徽章压标题只报 badge_overlap：徽章标签（numt）随徽章压标题是同一
        # 几何事实，不再按 text_stack_overlap 重复报
        num = _shape("dg100-n1-num", [116, 138, 20, 20])
        numt = _text("dg100-n1-numt", [116, 138, 20, 20], "1",
                     fontSize=10, wrap=False)
        title = _text("dg100-n1-title", [100, 140, 200, 20], "步骤标题",
                      fontSize=13, wrap=False)
        issues = lint_pptd_files(_files([num, numt, title]))
        assert _kinds(issues) == ["badge_overlap"]


class TestTextStackOverlap:
    """②同组两个文本框纵向相交 -> text_stack_overlap error（I-2）。"""

    def test_desc_on_chipt_reported(self):
        # dg403-l0-desc 底边侵入 dg403-l0-chipt-0（desc 压 chips 特征）
        desc = _text("dg403-l0-desc", [100, 100, 200, 30], "描述文字", fontSize=12)
        chipt = _text("dg403-l0-chipt-0", [100, 122, 80, 24], "标签",
                      fontSize=12, wrap=False)
        issues = lint_pptd_files(_files([desc, chipt]))
        assert _kinds(issues) == ["text_stack_overlap"]
        assert issues[0].severity == ERROR

    def test_stacked_texts_no_intersection_passes(self):
        # 同组 title/body 纵向堆叠但不相交：正常容器布局，不报
        title = _text("card-100-1-title", [214, 140, 260, 24], "标题",
                      fontSize=15, wrap=False)
        body = _text("card-100-1-body", [214, 168, 260, 60], "正文", fontSize=13)
        assert lint_pptd_files(_files([title, body])) == []

    def test_texts_small_intersection_passes(self):
        # 相交 ≤30% 不报（估算误差余量）
        desc = _text("dg403-l0-desc", [100, 100, 200, 30], "描述文字", fontSize=12)
        chipt = _text("dg403-l0-chipt-0", [100, 128, 80, 24], "标签",
                      fontSize=12, wrap=False)
        assert lint_pptd_files(_files([desc, chipt])) == []

    def test_different_group_texts_generic_overlap(self):
        # 不同组两文本相交仍走通用 overlap（非 text_stack_overlap）
        a = _text("note-1", [100, 100, 200, 40], "注释一", fontSize=12)
        b = _text("note-2", [100, 110, 200, 40], "注释二", fontSize=12)
        assert _kinds(lint_pptd_files(_files([a, b]))) == ["overlap"]


# ---------------------------------------------------------------------------
# table 内部检查（间距体系 v1 §四 2）：行数 × 最小行高 vs bounds.h
# ---------------------------------------------------------------------------

class TestTableContents:
    def _table(self, bounds, n_rows):
        rows = [[{"content": {"text": f"r{i}c{j}"}} for j in range(2)]
                for i in range(n_rows)]
        return {"elementId": "table-130", "elementType": "table",
                "bounds": bounds, "rows": rows}

    def test_rows_exceed_height_error(self):
        # 4 行 × 36 = 144 > 60：行被压缩 -> error
        issues = lint_pptd_files(_files([self._table([80, 130, 1120, 60], 4)]))
        assert _kinds(issues) == ["table_row_overflow"]
        assert issues[0].severity == ERROR

    def test_rows_fit_height_passes(self):
        # 4 行 × 36 = 144 == 表高：正好放下
        assert lint_pptd_files(_files([self._table([80, 130, 1120, 144], 4)])) == []

    def test_empty_rows_passes(self):
        table = {"elementId": "table-130", "elementType": "table",
                 "bounds": [80, 130, 1120, 40], "rows": []}
        assert lint_pptd_files(_files([table])) == []

    def test_clamp_line_bottom_exempt(self):
        # 底边贴 674 防线裁剪线：防线高度裁剪产物（行高压缩已处置），豁免
        table = self._table([80, 530, 1120, 144], 6)  # 6×36=216 > 144，底=674
        assert lint_pptd_files(_files([table])) == []

    def test_non_clamped_compressed_table_error(self):
        # 同上行压缩但底边不在防线（手写 .page）：仍报 error
        table = self._table([80, 300, 1120, 144], 6)
        assert _kinds(lint_pptd_files(_files([table]))) == ["table_row_overflow"]


# ---------------------------------------------------------------------------
# lint_pptd_dir（落盘工程）
# ---------------------------------------------------------------------------

class TestLintPptdDir:
    def test_dir_matches_files(self, tmp_path):
        files = _files([_shape("s1", [1200, 100, 200, 50])])
        root = str(tmp_path / "deck")
        os.makedirs(os.path.join(root, "pages"))
        for rel, content in files.items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        from_dir = lint_pptd_dir(root)
        from_files = lint_pptd_files(files)
        assert from_dir == from_files
        assert _kinds(from_dir) == ["out_of_bounds"]

    def test_accepts_pptd_file_path(self, tmp_path):
        files = _files([_shape("s1", [1200, 100, 200, 50])])
        root = str(tmp_path / "deck")
        for rel, content in files.items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        issues = lint_pptd_dir(os.path.join(root, "deck.pptd"))
        assert _kinds(issues) == ["out_of_bounds"]


# ---------------------------------------------------------------------------
# CLI 接入（pptd-gen：error 阻断）
# ---------------------------------------------------------------------------

def _run_main(argv, monkeypatch):
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        with pytest.raises(SystemExit) as exc_info:
            _cli.main()
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved
    return exc_info.value.code


def _run_main_allow_success(argv, monkeypatch):
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _mock_pre_check(monkeypatch):
    import _cli_generate
    monkeypatch.setattr(_cli_generate, "_run_pre_check",
                        lambda client_name=None: {"ok": True})
    monkeypatch.setattr(_cli_generate, "backup_before_generate", lambda *a, **k: None)


def _base_spec():
    return {
        "confirmed": True,
        "author": "测试公司",
        "date": "2026-07-20",
        "style": "enterprise",
        "document": {"title": "lint 测试", "subtitle": "副标题",
                     "cover": {"veil": "#0A1540"}},
        "pages": [],
    }


def _overfull_spec():
    """构造真实超量的 spec：16 块单条 bullets 把 y 游标推到 ~663，第 14 块
    可用空间 ~11px 不足一行 → §七 2.8 d 碎片整元素 skip（不再 emit 裁剪碎片）。"""
    spec = _base_spec()
    spec["pages"] = [{"id": "p01", "title": "挤爆页", "elements": [
        {"type": "bullets", "items": [f"要点{i}"]} for i in range(16)
    ]}]
    return spec


class TestCliIntegration:
    OUT_DIR = os.path.join("output", "通用", "_lint_cli_test")

    def _write_spec(self, tmp_path, spec):
        p = tmp_path / "spec.yml"
        p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        return str(p)

    def setup_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def teardown_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def test_pptd_gen_overfull_spec_fragment_skipped(self, monkeypatch, tmp_path, capsys):
        """§七 2.8 d：真实超量页碎片元素整元素 skip，生成不阻断（工程落盘、
        页内无贴线碎片）。注意 P1-D 语义 skipped→verify FAIL：阻断发生在
        pptd-build 的 verify 环节，逼用户拆页——预期行为不是 bug。"""
        _mock_pre_check(monkeypatch)
        spec_path = self._write_spec(tmp_path, _overfull_spec())
        code = _run_main_allow_success(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", self.OUT_DIR], monkeypatch)
        assert code in (None, 0)
        out = capsys.readouterr().out
        assert "可用空间不足一行" in out
        with open(os.path.join(self.OUT_DIR, "pages", "02_p01.page"),
                  encoding="utf-8") as f:
            page = yaml.safe_load(f)
        for e in page["elements"]:
            if e["elementId"].startswith("footer-"):
                continue  # 页脚固定在 y=690，属三件套设计，不在内容区防线范围
            assert e["bounds"][1] + e["bounds"][3] <= 674 + 1

    def test_pptd_gen_lint_error_exits_1(self, monkeypatch, tmp_path, capsys):
        """lint 接线：lint_pptd_files 返回 error 时 pptd-gen 阻断（exit 1 不落盘）。
        （§七 2.8 后生成器产出天然 lint 干净，error 路径用 monkeypatch 验证接线）"""
        _mock_pre_check(monkeypatch)
        import _layout_lint
        monkeypatch.setattr(_layout_lint, "lint_pptd_files", lambda files: [
            _layout_lint.Issue("pages/02.page", "e1", "out_of_bounds",
                               "伪造越界", "error")])
        spec = _base_spec()
        spec["pages"] = [{"id": "p01", "title": "正常页", "elements": [
            {"type": "text", "content": "一段普通正文。"}]}]
        spec_path = self._write_spec(tmp_path, spec)
        code = _run_main(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", self.OUT_DIR], monkeypatch)
        assert code == 1
        assert "layout-lint" in capsys.readouterr().out
        assert not os.path.exists(self.OUT_DIR)

    def test_pptd_gen_clean_spec_passes(self, monkeypatch, tmp_path):
        _mock_pre_check(monkeypatch)
        spec = _base_spec()
        spec["pages"] = [{"id": "p01", "title": "正常页", "elements": [
            {"type": "text", "content": "一段普通正文。"},
            {"type": "bullets", "items": ["要点一", "要点二"]},
        ]}]
        spec_path = self._write_spec(tmp_path, spec)
        code = _run_main_allow_success(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", self.OUT_DIR], monkeypatch)
        assert code in (None, 0)
        assert os.path.isfile(os.path.join(self.OUT_DIR, "lint_测试.pptd"))


# ---------------------------------------------------------------------------
# 基线回归测试已随发布版移除（基线 spec 含客户材料，见 README 测试说明）
# ---------------------------------------------------------------------------

