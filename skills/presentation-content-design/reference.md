# Presentation Content Design — Reference

> Read the matching anchor on demand; do not read the whole file at once.
> Content source: `inbox/AI修炼宝典` (ZSW SKILL suite methodology) translated into our project context; implemented decisions follow SKILL.md "Decisions".

## Anchor Index

| Anchor | Content | When to read |
|---|---|---|
| #containers | Containers A-D + local layouts E-K | Step 1 container reading mode |
| #components | 19-component library + content-relationship mapping | Step 2 component details |
| #simulation | Three simulation modes + feedback selection table | Step 3 simulation intuition |
| #composition | 12 composition boards + composite patterns | Step 4 template layout |
| #template-families | Ten template families (recipe cards) | Complex pages: find composition DNA |
| #quality-gate | Anti-degradation list + passing line + eight checks | Step 5 quality-gate acceptance |
| #styles | Eight style directions A-H (incl. #training style card) | When setting material tone |
| #extension-discipline | Extension discipline for template sedimentation | When maintaining skills / _knowledge |

---

## #containers Container Library: How the Whole Deck Is Read

Containers decide how readers enter, flip through, and switch across the whole deck; **they do not decide what a page looks like**. Choose containers by reading behavior, not personal habit.

### Top-level containers A-D (manage "doors and corridors")

| Container | Form | Reading behavior | Use for |
|---|---|---|---|
| A 纵向场景 | single long page, scroll screen by screen | sequential scrolling | single-page proposals, executive overviews |
| B 章节式 Part | top chapter switching, natural reading within chapters | jump by TOC | long proposals, requirements analysis |
| C PPT 演示舞台 | one page per screen, arrow to flip | led by the presentation | presentations, on-site reporting |
| D 连续报告 | document-style linear layout | linear deep reading | research reports, white papers |

### Local layouts E-K (how "furniture in a room" is arranged)

Orthogonal to A-D; can be freely combined into any container:

| Layout | Organization |
|---|---|
| E Part + 步骤 | main conclusion persists + steps 1/2/3 can be revisited |
| F 交互工作台 | simulation operation area + operation feedback |
| G 滚动叙事 | narrative paragraphs advancing with scroll |
| H 时间轴流 | milestones laid out along a timeline |
| I 知识图谱 | central node + radial relationships |
| J 空间画布 | freely positioned spatial relationships |
| K 证据室 | conclusion-source grouped evidence display |

> Implementation: spec top-level `container` field (decided; scroll/chapters/stage/report, default scroll). Local layouts E-K are combination patterns for page components; no separate field.

### container → P01-P16 layout mapping (2026-08-13)

| container | Recommended layouts | Avoid | Notes |
|---|---|---|---|
| scroll | P01/P03/P04/P08/P11 | P02 chapter pages, P12 TOC pages | single long page scrolling, no chapter switching |
| chapters | P02/P12 + P03~P10 | none (most flexible) | TOC + chapter pages guide jumping |
| stage | P01~P11 + P16 | long scrolling narrative | one page per screen flip presentation |
| report | P03/P07/P09/P10 + text elements | P05/P06 image-led | document-style linear deep reading |

---

## #components Component Library: Choose by Content Relationship

Components are not "card skins"; they are Legos for presentations. Choose components by "what relationship this content has", not "which shell looks good".

### Components we already support (reuse first, don't reinvent)

| ZSW component | Relationship it tells | Our current state |
|---|---|---|
| 叙事卡 | judgment + explanation + example | info_cards and other base elements |
| 对比板 | two-party comparison | duo_compare / diagram: matrix |
| 能力成绩单 | multi-indicator scoring overview | stat_cards / kpi_cards |
| 文本图示板 | mixed text + diagram | page component combinations |
| 架构图 | system layering and connections | diagram: architecture (28 diagram types) |

### First 5 components (decided 2026-08-13; B-3~B-7 implemented)

