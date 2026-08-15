# -*- coding: utf-8 -*-
"""页面构件渲染（视觉规范 v2.0 §7）：10 种构件 HTML + CSS，主题变量驱动。

视觉基准 = 用户确认的验收 mock 版式样板
（dev_plan_visual_v2_2026-07-25 §7）：CSS 直接提炼自该文件，主题色一律换
--t- 变量（_renderer.diagram.theme.theme_tokens_css 注入），禁 hex 硬编码
（§9.3 机械防线）。全部文字节点标 data-editable="true"（D-091 可编辑）。

行内强调 hl-* 只允许经 action_title/text 的 segments 写法产出，渲染器不接
受用户 HTML 标签（防注入铁律，§7）。
"""

from _renderer.diagram.theme import _esc  # 单一源（§七 2.6），禁重复定义
from _renderer.elements import _nl2br


# ---------------------------------------------------------------------------
# CSS（mock 提炼，主题变量驱动）
# ---------------------------------------------------------------------------

def chrome_css():
    """页面构件 + exhibit 图框 + 三态芯片 + flow_rows 的 CSS 块。

    注入条件（_renderer 页级渲染）：spec 含 v2 构件元素或 flow_rows 图。
    颜色全部 var(--t-*)，依赖 theme_tokens_css 的 :root 块先于本块注入。
    """
    return """
/* ===== v3.0 中文排版基础（同事经验：防「80000多家」拆行） ===== */
.v2-page, .v2-page p, .v2-page li, .v2-page td, .v2-page th {
  word-break: normal; overflow-wrap: normal; line-height: 1.6;
}
/* ===== v2 页面构件（visual v2.0 §7，mock 版式样板_v0 提炼） ===== */
/* P 系版式页骨架（§6）：锚点 + 节距 + 分隔线 */
.v2-page { padding: 24px 0 20px; border-bottom: 1px solid var(--t-border); }
.v2-page:last-child { border-bottom: none; }
.topnav { position: sticky; top: 0; z-index: 100; background: var(--t-card); border-bottom: 1px solid var(--t-border); box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.topnav-inner { max-width: 1280px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; gap: 24px; height: 54px; }
.topnav .brand { font-weight: 800; font-size: 15px; color: var(--t-primary); }
.topnav .brand-sub { font-size: 12px; color: var(--t-text-secondary); }
.topnav .nav-links { display: flex; gap: 4px; flex: 1; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; min-width: 0; }
.topnav .nav-links::-webkit-scrollbar { display: none; }
.topnav .nav-link { padding: 6px 10px; font-size: 12.5px; color: var(--t-text-secondary); text-decoration: none; border-radius: 6px; white-space: nowrap; }
.topnav .nav-link:hover { background: var(--t-bg-muted); color: var(--t-primary); }
/* v3.0 logo 槽位（spec 顶层 brand 注入） */
.brand-logo { height: 28px; width: auto; display: inline-block; margin-right: 10px; vertical-align: middle; }
.brand-logo-placeholder { height: 28px; width: 96px; display: inline-flex; align-items: center; justify-content: center; border: 1px dashed var(--t-border); border-radius: 4px; color: var(--t-text-tertiary); font-size: 11px; margin-right: 10px; }

.hero { background: linear-gradient(135deg, var(--t-hero-from) 0%, var(--t-hero-to) 100%); color: white; padding: 44px 32px 36px; border-radius: 12px; margin: 20px 0; }
.hero-inner { max-width: 1280px; margin: 0 auto; }
.hero-eyebrow { display: inline-block; justify-self: start; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--t-hero-from); background: var(--t-accent); padding: 3px 10px; border-radius: 3px; margin-bottom: 14px; }
/* 深色背景标题强制白（客户内审铁律）：覆盖基础样式 h1 的深色 + 下划线 */
.hero-title { font-size: 30px; line-height: 1.25; font-weight: 800; margin: 0 0 10px; letter-spacing: -0.3px; color: white; border-bottom: none; padding-bottom: 0; }
.hero-subtitle { font-size: 14px; color: rgba(255,255,255,0.82); max-width: 860px; margin: 0 0 18px; }
.hero-meta { display: flex; gap: 18px; font-size: 12px; color: rgba(255,255,255,0.6); flex-wrap: wrap; }
.hero-stats { margin-top: 20px; }
.hero-stats .stat-card { background: rgba(255,255,255,0.10); border-color: rgba(255,255,255,0.25); border-left-color: var(--t-accent); }
.hero-stats .stat-value { color: white; }
.hero-stats .stat-value small { color: rgba(255,255,255,0.65); }
.hero-stats .stat-label { color: rgba(255,255,255,0.75); }

.section-tag { display: inline-block; font-size: 11px; font-weight: 700; color: var(--t-primary); background: var(--t-primary-a08); padding: 4px 10px; border-radius: 4px; letter-spacing: 0.5px; margin-bottom: 10px; }
.action-title { font-size: 21px; font-weight: 800; line-height: 1.4; margin: 0 0 6px; letter-spacing: -0.2px; color: var(--t-text-primary); }
.action-title .hl-yellow { background: linear-gradient(transparent 62%, var(--t-accent-a55) 62%); padding: 0 2px; }
.hl-red { color: var(--t-role-legal); font-weight: 700; }
.hl-green { color: var(--t-lit-text); font-weight: 700; }
.section-sub { font-size: 13px; color: var(--t-text-secondary); margin: 0 0 22px; }

.stats-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 6px; }
.stat-card { border: 1px solid var(--t-border); border-left: 4px solid var(--t-primary); border-radius: 6px; padding: 12px 16px; background: var(--t-card); }
.stat-card.s-lit { border-left-color: var(--t-lit-border); }
.stat-card.s-part { border-left-color: var(--t-part-border); }
.stat-card.s-gap { border-left-color: var(--t-gap-border); }
.stat-value { font-size: 26px; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; color: var(--t-text-primary); }
.stat-value small { font-size: 13px; font-weight: 600; color: var(--t-text-tertiary); margin-left: 2px; }
.stat-label { font-size: 12px; color: var(--t-text-secondary); margin-top: 2px; }

.kpi-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 6px; }
.kpi-card { border: 1px solid var(--t-border); border-left: 4px solid var(--t-primary); border-radius: 6px; padding: 12px 16px; background: var(--t-card); }
.kpi-label { font-size: 12px; color: var(--t-text-secondary); margin-bottom: 6px; }
.kpi-nums { display: flex; align-items: baseline; gap: 8px; }
.kpi-from { font-size: 16px; font-weight: 700; color: var(--t-text-tertiary); font-variant-numeric: tabular-nums; }
.kpi-arrow { color: var(--t-primary-mid); font-weight: 700; }
.kpi-to { font-size: 24px; font-weight: 800; color: var(--t-primary); font-variant-numeric: tabular-nums; }
.kpi-note { font-size: 11px; color: var(--t-text-tertiary); margin-top: 4px; }

.pain-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0 6px; }
.pain-card { border: 1px solid var(--t-border); border-radius: 8px; padding: 14px 16px; background: var(--t-card); }
.pain-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.pain-title { font-size: 14px; font-weight: 800; color: var(--t-text-primary); }
.pain-badge { margin-left: auto; font-size: 11px; font-weight: 800; color: white; padding: 2px 8px; border-radius: 10px; }
.pain-badge.lv-P0 { background: var(--t-role-legal); }
.pain-badge.lv-P1 { background: var(--t-part-border); }
.pain-badge.lv-P2 { background: var(--t-text-tertiary); }
.pain-impact { font-size: 12px; font-weight: 700; color: var(--t-primary); margin-bottom: 4px; }
.pain-body { font-size: 12px; color: var(--t-text-secondary); line-height: 1.55; }

.info-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0 6px; }
.info-card { border: 1px solid var(--t-border); border-radius: 8px; padding: 14px 16px; background: var(--t-card); }
.info-card h4 { margin: 0 0 8px; font-size: 13px; font-weight: 800; display: flex; align-items: center; gap: 8px; color: var(--t-text-primary); }
.info-card h4::before { content: ""; width: 8px; height: 8px; background: var(--t-primary); transform: rotate(45deg); flex: 0 0 auto; }
.info-card ul { margin: 0; padding-left: 18px; font-size: 12px; color: var(--t-text-secondary); }
.info-card li { margin-bottom: 4px; }

.legend-bar { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; padding: 10px 14px; background: var(--t-bg-soft); border: 1px solid var(--t-border); border-radius: 6px; margin: 14px 0; font-size: 12px; color: var(--t-text-secondary); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
.sw-lit { background: var(--t-lit-bg); border: 1.5px solid var(--t-lit-border); }
.sw-part { background: var(--t-part-bg); border: 1.5px solid var(--t-part-border); }
.sw-gap { background: var(--t-gap-bg); border: 1.5px dashed var(--t-gap-border); }
.sw-keep { background: var(--t-bg-muted); border: 1.5px solid var(--t-text-tertiary); }
.sw-role-biz { background: var(--t-role-biz); }
.sw-role-legal { background: var(--t-role-legal); }
.sw-role-fin { background: var(--t-role-fin); }
.sw-role-sys { background: var(--t-role-sys); }
.sw-role-ext { background: var(--t-role-ext); }

.qa-block { margin: 18px 0 6px; }
.qa-item { border-left: 3px solid var(--t-primary); background: var(--t-bg-soft); border-radius: 0 6px 6px 0; padding: 10px 14px; margin-bottom: 10px; }
.qa-q { font-size: 13px; font-weight: 800; color: var(--t-text-primary); }
.qa-a { font-size: 12px; color: var(--t-text-secondary); margin-top: 4px; line-height: 1.55; }

/* ===== D-093 view_cards（4 列视角卡 + 顶部半圆顶） + callout_block（底部说服区）===== */
/* view_cards：仿"麦肯锡式 4 视角叙事页"——顶端半圆顶居中标题 + 4 列并列卡片半圆顶 */
.view-cards { margin: 24px 0 18px; }
.view-cap { position: relative; height: 64px; background: var(--t-bg-soft); border-radius: 12px; margin-bottom: -32px; }
.view-cap-circle { position: absolute; left: 50%; top: 0; transform: translateX(-50%); width: 360px; max-width: 80%; background: var(--t-primary); color: var(--t-card); font-size: 14px; font-weight: 700; padding: 18px 20px 14px; border-radius: 0 0 180px 180px / 0 0 64px 64px; text-align: center; letter-spacing: 0.5px; box-shadow: 0 4px 12px var(--t-primary-a15); }
.view-cap-circle span { display: inline-block; padding: 0 12px; }

.view-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding-top: 52px; }
.view-card { background: var(--t-card); border: 1px solid var(--t-border); border-radius: 10px; padding: 18px 18px 20px; text-align: center; transition: transform 0.2s, box-shadow 0.2s; }
.view-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px var(--t-border); }
.view-icon { width: 48px; height: 48px; margin: 0 auto 12px; display: flex; align-items: center; justify-content: center; background: var(--t-bg-soft); border-radius: 50%; color: var(--t-primary); font-size: 22px; font-weight: 700; }
.view-perspective { font-size: 15px; font-weight: 800; color: var(--t-text-primary); margin-bottom: 10px; }
.view-headline { margin-bottom: 8px; }
.view-headline-num { font-size: 22px; font-weight: 800; color: var(--t-accent); letter-spacing: -0.5px; }
.view-detail { font-size: 12px; color: var(--t-text-secondary); line-height: 1.6; text-align: left; }

/* callout_block：底部说服区（淡蓝底 + 圆角 + 双编号） */
.callout-block { background: var(--t-bg-soft); border: 1px solid var(--t-border); border-radius: 10px; padding: 18px 22px; margin: 20px 0 6px; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px 24px; }
.callout-point { display: flex; gap: 14px; align-items: flex-start; }
.callout-num { font-size: 22px; font-weight: 800; color: var(--t-primary); line-height: 1; flex: 0 0 auto; padding-top: 2px; font-family: Georgia, serif; letter-spacing: 0.5px; }
.callout-body { flex: 1 1 auto; min-width: 0; }
.callout-title { font-size: 14px; font-weight: 700; color: var(--t-text-primary); line-height: 1.5; margin-bottom: 4px; }
.callout-hl { color: var(--t-accent); font-weight: 800; padding: 0 2px; background: var(--t-accent-a55); }
.callout-desc { font-size: 12px; color: var(--t-text-secondary); line-height: 1.55; }

/* ===== v3.0 新构件（P12 目录 / P14 双栏对比 / P15 优缺点 / P16 CTA） ===== */
.toc-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 18px 0 6px; }
.toc-card { display: flex; gap: 12px; border: 1px solid var(--t-border); border-radius: 8px; padding: 14px 16px; background: var(--t-card); }
.toc-num { font-size: 20px; font-weight: 800; color: var(--t-primary); font-variant-numeric: tabular-nums; min-width: 36px; }
.toc-title { font-size: 15px; font-weight: 700; color: var(--t-text-primary); }
.toc-desc { font-size: 12px; color: var(--t-text-secondary); margin-top: 4px; }
.duo-compare { display: grid; grid-template-columns: 1fr 1px 1fr; gap: 16px; margin: 18px 0 6px; align-items: stretch; }
.duo-vrule { background: var(--t-border); width: 1px; }
.duo-title { font-size: 16px; font-weight: 800; color: var(--t-text-primary); margin-bottom: 10px; }
.duo-points { margin: 0; padding-left: 18px; }
.duo-points li { font-size: 13px; color: var(--t-text-secondary); margin: 6px 0; }
.pros-cons { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 18px 0 6px; }
.pc-col { border: 1px solid var(--t-border); border-radius: 8px; padding: 14px 16px; background: var(--t-card); }
.pc-col .pros { color: var(--t-lit-text); }
.pc-col .cons { color: var(--t-part-text); }
.pc-head { font-size: 13px; font-weight: 800; margin: 0 0 8px; }
.pc-col ul { margin: 0; padding-left: 18px; }
.pc-item { font-size: 13px; color: var(--t-text-secondary); margin: 5px 0; }
.cta-block { margin: 18px 0 6px; text-align: center; padding: 32px 24px; background: linear-gradient(135deg, var(--t-hero-from), var(--t-hero-to)); border-radius: 12px; }
.cta-title { font-size: 24px; font-weight: 800; color: white; margin-bottom: 16px; }
.cta-btn { display: inline-block; background: var(--t-accent); color: var(--t-hero-from); font-weight: 800; padding: 10px 28px; border-radius: 100px; font-size: 14px; }
.cta-contact { margin-top: 12px; font-size: 12px; color: rgba(255,255,255,0.7); }

/* exhibit 图框（§5.5：既有 diagram 的编号+标题+来源包装） */
.exhibit { border: 1px solid var(--t-border); border-radius: 8px; overflow: hidden; margin-top: 18px; }
.exhibit-header { display: flex; align-items: baseline; gap: 12px; padding: 12px 18px; background: var(--t-bg-soft); border-bottom: 1px solid var(--t-border); }
.exhibit-num { font-size: 11px; font-weight: 800; color: white; background: var(--t-primary); padding: 2px 8px; border-radius: 3px; letter-spacing: 0.5px; }
.exhibit-title { font-size: 14px; font-weight: 700; color: var(--t-text-primary); }
.exhibit-body { padding: 20px 18px; }
.exhibit-source { padding: 8px 18px; font-size: 11px; color: var(--t-text-tertiary); border-top: 1px dashed var(--t-border); background: var(--t-bg-soft); }
/* 图框内 diagram 去二层边框（外层 exhibit 已有框） */
.exhibit-body section.diagram { border: none; box-shadow: none; margin: 0; padding: 0; }

/* 三态芯片（§8.2 共享组件：flow_rows 与后续 capability_map 改造共用） */
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 12px; padding: 3px 9px; border-radius: 4px; border: 1.5px solid; white-space: nowrap; }
.chip-lit { background: var(--t-lit-bg); border-color: var(--t-lit-border); color: var(--t-lit-text); font-weight: 600; }
.chip-part { background: var(--t-part-bg); border-color: var(--t-part-border); color: var(--t-part-text); font-weight: 600; }
.chip-gap { background: var(--t-gap-bg); border-color: var(--t-gap-border); border-style: dashed; color: var(--t-gap-text); }
.chip-keep { background: var(--t-bg-muted); border-color: var(--t-text-tertiary); color: var(--t-text-secondary); }

/* flow_rows（§8.1，第 28 种子类型；渲染在 diagram/flow.py，样式集中于此） */
.flow-canvas { display: flex; flex-direction: column; gap: 0; }
.flow-row { display: flex; align-items: stretch; gap: 10px; padding: 12px 14px; border-radius: 6px; }
.flow-row.g-blue { background: var(--t-group-blue); }
.flow-row.g-teal { background: var(--t-group-teal); }
.flow-row.dashed-opt { background: var(--t-part-bg); border: 1.5px dashed var(--t-part-border); }
.flow-row.dashed-opt .fc-label { color: var(--t-part-border); }
.flow-row-label { flex: 0 0 86px; display: flex; flex-direction: column; justify-content: center; font-size: 12px; font-weight: 800; color: var(--t-primary); border-right: 2px solid var(--t-primary-a15); padding-right: 10px; }
.flow-row-label small { font-weight: 500; color: var(--t-text-tertiary); font-size: 11px; }
.flow-cards { display: flex; flex: 1; align-items: stretch; gap: 8px; }
.flow-card { flex: 1; background: var(--t-card); border: 1.5px solid var(--t-border); border-top: 3px solid var(--t-primary); border-radius: 6px; padding: 10px 12px; position: relative; }
.flow-card.r-biz { border-top-color: var(--t-role-biz); }
.flow-card.r-legal { border-top-color: var(--t-role-legal); }
.flow-card.r-fin { border-top-color: var(--t-role-fin); }
.flow-card.r-sys { border-top-color: var(--t-role-sys); }
.flow-card.r-ext { border-top-color: var(--t-role-ext); }
.flow-card.dim { opacity: 0.75; }
.num-badge { position: absolute; top: -9px; left: 10px; width: 18px; height: 18px; border-radius: 50%; background: var(--t-primary-dark); color: white; font-size: 11px; font-weight: 800; display: flex; align-items: center; justify-content: center; }
.fc-label { font-size: 13px; font-weight: 700; line-height: 1.35; color: var(--t-text-primary); }
.fc-desc { font-size: 11px; color: var(--t-text-secondary); margin-top: 3px; line-height: 1.45; }
.flow-arrow { align-self: center; color: var(--t-primary-mid); font-size: 18px; font-weight: 700; flex: 0 0 auto; }
.flow-down { text-align: center; color: var(--t-primary-mid); font-size: 20px; line-height: 1; padding: 2px 0; }
.opt-tag { font-size: 11px; font-weight: 800; color: var(--t-part-border); writing-mode: vertical-lr; letter-spacing: 2px; display: flex; align-items: center; }

/* ===== 审美升级 v2.1（2026-07-31）：阴影层次 / hero 装饰 / 深色导航 / 表格升级 ===== */
/* 页面背景：浅灰渐变，摆脱纯白公文体 */
body { background: linear-gradient(180deg, var(--t-bg-muted) 0%, var(--t-card) 420px); }
.v2-page { padding: 30px 0 28px; }

/* topnav：深蓝渐变导航（对照 v5 渐变页眉，汇报 PPT 质感） */
.topnav { background: linear-gradient(90deg, var(--t-hero-from) 0%, var(--t-hero-to) 100%); border-bottom: none; box-shadow: 0 2px 10px rgba(15,23,42,0.14); }
.topnav .brand { color: var(--t-card); }
.topnav .brand-sub { color: rgba(255,255,255,0.72); }
.topnav .nav-link { color: rgba(255,255,255,0.86); }
.topnav .nav-link:hover { background: rgba(255,255,255,0.14); color: var(--t-card); }
.topnav .nav-links { -webkit-mask-image: linear-gradient(90deg, black 0%, black 93%, transparent 100%); mask-image: linear-gradient(90deg, black 0%, black 93%, transparent 100%); scroll-behavior: smooth; }

/* hero：装饰圆环 + 水印（封面高级感） */
.hero { position: relative; overflow: hidden; box-shadow: 0 4px 20px rgba(15,23,42,0.16); }
.hero::before { content: ""; position: absolute; right: -70px; top: -70px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 68%); }
.hero::after { content: ""; position: absolute; right: 9%; bottom: -110px; width: 240px; height: 240px; border-radius: 50%; border: 30px solid rgba(255,255,255,0.05); }
.hero-inner { position: relative; z-index: 1; max-width: 900px; }
.hero-eyebrow { box-shadow: 0 1px 4px rgba(15,23,42,0.18); letter-spacing: 1.5px; }
/* hero 双栏（有 stats）：左文字区 / 右数据卡，封面右侧有视觉落点 */
.hero-inner.has-stats { max-width: 1280px; display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 44px; align-items: center; }
.hero-inner.has-stats .hero-stats { margin-top: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.hero-inner.has-stats .stat-card { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.22); border-radius: 10px; padding: 16px 14px; text-align: center; backdrop-filter: blur(2px); }
.hero-inner.has-stats .stat-card::after { background: linear-gradient(90deg, var(--t-accent), transparent); }

/* 卡片：阴影层次 + hover 微抬升 */
.stat-card, .kpi-card, .pain-card, .info-card {
  box-shadow: 0 1px 2px rgba(15,23,42,0.05), 0 3px 10px rgba(15,23,42,0.05);
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}
.stat-card:hover, .kpi-card:hover, .pain-card:hover, .info-card:hover {
  box-shadow: 0 2px 5px rgba(15,23,42,0.07), 0 9px 20px rgba(15,23,42,0.09);
  transform: translateY(-2px);
}
.stat-card { position: relative; overflow: hidden; }
.stat-card::after { content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 3px; background: linear-gradient(90deg, var(--t-primary), var(--t-primary-mid)); }
.stat-card.s-lit::after { background: linear-gradient(90deg, var(--t-lit-border), var(--t-lit-text)); }
.stat-card.s-part::after { background: linear-gradient(90deg, var(--t-part-border), var(--t-part-text)); }
.stat-card.s-gap::after { background: linear-gradient(90deg, var(--t-gap-border), var(--t-gap-text)); }
.stat-value { font-size: 30px; color: var(--t-primary-dark); }
.stat-card.s-lit .stat-value { color: var(--t-lit-text); }
.stat-card.s-part .stat-value { color: var(--t-part-text); }
.stat-card.s-gap .stat-value { color: var(--t-gap-text); }

/* pain 卡：标题菱形 + impact 左竖线 */
.pain-card { border-top: 3px solid var(--t-border); }
.pain-title { display: flex; align-items: center; }
.pain-title::before { content: ""; width: 9px; height: 9px; background: var(--t-primary); transform: rotate(45deg); display: inline-block; margin-right: 8px; flex: 0 0 auto; }
.pain-impact { border-left: 3px solid var(--t-primary-mid); padding-left: 9px; }
.pain-badge { box-shadow: 0 1px 3px rgba(15,23,42,0.18); }

/* kpi：to 数字主色冲击 */
.kpi-card { border-top: 3px solid var(--t-border); }
.kpi-to { font-size: 26px; }

/* section-tag：左竖条 + 渐变胶囊 */
.section-tag { background: linear-gradient(135deg, var(--t-primary-a15), var(--t-primary-a08)); border-left: 3px solid var(--t-primary); padding-left: 12px; }

/* D-092 page_header 页眉横幅：渐变底 + EX 编号徽章 + 标题 + 章节胶囊 + meta */
.page-header { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; background: linear-gradient(90deg, var(--t-hero-from) 0%, var(--t-hero-to) 100%); border-radius: 10px; padding: 16px 22px; margin: 18px 0 8px; box-shadow: 0 2px 10px rgba(15,23,42,0.14); position: relative; overflow: hidden; }
.page-header::after { content: ""; position: absolute; right: -40px; top: -40px; width: 140px; height: 140px; border-radius: 50%; border: 18px solid rgba(255,255,255,0.06); }
.ph-index { font-size: 12px; font-weight: 800; color: var(--t-hero-from); background: var(--t-accent); padding: 4px 10px; border-radius: 4px; letter-spacing: 0.5px; position: relative; z-index: 1; }
.ph-title { font-size: 20px; font-weight: 800; color: var(--t-card); margin: 0; position: relative; z-index: 1; }
.ph-tag { font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.9); background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.3); padding: 3px 10px; border-radius: 20px; position: relative; z-index: 1; }
.ph-meta { margin-left: auto; display: flex; gap: 14px; font-size: 11px; color: rgba(255,255,255,0.68); flex-wrap: wrap; position: relative; z-index: 1; }
.ph-meta-item::before { content: "•"; margin-right: 6px; opacity: 0.7; }

/* 图例：微投影 */
.legend-bar { box-shadow: 0 1px 3px rgba(15,23,42,0.04); }

/* flow_rows 徽章：渐变 + 白描边 */
.num-badge { background: linear-gradient(135deg, var(--t-primary-mid), var(--t-primary-dark)); border: 2px solid var(--t-card); box-shadow: 0 1px 3px rgba(15,23,42,0.22); }

/* 表格升级：深蓝表头 + 斑马纹 + 圆角容器（覆盖旧式 th/td 边框） */
table { border-collapse: separate; border-spacing: 0; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 2px rgba(15,23,42,0.05), 0 3px 10px rgba(15,23,42,0.05); }
th { background: var(--t-primary); color: var(--t-card); font-weight: 700; font-size: 13px; padding: 12px 14px; border: none; }
td { border: none; border-bottom: 1px solid var(--t-border); padding: 12px 14px; font-size: 13px; color: var(--t-text-secondary); }
tbody tr:nth-child(even) { background: var(--t-bg-soft); }
tbody tr:hover { background: var(--t-bg-muted); }
tbody tr:last-child td { border-bottom: none; }

/* D-092 diagram 附件槽位：stats（图上）+ legend/notes（图下），组合体 */
.dg-slot-wrap { border: 1px solid var(--t-border); border-radius: 10px; padding: 16px 16px 14px; background: var(--t-card); margin: 18px 0 8px; }
.dg-slot-wrap section.diagram { border: none; box-shadow: none; margin: 0 0 4px; padding: 0; }
.dg-slot-stats { display: grid; gap: 14px; margin-bottom: 14px; }
.dg-slot-stats .stat-card { margin: 0; box-shadow: 0 1px 2px rgba(15,23,42,0.05), 0 3px 10px rgba(15,23,42,0.05); }
.dg-slot-notes { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 12px; }
.dg-slot-notes .info-card { margin: 0; border-top: 3px solid var(--t-primary); }
.dg-slot-notes .info-card-title { font-size: 13px; font-weight: 800; color: var(--t-text-primary); margin-bottom: 6px; }
.dg-slot-notes .info-card-list { list-style: none; margin: 0; padding: 0; font-size: 12px; color: var(--t-text-secondary); line-height: 1.55; }
.dg-slot-notes .info-card-list li { position: relative; padding-left: 12px; margin-bottom: 3px; }
.dg-slot-notes .info-card-list li::before { content: ""; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; background: var(--t-primary-mid); border-radius: 50%; }

/* ===== 文字排版 v2.2（2026-08-02）：中文正文行高 / 标题节奏 / 阅读舒适度 ===== */
/* 中文正文统一舒适行高（正文 1.6-1.75，标题 1.35-1.5），小字号优先受益 */
.section-sub { line-height: 1.75; max-width: 980px; }
.hero-meta { line-height: 1.6; }
.hero-title { line-height: 1.3; max-width: 600px; }
.hero-subtitle { line-height: 1.75; max-width: 600px; }
.action-title { line-height: 1.38; margin-bottom: 10px; }
.stat-label { line-height: 1.55; }
.kpi-label { line-height: 1.5; }
.kpi-note { line-height: 1.55; }
.pain-title { line-height: 1.45; }
.pain-impact { line-height: 1.5; }
.pain-body { line-height: 1.7; }
.info-card h4 { line-height: 1.4; }
.info-card ul { line-height: 1.75; }
.info-card li { margin-bottom: 5px; }
.qa-a { line-height: 1.7; }
.exhibit-title { line-height: 1.5; }
.exhibit-source { line-height: 1.6; }
.fc-label { line-height: 1.45; }
.fc-desc { line-height: 1.55; }
.flow-row-label { line-height: 1.45; }
.legend-item { line-height: 1.5; }
td { line-height: 1.6; }
th { line-height: 1.4; }
"""


