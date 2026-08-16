# -*- coding: utf-8 -*-
"""D-118：skip 目录三处一致快照测试。

单一数据源链条：_paths.OUTPUT_SKIP_DIRS（CLI）== .folio/hooks/_output_skip_dirs.json
（hook 读取）== hook 内硬编码 fallback（fail-safe）。任一处漂移本测试挂掉。
"""

import importlib.util
import json
import os
import sys

import _paths

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(SCRIPT_DIR, ".folio", "hooks", "_output_skip_dirs.json")


def _load_hook_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_json_matches_paths_constants():
    with open(JSON_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    assert tuple(cfg["skip_dirs"]) == tuple(_paths.OUTPUT_SKIP_DIRS)
    assert tuple(cfg["intermediate_dirs"]) == tuple(_paths.OUTPUT_INTERMEDIATE_DIRS)
    assert set(_paths.OUTPUT_INTERMEDIATE_DIRS) == \
        set(_paths.OUTPUT_SKIP_DIRS) | {"pages", "media"}


def test_audit_uses_paths_constant():
    src = open(os.path.join(SCRIPT_DIR, "_cli_audit.py"), encoding="utf-8").read()
    assert "from _paths import OUTPUT_SKIP_DIRS" in src
    assert 'SKIP_DIRS = set(OUTPUT_SKIP_DIRS)' in src


def test_path_guard_reads_json():
    mod = _load_hook_module("hook_path_guard_test",
                            os.path.join(SCRIPT_DIR, ".folio", "hooks",
                                         "pretool_path_guard.py"))
    assert set(mod.INTERMEDIATE_DIRS) == set(_paths.OUTPUT_INTERMEDIATE_DIRS)


def test_stop_verify_fallback_matches_json():
    # fallback 硬编码应等于 json skip_dirs（源码级断言，防止 fallback 漂移）
    src = open(os.path.join(SCRIPT_DIR, ".folio", "hooks",
                            "stop_verify.py"), encoding="utf-8").read()
    with open(JSON_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    for d in cfg["skip_dirs"]:
        assert f'"{d}"' in src, f"stop_verify fallback 缺目录 {d}"
