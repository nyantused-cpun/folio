# -*- coding: utf-8 -*-
"""批5（2026-09-05）知识层观察级检查封闭化测试。

- C2 术语漂移扫描（_audit_knowledge_terms_drift，总方案 §9.2 + §8 glossary 规则）
- S11 锚点完整性检查（_audit_knowledge_anchor_integrity，v0.2 §2.6 三件套之三）

全部用例在 tmp 目录构造 glossary/域卡/skill 文本，不依赖仓库真实卡片
（audit 测试封闭化先例：test_cli_audit_ratchet / test_keynote_chain）。
两项检查均为观察级：恒返回 True（WARN 不 FAIL），断言落在输出文本上。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


_GLOSSARY = """# 方法总纲与术语表

## 8. 全局 glossary 规则

| 标准名 | 别名/客户叫法 | 定义出处 |
|---|---|---|
| 回单认领 | 回单匹配/回单自动回传认领 | 费控域 §三名词表 |
| 预算占用 | 事前申请卡预算/节点关联预算 | 费控域 §四.1 |
"""


def _mk_glossary(tmp_path):
    p = tmp_path / "方法总纲与术语表.md"
    p.write_text(_GLOSSARY, encoding="utf-8")
    return str(p)


class TestTermsDrift:
    def test_positive_alias_without_mapping_warns(self, tmp_path, capsys):
        """正例：域卡用登记旧称且同行无标准名 → WARN（卡名/行号/旧称/标准名）。"""
        import _cli_audit_p0
        domains = tmp_path / "domains"
        domains.mkdir()
        (domains / "项目域.md").write_text(
            "# 项目域\n\n| 核心功能诉求 | 节点关联预算 + 交付物归档 | 最小功能集 |\n",
            encoding="utf-8")
        ok = _cli_audit_p0._audit_knowledge_terms_drift(
            glossary_path=_mk_glossary(tmp_path), domains_dir=str(domains))
        assert ok is True  # 观察级：恒 True
        out = capsys.readouterr().out
        assert "⚠" in out and "项目域.md:3" in out
        assert "节点关联预算" in out and "预算占用" in out

    def test_negative_standard_name_no_warn(self, tmp_path, capsys):
        """负例：域卡用标准名 → 无 WARN。"""
        import _cli_audit_p0
        domains = tmp_path / "domains"
        domains.mkdir()
        (domains / "费控域.md").write_text(
            "# 费控域\n\n回单认领靠银企直连自动完成。\n",
            encoding="utf-8")
        assert _cli_audit_p0._audit_knowledge_terms_drift(
            glossary_path=_mk_glossary(tmp_path), domains_dir=str(domains)) is True
        assert "⚠ 0 项" in capsys.readouterr().out

    def test_negative_alias_with_std_same_line_is_mapping(self, tmp_path, capsys):
        """负例：同行兼含别名与标准名 = 别名映射行（速查表真实形态），放行。"""
        import _cli_audit_p0
        domains = tmp_path / "domains"
        domains.mkdir()
        (domains / "电子会计档案域.md").write_text(
            "| 回单认领 | 银行回单自动回传后关联付款单 | 证据链 | 回单匹配 / 认领 |\n",
            encoding="utf-8")
        assert _cli_audit_p0._audit_knowledge_terms_drift(
            glossary_path=_mk_glossary(tmp_path), domains_dir=str(domains)) is True
        assert "⚠ 0 项" in capsys.readouterr().out

    def test_unregistered_wording_not_judged(self, tmp_path, capsys):
        """不判：总纲未登记的用词（宁缺毋滥，不发明规则）。"""
        import _cli_audit_p0
        domains = tmp_path / "domains"
        domains.mkdir()
        (domains / "销售域.md").write_text("线索到手后要及时跟进。\n", encoding="utf-8")
        assert _cli_audit_p0._audit_knowledge_terms_drift(
            glossary_path=_mk_glossary(tmp_path), domains_dir=str(domains)) is True
        assert "⚠ 0 项" in capsys.readouterr().out

    def test_no_glossary_table_skips(self, tmp_path, capsys):
        """总纲无标准名登记表 → 跳过（不判），返回 True。"""
        import _cli_audit_p0
        g = tmp_path / "总纲.md"
        g.write_text("# 总纲\n\n无登记表。\n", encoding="utf-8")
        domains = tmp_path / "domains"
        domains.mkdir()
        (domains / "项目域.md").write_text("节点关联预算。\n", encoding="utf-8")
        assert _cli_audit_p0._audit_knowledge_terms_drift(
            glossary_path=str(g), domains_dir=str(domains)) is True
        out = capsys.readouterr().out
        assert "跳过" in out and "⚠" not in out


def _mk_sandbox(tmp_path, skill_text, knowledge_files=None):
    """构造 tmp 工程根：.folio/skills/<name>/SKILL.md + _knowledge 目标文件。"""
    root = tmp_path
    skill_dir = root / ".folio" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    for rel, content in (knowledge_files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return str(root / ".folio" / "skills"), str(root)


class TestAnchorIntegrity:
    def test_positive_missing_file_anchor_warns(self, tmp_path, capsys):
        """正例：skill 引用的 L2 文件不存在 → 失效文件锚 WARN。"""
        import _cli_audit_p0
        skills_dir, root = _mk_sandbox(
            tmp_path, "方法见 `_knowledge/methodology/methods/规划方法.md`。\n")
        assert _cli_audit_p0._audit_knowledge_anchor_integrity(
            skills_dir=skills_dir, script_dir=root) is True
        out = capsys.readouterr().out
        assert "失效文件锚" in out and "规划方法.md" in out

    def test_positive_missing_section_anchor_warns(self, tmp_path, capsys):
        """正例：文件在但无 §九 小节 → 失效章节锚 WARN（锚点改名静默失效场景）。"""
        import _cli_audit_p0
        skills_dir, root = _mk_sandbox(
            tmp_path,
            "环节定义以 `_knowledge/methodology/methods/规划方法.md` §九 为准。\n",
            {"_knowledge/methodology/methods/规划方法.md": "# 规划方法\n\n## 一、主链\n\n## 二、现状\n"})
        assert _cli_audit_p0._audit_knowledge_anchor_integrity(
            skills_dir=skills_dir, script_dir=root) is True
        out = capsys.readouterr().out
        assert "失效章节锚" in out and "§九" in out

    def test_negative_file_and_section_exist(self, tmp_path, capsys):
        """负例：文件锚 + 章节锚（中文数字小节）均存在 → 无 WARN。"""
        import _cli_audit_p0
        skills_dir, root = _mk_sandbox(
            tmp_path,
            "环节定义以 `_knowledge/methodology/methods/规划方法.md` §一 为准。\n",
            {"_knowledge/methodology/methods/规划方法.md": "# 规划方法\n\n## 一、主链\n"})
        assert _cli_audit_p0._audit_knowledge_anchor_integrity(
            skills_dir=skills_dir, script_dir=root) is True
        assert "⚠ 0 项" in capsys.readouterr().out

    def test_negative_arabic_ref_matches_cn_heading(self, tmp_path, capsys):
        """负例：阿拉伯 §4 与中文数字小节 `## 四、` 互为变体（真实形态两轨并存）。"""
        import _cli_audit_p0
        skills_dir, root = _mk_sandbox(
            tmp_path,
            "蓝图见 `_knowledge/methodology/methods/规划方法.md` §4。\n",
            {"_knowledge/methodology/methods/规划方法.md": "## 四、蓝图设计\n"})
        assert _cli_audit_p0._audit_knowledge_anchor_integrity(
            skills_dir=skills_dir, script_dir=root) is True
        assert "⚠ 0 项" in capsys.readouterr().out

    def test_non_knowledge_refs_not_judged(self, tmp_path, capsys):
        """不判：非 _knowledge 全路径引用（同包相对引用/meta 简写）。"""
        import _cli_audit_p0
        skills_dir, root = _mk_sandbox(
            tmp_path,
            "见 `references/requirements.md` §2 与 `meta/方法总纲与术语表.md` §4。\n")
        assert _cli_audit_p0._audit_knowledge_anchor_integrity(
            skills_dir=skills_dir, script_dir=root) is True
        assert "⚠ 0 项" in capsys.readouterr().out