# ---------------------------------------------------------------------------
# 构件渲染（输入均为 normalize 后的 dict）
# ---------------------------------------------------------------------------

def _grid_cols(n, default=3):
    """卡行网格列数（内联 style 覆盖默认，按实际卡数均分）。"""
    n = max(1, min(n, 6))
    return f' style="grid-template-columns: repeat({n}, 1fr);"'


def render_hero(n):
    """hero 封面横幅：eyebrow 胶囊 + 大标题 + 副标题 + meta 行 + 可选统计卡。

    有 stats 时双栏布局（左文字区 / 右数据卡，封面右侧不空旷，D-091 v2.2）。
    """
    has_stats = bool(n["stats"])
    parts = ['<div class="hero">',
             '  <div class="hero-inner' + (' has-stats' if has_stats else '') + '">']
    if n["eyebrow"]:
        parts.append(f'    <span class="hero-eyebrow" data-editable="true">{_esc(n["eyebrow"])}</span>')
    parts.append(f'    <h1 class="hero-title" data-editable="true">{_esc(n["title"])}</h1>')
    if n["subtitle"]:
        parts.append(f'    <p class="hero-subtitle" data-editable="true">{_nl2br(n["subtitle"])}</p>')
    if n["meta"]:
        metas = "".join(
            f'<span data-editable="true">{_esc(m)}</span>' for m in n["meta"])
        parts.append(f'    <div class="hero-meta">{metas}</div>')
    if has_stats:
        cards = "".join(
            f'<div class="stat-card"><div class="stat-value num" data-editable="true">'
            f'{_esc(s["value"])}<small>{_esc(s["unit"])}</small></div>'
            f'<div class="stat-label" data-editable="true">{_esc(s["label"])}</div></div>'
            for s in n["stats"])
        parts.append(f'    <div class="hero-stats stats-bar"{_grid_cols(len(n["stats"]), 4)}>{cards}</div>')
    parts.append('  </div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_section_tag(n):
    """section_tag 章节胶囊标签：index · label（index 可空）。"""
    text = f'{n["index"]} · {n["label"]}' if n["index"] else n["label"]
    return f'<span class="section-tag" data-editable="true">{_esc(text)}</span>'


def render_page_header(n):
    """page_header 页眉横幅（D-092 第1层统一页面语言）：EX 编号 + 标题 + 章节胶囊 + meta。

    index：EX-XX 页眉编号徽章；title：页标题；tag：右侧章节胶囊；meta：meta 行。
    """
    parts = ['<div class="page-header">']
    if n["index"]:
        parts.append(f'  <span class="ph-index" data-editable="true">{_esc(n["index"])}</span>')
    parts.append(f'  <h2 class="ph-title" data-editable="true">{_esc(n["title"])}</h2>')
    if n["tag"]:
        parts.append(f'  <span class="ph-tag" data-editable="true">{_esc(n["tag"])}</span>')
    if n["meta"]:
        metas = "".join(
            f'<span class="ph-meta-item" data-editable="true">{_esc(m)}</span>'
            for m in n["meta"])
        parts.append(f'  <span class="ph-meta">{metas}</span>')
    parts.append('</div>')
    return "\n".join(parts)


def render_action_title(n):
    """action_title 结论式标题：segments 行内强调（防注入：只认 hl 枚举）。"""
    segs = []
    prev_raw = ""  # 上一段原始文本（判断是否需要补空格分隔，避免粘连）
    for seg in n["segments"]:
        raw = seg["t"]
        hl = seg["hl"]
        text = _esc(raw)
        if hl in ("yellow", "red", "green"):
            text = f'<span class="hl-{hl}">{text}</span>'
        if segs and not prev_raw.endswith(" "):
            segs.append(" ")
        segs.append(text)
        prev_raw = raw
    parts = [f'<h2 class="action-title" data-editable="true">{"".join(segs)}</h2>']
    if n["sub"]:
        parts.append(f'<p class="section-sub" data-editable="true">{_nl2br(n["sub"])}</p>')
    return "\n".join(parts)


def render_stat_cards(n):
    """stat_cards 统计卡行：左 4px 色条（tone）+ 大数字 + 标签。"""
    cards = []
    for c in n["cards"]:
        cls = f' s-{_esc(c["tone"])}' if c["tone"] in ("lit", "part", "gap") else ""
        unit = f'<small>{_esc(c["unit"])}</small>' if c["unit"] else ""
        cards.append(
            f'<div class="stat-card{cls}">'
            f'<div class="stat-value num" data-editable="true">{_esc(c["value"])}{unit}</div>'
            f'<div class="stat-label" data-editable="true">{_esc(c["label"])}</div></div>')
    return f'<div class="stats-bar"{_grid_cols(len(cards), 4)}>{"".join(cards)}</div>'


def render_kpi_cards(n):
    """kpi_cards 前后对比卡：from → to 大数字 + 指标名 + 注。"""
    cards = []
    for c in n["cards"]:
        arrow = '<span class="kpi-arrow">→</span>' if c["from"] else ""
        from_ = (f'<span class="kpi-from num" data-editable="true">{_esc(c["from"])}</span>'
                 if c["from"] else "")
        note = (f'<div class="kpi-note" data-editable="true">{_esc(c["note"])}</div>'
                if c["note"] else "")
        cards.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label" data-editable="true">{_esc(c["label"])}</div>'
            f'<div class="kpi-nums">{from_}{arrow}'
            f'<span class="kpi-to num" data-editable="true">{_esc(c["to"])}</span></div>'
            f'{note}</div>')
    return f'<div class="kpi-cards"{_grid_cols(len(cards), 4)}>{"".join(cards)}</div>'


