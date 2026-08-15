---
name: spec-writing-guide
version: "1.3"
description: "定义 spec.yml 字段规则、容量预算和 confirmed 门禁。当用户说写 spec / 改 spec / 生成 spec / spec-gen / RenderBlockedError 时调用。Defines spec.yml field rules, layout catalog, capacity budget, and the confirmed:true gate. v1.3: diagram 子类型 33 种全量对齐（含 D-5 pyramid/quadrant、B-7 milestone_gantt）；v1.2: 容量预算表；v1.1: 对齐 spec 协议 v1。"
---

# Spec Writing Guide

`spec.yml` is the contract between user intent and the renderer. Without `confirmed: true`, every `*-build` command raises `RenderBlockedError`. This skill exists because AI used to hallucinate spec fields, invent layouts, and skip the confirmation gate.

**字段与元素的唯一事实源：`docs/spec_protocol_v1.md`（spec 协议 v1，2026-07-20）。** 本 skill 只讲流程；字段表、能力矩阵、降级行为以协议文档为准。

## When to Invoke

- User says: 写 spec / 改 spec / 生成 spec / spec-gen
- `spec-gen` or `outline-to-spec` returned a draft and you need to finalize it
- `RenderBlockedError: spec not confirmed` occurred
- Before any `html-build` / `docx-build` / `quote-build` / `pptd-gen` call (preflight check)

Do NOT invoke for: reading an already-confirmed spec, or non-spec YAML files.

## The confirmed:true Gate (L3 hard constraint)

