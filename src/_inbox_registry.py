# -*- coding: utf-8 -*-
"""_inbox_registry.py - Inbox 登记表（唯一移动白名单）。

设计原则（spec 第 2 节）：
- 归属在文件进入会话那一刻确定：dest=client | general，note 记用途
- 登记表损坏 → load 降级返回空表（调用方"只报告不移动"）
- 同一文件重复登记 → 更新既有 pending 条目
"""
import json
import os
from datetime import datetime

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR
REGISTRY_PATH = os.path.join(SCRIPT_DIR, ".folio", "logs", "inbox_registry.json")


def _log(msg: str) -> None:
    """降级/异常记录（沿用 _archive_auto._log 风格：吞异常绝不影响主流程）。"""
    try:
        os.makedirs(os.path.join(SCRIPT_DIR, ".folio", "logs"), exist_ok=True)
        with open(os.path.join(SCRIPT_DIR, ".folio", "logs", "inbox_registry.log"),
                  "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except OSError:
        pass


_corrupt = False


def is_corrupt() -> bool:
    """上次 load 是否因损坏降级（auto_archive 据此整体降级为只报告）。"""
    return _corrupt


def load_registry() -> dict:
    global _corrupt
    if not os.path.exists(REGISTRY_PATH):
        _corrupt = False
        return {"entries": []}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            _log("load_registry: entries 非列表，降级为空表")
            _corrupt = True
            return {"entries": []}
        _corrupt = False
        return {"entries": entries}
    except (json.JSONDecodeError, OSError) as e:
        _log(f"load_registry: 登记表损坏，降级为空表（{e}）")
        _corrupt = True
        return {"entries": []}


def save_registry(reg: dict) -> None:
    """原子写：先 .tmp 再 os.replace，崩溃不留半截 JSON（对齐 _archive_auto）。"""
    try:
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        tmp = REGISTRY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, REGISTRY_PATH)
    except OSError as e:
        _log(f"save_registry: 写入失败（{e}）")


def register_entry(filename: str, dest: str, client: str = "", note: str = "") -> dict:
    assert dest in ("client", "general"), f"非法 dest: {dest}"
    entry = {
        "file": os.path.basename(filename),
        "dest": dest,
        "client": client if dest == "client" else "",
        "note": note,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
    }
    reg = load_registry()
    for i, e in enumerate(reg["entries"]):
        if e.get("file") == entry["file"] and e.get("status") == "pending":
            reg["entries"][i] = entry
            save_registry(reg)
            return entry
    reg["entries"].append(entry)
    save_registry(reg)
    return entry


def pending_entries(client: str | None = None) -> list:
    reg = load_registry()
    if client is None:
        return [e for e in reg["entries"] if e.get("status") == "pending"]
    return [e for e in reg["entries"]
            if e.get("status") == "pending" and e.get("dest") == "client"
            and e.get("client") == client]


def mark_done(filename: str) -> bool:
    base = os.path.basename(filename)
    reg = load_registry()
    hit = False
    for e in reg["entries"]:
        if e.get("file") == base and e.get("status") == "pending":
            e["status"] = "done"
            hit = True
            break  # 登记时同 file 仅一条 pending，命中即止防误杀
    if hit:
        save_registry(reg)
    return hit