def render_pain_cards(n):
    """pain_cards 痛点卡：标题 + level 徽章（P0 红/P1 朱橙/P2 灰）+ 量化影响。"""
    cards = []
    for c in n["cards"]:
        badge = ""
        if c["level"] in ("P0", "P1", "P2"):
            badge = f'<span class="pain-badge lv-{c["level"]}">{c["level"]}</span>'
        impact = (f'<div class="pain-impact" data-editable="true">{_esc(c["impact"])}</div>'
                  if c["impact"] else "")
        body = (f'<div class="pain-body" data-editable="true">{_nl2br(c["body"])}</div>'
                if c["body"] else "")
        cards.append(
            f'<div class="pain-card"><div class="pain-head">'
            f'<span class="pain-title" data-editable="true">{_esc(c["title"])}</span>{badge}'
            f'</div>{impact}{body}</div>')
    return f'<div class="pain-cards"{_grid_cols(len(cards))}>{"".join(cards)}</div>'


def render_info_cards(n):
    """info_cards 要点卡：菱形符标题 + ul（2-4 联网格）。"""
    cards = []
    for c in n["cards"]:
        items = "".join(f'<li data-editable="true">{_esc(i)}</li>' for i in c["items"])
        ul = f'<ul>{items}</ul>' if items else ""
        cards.append(
            f'<div class="info-card"><h4 data-editable="true">{_esc(c["title"])}</h4>{ul}</div>')
    return f'<div class="info-cards"{_grid_cols(len(cards))}>{"".join(cards)}</div>'


