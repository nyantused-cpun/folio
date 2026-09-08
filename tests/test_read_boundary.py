# -*- coding: utf-8 -*-
"""B2 回归：读边界白名单（P2-4/D3）+ realpath 加固（P2-8）+ --out 写白名单（P2-3）。

D3 拍板：读边界 = 工作区白名单 + `--allow-outside` 显式旗标；
守卫单点 `_paths._validate_read_path`，命令入口统一接 `_cli_infra._guard_read_path`。
"""
import os
import subprocess
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _paths import ReadPathNotAllowedError, _validate_read_path  # noqa: E402


def _run_main(argv, monkeypatch):
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


class TestValidateReadPath:
    """守卫单点行为。"""

    def test_workspace_path_passes(self):
        out = _validate_read_path(os.path.join(SCRIPT_DIR, "_context.py"))
        assert os.path.isabs(out)

    def test_outside_rejected(self):
        with pytest.raises(ReadPathNotAllowedError):
            _validate_read_path("C:/Windows/win.ini")

    def test_allow_outside_explicit(self):
        out = _validate_read_path("C:/Windows/win.ini", allow_outside=True)
        assert os.path.isabs(out)

    def test_sibling_prefix_dir_rejected(self):
        # 工作区兄弟目录（前缀相似）不算工作区内
        sibling = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "knowledge base_evil", "x.txt"))
        with pytest.raises(ReadPathNotAllowedError):
            _validate_read_path(sibling)

    def test_empty_rejected(self):
        with pytest.raises(ReadPathNotAllowedError):
            _validate_read_path("")


class TestReadCommandsGuarded:
    """命令入口接线：仓外默认拒 exit 1，发生在任何读取/缓存写入之前。"""

    def test_read_outside_exit_1(self, monkeypatch, capsys):
        code = _run_main(["_cli.py", "read", "C:/Windows/win.ini"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_chunk_read_outside_exit_1(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "chunk-read", "C:/Windows/win.ini#p0"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_doc_extract_outside_exit_1(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "doc-extract", "C:/Windows/win.ini"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_vision_outside_exit_1(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "vision-describe", "C:/Windows/win.ini"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_bid_parse_outside_exit_1(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "bid-parse", "C:/Windows/win.ini"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_extract_md_outside_doc_exit_1(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "extract-md", "--out", "output/通用/_t.md",
             "C:/Windows/win.ini"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_extract_md_out_outside_output_blocked(self, monkeypatch, capsys):
        """--out 写白名单（P2-3）：output/ 外拒绝。"""
        code = _run_main(
            ["_cli.py", "extract-md", "--out", "C:/evil/out.md"], monkeypatch)
        assert code == 1

    def test_pdf_pages_out_outside_output_blocked(self, monkeypatch, capsys):
        code = _run_main(
            ["_cli.py", "pdf-pages", "x.pdf", "--out", "C:/evil/pages"], monkeypatch)
        assert code == 1


class TestRealpathHardening:
    """P2-8：junction/symlink 指 workspace 外，读/写白名单均拒绝。"""

    def _make_junction(self, link, target):
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                           capture_output=True, text=True)
        return r.returncode == 0

    def test_read_through_junction_rejected(self, tmp_path):
        outside = os.path.expanduser("~")  # 仓外真实目录（用户主目录）
        assert not os.path.abspath(outside).startswith(os.path.abspath(SCRIPT_DIR))
        link = os.path.join(SCRIPT_DIR, "output", "通用", "_junc_b2_test")
        if os.path.exists(link):
            os.rmdir(link)
        try:
            if not self._make_junction(link, outside):
                pytest.skip("无权限创建 junction")
            probe = os.path.join(link, "secret.txt")
            with pytest.raises(ReadPathNotAllowedError):
                _validate_read_path(probe)
        finally:
            if os.path.exists(link):
                os.rmdir(link)

    def test_write_through_junction_rejected(self, tmp_path):
        from _renderer import OutputPathNotAllowedError, _validate_output_path
        outside = os.path.expanduser("~")
        link = os.path.join(SCRIPT_DIR, "output", "通用", "_junc_b2_test")
        if os.path.exists(link):
            os.rmdir(link)
        try:
            if not self._make_junction(link, outside):
                pytest.skip("无权限创建 junction")
            with pytest.raises(OutputPathNotAllowedError):
                _validate_output_path(os.path.join(link, "out.txt"))
        finally:
            if os.path.exists(link):
                os.rmdir(link)


class TestClientNameHardening:
    """P2-2/P2-1：client 名拦盘符与 Windows 设备名；bid-save 接校验。"""

    def test_drive_relative_name_rejected(self):
        import _paths
        with pytest.raises(ValueError):
            _paths._validate_client_name("C:evil")

    def test_device_names_rejected(self):
        import _paths
        for name in ("CON", "NUL", "COM1", "LPT2", "con.txt", "nul.txt"):
            with pytest.raises(ValueError):
                _paths._validate_client_name(name)

    def test_normal_names_still_pass(self):
        import _paths
        _paths._validate_client_name("蓝海")
        _paths._validate_client_name("示例集团")
        _paths._validate_client_name("蓝海集团")  # 含设备名前缀的合法名不误伤

    def test_save_bid_criteria_bad_client_rejected(self, tmp_path):
        from _bid_parse import save_bid_criteria
        with pytest.raises(ValueError):
            save_bid_criteria({"scoring": []}, client_name="../../evil")
