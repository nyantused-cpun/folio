# -*- coding: utf-8 -*-
"""容量预算 *_WARN 常量单一事实源（S4 棘轮处置，2026-09-07，自 schema.py 成簇拆出）。

schema.py 与 graphics.md §2 的容量预算镜像共用本模块的数字。C-1 终态双层制
（D7-2 裁决，S10-3d 落地）：graphics.md §2 = **写作预算层**（standard 密度档，
= 告警阈值-1）；本模块 `*_WARN` = **机检告警层**（warning 级不阻断）。深度三档：
dense=告警阈值、standard=阈值-1、airy=阈值-2（规则成文于 graphics.md §2 注记）。
改任一侧必须同步另一侧，tests/test_graphics_capacity_sync.py 做 grep 对账
（写作预算断言=常量-1，机检告警断言=常量）。schema.py 经 import 暴露同名常量，
既有引用面（schema.PAGE_ELEMENTS_WARN / from _renderer.schema import ...）不变。
"""
# 页面级容量上限（§七 2.5 第一级 源头限量，行业依据 §11.2 第 4 条：
# Gamma 的 brief/medium/detailed 文字量旋钮——超量页面生成前亮灯）。
# 阈值依据：6 个基线 spec 实测单页最多 9 个元素（fuwu_jianyishu s4）、
# 单元素文本最长 1091 字（summary p03），各留约 20% 余量取整；
# 基线页均不触发（warning 只进 report，不改产出）。
PAGE_ELEMENTS_WARN = 10
ELEMENT_TEXT_WARN = 1300

# diagram 数量型 subtype 容量阈值（间距体系 v1 §六 5，warning 级别不阻断）。
# 阈值取 docs/diagram_hardcode_audit_2026-07-20 §3 实测越界数据 -1 的安全线：
# swimlane ≥5 道 bottom 909 / cross_system ≥5 行 724 / capability_map 多
# section 953 / timeline vertical ≥8 卡 1045 / biz_capability_tree 3 组×5 子
# 822 / decision ≥7 步菱形互压 / timeline horizontal ≥9 卡短标签溢出。
SWIMLANE_LANES_WARN = 4
CROSS_SYSTEM_ROWS_WARN = 4
DECISION_STEPS_WARN = 6
TIMELINE_VERTICAL_CARDS_WARN = 7
TIMELINE_HORIZONTAL_CARDS_WARN = 8
MSG_TASKS_WARN = 10             # B-7 甘特任务行数上限
CAPABILITY_MAP_SECTIONS_WARN = 3
BCT_CHILDREN_WARN = 12
# graphics.md §2 容量预算镜像（C-F1，2026-09-07）：本模块是 *_WARN 常量单一事实源
# （C-1 终态双层制见模块 docstring：写作预算=graphics.md §2，差 1 档缓冲，D7-2），
# verify 链与写作侧共用同一组数字。
CROSS_SYSTEM_SYSTEMS_WARN = 6   # flow/cross_system ≤6 个系统列
INFRA_ZONES_WARN = 4            # architecture/infra ≤4 zone
INFRA_ZONE_NODES_WARN = 4       # architecture/infra 每 zone ≤4 节点

# v2 元素/版式容量阈值（warning 级，§5.3/§6/§10 检查 6）
HERO_STATS_WARN = 4
KPI_CARDS_WARN = 4
INFO_CARDS_MAX_WARN = 4     # info_cards 2-4 联
INFO_CARDS_MIN_WARN = 2
PAIN_CARDS_WARN = 9
EVIDENCE_LEDGER_ROWS_WARN = 12   # B-3 证据台账行数上限
RISK_REGISTER_ROWS_WARN = 12     # B-4 风险登记行数上限
RACI_TASKS_WARN = 12             # B-5 RACI 任务行数上限
DECISION_OPTIONS_WARN = 4        # B-6 决策方案数上限
LOGO_WALL_CELLS_WARN = 8         # S8-B logo_wall 网格上限（泛微实证收尾标配）
# C-1 终态互标（D7-2，S10-3d）：写作预算=graphics.md §2（差 1 档缓冲）——
# 本行是机检告警阈值（dense 档），写作预算（standard 档）=本值-1
P07_TABLE_ROWS_WARN = 12
TIMELINE_VERTICAL_CARDS_WARN = 7     # 写作预算=graphics.md §2「≤6 卡」（差 1 档缓冲，D7-2）
TIMELINE_HORIZONTAL_CARDS_WARN = 8   # 写作预算=graphics.md §2「≤7 个 milestones」（差 1 档缓冲，D7-2）
FLOW_ROWS_TOTAL_WARN = 8    # flow_rows 总行数（含 arrow 行）
FLOW_ROWS_CARDS_WARN = 6    # flow_rows 单行卡数
