# -*- coding: utf-8 -*-
"""T3 BM25 多字段 + 元数据测试。

覆盖：
- title/section 字段抽取
- 多字段索引构建与标题命中加权
- 旧单字段索引回退兼容
"""

import _bm25


class TestFieldExtraction:
    def test_doc_title_from_path(self):
        assert _bm25._doc_title_from_path("_knowledge/clients/甲/方案_v1.md#p0") == "方案_v1"
        assert _bm25._doc_title_from_path("docs/方法.md#h0") == "方法"

    def test_section_from_text(self):
        text = "前置说明\n## 第一章 方案\n正文内容"
        assert _bm25._section_from_text(text) == "第一章 方案"
        assert _bm25._section_from_text("无标题正文") == ""


class TestBm25MultiField:
    def test_title_hit_ranks_above_text_absence(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_bm25, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)

        # 方案 只出现在 doc1 的标题里，不出现在任何正文中
        paths = [
            f"{tmp_path}/clients/甲/方案.md",
            f"{tmp_path}/clients/甲/其他.md",
            f"{tmp_path}/clients/甲/第三.md",
        ]
        texts = [
            "正文 完全 无关 内容",
            "正文 完全 无关 内容",
            "正文 完全 无关 内容",
        ]
        _bm25.build_bm25_index(paths, texts)
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)

        results = _bm25.query_bm25("方案", top_k=10)
        assert results, "标题命中应能通过多字段 BM25 召回"
        assert results[0][0].endswith("方案.md")

    def test_fallback_when_old_index_lacks_multifield(self, tmp_path, monkeypatch):
        from _paths import safe_pickle_load, safe_pickle_dump
        monkeypatch.setattr(_bm25, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(_bm25, "BM25_INDEX_PATH", str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)

        paths = [
            f"{tmp_path}/clients/甲/a.md",
            f"{tmp_path}/clients/甲/b.md",
            f"{tmp_path}/clients/甲/c.md",
        ]
        texts = ["报价 单 内容", "完全 无关", "别的内容 也无关"]
        _bm25.build_bm25_index(paths, texts)
        data = safe_pickle_load(str(tmp_path / "bm25_index.pkl"))
        data.pop("bm25_title", None)
        data.pop("bm25_section", None)
        data.pop("bm25_text", None)
        safe_pickle_dump(data, str(tmp_path / "bm25_index.pkl"))
        monkeypatch.setattr(_bm25, "_INDEX_CACHE", None)

        results = _bm25.query_bm25("报价")
        assert results
        assert results[0][0].endswith("a.md")