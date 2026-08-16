---
name: ui-design-system
version: "1.0"
description: "非固定部分（页眉页脚/布局/配色/组件）的统一 UI 规范。当用户说生成 HTML / 做 PPT / UI 规范 / 页面布局 / 调试样式 / 改配色 / 页眉页脚时调用。Unified UI spec for headers/footers, layout, colors, and component patterns across HTML and PPT outputs."
---

# UI Design System

产出物的 UI 骨架规范。Renderer 的固定部分（slide master / HTML head）由 `_renderer/` 代码控制，本 Skill 定义**非固定部分**：页眉页脚结构、布局网格、配色引用、组件模式、调试流程。

## 1. 页眉页脚规范

### HTML

- **header**：`<header>` 标签，含标题（h1）+ 副标题（p.subtitle）+ 渐变分隔线（`border-bottom: 3px solid var(--accent)`）
- **footer**：`<footer>` 标签，含作者 + 日期 + 版本号
- 不同内容类型微调：
  - 架构图：header 加面包屑（客户名 > 系统名 > 架构图）
  - 需求清单：header 加版本标记（v0/v1/终稿）
  - 门户原型：header 加导航栏（首页 / 功能 / 报价）

### PPT

- **顶栏**：`header_bar` 背景色（styles.json `slides.header_bar`）+ 标题文字 + 右侧页码
- **底栏**：分隔线（`footer_border` 色）+ 左侧日期 + 右侧客户名
- 架构图页：顶栏加"第 N 层"标记

## 2. 布局规则

- **网格系统**：12 列网格，间距 24px
- **间距体系**：4 / 8 / 16 / 24 / 32 / 48px（Tailwind 对应：gap-1 到 gap-12）
- **响应式断点**：768px（移动端单列）
- **最大宽度**：max-w-6xl（1152px），内容居中
- **卡片间距**：24px（大屏）/ 16px（小屏）

## 3. 配色指引

引用 `_renderer/styles.json` 的 CSS 变量名，不重复定义色值。

### 变量映射

| styles.json 路径 | CSS 变量 | 用途 |
|---|---|---|
| `colors.primary` | `--primary` | 标题、页眉背景 |
| `colors.accent` | `--accent` | CTA 按钮、高亮、强调 |
| `colors.background` | `--bg` | 页面背景 |
| `html.card_bg` | `--card-bg` | 卡片背景 |
| `html.border` | `--border` | 边框、分隔线 |
| `html.heading_color` | `--heading` | 标题文字色 |
| `html.text_color` | `--text` | 正文文字色 |

### 禁用色

- 纯黑 `#000000`：大面积背景禁用（gov 风格除外）
- 纯白 `#FFFFFF`：大面积背景禁用，用 `#f7fafc` / `#f8fafc` 替代
- 高饱和红/绿/蓝：仅用于状态标记（success/warning/error），不用于装饰

### 强调色使用场景

- `accent`：CTA 按钮、高亮文字、图标、分隔线
- `primary`：标题文字、页眉背景、表头背景
- 不用 `accent` 做大面积背景

## 4. 组件模式

### 卡片

```css
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  padding: 24px;
}
```

### 表格

- 表头：`table_header_bg` 背景色 + 白色文字
- 斑马纹：偶数行 `rgba(0,0,0,0.02)` 背景
- hover：`rgba(0,0,0,0.05)` 背景
- 圆角：仅外层容器，单元格不单独圆角

### 时间线

- 左侧竖线：2px solid `--accent`
- 节点圆点：12px，`--accent` 背景，白色边框 3px
- 右侧内容：卡片样式，缩进 24px

### 树形图

- 缩进：20px/层
- 连接线：1px solid `--border`，L 形
- 折叠箭头：CSS 三角形，8px

### 标准组件 CSS 代码片段

可在 HTML spec 的 `custom_css` 字段中直接引用上述组件类名。

## 5. 调试指引

- **HTML 调试**：`python _cli.py html-build <spec> --client <客户>` 后用浏览器打开 output 文件
- **PPT 调试**：改单页走 HTML 可编辑模式（`html-build` 双输出），再 `python _cli.py pptd-build <工程目录>/<主>.pptd` 重建；旧命令 `ppt-page`/`ppt-build`/`html-to-ppt` 已退役（D-090）
- **styles.json 修改后**：重新 build 即可生效（每次 `Renderer.__init__` 重读 styles.json）
- **verify 只检查格式**：不检查 UI 质量。UI 质量靠 `python _cli.py review <文件> --client <客户>` 审查
- **配色检查**：用浏览器开发者工具检查 CSS 变量是否正确加载

