# -*- coding: utf-8 -*-
"""schema 全量校验测试（重构 Phase 1，§6.2）。

覆盖：
- 8 种基础元素：合法样本零误报 + 非法样本（缺必填/结构错误）报错
- table 行列不齐指名行号
- 未知 type（含缺 type 键）报错且消息含合法值列表
- KNOWN_ELEMENT_TYPES 与 elements.CAPABILITIES 键集一致（单一事实源）
- 现存真实 spec（output/、_knowledge/clients/ 下 *spec*.yml）跑 validate_spec
  零误报：仅 MRO 旧 spec 的 9 个无 type 元素报错（这正是目的）
- Renderer init 的校验错误进 report.warnings（不再 try/except 吞掉）
"""

import glob
import os
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.elements import CAPABILITIES
from _renderer.schema import KNOWN_ELEMENT_TYPES, validate_element, validate_spec


# ---------------------------------------------------------------------------
# 样例
# ---------------------------------------------------------------------------

VALID_ELEMENTS = [
    # text：content 正典 / text 兼容
    {"type": "text", "content": "正文"},
    {"type": "text", "text": "旧字段写法"},
    # bullets
    {"type": "bullets", "items": ["甲", "乙"]},
    # cards：body/tag/highlight 均可缺省，title 必填
    {"type": "cards", "cards": [{"title": "卡一"}, {"title": "卡二", "body": "体"}]},
    # table
    {"type": "table", "headers": ["列1", "列2"], "rows": [["a", "b"], ["c", "d"]]},
    # phases：正典 name/desc + 旧写法 label/goal
    {"type": "phases", "phases": [{"name": "一期", "desc": "上线"}]},
    {"type": "phases", "phases": [{"label": "一期", "goal": "上线", "actions": ["调研"]}]},
    # pullquote
    {"type": "pullquote", "content": "引文"},
    {"type": "pullquote", "content": "引文", "cite": "署名"},
    # heading：text 正典 / title 兼容 / level 合法 / level 缺省
    {"type": "heading", "text": "小节", "level": 3},
    {"type": "heading", "title": "小节"},
    {"type": "heading", "text": "小节", "level": 1},
    {"type": "heading", "text": "小节", "level": 7},
    # architecture_4a：DOCX 渲染读 layers[].name/components
    {"type": "architecture_4a", "layers": [
        {"name": "业务架构", "components": ["流程梳理"]},
        {"name": "应用架构"},
    ]},
]


# ---------------------------------------------------------------------------
# 单一事实源
# ---------------------------------------------------------------------------

class TestKnownTypesConsistency:
    def test_known_types_derive_from_capabilities(self):
        """KNOWN_ELEMENT_TYPES 与协议层 CAPABILITIES 键集一致（§6.2 单一事实源）。"""
        assert KNOWN_ELEMENT_TYPES == set(CAPABILITIES)
        # 10 v1 + 13 v2 页面构件 + D-092 page_header + D-093 view_cards/
        # callout_block + 4 v3.0 版式构件 + B-3/B-4/B-5/B-6 四个批次 B 组件
        assert len(KNOWN_ELEMENT_TYPES) == 31


# ---------------------------------------------------------------------------
# 8 种基础元素：合法零误报
# ---------------------------------------------------------------------------

class TestValidBaseElements:
    @pytest.mark.parametrize("elem", VALID_ELEMENTS)
    def test_valid_samples_pass(self, elem):
        assert validate_element(elem) == []


# ---------------------------------------------------------------------------
# 8 种基础元素：非法样本报错
# ---------------------------------------------------------------------------

