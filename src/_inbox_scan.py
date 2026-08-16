# -*- coding: utf-8 -*-
"""_inbox_scan.py - Inbox 定期扫描（检视+报告，不亲自移动）。

职责：
1. 扫描 inbox/ 根目录 + _uncategorized/ 子目录
2. 分类：A 高置信（与 refs/ 同名同大小 → 自动归档 _trash/）
         B/C/D 低置信（仅入清单，等人工 review）
3. 写双产物报告：.md（AI 注入用）+ .json（审计用）
4. 时间窗/冷却期判断（供 Hook 调用）

设计原则：
- 只检视+报告，不直接 shutil.move（归档动作复用 _cli.py classify）
- 报告落地到 inbox/_scan_reports/
- 时间戳写到 .trae/logs/last_inbox_scan.txt（纯文本 ISO）
- 失败兜底：所有 IO 异常吞掉，返回空报告，Hook 不阻塞

调用方式：
- CLI: python _cli.py inbox-scan [--dry-run] [--force]
- Hook: session_start.py 在时间窗内 Popen('python _cli.py inbox-scan')
"""
import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
INBOX_DIR = os.path.join(SCRIPT_DIR, "inbox")
UNCATEGORIZED_DIR = os.path.join(INBOX_DIR, "_uncategorized")
REPORTS_DIR = os.path.join(INBOX_DIR, "_scan_reports")
LAST_SCAN_LOG = os.path.join(SCRIPT_DIR, ".trae", "logs", "last_inbox_scan.txt")
FAILURE_LOG = os.path.join(SCRIPT_DIR, ".trae", "logs", "inbox_scan_failures.log")
DEFAULT_TRASH_DIR = "_trash"

# 时间窗：22:00-22:30（30 分钟容差，含头不含尾）
WINDOW_START_HOUR = 22
WINDOW_START_MIN = 0
WINDOW_END_HOUR = 22
WINDOW_END_MIN = 30

# 冷却期：22 小时（防一天内重复触发）
COOLDOWN_HOURS = 22


# ---------- 数据结构 ----------

@dataclass
class FileCategory:
    """单个文件的分类结果。"""
    filename: str
    location: str  # "root" 或 "uncategorized"
    size_bytes: int
    category: str   # "A_repeat" / "B_material" / "C_output" / "D_script"
    reason: str


@dataclass
class ScanReport:
    """一次扫描的完整结果。"""
    timestamp: str
    auto_candidate: List[FileCategory] = field(default_factory=list)
    pending_review: List[FileCategory] = field(default_factory=list)
    archived: List[FileCategory] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "auto_candidate": [asdict(f) for f in self.auto_candidate],
            "pending_review": [asdict(f) for f in self.pending_review],
            "archived": [asdict(f) for f in self.archived],
            "errors": self.errors,
        }


# ---------- 工具函数 ----------

def _now() -> datetime:
    """当前本地时间。设计为可被 monkeypatch 替换。"""
    return datetime.now()


def _now_in_window(dt: Optional[datetime] = None) -> bool:
    """判断给定（或当前）时间是否在 22:00-22:30 窗口内。"""
    if dt is None:
        dt = _now()
    minutes = dt.hour * 60 + dt.minute
    start = WINDOW_START_HOUR * 60 + WINDOW_START_MIN
    end = WINDOW_END_HOUR * 60 + WINDOW_END_MIN
    return start <= minutes < end


def _read_last_scan(project_dir: str) -> Optional[datetime]:
    """读上次扫描时间戳；文件不存在返回 None。"""
    path = os.path.join(project_dir, ".trae", "logs", "last_inbox_scan.txt")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return datetime.fromisoformat(f.read().strip())
    except (ValueError, OSError):
        return None


