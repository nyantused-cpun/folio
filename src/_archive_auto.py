# -*- coding: utf-8 -*-
"""_archive_auto.py - save 时自动归档（登记制，spec 2026-09-01）。

解决的问题：产出/接收文件在 A 对话，跑归档在 B 对话 -> mtime/关键词猜客户屡屡出错。
方案（登记制三层）：
  1. session-start 记录会话开始时间戳（保留，供提示信号）
  2. archive-note 显式登记（dest=client|general，note 记用途）-> 归属在进入会话那一刻确定
  3. save 只移动"登记过的"文件（登记表是唯一移动白名单）：
     client 条目归 _knowledge/clients/{客户}/refs/，general 条目归 _knowledge/refs/
     剩余未登记文件交 _inbox_scan.sweep_pending 收进中转区（save 即巡，结束 inbox 必空）

设计原则：
- 归属看用途不看内容：关键词/mtime 只出提示，无移动权
- 禁止自动创建客户目录（clients/{X} 不存在 → 拒绝移动，走客户入库流程）
- 登记表损坏 → 整体降级为只报告，连 sweep 也不动
- 所有 IO 异常吞掉并记日志，绝不影响 save 主流程
"""
import json
import os
import shutil
from datetime import datetime

import _inbox_registry as _reg

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR
LOG_DIR = os.path.join(SCRIPT_DIR, ".folio", "logs")
SESSION_START_LOG = os.path.join(LOG_DIR, "session_start_time.txt")
INDEX_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "index.json")
GENERAL_REFS_KEY = "通用参考"  # _update_index 中通用库的 project 名称

# 与 _classify_config.json rules_meta 保持一致：inbox 禁止残留的类型（sweep 跳过，归 classify 处理）
FORBIDDEN_IN_INBOX_EXTS = (".py", ".log", ".pyc", ".tmp", ".bak")


# ---------- 时间戳（提示信号用） ----------

def record_session_start(client_name: str) -> None:
    """会话开始时记录时间戳 + 客户名（原子写）。"""
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


# ---------- 显式登记（三选一） ----------

def archive_note(filenames: list, dest: str = "client",
                 client_name: str = "", note: str = "") -> dict:
    """显式登记：dest=client 需客户名；dest=general 不需要。返回 {"added","ignored","errors"}。"""
    result = {"added": [], "ignored": [], "errors": []}
    if dest not in ("client", "general"):
        result["errors"].append(f"非法 dest: {dest}")
        return result
    if dest == "client" and not client_name:
        result["errors"].append("dest=client 必须提供客户名")
        return result
    for fn in filenames:
        base = os.path.basename(fn)
        if not base:
            result["ignored"].append(fn)
            continue
        _reg.register_entry(base, dest, client=client_name, note=note)
        result["added"].append(base)
    return result


def list_pending() -> dict:
    """查看全部待归档登记（含 general）。"""
    return {"entries": _reg.pending_entries()}


# ---------- index 维护 ----------

def _load_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # C-A7：损坏不再静默清空——先把损坏件备份留档，再从空结构重建
            # （此前 JSONDecodeError 直接返回空 dict，下一次 _save_index 用空结构
            # 覆盖全库索引，历史登记无痕丢失）。备份失败不阻断重建（记日志）。
            backup = f"{INDEX_PATH}.corrupt-{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            try:
                shutil.copy2(INDEX_PATH, backup)
                _log(f"[index] index.json 解析失败（{e}），已备份 {os.path.basename(backup)} 后重建")
            except OSError as be:
                _log(f"[index] index.json 解析失败（{e}），备份也失败（{be}），仍重建")
            return {"projects": {}, "recents": []}
    return {"projects": {}, "recents": []}


def _replace_with_retry(src, dst, attempts=5, delay=0.2):
    """os.replace 带 backoff 重试：Windows 共享冲突 flaky 在案（B5b 2 例；
    _cloud_llm_vision 实测 6 线程压 replace 全数 PermissionError），单次即弃
    会把整次索引写入打丢。attempts 用尽仍失败则抛出。"""
    import time
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))


