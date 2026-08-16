---
name: spec-writing-guide
version: "1.3"
description: "定义 spec.yml 字段规则、容量预算和 confirmed 门禁。Defines spec.yml field rules, capacity budget, and the confirmed:true gate."
---

# Spec Writing Guide

`spec.yml` is the contract between user intent and the renderer. Without `confirmed: true`, every `*-build` command raises `RenderBlockedError`. This skill exists because AI used to hallucinate spec fields, invent layouts, and skip the confirmation gate.

**Single source of truth for fields and elements: `docs/spec_protocol_v1.md` (spec protocol v1, 2026-07-20).** This skill only covers process; field tables, capability matrix, and degradation behavior are governed by the protocol doc.

## When to Invoke

- User says: write spec / edit spec / generate spec / spec-gen
- `spec-gen` or `outline-to-spec` returned a draft and you need to finalize it
- `RenderBlockedError: spec not confirmed` occurred
- Before any `html-build` / `docx-build` / `quote-build` / `pptd-gen` call (preflight check)

Do NOT invoke for: reading an already-confirmed spec, or non-spec YAML files.

## The confirmed:true Gate (L3 hard constraint)

`src/_cli_guards.py:16-21` — `require_confirmed(spec)`: raises `RenderBlockedError(...)` if not confirmed (single decision point `is_confirmed`, `_cli_guards.py:6-13`; Renderer calls it at `_renderer/__init__.py:97-98`).

Workflow:

1. Generate draft spec (via `spec-gen` / `outline-to-spec` / manual write)
2. **Show the draft to the user** and explicitly ask: "Draft spec generated. Please confirm the content is correct? After confirmation I will add `confirmed: true` and start generation."
3. Only after the user confirms, add `confirmed: true` to the spec top level
4. Then call `html-build` (also outputs .pptd project) / `pptd-build` / etc. (`ppt-build` is retired D-090)

Never set `confirmed: true` proactively without user confirmation. This is the L3 boundary — do not write anything not in the spec.

## Spec Type 1 — Proposal Spec (HTML/PPT/DOCX)

Full field reference: `docs/spec_protocol_v1.md` (top-level field table + canonical/compatible fields per element + three-format capability matrix). Check it before writing any field.

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

### Document-level New Fields (Batch A, 2026-08-13, observation/reserved)

These fields are currently only schema-validated and reported by `verify` observation; the render layer does not consume them yet (promotion per §8 during observation).

**container (narrative container)**: optional at spec top level; valid values `scroll | chapters | stage | report`; default `scroll`.
- Semantics: narrative container shape. scroll=scrolling long-form (current default); chapters=chaptered; stage=stage presentation; report=report-style.
- Counterexample: `container: flipbook` (not whitelisted, error)

**simulation (simulation mode)**: optional at spec top level; valid values `none | static | interactive | guided`; default `none`.
- Semantics: reserved field for simulation components (component work is paused; field reserved). Keep default `none` when writing specs.

**type_roles (font-size role system)**: optional top-level block; role name → size (number or `{size: number}`).
- Six whitelisted role names: `title / subtitle / body / caption / footnote / hero_number`
- Omission is error-free (fully backward compatible); if present, validate role name and numeric size.
- Counterexamples: `type_roles: {heading: 40}` (`heading` not whitelisted), `type_roles: {title: "大"}` (size not numeric)

```yaml
type_roles:
  title: {size: 40}
  body: 16
  caption: 12
```

**font_role (element-level role)**: generic optional attribute on any element; role name must be in the same whitelist.
- Absent is error-free; an invalid role name errors.
- Counterexample: `{type: text, text: "x", font_role: banner}` (`banner` not whitelisted)
- Render priority (planned): explicit element `size` > `font_role` > default (renderer parsing not yet wired; currently validation only)

### Layout catalog (page metadata)

The `layout` field is written by the generator; **protocol v1 three-format renderers do not consume it** — page content is fully determined by `elements[]` (protocol doc §2). The following is only the generator's page-intent classification; focus on choosing the right elements when writing specs.

