# -*- coding: utf-8 -*-
"""P3 加固回归测试（2026-09-06 安全审查报告 P3 条目，全部离线，不启真浏览器/PowerPoint）。

覆盖：
1. _cloud_llm_vision：host 模式只记长度+前 80 字符预览，不回显完整 prompt
2. _cli_cmds_qa：web-search 服务器可控 content 默认不回显（DEBUG_REMOTE_ECHO 门控）
3. _pptd：临时 .ps1 回读比对校验（不一致大声拒绝，正常链路不受影响）
4. _density：无头渲染注册 route 守卫，只放行 file://，拦截远程 navigation/子资源
5. _cli_audit：key-doctor 掩码只留末 4 位（前0后4），不足 8 位全掩
"""
from types import SimpleNamespace

import pytest

import _cli_audit
import _cli_cmds_qa
import _cloud_llm
import _cloud_llm_vision
import _density
import _pptd


# ============================================================
# 1. host 模式 prompt 截断
# ============================================================
class TestVisionHostPromptBrief:
    def test_host_mode_truncates_prompt_to_length_and_preview(self, monkeypatch, capsys):
        """host 模式：vision_chat 返回 None，只打印长度+前 80 字符，不回显全文。"""
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "host")
        prompt = "M" * 80 + "SECRET_TAIL_MATERIAL"
        result = _cloud_llm_vision.vision_chat(prompt, "fake.png", task="vision")
        out = capsys.readouterr().out
        assert result is None
        assert "[host-mode" in out
        assert "image=fake.png" in out
        assert "长度=100" in out
        assert prompt[:80] in out          # 前 80 字符预览在场
        assert "SECRET_TAIL_MATERIAL" not in out  # 全文不进会话日志


# ============================================================
# 2. web-search 服务器可控内容回显门控
# ============================================================
def _ws_args():
    return SimpleNamespace(query="测试", max_results=3, engines=None)


class TestWebSearchEchoGate:
    def test_content_not_echoed_by_default(self, monkeypatch, capsys):
        """默认：content（服务器可控）不回显，标题/URL 照常。"""
        monkeypatch.delenv("DEBUG_REMOTE_ECHO", raising=False)
        monkeypatch.setattr(_cloud_llm, "web_search", lambda *a, **k: [
            {"source": "tavily", "title": "标题A", "url": "https://example.com/a",
             "content": "OKDATA" + "X" * 250 + "NEVER_ECHO_SECRET"},
        ])
        _cli_cmds_qa.cmd_web_search(_ws_args())
        out = capsys.readouterr().out
        assert "标题A" in out and "https://example.com/a" in out
        assert "OKDATA" not in out
        assert "NEVER_ECHO_SECRET" not in out

    def test_content_echoed_only_with_debug_env(self, monkeypatch, capsys):
        """DEBUG_REMOTE_ECHO=1：回显前 200 字符，尾部仍被截断。"""
        monkeypatch.setenv("DEBUG_REMOTE_ECHO", "1")
        content = "OKDATA" + "X" * 250 + "TAILSECRET"
        monkeypatch.setattr(_cloud_llm, "web_search", lambda *a, **k: [
            {"source": "tavily", "title": "标题B", "url": "https://example.com/b",
             "content": content},
        ])
        _cli_cmds_qa.cmd_web_search(_ws_args())
        out = capsys.readouterr().out
        assert content[:200] in out
        assert "TAILSECRET" not in out


# ============================================================
# 3. 临时 .ps1 回读比对校验
# ============================================================
class TestPs1ReadbackVerify:
    def test_readback_helper_detects_tamper(self, tmp_path):
        """写入后未被改动→放行；被改动→拒绝；文件缺失→拒绝。"""
        ps1 = tmp_path / "export.ps1"
        ps1.write_text(_pptd._EXPORT_PS1, encoding="utf-8")
        assert _pptd._verify_ps1_readback(str(ps1), _pptd._EXPORT_PS1) is True
        ps1.write_text(_pptd._EXPORT_PS1 + "\n; tampered", encoding="utf-8")
        assert _pptd._verify_ps1_readback(str(ps1), _pptd._EXPORT_PS1) is False
        assert _pptd._verify_ps1_readback(str(tmp_path / "nope.ps1"), "x") is False

    def test_export_shots_refuses_when_readback_mismatch(self, tmp_path, monkeypatch, capsys):
        """校验不过：不启动 PowerShell，返回 False 并大声报篡改。"""
        src = tmp_path / "src.pptx"
        src.write_bytes(b"PK\x03\x04fake")

        def _boom(*a, **k):
            raise AssertionError("校验失败时不得启动 PowerShell 进程")

        monkeypatch.setattr(_pptd, "find_pwsh", lambda: "pwsh-fake")
        monkeypatch.setattr(_pptd.tempfile, "mkdtemp", lambda prefix="": str(tmp_path / "tmpshots"))
        (tmp_path / "tmpshots").mkdir()
        monkeypatch.setattr(_pptd.subprocess, "Popen", _boom)
        monkeypatch.setattr(_pptd, "_verify_ps1_readback", lambda *a, **k: False)
        ok = _pptd.export_shots(str(src), str(tmp_path / "out"))
        assert ok is False
        assert "疑似被篡改" in capsys.readouterr().out

    def test_export_shots_normal_chain_still_executes(self, tmp_path, monkeypatch, capsys):
        """校验通过：正常链路照常走到 Popen，行为与修复前一致。"""
        src = tmp_path / "src.pptx"
        src.write_bytes(b"PK\x03\x04fake")
        called = {}

        class _FakeProc:
            pid = 4242
            returncode = 0

            def communicate(self, timeout=None):
                return ("", None)

        def _fake_popen(cmd, **kwargs):
            called["cmd"] = cmd
            return _FakeProc()

        monkeypatch.setattr(_pptd, "find_pwsh", lambda: "pwsh-fake")
        monkeypatch.setattr(_pptd.tempfile, "mkdtemp", lambda prefix="": str(tmp_path / "tmpshots"))
        (tmp_path / "tmpshots").mkdir()
        monkeypatch.setattr(_pptd.subprocess, "Popen", _fake_popen)
        ok = _pptd.export_shots(str(src), str(tmp_path / "out"))
        assert called["cmd"][0] == "pwsh-fake"
        assert "-ExecutionPolicy" in called["cmd"] and "-File" in called["cmd"]
        assert ok is False  # 无 PNG 产出，与修复前行为一致
        assert "未导出任何 PNG" in capsys.readouterr().out