def render_legend_bar(n):
    """legend_bar 图例条：swatch（三态/角色/keep）+ label。"""
    items = []
    for it in n["items"]:
        sw = it["swatch"] if it["swatch"] else "keep"
        sw = sw.replace("role_", "role-")  # role_biz -> sw-role-biz
        items.append(
            f'<span class="legend-item"><i class="legend-swatch sw-{_esc(sw)}"></i>'
            f'<span data-editable="true">{_esc(it["label"])}</span></span>')
    return f'<div class="legend-bar">{"".join(items)}</div>'


def render_qa_block(n):
    """qa_block 问答块：Q 粗体 + A 段落。"""
    items = []
    for it in n["items"]:
        a = (f'<div class="qa-a" data-editable="true">{_nl2br(it["a"])}</div>'
             if it["a"] else "")
        items.append(
            f'<div class="qa-item"><div class="qa-q" data-editable="true">'
            f'{_esc(it["q"])}</div>{a}</div>')
    return f'<div class="qa-block">{"".join(items)}</div>'


def render_view_cards(n):
    """view_cards：4 列视角卡片 + 顶部半圆顶居中标题（D-093 麦肯锡式）。

    顶部半圆顶（赛道灰底 + 蓝色实心半圆 + 标题），底部 4 列并列卡片
    （每卡：icon 区 + 视角名 + 关键数字 headline + 1-3 行 detail）。
    整体视觉：克制的开场 + 高密度卡片 + 横向并列的"4 视角"叙事。
    """
    title = n.get("title", "")
    cap = (f'<div class="view-cap"><div class="view-cap-circle">'
           f'<span data-editable="true">{_esc(title)}</span></div></div>'
           if title else "")
    cards = []
    for c in n["cards"]:
        icon = _esc(c["icon"]) if c["icon"] else "◆"
        perspective = _esc(c["perspective"])
        headline = _esc(c["headline"]) if c["headline"] else ""
        detail = _esc(c["detail"]) if c["detail"] else ""
        # 关键数字高亮（红色 + 大字）— 模仿标杆页"30% / 60%"那种强调
        headline_html = (f'<div class="view-headline" data-editable="true">'
                         f'<span class="view-headline-num">{headline}</span></div>'
                         if headline else "")
        detail_html = (f'<div class="view-detail" data-editable="true">{detail}</div>'
                       if detail else "")
        cards.append(
            f'<div class="view-card">'
            f'<div class="view-icon" data-editable="true">{icon}</div>'
            f'<div class="view-perspective" data-editable="true">{perspective}</div>'
            f'{headline_html}{detail_html}'
            f'</div>')
    return f'<div class="view-cards">{cap}<div class="view-grid">{"".join(cards)}</div></div>'


