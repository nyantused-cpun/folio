# -*- coding: utf-8 -*-
"""B3 批 A9 组回归测试：
1. P2 layout_lint 主文件匹配（_check_ 副本不再劫持，只剩副本体面跳过）
2. P2 export_shots 超时体面退出 + 杀进程树（含孙进程 POWERPNT）
3. P2 COM finally 统一走 _close_word（Close 抛异常仍 Quit，进程不残留）
"""
import os
import subprocess
import types

import pytest

import _layout_lint
import _pptd
from _renderer import docx_com_postprocess as com_pp


# ---------------------------------------------------------------------------
# P2 layout_lint 主文件匹配
# ---------------------------------------------------------------------------

class TestPickMainPptd(object):
    def test_check_copy_not_picked(self, tmp_path):
        """`_check_` 副本排序在 CJK 主文件前，不得劫持。"""
        (tmp_path / "_check_批次.pptd").write_text("copy", encoding="utf-8")
        (tmp_path / "某客户方案.pptd").write_text("main", encoding="utf-8")
        picked = _layout_lint._pick_main_pptd(str(tmp_path))
        assert os.path.basename(picked) == "某客户方案.pptd"

    def test_only_copies_returns_none(self, tmp_path):
        (tmp_path / "_check_批次.pptd").write_text("copy", encoding="utf-8")
        assert _layout_lint._pick_main_pptd(str(tmp_path)) is None

    def test_lint_dir_only_copies_skips(self, tmp_path):
        """目录只剩 _check_ 副本：lint 体面返回空，不误检副本。"""
        (tmp_path / "_check_批次.pptd").write_text("pages: []\n", encoding="utf-8")
        assert _layout_lint.lint_pptd_dir(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# P2 export_shots 超时处理
# ---------------------------------------------------------------------------

class _TimeoutPopen(object):
    """第一次 communicate 抛 TimeoutExpired，之后正常返回（模拟收割）。"""

    def __init__(self, cmd, **kwargs):
        self.pid = 4321
        self.returncode = 0
        self._raised = False

    def communicate(self, timeout=None):
        if not self._raised:
            self._raised = True
            raise subprocess.TimeoutExpired(cmd="pwsh", timeout=timeout or 300)
        return "", None


class _NormalPopen(_TimeoutPopen):
    def communicate(self, timeout=None):
        return "", None


@pytest.fixture()
def _shots_env(tmp_path, monkeypatch):
    monkeypatch.setattr(_pptd, "find_pwsh", lambda: "pwsh")
    work = tmp_path / "shots_tmp"
    work.mkdir()
    (tmp_path / "x.pptx").write_bytes(b"PK")  # copy2 源文件
    monkeypatch.setattr(_pptd.tempfile, "mkdtemp", lambda prefix="": str(work))
    return work


class TestExportShotsTimeout(object):
    def test_timeout_kills_tree_and_returns_false(self, _shots_env, monkeypatch,
                                                  capsys, tmp_path):
        killed = []
        monkeypatch.setattr(_pptd, "_kill_process_tree", lambda pid: killed.append(pid))
        monkeypatch.setattr(_pptd.subprocess, "Popen", _TimeoutPopen)
        ok = _pptd.export_shots(str(tmp_path / "x.pptx"), str(tmp_path / "out"))
        assert ok is False
        assert killed == [4321]
        assert "超时" in capsys.readouterr().out

    def test_normal_exit_never_kills_tree(self, _shots_env, monkeypatch, tmp_path):
        monkeypatch.setattr(_pptd, "_kill_process_tree",
                            lambda pid: pytest.fail("正常退出不应杀进程树"))
        monkeypatch.setattr(_pptd.subprocess, "Popen", _NormalPopen)
        ok = _pptd.export_shots(str(tmp_path / "x.pptx"), str(tmp_path / "out"))
        assert ok is False  # 无 PNG -> 正常失败路径（非异常）

    def test_kill_process_tree_windows_uses_taskkill(self, monkeypatch):
        calls = []
        monkeypatch.setattr(_pptd.os, "name", "nt", raising=False)
        monkeypatch.setattr(_pptd.subprocess, "run", lambda *a, **k: calls.append(a))
        _pptd._kill_process_tree(99)
        assert calls and "taskkill" in calls[0][0] and "/T" in calls[0][0]


# ---------------------------------------------------------------------------
# P2 COM finally 统一 _close_word
# ---------------------------------------------------------------------------

class _FakeCom(object):
    def __init__(self):
        self.calls = []

    def Close(self, flag):
        self.calls.append(("close", flag))

    def Quit(self):
        self.calls.append(("quit",))

    def Save(self):
        self.calls.append(("save",))


@pytest.fixture()
def com_env(monkeypatch):
    """注入假 win32com 模块强制走 COM 路径，并记录 _open_word 产物。

    同时注入父包 ``win32com``：生产代码用 ``import win32com.client`` 探测 pywin32，
    只塞子模块的话父包仍会真导入失败、整组用例在没装 pywin32 的环境（CI/社区）走
    fallback 分支而失败。注入父包后本组用例与真实 pywin32 解耦。
    """
    fake_pkg = types.ModuleType("win32com")
    fake_client = types.ModuleType("win32com.client")
    fake_pkg.client = fake_client
    monkeypatch.setitem(sys_modules(), "win32com", fake_pkg)
    monkeypatch.setitem(sys_modules(), "win32com.client", fake_client)
    holder = {}
    return holder


def sys_modules():
    import sys
    return sys.modules


class TestComFinallyUsesCloseWord(object):
    def test_postprocess_close_exception_still_quits_word(self, tmp_path, monkeypatch,
                                                          com_env):
        """doc.Save 抛异常：finally 里 Close/Quit 全执行（裸版本 Quit 会被跳过）。"""
        doc = _FakeCom()
        word = _FakeCom()

        real_save = doc.Save

        def _save():
            real_save()
            raise RuntimeError("磁盘满")
        doc.Save = _save

        class _Docs(object):
            def Open(self, p):
                return doc
        word.Documents = _Docs()
        monkeypatch.setattr(com_pp, "_open_word", lambda: word)
        monkeypatch.setattr(com_pp, "_manual_numbering", lambda *a, **k: None)
        monkeypatch.setattr(com_pp, "_add_headers_footers", lambda *a, **k: None)

        src = tmp_path / "in.docx"
        src.write_bytes(b"PK")
        with pytest.raises(RuntimeError):
            com_pp.com_postprocess(str(src), {})
        assert ("save",) in doc.calls
        assert ("close", False) in doc.calls
        assert word.calls == [("quit",)]  # 关键：Quit 必达

    def test_postprocess_normal_path_releases_both(self, tmp_path, monkeypatch,
                                                   com_env):
        doc = _FakeCom()
        word = _FakeCom()

        class _Docs(object):
            def Open(self, p):
                return doc
        word.Documents = _Docs()
        monkeypatch.setattr(com_pp, "_open_word", lambda: word)
        monkeypatch.setattr(com_pp, "_manual_numbering", lambda *a, **k: None)
        monkeypatch.setattr(com_pp, "_add_headers_footers", lambda *a, **k: None)

        src = tmp_path / "ok.docx"
        src.write_bytes(b"PK")
        com_pp.com_postprocess(str(src), {})
        assert doc.calls[-2:] == [("save",), ("close", False)]
        assert word.calls == [("quit",)]

    def test_compare_releases_doc_and_word(self, tmp_path, monkeypatch, com_env):
        """compare 失败路径：result/doc/word 释放，失败体面返回 False。"""
        result = _FakeCom()
        doc = _FakeCom()
        word = _FakeCom()

        def _compare(*a, **k):
            return result

        def _accept():
            raise RuntimeError("接受修订失败")
        result.AcceptAllRevisions = _accept
        doc.Compare = _compare

        class _Docs(object):
            def Open(self, p):
                return doc
        word.Documents = _Docs()
        monkeypatch.setattr(com_pp, "_open_word", lambda: word)

        old = tmp_path / "old.docx"
        old.write_bytes(b"PK")
        new = tmp_path / "new.docx"
        new.write_bytes(b"PK")
        ok = com_pp.compare_documents(str(new), str(old))
        assert ok is False
        assert ("close", False) in result.calls
        assert ("close", False) in doc.calls
        assert word.calls == [("quit",)]