def _save_index(index) -> None:
    """index.json 落盘（C-A7）：_save_lock 互斥 + tmp→os.replace 原子写。

    此前裸 open("w")——写中断留半截 JSON（下次 _load_index 走重建路径），
    且并发归档存在 read-modify-write 丢失更新窗口。锁等待超时大声失败
    （绝不绕锁写入，_save_lock 纪律），由调用方记日志降级。
    """
    from _save_lock import acquire_save_lock, release_save_lock
    lock_dir = os.path.dirname(INDEX_PATH)
    os.makedirs(lock_dir, exist_ok=True)
    fd = acquire_save_lock(lock_dir, lock_name=".index_save_lock")
    if fd is None:
        raise TimeoutError(f"index.json 写锁获取超时（{lock_dir}/.index_save_lock）")
    try:
        tmp_path = INDEX_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        _replace_with_retry(tmp_path, INDEX_PATH)
    finally:
        release_save_lock(lock_dir, fd, lock_name=".index_save_lock")


def _update_index(project_key: str, display_name: str, filename: str) -> None:
    """向 index.json 追加资产记录。project_key 形如 _knowledge/clients/{客户}/refs 或 _knowledge/refs。"""
    index = _load_index()
    if project_key not in index["projects"]:
        index["projects"][project_key] = {"name": display_name, "assets": []}
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
    try:
        _save_index(index)
    except TimeoutError as e:
        # 文件已移动但索引登记失败：大声记日志，不影响归档主流程（与既有 IO 容错同档）
        _log(f"FAIL {filename}: index.json 登记被跳过（{e}）")


def _log(msg: str) -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(LOG_DIR, f"archive_auto_{day}.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass
    print(f"[归档] {msg}")


def _move_into(refs_dir: str, filenames: list, src_dir: str) -> dict:
    """移动一组文件到 refs_dir 并更新 index。

    返回 {"moved": [(原名, 落盘实名)], "skipped": [(name, reason)]}。
    dst 撞名时自动加时间戳后缀——moved 必须记 (原名, 实名) 二元组：
    销账（mark_done）用原名（登记表只存原名），索引/日志/返回值用实名
    （盘上是实名），否则重复归档 + 溯源断链（C-A6）。
    """
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
            moved.append((fn, os.path.basename(dst)))
        except OSError as e:
            _log(f"FAIL {fn}: 移动失败（{e}）")
            skipped.append((fn, f"移动失败: {e}"))
    return {"moved": moved, "skipped": skipped}


def archive_to_client(client_name: str, filenames: list, src_dir: str) -> dict:
    """把文件移入 _knowledge/clients/{client}/refs/ 并更新 index。

    防线：客户目录不存在 → 拒绝移动（禁止自动创建客户，走客户入库流程）。
    """
    clients_root = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if not os.path.isdir(os.path.join(clients_root, client_name)):
        _log(f"REFUSE {client_name}: 客户目录不存在，拒绝自动创建（走客户入库流程）")
        return {"moved": [], "renamed": {}, "skipped": [
            (fn, "客户目录不存在，拒绝自动创建（走客户入库流程）") for fn in filenames]}
    outcome = _move_into(
        os.path.join(clients_root, client_name, "refs"), filenames, src_dir)
    key = f"_knowledge/clients/{client_name}/refs"
    for orig, actual in outcome["moved"]:
        _update_index(key, client_name, actual)  # C-A6：索引记实名
        if actual != orig:
            _log(f"OK {orig} 重名改名 -> {key}/{actual}")
        else:
            _log(f"OK {orig} -> {key}/")
    return {
        "moved": [actual for _, actual in outcome["moved"]],   # 实名
        "renamed": {orig: actual for orig, actual in outcome["moved"]
                    if actual != orig},
        "skipped": outcome["skipped"],
    }


def archive_to_general(filenames: list, src_dir: str) -> dict:
    """把文件移入 _knowledge/refs/（通用参考库）并更新 index。"""
    refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "refs")
    outcome = _move_into(refs_dir, filenames, src_dir)
    for orig, actual in outcome["moved"]:
        _update_index("_knowledge/refs", GENERAL_REFS_KEY, actual)  # C-A6：索引记实名
        if actual != orig:
            _log(f"OK {orig} 重名改名 -> _knowledge/refs/{actual}")
        else:
            _log(f"OK {orig} -> _knowledge/refs/")
    return {
        "moved": [actual for _, actual in outcome["moved"]],   # 实名
        "renamed": {orig: actual for orig, actual in outcome["moved"]
                    if actual != orig},
        "skipped": outcome["skipped"],
    }


