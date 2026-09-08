# -*- coding: utf-8 -*-
"""安全 P1-2 回归：Word COM 启动必须强制禁宏（AutomationSecurity=3）。

msoAutomationSecurityForceDisable=3：打开外部/客户提供的 docx 前禁用宏，
防宏病毒。docx_com_postprocess 的全部启动入口（com_postprocess +
renumber/normalize/style_set/headers/toc/pdf/accept/compare 8 处）收拢于
_open_word 单点，_cli_cmds_gen._open_word_doc 独立设置。
"""
from unittest.mock import MagicMock

import pytest

import _cli_cmds_gen
import _renderer.docx_com_postprocess as com_mod

# pywin32 是可选依赖（Word COM 后处理才需要）；社区/CI 环境可不装。
# 缺包时整模块跳过，而不是让收集期 ImportError 把 CI 打红。
win32com_client = pytest.importorskip(
    "win32com.client",
    reason="需要 pywin32（Word COM）；未安装则跳过本组用例",
)


class TestWordComMacroDisabled:
    def test_open_word_sets_automation_security(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(win32com_client, "Dispatch", lambda name: fake)
        word = com_mod._open_word()
        assert word.AutomationSecurity == 3

    def test_open_word_doc_sets_automation_security(self, monkeypatch, tmp_path):
        fake = MagicMock()
        monkeypatch.setattr(win32com_client, "Dispatch", lambda name: fake)
        docx = tmp_path / "x.docx"
        docx.write_bytes(b"PK")
        word, doc = _cli_cmds_gen._open_word_doc(str(docx))
        assert word.AutomationSecurity == 3
        word.Documents.Open.assert_called_once()

    def test_com_postprocess_launches_via_open_word(self, monkeypatch, tmp_path):
        """com_postprocess 不再直连 Dispatch，统一走 _open_word。"""
        fake_word = MagicMock()
        monkeypatch.setattr(com_mod, "_open_word", lambda: fake_word)
        docx = tmp_path / "x.docx"
        docx.write_bytes(b"PK")
        com_mod.com_postprocess(str(docx), {"dark_bid": True})
        fake_word.Documents.Open.assert_called_once()
        fake_word.Quit.assert_called_once()

    def test_dispatch_centralized_in_helper(self):
        """源码守卫「集中为 helper 防遗漏」：模块内 Dispatch 只允许 _open_word 一处。"""
        with open(com_mod.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        assert src.count("win32com.client.Dispatch") == 1
