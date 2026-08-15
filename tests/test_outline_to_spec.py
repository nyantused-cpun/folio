# -*- coding: utf-8 -*-
"""outline-to-spec 产出合法性回归测试（P0：tree/phases 曾产出三端不识别的元素）。"""

import os
import shutil

import yaml

from _outline_to_spec import ROLE_LAYOUT, build_elements
from _renderer.schema import KNOWN_ELEMENT_TYPES, validate_element


def _fake_layers():
    return [
        {"name": "感知层", "desc": "数据采集", "components": ["传感器", "摄像头", "RFID"]},
        {"name": "平台层", "desc": "数据中台", "components": ["数据仓库", "主数据管理", "ETL"]},
        {"name": "应用层", "desc": "业务应用", "components": ["CRM", "ERP", "OA"]},
    ]


def _fake_result():
    return {
        "key_points": ["要点一", "要点二", "要点三", "要点四"],
        "content": "这是章节正文内容。",
        "data": ["100", "200", "300"],
    }


def _fake_section():
    return {"section": "总体蓝图", "children": ["子节1", "子节2"]}


class TestBuildElementsLegal:
    """所有 layout 产出的元素 type 必须全部落在 KNOWN_ELEMENT_TYPES。"""

    def test_all_layouts_produce_known_types(self):
        for layout in set(ROLE_LAYOUT.values()):
            elements = build_elements(layout, _fake_result(), _fake_section())
            assert elements, f"layout={layout} 产出为空"
            for elem in elements:
                assert elem.get("type") in KNOWN_ELEMENT_TYPES, \
                    f"layout={layout} 产出非法元素 type={elem.get('type')}"

    def test_tree_layout_keeps_content(self):
        """tree（架构章节）改产 text+cards 后内容不丢。"""
        elements = build_elements("tree", _fake_result(), _fake_section())
        types = [e["type"] for e in elements]
        assert "cards" in types
        cards = next(e for e in elements if e["type"] == "cards")
        titles = [c["title"] for c in cards["cards"]]
        assert "要点一" in titles

    def test_phases_uses_canonical_fields(self):
        """phases 产出正典 name/desc 字段（三端可读）。"""
        elements = build_elements("phases", _fake_result(), _fake_section())
        phases = elements[0]["phases"]
        assert phases, "phases 为空"
        for ph in phases:
            assert ph.get("name"), f"phase 缺 name: {ph}"
            assert "desc" in ph
            # 双写字段保证 DOCX 端可见
            assert ph.get("label") == ph["name"]

    def test_empty_result_still_legal(self):
        """LLM 返回空时也不能产出非法元素。"""
        empty = {"key_points": [], "content": "", "data": []}
        for layout in set(ROLE_LAYOUT.values()):
            elements = build_elements(layout, empty, _fake_section())
            for elem in elements:
                assert elem.get("type") in KNOWN_ELEMENT_TYPES


