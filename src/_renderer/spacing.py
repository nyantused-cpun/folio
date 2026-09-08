# -*- coding: utf-8 -*-
"""间距令牌单一源（间距体系 v1 第一阶段，docs/spacing_design_v1_2026-07-20 §3.1）。

1280×720 画布（96px/in）下所有坐标/尺寸只能是令牌或令牌倍数。
数值取自 Carbon（2/4/8 倍数，13 级）与 Atlassian（0–8 微间距、12–24 容器、
32+ 布局）的交叉共识，按画布密度收敛为 6 档（设计文档 §3.1 令牌表）。
后续要调间距，改本文件一处全端传播。

消费方：
- _pptd_gen（cards/phases/pullquote 内边距折算、堆叠间距、页出口坐标吸附）
- _renderer/diagram/pptd_emit（text() 内边距折算、shape/text/connector 出口吸附、
  est_text_w/estimate_text_height 经本文件单源 re-export，S6 2026-09-07 下移）
- _layout_lint（网格相关容差、text_overflow 贴线豁免口径）
- _pptd_parts（硬防线裁剪线，经别名 _CONTENT_Y_MAX re-export）
"""
import math
import re

# 内容区下限（页脚 y=690，留 16px 间距）——第三级 硬防线（§七 2.5）：
# y 游标超线的元素不再 emit，进 report.skip("页面溢出截断")。
# 单源在此：_pptd_parts._CONTENT_Y_MAX（别名）与 _layout_lint 贴线豁免
# 共用本值，改一处全端传播（S6 2026-09-07 从 _pptd_parts 上移，切断
# lint→_pptd_gen 私有 import 链）。
CONTENT_Y_MAX = 674

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


def est_text_w(s, font_size):
    """估算文本宽度（px）：全角≈font_size，半角≈0.55*font_size。"""
    w = 0.0
    for ch in str(s):
        w += font_size if ord(ch) > 0x2E7F else font_size * 0.55
    return w


def estimate_text_height(text, font_size, line_height, width):
    """统一文本块高度估算入口（S6 2026-09-07 单源：lint 与生成器同源）。

    行数按 est_text_w 全角/半角估算宽度折行（宽度估算唯一源）；段落按
    \n 切分，HTML 标签剔除后计量，首尾空白不计，空段占一行。高度
    = 行数 × 字号 × line_height（行距为显式参数，调用方各自口径：
    lint 1.3 / 正文 1.65 / 缩排 1.4），至少一行高。
    """
    if not text:
        return font_size * line_height
    avail = max(float(width), 1.0)
    lines = 0
    for seg in str(text).split("\n"):
        seg = seg.strip()
        if not seg:
            lines += 1
            continue
        plain = re.sub(r"<[^>]+>", "", seg)
        lines += max(1, math.ceil(est_text_w(plain, font_size) / avail))
    return max(font_size * line_height, lines * font_size * line_height)
