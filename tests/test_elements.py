# -*- coding: utf-8 -*-
"""_renderer.elements 元素协议层测试（重构 Phase 1，§6.1）。"""

from _renderer.elements import (
    CAPABILITIES,
    DEGRADE,
    ENDS,
    RENDER,
    RenderReport,
    _nl2br,
    degrade_text,
    empty_payload_reason,
    is_empty_payload,
    normalize_bullets,
    normalize_cards,
    normalize_element,
    normalize_heading,
    normalize_phases,
    normalize_pullquote,
    normalize_table,
    normalize_text,
)
from _renderer.schema import KNOWN_ELEMENT_TYPES


class TestCapabilities:
    """能力矩阵：覆盖全部已知元素，取值合法，降级格与设计一致。"""

    def test_covers_all_known_types(self):
        """CAPABILITIES 覆盖 KNOWN_ELEMENT_TYPES 全部 31 种，不多不少。"""
        assert set(CAPABILITIES) == set(KNOWN_ELEMENT_TYPES)
        assert len(CAPABILITIES) == 31  # 27 + B-3/B-4/B-5/B-6 四个批次 B 组件

    def test_values_are_legal(self):
        """每种元素恰好声明三端，取值只能是 render/degrade。"""
        for elem_type, caps in CAPABILITIES.items():
            assert set(caps) == set(ENDS), elem_type
            for end, cap in caps.items():
                assert cap in (RENDER, DEGRADE), (elem_type, end)

    def test_base_types_render_everywhere(self):
        """7 种基础元素三端全 render（含本次补齐的 pullquote.docx、heading.html/pptd）。"""
        for elem_type in ("text", "bullets", "cards", "table", "phases",
                          "pullquote", "heading"):
            for end in ENDS:
                assert CAPABILITIES[elem_type][end] == RENDER, (elem_type, end)

    def test_degrade_cells(self):
        """architecture_4a 仅 docx render；diagram/placeholder 仅 docx degrade。"""
        assert CAPABILITIES["architecture_4a"] == {
            "html": DEGRADE, "docx": RENDER, "pptd": DEGRADE,
        }
        assert CAPABILITIES["diagram"] == {
            "html": RENDER, "docx": DEGRADE, "pptd": RENDER,
        }
        assert CAPABILITIES["product_intro_placeholder"] == {
            "html": RENDER, "docx": DEGRADE, "pptd": RENDER,
        }


class TestNormalizeText:
    def test_content_canonical(self):
        assert normalize_text({"content": "正文"}) == {"content": "正文", "role": ""}

    def test_text_compat(self):
        """旧写法 text 字段兼容到 content。"""
        assert normalize_text({"text": "旧字段"}) == {"content": "旧字段", "role": ""}

    def test_content_priority_over_text(self):
        assert normalize_text({"content": "新", "text": "旧"})["content"] == "新"

    def test_role_and_defaults(self):
        assert normalize_text({"content": "x", "role": "lead"})["role"] == "lead"
        assert normalize_text({}) == {"content": "", "role": ""}

    def test_none_content_is_empty(self):
        assert normalize_text({"content": None})["content"] == ""


class TestNormalizeBullets:
    def test_items(self):
        assert normalize_bullets({"items": ["a", "b"]}) == {"items": ["a", "b"]}

    def test_non_str_items_to_str(self):
        assert normalize_bullets({"items": [1, 2.5, None]}) == {
            "items": ["1", "2.5", "None"],
        }

    def test_missing_items(self):
        assert normalize_bullets({}) == {"items": []}


class TestNormalizeCards:
    def test_four_keys_complete(self):
        """每张卡四键齐全，缺省 ""。"""
        result = normalize_cards({"cards": [{"title": "T"}]})
        assert result == {"cards": [
            {"title": "T", "body": "", "tag": "", "highlight": ""},
        ]}

    def test_tag_highlight_preserved(self):
        """HTML 端在用的 tag/highlight 不丢。"""
        result = normalize_cards({"cards": [
            {"title": "T", "body": "B", "tag": "重点", "highlight": "省 30%"},
        ]})
        card = result["cards"][0]
        assert card["tag"] == "重点"
        assert card["highlight"] == "省 30%"

    def test_missing_and_non_dict(self):
        assert normalize_cards({}) == {"cards": []}
        # 非 dict 项不抛异常，归一为四空键
        assert normalize_cards({"cards": ["坏项"]}) == {"cards": [
            {"title": "", "body": "", "tag": "", "highlight": ""},
        ]}


class TestNormalizeTable:
    def test_basic(self):
        result = normalize_table({
            "headers": ["列1", "列2"],
            "rows": [["a", "b"], ["c", "d"]],
        })
        assert result == {"headers": ["列1", "列2"],
                          "rows": [["a", "b"], ["c", "d"]]}

    def test_non_str_cells_to_str(self):
        """rows 非 str 元素（int/None）统一转 str。"""
        result = normalize_table({
            "headers": [1, 2],
            "rows": [[1, None], [3, 4]],
        })
        assert result["headers"] == ["1", "2"]
        assert result["rows"] == [["1", "None"], ["3", "4"]]

    def test_scalar_row_wrapped(self):
        """非列表的 row 不抛异常，包成单格行。"""
        result = normalize_table({"headers": ["h"], "rows": ["单行"]})
        assert result["rows"] == [["单行"]]

    def test_missing(self):
        assert normalize_table({}) == {"headers": [], "rows": []}


