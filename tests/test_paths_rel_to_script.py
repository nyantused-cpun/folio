# -*- coding: utf-8 -*-
"""跨盘符路径回归（2026-09-08 CI 实证）。

GitHub Windows runner 工作区在 D:、TEMP 在 C:，对 tmp_path 产物做
``os.path.relpath(fpath, SCRIPT_DIR)`` 会抛 ``ValueError: path is on mount
'C:', start on mount 'D:'``——save / audit / breeding / theme 四处链断，CI 12 红。
``_paths.rel_to_script`` 统一回退绝对路径修复。
"""
import os

import pytest

import _paths


def test_rel_to_script_same_root_returns_relative():
    p = os.path.join(_paths.SCRIPT_DIR, "output", "x.html")
    assert _paths.rel_to_script(p) == os.path.join("output", "x.html")


@pytest.mark.skipif(os.name != "nt", reason="跨盘符语义仅 Windows")
def test_rel_to_script_cross_drive_falls_back_to_abs(monkeypatch):
    monkeypatch.setattr(_paths, "SCRIPT_DIR", r"D:\proj")
    assert _paths.rel_to_script(r"C:\tmp\a.html") == os.path.abspath(r"C:\tmp\a.html")


@pytest.mark.skipif(os.name != "nt", reason="跨盘符语义仅 Windows")
def test_scan_observation_ttl_cross_drive_does_not_raise(tmp_path, monkeypatch):
    """端到端：产物在别的盘符时 breeding 扫描不再抛 ValueError。"""
    import _breeding
    f = tmp_path / "x.py"
    f.write_text("# 观察项：待升级\n", encoding="utf-8")
    monkeypatch.setattr(_paths, "SCRIPT_DIR", r"D:\proj")
    assert isinstance(_breeding.scan_observation_ttl([str(f)]), list)
