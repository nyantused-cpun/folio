# -*- coding: utf-8 -*-
"""_inbox_scan.py - Inbox 兜底 sweep（session-start / save 双挂点）。

职责（spec 第 3 节，2026-09-01 改造）：
1. 未登记文件（登记表无 pending 记录）从 inbox/ 根目录收进 inbox/_pending/YYYY-MM/
2. 刷新 inbox/_pending/_todo.md 催办清单（strong 命中给建议不裁决；>30 天置顶）
3. _uncategorized/ 一次性搬入 _pending/legacy-uncategorized/ 后退役

设计原则：
- 不猜归属：sweep 只移进中转区，永不进客户/通用库
- 登记表 pending 文件不动（归 save 流程消费）
- 幂等、廉价；IO 异常吞掉记日志，绝不阻塞调用方（hook / save）
- `_` 前缀系统文件不扫
"""
import os
import shutil
from datetime import datetime

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR
INBOX_DIR = os.path.join(SCRIPT_DIR, "inbox")
PENDING_DIRNAME = "_pending"
FAILURE_LOG = os.path.join(SCRIPT_DIR, ".folio", "logs", "inbox_scan_failures.log")
TODO_CUTOFF_DAYS = 30
# inbox 禁止残留的类型（与 _archive_auto.FORBIDDEN_IN_INBOX_EXTS 一致）：sweep 不碰，留给 classify 归档
FORBIDDEN_EXTS = (".py", ".log", ".pyc", ".tmp", ".bak")

_registry = None
_config_cache = None


def _now() -> datetime:
    """当前本地时间。设计为可被 monkeypatch 替换。"""
    return datetime.now()


def _get_registry():
    """延迟导入登记表模块，避免循环依赖。"""
    global _registry
    if _registry is None:
        import _inbox_registry
        _registry = _inbox_registry
    return _registry


def _log_failure(project_dir: str, msg: str) -> None:
    """失败兜底：写 .folio/logs/inbox_scan_failures.log。"""
    try:
        log_dir = os.path.join(project_dir, ".folio", "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(FAILURE_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{_now().isoformat(timespec='seconds')}] {msg}\n")
    except OSError:
        pass  # 兜底中的兜底


def _find_duplicate(project_dir: str, filename: str, size: int):
    """在 _knowledge/clients/*/refs/ 内查找同名文件，返回 (client_dir, size_or_None)。

    #48/D2：客户枚举收口 _paths.list_client_dirs，_internal/ 内部账本目录不参与查重。
    """
    knowledge = os.path.join(project_dir, "_knowledge", "clients")
    if not os.path.exists(knowledge):
        return None
    from _paths import list_client_dirs
    for client in list_client_dirs(clients_dir=knowledge):
        refs = os.path.join(knowledge, client, "refs")
        candidate = os.path.join(refs, filename)
        if os.path.exists(candidate):
            try:
                cand_size = os.path.getsize(candidate)
                return (client, cand_size)
            except OSError:
                continue
    return None


def _load_classify_config():
    """strong 建议用的 classify 配置（进程内缓存一次）。"""
    global _config_cache
    if _config_cache is None:
        try:
            import _classify
            _config_cache = _classify.load_config()
        except Exception:
            _config_cache = {}
    return _config_cache


def strong_hint(project_dir: str, filename: str) -> str:
    """strong 路由命中 → '建议归 X（命中词: ...）'；否则 ''。只建议不裁决。"""
    try:
        import _classify
        for route in _load_classify_config().get("routes", []):
            for rule in route.get("rules", []):
                if rule.get("strong") and _classify.match_file(filename, [rule]):
                    words = ",".join(rule.get("keyword", []))
                    return f"建议归 {route['name']}（命中词: {words}）"
    except Exception as e:  # 建议失败不阻塞 sweep
        _log_failure(project_dir, f"strong_hint: {e}")
    return ""


def _pending_month_dir(project_dir: str, create: bool = True) -> str:
    """_pending/YYYY-MM/ 月目录路径。create=False 时只算路径不落盘（dry_run 用）。"""
    d = os.path.join(project_dir, "inbox", PENDING_DIRNAME, _now().strftime("%Y-%m"))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def sweep_pending(project_dir: str, dry_run: bool = False) -> dict:
    """把 inbox 根目录未登记文件收进 _pending/YYYY-MM/，刷新 todo。幂等。

    返回 {"swept": [{"file","dest","reason"}], "todo_path": str, "errors": [str]}
    """
    result = {"swept": [], "todo_path": "", "errors": []}
    try:
        reg = _get_registry()
        pending_files = {e["file"] for e in reg.pending_entries()}
        inbox = os.path.join(project_dir, "inbox")
        if not os.path.isdir(inbox):
            return result
        for fn in sorted(os.listdir(inbox)):
            full = os.path.join(inbox, fn)
            if (not os.path.isfile(full) or fn.startswith("_")
                    or fn.lower().endswith(FORBIDDEN_EXTS) or fn in pending_files):
                continue  # 子目录 / 系统文件 / 脚本类 / 已登记文件不动
            dest_dir = _pending_month_dir(project_dir, create=not dry_run)
            dst = os.path.join(dest_dir, fn)
            if os.path.exists(dst):
                base, ext = os.path.splitext(fn)
                dst = os.path.join(dest_dir, f"{base}_{_now().strftime('%Y%m%d_%H%M%S')}{ext}")
            reason = "未登记文件，归属待定"
            try:
                size = os.path.getsize(full)
                dup = _find_duplicate(project_dir, fn, size)
                if dup and dup[1] == size:
                    reason = f"疑似重复（与 clients/{dup[0]}/refs 同名同大小）"
            except OSError:
                pass
            hint = strong_hint(project_dir, fn)
            if hint:
                reason += f"；{hint}"
            if dry_run:
                result["swept"].append({
                    "file": fn,
                    "dest": os.path.relpath(dst, project_dir),
                    "reason": reason,
                })
                continue
            try:
                shutil.move(full, dst)
                result["swept"].append({
                    "file": fn,
                    "dest": os.path.relpath(dst, project_dir),
                    "reason": reason,
                })
            except OSError as e:
                result["errors"].append(f"{fn}: 移动失败 - {e}")  # 文件留原地
                _log_failure(project_dir, f"sweep_pending: {fn}: {e}")
        if dry_run:
            # P3（2026-09-06）：dry_run 全路径只读——不重写 _todo.md，只报将写入的路径
            result["todo_path"] = os.path.join(
                project_dir, "inbox", PENDING_DIRNAME, "_todo.md")
            return result
        result["todo_path"] = refresh_todo(project_dir)
    except Exception as e:
        result["errors"].append(f"sweep 异常: {e}")
        _log_failure(project_dir, f"sweep_pending: {e}")
    return result