class TestNormalizePhases:
    """phases 三套历史写法 + milestones 写法全部归一到 name/desc/actions。"""

    def test_html_docx_legacy_label_goal(self):
        """HTML/DOCX 旧写法 label/goal/actions。"""
        result = normalize_phases({"phases": [
            {"label": "一期", "goal": "上线", "actions": ["调研", "开发"]},
        ]})
        assert result == {"phases": [
            {"name": "一期", "desc": "上线", "actions": ["调研", "开发"]},
        ]}

    def test_pptd_legacy_name_desc(self):
        """PPTD 旧写法 name/desc（无 actions 时缺省 []）。"""
        result = normalize_phases({"phases": [
            {"name": "二期", "desc": "推广"},
        ]})
        assert result == {"phases": [
            {"name": "二期", "desc": "推广", "actions": []},
        ]}

    def test_outline_to_spec_legacy_phase_title_items(self):
        """outline-to-spec 旧写法 phase/title/items（重构计划 §二 B3）。"""
        result = normalize_phases({"phases": [
            {"phase": "第一阶段", "title": "蓝图规划", "duration": "4周",
             "items": ["现状调研"]},
        ]})
        phase = result["phases"][0]
        assert phase["name"] == "第一阶段"
        assert phase["desc"] == ""
        assert phase["actions"] == ["现状调研"]

    def test_milestones_label_desc(self):
        """真实 spec 的 milestones 写法 label+desc 也归一。"""
        result = normalize_phases({"phases": [
            {"label": "M1", "desc": "蓝图确认"},
        ]})
        assert result == {"phases": [
            {"name": "M1", "desc": "蓝图确认", "actions": []},
        ]}

    def test_canonical_wins(self):
        """正典 name/desc 优先于兼容字段。"""
        result = normalize_phases({"phases": [
            {"name": "正典", "label": "旧", "desc": "新", "goal": "旧"},
        ]})
        assert result["phases"][0]["name"] == "正典"
        assert result["phases"][0]["desc"] == "新"

    def test_missing_and_bad_items(self):
        assert normalize_phases({}) == {"phases": []}
        # 非 dict 项不抛异常
        assert normalize_phases({"phases": [None]}) == {"phases": [
            {"name": "", "desc": "", "actions": []},
        ]}


class TestNormalizePullquote:
    def test_basic(self):
        result = normalize_pullquote({"content": "引文", "cite": "张三"})
        assert result == {"content": "引文", "cite": "张三"}

    def test_defaults(self):
        assert normalize_pullquote({}) == {"content": "", "cite": ""}


class TestNormalizeHeading:
    def test_text_canonical(self):
        assert normalize_heading({"text": "小节", "level": 3}) == {
            "text": "小节", "level": 3,
        }

    def test_title_content_compat(self):
        assert normalize_heading({"title": "T"})["text"] == "T"
        assert normalize_heading({"content": "C"})["text"] == "C"

    def test_level_default_2(self):
        assert normalize_heading({"text": "x"})["level"] == 2

    def test_level_clamped_to_1_7(self):
        assert normalize_heading({"text": "x", "level": 0})["level"] == 1
        assert normalize_heading({"text": "x", "level": 9})["level"] == 7

    def test_bad_level_falls_back_to_2(self):
        assert normalize_heading({"text": "x", "level": "abc"})["level"] == 2


class TestNormalizeElement:
    def test_dispatch(self):
        """有 normalize 的 7 种元素走分派。"""
        elem_type, normalized = normalize_element({"type": "text", "text": "旧"})
        assert elem_type == "text"
        assert normalized == {"content": "旧", "role": ""}

    def test_special_types_returned_as_is(self):
        """diagram/placeholder/architecture_4a 不标准化，返回原 dict。"""
        for t in ("diagram", "product_intro_placeholder", "architecture_4a"):
            elem = {"type": t, "title": "X", "custom": [1]}
            elem_type, normalized = normalize_element(elem)
            assert elem_type == t
            assert normalized is elem

    def test_unknown_type_returned_as_is(self):
        elem = {"type": "tree", "foo": 1}
        elem_type, normalized = normalize_element(elem)
        assert elem_type == "tree"
        assert normalized is elem

    def test_non_dict_input(self):
        assert normalize_element("坏") == ("", {})


