# -*- coding: utf-8 -*-
"""_archive_auto.py - 会话后自动归档（归属在会话内产生，归档在 save 时消费）。

解决的问题：产出/接收文件在 A 对话，跑归档在 B 对话 -> 只能靠文件名猜客户，屡屡出错。
方案（三层防线）：
  1. session-start 记录会话开始时间戳 -> 定义"本会话窗口"
  2. archive-note 显式登记（AI 会话内声明"文件 X 属于客户 Y"）-> 归属 100% 准确
  3. save 自动归档：inbox/ 根目录中 mtime 落在会话窗口内、或被登记的文件，
     直接移入 _knowledge/clients/{客户}/refs/ 并更新 index.json + 写日志
     （窗口外未登记文件不移动，只列待确认清单）

设计原则：
- 只动 inbox/ 根目录文件，不扫子目录（_uncategorized/ 等保持现状）
- 归档动作与 _classify.classify 同构（移动 + index 更新），可独立使用
- 所有 IO 异常吞掉并记日志，绝不影响 save 主流程
"""
import json
import os
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, ".trae", "logs")
SESSION_START_LOG = os.path.join(LOG_DIR, "session_start_time.txt")
PENDING_LOG = os.path.join(LOG_DIR, "archive_pending.json")
INDEX_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "index.json")

# 与 _classify_config.json rules_meta 保持一致：inbox 禁止残留的类型
FORBIDDEN_IN_INBOX_EXTS = (".py", ".log", ".pyc", ".tmp", ".bak")


# ---------- 时间戳 ----------

def record_session_start(client_name: str) -> None:
    """会话开始时记录时间戳 + 客户名（原子写）。save 自动归档靠它界定窗口。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        tmp = SESSION_START_LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"ts": datetime.now().isoformat(timespec="seconds"), "client": client_name},
                f, ensure_ascii=False
            )
        os.replace(tmp, SESSION_START_LOG)
    except OSError:
        pass  # 记录失败不影响会话启动


def _read_session_start() -> tuple | None:
    """读会话开始时间戳。返回 (iso_ts, client) 或 None。"""
    if not os.path.exists(SESSION_START_LOG):
        return None
    try:
        with open(SESSION_START_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("ts", ""), data.get("client", ""))
    except (OSError, json.JSONDecodeError):
        return None


# ---------- 显式登记表 ----------

def _load_pending() -> dict:
    """读登记表 {client: {filename: ts}}。损坏时重置。"""
    if not os.path.exists(PENDING_LOG):
        return {}
    try:
        with open(PENDING_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_pending(data: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(PENDING_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def archive_note(client_name: str, filenames: list) -> dict:
    """显式登记：文件（可含路径，只取文件名）归属某客户。返回 {"added": [...], "ignored": [...]}。"""
    added, ignored = [], []
    pending = _load_pending()
    bucket = pending.setdefault(client_name, {})
    ts = datetime.now().isoformat(timespec="seconds")
    for fn in filenames:
        base = os.path.basename(fn)
        if not base:
            ignored.append(fn)
            continue
        bucket[base] = ts
        added.append(base)
    _save_pending(pending)
    return {"added": added, "ignored": ignored}


def list_pending() -> dict:
    """查看全部待归档登记。"""
    return _load_pending()


# ---------- 归档核心 ----------

def _load_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"projects": {}, "recents": []}
    return {"projects": {}, "recents": []}


def _save_index(index) -> None:
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _update_index(client_name: str, filename: str) -> None:
    """向 index.json 追加资产记录（结构与 _classify.classify 一致）。"""
    index = _load_index()
    project_key = f"_knowledge/clients/{client_name}/refs"
    if project_key not in index["projects"]:
        index["projects"][project_key] = {"name": client_name, "assets": []}
    index["projects"][project_key]["assets"].append({
        "file": filename,
        "type": "input",
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    index["recents"].insert(0, {
        "file": filename,
        "target": project_key,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    index["recents"] = index["recents"][:50]
    _save_index(index)


def _log(msg: str) -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(LOG_DIR, f"archive_auto_{day}.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass
    print(f"[归档] {msg}")


def archive_to_client(client_name: str, filenames: list, src_dir: str) -> dict:
    """把一组文件移入 _knowledge/clients/{client}/refs/ 并更新 index。
    返回 {"moved": [name], "skipped": [(name, reason)]}。"""
    refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "refs")
    os.makedirs(refs_dir, exist_ok=True)
    moved, skipped = [], []
    for fn in filenames:
        src = os.path.join(src_dir, fn)
        if not os.path.isfile(src):
            skipped.append((fn, "源文件不存在"))
            continue
        dst = os.path.join(refs_dir, fn)
        if os.path.exists(dst):
            base, ext = os.path.splitext(fn)
            dst = os.path.join(refs_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
        try:
            shutil.move(src, dst)
            _update_index(client_name, os.path.basename(dst))
            _log(f"OK {fn} -> _knowledge/clients/{client_name}/refs/")
            moved.append(fn)
        except OSError as e:
            _log(f"FAIL {fn}: 移动失败（{e}）")
            skipped.append((fn, f"移动失败: {e}"))
    return {"moved": moved, "skipped": skipped}


def auto_archive(client_name: str) -> dict:
    """save 时自动归档。返回 {"archived": [...], "pending_review": [...], "ignored": [...], "reason": ""}。"""
    result = {"archived": [], "pending_review": [], "ignored": [], "reason": ""}
    try:
        inbox = os.path.join(SCRIPT_DIR, "inbox")
        if not os.path.isdir(inbox):
            return result

        # 窗口内文件 + 登记文件
        pending = _load_pending()
        registered = set(pending.get(client_name, {}).keys())
        start_info = _read_session_start()
        start_dt = None
        if start_info:
            start_ts, start_client = start_info
            # 防多客户交替误归：仅当 session-start 客户与当前 save 客户一致时才启用窗口
            if start_client == client_name:
                try:
                    start_dt = datetime.fromisoformat(start_ts)
                except ValueError:
                    start_dt = None

        candidates, leaves = [], []
        for fn in os.listdir(inbox):
            full = os.path.join(inbox, fn)
            if not os.path.isfile(full):
                continue  # 子目录不动
            if fn.lower().endswith(FORBIDDEN_IN_INBOX_EXTS):
                result["ignored"].append(fn)
                continue
            if fn in registered:
                candidates.append(fn)
            elif start_dt is not None:
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(full))
                except OSError:
                    leaves.append(fn)
                    continue
                if mtime >= start_dt:
                    candidates.append(fn)
                else:
                    leaves.append(fn)
            else:
                leaves.append(fn)

        if not candidates:
            result["reason"] = "无窗口内/登记文件" if not leaves else "仅窗口外文件，未移动"
            result["pending_review"] = leaves
            return result

        outcome = archive_to_client(client_name, candidates, inbox)
        result["archived"] = outcome["moved"]
        result["pending_review"] = leaves + [name for name, _ in outcome["skipped"]]

        # 已处理登记项清除
        if outcome["moved"]:
            pending = _load_pending()
            bucket = pending.get(client_name, {})
            for fn in outcome["moved"]:
                bucket.pop(fn, None)
            if not bucket:
                pending.pop(client_name, None)
            _save_pending(pending)
    except Exception as e:
        result["reason"] = f"自动归档异常（不影响 save 主流程）: {e}"
        _log(f"ERROR auto_archive: {e}")
    return result
