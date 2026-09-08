# -*- coding: utf-8 -*-
"""页面构件渲染（视觉规范 v2.0 §7）：10 种构件 HTML + CSS，主题变量驱动。

视觉基准 = 用户确认的验收 mock output/蓝海集团/蓝海集团_版式样板_v0.html
（dev_plan_visual_v2_2026-07-25 §7）：CSS 直接提炼自该文件，主题色一律换
--t- 变量（_renderer.theme.theme_tokens_css 注入），禁 hex 硬编码
（§9.3 机械防线）。全部文字节点标 data-editable="true"（D-091 可编辑）。

行内强调 hl-* 只允许经 action_title/text 的 segments 写法产出，渲染器不接
受用户 HTML 标签（防注入铁律，§7）。
"""

from _renderer.theme import _esc  # 单一源（§七 2.6），禁重复定义
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
/* 页骨架（§6）：v2 版式页 + 自由流页统一成“页面卡片”，滚动时有明显页边界 */
.v2-page, .page-shell {
  background: var(--t-card);
  border: 1px solid var(--t-border);
  border-radius: 14px;
  box-shadow: 0 2px 10px rgba(15,23,42,0.06);
  margin: 28px 0;
  padding: 32px 36px;
}
.v2-page:last-child, .page-shell:last-child { margin-bottom: 0; }
.page-shell > h2 { margin-top: 0; }
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
/* logo_position=topnav_right：槽位移到导航右端，margin 翻到左边（B4 P1-6 消费） */
.brand-logo.pos-right, .brand-logo-placeholder.pos-right { margin-right: 0; margin-left: 10px; }

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
/* C-E4 官方绿语义槽（--t-qa-*，theme.py DEFAULT_QA_SLOTS 单一事实源，gov_red 金系覆写防红绿撞色） */
.qa-item { border-left: 3px solid var(--t-qa-text, var(--t-primary)); background: var(--t-qa-bg, var(--t-bg-soft)); border-radius: 0 6px 6px 0; padding: 10px 14px; margin-bottom: 10px; }
.qa-q { font-size: 13px; font-weight: 800; color: var(--t-qa-text, var(--t-text-primary)); }
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
/* C-E3 语义强化：before 灰（现状）/ after 主色（未来），未写 tone 走上方中性样式 */
.duo-panel.duo-before .duo-title { color: var(--t-text-tertiary); }
.duo-panel.duo-before .duo-points li { color: var(--t-text-tertiary); }
.duo-panel.duo-after { border-left: 3px solid var(--t-primary); padding-left: 13px; }
.duo-panel.duo-after .duo-title { color: var(--t-primary); }
.duo-panel.duo-after .duo-points li { color: var(--t-text-primary); }
/* C-E3 量化对比行：双栏下方对照表，after 列主色 */
.duo-metrics { width: 100%; border-collapse: collapse; margin: 0 0 6px; }
.duo-metrics th { font-size: 12px; font-weight: 800; text-align: left; padding: 6px 10px; border-bottom: 1.5px solid var(--t-border); color: var(--t-text-secondary); }
.duo-metrics th.duo-m-after { color: var(--t-primary); }
.duo-metrics td { font-size: 13px; padding: 6px 10px; border-bottom: 1px solid var(--t-border); font-variant-numeric: tabular-nums; }
.duo-metrics td.duo-m-label { font-weight: 700; color: var(--t-text-primary); width: 34%; }
.duo-metrics td.duo-m-right { color: var(--t-primary); font-weight: 700; }
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

