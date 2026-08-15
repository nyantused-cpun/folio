# -*- coding: utf-8 -*-
"""间距令牌单一源（间距体系 v1 第一阶段，docs/spacing_design_v1_2026-07-20 §3.1）。

1280×720 画布（96px/in）下所有坐标/尺寸只能是令牌或令牌倍数。
数值取自 Carbon（2/4/8 倍数，13 级）与 Atlassian（0–8 微间距、12–24 容器、
32+ 布局）的交叉共识，按画布密度收敛为 6 档（设计文档 §3.1 令牌表）。
后续要调间距，改本文件一处全端传播。

消费方：
- _pptd_gen（cards/phases/pullquote 内边距折算、堆叠间距、页出口坐标吸附）
- _renderer/diagram/pptd_emit（text() 内边距折算、shape/text/connector 出口吸附）
- _layout_lint（网格相关容差）
"""

INSET_X = 10   # 形状内文字左右内边距（≈OOXML 默认 0.1in @96px/in）
INSET_Y = 6    # 形状内文字上下内边距（≈OOXML 默认 0.05in）
GAP_XS = 4     # 徽章/图标与文字、chip 内间距
GAP_SM = 8     # 卡片内 title→body、节点内元素间
GAP_MD = 12    # 元素组内堆叠间距
GAP_LG = 24    # 卡片/分区间距
GRID = 4       # 所有坐标吸附 4px 网格（对齐自动化，§3.3）


def snap(v):
    """坐标吸附：round(v / GRID) * GRID。发射器输出 bounds 一律过此（§3.3）。"""
    return round(v / GRID) * GRID