| Component | Content relationship | Selection signal (content cues) | Structural points | Current fallback |
|---|---|---|---|---|
| 证据台账 | requirements coverage, outcome proof | each conclusion must be "verifiable" | conclusion-evidence-status-number, expandable | table |
| 风险控制登记 | risk ledger | risks must be "trackable" | high/medium/low + status + response | table / info_cards |
| 角色责任矩阵 | division of responsibility | multiple roles/tasks "who owns what" | client/our RACI (exactly one A per row) | table |
| 里程碑甘特 | implementation plan | "what to do when" task × time × dependency | task track × milestone × dependency, weekly layout | diagram: timeline (≤4 nodes) |
| 决策面板 | decision page | multiple options "which to choose" | option comparison + recommended next step | duo_compare |

### Missing components (second batch, on demand)

| Component | Content relationship | Current fallback |
|---|---|---|
| 指标叙事带 | tell business data story (scope → reason → action) | stat_cards has only big numbers |
| 审计事件行 | system operation trace (action → status → feedback + evidence number) | none |
| 场景旅程条 | rollout path (pain point → pilot → rollout) | none |
| 执行作战板 | progress plan (action-standard-evidence) | none |

### Simulation interactive components (default pending; `simulation` field reserved; see SKILL.md Decisions item 4)

编号证据卡, 流程向导 (step bar with back), 真实工作台, 爆炸拆解图 (UI / objects), 聚光交互指引—present products without screenshots; build clickable pages. HTML only; PPT needs fallback strategy.

---

## #simulation Simulation Library: Three Page Realisms

When presenting products, screenshots are the weakest approach. Realism requires complete **action → state → feedback**: what was clicked, how the interface changed, how the result feeds back.

| Mode | Question answered | Requirements | Explanation depth |
|---|---|---|---|
| Static high-fidelity page | What does the system look like | has shell, navigation, real data; need not be clickable but must look like a real product | show structure, fields, business states |
| Interactive clickable | How people use it, how the system responds | every button must have real state change and feedback | demonstrate approval, filtering, processing records |
| Guided Demo | How the whole flow goes | every step locatable, reversible, skippable | walk the audience along a real path |

### Feedback selection table (feedback is not a random toast)

| Feedback method | When to use | Should not be used for |
|---|---|---|
| Audit event row | when an operation result must be retained: status + event + time/object + result details + evidence number/next step | just show a disappearing "操作成功" |
| Inline annotation | local issues on a field or record: mark directly beside the failing row | pop a local issue as a global large dialog |
| Status log / drawer / expandable evidence | when users need to keep viewing reasons, evidence, processing history | give only conclusion without context |
| Toast | short-lived feedback that need not be retained ("已保存") | replace audit receipts, error details, business processing results |

### PPT fallback strategy (B-8, designed 2026-08-13; components pending)

simulation is native only on HTML; PPT fallback:

| simulation | PPT fallback |
|---|---|
| static | high-fidelity static page layout (shell + nav + real data), not clickable |
| interactive | step-by-step static sequence: one screen per step, action→state→feedback linked by arrows |
| guided | step bar + screenshots per step: sequence number + review path expressed as static sequence |

- Fallback principle: preserve completeness of action→state→feedback; interactivity (clickable/back) degrades to static arrows/step bars
- Trigger: when a real demo need appears (client wants to see system operation flow), start a project and re-estimate effort
- Status: pending (`simulation` field reserved; render logic not implemented)

---

## #composition Composition Boards: Twelve "Telling Modes"

Composition boards are the "syntax" of good presentations: decide where key information goes, what readers see first, and how relationships are understood. Difference from skin-changing: skin-changing only changes colors/radii; boards change **the organizational logic of information on the page**. The same "project progress" can be told as a trend with 数据叙事, as trade-offs with 决策板, or as evidence with 证据台账—different telling modes lead readers to different conclusions.

| Board | Best at telling |
|---|---|
| 全幅主张 | a single core claim, one judgment on the page |
| 编辑式分栏 | magazine-style text/image interleaving, narrative with evidence |
| 架构板 | system layering + foundation + governance bar |
| 证据台账 | conclusion-evidence-status line by line |
| 流程脊柱 | stage-by-stage handoff, stage-gate reviews |
| 场景序列 | multiple scenarios in order (pain point → pilot → rollout) |
| 数据叙事 | inflection annotations + source + conclusion; data tells the story |
| 仿真产品 | page realism as the main body, presenting a product |
| 时间线甘特 | task track × milestone × dependency, weekly layout |
| 对比矩阵 | multi-option multi-dimension scoring comparison |
| 决策板 | option comparison + recommendation + suggested next step |
| 能力图谱 | relationship graph of core + capability items |

