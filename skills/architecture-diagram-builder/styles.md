# 视觉渲染规范（styles.md）

> 本文件从 reference.md 拆分出来，专门用于 HTML 架构图的视觉渲染。
> **使用时机**：写完 4A 文档后，合并检查通过，最后根据文档画图时读取本文件。

---

## v4.0 重要变化：共享视觉语言已委托

**配色、语义色、字体、层叠行、集成双框、时间线、Fit-Gap 三色、映射图组件（archimate/automation/cross-table/fit-table）的唯一事实源已迁移到 `docs/diagram_visual_design_v1_2026-07-19.md`**（27 种 diagram 视觉规范 v1.2）。

画 4A 架构图时：
- 通用视觉规则（配色/字体/语义色纪律）→ 读设计规范 §1-§2
- 泳道/层叠/集成/时间线/矩阵/映射图画法 → 读设计规范 §3（对应子类型条目）
- **本文件只保留 architecture-diagram-builder 独有内容**：6 层架构元素体系、原则卡、简易分栏、渲染规则、EXHIBIT 约定

两个体系的分工：
- 手工画 4A 架构图（本 skill 流程）→ 本文件 + 设计规范
- spec 结构化图形（`type: diagram`，html-build 双输出）→ 设计规范 + `_renderer/diagram/`

---

## 核心原则

1. **保证 HTML 和 PPT 的绝对精确一致**：直接手写 HTML/CSS，不用 Mermaid 等声明式语法，确保渲染效果完全可控
2. **只用蓝+绿两色**，不用橙/红/黄（除非 Fit-Gap 等特殊场景）
3. **蓝底白字 / 蓝底黑字** 为主，绿色为辅助色
4. **字体统一**：中文微软雅黑，西文 Helvetica（回落 Arial），标题加粗
5. **最小字号 12px**，推荐 14px，投屏可读
6. **多用背景色区分层级**，少用边框

配色与 CSS 变量：**以 `docs/diagram_visual_design_v1_2026-07-19.md` §2 设计令牌为准**（蓝 `#1B5E8A` / 绿 `#2F7D5F` 低饱和体系 + 语义色纪律）。

---

## 6 层架构元素（蓝+绿配色 · v6 确认版）

| 层级 | 背景 | 文字 | 说明 |
|---|---|---|---|
| AD 应用域 | `--blue` 深蓝底 | 白字 | 最外层大容器，包裹全部 |
| AG 应用组 | `--blue-light` 浅蓝底 | `--blue` 蓝字 | 嵌套在 AD 内 |
| APP 一级模块 | `--blue` 深蓝底 | 白字 | 卡片标题，居中，3 列网格 |
| ABB 二级模块 | `--green` 深绿底 | 白字 | Grid 左列固定 110px |
| 功能项 | `--green-light` 浅绿底 | `--green` 绿字 | Grid 右列，flex wrap |
| 功能子项 | 白底 | `--text-sub` 灰字 | 不画，仅文档 |

**布局规则**：
- AD 用 `.ad-box` 深蓝大容器包裹整个架构图
- AG 用 `.ag-box` 浅蓝嵌套在 AD 内
- APP 用 `.app-grid` 3 列网格，每个 APP 是 `.app-card` 白底卡片
- APP 标题 `.app-name` 居中显示
- ABB 行用 `.abb-row` Grid 布局：左列 ABB 固定 110px，右列功能项自适应
- 核心 APP 加 `.core` 类（红框），新增 APP 加 `.new-app` 类（绿框）

```css
/* ========== AD 应用域（深蓝大容器） ========== */
.ad-box {
  background: var(--blue);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
}
.ad-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.ad-label {
  background: rgba(255,255,255,0.18);
  color: white;
  border-radius: 6px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 700;
  min-width: 70px;
  text-align: center;
}
.ad-title { font-size: 17px; font-weight: 700; color: white; }
.ad-meta { font-size: 12px; color: rgba(255,255,255,0.6); margin-top: 2px; }

/* ========== AG 应用组（浅蓝嵌套） ========== */
.ag-box {
  background: var(--blue-light);
  border-radius: 10px;
  padding: 20px;
  margin-left: 20px;
}
.ag-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.ag-label {
  background: var(--blue);
  color: white;
  border-radius: 4px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
}
.ag-title { font-size: 15px; font-weight: 700; color: var(--blue); }

/* ========== APP 网格（3 列） ========== */
.app-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

/* ========== APP 卡片 ========== */
.app-card {
  background: var(--card);
  border-radius: 8px;
  padding: 16px 16px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
}
.app-card.core {
  border: 2px solid var(--core-red);
  background: #FEFAFA;
}
.app-card.new-app {
  border: 2px solid var(--green);
  background: var(--green-light);
}

/* APP 标题（居中） */
.app-name {
  background: var(--blue);
  color: white;
  border-radius: 6px;
  padding: 9px 16px;
  font-size: 14px;
  font-weight: 700;
  margin: 0 auto 14px;
  display: block;
  text-align: center;
  width: fit-content;
  min-width: 120px;
}
.app-card.core .app-name { background: var(--core-red); }
.app-card.new-app .app-name { background: var(--green); }

/* ========== ABB 行（Grid 对齐：左列固定 110px，右列自适应） ========== */
.abb-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 8px;
  align-items: start;
  margin-bottom: 8px;
}
.abb-name {
  background: var(--green);
  color: white;
  border-radius: 5px;
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
}
.func-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.func-item {
  background: var(--green-light);
  color: var(--green);
  border: 1px solid rgba(47,125,95,0.2);
  border-radius: 4px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
```