class TestInvalidBaseElements:
    """每种元素至少 2 个非法样本：缺必填 / 结构错误。"""

    # text ----
    def test_text_missing_content(self):
        errors = validate_element({"type": "text"})
        assert any("content" in e for e in errors)

    def test_text_empty_content(self):
        errors = validate_element({"type": "text", "content": "", "text": ""})
        assert len(errors) == 1 and "text" in errors[0]

    # bullets ----
    def test_bullets_missing_items(self):
        errors = validate_element({"type": "bullets"})
        assert any("items" in e for e in errors)

    def test_bullets_empty_items(self):
        errors = validate_element({"type": "bullets", "items": []})
        assert len(errors) == 1 and "items" in errors[0]

    def test_bullets_non_list_items(self):
        errors = validate_element({"type": "bullets", "items": "不是列表"})
        assert any("items" in e for e in errors)

    # cards ----
    def test_cards_missing_cards(self):
        errors = validate_element({"type": "cards"})
        assert any("cards" in e for e in errors)

    def test_cards_empty_cards(self):
        errors = validate_element({"type": "cards", "cards": []})
        assert len(errors) == 1

    def test_cards_item_missing_title(self):
        errors = validate_element({"type": "cards", "cards": [
            {"title": "有标题"}, {"body": "无标题"},
        ]})
        assert len(errors) == 1
        assert "cards[1]" in errors[0] and "title" in errors[0]

    # table ----
    def test_table_missing_headers(self):
        errors = validate_element({"type": "table", "rows": [["a"]]})
        assert any("headers" in e for e in errors)

    def test_table_empty_headers(self):
        errors = validate_element({"type": "table", "headers": [], "rows": []})
        assert len(errors) == 1 and "headers" in errors[0]

    def test_table_row_mismatch_names_row(self):
        """行列数不齐指名哪一行；合规行不误报。"""
        errors = validate_element({"type": "table",
                                   "headers": ["a", "b", "c"],
                                   "rows": [["1", "2", "3"],
                                            ["1", "2"],
                                            ["1", "2", "3", "4"]]})
        assert len(errors) == 2
        assert any("rows[1]" in e and "列数 2" in e for e in errors)
        assert any("rows[2]" in e and "列数 4" in e for e in errors)
        assert not any("rows[0]" in e for e in errors)

    # phases ----
    def test_phases_missing_phases(self):
        errors = validate_element({"type": "phases"})
        assert any("phases" in e for e in errors)

    def test_phases_empty_phases(self):
        errors = validate_element({"type": "phases", "phases": []})
        assert len(errors) == 1

    def test_phases_item_unresolvable_name(self):
        """name|label|phase|title 四套写法都取不到 name 时报错并指名序号。"""
        errors = validate_element({"type": "phases", "phases": [
            {"name": "有名字"}, {"desc": "没名字", "duration": "4周"},
        ]})
        assert len(errors) == 1
        assert "phases[1]" in errors[0] and "name" in errors[0]

    # pullquote ----
    def test_pullquote_missing_content(self):
        errors = validate_element({"type": "pullquote"})
        assert any("content" in e for e in errors)

    def test_pullquote_empty_content(self):
        errors = validate_element({"type": "pullquote", "content": ""})
        assert len(errors) == 1 and "content" in errors[0]

    # heading ----
    def test_heading_missing_text(self):
        errors = validate_element({"type": "heading", "level": 2})
        assert any("text" in e for e in errors)

    def test_heading_level_out_of_range(self):
        for bad in (0, 8):
            errors = validate_element({"type": "heading", "text": "x", "level": bad})
            assert len(errors) == 1 and "level" in errors[0] and "1-7" in errors[0]

    def test_heading_level_not_int(self):
        errors = validate_element({"type": "heading", "text": "x", "level": "abc"})
        assert any("level" in e for e in errors)

    # architecture_4a ----
    def test_architecture_4a_missing_layers(self):
        errors = validate_element({"type": "architecture_4a"})
        assert any("layers" in e for e in errors)

    def test_architecture_4a_empty_layers(self):
        errors = validate_element({"type": "architecture_4a", "layers": []})
        assert len(errors) == 1 and "layers" in errors[0]

    def test_architecture_4a_layer_missing_name(self):
        errors = validate_element({"type": "architecture_4a", "layers": [
            {"name": "业务架构", "components": ["x"]},
            {"components": ["y"]},
        ]})
        assert len(errors) == 1
        assert "layers[1]" in errors[0] and "name" in errors[0]


# ---------------------------------------------------------------------------
# 未知 type：从静默改为报错（§6.2）
# ---------------------------------------------------------------------------

class TestUnknownType:
    def test_unknown_type_errors_with_legal_values(self):
        errors = validate_element({"type": "tree"})
        assert len(errors) == 1
        assert "未知元素类型 'tree'" in errors[0]
        assert "合法值" in errors[0]
        # 合法值列表确实列出了已知类型
        for t in ("text", "diagram", "architecture_4a"):
            assert t in errors[0]

    def test_missing_type_key_is_unknown(self):
        """elem 无 type 键时 type='' 同样按未知类型报（MRO 旧 spec 场景）。"""
        errors = validate_element({"role": "body", "text": "旧写法"})
        assert len(errors) == 1
        assert "未知元素类型 ''" in errors[0]
        assert "合法值" in errors[0]

    def test_non_dict_element(self):
        assert validate_element("坏") == ["element: 元素必须是对象"]


