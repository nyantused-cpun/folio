# -*- coding: utf-8 -*-
"""doc-extract run() 退出码回归（B5#B2，2026-09-06）。

原实现按正文子串（"不存在/失败/不支持"）猜成败，正文含这些词即误判 exit 1；
修复后统一走 extract_document dict 的 ok 字段。
"""
import _doc_extract


def test_text_containing_fail_words_exits_zero(tmp_path, capsys):
    p = tmp_path / "doc.txt"
    p.write_text("传统方案失败的三点原因：成本高。世上不存在银弹。", encoding="utf-8")
    rc = _doc_extract.run([str(p)])
    assert rc == 0
    assert "传统方案失败" in capsys.readouterr().out


def test_missing_file_exits_one(capsys):
    rc = _doc_extract.run(["__不存在_的文件__.txt"])
    assert rc == 1
    assert "文件不存在" in capsys.readouterr().out


def test_json_success_exits_zero(tmp_path, capsys):
    p = tmp_path / "doc.txt"
    p.write_text("正常内容", encoding="utf-8")
    rc = _doc_extract.run([str(p), "--json"])
    assert rc == 0
    assert '"ok": true' in capsys.readouterr().out


def test_json_failure_exits_one(capsys):
    rc = _doc_extract.run(["__不存在_的文件__.txt", "--json"])
    assert rc == 1


# ── P3-2026-09-06：非法 fmt_hint fail-soft（原实现透传令 FORMAT_READERS 取键
#    KeyError，程序化调用拿到裸 traceback）─────────────────────────────────

def test_detect_format_rejects_unknown_hint():
    """detect_format 单元：非法 hint 返回 None，合法 hint 优先级不变。"""
    assert _doc_extract.detect_format("a.unknown", "docx2") is None
    assert _doc_extract.detect_format("a.unknown", "docx") == "docx"
    assert _doc_extract.detect_format("a.pdf", "auto") == "pdf"
    assert _doc_extract.detect_format("a.unknown") is None


def test_invalid_format_hint_fails_soft(tmp_path, capsys):
    """非法 --format：中文报错 exit 1，不抛 KeyError。"""
    p = tmp_path / "doc.txt"
    p.write_text("内容", encoding="utf-8")
    rc = _doc_extract.run([str(p), "--format", "docx2"])
    assert rc == 1
    out = capsys.readouterr()
    assert "不支持的格式: docx2" in out.out
    assert "KeyError" not in out.out + out.err


def test_invalid_format_hint_json_payload(tmp_path, capsys):
    """--json 程序化消费：非法 hint 走 error 字段，退出码 1，无异常逃逸。"""
    import json
    p = tmp_path / "doc.txt"
    p.write_text("内容", encoding="utf-8")
    rc = _doc_extract.run([str(p), "--format", "docx2", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "docx2" in payload["error"]