/* ===== Step 5 新增元素：ui_mock 界面示意卡 + conclusion_band 结论色带 ===== */
.ui-mock { border: 1px solid var(--t-border); border-radius: 10px; overflow: hidden; margin: 18px 0 8px; background: var(--t-card); box-shadow: 0 1px 2px rgba(15,23,42,0.05), 0 3px 10px rgba(15,23,42,0.05); }
.ui-mock-browser { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--t-bg-muted); border-bottom: 1px solid var(--t-border); }
.ui-mock-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--t-text-tertiary); opacity: 0.55; }
.ui-mock-address { flex: 1; margin-left: 8px; height: 14px; border-radius: 999px; background: var(--t-card); border: 1px solid var(--t-border); font-size: 10px; color: var(--t-text-tertiary); padding: 0 8px; line-height: 14px; }
.ui-mock-body { padding: 16px 18px; }
.ui-mock-tabs { display: flex; gap: 10px; margin-bottom: 12px; border-bottom: 1px solid var(--t-border); }
.ui-mock-tab { font-size: 12px; font-weight: 600; color: var(--t-text-secondary); padding: 5px 2px 7px; border-bottom: 2px solid transparent; }
.ui-mock-tab.active { color: var(--t-primary); border-bottom-color: var(--t-primary); font-weight: 800; }
.ui-mock-title { font-size: 16px; font-weight: 800; color: var(--t-primary); margin: 0 0 12px; }
.ui-mock-section { margin-bottom: 14px; }
.ui-mock-subtitle { font-size: 12px; font-weight: 700; color: var(--t-text-secondary); margin-bottom: 6px; }
.ui-mock-bars { display: flex; flex-direction: column; gap: 6px; }
.ui-mock-bar { height: 10px; border-radius: 4px; background: var(--t-border); }
.ui-mock-seal { width: 84px; height: 84px; border-radius: 50%; border: 2px solid var(--t-role-legal); color: var(--t-role-legal); display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; font-weight: 800; margin: 10px auto 4px; transform: rotate(-8deg); }
.ui-mock-seal-text { font-size: 13px; line-height: 1.25; }
.ui-mock-seal-company { font-size: 8px; opacity: 0.85; margin-top: 3px; line-height: 1.2; }
.ui-mock-caption { font-size: 11px; color: var(--t-text-tertiary); text-align: center; padding: 6px 12px 12px; }

.conclusion-band { margin: 18px 0 6px; border-radius: 8px; padding: 14px 18px; font-size: 14px; line-height: 1.6; }

/* ===== S8 Wave B：C-E2 三件套（sla_block / profile_card / logo_wall） ===== */
.sla-block { margin: 18px 0 6px; }
.sla-heading, .pcard-heading, .lwall-heading { font-size: 15px; font-weight: 800; color: var(--t-text-primary); margin: 0 0 10px; }
.sla-grid { display: grid; gap: 12px; }
.sla-card { border: 1px solid var(--t-border); border-top: 3px solid var(--t-primary); border-radius: 8px; padding: 14px 16px; background: var(--t-card); }
.sla-name { font-size: 12px; font-weight: 700; color: var(--t-text-secondary); }
.sla-value { font-size: 22px; font-weight: 800; color: var(--t-primary); font-variant-numeric: tabular-nums; margin-top: 4px; line-height: 1.2; }
.sla-desc { font-size: 11px; color: var(--t-text-tertiary); margin-top: 6px; line-height: 1.5; }
.profile-card { margin: 18px 0 6px; }
.pcard { display: flex; gap: 14px; border: 1px solid var(--t-border); border-radius: 8px; padding: 14px 16px; background: var(--t-card); margin-bottom: 12px; }
.pcard-photo { width: 72px; height: 96px; object-fit: cover; border-radius: 6px; flex: 0 0 auto; }
.pcard-avatar { width: 48px; height: 48px; border-radius: 50%; background: var(--t-bg-soft); color: var(--t-primary); font-size: 20px; font-weight: 800; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; margin-top: 4px; }
.pcard-body { flex: 1 1 auto; min-width: 0; }
.pcard-name { font-size: 14px; font-weight: 800; color: var(--t-text-primary); }
.pcard-role { font-size: 12px; font-weight: 700; color: var(--t-primary); margin-left: 8px; }
.pcard-desc { font-size: 12px; color: var(--t-text-secondary); line-height: 1.6; margin-top: 6px; }
.pcard-contact { font-size: 11px; color: var(--t-text-tertiary); margin-top: 6px; }
.logo-wall { margin: 18px 0 6px; }
.lwall-grid { display: grid; gap: 12px; }
.lwall-cell { border: 1px solid var(--t-border); border-radius: 8px; background: var(--t-card); min-height: 64px; display: flex; align-items: center; justify-content: center; padding: 10px 12px; }
.lwall-img { max-width: 100%; max-height: 48px; object-fit: contain; }
.lwall-name { font-size: 13px; font-weight: 700; color: var(--t-text-tertiary); letter-spacing: 1px; }
.conclusion-band.tone-primary { background: var(--t-primary-a15); border-left: 4px solid var(--t-primary); color: var(--t-text-primary); }
.conclusion-band.tone-accent { background: var(--t-accent-a55); border-left: 4px solid var(--t-accent); color: var(--t-text-primary); }
.conclusion-band.tone-muted { background: var(--t-bg-muted); border-left: 4px solid var(--t-text-tertiary); color: var(--t-text-secondary); }
.conclusion-band .cb-red { color: var(--t-role-legal); font-weight: 800; }

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

