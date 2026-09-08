# -*- coding: utf-8 -*-
"""I-3 批3 测试：B4 三区表结构校验 + C1/C2 方向文件机械消费 + chunk-read 顺带项。

覆盖：
B4（_verify_checks.check_analysis_structure / verify_analysis_md / auto_verify 接线）
- 规则①：缺依据类型 / 缺证据锚点 / 锚点非法 → 触发；合规条目 → 不触发
- 规则②：confirmed 6 条 >5 → 触发；5 条 → 不触发
- 规则③：[confirmed]+推断 → 触发；[draft]+推断 → 不触发
- 无「确认事实」固定小节 → 跳过（[]）；非 analysis 路径 → None
- auto_verify .md 接线：三区表 → ok=True 观察级不阻断；普通 .md → 不支持
C2（_outline_to_spec）
- 无方向文件：prompt 组装与缓存键与现状逐字节一致（兼容红线 pin）
- 人批方向文件：prompt 注入【客户已定方向】+ 缓存键变化
- 草稿方向文件：与无文件行为一致（不进 prompt / 不改缓存键）
- 有方向文件时 spec evidence 锚点强制 100% 合法（build 集成路径）
chunk-read 顺带项（_recall.read_chunk）
- analysis 文件锚点读取 → 只回 confirmed 文本；格式损坏 → fail-closed 说明
全部 tmp 封闭，绝不读写真实 _knowledge/。
"""

import os

import _outline_to_spec
import _verify_checks
from _memory_guard import parse_source_refs

_OK_ENTRY = "- [confirmed] 已确认事实甲 ｜ 依据类型：材料原文 ｜ 证据：file:refs/x.md"


def _analysis_md(fact_entries):
    return (
        "# 客户A · 三区表\n\n> 解析约定\n\n## 确认事实\n\n"
        + "\n".join(fact_entries)
        + "\n\n## 开放问题\n\n| # | 开放问题 |\n|---|---|\n| 1 | 问？ |\n"
        + "\n\n## 框架缺口\n\n| 缺口 | 影响 |\n|---|---|\n| 缺 | 影响 |\n"
    )