---

## 架构图独有组件

### 简易分栏泳道（BA 用，非流程泳道）

> 这是 div 列式简易分栏，用于 BA 文档里按角色罗列要点。
> **流程泳道图（带节点箭头）请用设计规范 §3.1 flow/swimlane（SVG）。**

```css
.swimlane {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin: 20px 0;
}
.swim-col {
  background: var(--card);
  border-radius: 8px;
  padding: 0;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.swim-col-header {
  background: var(--blue);
  color: white;
  font-size: 14px;
  font-weight: 700;
  padding: 12px 16px;
  text-align: center;
}
.swim-col .step {
  background: var(--blue-light);
  color: var(--blue);
  border-radius: 6px;
  padding: 10px 14px;
  margin: 8px 12px;
  font-size: 13px;
  font-weight: 600;
}
```

### 原则卡

```css
.principle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin: 20px 0;
}
.principle-card {
  border-left: 4px solid var(--blue);
  padding: 16px 20px;
  background: var(--blue-light);
  border-radius: 0 8px 8px 0;
}
.principle-card .title { font-weight: 700; color: var(--blue); font-size: 16px; }
.principle-card .reason { font-size: 13px; color: var(--text-sub); margin-top: 6px; }
```

---

## 渲染规则

1. **每个 section 必须有图**：不能只有文字 bullet，必须有嵌套 div 框或 HTML 表格
2. **禁止 Mermaid**：所有图用 HTML/CSS 嵌套 div 框实现
3. **嵌套 div 框用 CSS 类**：`.ad-box` / `.ag-box` / `.app-card` / `.abb-row` / `.func-item`
4. **表格必须有三色标注**（Fit-Gap 场景）：Fit 绿底 / Partial 黄底 / Gap 红底（画法见设计规范 §3.3 fit_gap）
5. **图必须有标题**：每个嵌套框上方有 `### EXHIBIT N: 标题`
6. **配色统一**：只用蓝+绿，不用橙/红/黄（Fit-Gap 除外）
7. **布局规则**：AD 大容器 → AG 嵌套 → APP 3 列网格卡片 → ABB 行 Grid 对齐（左 110px + 右自适应）
8. **颜色柔和**：使用低饱和配色，避免过于鲜艳
9. **对齐纪律**：行列对齐靠 grid 结构绑定，禁止多列独立堆叠手写 margin 凑数（设计规范 §3.5 同约）

### 异常流规则（reference.md §5.2 强制）

EXHIBIT 6（流程-服务-单据）异常流/回流**必须**用红色虚线标注，按 `.exception-note` 类。
EXHIBIT 6-9 四张映射图的画法（`.archimate` / `.automation-table` / `.cross-table` / `.fit-table`）：
**以设计规范 §3.5 对应子类型为准**（process_service_doc_mapping / automation_table / cross_4a_reconcile / fit_gap），配色语义一致（蓝=人工/BA · 绿=系统/AA · 青=单据/TA · 紫=DA · 橙=决策/部分 · 红=异常/缺口）。

---

## 文档版本

- **版本**：v4.0（2026-07-19 · 共享视觉语言委托 `docs/diagram_visual_design_v1`，本文件保留架构图独有体系）
- **创建日期**：2026-07-07
- **历史**：v3.0 降低饱和度 + 卡片网格布局 + ABB 行对齐；v3.1 补充 TA 层叠色 + EXHIBIT 6/7/8/9 映射图组件；v4.0 删除与设计规范重复部分（配色变量/层叠行/集成双框/时间线/Fit-Gap/映射图组件）
- **用途**：HTML 架构图的视觉渲染规范（architecture-diagram-builder 专用层）
- **确认状态**：用户已确认 v6 版本 UI；v4.0 委托结构
