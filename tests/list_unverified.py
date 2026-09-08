# -*- coding: utf-8 -*-
"""列出 output/ 下所有无 verify 记录的产出物（只读文件系统，不 import 内部模块）。

对照 .folio/logs/task_history.json 的 verify 记录，找出 audit 会报的全部未验证文件。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
HISTORY = os.path.join(ROOT, ".folio", "logs", "task_history.json")

SKIP_DIRS = {".versions", "_archive", "_assets", "_vision_tmp", "_baseline_work"}
SKIP_PATTERNS = (".bak", "_backup", "_bak")
EXTS = (".html", ".htm", ".pptx", ".docx", ".xlsx")


def main():
    verified = set()
    with open(HISTORY, "r", encoding="utf-8") as f:
        history = json.load(f)
    tasks = history.get("tasks", []) if isinstance(history, dict) else (
        history if isinstance(history, list) else [])
    for t in tasks:
        if isinstance(t, dict):
            verified.update((t.get("verify") or {}).keys())

    unverified = []
    for root, dirs, files in os.walk(OUTPUT_DIR):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.startswith("portal-")
                   and not d.endswith("_audit")]
        for fname in files:
            if fname.startswith(".") or fname.startswith("~$"):
                continue
            if any(p in fname for p in SKIP_PATTERNS):
                continue
            if os.path.splitext(fname)[1].lower() not in EXTS:
                continue
            fpath = os.path.join(root, fname)
            norm = os.path.normpath(fpath)
            rel = os.path.relpath(fpath, ROOT)
            found = False
            for v in verified:
                vn = os.path.normpath(v)
                if (os.path.normcase(vn) == os.path.normcase(norm)
                        or os.path.normcase(vn) == os.path.normcase(rel)):
                    found = True
                    break
            if not found:
                unverified.append(rel)

    print(f"未验证产出物: {len(unverified)}")
    for u in unverified:
        print("UNVERIFIED:", u)


if __name__ == "__main__":
    main()
