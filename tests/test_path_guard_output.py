# -*- coding: utf-8 -*-
"""pretool_path_guard output/** 细分（2026-08-11）的回归测试。

- 最终交付物（.html/.pptx/.docx/.xlsx）-> deny（须走 CLI 生成）
- 中间工程产物（pages/、_assets/、figures/、debug/、spec.yml、.page）-> allow
"""
import importlib.util
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

HOOKS_DIR = os.path.join(SCRIPT_DIR, ".folio", "hooks")


_HOOK_MODS = {}


def _load_hook(name):
    """按路径加载 hook 脚本（hooks 不在 sys.path）。

    模块级缓存：同一路径只 exec 一次，保证 fixture 与 test 引用同一实例。
    """
    if name not in _HOOK_MODS:
        spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS_DIR, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HOOK_MODS[name] = mod
    return _HOOK_MODS[name]


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    g = _load_hook("pretool_path_guard")
    proj = tmp_path / "root"
    proj.mkdir(exist_ok=True)
    monkeypatch.setenv("TRAE_PROJECT_DIR", str(proj))
    return g


def _check(guard, rel):
    """以项目根为基准检查相对路径（output/...）。"""
    path = os.path.join(os.environ["TRAE_PROJECT_DIR"], rel)
    return guard._check_path(path, "Write", {})


class TestOutputDeliverableDenied:
    def test_top_level_html_denied(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/方案_v1.html")
        assert decision == "deny"

    def test_nested_pptx_denied(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/方案_v1/方案_v1.pptx")
        assert decision == "deny"

    def test_top_level_xlsx_denied(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/需求清单_v1.xlsx")
        assert decision == "deny"


class TestOutputIntermediateAllowed:
    def test_page_intermediate_allowed(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/方案_v14/pages/06_process.page")
        assert decision == "allow"

    def test_spec_yml_allowed(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/蓝海集团_方案_spec.yml")
        assert decision == "allow"

    def test_figures_dir_allowed(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/figures/01_流程.html")
        assert decision == "allow"

    def test_assets_dir_allowed(self, guard):
        decision, _ = _check(guard, "output/蓝海集团/方案_v1/_assets/editor.js")
        assert decision == "allow"
