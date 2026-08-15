# -*- coding: utf-8 -*-
"""pretool_cmd_guard 危险信号判定 + ask 记忆（2026-08-11 增强）的回归测试。

场景：
- 脚本内容 import 内部模块 -> deny（绕过防线 2 的脚本化尝试）
- 脚本内容直写 output/ 下最终交付物 -> deny（绕过 path_guard 的脚本化尝试）
- 脚本内容写中间产物（.page）-> allow
- 普通脚本 -> allow + 提示
- 脚本不存在 -> ask（fail-closed）；同脚本 TTL 内再次 -> allow（ask 记忆）
"""
import importlib.util
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

HOOKS_DIR = os.path.join(SCRIPT_DIR, ".trae", "hooks")


_HOOK_MODS = {}


def _load_hook(name):
    """按路径加载 hook 脚本（hooks 不在 sys.path）。

    模块级缓存：同一路径只 exec 一次，保证 fixture 的 monkeypatch 与
    test 内引用同一模块实例（否则 monkeypatch 不生效）。
    """
    if name not in _HOOK_MODS:
        spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS_DIR, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HOOK_MODS[name] = mod
    return _HOOK_MODS[name]


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    """加载 guard + 隔离 ask 缓存到 tmp（不污染真实 .trae/logs/）。"""
    g = _load_hook("pretool_cmd_guard")
    monkeypatch.setattr(g, "_approved_cache_path", lambda: str(tmp_path / "approved.json"))
    monkeypatch.setattr(g, "ASK_TTL", 3600)
    # 脚本内容读取基于项目根：隔离到 tmp/root
    proj = tmp_path / "root"
    proj.mkdir(exist_ok=True)
    monkeypatch.setenv("TRAE_PROJECT_DIR", str(proj))
    return g, proj


def _mk_script(proj, name, content):
    (proj / name).write_text(content, encoding="utf-8")
    return name


class TestDangerSignals:
    def test_import_internal_module_denied(self, guard):
        g, proj = guard
        _mk_script(proj, "a.py", "import _renderer\nprint('x')\n")
        decision, reason = g._check_command("python a.py")
        assert decision == "deny"
        assert "import 内部模块" in reason

    def test_direct_deliverable_write_denied(self, guard):
        g, proj = guard
        _mk_script(proj, "b.py", "open(r'output/蓝海集团/方案_v1.html', 'w').write('x')\n")
        decision, reason = g._check_command("python b.py")
        assert decision == "deny"
        assert "产出物" in reason

    def test_pptx_deliverable_write_denied(self, guard):
        g, proj = guard
        _mk_script(proj, "b2.py", "open(r'output/蓝海集团/方案_v1.pptx', 'wb').write(b'x')\n")
        decision, reason = g._check_command("python b2.py")
        assert decision == "deny"
        assert "产出物" in reason

    def test_shutil_move_to_deliverable_denied(self, guard):
        g, proj = guard
        _mk_script(proj, "g.py", "shutil.move('output/蓝海集团/方案_v1.html', '.versions/')\n")
        decision, reason = g._check_command("python g.py")
        assert decision == "deny"
        assert "产出物" in reason

    def test_path_reference_in_comment_allowed(self, guard):
        """归档/读取脚本：仅引用产出物路径（无写操作）不误伤。"""
        g, proj = guard
        _mk_script(proj, "f.py", "# 输出到 output/蓝海集团/方案_v1.html 供人工核对\nprint('ok')\n")
        decision, _ = g._check_command("python f.py")
        assert decision == "allow"

    def test_intermediate_page_write_allowed(self, guard):
        g, proj = guard
        _mk_script(proj, "c.py", "open(r'output/蓝海集团/方案_v1/pages/06.page', 'w').write('x')\n")
        decision, _ = g._check_command("python c.py")
        assert decision == "allow"

    def test_plain_script_allowed(self, guard):
        g, proj = guard
        _mk_script(proj, "d.py", "print(1 + 1)\n")
        decision, _ = g._check_command("python d.py")
        assert decision == "allow"

    def test_stdlib_import_not_flagged(self, guard):
        g, proj = guard
        _mk_script(proj, "e.py", "import os, json, re\nprint('ok')\n")
        decision, _ = g._check_command("python e.py")
        assert decision == "allow"


class TestAskMemory:
    def test_missing_script_asks_then_remembered(self, guard):
        g, proj = guard
        decision1, _ = g._check_command("python nonexistent.py")
        assert decision1 == "ask"
        # 同脚本 TTL 内再次 -> allow（ask 记忆生效）
        decision2, reason2 = g._check_command("python nonexistent.py")
        assert decision2 == "allow"
        assert "已确认" in reason2

    def test_ask_memory_expires(self, guard):
        g, proj = guard
        g._check_command("python ghost.py")
        g.ASK_TTL = -1  # 过期 -> 再次 ask
        decision, _ = g._check_command("python ghost.py")
        assert decision == "ask"
