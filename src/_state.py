# -*- coding: utf-8 -*-
"""M3-F2 阶段状态机：跨 CLI 调用的轻事实源。

设计取舍（见 M3-F2-report.md）：
- 多客户共存：文件格式为 ``{"clients": {client: state}}``，避免多客户互相覆盖。
- 未指定 client 时 ``get_state()`` 返回默认状态（client 为空字符串、stage=intake）。
- 写入使用临时文件 + ``os.replace`` 原子替换；未使用 ``_save_lock``，因为
  状态文件是单一全局 JSON，且写入量极小；原子 rename 在多数场景下已足够。
  若后续出现多进程高频写竞态，可切换到 ``_save_lock.acquire_save_lock``。
- 所有函数对缺失/损坏文件降级为空状态，绝不抛异常到调用方（除非客户名非法）。
"""
import copy
import json
import os
import tempfile
from datetime import datetime

from _paths import SESSION_STATE_PATH, _validate_client_name

# 阶段机器：intake -> outline -> spec_draft -> spec_confirmed -> html_done
#            -> html_confirmed -> pptx_done -> delivered
# 允许线性推进；当前实现不强制相邻跳转（命令推进点按固定目标写入）。
STAGES = [
    "intake",
    "outline",
    "spec_draft",
    "spec_confirmed",
    "html_done",
    "html_confirmed",
    "pptx_done",
    "delivered",
]

DEFAULT_STATE = {
    "client": "",
    "mode": "pre-sales",
    "stage": "intake",
    "taskId": "",
    "lastReview": {"verdict": "", "issues": [], "at": ""},
    "updatedAt": "",
    # P1-3 context-health 状态
    "context_warn_count": 0,
    "context_ack_used": False,
    "theme_guard_at": "",
    "decisions_read_at": "",
    "context_health_skipped": [],
}

# 允许 set_state 写入的顶层字段（lastReview/taskId 等由调用方自由更新）
_MUTABLE_FIELDS = {
    "client",
    "mode",
    "stage",
    "taskId",
    "lastReview",
    "updatedAt",
    "context_warn_count",
    "context_ack_used",
    "theme_guard_at",
    "decisions_read_at",
    "context_health_skipped",
}


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _empty_store():
    return {"clients": {}}


def _read_store():
    """读取状态文件；文件缺失/损坏/格式异常时返回空 store（不抛异常）。"""
    try:
        with open(SESSION_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_store()
        clients = data.get("clients")
        if not isinstance(clients, dict):
            return _empty_store()
        return data
    except (OSError, ValueError):
        return _empty_store()


def _write_store(store):
    """原子写：写入同目录临时文件后 os.replace 覆盖目标。"""
    directory = os.path.dirname(SESSION_STATE_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".session_state.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SESSION_STATE_PATH)
    except Exception:
        # 临时文件可能已创建；尽力清理，不掩盖原始异常
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _default_for(client_name, mode="pre-sales"):
    state = copy.deepcopy(DEFAULT_STATE)
    state["client"] = client_name
    state["mode"] = mode
    return state


def get_state(client_name=None):
    """读取单个客户状态；client_name 为空时返回默认状态。

    返回 deep copy（调用方可安全修改 lastReview/外层而不影响默认值或磁盘数据）。
    """
    if not client_name:
        return copy.deepcopy(DEFAULT_STATE)
    _validate_client_name(client_name)
    store = _read_store()
    state = store.get("clients", {}).get(client_name)
    if not state or not isinstance(state, dict):
        return _default_for(client_name)
    # 归一化：缺失 key 补默认，兼容手改/旧文件
    merged = _default_for(client_name)
    merged.update(state)
    merged["client"] = merged.get("client") or client_name
    return copy.deepcopy(merged)


def set_state(client, **fields):
    """设置客户状态字段；stage 必须合法；返回更新后的状态副本。

    未知字段忽略（避免手滑写入无关 key）。
    """
    if not client:
        raise ValueError("client 不能为空")
    _validate_client_name(client)
    store = _read_store()
    clients = store.setdefault("clients", {})
    state = clients.get(client)
    if not state or not isinstance(state, dict):
        state = _default_for(client)
        clients[client] = state
    for key in _MUTABLE_FIELDS:
        if key in fields:
            value = fields[key]
            if key == "stage":
                if value not in STAGES:
                    raise ValueError(
                        f"非法 stage {value!r}，合法值: {', '.join(STAGES)}"
                    )
                state[key] = value
            elif key in ("client", "taskId", "mode", "updatedAt"):
                if value is not None:
                    state[key] = value
            elif key == "lastReview":
                if isinstance(value, dict):
                    state[key] = copy.deepcopy(value)
            elif key == "context_warn_count":
                if isinstance(value, int):
                    state[key] = max(0, value)
            elif key == "context_ack_used":
                if isinstance(value, bool):
                    state[key] = value
            elif key in ("theme_guard_at", "decisions_read_at"):
                if isinstance(value, str):
                    state[key] = value
            elif key == "context_health_skipped":
                if isinstance(value, list):
                    state[key] = [str(v) for v in value if isinstance(v, str)]
    state["updatedAt"] = _now_iso()
    clients[client] = state
    _write_store(store)
    return copy.deepcopy(state)


def advance(client, stage):
    """推进到指定 stage（命令推进点使用）。

    stage 必须属于 STAGES，否则 ValueError。
    """
    if stage not in STAGES:
        raise ValueError(f"非法 stage {stage!r}，合法值: {', '.join(STAGES)}")
    return set_state(client, stage=stage)


def reset_state(client):
    """重置客户到默认 intake（保留客户名）。"""
    if not client:
        raise ValueError("client 不能为空")
    _validate_client_name(client)
    store = _read_store()
    store.setdefault("clients", {})[client] = _default_for(client)
    _write_store(store)
    return copy.deepcopy(_default_for(client))


def list_states():
    """返回 {client: state} 深拷贝快照（不含默认空客户）。"""
    store = _read_store()
    out = {}
    for client, state in store.get("clients", {}).items():
        if not state or not isinstance(state, dict):
            continue
        merged = _default_for(client)
        merged.update(state)
        merged["client"] = merged.get("client") or client
        out[client] = copy.deepcopy(merged)
    return out