# ============================================================
# 4. playwright 无头渲染 route 守卫（fake page，不启真浏览器）
# ============================================================
class _FakeRoute:
    def __init__(self, url):
        self.request = SimpleNamespace(url=url)
        self.continued = False
        self.aborted = False

    def continue_(self):
        self.continued = True

    def abort(self):
        self.aborted = True


class _FakePage:
    def __init__(self):
        self.routes = []
        self.gotos = []
        self.waits = []

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def goto(self, url):
        self.gotos.append(url)

    def wait_for_load_state(self, state):
        self.waits.append(state)

    def set_viewport_size(self, size):
        self.viewport = size

    def screenshot(self, path, full_page=False):
        self.shots = getattr(self, "shots", []) + [path]

    def close(self):
        self.page_closed = True

    def evaluate(self, js):
        return {"is_crafted": False, "findings": [], "metrics": {}}


class _FakeBrowser:
    def __init__(self):
        self.page = _FakePage()
        self.closed = False

    def new_page(self, **kwargs):
        return self.page

    def close(self):
        self.closed = True


class _FakePwCtx:
    """模拟 sync_playwright() 上下文管理器（替代真 playwright，离线）。"""

    def __init__(self):
        self.browser = _FakeBrowser()
        self.launch_kwargs = None
        outer = self

        class _Chromium:
            @staticmethod
            def launch(**kwargs):
                outer.launch_kwargs = kwargs
                return outer.browser

        self.chromium = _Chromium()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestDensityRouteGuard:
    def test_guard_allows_file_and_blocks_remote(self):
        """file:// 放行；远程 navigation 与子资源、空 URL 一律 abort。"""
        page = _FakePage()
        _density._install_local_only_route(page)
        assert page.routes and page.routes[0][0] == "**/*"
        handler = page.routes[0][1]
        local = _FakeRoute("file:///D:/out/page.html")
        remote_nav = _FakeRoute("https://evil.example/next")
        remote_asset = _FakeRoute("http://cdn.example/x.png")
        blank = _FakeRoute(None)
        handler(local)
        handler(remote_nav)
        handler(remote_asset)
        handler(blank)
        assert local.continued and not local.aborted
        assert remote_nav.aborted and not remote_nav.continued
        assert remote_asset.aborted and not remote_asset.continued
        assert blank.aborted

    def test_check_density_html_registers_route_guard(self, tmp_path, monkeypatch):
        """check_density_html 渲染前注册 route 守卫，goto 仍为本机 file:// 产物。"""
        html = tmp_path / "page.html"
        html.write_text("<html><body>x</body></html>", encoding="utf-8")
        ctx = _FakePwCtx()
        # playwright 是可选依赖（无头渲染才需要）；CI 不安装，缺包跳过本用例
        pw_sync_api = pytest.importorskip(
            "playwright.sync_api",
            reason="需要 playwright（无头渲染）；未安装则跳过本用例",
        )
        monkeypatch.setattr(pw_sync_api, "sync_playwright", lambda: ctx)
        findings = _density.check_density_html(str(html))
        page = ctx.browser.page
        assert len(page.routes) == 1 and page.routes[0][0] == "**/*"
        assert page.gotos and page.gotos[0].startswith("file:///")
        assert findings == []
        assert ctx.browser.closed


# ============================================================
# 5. key-doctor 掩码收紧（主控补：_cli_audit._mask_key）
# ============================================================
class TestMaskKey:
    def test_long_key_keeps_only_last_four(self):
        """长 key 只留末 4 位：前 6 位不再暴露。"""
        assert _cli_audit._mask_key("sk-abcdefghij1234") == "***1234"

    def test_short_key_fully_masked(self):
        """不足 8 位全掩：末 4 已过半不放过。"""
        assert _cli_audit._mask_key("abc123") == "***"
        assert _cli_audit._mask_key("12345678") == "***5678"  # 恰 8 位：末 4 可留
