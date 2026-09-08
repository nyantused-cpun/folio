# -*- coding: utf-8 -*-
"""#39 context-health 计数治理回归测试：常驻 WARN 不计次 + 计数器会话隔离。

所有测试隔离到 tmp_path（客户目录 / session_state.json / logs 三处均 monkeypatch），
绝不触碰真实 .folio/logs/ 与 _knowledge/clients/。
"""
import json
import os
import time
from types import SimpleNamespace

import pytest

import _state
import _context_health


@pytest.fixture
def ch_env(tmp_path, monkeypatch):
    clients_dir = tmp_path / "clients"
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(_context_health, "CLIENTS_DIR", str(clients_dir))
    monkeypatch.setattr(_context_health, "LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(_state, "SESSION_STATE_PATH", str(tmp_path / "session_state.json"))
    return SimpleNamespace(clients_dir=clients_dir, logs_dir=logs_dir)


def _make_client(env, name="测试客户A", ctx_pending=True, stale=False):
    """建客户目录。ctx_pending=False 时 context.md 无待澄清段 → C5 常驻 WARN。"""
    client_dir = env.clients_dir / name
    client_dir.mkdir(parents=True)
    ctx = client_dir / "context.md"
    text = "# 测试客户\n"
    if ctx_pending:
        text += "## 待澄清问题(open_questions)\n- 无\n"
    ctx.write_text(text, encoding="utf-8")
    if stale:
        old = time.time() - 30 * 86400
        os.utime(ctx, (old, old))


def _mark_session_done(name="测试客户A"):
    """C2/C3 置 ok（theme-guard / decisions 已读），只留目标项 WARN。"""
    _state.set_state(name, theme_guard_at="2026-09-06T10:00:00", decisions_read_at="2026-09-06T10:00:00")


def test_structural_warn_never_blocks(ch_env):
    """C5 常驻 WARN 连续 5 次不触发 block，计数器纹丝不动。"""
    _make_client(ch_env, ctx_pending=False)  # 仅 C5 WARN（结构性）
    _mark_session_done()
    for i in range(5):
        result = _context_health.run_context_health("测试客户A", command="test")
        assert result["verdict"] == "warn", f"第 {i + 1} 次不应升级"
        assert result["warn_count"] == 0
    assert _state.get_state("测试客户A")["context_warn_count"] == 0


def test_transient_warn_blocks_at_third(ch_env):
    """C2 瞬时 WARN 连续 3 次仍升级 block。"""
    _make_client(ch_env, ctx_pending=True)  # C5 ok
    # C2 WARN（未 theme-guard），C1/C3/C4/C5 均 ok
    for i, expected in enumerate(["warn", "warn", "block"], start=1):
        result = _context_health.run_context_health("测试客户A", command="test")
        assert result["verdict"] == expected, f"第 {i} 次判定 {result['verdict']} != {expected}"
        assert result["warn_count"] == i


def test_session_isolation(ch_env):
    """带 session id 的两次调用互不累计；客户级计数器也不被会话计数污染。"""
    _make_client(ch_env, ctx_pending=True)
    r1 = _context_health.run_context_health("测试客户A", session_id="s1", command="test")
    assert (r1["verdict"], r1["warn_count"], r1["scope"]) == ("warn", 1, "s1")
    r2 = _context_health.run_context_health("测试客户A", session_id="s1", command="test")
    assert (r2["verdict"], r2["warn_count"]) == ("warn", 2)
    # 另一会话从零起算，不继承 s1 的 2 次
    r3 = _context_health.run_context_health("测试客户A", session_id="s2", command="test")
    assert (r3["verdict"], r3["warn_count"]) == ("warn", 1)
    # s1 第 3 次自己阻断，不波及 s2
    r4 = _context_health.run_context_health("测试客户A", session_id="s1", command="test")
    assert r4["verdict"] == "block"
    r5 = _context_health.run_context_health("测试客户A", session_id="s2", command="test")
    assert (r5["verdict"], r5["warn_count"]) == ("warn", 2)
    # 客户级计数器全程未被会话计数写入
    assert _state.get_state("测试客户A")["context_warn_count"] == 0


def test_no_session_keeps_client_level_behavior(ch_env):
    """无 session id 的旧调用行为不变：客户级累计、3 次阻断、--ack 重置。"""
    _make_client(ch_env, ctx_pending=True)
    for i, expected in enumerate(["warn", "warn", "block"], start=1):
        result = _context_health.run_context_health("测试客户A", command="test")
        assert result["verdict"] == expected
        assert result["warn_count"] == i
        assert result["scope"] == "client"
    assert _state.get_state("测试客户A")["context_warn_count"] == 3
    # ack 就地重置客户级计数；本次瞬时 WARN 仍在，重置后计 1
    acked = _context_health.run_context_health("测试客户A", ack=True, command="test")
    assert acked["verdict"] == "warn"
    assert acked["warn_count"] == 1
    assert _state.get_state("测试客户A")["context_warn_count"] == 1


def test_ack_follows_session_scope(ch_env):
    """ack 跟随计数器作用域：会话 ack 只重置该会话，不碰客户级与其他会话。"""
    _make_client(ch_env, ctx_pending=True)
    _context_health.run_context_health("测试客户A", session_id="s1", command="test")
    _context_health.run_context_health("测试客户A", session_id="s1", command="test")
    acked = _context_health.run_context_health("测试客户A", session_id="s1", ack=True, command="test")
    assert "[ack]" in acked["message"]
    assert acked["warn_count"] == 1  # 重置后本次瞬时 WARN 计 1
    with open(_context_health._session_store_path(), "r", encoding="utf-8") as f:
        store = json.load(f)
    assert store["测试客户A"]["s1"]["count"] == 1
    # 客户级计数器未被 ack 触碰
    assert _state.get_state("测试客户A")["context_warn_count"] == 0