class TestDegradeText:
    def test_architecture_4a(self):
        for end in ("html", "pptd"):
            assert degrade_text("architecture_4a", {}, end) == \
                "[4A 架构图] 本节内容请见 Word 版"

    def test_diagram_with_title(self):
        text = degrade_text("diagram", {"title": "集成架构"}, "docx")
        assert text == "[架构图：集成架构] 请见 HTML/PPT 版"

    def test_diagram_without_title(self):
        assert degrade_text("diagram", {}, "docx") == \
            "[架构图：未命名] 请见 HTML/PPT 版"

    def test_product_intro_placeholder(self):
        assert degrade_text(
            "product_intro_placeholder", {"title": "产品介绍"}, "docx"
        ) == "[产品介绍占位：产品介绍]"

    def test_unknown_type(self):
        assert degrade_text("tree", {}, "docx") == "[不支持的元素类型：tree]"


class TestRenderReport:
    def test_empty_report_has_no_issues(self):
        report = RenderReport()
        assert not report.has_issues()
        assert "跳过 0 元素 / 降级 0 元素 / 警告 0 条" in report.summary()

    def test_accumulation(self):
        """skip/degrade/warn 逐条累计，字段齐全。"""
        report = RenderReport()
        report.skip("p1", 0, "tree", "未知元素类型")
        report.skip("p1", 2, "cards", "cards 为空")
        report.degrade("p2", 1, "diagram", "docx", "[架构图：X] 请见 HTML/PPT 版")
        report.warn("p3 内容超限")

        assert len(report.skipped) == 2
        assert report.skipped[0] == {
            "page": "p1", "index": 0, "type": "tree", "reason": "未知元素类型",
        }
        assert report.degraded[0] == {
            "page": "p2", "index": 1, "type": "diagram", "target": "docx",
            "message": "[架构图：X] 请见 HTML/PPT 版",
        }
        assert report.warnings == ["p3 内容超限"]
        assert report.has_issues()

    def test_summary_output(self):
        """summary 首行计数 + 逐条明细。"""
        report = RenderReport()
        report.skip("p1", 0, "tree", "未知元素类型")
        report.skip("p1", 2, "cards", "cards 为空")
        report.degrade("p2", 1, "diagram", "docx", "降级文本")
        for i in range(3):
            report.warn(f"警告{i}")

        summary = report.summary()
        assert "跳过 2 元素 / 降级 1 元素 / 警告 3 条" in summary
        assert "[跳过] p1 elements[0] tree: 未知元素类型" in summary
        assert "[降级] p2 elements[1] diagram -> docx: 降级文本" in summary
        assert "[警告] 警告2" in summary


class TestIsEmptyPayloadTable:
    """table 空载荷口径：headers 或 rows 任一缺失/空即空载荷。

    旧口径要求 headers 和 rows 都空才算空，rows-only/headers-only 的半边
    表格在 HTML 端 `return ""` 静默丢弃（不进 report）。
    """

    def test_rows_only_is_empty(self):
        """headers 空但 rows 非空也计空载荷。"""
        assert is_empty_payload("table", {"headers": [], "rows": [["a"]]})

    def test_headers_only_is_empty(self):
        assert is_empty_payload("table", {"headers": ["列"], "rows": []})

    def test_both_empty_is_empty(self):
        assert is_empty_payload("table", {"headers": [], "rows": []})

    def test_missing_keys_is_empty(self):
        assert is_empty_payload("table", {})

    def test_full_table_not_empty(self):
        assert not is_empty_payload(
            "table", {"headers": ["列"], "rows": [["a"]]})


class TestEmptyPayloadReason:
    def test_table_specific_reason(self):
        assert empty_payload_reason("table") == "表格缺 headers 或 rows"

    def test_generic_reason(self):
        assert empty_payload_reason("text") == \
            "内容为空（可能字段名错误或空元素）"


class TestNl2br:
    r"""_nl2br：字面 \n 与真实换行统一 <br>；\\n 保留字面；\r 清除；先 _esc。"""

    def test_literal_backslash_n_to_br(self):
        r"""字面 \n（单反斜杠+n，YAML 单引号写法）转 <br>。"""
        assert _nl2br("第一行\\n第二行") == "第一行<br>第二行"

    def test_real_newline_to_br(self):
        assert _nl2br("第一行\n第二行") == "第一行<br>第二行"

    def test_double_backslash_n_kept_literal(self):
        r"""\\n（双反斜杠+n）不误拆成换行，恢复为字面 \n。"""
        assert _nl2br("a\\\\nb") == "a\\nb"
        assert "<br>" not in _nl2br("a\\\\nb")

    def test_windows_path_not_eaten(self):
        r"""Windows 路径写法 C:\\new\dir 的字面 \n 不被吃成换行。"""
        assert _nl2br("C:\\\\new\\dir") == "C:\\new\\dir"

    def test_cr_cleared(self):
        assert _nl2br("a\r\nb") == "a<br>b"
        assert _nl2br("a\rb") == "ab"

    def test_esc_before_br(self):
        """先 _esc 再替换：尖括号被转义，换行仍转 <br>（保持现状顺序）。"""
        assert _nl2br("<b>x</b>\n") == "&lt;b&gt;x&lt;/b&gt;<br>"

    def test_mixed_literal_and_real(self):
        r"""字面 \n 与真实换行混排统一 <br>。"""
        assert _nl2br("a\\nb\nc") == "a<br>b<br>c"
