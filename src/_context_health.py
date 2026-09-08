# -*- coding: utf-8 -*-
"""P1-3 context-health：生成前上下文健康检查与 WARN 累计门禁。

检查项 C1-C5，全部为确定性判据；前 2 次 WARN 放行，第 3 次阻断；
`--ack` 重置累计一次。落盘 .folio/logs/context_health.jsonl。

#39 计数治理（2026-09-06）：
- C4/C5 为结构性常驻项（refs 未读、待澄清段缺失在修复前每次必 WARN），
  不计入 block 升级累计——只有 C1-C3 瞬时可修复问题计次；
- 计数器按会话隔离：传 session_id 时计数落
  .folio/logs/context_health_sessions.json（按 client+session 隔离，每客户
  最多保留 _SESSION_CAP 个会话，按 updated_at 淘汰）；不传则沿用原客户级
  context_warn_count（向后兼容）。ack 跟随当前作用域就地重置。
"""
import os
import json
import tempfile
from datetime import datetime

from _paths import CLIENTS_DIR, LOGS_DIR

# 结构性常驻检查项：不计入 block 升级累计（#39）
_STRUCTURAL_CHECKS = {"C4", "C5"}
# 会话隔离计数存储（#39）
_SESSION_STORE_FILE = "context_health_sessions.json"
_SESSION_CAP = 8


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _client_dir(client_name):
    return os.path.join(CLIENTS_DIR, client_name)


def _load_state(client_name):
    from _state import get_state
    return get_state(client_name)


def _save_state(client_name, **fields):
    from _state import set_state
    return set_state(client_name, **fields)


