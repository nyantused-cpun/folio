# -*- coding: utf-8 -*-
"""B3 批 A6 组回归测试：
1. P2 deliver --pptd 透传 Step 1（否则 --resume 定位必失败）
2. P2 save 客户名 `--` 注入拦截（--help/-h 不再落进客户名建目录）
3. P2 三处 _run_pre_check 返回 None 阻断（style 守卫不再 fail-open）
4. P2 aliases --global --edit 死分支复活（edit 判定先于 global 列表）
"""
import subprocess
import types

import pytest

import _cli
import _cli_generate
import _cli_cmds_gen
import _cli_cmds_idx
from _aliases import GLOBAL_ALIASES_PATH


# ---------------------------------------------------------------------------
# P2 deliver --pptd 透传
# ---------------------------------------------------------------------------

class TestDeliverPptdPassthrough(object):
    def test_pptd_flag_forwarded_to_step1(self, monkeypatch, capsys):
        calls = []

        def _fake_call(cmd, **kwargs):
            calls.append(cmd)
            return 0
        monkeypatch.setattr(subprocess, "call", _fake_call)
        args = types.SimpleNamespace(
            spec="s.yml", output="o.html", client="", style="", inline_editor=False,
            skip_review=True, review=False, pptd="自定义工程目录", resume=False,
            shots=False)
        _cli_generate.cmd_deliver(args)
        step1 = calls[0]
        assert step1[2] == "html-build"
        assert "--pptd" in step1 and "自定义工程目录" in step1
        assert step1[step1.index("--pptd") + 1] == "自定义工程目录"

    def test_no_pptd_flag_keeps_default(self, monkeypatch):
        calls = []
        monkeypatch.setattr(subprocess, "call",
                            lambda cmd, **k: (calls.append(cmd), 0)[1])
        args = types.SimpleNamespace(
            spec="s.yml", output="o.html", client="", style="", inline_editor=False,
            skip_review=True, review=False, pptd=None, resume=False, shots=False)
        _cli_generate.cmd_deliver(args)
        assert "--pptd" not in calls[0]


# ---------------------------------------------------------------------------
# P2 save 客户名 -- 注入拦截
# ---------------------------------------------------------------------------

class _StubExit(Exception):
    def __init__(self, code=0):
        super().__init__(code)
        self.code = code


class _ExitStub(object):
    def __call__(self, code=0):
        raise _StubExit(code)


class TestSaveDashInjection(object):
    def _run_main(self, monkeypatch, argv_tail):
        dispatched = []
        monkeypatch.setattr(_cli, "cmd_save", lambda args: dispatched.append(args))
        monkeypatch.setattr("sys.argv", ["_cli.py", "save"] + argv_tail)
        code = None
        try:
            _cli.main()
        except SystemExit as e:  # 拦截路径 exit 1；正常路径 main 走完返回 None
            code = e.code
        return code, dispatched

    def test_save_dashdash_help_rejected(self, monkeypatch, capsys):
        code, _ = self._run_main(monkeypatch, ["--help"])
        assert code == 1
        assert "不合法" in capsys.readouterr().out

    def test_save_dash_h_rejected(self, monkeypatch):
        code, _ = self._run_main(monkeypatch, ["-h"])
        assert code == 1

    def test_normal_client_still_dispatched(self, monkeypatch):
        """正常客户名不受拦截影响（守卫不误伤）。"""
        code, dispatched = self._run_main(monkeypatch, ["正常客户"])
        assert code is None  # main 正常走完（patched cmd_save 直接返回）
        assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# P2 _run_pre_check None 阻断（三处）
# ---------------------------------------------------------------------------

class TestPreCheckNoneBlocking(object):
    def test_spec_gen_blocks_on_none(self, monkeypatch):
        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda **k: None)
        stub = _ExitStub()
        monkeypatch.setattr(_cli_generate.sys, "exit", stub)
        with pytest.raises(_StubExit) as ei:
            _cli_generate.cmd_spec_gen(types.SimpleNamespace(client=None))
        assert ei.value.code == 1

    def test_outline_to_spec_blocks_on_none(self, monkeypatch):
        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda **k: None)
        monkeypatch.setattr(_cli_generate.sys, "exit", _ExitStub())
        with pytest.raises(_StubExit) as ei:
            _cli_generate.cmd_outline_to_spec(types.SimpleNamespace(client=None))
        assert ei.value.code == 1

    def test_quote_spec_gen_blocks_on_none(self, monkeypatch):
        monkeypatch.setattr(_cli_cmds_gen, "_run_pre_check", lambda **k: None)
        monkeypatch.setattr(_cli_cmds_gen.sys, "exit", _ExitStub())
        with pytest.raises(_StubExit) as ei:
            _cli_cmds_gen.cmd_quote_spec_gen(types.SimpleNamespace(client=None))
        assert ei.value.code == 1


# ---------------------------------------------------------------------------
# P2 aliases --global --edit 死分支
# ---------------------------------------------------------------------------

class TestAliasesGlobalEdit(object):
    def test_global_edit_reaches_open_file(self, monkeypatch, capsys):
        opened = []
        monkeypatch.setattr(_cli_cmds_idx, "_open_file",
                            lambda p: opened.append(p))
        args = types.SimpleNamespace(global_only=True, edit=True, client=None,
                                     diff=None)
        _cli_cmds_idx.cmd_aliases(args)
        assert opened == [GLOBAL_ALIASES_PATH]
        # 不再被 global 列表分支截胡（列表不应打印）
        assert "=== 全局别名 ===" not in capsys.readouterr().out

    def test_client_edit_creates_template_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_cli_cmds_idx, "SCRIPT_DIR", str(tmp_path))
        opened = []
        monkeypatch.setattr(_cli_cmds_idx, "_open_file", lambda p: opened.append(p))
        args = types.SimpleNamespace(global_only=False, edit=True, client="某客户",
                                     diff=None)
        _cli_cmds_idx.cmd_aliases(args)
        expected = tmp_path / "_knowledge" / "clients" / "某客户" / "aliases.yml"
        assert expected.exists() and "标准词" in expected.read_text(encoding="utf-8")
        assert opened == [str(expected)]

    def test_client_edit_requires_client(self, monkeypatch, capsys):
        monkeypatch.setattr(_cli_cmds_idx, "_open_file",
                            lambda p: pytest.fail("缺客户名不应打开文件"))
        args = types.SimpleNamespace(global_only=False, edit=True, client=None,
                                     diff=None)
        with pytest.raises(SystemExit):
            _cli_cmds_idx.cmd_aliases(args)