# ---------------------------------------------------------------------------
# validate_spec 聚合
# ---------------------------------------------------------------------------

class TestValidateSpecAggregation:
    def test_error_paths_and_mixed_elements(self):
        spec = {"pages": [
            {"elements": [
                {"type": "text", "content": "正常"},      # 合法
                {"type": "table", "headers": ["a"], "rows": [["1", "2"]]},  # 行不齐
            ]},
            {"elements": [
                {"type": "tree"},                          # 未知 type
            ]},
        ]}
        errors = validate_spec(spec)
        assert len(errors) == 2
        assert any(e.startswith("pages[0].elements[1]") and "rows[0]" in e
                   for e in errors)
        assert any(e.startswith("pages[1].elements[0]") and "未知元素类型" in e
                   for e in errors)

    def test_spec_without_pages_is_clean(self):
        """无 pages / 页面无 elements[]（报价 spec、蓝海集团 bespoke schema）零错误。"""
        assert validate_spec({}) == []
        assert validate_spec({"pages": [{"id": "p", "title": "无元素页"}]}) == []


# ---------------------------------------------------------------------------
# 真实 spec 数据驱动校验（§6.2 出口：零误报，仅 MRO 旧元素报出）
# ---------------------------------------------------------------------------

def _real_spec_files():
    files = glob.glob(os.path.join(SCRIPT_DIR, "output", "**", "*spec*.yml"),
                      recursive=True)
    files += glob.glob(os.path.join(SCRIPT_DIR, "_knowledge", "clients", "**",
                                    "*spec*.yml"), recursive=True)
    excluded = (".scratch", ".pytest_tmp", "node_modules", "schema验收")
    # "schema验收" 是故意含错的验收样件（见下方 TestSchemaAcceptanceFixture），
    # 必须报错，不属于"零意外错误"护栏范围
    return sorted(f for f in files
                  if not any(x in f for x in excluded))


REAL_SPEC_FILES = _real_spec_files()


@pytest.mark.parametrize("spec_path", REAL_SPEC_FILES,
                         ids=[os.path.basename(f) for f in REAL_SPEC_FILES])
def test_real_spec_has_no_unexpected_errors(spec_path):
    """真实 spec 跑全量校验：除 MRO 的 9 个无 type 旧元素外零错误。

    - MRO客户门户方案_spec.yml：9 个 role/text 旧元素（无 type 键）必须报出
      ——它们本来就渲染不出，报出正是 §6.2 的目的；
    - 蓝海集团 bespoke schema（无 elements[]）与报价 spec（无 pages）自然零错误；
    - 其余 spec 任何报错都视为误报，本测试即防误报护栏。
    """
    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    errors = validate_spec(spec)
    if "MRO客户门户方案_spec" in os.path.basename(spec_path):
        assert len(errors) == 9, f"MRO 应报 9 条无 type 错误，实际: {errors}"
        assert all("未知元素类型 ''" in e for e in errors)
    else:
        assert errors == [], f"{spec_path} 出现意外校验错误: {errors[:5]}"


class TestSchemaAcceptanceFixture:
    """通用_schema验收_v1.spec.yml（故意用错 cards 字段名 items）的验收语义：

    - schema 校验必须报出（不是静默通过）
    - 渲染时该元素必须计入 report.skipped（不是静默丢失）
    """

    FIXTURE = os.path.join(SCRIPT_DIR, "tests", "fixtures", "通用_schema验收_v1.spec.yml")

    def test_fixture_reports_error(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        errors = validate_spec(spec)
        assert len(errors) == 1
        assert "cards 缺 cards" in errors[0]

    def test_fixture_render_counts_skipped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_baseline_work",
                           "schema_acceptance_probe.html")
        r = Renderer(self.FIXTURE)
        try:
            r.render_html(out)
        finally:
            if os.path.exists(out):
                os.remove(out)
        assert r.report.skipped, "错字段 cards 元素必须计入 skipped，否则就是静默盲区"
        assert "字段名" in r.report.skipped[0]["reason"]


# ---------------------------------------------------------------------------
# Renderer init：校验错误进 report.warnings，不再被 try/except 吞掉（§6.2/§6.3）
# ---------------------------------------------------------------------------

def _write_spec(tmp_path, pages):
    spec = {"confirmed": True, "document": {"title": "校验测试"}, "pages": pages}
    spec_path = os.path.join(str(tmp_path), "spec.yml")
    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True)
    return spec_path