### Composite patterns

A page can combine multiple expressions (架构板 + 证据台账, 仿真工作台 + 操作步骤, 甘特 + 责任矩阵), but **each region must play a clear role**: main judgment / main relationship / supporting evidence / example / source / action—do not pile up to look rich.

---

## #template-families Ten Template Families (Recipe Cards)

A recipe preserves not the "skin" (colors/radii) but four things: **information anatomy + spatial organization + reading path + interaction behavior**. Style can change; structure does not scatter. Not a closed list: new pages can be created as long as you explain what information relationship the new composition solves.

### Architecture and ecosystem families

| Recipe | Tells | Structure list |
|---|---|---|
| 分层企业蓝图 | 大型平台、能力全景、技术与业务分层 | 横向层级 + 纵向治理栏 + 能力分区 + 外部系统 + 跨层连接 + 底座 |
| 中心生态拓扑 | 中心平台与用户/渠道/模型/外围系统的关系 | 核心枢纽 + 外围角色 + 接口方向 + 治理环 |
| 系统集成关系图 | 多系统对接、数据流、消息流、身份访问 | 真实系统 + 接口端口 + 流向标签 + 失败边界 |
| 多租户治理图 | 集团/租户/组织/身份映射 | 组织层级 + 租户边界 + 数据隔离 + 治理中心 |

### Scenario and demo families

| Recipe | Tells | Structure list |
|---|---|---|
| 场景行动链 | 从用户表达走向系统执行 | 用户原话 → 意图识别 → 信息预填 → 规则校验 → 人工确认 → 系统回写 → 结果证据 |
| 交互时序板 | 多参与方调用、审批、返回、日志沉淀 | 参与方 + 时间方向 + 状态变化 + 异常支路 |
| 运营看板与业务工作台 | 运营分析、产品演示、配置操作 | 有口径的指标 + 真实图表 + 任务导航 + 操作反馈 |
| 深度叙事面板 | 痛点、机制、能力、风险、案例 | 语义图示 + 明确判断 + 原因机制 + 具体例子 + 证据/行动 |

### Evidence and decision families

| Recipe | Tells | Structure list |
|---|---|---|
| 证据与覆盖账本 | 成果成绩、需求覆盖、完成状态、问题响应 | 汇总判断 + 明细层级 + 状态来源 + 证据编号 + 可展开 |
| 决策与路线套件 | 方案比较、双轨迁移、阶段规划、里程碑 | 比较轴 + 当前与目标 + 阶段时间 + 责任依赖 + 风险与建议 |

---

## #quality-gate Quality Gate: Minimum Completeness

The quality gate does not look at colors/radii; it checks **whether structure is complete**: whether a component fully tells the information relationship. It blocks pages that "look plausible but don't explain clearly".

### Common failing degradations (negative list)

- Narrative card: only icon + title + vague slogan; no judgment, explanation, or example
- Metric card: one big number; no unit, period, business context, or reason for change
- Flow/sequence: only step names; no participants, actions, states, inputs/outputs, or exceptions
- Architecture diagram: multi-layer boxes + arrows; no real entities, boundaries, interfaces, or flows
- Table/ledger: paragraphs arranged in a grid; no field relationships, status, source, or responsibility
- Data chart: colored bars; no scope, units, scale, data labels, or business explanation
- Simulated workbench: browser frame only; no real tasks, fields, records, states, or feedback

### Passing line (structural completeness)

| Component type | Passing line |
|---|---|
| Narrative component | judgment + explanation + example, all three present |
| Metric component | unit + period + context + reason for change, traceable |
| Flow/sequence | participants + action + state + inputs/outputs + exception branches |
| Architecture diagram | real entities + boundaries + interfaces + flows; can explain how the system works |
| Table/ledger | field relationships + status + source + responsibility/response point |
| Data chart | scope + units + scale + labels + business explanation |
| Simulated workbench | real tasks + fields + records + states + feedback, none missing |

### Eight checks across all entries