def _append_log(client_name, command, checks, verdict, warn_count, session_id=None):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        path = os.path.join(LOGS_DIR, "context_health.jsonl")
        line = {
            "ts": _now_iso(),
            "client": client_name,
            "command": command,
            "checks": checks,
            "verdict": verdict,
            "warn_count": warn_count,
            "scope": session_id or "client",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _session_store_path():
    return os.path.join(LOGS_DIR, _SESSION_STORE_FILE)


def _load_session_count(client_name, session_id):
    """读会话隔离计数；文件缺失/损坏/条目异常一律按 0 起算。"""
    try:
        with open(_session_store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get(client_name, {}).get(session_id, {})
        return int(entry.get("count") or 0)
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def _save_session_count(client_name, session_id, count):
    """写会话隔离计数（原子替换）；失败不阻断检查（与 _append_log 同口径）。"""
    try:
        path = _session_store_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        sessions = data.get(client_name)
        if not isinstance(sessions, dict):
            sessions = {}
        sessions[session_id] = {"count": max(0, int(count)), "updated_at": _now_iso()}
        if len(sessions) > _SESSION_CAP:
            ranked = sorted(
                sessions.items(),
                key=lambda kv: kv[1].get("updated_at", "") if isinstance(kv[1], dict) else "",
                reverse=True,
            )
            sessions = dict(ranked[:_SESSION_CAP])
        data[client_name] = sessions
        os.makedirs(LOGS_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".ch_sessions.", suffix=".tmp", dir=LOGS_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        pass


def run_context_health(client_name, skip=None, reasons=None, ack=False, command="manual", session_id=None):
    """执行 context-health 检查。

    skip: 本次显式跳过的 refs（从 WARN 中豁免）。
    reasons: {ref: reason}，仅用于日志。
    ack: 人工确认，重置当前作用域累计 WARN 一次。
    session_id: 传入则计数按会话隔离（#39）；None 保持客户级累计（向后兼容）。
    """
    if not client_name:
        return {
            "client": "",
            "checks": [{"id": "C1", "status": "warn", "detail": "未指定客户"}],
            "verdict": "warn",
            "warn_count": 0,
            "message": "context-health 需要 --client <客户名>",
        }

    skip = set(skip or [])
    reasons = reasons or {}
    state = _load_state(client_name)
    checks = []
    warn = 0
    warn_transient = 0
    warn_structural = 0

    # C1: context 活性——存在、非空、14 天更新
    client_dir = _client_dir(client_name)
    context_path = os.path.join(client_dir, "context.md")
    c1_detail = ""
    c1_ok = False
    if not os.path.isdir(client_dir):
        c1_detail = "客户目录不存在"
    elif not os.path.exists(context_path):
        c1_detail = "context.md 缺失"
    else:
        try:
            size = os.path.getsize(context_path)
            age_days = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(context_path))).days
            if size > 0 and age_days <= 14:
                c1_ok = True
                c1_detail = f"context.md {size} bytes / {age_days} 天"
            else:
                c1_detail = f"context.md 空或超过 14 天未更新（{age_days} 天）"
        except OSError as e:
            c1_detail = f"context.md 读取失败: {e}"
    checks.append({"id": "C1", "status": "ok" if c1_ok else "warn", "detail": c1_detail})
    if not c1_ok:
        warn += 1
        warn_transient += 1

    # C2: 本会话已 theme-guard
    c2_ok = bool(state.get("theme_guard_at"))
    checks.append({
        "id": "C2",
        "status": "ok" if c2_ok else "warn",
        "detail": f"theme_guard_at={state.get('theme_guard_at') or '未执行'}",
    })
    if not c2_ok:
        warn += 1
        warn_transient += 1

    # C3: 决策已读（session-start 已运行视为读取事件）
    c3_ok = bool(state.get("decisions_read_at"))
    checks.append({
        "id": "C3",
        "status": "ok" if c3_ok else "warn",
        "detail": f"decisions_read_at={state.get('decisions_read_at') or '未标记'}",
    })
    if not c3_ok:
        warn += 1
        warn_transient += 1

    # C4: refs 声明制——refs 非空且未全部显式 skip/已读 -> WARN
    refs = []
    refs_dir = os.path.join(client_dir, "refs")
    if os.path.isdir(refs_dir):
        refs = [f for f in os.listdir(refs_dir) if not f.startswith(".") and os.path.isfile(os.path.join(refs_dir, f))]
    pending_refs = [r for r in refs if r not in skip]
    c4_ok = not pending_refs
    c4_detail = (
        "无 refs，跳过检查" if not refs
        else f"已声明但未读 {len(pending_refs)} 个: {', '.join(pending_refs[:5])}"
    )
    checks.append({"id": "C4", "status": "ok" if c4_ok else "warn", "detail": c4_detail})
    if not c4_ok:
        warn += 1
        warn_structural += 1

    # C5: open_questions 缺失未声明
    c5_ok = False
    c5_detail = "未找到 open_questions/待澄清声明"
    if os.path.exists(context_path):
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                ctx_text = f.read()
            if "待澄清" in ctx_text or "open_questions" in ctx_text.lower():
                c5_ok = True
                c5_detail = "context.md 含待澄清/open_questions 段"
        except OSError:
            pass
    checks.append({"id": "C5", "status": "ok" if c5_ok else "warn", "detail": c5_detail})
    if not c5_ok:
        warn += 1
        warn_structural += 1

    # 计数器按作用域取值（#39）：有 session_id 用会话隔离计数，否则客户级累计
    if session_id:
        scope_count = _load_session_count(client_name, session_id)
    else:
        scope_count = int(state.get("context_warn_count") or 0)

    # 人工 --ack 就地重置当前作用域累计一次（ack 跟随计数器作用域，#39/Q4）
    if ack:
        if session_id:
            _save_session_count(client_name, session_id, 0)
            state = _save_state(client_name, context_ack_used=True)
        else:
            state = _save_state(client_name, context_warn_count=0, context_ack_used=True)
        warn_count = 0
        ack_note = "[ack] 已重置累计 WARN"
    else:
        warn_count = scope_count
        ack_note = ""

    # 只有瞬时可修复问题（C1-C3）计次；C4/C5 常驻 WARN 每次提示但不升级（#39）
    if warn_transient > 0:
        warn_count += 1
        if session_id:
            _save_session_count(client_name, session_id, warn_count)
        else:
            state = _save_state(client_name, context_warn_count=warn_count)

    scope_note = f"会话 {session_id} " if session_id else ""
    if warn_count >= 3:
        verdict = "block"
        message = f"context-health：{scope_note}累计第 {warn_count} 次 WARN，生成阻断；请补齐上下文或执行 --ack 重置一次"
    elif warn > 0:
        verdict = "warn"
        message = f"context-health：{warn} 项 WARN（{scope_note}累计 {warn_count}/3），本次放行"
        if warn_structural > 0:
            message += "；C4/C5 结构性项不计次"
    else:
        verdict = "pass"
        message = "context-health：全部检查通过"

    if ack_note:
        message += f"；{ack_note}"

    _append_log(client_name, command, checks, verdict, warn_count, session_id=session_id)
    return {
        "client": client_name,
        "checks": checks,
        "verdict": verdict,
        "warn_count": warn_count,
        "scope": session_id or "client",
        "message": message,
    }