class TestRendererInitValidation:
    def test_invalid_elements_become_warnings(self, tmp_path, monkeypatch):
        """含非法元素的 spec：init 不阻断，错误逐条进 report.warnings。"""
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, [{
            "id": "p1", "title": "页一",
            "elements": [
                {"type": "text"},                            # 缺 content
                {"role": "body", "text": "旧写法"},           # 无 type 键
                {"type": "cards", "cards": [{"body": "无标题"}]},  # 缺 title
            ],
        }])
        r = Renderer(spec_path)
        assert len(r.report.warnings) == 3
        assert any("text 缺 content" in w for w in r.report.warnings)
        assert any("未知元素类型 ''" in w for w in r.report.warnings)
        assert any("cards[0] 缺 title" in w for w in r.report.warnings)

    def test_valid_spec_no_warnings(self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, [{
            "id": "p1", "title": "页一",
            "elements": [
                {"type": "text", "content": "正文"},
                {"type": "table", "headers": ["h"], "rows": [["1"]]},
            ],
        }])
        r = Renderer(spec_path)
        assert r.report.warnings == []
        assert not r.report.has_issues()

    def test_validation_exception_becomes_warning(self, tmp_path, monkeypatch):
        """validate_spec 自身异常也不阻断 init，转为 report 警告。"""
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        import _renderer.schema as schema_mod
        from _renderer import Renderer

        def _boom(spec):
            raise RuntimeError("校验器炸了")

        monkeypatch.setattr(schema_mod, "validate_spec", _boom)
        spec_path = _write_spec(tmp_path, [{
            "id": "p1", "title": "页一",
            "elements": [{"type": "text", "content": "正文"}],
        }])
        r = Renderer(spec_path)
        assert any("spec 校验异常" in w and "校验器炸了" in w
                   for w in r.report.warnings)


# ---------------------------------------------------------------------------
# §七 2.5 第一级 源头限量：页面级容量警告（warning 级别，不进 errors 不阻断）
# ---------------------------------------------------------------------------

class TestPageCapacityWarnings:
    """validate_page_warnings：单页元素数/单元素文本长超限 -> 页面级警告。

    阈值（schema.PAGE_ELEMENTS_WARN=10 / ELEMENT_TEXT_WARN=1300）取自 6 个
    基线 spec 实测最大值（9 元素 / 1091 字）+ 约 20% 余量，基线页均不触发。
    """

    def test_over_element_limit_warns(self):
        from _renderer.schema import validate_page_warnings
        page = {"id": "p1", "elements": [
            {"type": "text", "content": f"第{i}段"} for i in range(11)]}
        warnings = validate_page_warnings(page, page_index=0)
        assert len(warnings) == 1
        assert "11 个元素" in warnings[0]
        assert "pages[0]" in warnings[0] and "id=p1" in warnings[0]

    def test_over_text_length_warns(self):
        from _renderer.schema import validate_page_warnings
        page = {"id": "p1", "elements": [
            {"type": "text", "content": "字" * 1301}]}
        warnings = validate_page_warnings(page)
        assert len(warnings) == 1
        assert "超过上限" in warnings[0]
        assert "elements[0]" in warnings[0]

    def test_baseline_maxima_no_warning(self):
        """基线实测最大值（9 元素 / 1091 字）在阈值内，不触发警告。"""
        from _renderer.schema import validate_page_warnings
        page = {"id": "p1", "elements": [
            {"type": "text", "content": f"第{i}段"} for i in range(9)]}
        assert validate_page_warnings(page) == []
        page2 = {"id": "p2", "elements": [
            {"type": "text", "content": "字" * 1091}]}
        assert validate_page_warnings(page2) == []

    def test_warnings_not_in_validate_spec_errors(self):
        """容量超限只产 warning，不进 validate_spec 的 errors（不阻断）。"""
        spec = {"pages": [{"id": "p1", "elements": [
            {"type": "text", "content": f"第{i}段"} for i in range(11)]}]}
        assert validate_spec(spec) == []

    def test_renderer_init_collects_page_warnings(self, tmp_path, monkeypatch):
        """Renderer init 调用页面级检查并进 report.warnings。"""
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, [{
            "id": "p1", "title": "超长页",
            "elements": [{"type": "text", "content": f"第{i}段"} for i in range(11)],
        }])
        r = Renderer(spec_path)
        assert any("11 个元素" in w for w in r.report.warnings)