class TestLlmFailurePlaceholder:
    """LLM 章节提取失败不再静默丢章节（§6.3）：

    页保留 + text 占位元素 + 明显警告（带章节名），重新运行可修复。
    """

    PLACEHOLDER = "（本章节内容提取失败，请重新运行 outline-to-spec 或手动补充）"

    def _run_build(self, tmp_path, monkeypatch, extract_fn):
        """mock 掉材料读取/证据召回/LLM 提取，跑 build_spec_from_outline。"""
        import _outline_to_spec
        outline = {
            "scene": "测试场景",
            "structure": [
                {"section": "客户痛点", "role": "pain_points", "children": []},
                {"section": "建设目标", "role": "goals", "children": []},
            ],
        }
        monkeypatch.setattr(_outline_to_spec, "load_outline", lambda scene: outline)
        monkeypatch.setattr(_outline_to_spec, "read_materials",
                            lambda paths, client_name="": "材料文本")
        monkeypatch.setattr(_outline_to_spec, "_recall_evidence", lambda *a, **k: [])
        monkeypatch.setattr(_outline_to_spec, "extract_section_content", extract_fn)

        # §八 3.5 起 spec 写入过 output/ 白名单：测试输出落到白名单内临时目录
        from _renderer import SCRIPT_DIR
        out_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_ots_test")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "spec.yml")
        try:
            result = _outline_to_spec.build_spec_from_outline(
                "测试场景", ["dummy.txt"], client_name="", output_path=out)
            assert result == out
            with open(out, encoding="utf-8") as f:
                return yaml.safe_load(f)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_failure_keeps_placeholder_page(self, tmp_path, monkeypatch, capsys):
        """全部章节提取失败：页一个不丢，均为占位元素，警告带章节名。"""
        spec = self._run_build(tmp_path, monkeypatch, lambda *a, **k: None)

        assert len(spec["pages"]) == 2
        for page in spec["pages"]:
            assert page["elements"] == [
                {"type": "text", "role": "body", "content": self.PLACEHOLDER}]
            # 占位元素本身是合法元素，不会引入新的 skip
            assert page["elements"][0]["type"] in KNOWN_ELEMENT_TYPES
        out = capsys.readouterr().out
        assert "提取失败" in out
        assert "客户痛点" in out
        assert "建设目标" in out

    def test_partial_failure_keeps_page_count(self, tmp_path, monkeypatch, capsys):
        """一章成功一章失败：失败页占位、成功页正常，页数结构完整。"""
        def _extract(section, *a, **k):
            if section["section"] == "客户痛点":
                return None
            return {"title": "建设目标", "content": "正文内容",
                    "key_points": ["要点一"], "data": []}

        spec = self._run_build(tmp_path, monkeypatch, _extract)

        assert len(spec["pages"]) == 2
        pain = next(p for p in spec["pages"] if p["title"] == "客户痛点")
        assert pain["elements"] == [
            {"type": "text", "role": "body", "content": self.PLACEHOLDER}]
        goal = next(p for p in spec["pages"] if p["title"] == "建设目标")
        assert goal["elements"][0].get("content") != self.PLACEHOLDER
        out = capsys.readouterr().out
        assert "客户痛点" in out and "提取失败" in out


class TestTreeDiagram:
    """§七 2.7：架构类章节（tree layout）LLM 返回合法 layers 时产 diagram 元素。"""

    def _result_with_layers(self):
        result = _fake_result()
        result["layers"] = _fake_layers()
        return result

    def test_layers_produce_diagram_and_pass_schema(self):
        elements = build_elements("tree", self._result_with_layers(), _fake_section())
        types = [e["type"] for e in elements]
        assert "diagram" in types
        diagram = next(e for e in elements if e["type"] == "diagram")
        assert diagram["diagram_type"] == "architecture"
        assert diagram["subtype"] == "layered"
        assert diagram["title"] == "总体蓝图"  # title 用章节名
        assert diagram["layers"] == _fake_layers()
        # 全部元素过 schema 校验零错误（layers 必填满足）
        for i, elem in enumerate(elements):
            assert validate_element(elem, index=i) == []

    def test_content_summary_text_prepended(self):
        """有 content 时 diagram 前插 text 摘要（前 200 字）。"""
        result = self._result_with_layers()
        result["content"] = "摘" * 300
        elements = build_elements("tree", result, _fake_section())
        assert elements[0]["type"] == "text"
        assert elements[0]["content"] == "摘" * 200
        assert elements[1]["type"] == "diagram"

    def test_no_content_skips_summary_text(self):
        result = self._result_with_layers()
        result["content"] = ""
        elements = build_elements("tree", result, _fake_section())
        assert [e["type"] for e in elements] == ["diagram"]

    def test_missing_layers_falls_back_to_cards(self):
        """无 layers → 现有 text+cards 回退路径不变。"""
        elements = build_elements("tree", _fake_result(), _fake_section())
        types = [e["type"] for e in elements]
        assert "diagram" not in types
        assert "cards" in types

    def test_malformed_layers_fall_back(self):
        """layers 结构不对 → 回退 text+cards，不报错。"""
        bad_variants = [
            {"layers": "not-a-list"},
            {"layers": []},
            {"layers": ["just-a-string"]},
            {"layers": [{"name": "感知层"}]},                        # 缺 components
            {"layers": [{"name": "感知层", "components": "传感器"}]},  # components 非 list
            {"layers": [{"name": "感知层", "components": []}]},        # 空组件
            {"layers": [{"components": ["传感器"]}]},                  # 缺 name
        ]
        for bad in bad_variants:
            result = _fake_result()
            result.update(bad)
            elements = build_elements("tree", result, _fake_section())
            types = [e["type"] for e in elements]
            assert "diagram" not in types, f"坏 layers 未回退: {bad}"
            assert "cards" in types, f"回退路径缺 cards: {bad}"
            for i, elem in enumerate(elements):
                assert validate_element(elem, index=i) == []


