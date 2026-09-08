# -*- coding: utf-8 -*-
"""_cli_generate 回归测试。

1. deliver venv 解释器路径（B5#B1，2026-09-06）：原实现 dirname(dirname(__file__))
   多算一层指向仓库外层，恒不存在静默降级 sys.executable；修复后单层 dirname
   指向仓库内 .venv。
2. P3 清扫（2026-09-06）：pptd-gen 项目名 slugify 空值兜底 + deliver --resume
   按 mtime 取最新 .pptd。
"""
import os
import re
import subprocess
import types

import pytest

import _cli_generate


def test_repo_venv_python_points_inside_repo():
    p = _cli_generate._repo_venv_python()
    module_dir = os.path.dirname(os.path.abspath(_cli_generate.__file__))
    # 单层 dirname：路径必须落在仓库根的 .venv 内，而非仓库外层（旧 bug 多算一层）
    assert os.path.dirname(p) == os.path.join(module_dir, ".venv", "Scripts")
    assert p.endswith(os.path.join(".venv", "Scripts", "python.exe"))


# ---------------------------------------------------------------------------
# P3：pptd-gen 项目名 slugify 空值兜底（对照 html-build 的 or "deck"）
# ---------------------------------------------------------------------------

class _StopRun(Exception):
    """在 build_deck 处截停 cmd_pptd_gen，只为捕获项目名。"""


class TestPptdGenNameFallback(object):
    def _run(self, monkeypatch, tmp_path, raw_name):
        import _cli_guards
        import _pptd_gen
        import _renderer

        spec_path = tmp_path / "spec.yml"
        spec_path.write_text("document:\n  title: 占位标题\n", encoding="utf-8")

        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda client_name=None: {"ok": True})
        monkeypatch.setattr(_cli_guards, "require_confirmed",
                            lambda spec, context="", spec_path=None: None)
        monkeypatch.setattr(_renderer, "_validate_output_path", lambda p: None)

        # 无内部兜底的 slugify 存根：模拟"清洗结果为空"的回归场景
        # （现役 _slugify_name 自带 deck 兜底，此处解除兜底以钉死调用侧契约）
        def _slug_no_fallback(name):
            if not name:
                return ""
            cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", str(name), flags=re.UNICODE)
            return cleaned.strip("_")

        monkeypatch.setattr(_pptd_gen, "_slugify_name", _slug_no_fallback)

        captured = {}

        def _fake_build(spec, sp, style, name, out_dir, **kw):
            captured["name"] = name
            raise _StopRun()

        monkeypatch.setattr(_pptd_gen, "build_deck", _fake_build)

        args = types.SimpleNamespace(
            spec=str(spec_path), name=raw_name, output=str(tmp_path / "out"),
            style="", logo=None, client="")
        with pytest.raises(_StopRun):
            _cli_generate.cmd_pptd_gen(args)
        return captured.get("name")

    def test_name_all_symbols_falls_back_to_deck(self, monkeypatch, tmp_path):
        # --name 全为符号：清洗结果为空时必须兜底 "deck"（旧代码最终名可为空串）
        assert self._run(monkeypatch, tmp_path, "!!!") == "deck"

    def test_name_normal_slug_untouched(self, monkeypatch, tmp_path):
        assert self._run(monkeypatch, tmp_path, "方案v1") == "方案v1"


# ---------------------------------------------------------------------------
# P3：deliver --resume 按 mtime 取最新 .pptd（旧实现取 listdir 第一个，顺序任意）
# ---------------------------------------------------------------------------

class TestDeliverResumeLatestPptd(object):
    def _run(self, monkeypatch, tmp_path, files):
        base = tmp_path / "方案_v1"
        base.mkdir()
        for fname, mtime in files.items():
            f = base / fname
            f.write_text("pptd", encoding="utf-8")
            os.utime(f, (mtime, mtime))

        calls = []
        monkeypatch.setattr(subprocess, "call", lambda cmd, **k: calls.append(cmd) or 0)
        monkeypatch.setattr(_cli_generate, "_advance_state", lambda *a, **k: None)
        monkeypatch.setattr(_cli_generate, "_budget_soft_warning", lambda: None)

        args = types.SimpleNamespace(
            spec="spec.yml", output=str(tmp_path / "方案_v1.html"), client="",
            style="", inline_editor=False, skip_review=False, review=False,
            pptd=None, resume=True, shots=False)
        _cli_generate.cmd_deliver(args)
        return calls

    def test_resume_picks_latest_mtime_pptd(self, monkeypatch, tmp_path):
        # aaa 字母序在前但修改时间更旧：旧实现按 listdir 顺序会拿错
        calls = self._run(monkeypatch, tmp_path,
                          {"aaa.pptd": 1000000000, "zzz.pptd": 2000000000})
        assert calls and calls[0][2] == "pptd-build"
        assert calls[0][3] == str(tmp_path / "方案_v1" / "zzz.pptd")


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
