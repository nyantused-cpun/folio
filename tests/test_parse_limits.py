# -*- coding: utf-8 -*-
"""B2 回归：二进制解析大小/页数上限（P2-5）。

inbox 投放巨 PDF / zip-bomb xlsx 曾可经 classify/inbox-scan 自动链
触发内存耗尽。上限单点在 _pipeline（read_full 与 _doc_extract 同源复用）。
"""


from _doc_extract import extract_document
from _pipeline import MAX_PDF_PAGES, MAX_READ_BYTES, read_full, size_exceeded


class TestSizeLimit:
    def test_small_file_not_exceeded(self, tmp_path):
        p = tmp_path / "small.txt"
        p.write_text("内容", encoding="utf-8")
        assert size_exceeded(str(p)) is None

    def test_oversized_rejected_before_parse(self, tmp_path):
        """超大文件拒绝且不触发 reader（稀疏文件不占真实磁盘/内存）。"""
        p = tmp_path / "huge.txt"
        with open(p, "wb") as f:
            f.seek(MAX_READ_BYTES + 1)
            f.write(b"\0")
        msg = size_exceeded(str(p))
        assert msg is not None and "过大" in msg

    def test_read_full_returns_error_tuple(self, tmp_path):
        p = tmp_path / "huge.txt"
        with open(p, "wb") as f:
            f.seek(MAX_READ_BYTES + 1)
            f.write(b"\0")
        summary, cache = read_full(str(p))
        assert "过大" in summary
        assert cache == ""  # 未写缓存

    def test_extract_document_size_error(self, tmp_path):
        p = tmp_path / "huge.txt"
        with open(p, "wb") as f:
            f.seek(MAX_READ_BYTES + 1)
            f.write(b"\0")
        out = extract_document(str(p), as_json=True)
        assert out["ok"] is False
        assert "过大" in out["error"]


class TestPdfPageCap:
    def test_page_cap_constant_sane(self):
        assert 0 < MAX_PDF_PAGES <= 10000

    def test_read_pdf_caps_pages(self, monkeypatch, tmp_path):
        """mock fitz 文档验证超页截断并声明（不依赖真实巨 PDF）。"""
        import _pipeline

        class FakePage:
            def get_text(self):
                return "正文"

        class FakeDoc:
            page_count = MAX_PDF_PAGES + 50

            def __iter__(self):
                return iter(FakePage() for _ in range(self.page_count))

            def close(self):
                pass

        class FakeFitz:
            def open(self, path):
                return FakeDoc()

        monkeypatch.setitem(__import__("sys").modules, "fitz", FakeFitz())
        out = _pipeline.read_pdf("fake.pdf")
        assert f"仅提取前 {MAX_PDF_PAGES} 页" in out
        # 第 MAX_PDF_PAGES 页在内，其后不再出现
        assert f"=== 第 {MAX_PDF_PAGES} 页 ===" in out