/* flow_rows（§8.1；渲染在 diagram/flow.py，样式集中于此） */
.flow-canvas { display: flex; flex-direction: column; gap: 0; }
.flow-row { display: flex; align-items: stretch; gap: 10px; padding: 12px 14px; border-radius: 6px; }
.flow-row.g-blue { background: var(--t-group-blue); }
.flow-row.g-teal { background: var(--t-group-teal); }
.flow-row.g-red { background: var(--t-group-red); }
.flow-row.g-gray { background: var(--t-group-gray); }
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
/* 页面背景：浅灰画布，让每页白卡片独立可见 */
body { background: var(--t-bg-muted); }
.v2-page, .page-shell { padding: 36px 40px; }

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
    """duo_compare：双栏对比（P14，v3.0）。左/右面板 + 1px 中隔线。

    S8 Wave B 语义强化（C-E3，向后兼容）：
    - side.tone=before 灰（现状）/after 主色（未来），未写 tone 走原中性样式
    - metrics 量化对比行：双栏下方对照表（指标名 | 左值 | 右值），after 列主色
    """
    def _side(k):
        s = n[k]
        tone_cls = f" duo-{_esc(s['tone'])}" if s.get("tone") else ""
        pts = "".join(f'<li>{_esc(p)}</li>' for p in s["points"])
        return (f'<div class="duo-panel{tone_cls}"><div class="duo-title" '
                f'data-editable="true">{_esc(s["title"])}</div>'
                f'<ul class="duo-points">{pts}</ul></div>')
    html = (f'<div class="duo-compare">{_side("left")}'
            f'<div class="duo-vrule"></div>{_side("right")}</div>')
    metrics = n.get("metrics") or []
    if metrics:
        left_title = _esc(n["left"]["title"])
        right_title = _esc(n["right"]["title"])
        rows = []
        for m in metrics:
            rows.append(
                f'<tr><td class="duo-m-label" data-editable="true">'
                f'{_esc(m["label"])}</td>'
                f'<td class="duo-m-left" data-editable="true">{_esc(m["left"])}</td>'
                f'<td class="duo-m-right" data-editable="true">{_esc(m["right"])}</td></tr>')
        html += (
            f'<table class="duo-metrics"><thead><tr><th></th>'
            f'<th>{left_title}</th><th class="duo-m-after">{right_title}</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')
    return html


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


