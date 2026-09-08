# -*- coding: utf-8 -*-
"""audit --mode behavior 行为台账统计（C-A1 最小实现，观察级）。升级条件: 连续两季全绿且有消费方依赖 → 评估入门禁（需拍板；盘点#15）

独立小模块动因：_cli_audit 体量棘轮 cap 1395（只许拆小不许加码），
C-A1 落码把主模块顶破线，按拆分纪律外迁；_cli_audit 顶部 import 保持
`_cli_audit._audit_behavior` 引用面不变（tests monkeypatch 目标不迁移）。
"""

import datetime
import json
import os

from _cli_infra import SCRIPT_DIR


def _audit_behavior(history_path=None):
    """对话行为统计（只报不判，C-A1 最小实现）：task_history 行为台账聚合。

    历史缺陷（0907 计划 C-A1/Q3）：argparse choices 与 TECH_SPEC 宣称 behavior
    模式但 dispatch 无分支——选择该值落「未知审计模式」continue，all_ok 不变
    仍 exit 0（脱账实锤）。现接最小 handler：读 task_history.json 出行为统计。
    只报不判恒不 FAIL（对齐 debt/drift/cost 先例：统计报告不是门禁）；
    数据源缺失降级标注；解析失败才 FAIL（损坏是真问题）。不并入 --mode all。
    history_path 参数供单测注入 tmp 文件（audit 测试封闭化先例）。
    """
    if history_path is None:
        history_path = os.path.join(SCRIPT_DIR, ".folio", "logs", "task_history.json")
    if not os.path.exists(history_path):
        print("ℹ task_history.json 数据源不存在（首次 save 后生成）")
        print("✓ 对话行为统计完成（只报不判恒不 FAIL）")
        return True
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"✗ task_history.json 解析失败: {e}")
        return False
    if isinstance(data, dict):
        tasks = data.get("tasks", [])
    elif isinstance(data, list):
        tasks = data
    else:
        tasks = None
    if not isinstance(tasks, list):
        print("✗ task_history.json 结构非法（顶层既非 list 也非 {tasks: list}）")
        return False
    month = datetime.datetime.now().strftime("%Y-%m")
    month_n = sum(1 for t in tasks
                  if isinstance(t, dict) and str(t.get("date", "")).startswith(month))
    projects = {}
    for t in tasks:
        if isinstance(t, dict):
            key = str(t.get("project") or "（未标项目）")
            projects[key] = projects.get(key, 0) + 1
    top = sorted(projects.items(), key=lambda kv: -kv[1])[:5]
    print(f"✓ 行为台账：{len(tasks)} 条任务（本月 {month_n} 条），覆盖 {len(projects)} 个项目")
    for proj, n in top:
        print(f"  - {proj}: {n} 条")
    print("✓ 对话行为统计完成（只报不判恒不 FAIL）")
    return True
