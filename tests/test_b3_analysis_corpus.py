# -*- coding: utf-8 -*-
import pytest
"""I-3 批2 B3 三区表语料排除机制测试（_embed_index analysis/ 扫描）。

覆盖：
- 确认事实区 [confirmed] 条目进语料（#confirmed 锚点）
- [draft] 条目不进语料，且排除条数经 warnings 可见
- 开放问题/框架缺口两区整区不进语料，排除清单可见
- 格式损坏（确认事实区无状态标记条目 / 缺固定小节）fail-closed：整文件不进语料
- analysis 属客户内容，走客户别名展开（与 context/decisions 一致）

全部用 tmp_path 造假工作区，绝不读写真实 _knowledge/。
"""

import _embed_index

_LONG = "内容足够长以通过二十字符的切片过滤门槛。" * 3


def _analysis_md(fact_entries, open_q=None, gaps=None):
    open_q = open_q if open_q is not None else ["| # | 开放问题 | 问谁 |", "|---|---|", "| 1 | 首期范围是否锁定？ | 老板 |"]
    gaps = gaps if gaps is not None else ["| 缺口 | 影响 |", "|---|---|", "| 生产制造域无域卡 | 缺先验 |"]
    return (
        "# 客户A · 三区表\n\n> 解析约定\n\n## 确认事实\n\n"
        + "\n".join(fact_entries)
        + "\n\n## 开放问题\n\n" + "\n".join(open_q)
        + "\n\n## 框架缺口\n\n" + "\n".join(gaps)
        + "\n\n## 备注\n\n自由说明。\n"
    )


def _fake_workspace(tmp_path, monkeypatch, analysis_text):
    clients = tmp_path / "_knowledge" / "clients"
    (clients / "客户A" / "analysis").mkdir(parents=True)
    (clients / "客户A" / "analysis" / "三区表.md").write_text(analysis_text, encoding="utf-8")
    monkeypatch.setattr(_embed_index, "SCRIPT_DIR", str(tmp_path))


class TestB3AnalysisCorpus:
    def test_confirmed_entries_indexed(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch, _analysis_md([
            "- [confirmed] 库位管理仅停留在仓库层级 ｜ 依据类型：材料原文 ｜ 证据：file:refs/x.md",
            "- [confirmed] 条码格式不统一一物多码 ｜ 依据类型：材料原文 ｜ 证据：session:2",
        ]))
        corpus, _ = _embed_index.scan_corpus_with_warnings()
        hits = [(p, t) for p, t in corpus if "analysis" in p]
        assert len(hits) == 1 and hits[0][0].endswith("三区表.md#confirmed"), \
            "confirmed 条目应以 #confirmed 锚点聚合成单块入语料"
        assert "库位管理仅停留在仓库层级" in hits[0][1]
        assert "条码格式不统一一物多码" in hits[0][1]

    def test_draft_entries_excluded_visible(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch, _analysis_md([
            "- [confirmed] 已确认事实甲 ｜ 依据类型：材料原文 ｜ 证据：file:refs/x.md",
            "- [draft] 未确认推断词ZQWdraft ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        hits = [t for p, t in corpus if "analysis" in p]
        assert hits and "未确认推断词ZQWdraft" not in hits[0], "draft 条目不得进语料"
        assert any("语料排除" in w and "draft 条目 1 条" in w for w in warnings), \
            "draft 排除条数应在 warnings 可见"

    def test_open_questions_and_gaps_excluded(self, tmp_path, monkeypatch):
        _fake_workspace(tmp_path, monkeypatch, _analysis_md(
            ["- [confirmed] 已确认事实乙 ｜ 依据类型：召回片段 ｜ 证据：session:3"],
            open_q=["| # | 开放问题 | 问谁 |", "|---|---|",
                    "| 1 | 开放问题词ZQWopen 是真的吗？ | 老板 |"],
            gaps=["| 缺口 | 影响 |", "|---|---|", "| 框架缺口词ZQWgap 无卡 | 缺先验 |"],
        ))
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        analysis_texts = [t for p, t in corpus if "analysis" in p]
        assert analysis_texts, "confirmed 条目应进语料"
        joined = "\n".join(analysis_texts)
        assert "开放问题词ZQWopen" not in joined, "开放问题区不得进语料"
        assert "框架缺口词ZQWgap" not in joined, "框架缺口区不得进语料"
        assert any("语料排除" in w and "开放问题区 1 条" in w for w in warnings), \
            "开放问题区排除应可见"
        assert any("语料排除" in w and "框架缺口区 1 条" in w for w in warnings), \
            "框架缺口区排除应可见"

    def test_unmarked_fact_entry_fail_closed(self, tmp_path, monkeypatch):
        """确认事实区出现无状态标记条目 = 格式损坏 -> 整文件 fail-closed 不进语料。"""
        _fake_workspace(tmp_path, monkeypatch, _analysis_md([
            "- [confirmed] 已确认事实丙 ｜ 依据类型：材料原文 ｜ 证据：file:refs/x.md",
            "- 无标记条目词ZQWcorrupt（忘了写状态）",
        ]))
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        assert not any("analysis" in p for p, _ in corpus), \
            "格式损坏应整文件 fail-closed，连 confirmed 条目也不进"
        assert any("语料排除" in w and "fail-closed" in w and "无状态标记" in w
                   for w in warnings), "fail-closed 原因应可见"

    def test_missing_sections_fail_closed(self, tmp_path, monkeypatch):
        """缺「确认事实」固定小节 = 非三区表格式 -> fail-closed。"""
        _fake_workspace(tmp_path, monkeypatch,
                        "# 随手笔记\n\n## 随便聊聊\n\n- [confirmed] 假装确认词ZQWfake\n")
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        assert not any("analysis" in p for p, _ in corpus)
        assert any("语料排除" in w and "fail-closed" in w for w in warnings)

    def test_no_confirmed_entries_no_chunk(self, tmp_path, monkeypatch):
        """全 draft 的合法三区表：不产出语料块，但排除清单可见。"""
        _fake_workspace(tmp_path, monkeypatch, _analysis_md([
            "- [draft] 全部待确认词ZQWall ｜ 依据类型：推断 ｜ 证据：session:1",
        ]))
        corpus, warnings = _embed_index.scan_corpus_with_warnings()
        assert not any("analysis" in p for p, _ in corpus)
        assert any("draft 条目 1 条" in w for w in warnings)

    def test_analysis_uses_client_alias_expansion(self, tmp_path, monkeypatch):
        """analysis 属客户内容，应走客户别名展开（与 context/decisions 分支一致）。"""
        _fake_workspace(tmp_path, monkeypatch, _analysis_md([
            "- [confirmed] 系统名代称词ZQWalias 在用 ｜ 依据类型：材料原文 ｜ 证据：session:1",
        ]))
        calls = []

        import _aliases
        orig_expand = _aliases.expand_text

        def _spy_expand(text, aliases):
            calls.append(text)
            return orig_expand(text, aliases)

        monkeypatch.setattr("_aliases.expand_text", _spy_expand, raising=False)
        corpus, _ = _embed_index.scan_corpus_with_warnings()
        assert any("analysis" in p for p, _ in corpus)
        assert any("代称词ZQWalias" in t for t in calls), \
            "analysis confirmed 块应经 expand_text 别名展开"


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