class TestArchPromptLayers:
    """架构 role 的提取 prompt 含 layers 要求，非架构 role 不含。"""

    def _capture_prompt(self, monkeypatch, tmp_path, role):
        import _cloud_llm
        captured = {}

        def _fake_chat(prompt, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return '{"title": "t", "content": "c", "key_points": [], "data": [], "source_quote": ""}'

        monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)

        import _outline_to_spec
        # §3.3 提取缓存隔离到 tmp：避免污染真实缓存文件 / 跨测试运行命中缓存导致 chat 不被调
        monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH",
                            str(tmp_path / "cache.json"))
        section = {"section": "章节名", "role": role, "children": []}
        result = _outline_to_spec.extract_section_content(
            section, "材料文本" * 1000, client_name="")
        assert result is not None
        return captured

    def test_arch_roles_prompt_has_layers(self, monkeypatch, tmp_path):
        for role in ("blueprint", "function_architecture", "tech_architecture"):
            captured = self._capture_prompt(monkeypatch, tmp_path, role)
            assert "layers" in captured["prompt"], f"role={role} 的 prompt 缺 layers 要求"
            assert "架构章节附加要求" in captured["prompt"]
            # 架构章节输出更长，max_tokens 提到 4000（zhipu 思考模式会吃掉 2000 预算）
            assert captured["kwargs"].get("max_tokens") == 4000

    def test_non_arch_role_prompt_no_layers(self, monkeypatch, tmp_path):
        for role in ("pain_points", "goals", "value", ""):
            captured = self._capture_prompt(monkeypatch, tmp_path, role)
            assert "layers" not in captured["prompt"], f"role={role} 的 prompt 不应含 layers 要求"
            assert captured["kwargs"].get("max_tokens") == 2000


