# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""pptd-gen 命令与 _pptd_gen 模块测试。

覆盖：守门链（未确认/出白名单/缺 spec exit 1）、主 pptd 结构
（方言六陷阱：无 version / textStyles 无 bold / primary 来自 style）、
cover v3 全要素、content 三件套、text/bullets 映射、bounds 不重叠。
不触真实 pyz（集成测试在 Issue 6）。
"""

import os
import sys

import pytest
import yaml


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _run_main(argv, monkeypatch):
    """调用 _cli.main()，断言 SystemExit 返回退出码。"""
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
    """同 _run_main，但允许成功路径（返回 None 或退出码）。"""
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
    """mock _run_pre_check 返回非 None（绕过依赖检查），聚焦守门测试。"""
    import _cli_generate
    monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda client_name=None: {"ok": True})
    # backup 不实际复制
    monkeypatch.setattr(_cli_generate, "backup_before_generate", lambda *a, **k: None)


def _minimal_spec_dict():
    """最小可用 spec：confirmed + document + 1 页 text/bullets。"""
    return {
        "confirmed": True,
        "author": "测试公司",
        "date": "2026-07-18",
        "style": "enterprise",
        "document": {
            "title": "测试方案",
            "subtitle": "副标题",
            "cover": {
                "template": "dark-photo",
                "veil": "#0A1540",
                "veil_opacity": 0.8,
                "confidential": "Confidential",
                "show_date": True,
                "show_author": True,
            },
        },
        "pages": [
            {"id": "p01-intro", "title": "01 · 引言", "elements": [
                {"type": "text", "content": "第一段正文。\n第二行内容。"},
                {"type": "bullets", "items": ["要点一", "要点二", "要点三"]},
            ]},
            {"id": "p02-next", "title": "02 · 后续", "elements": [
                {"type": "text", "content": "另一段。"},
            ]},
        ],
    }


def _write_spec(tmp_path, spec_dict=None):
    spec = spec_dict or _minimal_spec_dict()
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# 守门链（走 _cli.main）
# ---------------------------------------------------------------------------

class TestGuardrails:
    """守门：未确认 exit 1 / 出白名单 exit 1 / 缺 spec exit 1。"""

    def test_missing_spec_exits_1(self, monkeypatch, tmp_path):
        _mock_pre_check(monkeypatch)
        code = _run_main(
            ["_cli.py", "pptd-gen", str(tmp_path / "不存在.yml"),
             "--client", "测试", "--output", str(tmp_path / "out")],
            monkeypatch)
        assert code == 1

    def test_unconfirmed_spec_exits_1(self, monkeypatch, tmp_path):
        _mock_pre_check(monkeypatch)
        spec = _minimal_spec_dict()
        spec["confirmed"] = False
        spec_path = _write_spec(tmp_path, spec)
        code = _run_main(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", str(tmp_path / "out")],
            monkeypatch)
        assert code == 1

    def test_output_outside_whitelist_exits_1(self, monkeypatch, tmp_path):
        _mock_pre_check(monkeypatch)
        spec_path = _write_spec(tmp_path)
        # C:/random 在 output/ 白名单外
        code = _run_main(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", "C:/random/pptd_out"],
            monkeypatch)
        assert code == 1

    def test_pre_check_failure_exits_1(self, monkeypatch, tmp_path):
        import _cli_generate
        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda client_name=None: None)
        spec_path = _write_spec(tmp_path)
        code = _run_main(
            ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
             "--output", str(tmp_path / "out")],
            monkeypatch)
        assert code == 1

    def test_happy_path(self, monkeypatch, tmp_path):
        _mock_pre_check(monkeypatch)
        spec_path = _write_spec(tmp_path)
        # 输出必须在白名单内（output/）；用唯一子目录避免冲突
        out_dir = os.path.join("output", "通用", "pptd_gen_test_happy")
        import shutil
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        try:
            code = _run_main_allow_success(
                ["_cli.py", "pptd-gen", spec_path, "--client", "测试",
                 "--output", out_dir], monkeypatch)
            assert code in (None, 0)
            # 主 pptd + 2 content 页 + cover
            assert os.path.isfile(os.path.join(out_dir, "测试方案.pptd"))
            assert os.path.isfile(os.path.join(out_dir, "pages", "01_cover.page"))
            assert os.path.isfile(os.path.join(out_dir, "pages", "02_p01_intro.page"))
            assert os.path.isfile(os.path.join(out_dir, "pages", "03_p02_next.page"))
        finally:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)


# ---------------------------------------------------------------------------
# 主 pptd 结构（方言六陷阱断言）
# ---------------------------------------------------------------------------

class TestMainPptd:
    """主 pptd：无 version / textStyles 无 bold / primary 来自 style / size。"""

    def _build(self, tmp_path, style_name="enterprise"):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["style"] = style_name
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style(style_name)
        out_dir = str(tmp_path / "out")
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        main_yaml = files["deck.pptd"]
        return yaml.safe_load(main_yaml)

    def test_no_version_field(self, tmp_path):
        """陷阱 1：主 pptd 顶层不写 version 字段。"""
        main = self._build(tmp_path)
        assert "version" not in main

    def test_size_is_1280_720(self, tmp_path):
        main = self._build(tmp_path)
        assert main["size"] == [1280, 720]

    def test_textstyles_no_bold(self, tmp_path):
        """陷阱 2：textStyles 里不写 bold 属性。"""
        main = self._build(tmp_path)
        for style_name, style_def in main["theme"]["textStyles"].items():
            assert "bold" not in style_def, f"textStyles.{style_name} 不应有 bold"

    def test_primary_from_style(self, tmp_path):
        """primary 来自 styles.json 指定 style。"""
        main = self._build(tmp_path, "enterprise")
        assert main["theme"]["colors"]["primary"] == "#2b6cb0"
        # syzygit 主色 #0078FF
        main_syzygit = self._build(tmp_path, "syzygit")
        assert main_syzygit["theme"]["colors"]["primary"] == "#0078FF"

    def test_tablestyles_has_header_fill(self, tmp_path):
        """陷阱 6：表格样式走 headerFill 系列。"""
        main = self._build(tmp_path)
        ts = main["theme"]["tableStyles"]["default"]
        assert ts["headerFill"] == "$navy"
        assert ts["headerColor"] == "#FFFFFF"
        assert ts["headerBold"] is True

    def test_pages_listed_in_order(self, tmp_path):
        """pages 清单顺序：cover 在前，spec 页按序。"""
        main = self._build(tmp_path)
        assert main["pages"][0] == "pages/01_cover.page"
        assert main["pages"][1] == "pages/02_p01_intro.page"
        assert main["pages"][2] == "pages/03_p02_next.page"


# ---------------------------------------------------------------------------
# cover 页（v3 全要素）
# ---------------------------------------------------------------------------

class TestCoverPage:
    """cover v3 全要素：background + mask + logo + title + subtitle + author + confidential。"""

    def _build_cover(self, tmp_path, with_logo=False, with_bg=False):
        import _pptd_gen
        spec = _minimal_spec_dict()
        if with_bg:
            # tmp_path 下造一个假背景图
            bg = tmp_path / "bg.jpg"
            bg.write_bytes(b"\xff\xd8\xff")  # 假 JPEG 头
            spec["document"]["cover"]["background_image"] = str(bg)
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        logo_path = str(tmp_path / "logo.png") if with_logo else None
        if with_logo:
            (tmp_path / "logo.png").write_bytes(b"\x89PNG")
        files, media = _pptd_gen.build_deck(
            spec_dict, spec_path, style, "deck", out_dir, logo_path=logo_path)
        return yaml.safe_load(files["pages/01_cover.page"]), media

    def test_cover_has_all_elements(self, tmp_path):
        """无 logo/bg 时仍发 title/subtitle/author/confidential。"""
        page, _ = self._build_cover(tmp_path)
        assert page["pageType"] == "cover"
        ids = [e["elementId"] for e in page["elements"]]
        assert "title" in ids
        assert "subtitle" in ids
        assert "author" in ids
        assert "confidential" in ids
        # 无 logo 时不发 logo
        assert "logo" not in ids

    def test_cover_title_uses_strong(self, tmp_path):
        """陷阱 2：粗体用内联 <strong>。"""
        page, _ = self._build_cover(tmp_path)
        title_elem = next(e for e in page["elements"] if e["elementId"] == "title")
        assert "<strong>" in title_elem["content"]["text"]
        assert "测试方案" in title_elem["content"]["text"]

    def test_cover_background_mask(self, tmp_path):
        """背景图 + 遮罩：veil + opacity 转十六进制。"""
        page, _ = self._build_cover(tmp_path, with_bg=True)
        bg = page["background"]
        assert bg["type"] == "image"
        assert bg["fit"]["mode"] == "cover"
        # veil #0A1540 + opacity 0.8 -> CC
        assert bg["mask"]["color"] == "#0A1540CC"

    def test_cover_logo_element(self, tmp_path):
        """有 logo 时发 logo 元素，bounds 发射值 [38,43,209,50] 经 4px 网格吸附。"""
        page, media = self._build_cover(tmp_path, with_logo=True)
        logo_elem = next(e for e in page["elements"] if e["elementId"] == "logo")
        assert logo_elem["elementType"] == "image"
        assert logo_elem["bounds"] == [40, 44, 208, 48]
        # media 列表含 logo
        assert any(m[1] == "logo.png" for m in media)

    def test_cover_bg_image_copied_to_media(self, tmp_path):
        """背景图复制到 media/。"""
        page, media = self._build_cover(tmp_path, with_bg=True)
        assert any(m[1] == "bg.jpg" for m in media)

    def test_cover_confidential_includes_date(self, tmp_path):
        """show_date True 时 confidential 含日期。"""
        page, _ = self._build_cover(tmp_path)
        conf_elem = next(e for e in page["elements"] if e["elementId"] == "confidential")
        assert "2026-07-18" in conf_elem["content"]["text"]


# ---------------------------------------------------------------------------
# content 页（三件套 + text/bullets）
# ---------------------------------------------------------------------------

class TestContentPage:
    """content 页：三件套（logo/标题/页脚）+ text/bullets 映射 + bounds 不重叠。"""

    def _build_page(self, tmp_path, page_index=0):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        # 造 logo 让三件套完整
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"\x89PNG")
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, style, "deck", out_dir, logo_path=str(logo))
        # 取第 page_index 个 content 页
        page_files = [p for p in files if p.endswith(".page") and "cover" not in p]
        page_files.sort()
        return yaml.safe_load(files[page_files[page_index]]), files

    def test_three_pieces_present(self, tmp_path):
        """三件套：header-logo + title + footer-left + footer-right。"""
        page, _ = self._build_page(tmp_path)
        ids = [e["elementId"] for e in page["elements"]]
        assert "header-logo" in ids
        assert "title" in ids
        assert "footer-left" in ids
        assert "footer-right" in ids

    def test_title_uses_strong(self, tmp_path):
        """标题用 <strong> 包裹。"""
        page, _ = self._build_page(tmp_path)
        title_elem = next(e for e in page["elements"] if e["elementId"] == "title")
        assert "<strong>" in title_elem["content"]["text"]
        assert "引言" in title_elem["content"]["text"]

    def test_footer_page_number(self, tmp_path):
        """页脚右含页码。第一页 page_num=2。"""
        page, _ = self._build_page(tmp_path, page_index=0)
        footer = next(e for e in page["elements"] if e["elementId"] == "footer-right")
        assert "Page - 2" in footer["content"]["text"]

    def test_text_element_emitted(self, tmp_path):
        """text 元素 -> 1 个 Text（bodytext 样式）。"""
        page, _ = self._build_page(tmp_path)
        text_elems = [e for e in page["elements"]
                      if e["elementType"] == "text"
                      and e["elementId"].startswith("elem-")]
        # spec 第一页有 1 个 text + 1 个 bullets
        text_contents = [e["content"]["text"] for e in text_elems
                         if "• " not in e["content"]["text"]]
        assert any("第一段正文" in t for t in text_contents)

    def test_bullets_rendered_with_prefix(self, tmp_path):
        """bullets -> 单 Text，rich 多段，每段前缀 '• '。"""
        page, _ = self._build_page(tmp_path)
        text_elems = [e for e in page["elements"]
                      if e["elementType"] == "text"
                      and e["elementId"].startswith("elem-")]
        bullets_elem = next(e for e in text_elems if "• " in e["content"]["text"])
        # 三条要点 -> 三段 <p>• ...</p>
        assert bullets_elem["content"]["text"].count("<p>• ") == 3
        assert "要点一" in bullets_elem["content"]["text"]

    def test_content_elements_no_overlap(self, tmp_path):
        """同页内容元素 bounds y 不重叠（按游标堆叠）。"""
        page, _ = self._build_page(tmp_path)
        elem_bounds = [e["bounds"] for e in page["elements"]
                       if e["elementId"].startswith("elem-")]
        elem_bounds.sort(key=lambda b: b[1])  # 按 y 排序
        for i in range(1, len(elem_bounds)):
            prev = elem_bounds[i - 1]
            curr = elem_bounds[i]
            # curr.y >= prev.y + prev.h（允许 12px 间距误差）
            assert curr[1] >= prev[1] + prev[3] - 1, \
                f"元素重叠：prev y={prev[1]} h={prev[3]}，curr y={curr[1]}"

    def test_empty_element_list_skipped(self, tmp_path):
        """空 cards/table/phases 不发元素也不报错。"""
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"].append({"type": "cards", "cards": []})
        spec["pages"][0]["elements"].append({"type": "table", "headers": [], "rows": []})
        spec["pages"][0]["elements"].append({"type": "phases", "phases": []})
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        # 不应抛异常
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        assert "pages/02_p01_intro.page" in files


# ---------------------------------------------------------------------------
# 富元素：cards / table / phases / pullquote（P2）
# ---------------------------------------------------------------------------

class TestCardsElement:
    """cards 映射：roundRect + 5px 竖条 + cardtitle/cardbody + <strong>。"""

    def _build_with_cards(self, tmp_path, cards):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [{"type": "cards", "cards": cards}]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_cards_roundrect_and_bar(self, tmp_path):
        """每卡 roundRect adjustments [8000] fill $card + 左侧 5px $primary 竖条。"""
        page = self._build_with_cards(tmp_path, [
            {"title": "卡1", "body": "内容1"},
            {"title": "卡2", "body": "内容2"},
        ])
        shapes = [e for e in page["elements"] if e["elementType"] == "shape"]
        # 2 卡 roundRect + 2 竖条 rect = 4 shape
        round_rects = [s for s in shapes if s.get("shapeName") == "roundRect"]
        bars = [s for s in shapes if s.get("shapeName") == "rect"]
        assert len(round_rects) == 2
        assert len(bars) == 2
        assert round_rects[0]["adjustments"] == [8000]
        assert round_rects[0]["fill"]["color"] == "$card"
        assert bars[0]["bounds"][2] == 4  # 竖条宽 5px 经 4px 网格吸附（间距体系 v1）为 4
        assert bars[0]["fill"]["color"] == "$primary"

    def test_cards_title_uses_strong(self, tmp_path):
        """卡标题用 <strong>。"""
        page = self._build_with_cards(tmp_path, [{"title": "蓝海集团实测", "body": "x"}])
        title_elem = next(e for e in page["elements"] if e["elementId"].endswith("-1-title"))
        assert "<strong>" in title_elem["content"]["text"]
        assert "蓝海集团实测" in title_elem["content"]["text"]
        assert title_elem["content"]["style"] == "$cardtitle"

    def test_cards_body_style(self, tmp_path):
        """卡正文用 $cardbody 样式。"""
        page = self._build_with_cards(tmp_path, [{"title": "t", "body": "正文内容"}])
        body_elem = next(e for e in page["elements"] if e["elementId"].endswith("-1-body"))
        assert body_elem["content"]["style"] == "$cardbody"
        assert "正文内容" in body_elem["content"]["text"]

    def test_cards_horizontal_layout(self, tmp_path):
        """n 卡横排均分，间距 24。"""
        page = self._build_with_cards(tmp_path, [
            {"title": "卡1", "body": "x"},
            {"title": "卡2", "body": "x"},
        ])
        cards = [e for e in page["elements"]
                 if e["elementType"] == "shape" and e.get("shapeName") == "roundRect"]
        # 卡 2 x = 卡 1 x + 卡宽 + 24
        gap = cards[1]["bounds"][0] - (cards[0]["bounds"][0] + cards[0]["bounds"][2])
        assert abs(gap - 24) < 1

    def test_no_icon_element(self, tmp_path):
        """PRD Q5：禁用 Icon 元素。"""
        page = self._build_with_cards(tmp_path, [{"title": "t", "body": "b"}])
        assert not any(e["elementType"] == "icon" for e in page["elements"])


class TestTableElement:
    """table 映射：columnWidths/rowHeights 均分 + {content:} + style "$default"。"""

    def _build_with_table(self, tmp_path, headers, rows):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [{"type": "table", "headers": headers, "rows": rows}]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_table_structure(self, tmp_path):
        """表结构：bounds + columnWidths 均分 + 行高 hug + style $default。"""
        page = self._build_with_table(
            tmp_path,
            ["维度", "内容"],
            [["企业现状", "机房服务器"], ["常见误区", "买多了闲置"]])
        table = next(e for e in page["elements"] if e["elementType"] == "table")
        assert table["style"] == "$default"
        # 2 列均分
        assert abs(sum(table["columnWidths"]) - 1.0) < 0.01
        assert abs(table["columnWidths"][0] - 0.5) < 0.01
        # 3 行（1 表头 + 2 数据），行高 hug（间距体系 v1 §五）：表头原比例高
        #（3×36×0.1=10.8）不足一行实高（14×1.3+2×6=30.2）被顶起；短内容数据行
        # 保持原均分高（3×36×0.45=48.6），总高 30.2+48.6+48.6=127.4
        assert abs(sum(table["rowHeights"]) - 1.0) < 0.01
        assert table["rowHeights"][0] == pytest.approx(30.2 / 127.4)
        assert table["rowHeights"][1] == pytest.approx(48.6 / 127.4)

    def test_table_cells_are_content_objects(self, tmp_path):
        """陷阱 5：单元格必须是 {content: {text: ...}} 对象，非裸字符串。"""
        page = self._build_with_table(
            tmp_path, ["A", "B"], [["x", "y"]])
        table = next(e for e in page["elements"] if e["elementType"] == "table")
        for row in table["rows"]:
            for cell in row:
                assert isinstance(cell, dict)
                assert "content" in cell
                assert "text" in cell["content"]

    def test_table_header_row(self, tmp_path):
        """首行是表头，单元格只写 text（headerFill 由主题负责）。"""
        page = self._build_with_table(tmp_path, ["列1", "列2"], [["a", "b"]])
        table = next(e for e in page["elements"] if e["elementType"] == "table")
        header_row = table["rows"][0]
        assert header_row[0]["content"]["text"] == "列1"
        assert header_row[1]["content"]["text"] == "列2"

    def test_table_first_column_bold_navy(self, tmp_path):
        """数据行首列加 <strong> + color $navy（照 v3）。"""
        page = self._build_with_table(
            tmp_path, ["维度", "内容"], [["企业现状", "机房"]])
        table = next(e for e in page["elements"] if e["elementType"] == "table")
        data_row = table["rows"][1]
        first_cell = data_row[0]
        assert "<strong>" in first_cell["content"]["text"]
        assert first_cell["content"]["color"] == "$navy"
        # 其余列不加粗
        assert "<strong>" not in data_row[1]["content"]["text"]

    def test_no_icon_in_table(self, tmp_path):
        """PRD Q5：表格不产 Icon 元素。"""
        page = self._build_with_table(tmp_path, ["A"], [["x"]])
        assert not any(e["elementType"] == "icon" for e in page["elements"])


class TestPhasesElement:
    """phases 映射：每阶段 Shape + name(<strong>) + desc 横排（spec 字段 name/desc）。"""

    def _build_with_phases(self, tmp_path, phases):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [{"type": "phases", "phases": phases}]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_phases_uses_name_desc(self, tmp_path):
        """spec 字段 name/desc（不是 label/goal）。"""
        page = self._build_with_phases(tmp_path, [
            {"name": "① 摸清家底", "desc": "盘点系统（2-4 周）"},
            {"name": "② 搭骨架", "desc": "本体建模（4-6 周）"},
        ])
        name_elem = next(e for e in page["elements"] if e["elementId"].endswith("-1-name"))
        desc_elem = next(e for e in page["elements"] if e["elementId"].endswith("-1-desc"))
        assert "摸清家底" in name_elem["content"]["text"]
        assert "盘点系统" in desc_elem["content"]["text"]

    def test_phases_strong_in_name(self, tmp_path):
        """阶段 name 用 <strong>。"""
        page = self._build_with_phases(tmp_path, [{"name": "步骤1", "desc": "x"}])
        name_elem = next(e for e in page["elements"] if e["elementId"].endswith("-1-name"))
        assert "<strong>" in name_elem["content"]["text"]

    def test_phases_horizontal_layout(self, tmp_path):
        """n 阶段横排均分，间距 24。"""
        page = self._build_with_phases(tmp_path, [
            {"name": "s1", "desc": "d1"},
            {"name": "s2", "desc": "d2"},
        ])
        shapes = [e for e in page["elements"]
                  if e["elementType"] == "shape" and e.get("shapeName") == "roundRect"]
        gap = shapes[1]["bounds"][0] - (shapes[0]["bounds"][0] + shapes[0]["bounds"][2])
        assert abs(gap - 24) < 1

    def test_no_icon_in_phases(self, tmp_path):
        """PRD Q5：phases 不产 Icon 元素。"""
        page = self._build_with_phases(tmp_path, [{"name": "s", "desc": "d"}])
        assert not any(e["elementType"] == "icon" for e in page["elements"])

    def test_phases_adaptive_height(self, tmp_path):
        """§七 2.8：phase_h 按 desc 内容自适应（原固定 110，7 列窄卡放不下）。

        7 列时 desc 宽 ≈ 89px，40 个全角字（est 520px）需 6 行 ≈ 121px，
        phase_h = 24 + 12 + 121 + 16 ≈ 173 > 110。"""
        long_desc = "全角字符占位" * 7  # 42 字
        page = self._build_with_phases(tmp_path, [
            {"name": f"阶段{i}", "desc": long_desc} for i in range(7)])
        shape = next(e for e in page["elements"] if e["elementId"] == "phase-130-1")
        assert shape["bounds"][3] > 110

    def test_phases_short_desc_keeps_min_height(self, tmp_path):
        """短 desc 仍取 min 110（基线兼容）。

        直接调 _emit_phases 验证发射层最小高度——经 build_deck 的整页断言
        会被页级填充（_fill_content_area）二次放大，见 TestContentFill。"""
        import _pptd_gen
        elements = []
        phase_h = _pptd_gen._emit_phases(
            elements, [{"name": f"阶段{i}", "desc": "短"} for i in range(3)],
            192, 130, 1048)
        assert phase_h == 110
        shape = next(e for e in elements if e["elementId"] == "phase-130-1")
        assert shape["bounds"][3] == 110


class TestElementIdUniqueness:
    """§七 2.4：cards/phases 的 elementId 带 y 坐标前缀（card-{y}-{i}），
    同页多组 cards/phases 不撞 ID。"""

    def _build_page(self, tmp_path, elements):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = elements
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, style, "deck", str(tmp_path / "out"))
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_same_page_multi_cards_phases_ids_unique(self, tmp_path):
        """同页两个 cards 元素 + 一个 phases：全部 elementId 唯一。"""
        page = self._build_page(tmp_path, [
            {"type": "cards", "cards": [{"title": "A", "body": "a"}]},
            {"type": "cards", "cards": [{"title": "B", "body": "b"}]},
            {"type": "phases", "phases": [{"name": "P1", "desc": "d1"}]},
        ])
        ids = [e["elementId"] for e in page["elements"]]
        assert len(ids) == len(set(ids)), \
            f"elementId 冲突: {[i for i in ids if ids.count(i) > 1]}"

    def test_card_id_carries_y_prefix(self, tmp_path):
        """cards ID 格式 card-{int(y)}-{i}（-bar/-title/-body 同前缀）。"""
        import re
        page = self._build_page(tmp_path, [
            {"type": "cards", "cards": [{"title": "A", "body": "a"}]},
        ])
        card = next(e for e in page["elements"]
                    if re.fullmatch(r"card-\d+-1", e["elementId"]))
        # id 记发射时 y（130），bounds 经页出口 4px 网格吸附（间距体系 v1），容差 GRID
        id_y = int(re.fullmatch(r"card-(\d+)-1", card["elementId"]).group(1))
        assert abs(id_y - card["bounds"][1]) <= 4

    def test_phases_id_carries_y_prefix(self, tmp_path):
        """phases ID 格式 phase-{int(y)}-{i}。"""
        import re
        page = self._build_page(tmp_path, [
            {"type": "phases", "phases": [{"name": "P1", "desc": "d1"}]},
        ])
        phase = next(e for e in page["elements"]
                     if re.fullmatch(r"phase-\d+-1", e["elementId"]))
        # id 记发射时 y，bounds 经页出口 4px 网格吸附（间距体系 v1），容差 GRID
        id_y = int(re.fullmatch(r"phase-(\d+)-1", phase["elementId"]).group(1))
        assert abs(id_y - phase["bounds"][1]) <= 4


class TestPullquoteElement:
    """pullquote 映射：5px $primary 竖条 + 引文 18pt $navy + 署名 12pt $gray。"""

    def _build_with_pullquote(self, tmp_path, quote, cite):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [{"type": "pullquote", "content": quote, "cite": cite}]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, _ = _pptd_gen.build_deck(spec_dict, spec_path, style, "deck", out_dir)
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_pullquote_bar_and_text(self, tmp_path):
        """竖条 5px $primary + 引文 $navy。"""
        page = self._build_with_pullquote(tmp_path, "模型是天花板", "- 共识")
        bar = next(e for e in page["elements"] if e["elementId"].endswith("-bar"))
        text = next(e for e in page["elements"] if e["elementId"].endswith("-text"))
        assert bar["bounds"][2] == 4  # 竖条宽 5px 经 4px 网格吸附（间距体系 v1）为 4
        assert bar["fill"]["color"] == "$primary"
        assert text["content"]["color"] == "$navy"
        assert text["content"]["fontSize"] == 18
        assert "模型是天花板" in text["content"]["text"]

    def test_pullquote_cite(self, tmp_path):
        """署名 12pt $gray。"""
        page = self._build_with_pullquote(tmp_path, "q", "- 来源")
        cite = next(e for e in page["elements"] if e["elementId"].endswith("-cite"))
        assert cite["content"]["fontSize"] == 12
        assert cite["content"]["color"] == "$gray"
        assert "- 来源" in cite["content"]["text"]

    def test_pullquote_no_cite(self, tmp_path):
        """无 cite 不发署名元素。"""
        page = self._build_with_pullquote(tmp_path, "q", "")
        assert not any(e["elementId"].endswith("-cite") for e in page["elements"])


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

class TestHelpers:
    """辅助函数：opacity 转换、slug 清洗、y 游标估算。"""

    def test_opacity_to_hex(self):
        import _pptd_gen
        assert _pptd_gen._opacity_to_hex(0.8) == "CC"
        assert _pptd_gen._opacity_to_hex(1.0) == "FF"
        assert _pptd_gen._opacity_to_hex(0.0) == "00"
        assert _pptd_gen._opacity_to_hex(0.5) == "80"

    def test_slugify_name(self):
        import _pptd_gen
        assert _pptd_gen._slugify_name("测试方案 v1") == "测试方案_v1"
        assert _pptd_gen._slugify_name("") == "deck"
        assert _pptd_gen._slugify_name("方案/路径") == "方案_路径"

    def test_page_slug(self):
        import _pptd_gen
        assert _pptd_gen._page_slug({"id": "p01-three-questions"}, 0) == "p01_three_questions"
        assert _pptd_gen._page_slug({"id": "p02-ai-bill"}, 1) == "p02_ai_bill"
        assert _pptd_gen._page_slug({}, 0) == "p01"

    def test_estimate_text_height_positive(self):
        import _pptd_gen
        h = _pptd_gen._estimate_text_height("短文本", font_size=14, width=1048)
        assert h > 0
        h2 = _pptd_gen._estimate_text_height("短文本" * 100, font_size=14, width=1048)
        assert h2 > h  # 长文本更高


# ---------------------------------------------------------------------------
# 集成：emit_deck 落盘
# ---------------------------------------------------------------------------

class TestEmitDeck:
    """emit_deck：文件落盘 + media 复制。"""

    def test_emit_writes_files(self, tmp_path):
        import _pptd_gen
        spec_path = _write_spec(tmp_path)
        spec = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, media = _pptd_gen.build_deck(spec, spec_path, style, "deck", out_dir)
        _pptd_gen.emit_deck(files, media, out_dir)

        assert os.path.isfile(os.path.join(out_dir, "deck.pptd"))
        assert os.path.isfile(os.path.join(out_dir, "pages", "01_cover.page"))
        assert os.path.isfile(os.path.join(out_dir, "pages", "02_p01_intro.page"))
        # 无 media 时不建 media/
        assert not os.path.isdir(os.path.join(out_dir, "media")) or not os.listdir(os.path.join(out_dir, "media"))

    def test_emit_copies_media(self, tmp_path):
        import _pptd_gen
        # 造 logo + bg
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"\x89PNG")
        bg = tmp_path / "bg.jpg"
        bg.write_bytes(b"\xff\xd8\xff")
        spec = _minimal_spec_dict()
        spec["document"]["cover"]["background_image"] = str(bg)
        spec_path = _write_spec(tmp_path, spec)
        spec = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        out_dir = str(tmp_path / "out")
        files, media = _pptd_gen.build_deck(
            spec, spec_path, style, "deck", out_dir, logo_path=str(logo))
        _pptd_gen.emit_deck(files, media, out_dir)

        assert os.path.isfile(os.path.join(out_dir, "media", "logo.png"))
        assert os.path.isfile(os.path.join(out_dir, "media", "bg.jpg"))


# ---------------------------------------------------------------------------
# P3: logo 多路径探测 + DESIGN_GUIDE.md
# ---------------------------------------------------------------------------

class TestLogoProbe:
    """logo 解析顺序：--logo > spec.cover.logo_image > refs/ > output media/ > 跳过。"""

    def test_explicit_logo_wins(self, tmp_path):
        """--logo 显式优先于 spec 和 refs。"""
        import _pptd_gen
        explicit = tmp_path / "explicit.png"
        explicit.write_bytes(b"\x89PNG")
        spec_logo = tmp_path / "spec_logo.png"
        spec_logo.write_bytes(b"\x89PNG")
        spec = _minimal_spec_dict()
        spec["document"]["cover"]["logo_image"] = str(spec_logo)
        src, name = _pptd_gen._resolve_logo(spec, str(tmp_path), str(explicit), "测试")
        assert name == "explicit.png"

    def test_spec_logo_used_when_no_explicit(self, tmp_path):
        """无 --logo 时用 spec.document.cover.logo_image。"""
        import _pptd_gen
        spec_logo = tmp_path / "spec_logo.png"
        spec_logo.write_bytes(b"\x89PNG")
        spec = _minimal_spec_dict()
        spec["document"]["cover"]["logo_image"] = str(spec_logo)
        src, name = _pptd_gen._resolve_logo(spec, str(tmp_path), None, "测试")
        assert name == "spec_logo.png"

    def test_refs_probe_when_no_spec_logo(self, tmp_path, monkeypatch):
        """无 spec logo 时探测 _knowledge/clients/{client}/refs/。"""
        import _pptd_gen
        # 造假的 refs 目录
        refs_dir = tmp_path / "_knowledge" / "clients" / "测试客户" / "refs"
        refs_dir.mkdir(parents=True)
        logo = refs_dir / "客户logo.png"
        logo.write_bytes(b"\x89PNG")
        # 切到 tmp_path 工作目录
        monkeypatch.chdir(tmp_path)
        spec = _minimal_spec_dict()  # 无 logo_image
        src, name = _pptd_gen._resolve_logo(spec, str(tmp_path), None, "测试客户")
        assert name == "客户logo.png"
        assert os.path.exists(src)

    def test_output_media_probe_fallback(self, tmp_path, monkeypatch):
        """refs 没有时回退到 output/{client}/*/media/。"""
        import _pptd_gen
        media_dir = tmp_path / "output" / "测试客户" / "旧工程" / "media"
        media_dir.mkdir(parents=True)
        logo = media_dir / "old_logo.png"
        logo.write_bytes(b"\x89PNG")
        monkeypatch.chdir(tmp_path)
        spec = _minimal_spec_dict()
        src, name = _pptd_gen._resolve_logo(spec, str(tmp_path), None, "测试客户")
        assert name == "old_logo.png"

    def test_no_logo_returns_none(self, tmp_path, monkeypatch):
        """都没有时返回 (None, None)。"""
        import _pptd_gen
        monkeypatch.chdir(tmp_path)  # 确保不在真实 output 里找
        spec = _minimal_spec_dict()
        src, name = _pptd_gen._resolve_logo(spec, str(tmp_path), None, "不存在的客户")
        assert src is None
        assert name is None

    def test_probe_finds_png_with_logo_in_name(self, tmp_path):
        """_probe_logo_in_dir 只找文件名含 logo 的图片。"""
        import _pptd_gen
        d = tmp_path / "dir"
        d.mkdir()
        (d / "photo.jpg").write_bytes(b"x")
        (d / "logo_color.png").write_bytes(b"\x89PNG")
        (d / "icon.svg").write_bytes(b"x")
        result = _pptd_gen._probe_logo_in_dir(str(d))
        assert result is not None
        assert result[1] == "logo_color.png"

    def test_probe_returns_none_when_no_logo_file(self, tmp_path):
        """目录里没有含 logo 的图片返回 None。"""
        import _pptd_gen
        d = tmp_path / "dir"
        d.mkdir()
        (d / "photo.jpg").write_bytes(b"x")
        assert _pptd_gen._probe_logo_in_dir(str(d)) is None


class TestDesignGuide:
    """DESIGN_GUIDE.md 模板：参数化、六陷阱、无 logo 待补注记。"""

    def _build_guide(self, tmp_path, logo_abs=None, bg_abs=None, client="测试"):
        import _pptd_gen
        spec = _minimal_spec_dict()
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        theme = _pptd_gen._build_theme(style)
        return _pptd_gen._build_design_guide(
            spec_dict, theme, logo_abs, bg_abs, client, "deck", str(tmp_path / "out"))

    def test_guide_has_six_traps(self, tmp_path):
        """六陷阱标题全在。"""
        guide = self._build_guide(tmp_path)
        for i, trap in enumerate([
            "无 version 字段",
            "<strong>",
            "斜体",
            "绝对路径",
            "content",
            "headerFill",
        ], 1):
            assert trap in guide, f"陷阱 {i} 缺失"

    def test_guide_has_primary_color(self, tmp_path):
        """GUIDE 含主题 primary 色值。"""
        guide = self._build_guide(tmp_path)
        # enterprise 主色 #2b6cb0
        assert "#2b6cb0" in guide

    def test_guide_no_logo_pending_note(self, tmp_path):
        """无 logo 时 GUIDE 注明待补。"""
        guide = self._build_guide(tmp_path, logo_abs=None)
        assert "待补 logo" in guide

    def test_guide_with_logo_shows_path(self, tmp_path):
        """有 logo 时 GUIDE 显示 logo 路径。"""
        guide = self._build_guide(tmp_path, logo_abs="/fake/path/logo.png")
        assert "/fake/path/logo.png" in guide

    def test_guide_has_client_name(self, tmp_path):
        """GUIDE 自检流程含 client 名。"""
        guide = self._build_guide(tmp_path, client="蓝海集团")
        assert "蓝海集团" in guide

    def test_guide_has_no_icon_ban(self, tmp_path):
        """GUIDE 含禁用 Icon 说明。"""
        guide = self._build_guide(tmp_path)
        assert "禁用 Icon" in guide or "禁用 Icon 元素" in guide

    def test_guide_in_deck_files(self, tmp_path):
        """build_deck 产出含 DESIGN_GUIDE.md。"""
        import _pptd_gen
        spec_path = _write_spec(tmp_path)
        spec = _pptd_gen.load_spec(spec_path)
        from _renderer import _resolve_style
        style = _resolve_style("enterprise")
        files, _ = _pptd_gen.build_deck(
            spec, spec_path, style, "deck", str(tmp_path / "out"), client_name="测试")
        assert "DESIGN_GUIDE.md" in files
        assert "方言六陷阱" in files["DESIGN_GUIDE.md"]


# ---------------------------------------------------------------------------
# P3 集成：python-pptx 后端全链（后端可用才跑）
# ---------------------------------------------------------------------------

class TestIntegrationPptxBackend:
    """tmp spec -> build_deck -> emit -> backend check 0 error -> convert 产出 pptx。

    C-2 起后端为自研 python-pptx（pyz 已死）；convert 在 C-3 转换器落地前
    skip，落地后自动转真实断言。
    """

    def _backend(self):
        try:
            import pptx  # noqa: F401
            from _pptd import PythonPptxBackend
            return PythonPptxBackend()
        except Exception:
            return None

    def test_check_and_convert(self, tmp_path):
        backend = self._backend()
        if backend is None:
            pytest.skip("python-pptx 不可用，跳过集成测试")
        import _pptd_gen

        # 输出必须在 output/ 白名单内
        out_dir = os.path.join("output", "通用", "pptd_gen_integration")
        import shutil
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        try:
            spec_path = _write_spec(tmp_path)
            spec = _pptd_gen.load_spec(spec_path)
            from _renderer import _resolve_style
            style = _resolve_style("enterprise")
            files, media = _pptd_gen.build_deck(
                spec, spec_path, style, "pptd_gen_integration",
                out_dir, client_name="测试")
            _pptd_gen.emit_deck(files, media, out_dir)

            main_pptd = os.path.join(out_dir, "pptd_gen_integration.pptd")
            assert os.path.isfile(main_pptd), "主 pptd 未生成"

            # backend check（error 阻断，warning 放行）
            ok, _ = backend.check(main_pptd)
            assert ok, "pptd check 未通过"

            # backend convert（C-3 转换器实现后为真实断言）
            out_pptx = os.path.join(out_dir, "pptd_gen_integration.pptx")
            try:
                converted = backend.convert(main_pptd, out_pptx)
            except NotImplementedError:
                pytest.skip("C-3 转换器未实现，convert 集成断言待 C-3 落地")
            assert converted, "convert 失败"
            assert os.path.isfile(out_pptx), "pptx 未产出"
        finally:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)



# ---------------------------------------------------------------------------
# §七 2.2/2.3：_build_theme 消费样式单一源 + 字体统一 + 页脚作者
# ---------------------------------------------------------------------------

class TestThemeSingleSource:
    """_build_theme 消费 resolve_theme：enterprise 锚定旧 11 值（基线零 diff），
    其余风格 9 个非锚点槽走派生；fontFamily 统一 styles.json fonts.body，
    build_deck 全产物无 MiSans 字样。"""

    LEGACY_ENTERPRISE_COLORS = {
        "primary": "#2b6cb0", "navy": "#4299e1", "ink": "#1A1A1A",
        "body": "#3A3A3A", "lead": "#595959", "gray": "#727171",
        "ltgray": "#B5B5B6", "chip": "#E5F3FF", "card": "#F4F9FF",
        "veil": "#0A1540", "hairline": "#D8E2EE",
    }

    def _build(self, style_name):
        import _pptd_gen
        from _renderer import _resolve_style
        return _pptd_gen._build_theme(_resolve_style(style_name))

    def test_enterprise_colors_equal_legacy(self):
        """enterprise 11 槽与重构前 _build_theme 产出逐值相等（含键序）。"""
        theme = self._build("enterprise")
        assert theme["colors"] == self.LEGACY_ENTERPRISE_COLORS
        assert list(theme["colors"]) == list(self.LEGACY_ENTERPRISE_COLORS)

    def test_syzygit_derives_non_anchor_slots(self):
        """syzygit：锚点槽跟随基色，非锚点槽走派生（不再是旧硬编码值）。"""
        colors = self._build("syzygit")["colors"]
        assert colors["primary"] == "#0078FF"
        assert colors["navy"] == "#0A238B"
        assert colors["chip"] != self.LEGACY_ENTERPRISE_COLORS["chip"]
        for value in colors.values():
            assert value.startswith("#") and len(value) == 7

    def test_font_family_unified_to_styles_json_body(self):
        """textStyles 7 套 + tableStyles 的 fontFamily 全取 fonts.body。"""
        for style_name in ("enterprise", "bookish", "syzygit"):
            theme = self._build(style_name)
            for name, style_def in theme["textStyles"].items():
                assert style_def["fontFamily"] == "Microsoft YaHei", \
                    f"{style_name}.textStyles.{name}"
            assert theme["tableStyles"]["default"]["fontFamily"] == "Microsoft YaHei"

    def test_build_deck_output_has_no_misans(self, tmp_path):
        """build_deck 全部产物（主 pptd + pages + DESIGN_GUIDE）无 MiSans 字样。

        spec 里塞 heading/pullquote 元素，覆盖行内 fontFamily 的两条路径。
        """
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] += [
            {"type": "heading", "text": "小节标题", "level": 2},
            {"type": "pullquote", "content": "引文内容", "cite": "署名"},
        ]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"))
        for path, content in files.items():
            assert "MiSans" not in content, f"{path} 仍含 MiSans"


class TestContentPageFooterAuthor:
    """页脚左版权文案：spec.author 优先，缺省回退 Syzygit Technology。"""

    def _footer_text(self, tmp_path, author):
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        if author is None:
            spec.pop("author", None)
        else:
            spec["author"] = author
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"))
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        footer = next(e for e in page["elements"] if e["elementId"] == "footer-left")
        return footer["content"]["text"]

    def test_footer_uses_spec_author(self, tmp_path):
        assert self._footer_text(tmp_path, "蓝海集团科技集团") == "© 2026 – 蓝海集团科技集团\n"

    def test_footer_falls_back_without_author(self, tmp_path):
        assert self._footer_text(tmp_path, None) == "© 2026 – Syzygit Technology\n"


# ---------------------------------------------------------------------------
# §七 2.6：pptd 端用户文本统一过 _esc
# ---------------------------------------------------------------------------

class TestEscapePptd:
    """pptd 端用户文本（标题/正文/卡片名等）统一过 _esc。"""

    def _build_page(self, tmp_path, elements, title="转义<页>"):
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        spec["pages"][0]["title"] = title
        spec["pages"][0]["elements"] = elements
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"))
        return yaml.safe_load(files["pages/02_p01_intro.page"])

    def test_text_script_escaped(self, tmp_path):
        """text 含 <script> 转义为 &lt;script&gt;。"""
        page = self._build_page(tmp_path, [
            {"type": "text", "content": "<script>alert(1)</script>"}])
        elem = next(e for e in page["elements"]
                    if e["elementId"].startswith("elem-"))
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in elem["content"]["text"]
        assert "<script>" not in elem["content"]["text"]

    def test_cards_title_amp_escaped(self, tmp_path):
        """cards title 含 & 转义为 &amp;。"""
        page = self._build_page(tmp_path, [
            {"type": "cards", "cards": [{"title": "A&B", "body": "x"}]}])
        title_elem = next(e for e in page["elements"]
                          if e["elementId"].endswith("-1-title"))
        assert "A&amp;B" in title_elem["content"]["text"]

    def test_page_title_escaped(self, tmp_path):
        """页标题（三件套）同样转义。"""
        page = self._build_page(tmp_path, [])
        title_elem = next(e for e in page["elements"] if e["elementId"] == "title")
        assert "转义&lt;页&gt;" in title_elem["content"]["text"]

    def test_esc_is_single_source(self):
        """_esc 全项目单点：elements 定义，diagram 两处 import 同一函数。"""
        from _renderer.elements import _esc as esc_src
        from _renderer.diagram import theme as dg_theme
        from _renderer.diagram import pptd_emit as dg_pe
        assert dg_theme._esc is esc_src
        assert dg_pe._esc is esc_src


# ---------------------------------------------------------------------------
# §七 2.5 第二/三级：pptd 溢出 shrink 自动适配 + 硬截断
# ---------------------------------------------------------------------------

class TestOverflowDefense:
    """y 游标过 _CONTENT_Y_SHRINK(560) 缩排，过 _CONTENT_Y_MAX(674) 截断进 report。

    每条单条 bullets 块推进 y ≈ 42.1px（shrink 后 ≈ 34.8px）：12 块峰值 593
    （纯 shrink 不截断）；16 块时 index 13 被 shrink 救回（y≈663），
    index 14/15 超线截断。
    """

    def _build(self, tmp_path, n_blocks):
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [
            {"type": "bullets", "items": [f"要点{i}"]} for i in range(n_blocks)]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        return page, report

    @staticmethod
    def _content_elems(page):
        return [e for e in page["elements"] if e["elementId"].startswith("elem-")]

    def test_shrink_shrinks_font_and_lineheight(self, tmp_path):
        """第二级：过收缩线的 bullets 缩字号 14->12、压行距 1.65->1.4。"""
        page, report = self._build(tmp_path, 12)
        elems = self._content_elems(page)
        assert report.skipped == []  # 峰值 593 <= 674，不触发截断
        shrunk = [e for e in elems if e["content"].get("fontSize") == 12]
        assert shrunk, "过 560 线的元素应缩到 12px"
        assert all(e["content"]["lineHeight"] == 1.4 for e in shrunk)
        normal = [e for e in elems if e not in shrunk]
        assert normal and all("fontSize" not in e["content"] for e in normal)

    def test_shrink_text_keeps_lineheight(self, tmp_path):
        """text 元素 shrink 只缩字号，行距不压（任务口径：bullets 才压行距）。"""
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = (
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(11)]
            + [{"type": "text", "content": "收尾段"}])
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"))
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        text_elem = next(e for e in page["elements"]
                         if "收尾段" in e["content"]["text"])
        assert text_elem["content"]["fontSize"] == 12
        assert "lineHeight" not in text_elem["content"]

    def test_hard_cutoff_skips_and_reports(self, tmp_path):
        """第三级 + §七 2.8 d：放不下的元素整元素 skip 进 report.skipped。

        16 块时第 14 块（index 13，y≈663）可用空间 ≈11px 不足一行（12×1.3=15.6），
        不 emit 裁剪碎片、整元素 skip（"可用空间不足一行"）；skip 不推进 y 游标，
        index 14/15 同样碎片跳过。"""
        page, report = self._build(tmp_path, 16)
        assert len(report.skipped) == 3
        assert all(s["reason"] == "可用空间不足一行，内容超量请拆页"
                   for s in report.skipped)
        assert [s["index"] for s in report.skipped] == [13, 14, 15]
        assert all(s["type"] == "bullets" for s in report.skipped)
        # 发出的元素全部在内容区内
        for e in self._content_elems(page):
            assert e["bounds"][1] <= 674

    def test_fragment_skip_vs_clamp_boundary(self, tmp_path):
        """§七 2.8 d 边界：可用空间 ≥ 一行 → 裁剪保留 + warn（对照碎片 skip）。

        12 块 bullets 把 y 推到 ≈628（可用 ≈46px ≥ 15.6），再跟 4 行文本
        （shrink 后 h≈79，底 ≈707 超线）→ 裁到 ≈46px + warn，不 skip。"""
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = (
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(12)]
            + [{"type": "text", "content": "\n".join([f"第{i}行" for i in range(4)])}])
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        text_elem = next(e for e in page["elements"]
                         if "第0行" in e["content"].get("text", ""))
        y, h = text_elem["bounds"][1], text_elem["bounds"][3]
        assert h >= 12 * 1.3, "可用空间 ≥ 一行时应保留裁剪而非碎片 skip"
        assert y + h <= 674 + 1e-6
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)

    def test_normal_page_untouched(self, tmp_path):
        """普通页（少量元素）不 shrink 不截断，无显式 fontSize 覆盖。"""
        page, report = self._build(tmp_path, 3)
        assert report.skipped == []
        assert all("fontSize" not in e["content"]
                   for e in self._content_elems(page))

    def test_clamp_truncates_and_warns(self, tmp_path):
        """§七 2.8 底边防线：起点在线内、底边超线的元素裁剪高度 + warn，不 skip。

        11 块 bullets 把 y 推到 ~593，再跟 8 行表格（h=288，底 ~881）：
        表格被裁到 674-y ≈ 81，进 report.warnings，不进 skipped。"""
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = (
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(11)]
            + [{"type": "table", "headers": ["甲", "乙"],
                "rows": [["1", "2"]] * 7}])
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        table = next(e for e in page["elements"] if e["elementType"] == "table")
        y, h = table["bounds"][1], table["bounds"][3]
        assert y + h <= 674 + 1e-6, "裁剪后底边应在内容区内"
        assert h < 288, "原高 288 应被裁小"
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)

    def test_bottom_aware_shrink_upgrade(self, tmp_path):
        """§七 2.8：起点未过收缩线但底边超线的正文元素，先升 shrink 重排。

        5 块 bullets 把 y 推到 ~340（<560），再跟 12 行长文（h≈277，底≈617
        不超线——此用例验证的是底边超线触发：直接造 y≈470、11 行文本）。"""
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = _minimal_spec_dict()
        long_text = "\n".join([f"第{i}行内容" for i in range(11)])  # 11 行
        spec["pages"][0]["elements"] = (
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(8)]
            + [{"type": "text", "content": long_text}])
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        text_elem = next(e for e in page["elements"]
                         if "第0行内容" in e["content"].get("text", ""))
        y = text_elem["bounds"][1]
        assert y <= 560, "该元素起点应在收缩线之下（本例 ~467）"
        assert text_elem["content"]["fontSize"] == 12, "底边超线应触发 shrink 升档"
        assert y + text_elem["bounds"][3] <= 674 + 1e-6


# ---------------------------------------------------------------------------
# §七 2.8：pullquote 页底防线（与 text/bullets 同款三档）
# ---------------------------------------------------------------------------

class TestPullquoteOverflowDefense:
    """pullquote 底边防线：底边超线先 shrink（引文 18->16），仍超 _clamp_bottom
    裁切 + warn，可用不足一行整元素 skip，y 游标过线走第三级硬防线。"""

    def _build(self, tmp_path, elements):
        import _pptd_gen
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = elements
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        return page, report

    @staticmethod
    def _pq_elems(page):
        return [e for e in page["elements"]
                if str(e["elementId"]).startswith("pullquote-")]

    def test_bottom_over_triggers_shrink(self, tmp_path):
        """底边预估超线先升 shrink：引文 18->16 重排后放下，不裁不 skip。

        8 块 bullets 推 y≈467（<560 收缩线）；7 行引文 18pt 底≈679 超线，
        16pt 底≈660 放下。"""
        page, report = self._build(tmp_path,
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(8)]
            + [{"type": "pullquote", "content": "引" * 427, "cite": "— 来源"}])
        quote = next(e for e in self._pq_elems(page)
                     if e["elementId"].endswith("-text"))
        assert quote["content"]["fontSize"] == 16, "底边超线应触发引文 shrink 18->16"
        assert quote["bounds"][1] + quote["bounds"][3] <= 674 + 1e-6
        assert report.skipped == []
        assert not any("高度裁切防溢出" in w for w in report.warnings)

    def test_still_over_clamped_with_warn(self, tmp_path):
        """shrink 后仍超线：整组裁到可用高度 + warn，署名放不下只发引文。

        12 块 bullets 推 y≈628；3 行引文 shrink 后底≈731 仍超线 →
        裁到可用 ≈46（≥ 一行 16×1.3=20.8）+ warn；署名连一行引文放不下被舍弃。"""
        page, report = self._build(tmp_path,
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(12)]
            + [{"type": "pullquote", "content": "引" * 150, "cite": "— 来源"}])
        elems = self._pq_elems(page)
        assert elems, "可用 ≥ 一行应裁剪保留而非 skip"
        bar = next(e for e in elems if e["elementId"].endswith("-bar"))
        assert bar["bounds"][1] + bar["bounds"][3] <= 674 + 1e-6
        assert not any(e["elementId"].endswith("-cite") for e in elems), \
            "裁切后署名放不下应舍弃（warn 已记录）"
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)

    def test_less_than_one_line_skips(self, tmp_path):
        """可用空间不足一行（< 16×1.3=20.8）：整元素 skip 进 report，不 emit 碎片。

        16 块 bullets 时 index 13-15 已被裁切档 skip，y 停在 ≈663（可用 ≈11）。"""
        page, report = self._build(tmp_path,
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(16)]
            + [{"type": "pullquote", "content": "引文", "cite": "— 来源"}])
        assert self._pq_elems(page) == []
        pq_skips = [s for s in report.skipped if s["type"] == "pullquote"]
        assert len(pq_skips) == 1
        assert pq_skips[0]["reason"] == "可用空间不足一行，内容超量请拆页"
        assert pq_skips[0]["index"] == 16

    def test_y_cursor_past_max_hard_skip(self, tmp_path):
        """y 游标越过 674（第三级硬防线）：pullquote 整元素 skip("页面溢出截断")。

        12 块 bullets + 4 行文本（裁切档保留，y 推进到 ≈686）后 y>674。"""
        page, report = self._build(tmp_path,
            [{"type": "bullets", "items": [f"要点{i}"]} for i in range(12)]
            + [{"type": "text", "content": "\n".join([f"第{i}行" for i in range(4)])}]
            + [{"type": "pullquote", "content": "引文", "cite": "— 来源"}])
        assert self._pq_elems(page) == []
        pq_skips = [s for s in report.skipped if s["type"] == "pullquote"]
        assert len(pq_skips) == 1
        assert pq_skips[0]["reason"] == "页面溢出截断"


# ---------------------------------------------------------------------------
# §七 2.8 d：cards/phases 整组 clamp 路径补"可用不足一行整组 skip"档
# ---------------------------------------------------------------------------

class TestCardsPhasesGroupSkip:
    """cards/phases：可用高度 < 一行卡正文（13pt×1.55≈20.2）时整组 skip，
    不发压碎碎片；≥ 一行仍走原 clamp + warn。"""

    def test_cards_less_than_one_line_group_skip(self):
        import _pptd_gen
        from _renderer.elements import RenderReport
        report = RenderReport()
        elements = []
        card_h, consumed = _pptd_gen._emit_cards(
            elements, [{"title": "t", "body": "b"}], 80, 654, 1120,
            max_h=20, report=report, page_id="p1", index=3)
        assert (card_h, consumed) == (0, 0), "可用 20px（< 20.2）应整组 skip"
        assert elements == [], "skip 不 emit 压碎碎片"
        assert len(report.skipped) == 1
        assert report.skipped[0]["type"] == "cards"
        assert report.skipped[0]["index"] == 3
        assert report.skipped[0]["reason"] == "可用空间不足一行，内容超量请拆页"
        assert not report.warnings

    def test_phases_less_than_one_line_group_skip(self):
        import _pptd_gen
        from _renderer.elements import RenderReport
        report = RenderReport()
        elements = []
        phase_h = _pptd_gen._emit_phases(
            elements, [{"name": "P1", "desc": "d1"}], 80, 654, 1120,
            max_h=20, report=report, page_id="p1", index=5)
        assert phase_h == 0, "可用 20px（< 20.2）应整组 skip"
        assert elements == []
        assert len(report.skipped) == 1
        assert report.skipped[0]["type"] == "phases"
        assert report.skipped[0]["index"] == 5
        assert report.skipped[0]["reason"] == "可用空间不足一行，内容超量请拆页"

    def test_cards_clamp_keeps_group_with_warn(self):
        """可用 54（≥ 一行）：整组裁切保留 + warn，卡底贴 674 防线裁剪线。"""
        import _pptd_gen
        from _renderer.elements import RenderReport
        report = RenderReport()
        elements = []
        card_h, consumed = _pptd_gen._emit_cards(
            elements, [{"title": "t", "body": "长" * 100}], 80, 620, 1120,
            max_h=54, report=report, page_id="p1", index=0)
        assert card_h == 54 and consumed == 1
        assert elements, "≥ 一行应裁剪保留而非 skip"
        card = next(e for e in elements if e["elementId"] == "card-620-1")
        assert card["bounds"][1] + card["bounds"][3] == 674
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# §七 2.4：elementId y 坐标口径统一 int
# ---------------------------------------------------------------------------

class TestElementIdInt:
    """text/pullquote/table 的 elementId 带 int(y) 前缀，float 全精度不再泄进 ID。"""

    def test_ids_carry_int_y(self, tmp_path):
        import re
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [
            {"type": "pullquote", "content": "短引文", "cite": "— 来源"},
            {"type": "text", "content": "第一段"},
            {"type": "text", "content": "第二段"},
        ]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"))
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        content_ids = [e["elementId"] for e in page["elements"]
                       if e["elementId"] not in ("title", "footer-left", "footer-right")]
        assert content_ids, "应有内容元素"
        for eid in content_ids:
            assert "." not in eid, f"elementId 不得带 float 小数: {eid}"
            assert re.match(r"^(elem|pullquote)-\d+", eid), f"ID 口径: {eid}"


# ---------------------------------------------------------------------------
# 版式改进：页级填充（_fill_content_area）
# ---------------------------------------------------------------------------

class TestContentFill:
    """页级填充：内容 <75% 纵向放大到 ~88%；饱满页零变化；fontSize 安全阀。"""

    FIXED_IDS = ("title", "header-logo", "footer-left", "footer-right")

    def _build(self, tmp_path, elements, report=None):
        import _pptd_gen
        from _renderer import _resolve_style
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = elements
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        return yaml.safe_load(files["pages/02_p01_intro.page"]), files

    @classmethod
    def _content(cls, page):
        return [e for e in page["elements"] if e["elementId"] not in cls.FIXED_IDS]

    @staticmethod
    def _bottom(elems):
        return max(float(e["bounds"][1]) + float(e["bounds"][3]) for e in elems)

    def test_sparse_phases_page_fills_to_target(self, tmp_path):
        """稀疏页（5 张 phase 卡）按限速 2.0 拉伸：内容高 110 -> 底边 130+220=350，
        页出口 4px 网格吸附后为 352（间距体系 v1）。

        限速口径（视觉抽查反馈）：目标 88% 需 s=4.48，超 _FILL_MAX_SCALE=2.0，
        停在 2 倍接受留白，不再追求底边 ~623。
        """
        page, _ = self._build(tmp_path, [
            {"type": "phases",
             "phases": [{"name": f"阶段{i}", "desc": "短"} for i in range(5)]}])
        bottom = self._bottom(self._content(page))
        assert bottom == pytest.approx(352.0, abs=0.5), \
            f"cap 2.0 下底边 {bottom} 应 = 352（350 吸附后）"
        assert bottom <= 674

    def test_fill_keeps_group_relative_layout(self, tmp_path):
        """组内相对位置保持：卡片横排 x/w 不变，组内偏移与卡高同比放大。"""
        page, _ = self._build(tmp_path, [
            {"type": "phases",
             "phases": [{"name": f"阶段{i}", "desc": "短"} for i in range(5)]}])
        shapes = {e["elementId"]: e for e in page["elements"]}
        card, card2 = shapes["phase-130-1"], shapes["phase-130-2"]
        name = shapes["phase-130-1-name"]
        s = 2.0  # 内容高 110（min 卡高），492.8/110=4.48 被 _FILL_MAX_SCALE 限速
        # 横排布局不变：x/w 与发射时一致（内容区左缘 80），卡间距 24 不变
        assert card["bounds"][0] == 80
        gap = card2["bounds"][0] - (card["bounds"][0] + card["bounds"][2])
        assert abs(gap - 24) < 1
        # 组内偏移同比：name 相对卡顶 10px -> 10×s；卡高 110 -> 110×s
        # （页出口 4px 网格吸附给 y/h 引入 ±GRID 偏差，间距体系 v1）
        assert name["bounds"][1] - card["bounds"][1] == pytest.approx(10 * s, abs=4.5)
        assert card["bounds"][3] == pytest.approx(110 * s, abs=4.5)

    def test_fill_never_touches_font_size(self, tmp_path):
        """安全阀：拉伸只撑盒子，fontSize/样式引用不变。"""
        page, _ = self._build(tmp_path, [
            {"type": "pullquote", "content": "模型是天花板", "cite": "- 共识"},
            {"type": "cards", "cards": [{"title": "卡", "body": "短"}]},
        ])
        texts = [e for e in self._content(page) if e["elementType"] == "text"]
        quote = next(e for e in texts if e["elementId"].endswith("-text"))
        cite = next(e for e in texts if e["elementId"].endswith("-cite"))
        assert quote["content"]["fontSize"] == 18
        assert cite["content"]["fontSize"] == 12
        # 卡片标题仍走样式引用，未被写入显式 fontSize
        card_title = next(e for e in texts if e["elementId"].endswith("-1-title"))
        assert "fontSize" not in card_title["content"]
        # 三件套不动（bounds 为 4px 网格吸附后值，间距体系 v1）
        title = next(e for e in page["elements"] if e["elementId"] == "title")
        assert title["bounds"] == [80, 56, 1120, 44]

    def test_full_page_zero_change(self, tmp_path):
        """饱满页（填充 >75%）填充零变化：bounds 仅经页出口 4px 网格吸附
        （发射 130 -> 128，间距体系 v1），无填充拉伸。"""
        page, _ = self._build(tmp_path, [
            {"type": "bullets", "items": [f"要点{i}"]} for i in range(12)])
        content = self._content(page)
        # 12 块单条 bullets 峰值底边 ≈593（>75% 阈值 550），不触发填充
        assert 550 <= self._bottom(content) <= 674
        first = next(e for e in content if e["elementId"] == "elem-130")
        assert first["bounds"][1] == 128  # 发射 130 经 4px 网格吸附
        assert first["bounds"][3] == 32  # 发射 30.1 经角吸附（底边 160.1 -> 160）

    def test_fill_lint_zero_issue(self, tmp_path):
        """填充后 lint 零 error 零 warning（防填充引入溢出/重叠）。"""
        import _layout_lint
        _, files = self._build(tmp_path, [
            {"type": "text", "content": "引言段。"},
            {"type": "phases",
             "phases": [{"name": f"阶段{i}", "desc": "短"} for i in range(5)]},
            {"type": "cards", "cards": [{"title": f"卡{i}", "body": "短"} for i in range(3)]},
            {"type": "table", "headers": ["甲", "乙"], "rows": [["1", "2"]]},
            {"type": "pullquote", "content": "收尾引文", "cite": "- 出处"},
        ])
        issues = _layout_lint.lint_pptd_files(files)
        assert not issues, "填充后 lint 应零 issue：\n" + _layout_lint.format_issues(issues)

    def test_diagram_group_uniform_scale_keeps_aspect(self, tmp_path):
        """diagram 组（dg- 前缀）均匀缩放：宽高比不变 + 倍率上限 1.6 + 水平居中。"""
        import _pptd_gen
        # 合成 dg 组：椭圆 200×100（若被纵向拉伸压扁，宽高比立即失真可检出）
        elems = [
            {"elementId": "dg130-e0", "elementType": "shape",
             "bounds": [242.0, 130.0, 200.0, 100.0], "shapeName": "ellipse",
             "fill": {"type": "solid", "color": "$chip"}},
            {"elementId": "dg130-e0-t", "elementType": "text",
             "bounds": [242.0, 160.0, 200.0, 40.0],
             "content": {"fontSize": 13, "text": "节点\n"}},
        ]
        _pptd_gen._fill_content_area(elems)
        e0, t = elems
        # 宽高比不变（均匀缩放，未压扁）；s = min(page_s, 1120/200, 1.6) = 1.6
        assert e0["bounds"][2] / e0["bounds"][3] == pytest.approx(2.0, abs=0.01)
        assert e0["bounds"][2] == pytest.approx(320.0, abs=0.05)
        # 水平居中：组中心 = 80 + 1120/2 = 640
        assert e0["bounds"][0] + e0["bounds"][2] / 2 == pytest.approx(640.0, abs=0.05)
        # 字号安全阀：diagram 放大不动 fontSize
        assert t["content"]["fontSize"] == 13

    def test_real_diagram_sparse_page_no_distortion(self, tmp_path):
        """真实 sequence 图 + 稀疏页：dg 元素宽高比逐元素保持，组宽顶到 1120 居中。"""
        diagram = {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
                   "title": "报销流程",
                   "steps": [{"label": "开始", "type": "start"},
                             {"label": "提交", "desc": "录入"},
                             {"label": "审批"},
                             {"label": "结束", "type": "end"}]}
        page, _ = self._build(tmp_path, [
            {"type": "text", "content": "流程说明。"}, diagram])
        # 参照：同一 diagram 在未填充页的原始几何（text 后 y 游标 = 130+23.1+12）
        import _renderer.diagram as dgmod
        raw, _ = dgmod.render_diagram_pptd(diagram, 80, 165.1, 1120)

        def _flat(elems):
            out = []
            for e in elems:
                out.append(e)
                out.extend(_flat(e.get("children") or []))
            return out
        # 校验实际形状（跳过 group 包围盒：其含角标 pad，snap 四角吸附下
        # 宽高比有固有抖动，不代表形状失真）
        raw_flat = [e for e in _flat(raw) if e.get("elementType") != "group"]
        raw_ratio = {e["elementId"]: float(e["bounds"][2]) / float(e["bounds"][3])
                     for e in raw_flat
                     if float(e["bounds"][2]) >= 5 and float(e["bounds"][3]) >= 5}
        dg_elems = [e for e in _flat(page["elements"])
                    if str(e.get("elementId", "")).startswith("dg")
                    and e.get("elementType") != "group"]
        assert dg_elems, "diagram 元素应已发射"
        for e in dg_elems:
            eid = e["elementId"]
            ew, eh = float(e["bounds"][2]), float(e["bounds"][3])
            # 连接符等近零尺寸元素的比例对 round 敏感，只校验有真实面积的元素；
            # 4px 网格吸附给小元素比例引入 ±2px/边 噪声（间距体系 v1），
            # min 边 < 40 的小元素放宽，其余容差 0.05（仍能检出纵向拉伸压扁）
            if eid in raw_ratio and ew >= 40 and eh >= 40:
                assert ew / eh == pytest.approx(raw_ratio[eid], abs=0.05), \
                    f"{eid} 宽高比失真"
        # 所有 dg 元素底边不超线
        for e in dg_elems:
            assert float(e["bounds"][1]) + float(e["bounds"][3]) <= 674.01
        # 组被均匀放大到内容区宽并居中（原组宽 1045.4 < 1120，宽度约束生效）
        gx0 = min(float(e["bounds"][0]) for e in dg_elems)
        gx1 = max(float(e["bounds"][0]) + float(e["bounds"][2]) for e in dg_elems)
        assert gx1 - gx0 == pytest.approx(1120.0, abs=0.5)
        assert (gx0 + gx1) / 2 == pytest.approx(640.0, abs=0.5)


# ---------------------------------------------------------------------------
# I-16：diagram 分支接入页底防线（均匀缩放 / 整图 skip）
# ---------------------------------------------------------------------------

class TestDiagramBottomDefense:
    """I-16：diagram 超高先均匀缩放压回界内；缩到 0.5 仍超则整图 skip 进 report。"""

    def _build_with_fake_diagram(self, tmp_path, monkeypatch, dg_h):
        import _pptd_gen
        import _renderer.diagram as dgmod
        from _renderer import _resolve_style
        from _renderer.elements import RenderReport
        fake_elems = [
            {"elementId": "dg130-box", "elementType": "shape",
             "bounds": [80.0, 130.0, 800.0, float(dg_h)], "shapeName": "roundRect",
             "fill": {"type": "solid", "color": "$card"}},
            {"elementId": "dg130-box-t", "elementType": "text",
             "bounds": [80.0, 130.0, 800.0, 40.0],
             "content": {"fontSize": 13, "text": "节点\n"}},
        ]

        def fake_render(elem, x, y, w, style=None, v2_theme=None):
            return [dict(e, bounds=list(e["bounds"])) for e in fake_elems], dg_h

        monkeypatch.setattr(dgmod, "render_diagram_pptd", fake_render)
        spec = _minimal_spec_dict()
        spec["pages"][0]["elements"] = [
            {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
             "title": "占位", "steps": [{"label": "a"}]}]
        spec_path = _write_spec(tmp_path, spec)
        spec_dict = _pptd_gen.load_spec(spec_path)
        report = RenderReport()
        files, _ = _pptd_gen.build_deck(
            spec_dict, spec_path, _resolve_style("enterprise"), "deck",
            str(tmp_path / "out"), report=report)
        page = yaml.safe_load(files["pages/02_p01_intro.page"])
        return page, files, report

    def test_over_tall_diagram_shrinks_into_bounds(self, tmp_path, monkeypatch):
        """高 600（可用 544）：均匀缩小 0.907 压回界内 + warn，宽高比不变。"""
        page, files, report = self._build_with_fake_diagram(tmp_path, monkeypatch, 600)
        box = next(e for e in page["elements"] if e["elementId"] == "dg130-box")
        x, y, w, h = [float(v) for v in box["bounds"]]
        assert y + h <= 674.01, "缩放后底边应回界内"
        assert w / h == pytest.approx(800 / 600, abs=0.01), "缩放应均匀（宽高比不变）"
        assert report.skipped == []
        assert any("防溢出" in w_ for w_ in report.warnings)
        # 字号同比缩小（13 × 0.907 ≈ 11.8），防缩盒后文本溢出
        text = next(e for e in page["elements"] if e["elementId"] == "dg130-box-t")
        assert text["content"]["fontSize"] == pytest.approx(11.8, abs=0.1)
        # 防线产物过 lint：零 error
        import _layout_lint
        errors = [i for i in _layout_lint.lint_pptd_files(files) if i.severity == "error"]
        assert not errors

    def test_beyond_half_scale_skips_diagram(self, tmp_path, monkeypatch):
        """高 1200（缩 0.45 < 0.5 仍超）：整图 skip 进 report，不 emit。"""
        page, _, report = self._build_with_fake_diagram(tmp_path, monkeypatch, 1200)
        assert not any(str(e.get("elementId", "")).startswith("dg")
                       for e in page["elements"]), "放不下的 diagram 不应 emit"
        assert len(report.skipped) == 1
        assert report.skipped[0]["type"] == "diagram"
        assert "拆页" in report.skipped[0]["reason"]

    def test_in_bounds_diagram_no_defense_warn(self, tmp_path, monkeypatch):
        """高 300 未超线：无 warn 无 skip；页级填充按 dg 组均匀放大居中。"""
        page, _, report = self._build_with_fake_diagram(tmp_path, monkeypatch, 300)
        assert report.skipped == []
        assert not any("防溢出" in w_ for w_ in report.warnings)
        box = next(e for e in page["elements"] if e["elementId"] == "dg130-box")
        x, y, w, h = [float(v) for v in box["bounds"]]
        assert w / h == pytest.approx(800 / 300, abs=0.03), \
            "填充放大应均匀（±0.03 为 4px 网格吸附噪声，间距体系 v1）"
        # 宽度约束 s = min(page_s, 1.6, 1120/800=1.4) -> 组宽顶满 1120 且居中
        assert w == pytest.approx(1120.0, abs=0.5)
        assert x == pytest.approx(80.0, abs=0.5)
        assert y + h <= 674.01
        # 填充 pass 不动字号（与 I-16 缩盒不同）
        text = next(e for e in page["elements"] if e["elementId"] == "dg130-box-t")
        assert text["content"]["fontSize"] == 13
