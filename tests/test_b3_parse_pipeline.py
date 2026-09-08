# -*- coding: utf-8 -*-
"""B3 批 A5 组回归测试：
1. P1-12 _read_tender as_json 闭环（错误串不再当招标全文）+ .doc 显式拒绝
2. P2 read_xlsx_structured 表头回退扫描（首行空表/合并标题行）
3. P2 read_materials 逐文件异常隔离（坏文件告警跳过）
4. P1-13 图形提取缓存 fail-closed 门接线（畸形图形结果不入缓存）
"""

import pytest

import _pipeline
from _pipeline import read_full_text, read_xlsx_structured
from _bid_parse import _read_tender
import _outline_to_spec
from _outline_to_spec import read_materials
from _diagram_extract import diagram_result_cacheable, ROLE_DIAGRAM_SPEC


# ---------------------------------------------------------------------------
# P1-12 _read_tender
# ---------------------------------------------------------------------------

class TestReadTender(object):
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_tender(str(tmp_path / "不存在.pdf"))

    def test_error_dict_raises(self, tmp_path, monkeypatch):
        """extract_document 失败（as_json=True 返回 ok=False dict）→ 拒绝，不产出全文。"""
        f = tmp_path / "t.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        import _doc_extract
        monkeypatch.setattr(_doc_extract, "extract_document",
                            lambda *a, **k: {"ok": False, "error": "读取失败: 坏文件"})
        with pytest.raises(ValueError, match="读取失败"):
            _read_tender(str(f))

    def test_error_string_never_treated_as_text(self, tmp_path, monkeypatch):
        """历史缺陷复现路径：错误字符串（非 dict）不得被当招标全文返回。"""
        f = tmp_path / "t.docx"
        f.write_bytes(b"PK fake")
        import _doc_extract
        monkeypatch.setattr(_doc_extract, "extract_document",
                            lambda *a, **k: "读取失败: 解析异常")
        with pytest.raises(ValueError, match="读取失败"):
            _read_tender(str(f))

    def test_success_returns_text(self, tmp_path, monkeypatch):
        f = tmp_path / "t.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        import _doc_extract

        def _fake(path, fmt_hint="auto", mode="text", as_json=False):
            assert as_json is True, "必须走 as_json=True 恒返 dict 契约"
            return {"ok": True, "text": "第一章 投标须知"}
        monkeypatch.setattr(_doc_extract, "extract_document", _fake)
        assert _read_tender(str(f)) == "第一章 投标须知"

    def test_doc_rejected(self, tmp_path):
        f = tmp_path / "t.doc"
        f.write_bytes(b"\xd0\xcf\x11\xe0 OLE2")
        with pytest.raises(ValueError, match="\\.doc"):
            _read_tender(str(f))


# ---------------------------------------------------------------------------
# P2 read_xlsx_structured 表头回退扫描
# ---------------------------------------------------------------------------

def _make_xlsx(path, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)


class TestXlsxHeaderFallback(object):
    def test_empty_first_row(self, tmp_path):
        """首行空表：表头下移到首个 ≥2 非空格行，数据行正确配对。"""
        p = str(tmp_path / "a.xlsx")
        _make_xlsx(p, [[None, None, None],
                       ["产品", "数量", "单价"],
                       ["服务器", 2, 30000]])
        chunks = read_xlsx_structured(p)
        data = [t for t, _a in chunks if "服务器" in t]
        assert data and "产品=服务器" in data[0] and "数量=2" in data[0]

    def test_merged_title_row(self, tmp_path):
        """首行合并标题（单非空格）：跳过标题，取真实表头行配对。"""
        p = str(tmp_path / "b.xlsx")
        _make_xlsx(p, [["XX 项目报价单"],
                       ["产品", "数量"],
                       ["交换机", 4]])
        chunks = read_xlsx_structured(p)
        data = [t for t, _a in chunks if "交换机" in t]
        assert data and "产品=交换机" in data[0] and "数量=4" in data[0]
        title = [t for t, _a in chunks if "报价单" in t]
        assert title and "=" not in title[0].split("]", 1)[1]

    def test_all_single_cell_fallback_warns(self, tmp_path, capsys):
        """前 5 个非空行都无表头形态：退化首个非空行并告警，不丢行。"""
        p = str(tmp_path / "c.xlsx")
        _make_xlsx(p, [["备注一"], ["备注二"], ["备注三"]])
        chunks = read_xlsx_structured(p)
        assert len(chunks) == 2  # 首行作表头，其余两行出块
        assert "警告" in capsys.readouterr().out

    def test_normal_header_unchanged(self, tmp_path):
        """常规表头在第 0 行：行为与修复前一致。"""
        p = str(tmp_path / "d.xlsx")
        _make_xlsx(p, [["产品", "数量"], ["服务器", 2]])
        chunks = read_xlsx_structured(p)
        assert len(chunks) == 1
        assert "产品=服务器" in chunks[0][0]