## 4 种 UI 风格选择

styles.json 定义 4 种风格，由 AI 按客户行业/场景选择（写进 spec 的 `style` 字段，
或 html-build 时用 `--style` 覆盖）：

| 风格 | 适用场景 | 关键词 | 特点 |
|------|---------|------|------|
| `education` | 教育/学校 | 教育/学校/校园/师生 | 深蓝白、楷体仿宋 |
| `enterprise` | 企业咨询/汇报 | IT/信息化/咨询/战略/汇报/高管 | 深蓝白、Microsoft YaHei |
| `tech` | 科技/互联网/Demo | demo/演示/极简/原型/POC/科技 | 暗色主题、Noto Sans SC |
| `gov` | 政府公文 | 政府/公文/机关/政务 | 黑红白、仿宋公文体 |

无法确定时，AI 应问用户选哪种风格（缺省 enterprise）。

## 与 architecture-diagram-builder 的关系

- 本 Skill：通用 UI 骨架（页眉页脚、布局、基础组件、配色指引）
- `architecture-diagram-builder/styles.md`：架构图专用视觉（6 层架构元素、泳道、Fit-Gap 配色）
- 两者互补不重叠。架构图页面同时遵守两者。

## diagram 图形元素版式约束（27 种，v1.2 定稿）

唯一事实源：`docs/diagram_visual_design_v1_2026-07-19.md`。要点：

- **配色**：蓝+绿低饱和变量（不写 hex 字面量）；语义色纪律——蓝=主体/基准，绿=系统/目标，橙=决策/部分，红=异常（<5%），紫/青/灰=架构分层，青=单据
- **字体**：中文微软雅黑 / 西文 Helvetica（回落 Arial）；标题与强调加粗（600-700）
- **技术分流**：连接型 8 种（flow 5 + ER 2 + data_flow）内联 SVG；容器型 19 种 div/table + flex/grid
- **对齐纪律**：行列对齐必须靠 grid 结构绑定，禁止三列独立堆叠手写 margin 凑数（#24 业务能力树教训）
- **PPT 映射**：连接线全原生 connector/preset shape（§4.1 契约），禁图像、禁 freeform custGeom
- 每图独立 `<section class="diagram">` 容器 + `.dg-title` + 可选 `.dg-desc`

## v2.0 主题 tokens（2026-07-25 冻结，consulting_kpmg / legacy_bluegreen 双包）

spec 只写主题名（`theme: consulting_kpmg | legacy_bluegreen`，缺省 legacy），禁 hex 字面量；渲染侧一律 CSS 变量（--t- 前缀），禁硬编码。

### consulting_kpmg v2 tokens（2026-08-13 提饱和去灰升级）

```
主色    #00338D   深色 #051C2C   中间 #3D6AA8
强调    #FFE600
角色    biz #00338D / legal #E11D48 / fin #0D9488 / sys #7C3AED / ext #EA580C
三态    lit:  border #059669  bg #ECFDF5  text #047857
        part: border #EA580C  bg #FFF7ED  text #C2410C
        gap:  border #DC2626(虚线1.5px)  bg #FEF2F2  text #B91C1C
文字    primary #0F172A / secondary #475569 / tertiary #64748B
底/边   bg-soft #F8FAFC / bg-muted #F1F5F9 / border #CBD5E1
hero    渐变 135deg #051C2C → #00338D
字体    "Helvetica Neue", Helvetica, Arial, "Microsoft YaHei", "微软雅黑", sans-serif
```

legacy_bluegreen = v1.2 冻结蓝绿原样收编（老 spec 缺省，视觉不变）。

### 三态使用纪律

- 三态成组出现：绿实底=已点亮 / 朱橙=部分 / 红虚线=缺口；**缺口必须画出**（点亮对比才可见）
- 覆盖率表达：废弃细覆盖率条，统一大百分比数字 + 点亮分数（`88% · 点亮 15/17`，24px/800/tabular-nums，按态着色）
- 角色色 >2 必须出 legend（flow_rows 自动生成，其他图手写 legend_bar）