def render_sla_block(n):
    """sla_block：SLA 服务承诺卡（C-E2，泛微实证标准件）。

    可选标题 + 承诺卡网格（指标名 / 承诺值大字主色 / 说明），≤4 张一行。
    """
    title = (f'<h3 class="sla-heading" data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    cards = []
    for it in n["items"]:
        desc = (f'<div class="sla-desc" data-editable="true">{_esc(it["desc"])}</div>'
                if it["desc"] else "")
        cards.append(
            f'<div class="sla-card"><div class="sla-name" data-editable="true">'
            f'{_esc(it["name"])}</div>'
            f'<div class="sla-value" data-editable="true">{_esc(it["value"])}</div>'
            f'{desc}</div>')
    return (f'<div class="sla-block">{title}'
            f'<div class="sla-grid"{_grid_cols(len(n["items"]))}>{"".join(cards)}</div></div>')


def render_profile_card(n):
    """profile_card：人员卡（C-E2，左照片/头像 + 右项目经历）。

    可选标题 + 人员卡列表；photo 缺失用姓名首字圆形头像兜底。
    """
    title = (f'<h3 class="pcard-heading" data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    cards = []
    for p in n["profiles"]:
        if p["photo"]:
            avatar = (f'<img class="pcard-photo" src="{_esc(p["photo"])}" '
                      f'alt="{_esc(p["name"])}">')
        else:
            initial = _esc(p["name"][:1]) if p["name"] else "◆"
            avatar = f'<div class="pcard-avatar">{initial}</div>'
        role = (f'<span class="pcard-role" data-editable="true">'
                f'{_esc(p["role"])}</span>' if p["role"] else "")
        contact = (f'<div class="pcard-contact" data-editable="true">'
                   f'{_esc(p["contact"])}</div>' if p["contact"] else "")
        desc = (f'<div class="pcard-desc" data-editable="true">{_nl2br(p["desc"])}</div>'
                if p["desc"] else "")
        cards.append(
            f'<div class="pcard">{avatar}'
            f'<div class="pcard-body"><div class="pcard-name" data-editable="true">'
            f'{_esc(p["name"])}</div>{role}{desc}{contact}</div></div>')
    return (f'<div class="profile-card">{title}{"".join(cards)}</div>')


def render_logo_wall(n):
    """logo_wall：logo 墙（C-E2，收尾标配，网格 ≤8 由容量预算管）。

    可选标题 + logo 网格；src 缺失用客户名文字牌兜底。
    """
    title = (f'<h3 class="lwall-heading" data-editable="true">{_esc(n["title"])}</h3>'
             if n["title"] else "")
    cells = []
    for lg in n["logos"]:
        if lg["src"]:
            body = (f'<img class="lwall-img" src="{_esc(lg["src"])}" '
                    f'alt="{_esc(lg["name"])}">')
        else:
            body = (f'<span class="lwall-name" data-editable="true">'
                    f'{_esc(lg["name"])}</span>')
        cells.append(f'<div class="lwall-cell">{body}</div>')
    return (f'<div class="logo-wall">{title}'
            f'<div class="lwall-grid"{_grid_cols(len(n["logos"]), 4)}>'
            f'{"".join(cells)}</div></div>')


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


def _render_red_strong(text):
    """把 `**红字**` 关键词转为主色加粗（泛微体系强调红），其余转义。"""
    parts = []
    idx = 0
    while True:
        start = text.find("**", idx)
        if start < 0:
            parts.append(_esc(text[idx:]))
            break
        parts.append(_esc(text[idx:start]))
        end = text.find("**", start + 2)
        if end < 0:
            parts.append(_esc(text[start:]))
            break
        parts.append(f'<strong class="cb-red">{_esc(text[start + 2:end])}</strong>')
        idx = end + 2
    return "".join(parts)


def render_ui_mock(n):
    """ui_mock：DOM 绘制的界面示意卡（禁 SVG，转 PPT 后可编辑）。"""
    parts = ['<div class="ui-mock">']
    if n["frame"] == "browser":
        dots = "".join('<span class="ui-mock-dot"></span>' for _ in range(3))
        parts.append(f'<div class="ui-mock-browser">{dots}'
                     f'<span class="ui-mock-address">app.example.com</span></div>')
    parts.append('<div class="ui-mock-body">')
    if n["tabs"]:
        tabs = "".join(
            f'<span class="ui-mock-tab{" active" if i == 0 else ""}" '
            f'data-editable="true">{_esc(t)}</span>'
            for i, t in enumerate(n["tabs"]))
        parts.append(f'<div class="ui-mock-tabs">{tabs}</div>')
    parts.append(f'<div class="ui-mock-title" data-editable="true">{_esc(n["title"])}</div>')
    for sec in n["sections"]:
        parts.append('<div class="ui-mock-section">')
        if sec["subtitle"]:
            parts.append(f'<div class="ui-mock-subtitle" data-editable="true">'
                         f'{_esc(sec["subtitle"])}</div>')
        bars = "".join(
            f'<div class="ui-mock-bar" style="width:{max(10, min(100, int(b)))}%"'
            f' data-editable="true"></div>'
            for b in sec["bars"])
        parts.append(f'<div class="ui-mock-bars">{bars}</div></div>')
    seal = n.get("seal") or {}
    if seal and n["variant"] == "document":
        parts.append(
            '<div class="ui-mock-seal" data-editable="true">'
            f'<span class="ui-mock-seal-text">{_esc(seal.get("text", ""))}</span>'
            f'<span class="ui-mock-seal-company">{_esc(seal.get("company", ""))}</span>'
            '</div>')
    parts.append('</div>')
    if n["caption"]:
        parts.append(f'<div class="ui-mock-caption" data-editable="true">'
                     f'{_esc(n["caption"])}</div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_conclusion_band(n):
    """conclusion_band：页底结论色带，支持 `**红字**` 强调。"""
    body = _render_red_strong(n["text"])
    return (f'<div class="conclusion-band tone-{_esc(n["tone"])}" '
            f'data-editable="true">{body}</div>')


def _nav_label(title, max_len=12):
    """导航短标签：先截冒号后副标题，仍超长再截括号，最后省略——防长标题撑爆 54px 导航条。"""
    import re as _re
    short = _re.split(r"[：:]", title, maxsplit=1)[0].strip() or title
    if len(short) > max_len:
        short = _re.split(r"[（(]", short, maxsplit=1)[0].strip() or short
    return short if len(short) <= max_len else short[:max_len] + "…"


def render_topnav(n, pages=None):
    """topnav 长 HTML 导航：logo（可选）+ brand + 章节锚点。

    logo_position 摆位（B4 P1-6 收尾消费，枚举见 schema._validate_doc_brand）：
    topnav_left（缺省）logo 槽在 brand 左侧；topnav_right 槽移到导航链接
    右端（pos-right 类翻转 margin），缺省/未知值输出与 B4 前逐字节一致。
    hero_corner 为封面（hero）场景声明值——topnav 不承担封面渲染，按缺省
    左位落（B4 未消费，接入封面 logo 需求时再扩展）。
    """
    links = []
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        pid, title = page.get("id", ""), page.get("title", "")
        # P3：YAML 数字标题（如 title: 2024）在 _nav_label 的正则切分处裸崩
        # TypeError，渲染前归一为字符串（str/None 原样，正常路径零 diff）
        if title is not None and not isinstance(title, str):
            title = str(title)
        if pid and title:
            label = _nav_label(title)
            links.append(
                f'<a class="nav-link" href="#{_esc(pid)}" title="{_esc(title)}">'
                f'{_esc(label)}</a>')
    sub = (f'<span class="brand-sub" data-editable="true">{_esc(n["brand_sub"])}</span>'
           if n["brand_sub"] else "")
    logo_pos = n.get("logo_position") or "topnav_left"
    logo = _brand_logo_html(n, right=(logo_pos == "topnav_right"))
    if logo_pos == "topnav_right":
        # 右位：brand 先行，logo 槽排 nav-links 之后（flex 尾部 = 导航右端）
        return (
            '<div class="topnav"><div class="topnav-inner">'
            f'<span class="brand" data-editable="true">{_esc(n["brand"])}</span>{sub}'
            f'<div class="nav-links">{"".join(links)}</div>'
            f'{logo}'
            '</div></div>')
    return (
        '<div class="topnav"><div class="topnav-inner">'
        f'{logo}'
        f'<span class="brand" data-editable="true">{_esc(n["brand"])}</span>{sub}'
        f'<div class="nav-links">{"".join(links)}</div>'
        '</div></div>')


def _brand_logo_html(n, right=False):
    """logo 槽位：有 logo 注入 <img>，无则占位虚线框（可编辑替换）。

    right=True（logo_position=topnav_right）：追加 pos-right 类（CSS 翻转
    margin），槽位落 topnav 右端；缺省 False 输出与 B4 前逐字节一致。
    """
    pos_cls = " pos-right" if right else ""
    logo = n.get("logo", "")
    if logo:
        return (f'<img class="brand-logo{pos_cls}" src="{_esc(logo)}" '
                f'alt="logo" data-editable="false">')
    return (f'<span class="brand-logo-placeholder{pos_cls}" '
            f'data-editable="true">LOGO</span>')


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
    # Step 5 新增元素
    "ui_mock": render_ui_mock,
    "conclusion_band": render_conclusion_band,
    # S8 Wave B（C-E2 三件套）
    "sla_block": render_sla_block,
    "profile_card": render_profile_card,
    "logo_wall": render_logo_wall,
}


def render_chrome_html(elem_type, normalized, pages=None):
    """页面构件总分派。未知 type 返回 None（调用方走既有未知元素路径）。"""
    if elem_type == "topnav":
        return render_topnav(normalized, pages=pages)
    renderer = CHROME_RENDERERS.get(elem_type)
    if renderer is None:
        return None
    return renderer(normalized)