def _write_last_scan(project_dir: str, dt: datetime) -> None:
    """原子写时间戳：先写 .tmp 再 os.replace，避免半写状态。"""
    log_dir = os.path.join(project_dir, ".trae", "logs")
    os.makedirs(log_dir, exist_ok=True)
    final = os.path.join(log_dir, "last_inbox_scan.txt")
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dt.isoformat())
    os.replace(tmp, final)


def _cooldown_elapsed(project_dir: str, hours: int = COOLDOWN_HOURS) -> bool:
    """距上次扫描是否超过 hours 小时。无记录返回 True（首次部署场景）。"""
    last = _read_last_scan(project_dir)
    if last is None:
        return True
    return (_now() - last) >= timedelta(hours=hours)


def _has_inbox_files(project_dir: str) -> bool:
    """inbox/ 根目录或 _uncategorized/ 至少各有一个文件。"""
    inbox = os.path.join(project_dir, "inbox")
    if not os.path.exists(inbox):
        return False
    # 根目录
    for f in os.listdir(inbox):
        if os.path.isfile(os.path.join(inbox, f)):
            return True
    # _uncategorized/
    unc = os.path.join(inbox, "_uncategorized")
    if os.path.exists(unc):
        for f in os.listdir(unc):
            if os.path.isfile(os.path.join(unc, f)):
                return True
    return False


def _log_failure(project_dir: str, msg: str) -> None:
    """失败兜底：写 .trae/logs/inbox_scan_failures.log。"""
    try:
        os.makedirs(os.path.dirname(FAILURE_LOG), exist_ok=True)
        with open(FAILURE_LOG, "a", encoding="utf-8") as f:
            ts = _now().isoformat(timespec="seconds")
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass  # 兜底中的兜底


# ---------- 核心：分类 ----------