### 投影安全原则

- 投影仪反射光+环境光洗色：中高饱和度 + 明度对比（30-70% 饱和区间）
- 三态色高区分 + 投影安全（2026-08-13 提饱和去灰：缺口灰改红更醒目；上文值勿改）
- 禁浅灰低对比文字；虚线 ≥1.5px 深灰（浅虚线投影消失）
- chip/徽章边框 1.5px（投影可读）

### 中文排版细节

- 全中文大标题字号降一档（hero 30px、action_title 21px）
- 数字 `font-variant-numeric: tabular-nums`（`.num` 类）
- 字号分级：页标题 20-24 / 节标题 16-18 / 正文 12-14 / 备注 10-11（px）
- 单行文本（标题/标签/数字/导航）pptd 侧必须显式 `wrap: false`；
  文字框高 ≥ fontSize × 1.3 × N 行 + 段距；修溢出优先级：凝练文案 > 换行 > 扩框高

### v3.0 中文排版补充（2026-08-11，signal 蓝本 + 同事经验）

- 盘古之白：中英混排加空格（`使用 Claude` 非 `使用Claude`）
- 全中文大标题无句号；正文行高 1.6-1.8，标题 1.2-1.3
- 中文无斜体轴：强调用颜色（--t-accent）+ 字重，不用 `font-style: italic`
- 断行：正文一律 `word-break: normal; overflow-wrap: normal`（防「80000多家」拆行，已全局落地 page_chrome）
- 中文标题字号分档：≤8 字用大字号，3 行+降一档（px 体系，对照上文）

### v3.0 反 AI Slop 视觉清单（2026-08-11，借鉴 frontend-slides + huashu-design）

生成任何 HTML/PPT 前对照，违反任一即返工：

| 检查项 | 规则 |
|--------|------|
| 标题字体 | 禁 Inter/Roboto/Arial 作 display 字体（正文可用） |
| 配色 | 禁紫色渐变白底；禁大段纯黑底+白字堆叠 |
| 图标 | 禁 emoji 作功能图标（用语义色块/几何） |
| 卡片 | 禁"圆角卡片+左彩色 border"的千篇一律组合 |
| 标题位置 | 方案正文标题一律左对齐，禁居中（封面除外） |
| 间距 | 禁二次叠加水平 padding（对齐 P0 法则） |

## 6. 审美审查框架（三层缺失诊断，2026-07-31 定稿）

审查产出物截图（HTML/PPT）时，按此三层诊断"简单感/不高级"的根源，
**不只看错位/配色/空白这些表面项**，直接对标老材料密度：

1. **页面级版式语言整体缺位**：页是否有完整设计语言——渐变头图横幅（含版本/日期/主体
   meta）、顶部 tab 导航、章节编号（一、二、三 + 菱形装饰）、左上 EX-XX 编号 + 右上页眉、
   底部图例条、底部三联信息卡、行内红色强调文字；还是"图是图、页是页"，diagram 孤立落在
   白页上只有 dg-title + 图体？
2. **图是单件 vs 组合体**：老材料一张"图"= 流程图 + 图例 + 底部三信息卡的组合；CBM 矩阵 =
   编号标签 + 深色表头 + 红框徽章阵列 + 图例条。渲染器一个 diagram 元素是否只有一张图、
   没有 stats / legend / notes / callout 这些附件槽位？
3. **视觉词汇单一**：多种子类型是否共用一套节点语言（白底蓝框 + 左色条 + 序号点）导致
   每页气质雷同；有无分组层次、数字强调、留白是否失衡。

输出格式：A. 诊断结论（对照三层逐条） B. 按优先级排的可执行改进（具体到加什么元素 /
改什么样式）。

用法：`python _cli.py vision-describe <截图> --prompt "<第1/2/3层问题 + 输出格式>"`。
若 vision-describe 返回空（视觉 key 未配置 / agent 自身多模态 / 网络失败），
必须明确告知用户「视觉自检未执行」，不得声称已自检；可改为人工截图抽查。
媒介差异要客观指出（16:9 PPT 页 vs 长滚动 HTML 页），但 PPT 侧必须做到老材料那种密度。