# ---------------------------------------------------------------------------
# P2 read_materials 逐文件异常隔离
# ---------------------------------------------------------------------------

class TestReadMaterialsIsolation(object):
    def test_bad_file_skipped_good_file_kept(self, tmp_path, monkeypatch):
        refs = tmp_path / "refs"
        refs.mkdir()
        (refs / "good.txt").write_text("正常材料内容", encoding="utf-8")
        (refs / "bad.txt").write_bytes(b"\xd6\xd0\xb9\xfa GBK bytes")  # 非 UTF-8
        monkeypatch.setattr(_pipeline, "CACHE_DIR", str(tmp_path / "cache"))
        out = read_materials([str(refs / "good.txt"), str(refs / "bad.txt")],
                             allow_outside=True)
        assert "正常材料内容" in out

    def test_all_bad_returns_empty_joined(self, tmp_path, monkeypatch, capsys):
        refs = tmp_path / "refs"
        refs.mkdir()
        (refs / "bad.txt").write_bytes(b"\xff\xfe\x00bad")
        monkeypatch.setattr(_pipeline, "CACHE_DIR", str(tmp_path / "cache"))
        out = read_materials([str(refs / "bad.txt")], allow_outside=True)
        assert out == ""
        assert "警告" in capsys.readouterr().out

    def test_read_full_text_returns_none_on_error(self, tmp_path, monkeypatch):
        p = tmp_path / "gbk.txt"
        p.write_bytes(b"\xd6\xd0\xb9\xfa")
        monkeypatch.setattr(_pipeline, "CACHE_DIR", str(tmp_path / "cache"))
        assert read_full_text(str(p)) is None


# ---------------------------------------------------------------------------
# P1-13 图形提取缓存 fail-closed 门
# ---------------------------------------------------------------------------

class TestDiagramCacheGate(object):
    def test_non_diagram_role_always_cacheable(self):
        assert diagram_result_cacheable({"role": "body"}, {"content": "x"})
        assert diagram_result_cacheable({}, None)

    def test_malformed_diagram_result_rejected(self):
        section = {"role": "roadmap", "section": "实施路线"}
        assert "roadmap" in ROLE_DIAGRAM_SPEC
        assert diagram_result_cacheable(section, {"content": "缺里程碑字段"}) is False

    def test_valid_diagram_result_cacheable(self):
        section = {"role": "roadmap", "section": "实施路线"}
        result = {"milestones": [
            {"label": "启动", "when": "M1", "desc": " kickoff"},
            {"label": "上线", "when": "M3", "desc": " go-live"},
        ]}
        assert diagram_result_cacheable(section, result) is True

    def test_wiring_malformed_result_not_cached(self, tmp_path, monkeypatch):
        """接线端到端：畸形图形结果走完 extract_section_content 后不落缓存。"""
        import _cloud_llm
        cache_path = tmp_path / "llm_extract_cache.json"
        monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH", str(cache_path))
        monkeypatch.setattr(_cloud_llm, "chat",
                            lambda *a, **k: '{"content": "缺里程碑字段"}')
        section = {"role": "roadmap", "section": "实施路线"}
        out = _outline_to_spec.extract_section_content(section, materials_text="材料")
        assert out == {"content": "缺里程碑字段"}  # 提取本身成功返回
        assert not cache_path.exists()  # 但门拦截了缓存写入

    def test_wiring_non_diagram_result_cached(self, tmp_path, monkeypatch):
        import _cloud_llm
        cache_path = tmp_path / "llm_extract_cache.json"
        monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH", str(cache_path))
        monkeypatch.setattr(_cloud_llm, "chat",
                            lambda *a, **k: '{"content": "现状描述"}')
        section = {"role": "body", "section": "现状"}
        _outline_to_spec.extract_section_content(section, materials_text="材料")
        assert cache_path.exists()  # 非图形 role 缓存语义不变