# 文件类型分类（参考上次会话定的 4 类策略）
MATERIAL_EXTS = {".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".txt", ".md"}
OUTPUT_EXTS = {".html", ".yml", ".yaml", ".json"}
SCRIPT_EXTS = {".py", ".sh", ".ps1", ".bat"}


def _categorize_ext(filename: str) -> str:
    """按扩展名分类：B 客户材料 / C 客户产出 / D 残留脚本 / unknown。"""
    ext = Path(filename).suffix.lower()
    if ext in MATERIAL_EXTS:
        return "B_material"
    if ext in OUTPUT_EXTS:
        return "C_output"
    if ext in SCRIPT_EXTS:
        return "D_script"
    return "unknown"


def _list_inbox_files(project_dir: str):
    """列出 inbox/ 根目录 + _uncategorized/ 下的所有文件。"""
    inbox = os.path.join(project_dir, "inbox")
    results = []
    if os.path.exists(inbox):
        for f in os.listdir(inbox):
            full = os.path.join(inbox, f)
            if os.path.isfile(full):
                results.append(("root", f, full))
    unc = os.path.join(inbox, "_uncategorized")
    if os.path.exists(unc):
        for f in os.listdir(unc):
            full = os.path.join(unc, f)
            if os.path.isfile(full):
                results.append(("uncategorized", f, full))
    return results


def _find_duplicate(project_dir: str, filename: str, size: int):
    """在 _knowledge/clients/*/refs/ 内查找同名文件，返回 (client_dir, size_or_None)。"""
    knowledge = os.path.join(project_dir, "_knowledge", "clients")
    if not os.path.exists(knowledge):
        return None
    for client in os.listdir(knowledge):
        refs = os.path.join(knowledge, client, "refs")
        candidate = os.path.join(refs, filename)
        if os.path.exists(candidate):
            try:
                cand_size = os.path.getsize(candidate)
                return (client, cand_size)
            except OSError:
                continue
    return None


def classify_inbox_files(project_dir: str) -> ScanReport:
    """扫描 + 分类，返回 ScanReport（不移动任何文件）。"""
    report = ScanReport(timestamp=_now().isoformat(timespec="seconds"))

    try:
        files = _list_inbox_files(project_dir)
        if not files:
            return report

        for location, filename, full_path in files:
            try:
                size = os.path.getsize(full_path)
            except OSError as e:
                report.errors.append(f"{filename}: stat 失败 - {e}")
                continue

            # 先查 A 类（重复）
            dup = _find_duplicate(project_dir, filename, size)
            if dup is not None:
                client, cand_size = dup
                if cand_size == size:
                    fc = FileCategory(
                        filename=filename,
                        location=location,
                        size_bytes=size,
                        category="A_repeat",
                        reason=f"refs/{client}/ 内有同名同大小文件",
                    )
                    report.auto_candidate.append(fc)
                    continue
                else:
                    reason = f"refs/{client}/ 内有同名但 size 不同（refs={cand_size}, inbox={size}），可能是新版本，请人工 review"
                    cat = "B_material"  # 暂按材料归类
                    fc = FileCategory(
                        filename=filename,
                        location=location,
                        size_bytes=size,
                        category=cat,
                        reason=reason,
                    )
                    report.pending_review.append(fc)
                    continue

            # B/C/D 按扩展名
            cat = _categorize_ext(filename)
            if cat == "unknown":
                reason = "未知扩展名，需人工判断（客户材料 / 产出 / 脚本 / 其他）"
            elif cat == "B_material":
                reason = "客户材料（按扩展名），需确认归属客户"
            elif cat == "C_output":
                reason = "客户产出（html/yml/json），需确认归属客户和版本"
            else:  # D_script
                reason = "残留脚本，应归档 _trash/ 或 _tools/，不属 inbox/"
            fc = FileCategory(
                filename=filename,
                location=location,
                size_bytes=size,
                category=cat,
                reason=reason,
            )
            report.pending_review.append(fc)

    except Exception as e:
        report.errors.append(f"扫描异常: {e}")
        _log_failure(project_dir, f"classify_inbox_files: {e}")

    return report


# ---------- 核心：归档动作 ----------

def archive_duplicate(report: ScanReport, project_dir: str, dry_run: bool = False) -> List[FileCategory]:
    """对 report.auto_candidate 执行归档（移入 _trash/）。返回已归档列表。"""
    archived = []
    trash_root = os.path.join(project_dir, DEFAULT_TRASH_DIR)
    inbox = os.path.join(project_dir, "inbox")

    for fc in report.auto_candidate:
        src_dir = inbox if fc.location == "root" else os.path.join(inbox, "_uncategorized")
        src = os.path.join(src_dir, fc.filename)
        if not os.path.exists(src):
            continue
        if dry_run:
            archived.append(fc)
            continue
        try:
            os.makedirs(trash_root, exist_ok=True)
            dst = os.path.join(trash_root, fc.filename)
            # 同名防覆盖：追加时间戳
            if os.path.exists(dst):
                base, ext = os.path.splitext(fc.filename)
                ts = _now().strftime("%Y%m%d_%H%M%S")
                dst = os.path.join(trash_root, f"{base}_{ts}{ext}")
            shutil.move(src, dst)
            fc.reason += f" → 已归档 {os.path.relpath(dst, project_dir)}"
            archived.append(fc)
        except OSError as e:
            report.errors.append(f"{fc.filename}: 归档失败 - {e}")
            _log_failure(project_dir, f"archive_duplicate: {fc.filename}: {e}")
    return archived


# ---------- 核心：报告写入 ----------

def write_report(report: ScanReport, project_dir: str) -> tuple:
    """写双产物报告（.md + .json）到 inbox/_scan_reports/。返回 (md_path, json_path)。"""
    reports_dir = os.path.join(project_dir, "inbox", "_scan_reports")
    os.makedirs(reports_dir, exist_ok=True)

    ts = report.timestamp.replace(":", "").replace("-", "")
    # YYYYMMDDTHHMMSS -> YYYYMMDD_HHMMSS
    if "T" in ts:
        date_part, time_part = ts.split("T", 1)
        stamp = f"{date_part}_{time_part}"
    else:
        stamp = ts

    md_path = os.path.join(reports_dir, f"{stamp}.md")
    json_path = os.path.join(reports_dir, f"{stamp}.json")

    # .md
    md_lines = [
        f"# Inbox 扫描报告 @ {report.timestamp}",
        "",
        f"## 自动归档（A 类·高置信）- {len(report.archived)} 个",
    ]
    if report.archived:
        for fc in report.archived:
            md_lines.append(f"- `{fc.filename}` ({fc.size_bytes} B) - {fc.reason}")
    else:
        md_lines.append("- （无）")
    md_lines.append("")
    md_lines.append(f"## 待人工 review（B/C/D 类）- {len(report.pending_review)} 个")
    if report.pending_review:
        # 按 category 分组
        groups = {}
        for fc in report.pending_review:
            groups.setdefault(fc.category, []).append(fc)
        cat_labels = {
            "B_material": "**B 客户材料**",
            "C_output": "**C 客户产出**",
            "D_script": "**D 残留脚本**",
            "unknown": "**unknown**",
        }
        for cat in ["B_material", "C_output", "D_script", "unknown"]:
            if cat in groups:
                md_lines.append(f"- {cat_labels[cat]}: {len(groups[cat])} 个")
                for fc in groups[cat]:
                    loc = "(uncategorized/)" if fc.location == "uncategorized" else ""
                    md_lines.append(f"  - `{fc.filename}` {loc}- {fc.reason}")
    else:
        md_lines.append("- （无）")
    if report.errors:
        md_lines.append("")
        md_lines.append(f"## 错误 - {len(report.errors)} 个")
        for e in report.errors:
            md_lines.append(f"- {e}")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # .json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    return md_path, json_path


# ---------- Hook 集成判断 ----------

def _should_trigger_inbox_scan(task_mode: str, project_dir: str) -> bool:
    """4 条件全满足才返回 True：
    1. task_mode != "engineering"
    2. inbox/ 非空（含 _uncategorized/）
    3. 当前时间在 22:00-22:30
    4. 距上次扫描 ≥ 22 小时
    """
    if task_mode == "engineering":
        return False
    if not _has_inbox_files(project_dir):
        return False
    if not _now_in_window():
        return False
    if not _cooldown_elapsed(project_dir):
        return False
    return True


# ---------- 延迟导入避免循环 ----------

from datetime import timedelta  # noqa: E402  放最后避免循环


# ---------- CLI 入口 ----------

def main_entry(project_dir: str = None, dry_run: bool = False, force: bool = False) -> ScanReport:
    """CLI 入口：扫 + 归档 + 写报告 + 更新时间戳。

    Args:
        project_dir: 项目根目录（None=当前 cwd）
        dry_run: True=不移动、不写时间戳。纯只读，跳过时间窗/冷却期判断
        force: True=忽略时间窗/冷却期但仍执行归档（排障用）
    """
    project_dir = project_dir or SCRIPT_DIR
    report = classify_inbox_files(project_dir)

    # dry_run 永远跑（纯只读，无副作用）
    # 否则检查 4 条件；Hook 触发时间窗内、force=true、或 manual 调试时跑
    if not dry_run and not force:
        if not _should_trigger_inbox_scan("presales", project_dir):
            # 不满足条件 → 早退（不归档、不写报告、不更新时间戳）
            return report

    archived = archive_duplicate(report, project_dir, dry_run=dry_run)
    report.archived = archived

    if report.auto_candidate or report.pending_review:
        try:
            write_report(report, project_dir)
        except OSError as e:
            report.errors.append(f"写报告失败: {e}")
            _log_failure(project_dir, f"write_report: {e}")

    if not dry_run and archived:
        try:
            _write_last_scan(project_dir, _now())
        except OSError as e:
            _log_failure(project_dir, f"write_last_scan: {e}")

    return report