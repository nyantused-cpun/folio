# -*- coding: utf-8 -*-
"""C-F1 deliver receipt 回归（2026-09-07）：_write_deliver_receipt sidecar 契约。

sidecar 先例（cmd_confirm 的 <名>.confirm.json）：同目录、JSON、host 标记；
本 receipt 追加产物 sha256/字节数 + 图级 verify 摘要。写入失败降级 warn 不阻断。
"""
import hashlib
import json
import os
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _cli_generate import _write_deliver_receipt


def _setup(tmp_path):
    spec = tmp_path / "方案.yml"
    spec.write_text(yaml.safe_dump({
        "pages": [{"elements": [
            {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
             "title": "流程", "steps": [{"name": "a"}]},
        ]}],
    }, allow_unicode=True), encoding="utf-8")
    html = tmp_path / "方案.html"
    html.write_text("<html>交付物</html>", encoding="utf-8")
    pptx = tmp_path / "方案.pptx"
    pptx.write_bytes(b"pptx-bytes")
    return spec, html, pptx


def test_receipt_written_with_hashes_and_verify_digest(tmp_path):
    spec, html, pptx = _setup(tmp_path)
    _write_deliver_receipt(str(spec), str(html), str(pptx), "测试客户")

    receipt = json.loads((tmp_path / "方案.deliver.json").read_text(
        encoding="utf-8"))
    assert receipt["client"] == "测试客户"
    assert receipt["host"] in ("dsh", "kimi", "unknown")
    assert "delivered_at" in receipt

    assert receipt["spec"]["sha256"] == hashlib.sha256(
        spec.read_bytes()).hexdigest()
    for key in ("html", "pptx"):
        art = receipt["artifacts"][key]
        assert art["sha256"] and art["bytes"] > 0
        assert "error" not in art

    digest = receipt["verify"]["diagram_level"]
    assert digest["diagrams"] == 1
    assert digest["errors"] == []
    assert digest["warnings"] == []


def test_receipt_naming_follows_confirm_sidecar(tmp_path):
    """命名跟随 confirm 先例：<产物基名>.<用途>.json，与产物同目录。"""
    spec, html, pptx = _setup(tmp_path)
    _write_deliver_receipt(str(spec), str(html), str(pptx), "")
    assert (tmp_path / "方案.deliver.json").is_file()


def test_receipt_degrades_warn_on_write_failure(tmp_path, capsys):
    """receipt 写入失败不阻断交付（降级 warn 留痕，不抛异常）。"""
    spec, html, pptx = _setup(tmp_path)
    ghost = tmp_path / "no_such_dir" / "方案.html"   # 目录不存在 → open OSError
    _write_deliver_receipt(str(spec), str(ghost), str(pptx), "")
    assert "receipt 写入失败" in capsys.readouterr().out


def test_receipt_bad_spec_records_verify_error(tmp_path):
    """spec 不可解析：receipt 仍写出，verify 摘要记录降级原因。"""
    spec, html, pptx = _setup(tmp_path)
    spec.write_text("{{{ 坏 yaml", encoding="utf-8")
    _write_deliver_receipt(str(spec), str(html), str(pptx), "")
    receipt = json.loads((tmp_path / "方案.deliver.json").read_text(
        encoding="utf-8"))
    assert "error" in receipt["verify"]
    assert receipt["artifacts"]["html"]["sha256"]