| Layout | Use for | Key elements |
|---|---|---|
| `title_body` | Overview / text-heavy page | `text` + `heading` |
| `cards_3` | Pain points / 3-column comparison | `cards` (title/tag/body/highlight) |
| `blueprint` / `function_architecture` | Architecture / capability hierarchy | `diagram` (org_tree / biz_capability_tree / architecture family) or `bullets`+`cards` combination |
| `timeline` | Phase plan / roadmap | `phases` (name/desc/actions) |
| `table` | Budget / matrix / data | `table` (headers/rows) |
| `summary` | Closing / next steps | `text` + `bullets` |

### Element types (full valid set in protocol v1, 10 total)

Only these 10 are valid — **unknown/misspelled `type` now raises a schema error, is rendered into `report.skipped`, and `verify` marks FAIL** (previously silently skipped and elements disappeared). Field details: protocol doc §3–§5.

- `text` — `{content, role?}` (compatible field `text`)
- `heading` — `{text, level?}` (`level` defaults to 2, 1–7; compatible `title|content`). **Available in all three formats**
- `bullets` — `items: [string]`
- `cards` — array of `{title, body, tag?, highlight?}` (tag/highlight render only in HTML)
- `phases` — array of `{name, desc, actions: [string]}`. **Canonical fields are name/desc/actions**; `label/goal`, `phase/title/items` are legacy compatible forms — do not use in new specs. Note PPTD emits only name/desc, not actions
- `table` — `{headers: [string], rows: [[string]]}` (each row's column count must match headers)
- `pullquote` — `{content, cite?}`. **Available in all three formats** (DOCX: indented italic quote)
- `architecture_4a` — `{layers: [{name, components[]}]}`. **DOCX-only native render; HTML/PPTD degrade to `[4A 架构图] 本节内容请见 Word 版`** — only use for DOCX-targeted specs; use `diagram` for HTML/PPT architecture
- `diagram` — structured graphics (next section, D-087). **DOCX degrades to `[架构图：{title}] 请见 HTML/PPT 版`** — know when writing that only HTML/PPT have diagrams
- `product_intro_placeholder` — product intro placeholder (D-089). DOCX similarly degrades to a text notice

### diagram element (HTML/PPT dual output, same source)

Visual spec: `docs/diagram_visual_design_v1_2026-07-19.md` v1.3 (drawing rules + full field table + §4.2 shape rules / §4.3 block arrows / §4.4 adj semantics table / §4.5 boolean-split hierarchy / §4.6 connector routing); subtype required fields follow protocol doc §5 (matches `DIAGRAM_SCHEMA` in `_renderer/schema.py`; wrong required fields cause schema errors).
**Writing rule: one diagram per page** (`_build_content_page` has no pagination; multiple large diagrams overflow the page).
**Format capability: HTML/PPTD render natively, DOCX degrades to text notice** — when the same spec will also produce DOCX, do not put key information only in diagrams.

```yaml
- type: diagram
  diagram_type: flow | architecture | matrix | timeline | relationship
  subtype: <子类型>
  title: "图的标题"      # 必填
  desc: "说明（可选）"
```

Subtypes and their dedicated fields (**all 33 implemented**: flow 6 / architecture 7 / matrix 5 / timeline 4 / relationship 11, including D-5 pyramid, quadrant and B-7 milestone_gantt; below are frequent examples; full field table in design spec §3 and protocol doc §5):

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

P1 writing notes:

- `flow/decision`: decision steps use `alt_next: "<no-branch target label>"` + `alt_label: "否"`; the main sequence is the "yes" branch
- `flow/cross_system`: steps need `system: "<system name>"` to assign columns; `async: true` draws dashed lines (async), `note:` marks interface names
- `flow/parallel`: `sources` stack vertically -> `merge` converges -> optional `after` follow-on chain
- `architecture/integration` two forms: point-to-point uses `source{items}+target{items}+links[mode]`; bus uses `hub+systems` (choose one)
- `architecture/deployment`: `zones[].nodes[]` nested; `links: [{from, to, label}]` from/to use zone names
- `matrix/cbm`: capability elements can use `{name, heat: strong|mid|weak}` for heat
- `relationship/er_*`: relations `type: one_to_one|one_to_many|many_to_many`; logical ER uses `pk/fk/attrs`
- `relationship/data_flow`: nodes `type: source|process|sink|store`; flows `direction: push|pull|bidirectional`
- `relationship/biz_capability_tree`: `groups[].children[].items[]` three levels

**pptd handwritten-page discipline** (read when writing `.page` directly instead of spec `diagram`; lesson from real project v14, 2026-08-11):

- Prefer `type: diagram` so the official renderer draws the graphic; when handwritten is required, route arrows per `_renderer/diagram/flow.py _pptd_arrow`: snap to node connection points — same row right edge→left edge straight line; misaligned `bentConnector3` elbow, bottom out/top in, no crossing node boxes
- No dangling arrows (fixed-height horizontal arrows between columns misalign with nodes; users call it "unreadable"); in-column nodes hug height, text wraps, vertical distribution fills the column, and narrower columns leave channels for arrows
- **Shape rules (selection gate)**: native preset/chart > boolean split > handwritten freeform path (banned). Shape names must be in the `_pptd_convert._SHAPE_NAME_MAP` / `_CONNECTOR_MAP` whitelist; `image` is banned in diagram graphic areas (`verify` intercepts in observation mode)
- **Block arrows**: solid-direction uses block arrow presets (`rightArrow`/`leftRightArrow`/`upDownArrow`/`pentagon`); fine relationships (interface/data-flow lines) use connector

## Capacity Budget (follow when writing specs, prevent Plan-Delivery Gap)

Page is 1280×720. **Do not exceed at writing time**; do not wait for lint to reject (basis: real project v7 measurement + spec `docs/思维链预算与验证回路规约_v1.1_2026-07-21.md` §5 L0):

| Element | Budget | Evidence source |
|---|---|---|
| `table` | ≤11 rows, ≤20 chars per cell; ≤9 rows when a `pullquote` follows | 13-row long text pushed pullquote out of bounds (v7 P11) |
| `pullquote` | content ≤2 lines (≈60 chars), cite ≤15 chars; halve text when on same page as a table | same as above |
| `architecture/4a`、`layered` | **Do not write `desc`** (renderer hardcodes desc/chips and they always collide, known_issue); fold info into `name` or page `pullquote` | desc crushed by chips into garbled text (v7 P2) |
| `timeline/horizontal` | ≤4 milestones, desc ≤30 chars | 4 nodes with 40-char desc barely passed (v7 P17) |
| `flow/cross_system` | ≤6 system columns, note ≤12 chars | 6-column connections crowded warning (v7 P15) |
| `architecture/deployment` | cross-zone links **do not write `label`** (hidden by zone background); fold info into node desc | label hidden/incomplete (v7 P19) |
| `cards` | ≤3 per row, body ≤3 lines | — |
| Page title | ≤30 chars | — |

One diagram per page (existing rule unchanged). **When over budget, do not force content in — split pages or trim copy.**

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

User: "Generate a spec from this requirements document"

1. `python _cli.py spec-gen 需求.docx --client 蓝海集团 --output spec.yml`
2. Read the draft, present key fields to user: pages count, layouts used, style
3. Ask: "Draft spec generated (5 pages, including pain points/architecture/phases/budget/summary). Does it look correct?"
4. User: "Confirmed" → add `confirmed: true` to spec.yml top level
5. Proceed to `html-build`

### Example 2 — Fixing RenderBlockedError

User ran `html-build` and got: `RenderBlockedError: spec.yml 未标记 confirmed: true`

1. Read the spec.yml
2. Show contents to user, ask for confirmation
3. After confirmation, edit spec.yml: add `confirmed: true` at top level (alongside `project`/`author`/`date`)
4. Re-run `html-build`

### Example 3 — Quote spec

User: "Create a quote spec"

1. Confirm materials are in `_knowledge/clients/{客户}/refs/`
2. `python _cli.py quote-spec-gen _knowledge/clients/蓝海集团/refs _knowledge/clients/蓝海集团/蓝海集团_quote_spec.yml --client 蓝海集团`
3. Show draft: sheets, sections, items, totals
4. After user confirms, add `confirmed: true` at top level (sibling of `quote:`)
5. `python _cli.py quote-build 蓝海集团_quote_spec.yml output/蓝海集团/蓝海集团_报价_v1.html --template 一页报价模板 --client 蓝海集团`

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RenderBlockedError` | spec lacks `confirmed: true` | Confirm with user, add field |
| `RenderBlockedError`（client_name） | `client_name` field exists but is empty | Fill in the real client name or remove the field |
| verify FAIL：`N 个元素被跳过` | Unknown/misspelled element type (no silent skip since protocol v1) | Use one of the 10 valid types from protocol doc §3; common in old specs using `tree`/`chart`/`actions` |
| `[spec校验] ... 缺必填字段` printed | Element missing required fields (e.g. cards missing title, table rows/columns mismatched) | Fill per required-field rules in protocol doc §4/§5; generation continues but rendered content will be incomplete |
| `[架构图：...] 请见 HTML/PPT 版` appears in DOCX | diagram/placeholder has no native DOCX render (expected degradation) | Expected; for architecture content in DOCX use `architecture_4a` or text elements |
| `[4A 架构图] 本节内容请见 Word 版` appears in HTML/PPT | `architecture_4a` renders natively only in DOCX | Use `diagram` (architecture/4a, layered subtypes) |
| `theme-verify` low coverage | Spec content missing permanent-theme keywords from `theme-guard` output | Add keywords to page content, rebuild |
| `pptd-build` errors on page N | Element type mismatch for that page's layout | Rebuild the .pptd project with `html-build` dual output, check that page's element schema, then rerun `pptd-build` |
| Quote `total_label` missing | Section lacks `total_label` field | Add `total_label: <合计标签>` to each section |
| `--style` rejected | Not one of `education/enterprise/tech/gov` | Use a valid style or omit (uses spec `style` field) |

## Anti-patterns (do NOT)

- Set `confirmed: true` before user confirmation
- Use element types outside the protocol v1 list of 10 (`tree`/`chart`/`actions`/misspelled types) — now raises schema errors and causes verify FAIL
- Use legacy phases forms in new specs (`label/goal`, `phase/title/items`) — canonical is `name/desc/actions`
- Rely on `diagram` for graphics in DOCX-targeted specs (DOCX only has degraded text); use `architecture_4a` in HTML/PPT-targeted specs (it degrades)
- Mix proposal spec fields with quote spec fields in one file
- Omit `id` field on pages (renderer uses it for chunking, report targeting, and replacement)
- Put vendor names in `cards`/`diagram` content (use system names per project rules)
- Write more pages than the spec needs (HTML first, iterate based on user feedback)

## v2.0 Page Layouts and Components (frozen 2026-07-25, dev_plan_visual_v2_2026-07-25)

### Layout selection (locked catalog: choose, do not invent)

Page-level `layout` field, controlled values P01-P16 (v3.0 adds P12/P14/P15/P16, no P13); if the catalog is insufficient = expand it through a decision, do not improvise in the spec.

| ID | Name | Required components (order) | Optional | Capacity limit |
|------|------|----------------|---------|---------|
| P01 | Cover | hero | stat_cards | hero.stats ≤4 |
| P02 | Chapter page | section_tag + action_title | info_cards | info_cards ≤1 group |
| P03 | Conclusion summary | section_tag + action_title + kpi_cards | info_cards | kpi ≤4 |
| P04 | Pain-point matrix | section_tag + action_title + pain_cards | legend_bar | pain ≤9 |
| P05 | Flowchart page | section_tag + action_title + diagram(flow family) + legend_bar | info_cards | Single diagram |
| P06 | Architecture diagram page | section_tag + action_title + diagram(architecture family) | legend_bar | Single diagram |
| P07 | Comparison table page | section_tag + action_title + table | info_cards | table ≤12 rows |
| P08 | Capability map page | section_tag + action_title + diagram(matrix family) + legend_bar | stat_cards | Single diagram |
| P09 | Roadmap page | section_tag + action_title + diagram(timeline family) | info_cards | Single diagram |
| P10 | Risks and open items page | section_tag + action_title + (table\|info_cards) | qa_block | — |
| P11 | Closing page | action_title + info_cards | hero(compact) | — |
| P12 | Table-of-contents page (v3.0) | section_tag + action_title + toc_cards | — | Cards ≤8 |
| P14 | Two-column comparison page (v3.0) | section_tag + action_title + duo_compare | legend_bar | — |
| P15 | Pros/cons checklist page (v3.0) | section_tag + action_title + pros_cons | legend_bar | — |
| P16 | CTA closing page (v3.0) | action_title + cta_block | — | — |

**Content type → layout mapping**: cover→P01 / quantified conclusions & value→P03 / pain points→P04 / process→P05 / architecture→P06 / comparison & channels→P07 / capabilities, lit-up, feature list→P08 / plan & roadmap→P09 / risks & open items→P10 / closing→P11 (product intro recommends P16 CTA).

Legacy `layout` values (`title_body`/`cards_3`/`blueprint`/`summary`/`table`/`tree`/`phases`/`timeline`) remain valid and render as free flow (F9); omitting `layout` is also free flow.

**Theme**: spec top-level `theme: consulting_kpmg | legacy_bluegreen | corporate_navy | product_charcoal` (default `legacy`); hex literals are banned in specs (v2 spec mechanical guard; colors go into theme packs).

**Scenario** (v3.0, batch A adds training): optional spec top-level `scenario: report | product_intro | training` (default `report`).
- `report`: presentation style (CFO/IT director), paired with `theme: corporate_navy`, default P01-P11 layouts
- `product_intro`: product intro style, paired with `theme: product_charcoal`, closing page recommends P16 CTA
- `training`: training/teaching style (added in batch A, 2026-08-13)
- scenario only guides the content→layout default mapping, does not force theme; the two are declared independently
- (Note: outline-to-spec P-family mapping waits for build_elements v2 componentization; the scenario field is currently used for validation and document semantics)

**Brand/logo** (v3.0): optional spec top-level `brand`:
```yaml
brand:
  logo: refs/logo.png          # 本地资产（refs/ 或 _assets/），禁外链；缺省占位虚线框
  logo_position: topnav_left   # topnav_left | topnav_right | hero_corner
```

### New element syntax (10 page components)

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

### evidence_ledger evidence ledger (B-3, batch B component)

```yaml
- type: evidence_ledger             # 每条结论挂证据编号 + 状态，三端原生渲染
  title: "需求覆盖台账"              # 可选
  items:
    - {num: "E-01", conclusion: "OA 平台标准模块覆盖 202 功能点",
       evidence: "分项功能清单 V2.0 §3", status: "已覆盖"}
    - {num: "E-02", conclusion: "缺口集中在资产大件管理",
       evidence: "调研访谈 2026-07", status: "待补"}
```

- Validation: `items` required and non-empty; each item `conclusion`/`evidence` required; `num`/`status` optional
- Capacity: ≤12 items (over → warning); ≤20 chars per cell (PPT truncates to one line; long text overflows)

### risk_register risk register (B-4, batch B component)

```yaml
- type: risk_register              # 风险项 + 等级 + 状态 + 应对，三端原生渲染
  title: "风险控制登记"            # 可选
  items:
    - {risk: "数据迁移失败", level: "高", status: "未解决",
       response: "迁移前全量备份 + 回滚预案"}
    - {risk: "接口联调延期", level: "中", status: "监控中",
       response: "提前两周联调 + 周例会跟踪"}
```

- Validation: `items` required and non-empty; each item `risk`/`response` required; `level` enum 高/中/低 (optional); `status` optional
- Capacity: ≤12 items (over → warning); ≤20 chars per cell

### raci_matrix RACI matrix (B-5, batch B component)

```yaml
- type: raci_matrix                # 行=任务，列=角色，单元格 R/A/C/I
  title: "角色责任矩阵"            # 可选
  roles: ["甲方项目经理", "我方PM", "我方顾问"]   # 列头
  tasks:
    - {task: "需求调研", cells: {甲方项目经理: "A", 我方PM: "R", 我方顾问: "C"}}
    - {task: "方案设计", cells: {甲方项目经理: "C", 我方PM: "R", 我方顾问: "A"}}
```

- Validation: `roles` required and non-empty; `tasks` required and non-empty; each item `task` required; `cells` values ∈ R/A/C/I; `cells` keys must be declared in `roles`
- Capacity: ≤12 task rows (over → warning); ≤6 role columns
- Semantics: R=Responsible / A=Accountable (exactly one per row) / C=Consulted / I=Informed

### decision_board decision panel (B-6, batch B component)

```yaml
- type: decision_board              # 方案比较 + 推荐 + 下一步，三端原生渲染
  title: "选型决策"                 # 可选
  options:
    - {name: "方案A 自研", pros: ["可控", "贴合"], cons: ["周期长"]}
    - {name: "方案B 采购", pros: ["成熟快"], cons: ["定制受限"]}
  recommendation: "推荐方案B（成熟快，缺口靠配置补齐）"   # 必填
  next_step: "启动 POC 验证"        # 可选
```

- Validation: `options` ≥2; each item `name` required; `recommendation` required; `pros`/`cons` optional
- Capacity: ≤4 options (over → warning)

### flow_rows syntax (row-based flowchart)

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

Validation: `rows` required; ≤6 cards per row, ≤8 total rows (over → warning); `card.role` must be declared in `roles` (otherwise error); badge in a `dashed_opt` row → warning (optional rows are not numbered).

### Line/box semantics table (F6 frozen, must-read for spec writing)

| Visual element | Unique semantics | Discipline |
|---------|---------|------|
| Solid arrow →/↓ | Synchronous call / main flow direction | Only line style for the main path |
| Dashed arrow ⇢ | Async / return / optional path | Must have text label (11px) |
| Solid box card | Main-path node | — |
| Row-level dashed orange box | Optional / alternative channel | Not numbered, must have "optional" label |
| Row-level background group | Same business stage/system domain | ≤3 per diagram |
| Role top-bar color | Node responsibility role | Legend required when >2 role colors |
| Green solid chip | Lit / standard direct support | Appear as a three-state group |
| Orange solid chip | Partially lit / config or secondary development | Same as above |
| Dark-gray dashed chip | Gap / custom / not covered | Must be drawn |
| Left color bar + numbered dot | Flow step order | Optional items not numbered |
| Cyan folded document node + arrowless dashed line | Document attachment (BPMN data object) | Keep v1.2 |

### Relationship decides graphic (choose relationship first, then subtype)

- Call/data flow → node chain with directional arrows (`flow/sequence`, `flow_rows`)
- Multi-role interaction → swimlane or `flow_rows` roles color palette
- State transition → state-machine style flow (`decision`)
- Deployment fault domains → `deployment` topology
- Option comparison → same-scale matrix (`fit_gap`/`cbm`)

### Drawing discipline (Kimi tech-engineering §6.2)

- Arrows must have direction + meaning; distinguish data/control/exception paths redundantly with color + line style + labels
- Connectors stop at node edges, never cross text (`verify` geometry check)
- Emphasize the critical path with bold/color; keep the rest neutral
- For complex architecture, show overview first, then zoom into layers
- Do not nest cards on the same page; ban the four high-saturation colors red/purple/yellow/green on one page (classic AI palette, `verify` check)
- Charts must be accompanied by text interpretation, never standalone; `icon` elements are banned (F7 blacklist: pyz test showed icons degrade to circles); use preset shapes or text symbols if icons are needed