class TestGoldSpecInjection:
    """§8 v1.2-4 三层示范库：架构章节 prompt 注入 gold spec 写法示范。

    注入位置在静态 system 段之后、【本章节任务】之前（与 evidence 同区，
    静态前缀逐字节稳定）；无对应 gold 不注入；注入截断到 token 预算。
    """

    GOLD = ("# Gold spec 示范片段：architecture/layered\n"
            "# 验收来源：测试\n"
            "type: diagram\n"
            "diagram_type: architecture\n"
            "subtype: layered\n"
            "title: 示范架构\n"
            "layers:\n"
            "- name: 应用层\n"
            "  components: [CRM, ERP]\n")

    def _capture_prompt(self, monkeypatch, tmp_path, role, gold_text=None):
        import _cloud_llm
        captured = {}

        def _fake_chat(prompt, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return ('{"title": "t", "content": "c", "key_points": [],'
                    ' "data": [], "source_quote": ""}')

        monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)

        import _outline_to_spec
        # gold 库与提取缓存都隔离到 tmp：真实缓存命中会跳过 chat 导致捕获不到 prompt
        monkeypatch.setattr(_outline_to_spec, "GOLD_SPECS_DIR", str(tmp_path))
        monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH",
                            str(tmp_path / "cache.json"))
        if gold_text is not None:
            (tmp_path / "architecture__layered.yml").write_text(
                gold_text, encoding="utf-8")
        section = {"section": "总体蓝图", "role": role, "children": []}
        result = _outline_to_spec.extract_section_content(
            section, "材料文本" * 1000, client_name="")
        assert result is not None
        return captured

    def test_arch_prompt_has_gold_demo_when_present(self, monkeypatch, tmp_path):
        """架构章节 + gold 存在 → 注入，且在静态段之后、章节任务之前。"""
        for role in ("blueprint", "function_architecture", "tech_architecture"):
            captured = self._capture_prompt(monkeypatch, tmp_path, role,
                                            gold_text=self.GOLD)
            prompt = captured["prompt"]
            system = captured["kwargs"].get("system", "")
            assert "【写法示范】" in prompt, f"role={role} 的 prompt 缺写法示范"
            assert "模仿其字段结构和信息密度，不要抄内容" in prompt
            assert "示范架构" in prompt  # gold 片段内容进入 prompt
            # §3 前缀稳定性：静态 system 段（已拆到 system 参数）< 示范注入 < 章节任务
            assert "【强制规则】" in system, f"role={role} 的 system 缺强制规则"
            assert (prompt.index("【写法示范】")
                    < prompt.index("【本章节任务】"))

    def test_arch_prompt_no_gold_no_injection(self, monkeypatch, tmp_path):
        """架构章节 + 无对应 gold 文件 → 不注入。"""
        captured = self._capture_prompt(monkeypatch, tmp_path, "blueprint",
                                        gold_text=None)
        assert "【写法示范】" not in captured["prompt"]

    def test_non_arch_prompt_no_injection_even_with_gold(self, monkeypatch, tmp_path):
        """非架构章节即使 gold 存在也不注入（不产 diagram 的页不花 token）。"""
        for role in ("pain_points", "goals", "value", ""):
            captured = self._capture_prompt(monkeypatch, tmp_path, role,
                                            gold_text=self.GOLD)
            assert "【写法示范】" not in captured["prompt"], f"role={role} 不应注入示范"

    def test_gold_comment_lines_stripped(self, monkeypatch, tmp_path):
        """gold 文件 `#` 注释行（验收来源/内部路径/客户名）剥除，不泄进 prompt。"""
        gold = ("# Gold spec 示范片段：architecture/layered\n"
                "# 验收来源：.scratch/内部路径_spec.yml（客户甲）\n"
                "type: diagram\n"
                "diagram_type: architecture\n"
                "subtype: layered\n"
                "title: 示范架构\n"
                "layers:\n"
                "- name: 应用层\n"
                "  components: [CRM, ERP]\n")
        captured = self._capture_prompt(monkeypatch, tmp_path, "blueprint",
                                        gold_text=gold)
        assert "【写法示范】" in captured["prompt"]
        assert "示范架构" in captured["prompt"], "内容行保留"
        assert "验收来源" not in captured["prompt"]
        assert "内部路径" not in captured["prompt"]

    def test_load_gold_demo_strips_comments_directly(self, monkeypatch, tmp_path):
        """load_gold_demo 单测：行首/缩进 # 注释行都剥除，内容行不动。"""
        import _outline_to_spec
        monkeypatch.setattr(_outline_to_spec, "GOLD_SPECS_DIR", str(tmp_path))
        (tmp_path / "architecture__layered.yml").write_text(
            "# 头部注释\ntype: diagram\n  # 缩进注释\ntitle: 架构\n",
            encoding="utf-8")
        demo = _outline_to_spec.load_gold_demo("architecture", "layered")
        assert "注释" not in demo
        assert "type: diagram" in demo
        assert "title: 架构" in demo

    def test_gold_truncated_to_token_budget(self, monkeypatch, tmp_path):
        """超大 gold 截断到 GOLD_DEMO_MAX_TOKENS（截断标注行另计，约 16 tokens）。"""
        import _outline_to_spec
        big_gold = "# 注释\nlayers:\n" + ("- name: " + "组" * 40 + "\n") * 200
        captured = self._capture_prompt(monkeypatch, tmp_path, "blueprint",
                                        gold_text=big_gold)
        prompt = captured["prompt"]
        assert "超出示范 token 预算，余下截断" in prompt
        demo = prompt.split("不要抄内容：\n", 1)[1].split("\n---", 1)[0]
        assert _outline_to_spec._est_tokens(demo) <= (
            _outline_to_spec.GOLD_DEMO_MAX_TOKENS + 20)