def render_callout_block(n):
    """callout_block：底部双编号说服区（D-093）。

    淡蓝底容器 + 圆角 + 双编号（01/02）说服句。每点：编号 + 标题
    （.callout-hl 红色关键数字） + 1-2 行 desc。整组 2-3 个点（视觉平衡）。
    """
    points = []
    for pt in n["points"]:
        num = _esc(pt["num"])
        title = _esc(pt["title"])
        highlight = _esc(pt["highlight"]) if pt["highlight"] else ""
        desc = _esc(pt["desc"]) if pt["desc"] else ""
        # highlight 用单独的 .callout-hl span 渲染红色强调数字
        if highlight and highlight in title:
            title_html = title.replace(
                highlight,
                f'<span class="callout-hl">{highlight}</span>')
        elif highlight:
            title_html = f'{title} <span class="callout-hl">{highlight}</span>'
        else:
            title_html = title
        desc_html = (f'<div class="callout-desc" data-editable="true">{desc}</div>'
                     if desc else "")
        points.append(
            f'<div class="callout-point">'
            f'<span class="callout-num" data-editable="true">{num}</span>'
            f'<div class="callout-body">'
            f'<div class="callout-title" data-editable="true">{title_html}</div>'
            f'{desc_html}'
            f'</div></div>')
    return f'<div class="callout-block">{"".join(points)}</div>'


