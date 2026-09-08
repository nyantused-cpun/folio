# -*- coding: utf-8 -*-
"""T1 分块器 v2 测试。

覆盖：
- <20 字段落不再丢弃：并入相邻块
- 标题后短句合并正确
- v2 块元数据（chunk_id / doc_hash / chunker_version / prev_block_id）
- 确需丢弃的噪声块写入 dropped_paragraphs.log
"""

import json

import _embed_index


def _long_paragraph(text="金额足够长的段落内容用于构造块。", repeat=12):
    return (text * repeat)


class TestShortParagraphMerged:
    def test_short_amount_paragraph_not_lost(self):
        text = (
            "# 测试文档\n\n"
            + _long_paragraph()
            + "\n\n"
            "报价金额 15 万元\n\n"
            + _long_paragraph("后续正文内容足够长。")
        )
        chunks = _embed_index._sliding_window_chunks(text, chunk_size=500, overlap=100)
        assert chunks
        assert any("报价金额 15 万元" in c for c in chunks), "短字段落不应被丢弃"

    def test_short_sentence_before_heading_merged(self):
        text = (
            "前置短句\n\n"
            "# 标题\n\n"
            + _long_paragraph("标题下的正文内容足够长。")
        )
        chunks = _embed_index._sliding_window_chunks(text, chunk_size=500, overlap=100)
        assert chunks
        assert any("前置短句" in c for c in chunks), "标题前短句应并入相邻块"


class TestV2Metadata:
    def test_chunk_metadata_shape_and_alignment(self):
        text = (
            "# 文档\n\n"
            + _long_paragraph(repeat=20)
            + "\n\n"
            + _long_paragraph("第二段内容足够长。", repeat=20)
        )
        chunks = _embed_index._sliding_window_chunks_v2(
            text, chunk_size=300, overlap=100
        )
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_id"] == i
            assert chunk["chunker_version"] == _embed_index.CHUNKER_VERSION
            assert chunk["doc_hash"] == _embed_index._doc_hash(text)
            assert chunk["prev_block_id"] == (i - 1 if i > 0 else None)
            assert chunk["text"]

    def test_wrapper_keeps_list_of_str(self):
        text = "# 文档\n\n" + _long_paragraph()
        chunks = _embed_index._sliding_window_chunks(text)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)


class TestDroppedLog:
    def test_noise_drop_is_auditable(self, tmp_path, monkeypatch):
        log_path = tmp_path / "dropped_paragraphs.log"
        monkeypatch.setattr(_embed_index, "DROPPED_LOG_PATH", str(log_path))
        # 纯符号/纯噪声块仍会被过滤，write_dropped_log=True 时留下审计记录
        text = "=" * 600 + "\n\n" + _long_paragraph()
        chunks = _embed_index._sliding_window_chunks_v2(
            text, chunk_size=500, overlap=100, write_dropped_log=True
        )
        assert chunks
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines
        record = json.loads(lines[-1])
        assert record["chunker_version"] == _embed_index.CHUNKER_VERSION
        assert record["doc_hash"] == _embed_index._doc_hash(text)


class TestHeadingNotOrphaned:
    """C-B2：标题边界感知——标题未并入正文前不可单独成 chunk。"""

    def _assert_no_heading_only_chunk(self, chunks):
        for c in chunks:
            assert not _embed_index._is_heading_only_block(c), \
                f"标题落单成独立 chunk: {c[:50]!r}"

    def test_heading_before_huge_paragraph_not_orphaned(self):
        huge = "超大段落内容。" * 80  # > chunk_size，走截断分支
        chunks = _embed_index._sliding_window_chunks(
            "# 项目背景\n\n" + huge, chunk_size=500, overlap=100
        )
        assert chunks
        self._assert_no_heading_only_chunk(chunks)
        # 标题并入超大段落首切片，作为块首
        assert chunks[0].startswith("# 项目背景")
        assert "超大段落内容。" in chunks[0]

    def test_consecutive_headings_not_orphaned(self):
        text = (
            "# 第一章\n\n"
            "## 第一节\n\n"
            + _long_paragraph("节内正文内容足够长。")
        )
        chunks = _embed_index._sliding_window_chunks(
            text, chunk_size=500, overlap=100
        )
        assert chunks
        self._assert_no_heading_only_chunk(chunks)
        # 连续标题合并为一个块首，带正文
        assert chunks[-1].startswith("# 第一章\n\n## 第一节")

    def test_heading_at_doc_end_merged_into_previous(self):
        text = _long_paragraph() + "\n\n# 附录"
        chunks = _embed_index._sliding_window_chunks(
            text, chunk_size=500, overlap=100
        )
        assert chunks
        self._assert_no_heading_only_chunk(chunks)
        assert chunks[-1].rstrip().endswith("# 附录")

    def test_heading_with_body_is_block_head(self):
        """中部标题 + 正文：标题正常成为块首（既有行为，防回退）。"""
        text = (
            _long_paragraph()
            + "\n\n## 第二节\n\n"
            + _long_paragraph("第二节正文内容足够长。")
        )
        chunks = _embed_index._sliding_window_chunks(
            text, chunk_size=500, overlap=100
        )
        assert len(chunks) >= 2
        heads = [c.split("\n\n")[0] for c in chunks]
        assert any(h.startswith("## 第二节") for h in heads)

    def test_heading_only_doc_falls_back_to_single_chunk(self):
        """全文只有标题、无正文可并：允许落单（无可并对象）。"""
        chunks = _embed_index._sliding_window_chunks(
            "# 只有标题", chunk_size=500, overlap=100
        )
        assert chunks == ["# 只有标题"]

    def test_headings_then_trailing_short_sentence_not_orphaned(self):
        """连续标题后仅跟短句收尾：短句是正文，标题块应与之同块。"""
        chunks = _embed_index._sliding_window_chunks(
            "# 第一章\n\n## 第一节\n\n本节小结", chunk_size=500, overlap=100
        )
        assert len(chunks) == 1
        self._assert_no_heading_only_chunk(chunks)
        assert "本节小结" in chunks[0]