[_cli_guards.py:16-21](file:///d:/knowledge%20base/_cli_guards.py) — `require_confirmed(spec)`：未确认即 `raise RenderBlockedError(...)`（判定单点 `is_confirmed`，`_cli_guards.py:6-13`；Renderer 在 `_renderer/__init__.py:97-98` 调用）。

Workflow:

1. Generate draft spec (via `spec-gen` / `outline-to-spec` / manual write)
2. **Show the draft to the user** and explicitly ask: "spec 草稿已生成，请确认内容是否正确？确认后我会加 `confirmed: true` 并开始生成。"
3. Only after the user confirms, add `confirmed: true` to the spec top level
4. Then call `html-build` / `ppt-build` / etc.

Never set `confirmed: true` proactively without user confirmation. This is the L3 boundary — spec 中没有的内容一律不写.

## Spec Type 1 — Proposal Spec (HTML/PPT/DOCX)

Full field reference: `docs/spec_protocol_v1.md`（顶层字段表 + 每种元素的正典/兼容字段 + 三端能力矩阵）。写任何字段前先查它。

### Top-level fields

```yaml
project: "方案标题"
author: "咨询团队"
date: "2026-07-04"
style: "enterprise"           # education | enterprise | tech | gov（旧字段仍兼容，_renderer 默认 enterprise）
theme: "consulting_kpmg"      # consulting_kpmg | legacy_bluegreen | corporate_navy | product_charcoal（v2.0，spec 禁 hex，配色进主题包）
scenario: "report"            # report | product_intro | training（缺省 report，见下）
container: "scroll"           # scroll | chapters | stage | report（缺省 scroll，批次 A）
simulation: "none"            # none | static | interactive | guided（缺省 none，批次 A 预留）
confirmed: true               # MANDATORY before any *-build call (gate)

document:
  title: "主标题"
  subtitle: "副标题"
  cover:
    show_date: true
    show_author: true
    show_logo: false

pages:                         # array of page objects
  - id: <unique_id>
    title: "<page title>"
    layout: "<layout_name>"
    elements: [...]
```

### 文档级新字段（批次 A，2026-08-13，观察/预留）

以下字段当前只做 schema 合法值校验 + verify 观察报告，渲染层暂不消费（观察期内，§8 晋级流程）。

**container（叙事容器）**：spec 顶层可选，合法值 `scroll | chapters | stage | report`，缺省 `scroll`。
- 语义：内容叙事容器形态。scroll=滚动长文（现状默认）；chapters=分章节；stage=舞台演示；report=报告式。
- 反例：`container: flipbook`（不在白名单，报错）

**simulation（仿真模式）**：spec 顶层可选，合法值 `none | static | interactive | guided`，缺省 `none`。
- 语义：仿真组件预留字段（仿真组件挂起，字段先占位）。写 spec 保持缺省 none 即可。

**type_roles（字号角色制）**：spec 顶层可选块，角色名 → size（数值或 `{size: 数值}`）。
- 角色名白名单 6 个：`title / subtitle / body / caption / footnote / hero_number`
- 不写零报错（完全向后兼容）；写了就校验角色名合法 + size 为数值
- 反例：`type_roles: {heading: 40}`（heading 不在白名单）、`type_roles: {title: "大"}`（size 非数值）

```yaml
type_roles:
  title: {size: 40}
  body: 16
  caption: 12
```

**font_role（元素级角色）**：任意元素的通用可选属性，角色名 ∈ 同一白名单。
- 未声明不报错；声明了非法角色名报错
- 反例：`{type: text, text: "x", font_role: banner}`（banner 不在白名单）
- 渲染优先级（规划）：元素显式 size > font_role > 默认（渲染解析待接入，当前仅校验）

### Layout catalog (page metadata)

`layout` 字段由生成器写入，**协议 v1 三端渲染器不消费它**——页面内容完全由 `elements[]` 决定（协议文档 §2）。以下仅为生成器沿用的页面意图分类，写 spec 时重点选对元素：

| Layout | Use for | Key elements |
|---|---|---|
| `title_body` | Overview / text-heavy page | `text` + `heading` |
| `cards_3` | Pain points / 3-column comparison | `cards` (title/tag/body/highlight) |
| `blueprint` / `function_architecture` | Architecture / capability hierarchy | `diagram`（org_tree / biz_capability_tree / architecture 系）或 `bullets`+`cards` 组合 |
| `timeline` | Phase plan / roadmap | `phases` (name/desc/actions) |
| `table` | Budget / matrix / data | `table` (headers/rows) |
| `summary` | Closing / next steps | `text` + `bullets` |

### Element types（协议 v1 合法全集，共 10 种）

只用了这 10 种——**未知/拼错的 type 现在会报 schema 错误、渲染进 report.skipped、verify 判 FAIL**（以前是静默跳过，元素直接消失）。字段细节见协议文档 §3-§5。

- `text` — `{content, role?}`（兼容字段 `text`）
- `heading` — `{text, level?}`（level 缺省 2，1-7；兼容 `title|content`）。**三端均可用**
- `bullets` — `items: [string]`
- `cards` — array of `{title, body, tag?, highlight?}`（tag/highlight 仅 HTML 端渲染）
- `phases` — array of `{name, desc, actions: [string]}`。**正典字段是 name/desc/actions**；`label/goal`、`phase/title/items` 是存量兼容写法，新写 spec 不要用。注意 PPTD 端只发 name/desc 不发 actions
- `table` — `{headers: [string], rows: [[string]]}`（每行列数须与 headers 齐）
- `pullquote` — `{content, cite?}`。**三端均可用**（DOCX 端为缩进斜体引文）
- `architecture_4a` — `{layers: [{name, components[]}]}`。**仅 DOCX 原生渲染，HTML/PPTD 降级为 `[4A 架构图] 本节内容请见 Word 版`**——只建议用于 DOCX 场景的 spec；HTML/PPT 架构图用 `diagram`
- `diagram` — 结构化图形（见下节，D-087）。**DOCX 端降级为 `[架构图：{title}] 请见 HTML/PPT 版`**——写 spec 时知道只有 HTML/PPT 才有图
- `product_intro_placeholder` — 产品介绍占位（D-089）。DOCX 端同样降级为文本提示

### diagram 图形元素（HTML/PPT 双输出，同源）

视觉规范：`docs/diagram_visual_design_v1_2026-07-19.md` v1.3（画法 + 字段全表 + §4.2 图形铁律 / §4.3 块箭头 / §4.4 adj 语义表 / §4.5 布尔切分层级图 / §4.6 连接线路由）；子类型必填字段以协议文档 §5 为准（与 `_renderer/schema.py` 的 DIAGRAM_SCHEMA 一致，写错必填字段会报 schema 错误）。
**写作约定：一页一图**（_build_content_page 无分页，多张大图会溢出页面）。
**端能力：HTML/PPTD 原生渲染，DOCX 端降级为文本提示**——同一份 spec 要出 DOCX 时，关键信息别只放在图里。

```yaml
- type: diagram
  diagram_type: flow | architecture | matrix | timeline | relationship
  subtype: <子类型>
  title: "图的标题"      # 必填
  desc: "说明（可选）"
```

子类型与专有字段（**33 种已全部实现**：flow 6 / architecture 7 / matrix 5 / timeline 4 / relationship 11，含 D-5 pyramid、quadrant 与 B-7 milestone_gantt；以下为高频示例，全量字段表见设计规范 §3 与协议文档 §5）：

```yaml
# flow/sequence 顺序流程图：steps[].type = start|task|system|decision|end|doc
- type: diagram
  diagram_type: flow
  subtype: sequence
  title: "费用报销流程"
  steps:
    - {label: "开始", type: start}
    - {label: "提交报销单", desc: "员工录入"}
    - {label: "财务记账", type: system, desc: "自动凭证"}
    - {label: "结束", type: end}

# flow/swimlane 泳道图：lanes + steps[].lane；type: doc 为单据便签（attach 挂接）
- type: diagram
  diagram_type: flow
  subtype: swimlane
  title: "客户主数据建立流程"
  lanes: [{name: "平台"}, {name: "SAP"}]
  steps:
    - {label: "创建主数据", lane: "平台"}
    - {label: "推送 SAP", lane: "平台", note: "SOAP 同步"}
    - {label: "SAP 接收", lane: "SAP", type: system}
    - {label: "统一管理", lane: "平台"}
    - {label: "主数据报文", lane: "平台", type: doc, attach: "推送 SAP"}

# architecture/4a、layered：layers[{name, desc, components[]}]
- {type: diagram, diagram_type: architecture, subtype: 4a, title: "企业 4A 架构",
   layers: [{name: "业务架构 BA", components: ["客户管理", "订单管理"]},
            {name: "应用架构 AA", components: ["CRM", "ERP"]},
            {name: "数据架构 DA", components: ["主数据"]},
            {name: "技术架构 TA", components: ["云平台"]}]}

# matrix/fit_gap：requirements × products，cells[].match = fit|partial|gap
- {type: diagram, diagram_type: matrix, subtype: fit_gap, title: "Fit-Gap",
   requirements: ["需求1"], products: ["我方", "竞品B"],
   cells: [{req: "需求1", product: "我方", match: fit, note: "原生支持"}]}

# matrix/capability_map 业务能力点亮图：chip 三态 lit|partial|none
- {type: diagram, diagram_type: matrix, subtype: capability_map, title: "能力点亮图",
   stats: [{label: "能力项", value: "18"}, {label: "覆盖率", value: "56%"}],
   sections: [{name: "Execute · 业务执行层",
     capabilities: [{code: "B1", name: "销售与订单", status: lit, system: "CRM+ERP",
       items: [{name: "客户管理", status: lit}, {name: "质量追溯", status: none}]}]}],
   systems_inventory: [{name: "ERP", pts: "9", detail: "订单/采购/财务"}]}

# timeline/horizontal：milestones[{label, date, desc}]
- {type: diagram, diagram_type: timeline, subtype: horizontal, title: "实施路线图",
   milestones: [{label: "启动", date: "Q1", desc: "蓝图"}, {label: "推广", date: "Q4", desc: "移交"}]}

# timeline/milestone_gantt：任务轨×里程碑×依赖，按周铺（B-7）
- {type: diagram, diagram_type: timeline, subtype: milestone_gantt, title: "实施路线图",
   columns: ["W1", "W2", "W3", "W4", "W5", "W6"],
   tasks: [{name: "需求调研", start: 0, span: 2, tone: blue, deps: [1]},
           {name: "方案设计", start: 1, span: 3, tone: green}],
   markers: [{col: 5, label: "评审"}]}
# 校验：columns/tasks 必填非空；每项 name 必填；start≥0、span≥1；tone ∈ blue/green/teal/orange/purple；deps 为任务索引（可选）；容量 ≤10 任务

# relationship/org_tree：root 嵌套 children
- {type: diagram, diagram_type: relationship, subtype: org_tree, title: "实施团队",
   root: {name: "项目总监", desc: "整体交付",
     children: [{name: "项目经理", children: [{name: "需求组"}, {name: "实施组"]}]}

# architecture/pyramid 层级金字塔（D-5）：levels 2-6 层，每层 title + desc
- {type: diagram, diagram_type: architecture, subtype: pyramid, title: "能力分层",
   levels: [{title: "战略层", desc: "决策支持"},
            {title: "管理层", desc: "运营管控"},
            {title: "执行层", desc: "业务操作"}]}
# 校验：levels 2-6 层；每层 title 必填（desc 可选）

# matrix/quadrant 四象限（D-5）：两轴标签 + 恰好 4 个象限（tl/tr/bl/br 顺序）
- {type: diagram, diagram_type: matrix, subtype: quadrant, title: "优先级四象限",
   axes: {x: "价值", y: "成本"},
   quads: [{title: "高价值低成本", items: ["优先做"]},
           {title: "高价值高成本", items: ["重点投入"]},
           {title: "低价值低成本", items: ["标准化"]},
           {title: "低价值高成本", items: ["砍掉"]}]}
# 校验：axes.x/axes.y 必填；quads 恰好 4 个，每项 title 必填（items 可选）

# 产品介绍占位（D-089）
- {type: product_intro_placeholder, title: "产品介绍",
   hint: "在此处插入客户产品介绍页", keywords: ["产品A", "模块B"]}
```

P1 写法注意：

- `flow/decision`：decision 步骤用 `alt_next: "<否分支目标 label>"` + `alt_label: "否"`；主线顺序即「是」分支
- `flow/cross_system`：steps 需带 `system: "<系统名>"` 落列；`async: true` 画虚线（异步），`note:` 标接口名
- `flow/parallel`：`sources` 纵排 -> `merge` 汇聚 -> 可选 `after` 后续链
- `architecture/integration` 双形态：点对点给 `source{items}+target{items}+links[mode]`；总线给 `hub+systems`（二选一）
- `architecture/deployment`：`zones[].nodes[]` 嵌套；`links: [{from, to, label}]` from/to 写 zone 名
- `matrix/cbm`：capabilities 元素可为 `{name, heat: strong|mid|weak}` 开热力
- `relationship/er_*`：relations `type: one_to_one|one_to_many|many_to_many`；逻辑 ER 用 `pk/fk/attrs`
- `relationship/data_flow`：nodes `type: source|process|sink|store`；flows `direction: push|pull|bidirectional`
- `relationship/biz_capability_tree`：`groups[].children[].items[]` 三层

**pptd 手写页纪律**（不走 spec diagram、直接写 .page 时必读；真实项目 v14 教训 2026-08-11）：

- 优先走 `type: diagram` 让官方渲染器出图；确需手写时，箭头路由照 `_renderer/diagram/flow.py _pptd_arrow`：吸附节点连接点——同行右缘→左缘直线；错位 `bentConnector3` 肘形，出底入顶、不穿节点盒
- 禁悬空箭头（固定高度的列间水平箭头对不齐节点，用户判"没法看"）；列内节点 hug 高度、文字可换行、上下分布布满列体，列变窄给箭头留通道
- **图形铁律（选择门）**：原生 preset/chart > 布尔切分 > 手写 freeform path（禁用）。shape 名必须在 `_pptd_convert._SHAPE_NAME_MAP` / `_CONNECTOR_MAP` 白名单内，diagram 图形区域禁 image（verify 观察模式拦截）
- **块箭头**：实心方向用块箭头 preset（`rightArrow`/`leftRightArrow`/`upDownArrow`/`pentagon`），细关系（接口/数据流连线）用 connector

## 容量预算（写 spec 时遵守，防 Plan-Delivery Gap）

页面 1280×720。**写作时就不许超**，不要等 lint 打回（依据：真实项目 v7 实测 + 规约 docs/思维链预算与验证回路规约_v1.1_2026-07-21.md §5 L0）：

| 元素 | 预算 | 实测出处 |
|---|---|---|
| `table` | ≤11 行、单格 ≤20 字；表后还有 pullquote 时 ≤9 行 | 13 行长文案致 pullquote 越界（v7 P11） |
| `pullquote` | content ≤2 行（≈60 字）、cite ≤15 字；与表格同页时文字再减半 | 同上 |
| `architecture/4a`、`layered` | **禁写 desc**（渲染器 desc/chips 硬编码必撞，known_issue）；信息并入 name 或页面 pullquote | desc 被 chips 压成乱码（v7 P2） |
| `timeline/horizontal` | ≤4 个 milestones、desc ≤30 字 | 4 节点 40 字 desc 勉强通过（v7 P17） |
| `flow/cross_system` | ≤6 个系统列、note ≤12 字 | 6 列连线拥挤 warning（v7 P15） |
| `architecture/deployment` | 跨 zone 的 link **不写 label**（被 zone 背景遮），信息并入节点 desc | label 被遮显示不全（v7 P19） |
| `cards` | ≤3 张/行、body ≤3 行 | — |
| 页面标题 | ≤30 字 | — |

一页一图（既有约定不变）。**超预算的正确做法不是硬塞，是拆页或精简文案。**

## Spec Type 2 — Quote Spec

Full reference: `_knowledge/clients/蓝海集团/蓝海集团_quote_spec.yml`.

```yaml
quote:
  client: <客户名>
  contact: <联系人>
  quote_number: <编号>           # e.g. CQ-2026-001
  version: V1.0
  valid_until: <有效期>          # e.g. 2026-07-21
  payment_terms: <付款条款>      # e.g. 3-3-3-1
  global_discount: 1.0           # 1.0 = 无折扣
  sheets:
    - ref: <sheet名>
      sections:
        - id: <section_id>
          total_label: <合计标签>
          items:
            - id: <item_id>
              name: <名称>
              unit_price: <单价>
              quantity: <数量>
```

Quote spec uses `quote-build` (not `html-build`). The `--template` flag selects the layout (default: `一页报价模板`).

## Spec Generation Commands

| Source | Command | Output |
|---|---|---|
| Client material (docx/pdf/md) | `spec-gen <file> --client <客户> --output <spec.yml> [--scene <场景>]` | Proposal spec draft |
| Quote materials dir | `quote-spec-gen <materials_dir> <spec.yml> --client <客户>` | Quote spec draft |
| Outline scenario | `outline-to-spec <场景> --client <客户> --output <spec.yml>` | Proposal spec draft |
| One-shot (mkdir + spec + optional HTML/quote) | `new <客户> [--scene <场景>] [--html] [--quote]` | Full client setup |

All generators produce **drafts without `confirmed: true`**. You must add it manually after user confirmation.

## Input/Output Contract

- **Input**: client material file path OR outline scenario name OR manual spec draft
- **Output**: valid `spec.yml` with `confirmed: true` set (only after user confirmation)
- **Validation**: `python _cli.py verify <output_file>` runs after `*-build`; `theme-verify <output> <客户>` checks permanent-theme keyword coverage

## Examples

### Example 1 — spec-gen then confirm

User: "用这份需求文档生成 spec"

1. `python _cli.py spec-gen 需求.docx --client 蓝海集团 --output spec.yml`
2. Read the draft, present key fields to user: pages count, layouts used, style
3. Ask: "spec 草稿已生成（5 页，含痛点/架构/阶段/预算/总结）。确认无误吗？"
4. User: "确认" → add `confirmed: true` to spec.yml top level
5. Proceed to `html-build`

### Example 2 — Fixing RenderBlockedError

User ran `html-build` and got: `RenderBlockedError: spec.yml 未标记 confirmed: true`

1. Read the spec.yml
2. Show contents to user, ask for confirmation
3. After confirmation, edit spec.yml: add `confirmed: true` at top level (alongside `project`/`author`/`date`)
4. Re-run `html-build`

### Example 3 — Quote spec

User: "出一份报价 spec"

1. Confirm materials are in `_knowledge/clients/{客户}/refs/`
2. `python _cli.py quote-spec-gen _knowledge/clients/蓝海集团/refs _knowledge/clients/蓝海集团/蓝海集团_quote_spec.yml --client 蓝海集团`
3. Show draft: sheets, sections, items, totals
4. After user confirms, add `confirmed: true` at top level (sibling of `quote:`)
5. `python _cli.py quote-build 蓝海集团_quote_spec.yml output/蓝海集团/蓝海集团_报价_v1.html --template 一页报价模板 --client 蓝海集团`

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RenderBlockedError` | spec lacks `confirmed: true` | Confirm with user, add field |
| `RenderBlockedError`（client_name） | `client_name` 字段存在但为空 | 填真实客户名或删掉该字段 |
| verify FAIL：`N 个元素被跳过` | 未知/拼错的元素 type（协议 v1 起不再静默跳过） | 改用协议文档 §3 的 10 种合法 type；常见于旧 spec 的 `tree`/`chart`/`actions` |
| 打印 `[spec校验] ... 缺必填字段` | 元素缺必填字段（如 cards 缺 title、table 行列不齐） | 按协议文档 §4/§5 的必填规则补齐；不阻断生成但渲染会缺内容 |
| DOCX 里出现 `[架构图：...] 请见 HTML/PPT 版` | diagram/占位卡在 DOCX 端无原生渲染（预期降级） | 预期行为；要 DOCX 出架构内容改用 `architecture_4a` 或文字元素 |
| HTML/PPT 里出现 `[4A 架构图] 本节内容请见 Word 版` | `architecture_4a` 仅 DOCX 原生 | 改用 `diagram`（architecture/4a、layered 子类型） |
| `theme-verify` low coverage | Spec content missing permanent-theme keywords from `theme-guard` output | Add keywords to page content, rebuild |
| `ppt-build` crashes on page N | Element type mismatch for that page's layout | Run `ppt-page spec.yml <page>` to isolate, fix element schema |
| Quote `total_label` missing | Section lacks `total_label` field | Add `total_label: <合计标签>` to each section |
| `--style` rejected | Not one of `education/enterprise/tech/gov` | Use a valid style or omit (uses spec `style` field) |

## Anti-patterns (do NOT)

- Set `confirmed: true` before user confirmation
- Use element types outside the protocol v1 list of 10 (`tree`/`chart`/`actions`/拼错的 type）——现在会报 schema 错误并导致 verify FAIL
- 新写 spec 用 phases 的兼容写法（`label/goal`、`phase/title/items`）——正典是 `name/desc/actions`
- 在要出 DOCX 的 spec 里依赖 `diagram` 出图（DOCX 端只有降级文本）；在要出 HTML/PPT 的 spec 里用 `architecture_4a`（会降级）
- Mix proposal spec fields with quote spec fields in one file
- Omit `id` field on pages (renderer uses it for chunking, report定位 and replacement)
- Put vendor names in `cards`/`diagram` content (use system names per project rules)
- Write more pages than the spec needs (HTML 先行, iterate based on user feedback)

## v2.0 页面版式与构件（2026-07-25 冻结，dev_plan_visual_v2_2026-07-25）

### 版式选择（锁定目录制：只能选、不能发明）

页面级 `layout` 字段，受控值 P01-P16（v3.0 扩展 P12/P14/P15/P16，无 P13）；目录不够用 = 扩目录走决策，不在 spec 里自由发挥。

| 编号 | 名称 | 必需构件（顺序） | 可选 | 容量上限 |
|------|------|----------------|---------|---------|
| P01 | 封面 | hero | stat_cards | hero.stats ≤4 |
| P02 | 章节页 | section_tag + action_title | info_cards | info_cards ≤1 组 |
| P03 | 结论摘要 | section_tag + action_title + kpi_cards | info_cards | kpi ≤4 |
| P04 | 痛点矩阵 | section_tag + action_title + pain_cards | legend_bar | pain ≤9 |
| P05 | 流程图页 | section_tag + action_title + diagram(flow 系) + legend_bar | info_cards | 单图 |
| P06 | 架构图页 | section_tag + action_title + diagram(architecture 系) | legend_bar | 单图 |
| P07 | 对比表页 | section_tag + action_title + table | info_cards | table ≤12 行 |
| P08 | 能力地图页 | section_tag + action_title + diagram(matrix 系) + legend_bar | stat_cards | 单图 |
| P09 | 路线图页 | section_tag + action_title + diagram(timeline 系) | info_cards | 单图 |
| P10 | 风险与待确认页 | section_tag + action_title + (table\|info_cards) | qa_block | — |
| P11 | 收尾页 | action_title + info_cards | hero(紧凑) | — |
| P12 | 目录页（v3.0） | section_tag + action_title + toc_cards | — | 卡 ≤8 |
| P14 | 双栏对比页（v3.0） | section_tag + action_title + duo_compare | legend_bar | — |
| P15 | 优缺点清单页（v3.0） | section_tag + action_title + pros_cons | legend_bar | — |
| P16 | CTA 收尾页（v3.0） | action_title + cta_block | — | — |

**内容类型→版式匹配**：封面→P01 / 量化结论·价值→P03 / 痛点→P04 / 流程→P05 / 架构→P06 / 对比·通道→P07 / 能力·点亮·功能清单→P08 / 计划·路线→P09 / 风险·待确认→P10 / 结尾→P11（产品介绍建议 P16 CTA）。

旧 layout 值（title_body/cards_3/blueprint/summary/table/tree/phases/timeline）继续有效按自由流渲染（F9）；不声明 layout 同为自由流。

**主题**：spec 顶层 `theme: consulting_kpmg | legacy_bluegreen | corporate_navy | product_charcoal`（缺省 legacy）；spec 内禁 hex 字面量（v2 spec 机械防线，配色进主题包）。

**场景**（v3.0，批次 A 加 training）：spec 顶层可选 `scenario: report | product_intro | training`（缺省 report）。
- `report`：汇报型（CFO/IT 总监），配 `theme: corporate_navy`，默认 P01-P11 版式
- `product_intro`：产品介绍型，配 `theme: product_charcoal`，收尾页建议 P16 CTA
- `training`：培训/教学型（批次 A 新增，2026-08-13）
- scenario 只作为内容→版式默认映射的参考，不强制主题；两者独立声明
- （注：outline-to-spec 的 P 系映射待 build_elements v2 构件化后接入，当前场景字段先用于校验与文档语义）

**品牌/logo**（v3.0）：spec 顶层可选 `brand`：
```yaml
brand:
  logo: refs/logo.png          # 本地资产（refs/ 或 _assets/），禁外链；缺省占位虚线框
  logo_position: topnav_left   # topnav_left | topnav_right | hero_corner
```

### 新元素写法（10 种页面构件）

```yaml
- type: hero
  eyebrow: "SECTION 0 · 方案总览"
  title: "大标题（全中文降一档）"
  subtitle: "副标题"
  meta: ["版本 v3", "日期 2026-07-25", "主体 蓝海控股"]
  stats: [{value: "202", unit: "功能点", label: "全量替换"}]   # 可选，≤4

- type: section_tag
  index: "SECTION 1"                # 或 "EXHIBIT 1"
  label: "业务背景"

- type: action_title                # 结论式标题：≥12 字且含数字或量化词（verify 检查）
  segments:                          # 行内强调唯一写法（禁 HTML 标签，防注入）
    - {t: "7 大统建系统 202 功能点：OA 平台标准模块直接点亮 "}
    - {t: "74%", hl: yellow}         # hl: yellow|red|green|null
    - {t: "，缺口集中在资产大件管理"}
  sub: "可选副标题/口径说明"

- type: stat_cards
  cards: [{value: "149", unit: "74%", label: "已点亮 · 标准平替", tone: lit}]
  # tone: blue|lit|part|gap → 左色条三态着色

- type: kpi_cards
  cards: [{label: "预算拦截率", from: "0%", to: "100%", note: "事前强控"}]   # ≤4

- type: pain_cards
  cards: [{title: "印章/电子签", level: P1, impact: "4 部门强共性", body: "..."}]
  # level: P0|P1|P2 → 徽章色 P0=红 P1=朱橙 P2=灰；≤9

- type: info_cards
  cards: [{title: "缺口 15 项集中在三处", items: ["...", "..."]}]   # 2-4 联

- type: legend_bar
  items: [{swatch: lit, label: "已点亮 · 标准模块直接平替"}]
  # swatch: lit|part|gap|keep|role_biz|role_legal|role_fin|role_sys|role_ext

- type: qa_block
  items: [{q: "...", a: "..."}]

- type: topnav                      # 仅 HTML；PPT/DOCX 降级页眉文本
  brand: "蓝海控股"
  brand_sub: "私有化 OA 平台"        # 章节锚点由 pages 自动生成
```

### evidence_ledger 证据台账（B-3，批次 B 组件）

```yaml
- type: evidence_ledger             # 每条结论挂证据编号 + 状态，三端原生渲染
  title: "需求覆盖台账"              # 可选
  items:
    - {num: "E-01", conclusion: "OA 平台标准模块覆盖 202 功能点",
       evidence: "分项功能清单 V2.0 §3", status: "已覆盖"}
    - {num: "E-02", conclusion: "缺口集中在资产大件管理",
       evidence: "调研访谈 2026-07", status: "待补"}
```

- 校验：`items` 必填非空；每项 `conclusion`/`evidence` 必填；`num`/`status` 可选
- 容量：≤12 条（超 → warning）；单格 ≤20 字（PPT 端单行截断，长文本会溢出）

### risk_register 风险登记（B-4，批次 B 组件）

```yaml
- type: risk_register              # 风险项 + 等级 + 状态 + 应对，三端原生渲染
  title: "风险控制登记"            # 可选
  items:
    - {risk: "数据迁移失败", level: "高", status: "未解决",
       response: "迁移前全量备份 + 回滚预案"}
    - {risk: "接口联调延期", level: "中", status: "监控中",
       response: "提前两周联调 + 周例会跟踪"}
```

- 校验：`items` 必填非空；每项 `risk`/`response` 必填；`level` 枚举 高/中/低（可选）；`status` 可选
- 容量：≤12 条（超 → warning）；单格 ≤20 字

### raci_matrix 角色责任矩阵（B-5，批次 B 组件）

```yaml
- type: raci_matrix                # 行=任务，列=角色，单元格 R/A/C/I
  title: "角色责任矩阵"            # 可选
  roles: ["甲方项目经理", "我方PM", "我方顾问"]   # 列头
  tasks:
    - {task: "需求调研", cells: {甲方项目经理: "A", 我方PM: "R", 我方顾问: "C"}}
    - {task: "方案设计", cells: {甲方项目经理: "C", 我方PM: "R", 我方顾问: "A"}}
```

- 校验：`roles` 必填非空；`tasks` 必填非空；每项 `task` 必填；`cells` 值 ∈ R/A/C/I；cells 的 key 须在 roles 声明内
- 容量：≤12 行任务（超 → warning）；角色列 ≤6
- 语义：R=执行 Responsible / A=问责 Accountable（每行恰一个）/ C=咨询 Consulted / I=知会 Informed

### decision_board 决策面板（B-6，批次 B 组件）

```yaml
- type: decision_board              # 方案比较 + 推荐 + 下一步，三端原生渲染
  title: "选型决策"                 # 可选
  options:
    - {name: "方案A 自研", pros: ["可控", "贴合"], cons: ["周期长"]}
    - {name: "方案B 采购", pros: ["成熟快"], cons: ["定制受限"]}
  recommendation: "推荐方案B（成熟快，缺口靠配置补齐）"   # 必填
  next_step: "启动 POC 验证"        # 可选
```

- 校验：`options` ≥2 个；每项 `name` 必填；`recommendation` 必填；`pros`/`cons` 可选
- 容量：≤4 个方案（超 → warning）

### flow_rows 写法（行式流程图）

```yaml
- type: diagram
  diagram_type: flow
  subtype: flow_rows
  title: "合同管理 TO-BE 主流程"
  desc: "可选一句话说明"
  exhibit: {num: "EXHIBIT 2", title: "合同管理 TO-BE 主流程（含履约链路）"}  # 可选图框
  source: "来源：分项功能清单 V2.0"                                    # 可选来源行
  roles:                               # 可选角色色板；>2 色时 legend 自动生成
    biz:   {label: "业务 / 采购"}
    legal: {label: "法务 / 审批控制"}
    fin:   {label: "财务 / 履约"}
    sys:   {label: "平台能力"}
    ext:   {label: "外部系统 / 可选项"}
  rows:
    - label: "相对方"                  # 行标签（可选）
      label_sub: "准入即风控"
      group: blue                      # 行级底色分组：blue|teal|none；同图 ≤3 种
      cards:
        - {badge: "1", label: "相对方准入申请", desc: "信息录入 + 资料附件", role: biz}
        - {badge: "2", label: "资格审核", desc: "不通过即拦截", role: legal}
    - arrow: down                      # 行间箭头行（down|up）
    - label: "用印"
      style: dashed_opt                # 虚线橙框可选项行：不编号、自动配「可选项」标签
      cards:
        - {label: "纸质用印", desc: "实体章场景保留", role: ext, dim: true}   # dim=降透明度
```

校验：rows 必填；单行 cards ≤6、总行数 ≤8（超 → warning）；card.role 必须在 roles 声明内（否则 error）；dashed_opt 行内带 badge → warning（可选项不编号）。

### 线型/框型语义表（F6 冻结，写 spec 必读）

| 视觉元素 | 唯一语义 | 纪律 |
|---------|---------|------|
| 实线箭头 →/↓ | 同步调用 / 主流程方向 | 主链路唯一线型 |
| 虚线箭头 ⇢ | 异步 / 回传 / 可选路径 | 必须带文字标注（11px） |
| 实线框卡片 | 主链路节点 | — |
| 行级虚线橙框 | 可选项 / 替代通道 | 不编号、须配「可选项」标签 |
| 行级底色分组 | 同一业务阶段/系统域 | 同图 ≤3 种 |
| 角色顶条色 | 节点责任角色 | 角色色 >2 必须出 legend |
| 芯片绿实底 | 已点亮 / 标准直接支持 | 三态成组出现 |
| 芯片朱橙实底 | 部分点亮 / 配置或二开 | 同上 |
| 芯片深灰虚线框 | 缺口 / 定制 / 未覆盖 | 必须画出 |
| 左色条+序号圆点 | 流程步骤顺序 | 可选项不编号 |
| 青色折角单据节点+无箭头虚线 | 单据挂载（BPMN data object） | 沿用 v1.2 |

### 关系决定图形（选 subtype 先定关系，再选图）

- 调用/数据流 → 带方向箭头的节点链（flow/sequence、flow_rows）
- 多角色交互 → 泳道（swimlane）或 flow_rows roles 色板
- 状态迁移 → 状态机式 flow（decision）
- 部署故障域 → deployment 拓扑
- 选项对比 → 同尺度矩阵（fit_gap/cbm）

### 制图纪律（Kimi tech-engineering §6.2）

- 箭头必须有方向 + 含义；数据流/控制流/异常路径用颜色 + 线型 + 标签冗余区分
- 连接线止于节点边缘，绝不穿越文字（verify 几何检查）
- 关键路径加粗/强调色，其余退中性色
- 复杂架构先总览再逐层放大
- 同页卡片不嵌套；禁红/紫/黄/绿高饱和四色同页（AI 经典配色，verify 检查）
- 图表必须配文字解读，不孤立存在；禁 icon 元素（F7 黑名单：pyz 实测图标退化圆形）；需图标用预设形状或文字符号
