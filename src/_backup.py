# -*- coding: utf-8 -*-
"""生成前备份工具（P1-1 修复：从 _cli.py 抽出，断开 _session ↔ _cli 循环依赖）。

H1+H2: 生成前备份已存在的产出到 .bak + .versions/。
"""
import os
import shutil
from datetime import datetime


def backup_before_generate(file_path, max_versions=5):
    """H1+H2: 生成前备份已存在的产出到 .bak + .versions/。

    1. 如果 file_path 已存在，复制到 .bak（最近一版快照，可恢复）
    2. 同时复制到 .versions/ 目录（保留最近 N 版，默认 5）

    返回 .bak 路径或 None（文件不存在时）。
    """
    if not os.path.exists(file_path):
        return None

    # .bak 快照（最近一版，可恢复）
    bak_path = file_path + ".bak"
    shutil.copy2(file_path, bak_path)

    # H2: 版本快照目录
    versions_dir = os.path.join(os.path.dirname(file_path), ".versions")
    os.makedirs(versions_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(file_path)
    version_path = os.path.join(versions_dir, f"{basename}.{timestamp}")
    shutil.copy2(file_path, version_path)

    # 清理旧版本（保留最近 N 版）
    existing = sorted([f for f in os.listdir(versions_dir) if f.startswith(basename + ".")])
    if len(existing) > max_versions:
        for old in existing[:-max_versions]:
            old_path = os.path.join(versions_dir, old)
            try:
                os.remove(old_path)
            except Exception:
                pass

    print(f"  [备份] {basename} → .bak + .versions/")
    return bak_path