def render_toc_cards(n):
    """toc_cards：目录卡（P12，v3.0）。编号 + 标题 + 可选描述。"""
    cards = []
    for c in n["cards"]:
        desc = (f'<div class="toc-desc">{_esc(c["desc"])}</div>' if c["desc"]
                else "")
        cards.append(
            f'<div class="toc-card"><span class="toc-num" data-editable="true">'
            f'{_esc(c["num"])}</span>'
            f'<div class="toc-body"><div class="toc-title" data-editable="true">'
            f'{_esc(c["title"])}</div>{desc}</div></div>')
    return f'<div class="toc-cards">{"".join(cards)}</div>'


def render_duo_compare(n):
    """duo_compare：双栏对比（P14，v3.0）。左/右面板 + 1px 中隔线。"""
    def _side(k):
        s = n[k]
        pts = "".join(f'<li>{_esc(p)}</li>' for p in s["points"])
        return (f'<div class="duo-panel"><div class="duo-title" '
                f'data-editable="true">{_esc(s["title"])}</div>'
                f'<ul class="duo-points">{pts}</ul></div>')
    return (f'<div class="duo-compare">{_side("left")}'
            f'<div class="duo-vrule"></div>{_side("right")}</div>')


def render_pros_cons(n):
    """pros_cons：优缺点清单（P15，v3.0）。pros 绿 / cons 橙双列。"""
    pros = "".join(f'<li class="pc-item pc-pro">{_esc(p)}</li>' for p in n["pros"])
    cons = "".join(f'<li class="pc-item pc-con">{_esc(c)}</li>' for c in n["cons"])
    return (f'<div class="pros-cons">'
            f'<div class="pc-col"><h4 class="pc-head pros" data-editable="true">'
            f'优势</h4><ul>{pros}</ul></div>'
            f'<div class="pc-col"><h4 class="pc-head cons" data-editable="true">'
            f'风险/成本</h4><ul>{cons}</ul></div></div>')