def migrate_uncategorized(project_dir: str) -> dict:
    """_uncategorized/ 一次性搬入 _pending/legacy-uncategorized/ 后退役。幂等。"""
    unc = os.path.join(project_dir, "inbox", "_uncategorized")
    target = os.path.join(project_dir, "inbox", PENDING_DIRNAME, "legacy-uncategorized")
    moved = 0
    if os.path.isdir(unc):
        os.makedirs(target, exist_ok=True)
        for fn in sorted(os.listdir(unc)):
            try:
                shutil.move(os.path.join(unc, fn), os.path.join(target, fn))
                moved += 1
            except OSError as e:
                _log_failure(project_dir, f"migrate_uncategorized: {fn}: {e}")
        try:
            if not os.listdir(unc):
                os.rmdir(unc)
        except OSError as e:
            _log_failure(project_dir, f"migrate_uncategorized: rmdir: {e}")
    return {"moved": moved, "target": os.path.relpath(target, project_dir)}


def _render_todo_lines(project_dir: str) -> list:
    """渲染 _todo.md 行清单（纯读取不写盘，refresh_todo 与 dry_run 预览共用）。

    P3（2026-09-06）：_pending 根目录散落文件（未落月目录）同样纳入催办清单，
    此前只扫月目录，根目录文件永不进清单。
    """
    pending_root = os.path.join(project_dir, "inbox", PENDING_DIRNAME)
    lines = [
        "# Inbox 待定归属清单",
        "",
        "> 处理方式：`python _cli.py pending-archive <文件> --dest client --client 客户名`"
        " 或 `--dest general`",
        "",
    ]
    cutoff = _now().timestamp() - TODO_CUTOFF_DAYS * 86400
    top, rest = [], []

    def _collect(label, full):
        try:
            age = os.path.getmtime(full)
        except OSError:
            age = _now().timestamp()
        hint = strong_hint(project_dir, os.path.basename(label))
        item = f"- `{label}`{('；' + hint) if hint else ''}"
        (top if age < cutoff else rest).append(item)

    if os.path.isdir(pending_root):
        for month in sorted(os.listdir(pending_root)):
            mdir = os.path.join(pending_root, month)
            if month.startswith("_") or not os.path.isdir(mdir):
                continue
            for fn in sorted(os.listdir(mdir)):
                _collect(f"{month}/{fn}", os.path.join(mdir, fn))
        for fn in sorted(os.listdir(pending_root)):
            full = os.path.join(pending_root, fn)
            if not fn.startswith("_") and os.path.isfile(full):
                _collect(fn, full)
    if top:
        lines += ["## ⚠ 超 30 天未定（置顶催办）"] + top + [""]
    lines += ["## 本期待定"] + (rest or ["- （无）"])
    return lines


def refresh_todo(project_dir: str) -> str:
    """重写 inbox/_pending/_todo.md：>30 天置顶，其余按月；含 strong 建议。返回路径。"""
    pending_root = os.path.join(project_dir, "inbox", PENDING_DIRNAME)
    os.makedirs(pending_root, exist_ok=True)
    todo = os.path.join(pending_root, "_todo.md")
    lines = _render_todo_lines(project_dir)
    try:
        with open(todo, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as e:
        _log_failure(project_dir, f"refresh_todo: {e}")
    return todo


def main_entry(project_dir: str = None, dry_run: bool = False, force: bool = False) -> dict:
    """CLI/Hook 入口：退役 _uncategorized + sweep 未登记文件（force 保留兼容，无窗口语义）。

    P3（2026-09-06）：dry_run 全路径只读——_uncategorized 迁移是真实移动，一并跳过。
    """
    project_dir = project_dir or SCRIPT_DIR
    mig = {"moved": 0, "target": ""} if dry_run else migrate_uncategorized(project_dir)
    swept = sweep_pending(project_dir, dry_run=dry_run)
    swept["migrated_uncategorized"] = mig["moved"]
    return swept
