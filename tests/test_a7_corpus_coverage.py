# -*- coding: utf-8 -*-
"""I-3 批1 A7 语料断点修复：domains/methodology/keynote 扫描覆盖测试。

覆盖：
- 客户 keynote.md 入语料（#full 锚点，人批准 permanent 资产）
- _knowledge/domains/*.md 入语料，*_草稿.md 过程稿排除且排除清单可见
- _knowledge/methodology/**/*.md 递归入语料，ppt-refs/ 与 _ 开头目录排除
- 全局内容（domains/methodology）不做客户别名展开（P2-9 先例）

全部用 tmp_path 造假工作区，绝不读写真实 _knowledge/。
"""

import _embed_index

_LONG = "内容足够长以通过二十字符的切片过滤门槛。" * 3 + "\n"


def _fake_workspace(tmp_path, monkeypatch):
    clients = tmp_path / "_knowledge" / "clients"
    (clients / "客户A").mkdir(parents=True)
    (clients / "客户A" / "keynote.md").write_text(
        "# 客户A 基调卡\n\n## 线清单\n" + _LONG, encoding="utf-8")
    domains = tmp_path / "_knowledge" / "domains"
    domains.mkdir(parents=True)
    (domains / "费控域.md").write_text("## 费控域\n" + _LONG, encoding="utf-8")
    (domains / "9.0财务域_草稿.md").write_text("## 财务域草稿\n" + _LONG, encoding="utf-8")
    meth = tmp_path / "_knowledge" / "methodology"
    (meth / "methods").mkdir(parents=True)
    (meth / "methods" / "诊断方法.md").write_text("## 诊断方法\n" + _LONG, encoding="utf-8")
    (meth / "ppt-refs" / "_extracted").mkdir(parents=True)
    (meth / "ppt-refs" / "_extracted" / "1026_IT架构蓝图.md").write_text(
        "## 外部提取件\n" + _LONG, encoding="utf-8")
    (meth / "_template").mkdir()
    (meth / "_template" / "模板.md").write_text("## 模板\n" + _LONG, encoding="utf-8")
    monkeypatch.setattr(_embed_index, "SCRIPT_DIR", str(tmp_path))


class TestA7CorpusCoverage:
    def test_keynote_scanned(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch)
        corpus, _ = _embed_index.scan_corpus_with_warnings()
        paths = [p for p, _ in corpus]
        assert any("客户A" in p and "keynote.md#full" in p for p in paths), \
            "客户 keynote.md 应以 #full 锚点入语料"

    def test_domains_scanned_drafts_excluded(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch)
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        paths = [p for p, _ in corpus]
        assert any("domains" in p and "费控域" in p for p in paths), \
            "domains 域卡应入语料"
        assert not any("_草稿" in p for p in paths), "过程稿不得入语料"
        assert any("语料排除" in w and "_草稿" in w for w in warnings), \
            "过程稿排除应在清单中可见"

    def test_methodology_scanned_ppt_refs_excluded(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch)
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        paths = [p for p, _ in corpus]
        assert any("methodology" in p and "诊断方法" in p for p in paths), \
            "methodology 方法件应递归入语料"
        assert not any("ppt-refs" in p for p in paths), \
            "ppt-refs 外部提取件不得入语料"
        assert not any("_template" in p for p in paths), "模板目录不得入语料"
        assert any("语料排除" in w and "ppt-refs" in w for w in warnings), \
            "ppt-refs 排除应在清单中可见"

    def test_global_md_no_alias_expansion(self, tmp_path, monkeypatch):
        """domains/methodology 为全局内容，不应用上个客户的别名映射展开（P2-9 先例）。"""
        _fake_workspace(tmp_path, monkeypatch)
        marker = "全局专属词ZQW"
        (tmp_path / "_knowledge" / "domains" / "费控域.md").write_text(
            "## 费控域\n" + marker + _LONG, encoding="utf-8")

        def _poison_expand(text, aliases):
            return text.replace(marker, "被别名污染")

        monkeypatch.setattr("_aliases.expand_text", _poison_expand, raising=False)
        corpus, _ = _embed_index.scan_corpus_with_warnings()
        dom_texts = [t for p, t in corpus if "费控域" in p]
        assert dom_texts and any(marker in t for t in dom_texts), \
            "domains 内容不得经客户别名展开"
