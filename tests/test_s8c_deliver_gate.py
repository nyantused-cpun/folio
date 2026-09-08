# -*- coding: utf-8 -*-
"""S8-C deliver 门全视口接线测试（density_gate 穿透链）。

既定口径：密度检查多视口（gate="deliver"，全视口 + 截图存档）仅 deliver 交付门
使用；日常验证链（verify 命令 / 独立 html-build / run_single 缺省）保持单视口
gate="verify"。

覆盖面：
- verify_html / run_single 缺省 gate == "verify"，显式 density_gate="deliver" 透传
- cmd_deliver Step1（subprocess 调 _cli.py html-build）必须携带 --density-gate deliver
- 独立 html-build 的 argparse 缺省仍为 verify（现状行为不变）

说明：cmd_deliver 经 subprocess 外部进程走 html-build（非进程内共用
cmd_html_build），deliver 链的行为测试落在「Step1 命令行组装」粒度
（monkeypatch subprocess.call 捕获 argv，不真跑渲染管线）。
cmd_html_build -> run_single 的透传为单 kwarg 接线点，全链路
（pre_check / confirm sidecar / Renderer 渲染）超出单测粒度，用源码断言
钉住 getattr(args, "density_gate", "verify") 透传不回退。
"""
import argparse
import inspect
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

import _cli_generate
import _verify
import _verify_hook

_HTML = (
    '<!DOCTYPE html><html><head>'
    '<style>body{color:#333}.card{padding:8px}</style></head>'
    '<body><section><div class="card">' + '密度门档接线测试内容。' * 60 +
    '</div></section></body></html>'
)


@pytest.fixture
def html_file(tmp_path):
    p = tmp_path / "方案_v1.html"
    p.write_text(_HTML, encoding="utf-8")
    return str(p)


@pytest.fixture
def gate_capture(monkeypatch):
    """捕获 check_density_html 收到的 gate 实参（不真跑 playwright）。"""
    captured = {}

    def fake_check(html_path, gate="verify"):
        captured["gate"] = gate
        return []

    monkeypatch.setattr("_density.check_density_html", fake_check)
    return captured


class TestVerifyHtmlGate:
    """verify_html 缺省 verify / 显式 deliver 透传到 check_density_html。"""

    def test_default_gate_is_verify(self, html_file, gate_capture):
        ok, _msg = _verify.verify_html(html_file)
        assert ok is True
        assert gate_capture["gate"] == "verify"

    def test_deliver_gate_passthrough(self, html_file, gate_capture):
        ok, _msg = _verify.verify_html(html_file, density_gate="deliver")
        assert ok is True
        assert gate_capture["gate"] == "deliver"


class TestRunSingleGate:
    """run_single 缺省 verify / 显式 deliver 经 auto_verify -> verify_html 透传。"""

    @pytest.fixture
    def hook_quiet(self, monkeypatch):
        """隔离 run_single 钩子副作用（conftest 守卫真实 .folio/logs 与片段库）。"""
        monkeypatch.setattr(_verify_hook, "write_log", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "update_task_history", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_auto_snippet_capture", lambda *a, **k: None)

    def test_default_gate_is_verify(self, html_file, gate_capture, hook_quiet):
        assert _verify_hook.run_single(html_file) is True
        assert gate_capture["gate"] == "verify"

    def test_deliver_gate_passthrough(self, html_file, gate_capture, hook_quiet):
        assert _verify_hook.run_single(html_file, density_gate="deliver") is True
        assert gate_capture["gate"] == "deliver"


class TestDeliverChainGate:
    """deliver 链：Step1 html-build 子进程命令必须携带 --density-gate deliver。"""

    def test_deliver_step1_carries_deliver_gate(self, monkeypatch, tmp_path):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        calls = []
        import subprocess
        monkeypatch.setattr(subprocess, "call",
                            lambda cmd, *a, **k: calls.append(cmd) or 0)
        args = argparse.Namespace(
            spec=str(tmp_path / "方案_spec.yml"),
            output=str(tmp_path / "方案_v1.html"),
            client="测试客户", style="", pptd=None, inline_editor=False,
            skip_review=False, review=False, resume=False, shots=False)
        _cli_generate.cmd_deliver(args)
        step1 = calls[0]
        assert "html-build" in step1
        i = step1.index("--density-gate")
        assert step1[i + 1] == "deliver"


class TestStandaloneUnchanged:
    """独立 html-build / verify 命令现状行为不变（缺省恒 verify）。"""

    def test_html_build_argparse_default_verify(self):
        import _cli
        ns = _cli.build_parser().parse_args(["html-build", "s.yml", "o.html"])
        assert ns.density_gate == "verify"

    def test_html_build_argparse_accepts_deliver(self):
        import _cli
        ns = _cli.build_parser().parse_args(
            ["html-build", "s.yml", "o.html", "--density-gate", "deliver"])
        assert ns.density_gate == "deliver"

    def test_cmd_html_build_forwards_gate(self):
        # cmd_html_build 全链路（pre_check/confirm sidecar/Renderer）超出单测粒度，
        # 单 kwarg 透传接线点用源码断言钉住，防回归退回无参调用（见模块 docstring）。
        src = inspect.getsource(_cli_generate.cmd_html_build)
        assert 'density_gate=getattr(args, "density_gate", "verify")' in src

    def test_run_single_default_value_pinned(self):
        # verify 命令（_cli_cmds_qa 走 run_single(args.file)）不带 density_gate，
        # 靠缺省值保持现状——钉住缺省恒 "verify"。
        sig = inspect.signature(_verify_hook.run_single)
        assert sig.parameters["density_gate"].default == "verify"
