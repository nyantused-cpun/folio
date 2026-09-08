# -*- coding: utf-8 -*-
"""I-9 零测试模块冒烟测试（7 个模块各 ≥1 条直接测试）。

覆盖：_snippet / _compress / _indexer / _archive_auto / _pipeline /
     _doc_extract / _context_health。
纯函数直接测；涉及路径的用 tmp_path + monkeypatch 重定向，绝不写真实知识库。
"""


class TestCompress:
    def test_extract_attention_keeps_attention_lines(self):
        from _compress import extract_attention
        out = extract_attention("第一行\n决定采用方案A\n第二行")
        assert isinstance(out, str)
        assert "第一行" in out and "第二行" in out  # 首尾行保留
        assert "决定采用方案A" in out              # 决策词行保留（ATTENTION_PATTERNS）

    def test_compress_document_truncates(self):
        from _compress import compress_document
        out = compress_document("一" * 500, max_chars=200)
        assert len(out) <= 300  # 含截断标记等

    def test_split_by_structure_returns_list(self):
        from _compress import split_by_structure
        parts = split_by_structure("\n## 一\n内容\n## 二\n内容")
        assert isinstance(parts, list) and len(parts) >= 2


class TestSnippet:
    def test_save_snippet_writes_file(self, tmp_path, monkeypatch):
        import _snippet
        monkeypatch.setattr(_snippet, "SNIPPETS_DIR", str(tmp_path / "snips"))
        monkeypatch.setattr(_snippet, "INDEX_PATH", str(tmp_path / "snips" / "index.json"))
        ok = _snippet.save_snippet("测试卡", "card", "# 内容", source="file:a.md", tags=["x"], client="测试客户")
        assert ok is True
        assert (tmp_path / "snips" / "card" / "测试卡.md").exists()

    def test_save_snippet_invalid_type(self, tmp_path, monkeypatch, capsys):
        import _snippet
        monkeypatch.setattr(_snippet, "SNIPPETS_DIR", str(tmp_path / "snips"))
        monkeypatch.setattr(_snippet, "INDEX_PATH", str(tmp_path / "snips" / "index.json"))
        assert _snippet.save_snippet("x", "badtype", "内容") is False


class TestIndexer:
    def test_extract_tags_returns_list(self):
        from _indexer import _extract_tags
        tags = _extract_tags("本方案覆盖业务系统、数据平台与流程管理，聚焦采购与库存。")
        assert isinstance(tags, list) and len(tags) > 0
        assert len(tags) <= 10


class TestArchiveAuto:
    def test_archive_note_illegal_dest_errors(self):
        from _archive_auto import archive_note
        r = archive_note(["a.txt"], dest="bad")
        assert r["errors"] and r["added"] == []

    def test_archive_note_client_requires_name(self):
        from _archive_auto import archive_note
        r = archive_note(["a.txt"], dest="client")
        assert r["errors"]

    def test_record_and_read_session_start(self, tmp_path, monkeypatch):
        import _archive_auto
        monkeypatch.setattr(_archive_auto, "LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setattr(_archive_auto, "SESSION_START_LOG", str(tmp_path / "logs" / "s.txt"))
        _archive_auto.record_session_start("测试客户")
        ts, client = _archive_auto._read_session_start()
        assert client == "测试客户" and ts


class TestPipeline:
    def test_read_txt(self, tmp_path):
        from _pipeline import read_txt
        p = tmp_path / "a.txt"
        p.write_text("你好 世界", encoding="utf-8")
        assert read_txt(str(p)) == "你好 世界"


class TestDocExtract:
    def test_detect_format_by_extension(self):
        from _doc_extract import detect_format
        assert detect_format("x.txt") == "txt"
        assert detect_format("x.pdf") == "pdf"
        assert detect_format("x.unknown") is None

    def test_detect_format_hint_priority(self):
        from _doc_extract import detect_format
        assert detect_format("x.unknown", fmt_hint="docx") == "docx"


class TestContextHealth:
    def test_no_client_returns_warn(self):
        from _context_health import run_context_health
        r = run_context_health("")
        assert r["verdict"] == "warn"
        assert any(c["id"] == "C1" for c in r["checks"])
