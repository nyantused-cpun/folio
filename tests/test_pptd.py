# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""pptd-build 命令与 _pptd 模块测试（C-2 重构后）。

全部 mock：不触真实 PPT 转换、不调 PowerPoint COM、不写真实 output/。
覆盖：backend 选择、本地结构校验、命令错误路径退出码、happy path 调用链、
截图导出（含中文路径 ASCII 临时目录回收）。
"""

import os
import subprocess
import sys

import pytest


def _run_main(argv, monkeypatch):
    """以给定 argv 调用 _cli.main()，断言其抛出 SystemExit 并返回退出码。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        with pytest.raises(SystemExit) as exc_info:
            _cli.main()
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved
    return exc_info.value.code


def _run_main_allow_success(argv, monkeypatch):
    """同 _run_main，但允许成功路径（无 SystemExit 时返回 None）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


# ---------------------------------------------------------------------------
# backend 选择（PPTD_BACKEND 环境变量）
# ---------------------------------------------------------------------------
class TestBackend:
    def test_default_python_pptx(self, monkeypatch):
        import _pptd
        monkeypatch.delenv("PPTD_BACKEND", raising=False)
        assert isinstance(_pptd.get_backend(), _pptd.PythonPptxBackend)

    def test_env_python_pptx(self, monkeypatch):
        import _pptd
        monkeypatch.setenv("PPTD_BACKEND", "python_pptx")
        assert isinstance(_pptd.get_backend(), _pptd.PythonPptxBackend)

    def test_env_unknown_returns_none(self, monkeypatch, capsys):
        import _pptd
        monkeypatch.setenv("PPTD_BACKEND", "kimi_slides")
        assert _pptd.get_backend() is None
        assert "未知 PPTD_BACKEND" in capsys.readouterr().out

    def test_pptd_check_warn_types_unchanged(self):
        import _pptd
        assert _pptd.PPTD_WARN_TYPES == (
            "TextOverflow", "TextOcclusion", "TextDrift",
            "TextUnderfill", "BoundsOutside")


# ---------------------------------------------------------------------------
# 本地结构校验（PythonPptxBackend.check -> _pptd_convert.check_pptd）
# ---------------------------------------------------------------------------
def _write_deck(tmp_path, main_text, pages=None):
    """写最小 pptd 工程：主文件 + 可选 pages/ 文件，返回主文件绝对路径。"""
    root = tmp_path / "deck_proj"
    (root / "pages").mkdir(parents=True, exist_ok=True)
    main = root / "deck.pptd"
    main.write_text(main_text, encoding="utf-8")
    for name, text in (pages or {}).items():
        (root / "pages" / name).write_text(text, encoding="utf-8")
    return str(main)


_OK_MAIN = "size: [1280, 720]\npages:\n- pages/01.page\n"
_OK_PAGE = (
    "elements:\n"
    "- elementId: s1\n"
    "  elementType: shape\n"
    "  bounds: [100, 100, 200, 50]\n"
    "  shapeName: rect\n")


class TestBackendCheck:
    def test_ok_deck_pass(self, tmp_path):
        import _pptd
        main = _write_deck(tmp_path, _OK_MAIN, {"01.page": _OK_PAGE})
        ok, warn = _pptd.PythonPptxBackend().check(main)
        assert ok is True
        assert warn == {}

    def test_missing_pages_field_fail(self, tmp_path, capsys):
        import _pptd
        main = _write_deck(tmp_path, "size: [1280, 720]\n")
        assert _pptd.PythonPptxBackend().check(main)[0] is False
        assert "缺少必填字段" in capsys.readouterr().out

    def test_page_file_missing_fail(self, tmp_path, capsys):
        import _pptd
        main = _write_deck(tmp_path, _OK_MAIN)  # pages 引用无对应文件
        assert _pptd.PythonPptxBackend().check(main)[0] is False
        assert "页面文件不存在" in capsys.readouterr().out

    def test_duplicate_element_id_fail(self, tmp_path, capsys):
        import _pptd
        page = (
            "elements:\n"
            "- elementId: a\n  elementType: text\n  bounds: [0, 0, 10, 10]\n"
            "  content: {text: x}\n"
            "- elementId: a\n  elementType: text\n  bounds: [0, 20, 10, 10]\n"
            "  content: {text: y}\n")
        main = _write_deck(tmp_path, _OK_MAIN, {"01.page": page})
        assert _pptd.PythonPptxBackend().check(main)[0] is False
        assert "elementId 重复" in capsys.readouterr().out

    def test_unknown_element_type_fail(self, tmp_path, capsys):
        import _pptd
        page = ("elements:\n"
                "- elementId: a\n  elementType: chart\n  bounds: [0, 0, 10, 10]\n")
        main = _write_deck(tmp_path, _OK_MAIN, {"01.page": page})
        assert _pptd.PythonPptxBackend().check(main)[0] is False
        assert "未知 elementType" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# COM 截图（保留原行为）
# ---------------------------------------------------------------------------
class TestExportShots:
    def test_no_pwsh_returns_false(self, monkeypatch, tmp_path, capsys):
        import _pptd
        monkeypatch.setattr(_pptd, "find_pwsh", lambda: None)
        pptx = tmp_path / "中文名.pptx"
        pptx.write_bytes(b"x")
        assert _pptd.export_shots(str(pptx), str(tmp_path / "out")) is False
        assert "未找到" in capsys.readouterr().out

    def test_export_moves_pngs_and_cleans_tmp(self, monkeypatch, tmp_path):
        import _pptd
        monkeypatch.setattr(_pptd, "find_pwsh", lambda: "/fake/pwsh")
        pptx = tmp_path / "中文名.pptx"
        pptx.write_bytes(b"x")
        out_dir = tmp_path / "shots"

        def _fake_run(cmd, **k):
            out = cmd[cmd.index("-OutDir") + 1]
            os.makedirs(out, exist_ok=True)
            for i in (1, 2):
                with open(os.path.join(out, f"slide_{i:02d}.png"), "wb") as f:
                    f.write(b"png")
            return subprocess.CompletedProcess(cmd, 0, stdout="Exported 2 slides")
        monkeypatch.setattr(subprocess, "run", _fake_run)

        assert _pptd.export_shots(str(pptx), str(out_dir)) is True
        assert sorted(os.listdir(out_dir)) == ["slide_01.png", "slide_02.png"]

    def test_export_com_failure_returns_false(self, monkeypatch, tmp_path, capsys):
        import _pptd
        monkeypatch.setattr(_pptd, "find_pwsh", lambda: "/fake/pwsh")
        pptx = tmp_path / "a.pptx"
        pptx.write_bytes(b"x")
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **k: subprocess.CompletedProcess(cmd, 1))
        assert _pptd.export_shots(str(pptx), str(tmp_path / "out")) is False
        assert "导出失败" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 命令层：错误路径 exit 1，happy path 调全 check/convert/verify 链
# ---------------------------------------------------------------------------
class _FakeBackend:
    """替身 backend：记录调用次数，可配置 check/convert 结果。"""

    def __init__(self, check_ok=True, convert_ok=True, calls=None):
        self._check_ok = check_ok
        self._convert_ok = convert_ok
        self.calls = calls or {"check": 0, "convert": 0, "shots": 0}

    def check(self, path):
        self.calls["check"] += 1
        return self._check_ok, {}

    def convert(self, path, out):
        self.calls["convert"] += 1
        if self._convert_ok:
            with open(out, "wb") as f:
                f.write(b"pptx")
        return self._convert_ok


class TestCmdPptdBuild:
    def _mock_pipeline(self, monkeypatch, check_ok=True, convert_ok=True):
        import _pptd
        calls = {"check": 0, "convert": 0, "shots": 0}
        backend = _FakeBackend(check_ok, convert_ok, calls)
        monkeypatch.setattr(_pptd, "get_backend", lambda: backend)
        monkeypatch.setattr(_pptd, "get_backend_or_exit", lambda: backend)
        monkeypatch.setattr(_pptd, "write_check_report", lambda *a, **k: None)
        import _verify
        monkeypatch.setattr(_verify, "verify_pptd_deck",
                            lambda *a, **k: (True, [], []))
        monkeypatch.setattr(_pptd, "export_shots",
                            lambda pptx, out_dir: (calls.__setitem__("shots", calls["shots"] + 1) or True))
        import _cli_generate
        monkeypatch.setattr(_cli_generate, "backup_before_generate",
                            lambda *a, **k: None)
        import _verify_hook
        monkeypatch.setattr(_verify_hook, "run_single",
                            lambda *a, **k: True)
        return calls

    def test_missing_input_exits_1(self, monkeypatch):
        code = _run_main(
            ["_cli.py", "pptd-build", "不存在的.pptd"], monkeypatch)
        assert code == 1

    def test_default_output_outside_whitelist_blocked(self, monkeypatch, tmp_path):
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        code = _run_main(["_cli.py", "pptd-build", str(pptd)], monkeypatch)
        assert code == 1

    def test_unknown_backend_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PPTD_BACKEND", "kimi_slides")
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        code = _run_main(["_cli.py", "pptd-build", str(pptd),
                          "-o", "output/通用/x.pptx"], monkeypatch)
        assert code == 1

    def test_missing_pptx_dep_exits_1(self, monkeypatch, tmp_path):
        import _pptd
        monkeypatch.setattr(_pptd, "get_backend", lambda: _pptd.PythonPptxBackend())
        real_import = __import__

        def _fake_import(name, *a, **k):
            if name == "pptx":
                raise ImportError("no pptx")
            return real_import(name, *a, **k)
        monkeypatch.setattr("builtins.__import__", _fake_import)
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        code = _run_main(["_cli.py", "pptd-build", str(pptd),
                          "-o", "output/通用/x.pptx"], monkeypatch)
        assert code == 1

    def test_check_failure_blocks_convert(self, monkeypatch, tmp_path):
        calls = self._mock_pipeline(monkeypatch, check_ok=False)
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        code = _run_main(["_cli.py", "pptd-build", str(pptd),
                          "-o", "output/通用/x.pptx"], monkeypatch)
        assert code == 1
        assert calls["check"] == 1
        assert calls["convert"] == 0

    def test_check_only_skips_convert(self, monkeypatch, tmp_path):
        calls = self._mock_pipeline(monkeypatch)
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        code = _run_main_allow_success(
            ["_cli.py", "pptd-build", str(pptd), "-o", "output/通用/x.pptx",
             "--check-only"], monkeypatch)
        assert code in (None, 0)
        assert calls["check"] == 1
        assert calls["convert"] == 0

    def test_layout_lint_error_blocks_convert(self, monkeypatch, tmp_path):
        """§七 2.8：pptd check 通过后版式 lint error 阻断（不 convert）。"""
        calls = self._mock_pipeline(monkeypatch)
        root = tmp_path / "deck_proj"
        (root / "pages").mkdir(parents=True)
        (root / "deck.pptd").write_text(
            "size: [1280, 720]\npages:\n- pages/01.page\n", encoding="utf-8")
        (root / "pages" / "01.page").write_text(
            "elements:\n"
            "- elementId: s1\n"
            "  elementType: shape\n"
            "  bounds: [1200, 100, 200, 50]\n", encoding="utf-8")
        code = _run_main(
            ["_cli.py", "pptd-build", str(root / "deck.pptd"),
             "-o", "output/通用/x.pptx"], monkeypatch)
        assert code == 1
        assert calls["check"] == 1
        assert calls["convert"] == 0

    def test_happy_path_with_shots(self, monkeypatch, tmp_path):
        calls = self._mock_pipeline(monkeypatch)
        pptd = tmp_path / "deck.pptd"
        pptd.write_text("x", encoding="utf-8")
        out = "output/通用/x.pptx"
        try:
            code = _run_main_allow_success(
                ["_cli.py", "pptd-build", str(pptd), "-o", out,
                 "--shots"], monkeypatch)
            assert code in (None, 0)
            assert calls["check"] == 1
            assert calls["convert"] == 1
            assert calls["shots"] == 1
        finally:
            if os.path.exists(out):
                os.remove(out)

    def test_pptx_input_without_shots_exits_1(self, monkeypatch, tmp_path):
        pptx = tmp_path / "deck.pptx"
        pptx.write_bytes(b"x")
        code = _run_main(["_cli.py", "pptd-build", str(pptx)], monkeypatch)
        assert code == 1

    def test_pptx_input_shots_only(self, monkeypatch, tmp_path):
        calls = self._mock_pipeline(monkeypatch)
        pptx = tmp_path / "deck.pptx"
        pptx.write_bytes(b"x")
        code = _run_main_allow_success(
            ["_cli.py", "pptd-build", str(pptx), "--shots"], monkeypatch)
        assert code in (None, 0)
        assert calls["check"] == 0
        assert calls["convert"] == 0
        assert calls["shots"] == 1