def _locate_in_inbox(inbox: str, fn: str) -> str:
    """登记消费的源定位：inbox 根优先，其次 _pending/YYYY-MM/（sweep 先行收纳后的常规落点）。

    登记表只存 basename，sweep 在 session-start 就会把未登记文件收进 _pending，
    消费时必须两处都找；找不到返回 inbox 根，由 _move_into 报「源文件不存在」保持旧行为。
    """
    if os.path.isfile(os.path.join(inbox, fn)):
        return inbox
    pending_root = os.path.join(inbox, "_pending")
    if os.path.isdir(pending_root):
        for month in sorted(os.listdir(pending_root), reverse=True):
            if os.path.isfile(os.path.join(pending_root, month, fn)):
                return os.path.join(pending_root, month)
    return inbox


def auto_archive(client_name: str) -> dict:
    """save 时自动归档（对话结束协议联动）。

    顺序：①消费登记表（client 匹配项 + general 全部）→ ②sweep 未登记文件进中转区 → ③报告。
    登记表损坏 → 整体降级只报告（不动文件、不 sweep）。
    返回 {"archived", "pending_review", "ignored", "reason", "swept", "unregistered_hint"}。
    """
    result = {"archived": [], "pending_review": [], "ignored": [],
              "reason": "", "swept": [], "unregistered_hint": []}
    try:
        inbox = os.path.join(SCRIPT_DIR, "inbox")
        if not os.path.isdir(inbox):
            result["reason"] = "inbox 不存在"
            return result

        all_pending = _reg.pending_entries()          # load（同时刷新损坏标志）
        if _reg.is_corrupt():
            result["reason"] = "登记表损坏，降级为只报告不移动"
            return result
        client_entries = [e["file"] for e in all_pending
                          if e.get("dest") == "client" and e.get("client") == client_name]
        general_entries = [e["file"] for e in all_pending if e.get("dest") == "general"]
        result["unregistered_hint"] = [e["file"] for e in all_pending
                                       if e.get("dest") == "client"
                                       and e.get("client") != client_name]
        result["ignored"] = [fn for fn in client_entries + general_entries
                             if fn.lower().endswith(FORBIDDEN_IN_INBOX_EXTS)]
        client_entries = [fn for fn in client_entries if fn not in result["ignored"]]
        general_entries = [fn for fn in general_entries if fn not in result["ignored"]]

        # ① 消费登记表（按实际所在目录分组移动：inbox 根 / _pending/**）
        def _consume(entries, mover):
            outcome = {"moved": [], "renamed": {}, "skipped": []}
            by_src = {}
            for fn in entries:
                by_src.setdefault(_locate_in_inbox(inbox, fn), []).append(fn)
            for src_dir, names in by_src.items():
                r = mover(names, src_dir)
                outcome["moved"] += r["moved"]
                outcome["renamed"].update(r.get("renamed", {}))
                outcome["skipped"] += r["skipped"]
            return outcome

        outcome_c = (_consume(client_entries,
                              lambda names, src: archive_to_client(client_name, names, src))
                     if client_entries else {"moved": [], "renamed": {}, "skipped": []})
        outcome_g = (_consume(general_entries, archive_to_general)
                     if general_entries else {"moved": [], "renamed": {}, "skipped": []})
        # C-A6：moved 记实名，销账反查回原名（登记表只存原名）；
        # archived 返回实名（盘上真实文件名），索引/日志同实名。
        renamed_inv = {actual: orig
                       for renamed in (outcome_c.get("renamed", {}), outcome_g.get("renamed", {}))
                       for orig, actual in renamed.items()}
        result["archived"] = outcome_c["moved"] + outcome_g["moved"]
        for name in result["archived"]:
            _reg.mark_done(renamed_inv.get(name, name))
        result["pending_review"] = [f"{n}: {r}" for n, r in outcome_c["skipped"] + outcome_g["skipped"]]

        # ② save 即巡：剩余未登记文件收进中转区（会话结束 inbox 根目录必空）
        import _inbox_scan
        swept = _inbox_scan.sweep_pending(SCRIPT_DIR)
        result["swept"] = swept.get("swept", [])
        if swept.get("errors"):
            result["pending_review"] += swept["errors"]

        result["reason"] = f"归档 {len(result['archived'])}，sweep {len(result['swept'])}"
    except Exception as e:
        result["reason"] = f"自动归档异常（不影响 save 主流程）: {e}"
        _log(f"ERROR auto_archive: {e}")
    return result
