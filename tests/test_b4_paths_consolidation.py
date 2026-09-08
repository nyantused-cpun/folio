# -*- coding: utf-8 -*-
"""B4-G5：SCRIPT_DIR 收拢回归（D1 单一数据源，事实源 _paths.py）。

14 个根模块的本地定义 `SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))`
统一收拢为 `from _paths import SCRIPT_DIR`。本文件两层断言：

1. 值一致：import 后各模块属性 SCRIPT_DIR == _paths.SCRIPT_DIR（同目录下
   两种写法本就等值，收拢后由事实源保证不再漂移）；
2. 语义不变：`from X import Y` 导入后 Y 仍是 X 的模块全局——monkeypatch
   模块属性后，函数体内裸名引用必须读到补丁值（既有 tests monkeypatch 面
   —— test_archive_auto_v2 / test_b3_analysis_corpus / test_b4_c2_direction /
   test_audit_2026_07_23_fixes_round2 等——不因收拢而缩水）。
"""
import os
import sys

import _paths
import _archive_auto
import _bm25
import _classify
import _cli_infra
import _diagram_extract
import _doc_extract
import _embed_index
import _inbox_registry
import _inbox_scan
import _outline_to_spec
import _pipeline
import _quote_spec_gen
import _snippet
import _verify

# 收拢清单（B4-G5 改动的 14 个模块）
CONSOLIDATED = [
    _archive_auto, _bm25, _classify, _cli_infra, _diagram_extract,
    _doc_extract, _embed_index, _inbox_registry, _inbox_scan,
    _outline_to_spec, _pipeline, _quote_spec_gen, _snippet, _verify,
]


def test_script_dir_matches_paths_source():
    """14 模块 import 后的 SCRIPT_DIR 与事实源 _paths.SCRIPT_DIR 一致。"""
    for mod in CONSOLIDATED:
        assert mod.SCRIPT_DIR == _paths.SCRIPT_DIR, (
            f"{mod.__name__}.SCRIPT_DIR 漂移：{mod.SCRIPT_DIR!r} != "
            f"{_paths.SCRIPT_DIR!r}")


def test_cli_infra_reexport_downstream_intact():
    """_cli_infra 收拢后模块属性仍在：下游 `from _cli_infra import SCRIPT_DIR`
    （_bid_parse/_cli_audit/_cli_audit_p0/_cli_cmds_gen 等）零改动可达。"""
    import _bid_parse
    import _cli_audit
    for mod in (_bid_parse, _cli_audit):
        assert mod.SCRIPT_DIR == _paths.SCRIPT_DIR, mod.__name__


def test_monkeypatch_semantics_doc_extract(tmp_path, monkeypatch):
    """抽样 1（纯函数）：函数体内裸名 SCRIPT_DIR 读模块全局，补丁生效。"""
    monkeypatch.setattr(_doc_extract, "SCRIPT_DIR", str(tmp_path))
    assert _doc_extract._resolve("a.txt") == os.path.join(str(tmp_path), "a.txt")


def test_monkeypatch_semantics_inbox_registry(tmp_path, monkeypatch):
    """抽样 2（落盘可见）：日志写进补丁后的 SCRIPT_DIR 树，而非真实 .folio/。"""
    monkeypatch.setattr(_inbox_registry, "SCRIPT_DIR", str(tmp_path))
    _inbox_registry._log("b4-g5 语义探针")
    log_file = os.path.join(str(tmp_path), ".folio", "logs", "inbox_registry.log")
    with open(log_file, "r", encoding="utf-8") as f:
        assert "b4-g5 语义探针" in f.read()


def test_monkeypatch_semantics_verify(tmp_path, monkeypatch):
    """抽样 3（早期返回路径）：check_bid_risks 用补丁后的 SCRIPT_DIR 找
    bid_criteria.json——补丁树下不存在 → 跳过（True, []），证明查的是补丁路径。"""
    monkeypatch.setattr(_verify, "SCRIPT_DIR", str(tmp_path))
    ok, issues = _verify.check_bid_risks("dummy.docx", client_name="B4探针客户")
    assert ok is True
    assert issues == []
    assert sys.modules["_verify"].SCRIPT_DIR == str(tmp_path)