class TestB4AnalysisStructure:
    """B4 三规则各自触发/不触发（观察级 warning 列表断言）。"""

    def test_rule1_missing_basis_triggers(self):
        w = _verify_checks.check_analysis_structure(_analysis_md([
            "- [confirmed] 事实缺依据词ZQW1 ｜ 证据：file:refs/x.md",
        ]))
        assert any("未挂依据类型" in m for m in w)

    def test_rule1_missing_or_invalid_anchor_triggers(self):
        w = _verify_checks.check_analysis_structure(_analysis_md([
            "- [confirmed] 事实缺证据词ZQW2 ｜ 依据类型：材料原文",
            "- [confirmed] 事实锚点非法词ZQW3 ｜ 依据类型：召回片段 ｜ 证据：乱写的",
        ]))
        assert sum("缺有效证据锚点" in m for m in w) == 2

    def test_rule1_compliant_entry_silent(self):
        w = _verify_checks.check_analysis_structure(_analysis_md([_OK_ENTRY]))
        assert w == []

    def test_rule2_top_limit(self):
        entries = [f"- [confirmed] 事实{i} ｜ 依据类型：材料原文 ｜ 证据：session:{i}"
                   for i in range(1, 7)]
        w = _verify_checks.check_analysis_structure(_analysis_md(entries))
        assert any("Top 纪律" in m and "6 条" in m for m in w)
        w5 = _verify_checks.check_analysis_structure(_analysis_md(entries[:5]))
        assert not any("Top 纪律" in m for m in w5), "5 条 confirmed 不应触发 Top 纪律"

    def test_rule3_confirmed_inference_triggers_draft_silent(self):
        w = _verify_checks.check_analysis_structure(_analysis_md([
            "- [confirmed] 推断当确认词ZQW4 ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        assert any("Claim 零条进确认区" in m for m in w)
        w_draft = _verify_checks.check_analysis_structure(_analysis_md([
            "- [draft] 推断待确认词ZQW5 ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        assert not any("Claim 零条进确认区" in m for m in w_draft), \
            "draft+推断是合法待确认态，不应触发规则③"

    def test_unmarked_entry_triggers(self):
        w = _verify_checks.check_analysis_structure(_analysis_md([
            _OK_ENTRY,
            "- 无状态标记条目词ZQW6",
        ]))
        assert any("机械标记" in m for m in w)

    def test_non_analysis_format_skips(self):
        assert _verify_checks.check_analysis_structure("# 随手笔记\n\n## 随便\n") == []


class TestB4VerifyWiring:
    """verify_analysis_md 触发面 + auto_verify .md 接线（tmp 封闭）。"""

    def _write(self, tmp_path, name="三区表.md", content=None):
        d = tmp_path / "analysis"
        d.mkdir(exist_ok=True)
        p = d / name
        p.write_text(content if content is not None else _analysis_md([_OK_ENTRY]),
                     encoding="utf-8")
        return str(p)

    def test_analysis_md_passes_observation_only(self, tmp_path):
        p = self._write(tmp_path)
        ok, msg = _verify_checks.verify_analysis_md(p)
        assert ok is True and "三区表结构校验" in msg

    def test_observation_warnings_in_msg(self, tmp_path):
        entries = [f"- [confirmed] 事实{i} ｜ 依据类型：材料原文 ｜ 证据：session:{i}"
                   for i in range(1, 7)]
        ok, msg = _verify_checks.verify_analysis_md(
            self._write(tmp_path, content=_analysis_md(entries)))
        assert ok is True, "观察级 warning 不得阻断（永不 FAIL）"
        assert "[观察]" in msg and "Top 纪律" in msg

    def test_non_analysis_md_returns_none(self, tmp_path):
        assert _verify_checks.verify_analysis_md(str(tmp_path / "README.md")) is None
        # analysis/ 下但不是三区表格式（缺固定小节）→ None
        p = self._write(tmp_path, name="笔记.md", content="# 笔记\n\n## 小节\n\n- 无三区\n")
        assert _verify_checks.verify_analysis_md(p) is None

    def test_auto_verify_md_branch(self, tmp_path):
        import _verify
        ok, msg = _verify.auto_verify(self._write(tmp_path))
        assert ok is True and "三区表结构校验" in msg
        plain = tmp_path / "plain.md"
        plain.write_text("# 普通文档\n", encoding="utf-8")
        ok2, msg2 = _verify.auto_verify(str(plain))
        assert ok2 is False and "不支持的文件类型" in msg2


class TestC2DirectionLoad:
    """方向文件加载：人批才消费；草稿/无文件 → ("", "")。"""

    def _ws(self, tmp_path, monkeypatch, status=None):
        clients = tmp_path / "_knowledge" / "clients" / "客户X"
        clients.mkdir(parents=True)
        if status is not None:
            (clients / "方向文件.md").write_text(
                f"# 客户X · 方向文件\n\n> 确认状态：{status} ｜ 批准人：用户\n\n"
                "## 已定方向\n\n- 方向标记词ZQWdir ｜ 来源：keynote ｜ 证据：file:keynote.md\n",
                encoding="utf-8")
        monkeypatch.setattr(_outline_to_spec, "SCRIPT_DIR", str(tmp_path))

    def test_no_file_returns_empty(self, tmp_path, monkeypatch):
        self._ws(tmp_path, monkeypatch, status=None)
        assert _outline_to_spec._load_direction_block("客户X") == ("", "")

    def test_draft_not_consumed(self, tmp_path, monkeypatch, capsys):
        self._ws(tmp_path, monkeypatch, status="草稿")
        assert _outline_to_spec._load_direction_block("客户X") == ("", "")
        assert "非「人批」" in capsys.readouterr().out

    def test_approved_consumed(self, tmp_path, monkeypatch):
        self._ws(tmp_path, monkeypatch, status="人批")
        block, sha = _outline_to_spec._load_direction_block("客户X")
        assert "【客户已定方向" in block and "方向标记词ZQWdir" in block
        assert len(sha) == 64


class TestC2PromptAndCacheKey:
    """判据 1/2：无方向文件行为逐字节不变；有方向文件注入 + 缓存键变化。"""

    SECTION = {"section": "章节名", "role": "", "children": [], "prompt": ""}
    MATERIALS = "材" * 4000

    def _capture_prompt(self, monkeypatch, tmp_path, with_direction=False):
        import _cloud_llm
        import _diagram_extract
        captured = {}

        def _fake_chat(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"title": "t", "content": "c", "key_points": [], "data": [], "source_quote": ""}'

        monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)
        monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH",
                            str(tmp_path / "cache.json"))
        monkeypatch.setattr(_diagram_extract, "GOLD_SPECS_DIR", str(tmp_path / "gold"))
        clients = tmp_path / "_knowledge" / "clients" / "客户X"
        clients.mkdir(parents=True)
        if with_direction:
            (clients / "方向文件.md").write_text(
                "# 客户X · 方向文件\n\n> 确认状态：人批 ｜ 批准人：用户\n\n"
                "## 已定方向\n\n- 方向标记词ZQWdir ｜ 来源：keynote ｜ 证据：file:keynote.md\n",
                encoding="utf-8")
        monkeypatch.setattr(_outline_to_spec, "SCRIPT_DIR", str(tmp_path))
        result = _outline_to_spec.extract_section_content(
            dict(self.SECTION), self.MATERIALS, client_name="客户X")
        assert result is not None
        return captured["prompt"]

    def test_no_direction_prompt_byte_identical_to_legacy(self, monkeypatch, tmp_path):
        """判据 1：无方向文件时 prompt 与现状（无 direction_block 插槽）逐字节一致。"""
        prompt = self._capture_prompt(monkeypatch, tmp_path, with_direction=False)
        fallback = (f"\n【客户材料（evidence 不足，前 4000 字符）】\n"
                    f"{self.MATERIALS[:4000]}\n")
        expected = (
            "【客户】客户X\n" + fallback + "\n---\n\n【本章节任务】\n"
            "章节：章节名\n章节角色：\n参考子要点：[]\n\n写作要求：\n\n\n"
            "请输出如下 JSON 格式（严格 JSON，不要加 ```json 标记）：\n"
            "{\n"
            '  "title": "本章节标题（基于材料内容拟定）",\n'
            '  "content": "本章节正文，2-4 句话，基于材料内容",\n'
            '  "key_points": ["从材料提取的 2-5 个具体要点，每个一句话"],\n'
            '  "data": ["材料中出现的具体数字/指标，原文引用"],\n'
            '  "source_quote": "材料中支撑本章节的原文片段"\n'
            "}"
        )
        assert prompt == expected, "无方向文件时 prompt 必须与现状逐字节一致"
        assert "【客户已定方向" not in prompt

    def test_approved_direction_injected(self, monkeypatch, tmp_path):
        prompt = self._capture_prompt(monkeypatch, tmp_path, with_direction=True)
        assert "【客户已定方向" in prompt and "方向标记词ZQWdir" in prompt
        # 注入位置：【客户】行之后、【本章节任务】之前
        assert prompt.index("【客户已定方向") < prompt.index("【本章节任务】")

    def test_cache_key_compat(self):
        """判据 1 缓存键侧：无方向文件（缺省/空 sha）key 与旧调用一致；有方向文件 key 变化。"""
        k_old = _outline_to_spec._extract_cache_key(self.SECTION, self.MATERIALS, "客户X", None)
        k_empty = _outline_to_spec._extract_cache_key(
            self.SECTION, self.MATERIALS, "客户X", None, direction_sha256="")
        assert k_old == k_empty, "无方向文件的存量 key 必须保持不变"
        k_dir = _outline_to_spec._extract_cache_key(
            self.SECTION, self.MATERIALS, "客户X", None, direction_sha256="a" * 64)
        assert k_dir != k_old, "方向文件内容 hash 必须进缓存键（防缓存错配）"
        k_dir2 = _outline_to_spec._extract_cache_key(
            self.SECTION, self.MATERIALS, "客户X", None, direction_sha256="b" * 64)
        assert k_dir2 != k_dir, "方向文件内容变化必须触发重取"


class TestC2EvidenceAnchorEnforcement:
    """判据 2：有方向文件（人批）时 spec evidence 段条目锚点 100% 合法。"""

    def _run_build(self, tmp_path, monkeypatch, client_name, evidence):
        outline = {
            "scene": "测试场景",
            "structure": [{"section": "建设目标", "role": "goals", "children": []}],
        }
        monkeypatch.setattr(_outline_to_spec, "load_outline", lambda scene: outline)
        monkeypatch.setattr(_outline_to_spec, "read_materials",
                            lambda paths, client_name="", allow_outside=False: "材料文本")
        monkeypatch.setattr(_outline_to_spec, "_recall_evidence",
                            lambda *a, **k: [dict(e) if isinstance(e, dict) else e
                                             for e in evidence])
        monkeypatch.setattr(
            _outline_to_spec, "extract_section_content",
            lambda *a, **k: {"title": "建设目标", "content": "内容",
                             "key_points": ["要点甲"], "data": []})
        monkeypatch.setattr(_outline_to_spec, "SCRIPT_DIR", str(tmp_path))
        from _renderer import SCRIPT_DIR as REAL_DIR
        out_dir = os.path.join(REAL_DIR, "output", "通用", "_ots_test_b4")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, "spec.yml")
        try:
            assert _outline_to_spec.build_spec_from_outline(
                "测试场景", ["dummy.txt"], client_name=client_name,
                output_path=out) == out
            import yaml
            with open(out, encoding="utf-8") as f:
                return yaml.safe_load(f)
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    EVIDENCE = [
        {"source": "_knowledge/clients/客户X/refs/x.md#p0", "snippet": "片段甲"},  # 裸路径
        {"source": "session:8", "snippet": "片段乙"},  # 已是合法锚点
        {"source": "", "snippet": "空来源"},  # 无法挂锚点 → 剔除
        "纯字符串垃圾条目",  # 非 dict → 剔除
    ]

    def test_anchors_enforced_with_direction(self, tmp_path, monkeypatch, capsys):
        clients = tmp_path / "_knowledge" / "clients" / "客户X"
        clients.mkdir(parents=True)
        (clients / "方向文件.md").write_text(
            "# 客户X · 方向文件\n\n> 确认状态：人批 ｜ 批准人：用户\n\n## 已定方向\n\n- 方向 ｜ 来源：keynote ｜ 证据：file:keynote.md\n",
            encoding="utf-8")
        spec = self._run_build(tmp_path, monkeypatch, "客户X", self.EVIDENCE)
        ev = spec["pages"][0]["evidence"]
        assert len(ev) == 2, "空来源与非 dict 条目应被剔除"
        for entry in ev:
            refs = parse_source_refs(entry["source"])
            assert refs and all(r["kind"] != "invalid" for r in refs), \
                f"evidence 锚点必须 100% 合法: {entry['source']}"
        assert ev[0]["source"].startswith("file:"), "裸路径应补 file: 前缀"
        assert ev[1]["source"] == "session:8", "已合法锚点原样保留"
        out = capsys.readouterr().out
        assert "已加载方向文件" in out and "剔除" in out

    def test_no_direction_behavior_unchanged(self, tmp_path, monkeypatch):
        """判据 1 build 侧：无方向文件时 evidence 原样落盘（不补前缀、不剔除）。"""
        spec = self._run_build(tmp_path, monkeypatch, "客户Y", self.EVIDENCE[:3])
        ev = spec["pages"][0]["evidence"]
        assert [e["source"] for e in ev] == [e["source"] for e in self.EVIDENCE[:3]], \
            "无方向文件时 evidence 必须与现状完全一致"

    def test_draft_direction_same_as_absent(self, tmp_path, monkeypatch):
        clients = tmp_path / "_knowledge" / "clients" / "客户Z"
        clients.mkdir(parents=True)
        (clients / "方向文件.md").write_text(
            "# 客户Z · 方向文件\n\n> 确认状态：草稿\n\n## 已定方向\n\n- 方向 ｜ 来源：keynote ｜ 证据：file:keynote.md\n",
            encoding="utf-8")
        spec = self._run_build(tmp_path, monkeypatch, "客户Z", self.EVIDENCE[:3])
        ev = spec["pages"][0]["evidence"]
        assert ev[0]["source"] == self.EVIDENCE[0]["source"], \
            "草稿方向文件不得改变现状行为（未确认不机械消费）"


class TestChunkReadAnalysisFilter:
    """批2 顺带项：analysis/ 三区表 chunk-read 只还原 confirmed 条目。"""

    def _write(self, tmp_path, content):
        d = tmp_path / "analysis"
        d.mkdir(exist_ok=True)
        p = d / "三区表.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_anchored_read_returns_confirmed_only(self, tmp_path):
        from _recall import read_chunk
        p = self._write(tmp_path, _analysis_md([
            "- [confirmed] 已确认事实词ZQWok ｜ 依据类型：材料原文 ｜ 证据：file:refs/x.md",
            "- [draft] 未确认推断词ZQWdraft ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        text = read_chunk(p + "#confirmed")
        assert "已确认事实词ZQWok" in text
        assert "未确认推断词ZQWdraft" not in text, "draft 条目不得经 chunk-read 回读"
        assert "开放问题" not in text, "开放问题区不得回读"

    def test_corrupted_analysis_fail_closed(self, tmp_path):
        from _recall import read_chunk
        p = self._write(tmp_path, "# 随手笔记\n\n## 随便\n\n- [confirmed] 假装词ZQWfake\n")
        text = read_chunk(p + "#confirmed")
        assert "fail-closed" in text and "假装词ZQWfake" not in text

    def test_bare_read_unchanged(self, tmp_path):
        """无锚点的整文件显式读取保持原文（read_chunk 裸路径语义不变）。"""
        from _recall import read_chunk
        p = self._write(tmp_path, _analysis_md([
            "- [draft] 未确认推断词ZQWbare ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        assert "未确认推断词ZQWbare" in read_chunk(p)