def render_cta_block(n):
    """cta_block：CTA 收尾（P16，v3.0）。标题 + 按钮 + 联系方式。"""
    btn = (f'<div class="cta-btn" data-editable="true">{_esc(n["button"])}</div>'
           if n["button"] else "")
    contact = (f'<div class="cta-contact" data-editable="true">'
               f'{_esc(n["contact"])}</div>' if n["contact"] else "")
    return (f'<div class="cta-block"><div class="cta-title" data-editable="true">'
            f'{_esc(n["title"])}</div>{btn}{contact}</div>')


def render_evidence_ledger(n):
    """evidence_ledger 证据台账（B-3）：编号 + 结论 + 证据 + 状态 四列表格。"""
    title = (f'<h3 data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    rows = []
    for it in n["items"]:
        num = _esc(it["num"]) if it["num"] else "—"
        status = _esc(it["status"]) if it["status"] else "—"
        rows.append(
            f'<tr><td class="ev-num" data-editable="true">{num}</td>'
            f'<td data-editable="true">{_esc(it["conclusion"])}</td>'
            f'<td data-editable="true">{_esc(it["evidence"])}</td>'
            f'<td class="ev-status" data-editable="true">{status}</td></tr>')
    thead = ('<thead><tr><th>编号</th><th>结论</th><th>证据</th><th>状态</th>'
             '</tr></thead>' if n["items"] else "")
    return (f'<div class="evidence-ledger">{title}<table class="evidence-table">'
            f'{thead}<tbody>{"".join(rows)}</tbody></table></div>')


def render_risk_register(n):
    """risk_register 风险登记（B-4）：风险 + 等级 + 状态 + 应对 四列表格。"""
    title = (f'<h3 data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    rows = []
    for it in n["items"]:
        level = it["level"] or "—"
        lv_cls = {"高": "lv-high", "中": "lv-mid", "低": "lv-low"}.get(level, "")
        status = _esc(it["status"]) if it["status"] else "—"
        rows.append(
            f'<tr><td data-editable="true">{_esc(it["risk"])}</td>'
            f'<td><span class="risk-level {lv_cls}" data-editable="true">'
            f'{_esc(level)}</span></td>'
            f'<td data-editable="true">{status}</td>'
            f'<td data-editable="true">{_esc(it["response"])}</td></tr>')
    thead = ('<thead><tr><th>风险</th><th>等级</th><th>状态</th><th>应对</th>'
             '</tr></thead>' if n["items"] else "")
    return (f'<div class="risk-register">{title}<table class="risk-table">'
            f'{thead}<tbody>{"".join(rows)}</tbody></table></div>')


def render_raci_matrix(n):
    """raci_matrix 角色责任矩阵（B-5）：行=任务，列=角色，单元格 R/A/C/I。"""
    title = (f'<h3 data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    roles = n["roles"]
    if not roles or not n["tasks"]:
        return f'<div class="raci-matrix">{title}</div>'
    th = "".join(f'<th data-editable="true">{_esc(r)}</th>' for r in roles)
    thead = f'<thead><tr><th>任务</th>{th}</tr></thead>'
    rows = []
    for t in n["tasks"]:
        cells = "".join(
            f'<td class="raci-{_esc(t["cells"].get(r, ""))}" data-editable="true">'
            f'{_esc(t["cells"].get(r, ""))}</td>'
            for r in roles)
        rows.append(
            f'<tr><td data-editable="true">{_esc(t["task"])}</td>{cells}</tr>')
    return (f'<div class="raci-matrix">{title}<table class="raci-table">'
            f'{thead}<tbody>{"".join(rows)}</tbody></table></div>')


def render_decision_board(n):
    """decision_board 决策面板（B-6）：方案对比 + 推荐 + 下一步。"""
    title = (f'<h3 data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    cards = []
    for opt in n["options"]:
        pros = "".join(f'<li data-editable="true">{_esc(p)}</li>'
                       for p in opt["pros"])
        cons = "".join(f'<li data-editable="true">{_esc(c)}</li>'
                       for c in opt["cons"])
        cards.append(
            f'<div class="decision-card"><h4 data-editable="true">'
            f'{_esc(opt["name"])}</h4>'
            f'<ul class="pros">{pros}</ul><ul class="cons">{cons}</ul></div>')
    grid = _grid_cols(len(n["options"])) if n["options"] else ""
    rec = (f'<div class="decision-rec" data-editable="true">'
           f'推荐：{_esc(n["recommendation"])}</div>'
           if n["recommendation"] else "")
    nxt = (f'<div class="decision-next" data-editable="true">'
           f'{_esc(n["next_step"])}</div>' if n["next_step"] else "")
    return (f'<div class="decision-board">{title}'
            f'<div class="decision-cards"{grid}>{"".join(cards)}</div>'
            f'{rec}{nxt}</div>')


def _nav_label(title, max_len=12):
    """导航短标签：先截冒号后副标题，仍超长再截括号，最后省略——防长标题撑爆 54px 导航条。"""
    import re as _re
    short = _re.split(r"[：:]", title, maxsplit=1)[0].strip() or title
    if len(short) > max_len:
        short = _re.split(r"[（(]", short, maxsplit=1)[0].strip() or short
    return short if len(short) <= max_len else short[:max_len] + "…"


def render_topnav(n, pages=None):
    """topnav 长 HTML 导航：logo（可选）+ brand + 章节锚点。"""
    links = []
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        pid, title = page.get("id", ""), page.get("title", "")
        if pid and title:
            label = _nav_label(title)
            links.append(
                f'<a class="nav-link" href="#{_esc(pid)}" title="{_esc(title)}">'
                f'{_esc(label)}</a>')
    sub = (f'<span class="brand-sub" data-editable="true">{_esc(n["brand_sub"])}</span>'
           if n["brand_sub"] else "")
    logo = _brand_logo_html(n)
    return (
        '<div class="topnav"><div class="topnav-inner">'
        f'{logo}'
        f'<span class="brand" data-editable="true">{_esc(n["brand"])}</span>{sub}'
        f'<div class="nav-links">{"".join(links)}</div>'
        '</div></div>')


def _brand_logo_html(n):
    """logo 槽位：有 logo 注入 <img>，无则占位虚线框（可编辑替换）。"""
    logo = n.get("logo", "")
    if logo:
        return (f'<img class="brand-logo" src="{_esc(logo)}" '
                f'alt="logo" data-editable="false">')
    return '<span class="brand-logo-placeholder" data-editable="true">LOGO</span>'


# 构件 type -> 渲染函数（topnav 特殊：需要 pages 生成锚点，单独分派）
CHROME_RENDERERS = {
    "hero": render_hero,
    "section_tag": render_section_tag,
    "page_header": render_page_header,
    "action_title": render_action_title,
    "stat_cards": render_stat_cards,
    "kpi_cards": render_kpi_cards,
    "pain_cards": render_pain_cards,
    "info_cards": render_info_cards,
    "legend_bar": render_legend_bar,
    "qa_block": render_qa_block,
    # D-093 view_cards + callout_block（麦肯锡式说服叙事页核心构件）
    "view_cards": render_view_cards,
    "callout_block": render_callout_block,
    # v3.0 版式构件（P12/P14/P15/P16）
    "toc_cards": render_toc_cards,
    "duo_compare": render_duo_compare,
    "pros_cons": render_pros_cons,
    "cta_block": render_cta_block,
    # 批次 B 组件（B-3 证据台账）
    "evidence_ledger": render_evidence_ledger,
    "risk_register": render_risk_register,
    "raci_matrix": render_raci_matrix,
    "decision_board": render_decision_board,
}


def render_chrome_html(elem_type, normalized, pages=None):
    """页面构件总分派。未知 type 返回 None（调用方走既有未知元素路径）。"""
    if elem_type == "topnav":
        return render_topnav(normalized, pages=pages)
    renderer = CHROME_RENDERERS.get(elem_type)
    if renderer is None:
        return None
    return renderer(normalized)