| Check | Standard |
|---|---|
| Content | each page has a clear task; conclusions supported by explanation/evidence/mechanism/example/boundary/action; complex content not compressed into a few sentences |
| Structure | the same complete conclusion is fully explained in one main position; terminology, numbers, time, roles, and states stay consistent |
| Diversity | consecutive pages do not repeatedly use the same cards, same left/right columns, or the same page shell |
| Readability | contrast, font size, line breaks, text overflow, clipping, and meaningless large whitespace are all in scope |
| Diagram | nodes, boundaries, arrows, legends, labels, alignment: not just boxes + arrows |
| Data | verify numbers, totals, units, time ranges, scales, legends, and graphic proportions |
| Interaction | actually click all controls; action→state→feedback consistent; guided demos can return to any step |
| Anti-templating | recognize cheap structures like "one-line feedback bar" or "generic three-layer architecture stack"; do not evade by changing colors |

> Rule-library discipline: rules are alive—each failure sediments one rule; four entries reference the same rule set; each check can say "per rule X"; when acceptance fails, point out which rule is unmet instead of vaguely saying "tweak it".

---

## #styles Eight Style Directions (Eight Narrative Languages, Not Eight Outfits)

True style change = **composition focus + type scale + spatial rhythm + visual language + control language** all move together; changing only a color set is not a style change.

| Style | Suits | What actually changes |
|---|---|---|
| A Formal Dossier 正式卷宗 | 领导汇报、成果、治理、证据密集的正式方案 | 公文三段式：居中红头、文号、表格化数据、落款 |
| B Editorial Narrative 编辑叙事 | 主题分享、咨询故事、概念解释与图文穿插 | 杂志通栏：超大标题、首字下沉、刊例数字栏、引言 |
| C Human Learning Studio 学习工作坊 | 概念讲解、例题、练习、反馈、迁移 | 教学白板：目标胶囊、编号学习卡、练习条、反馈 |
| D Technical Blueprint 技术蓝图 | 技术方案、架构评审、部署与集成设计 | 工程流水线：元信息标签、阶段条、进度条、指标节点 |
| E Product Workspace 产品工作台 | 产品演示、操作培训、场景证明 | 软件界面：窗框、工具栏、列表、面板、状态栏 |
| F Minimal Analytical 极简分析 | 单一关键问题、研究发现、决策摘要 | 极简海报：巨号结论、单焦点、细线标签行 |
| G Information Atlas 信息图谱 | 能力地图、行业版图、知识体系、组合关系 | 图谱语言：中心节点、放射关系、图例、多层嵌套 |
| H Scenario Documentary 场景纪实 | 客户案例、实施复盘、角色变化、前后对照 | 纪实语言：时间线、角色卡片、前后对照、旁白引用 |

> Compared to us: 4 style + 4 theme are essentially color/font packages; C (training grammar) corresponds to `scenario: training`.

### #training Training Scenario Style Card (2026-08-13, B-2)

`scenario: training` uses C Human Learning Studio style.

| Dimension | Key points |
|---|---|
| 页面骨架 | 学习动作先行：目标胶囊 → 编号学习卡（概念）→ 例题 → 练习条 → 反馈 → 迁移 |
| 密度 | 中偏低（每页 1 个学习动作，不给读者信息过载） |
| 组件 | 优先 info_cards / stat_cards + diagram（流程/架构做图示）；避免大段 text |
| 版式 | 复用 P01-P11 骨架，但每页首元素用 action_title 写「学习目标」而非「结论」 |
| 主题 | 配 product_charcoal 或 corporate_navy（按场景，不强制） |
| 触发 | 内容目标是「教会概念/流程/操作」而非「汇报结论」 |

---

## #extension-discipline Extension Discipline for Template Sedimentation

New industries/clients only sediment: **objects, terminology, roles, evidence, fields, common questions**.

Do not sediment: **fixed colors, page counts, card layouts**—to prevent the suite from sprawling (echoing `writing-great-skills` sediment/sprawl issue).

Applies to skills and `_knowledge/` maintenance in this project: client-level refs sediment material facts; renderer-level layout/component decisions go through the project-level extension process (P-series precedents), not reverse contamination.
