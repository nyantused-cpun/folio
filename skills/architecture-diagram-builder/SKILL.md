---
name: architecture-diagram-builder
version: "5.0"
description: "架构图/蓝图架构/信息化规划/数据/应用/技术/治理架构时调用。Enterprise-architecture diagram construction methodology; invoke for architecture diagrams and use before outline-to-spec."
---

# Architecture Diagram Builder

> This file is a directory page, not an encyclopedia. Read methodology details on demand at the corresponding anchors in [reference.md](./reference.md).

## When to Invoke

**Invoke**: architecture diagrams / blueprint architecture / overall IT planning / data architecture / application architecture / technical architecture / governance architecture / evolution roadmap / EA architecture governance.
**Do not invoke**: simple flowcharts, tech-stack diagrams, single-page UI screenshots, or minor tweaks to an existing architecture diagram.

**Process-service mapping diagram**: after BA 5.1 task→system service derivation, you MUST output this diagram (MANDATORY) to verify the mapping is realized. Drawing: see section 5.2 at the end of [reference.md#BA](./reference.md#ba业务架构完整设计步骤).

## What Problem It Solves

AI often makes 5 mistakes when drawing architecture diagrams; this skill prevents each one with locked checklists + step-by-step cross-domain checks:

| # | Common mistake | Why it is wrong | How this skill prevents it |
|---|---|---|---|
| 1 | Skipping principles and going straight to steps | Design criteria are not explained; the diagram can be drawn but has no logical foundation, so you won't know how to adjust when requirements change | Each architecture type must produce 3-6 principles before steps are allowed |
| 2 | Drawing the four 4A diagrams independently without checking cross-domain consistency | The same business object has different names across the four diagrams, so readers cannot match them | Each step outputs a locked checklist; the next step must compare against it item by item |
| 3 | Reversing the granularity of function items and APPs | Treating a small function like "OCR recognition" as an APP while treating a full business capability like "invoice receipt registration" as a function item | Three-track comparison table for function identification + granularity rules (APP = has independent use cases; function item = a task that ends when assigned to one person) |
| 4 | Hiding Gap items in product mapping | Marking only Fit to make the proposal look good; Gap is omitted or marked without stating how to handle it | Every requirement must be marked Fit/Partial/Gap; Gap items must state the handling approach |
| 5 | Governance inventing content detached from reconciliation results | The governance chapter writes vague control systems, does not answer "who owns each process and which module it runs in", and does not match the reconciliation table | Every governance matrix row must have Owner + supporting module, all from the cross-domain reconciliation table (enable three-governance × three-dimensions only for group-level reporting) |

Methodology foundation: [reference.md#methodology](./reference.md#methodology方法论基础).

## Scenario Routing (Ask Direction on First Contact)

| Scenario | Output form | Granularity |
|---|---|---|
| Architecture blueprint for executives | HTML single page + 4A overview diagram + evolution roadmap | L1-L2, conclusion-focused, light on detail |
| Internal requirements list | HTML per-domain detail + APP/function-item list + cross-domain association table | L3-L5, detail-focused and actionable |
| Packaged software sales | 4A architecture diagrams + product mapping trio (Fit-Gap) | Methodology + product correspondence |
| Training/teaching architecture walkthrough | Build intuition by simulation first (scenario penetration) → then abstract layers (4A layered diagram) | L1-L2, learning action first |
| Platform clients (hub ecosystem) | Hub-ecosystem topology: core hub + peripheral roles + interface directions + governance loop | L1-L2, ecosystem relations and interface directions |
| Group clients (multi-tenant) | Multi-tenant governance diagram: org hierarchy + tenant boundaries + data isolation | L2-L3, tenant isolation and governance boundaries |

## Tool and Workflow Integration (MANDATORY)

This skill is a subcomponent of this project and must use the CLI workflow:

| Stage | Command | Description |
|---|---|---|
| Session start | `python _cli.py session-start "<输入>" --client <客户>` | Determine level + load history + refresh theme |
| Client ground rules | `python _cli.py theme-guard <客户>` | Inject client's permanent ground rules at HEAD |
| Read materials | `python _cli.py read <文件>` / environment document-reading tool | Read full text; never conclude from the first N characters |
| Generate HTML | `python _cli.py html-build <spec> --client <客户>` | spec must set confirmed:true, otherwise blocked |
| Verify | `python _cli.py verify <文件>` + `theme-verify <文件> <客户>` | Runs automatically after generation; must redo on failure |
| Session end | `python _cli.py save <客户>` | Write task_history + update index |

Rendering spec (CSS/colors/drawing): [reference.md#rendering](./reference.md#rendering视觉渲染规范), read on demand.

## Execution Order (MANDATORY · Three-Phase Process)

> **Three phases**: ① Write documents → ② Merge checks → ③ Draw diagrams
>
> **Core principle**: finish all document content first, ensure cross-domain consistency, then generate the HTML architecture diagram.

```
─── 阶段一：写文档 ───
Step 1: 需求识别 → reference.md#requirements（需求识别步骤）→ 4A 需求清单 + 缺口清单

Step 2: 业务架构文档(BA) → reference.md#BA（业务架构完整设计步骤）
  · 分层原则 + APQC L1 参照见 reference.md#methodology
  · 5.1 task→系统服务推导 → 5.2 流程-服务-单据映射 → 5.3 自动化提升清单
  → 🔒 锁定 BA 文档 → 用户确认 → 才进 Step 3

Step 3: 数据架构文档(DA) → reference.md#DA（数据架构完整设计步骤）→ 5 层资产目录 + 概念模型
  → 🔒 锁定 DA 文档 → 跨域检查 BA→DA → 用户确认 → 才进 Step 4

Step 4: 应用架构文档(AA) → reference.md#AA（应用架构完整设计步骤）→ 6 层应用架构
  · 功能识别方法论见 reference.md#function-identification（AA 子步骤：粒度判断 + 三轨对照）
  → 🔒 锁定 AA 文档 → 跨域检查 BA→AA + DA→AA → 用户确认 → 才进 Step 5

Step 5: 技术架构文档(TA) → reference.md#TA（技术架构完整设计步骤）→ 三横两纵 + 部署架构
  → 🔒 锁定 TA 文档 → 跨域检查 AA→TA → 用户确认 → 才进 Step 6

Step 6: 治理 + 演进文档（可选 · 需人决策 · AI 只出草稿）→ reference.md#governance（责任矩阵 + 演进路线）→ 治理演进草稿供人决策

Step 7: 产品映射文档(如有) → reference.md#product-mapping（产品映射三件套）→ 三件套

─── 阶段二：合并检查 ───
Step 8: 场景穿透验证（D-6 · 外部有效性）→ reference.md#scenario-walkthrough（场景穿透验证）→ 穿透表
  选 3-5 个关键业务场景沿 4A 各层端到端穿透，查断点/错位——证明架构能跑通业务，不只内部自洽
  → 🔒 穿透表通过 → 才进 Step 9

Step 9: 跨域总检查（全局自洽 · 与逐步检查不重复）→ reference.md#cross-domain（4A 关联规则）→ 全链路关联表 + 自洽核对
  查逐步检查查不出的：传递一致性、范围闭合、遗漏发现、术语漂移
  → 🔒 所有文档通过检查 → 才进阶段三

Step 10: 校验清单 → reference.md#checklist（校验清单）
  → 🔒 所有校验项通过 → 才进阶段三

─── 阶段三：画图 ───
Step 11: 生成 HTML 架构图
  · 读取 [styles.md](./styles.md) 获取视觉渲染规范（CSS 类、组件库、配色方案）
  · 根据已确认的文档内容，生成对应的 HTML 架构图
  · 每个 EXHIBIT 必须有对应的文档内容支撑
  · 禁止在画图阶段修改文档内容（如需修改，回到阶段一）
```

**Key constraints**:
- Do not generate any HTML architecture diagram before phase one is complete
- Do not enter phase three unless phase two passes
- If phase three finds document issues, return to phase one to fix; do not change directly in the HTML

**Key rules**:
1. Read only the relevant reference.md section for the current step; do not read the whole file at once.
2. Do not generate BA/DA/AA/TA in parallel.
3. **Lock mechanism (🔒)**: after each step, output a locked checklist and wait for user confirmation before the next step. Format and cross-domain check rules: [reference.md#execution-flow](./reference.md#execution-flow执行流与锁定机制). Scope: valid only in the current session; resuming across sessions requires re-confirmation.
4. Run cross-domain checks step by step, not only at the end.

## Composite Composition (Diagrams Are Assemblies, Not Single Pieces)

Architecture diagrams start from a composite of an architecture board + supporting components, not from an isolated image. Three common composites:

| Composite | Architecture board | Supporting components | What it solves |
|---|---|---|---|
| Architecture board + evidence ledger | Layered architecture diagram | `evidence_ledger` (B-3) | Every design decision carries an evidence number; "what is the basis?" can be traced during defense |
| Architecture board + responsibility matrix | Layered/governance architecture diagram | `raci_matrix` (B-5) | Mandatory pairing for governance architecture: who owns each process and which module it runs in |
| Evolution roadmap + milestone gantt | Evolution roadmap | `milestone_gantt` (B-7) | Replaces weak timeline with ≤4 milestones; task tracks × dependencies laid out by week |

**Architecture evidence chain (D-6 · design decisions carry evidence numbers)**: every design decision carries an evidence number (`EV-<序号>`), sourced from client requirement items / material references. During "what is the basis?" defense, look up `evidence_ledger` (B-3) by number on the spot, not from memory. Evidence numbers in architecture documents correspond one-to-one with `num` in the B-3 ledger: the diagram marks the number, the ledger lists the full evidence text, forming a traceable chain of diagram → number → evidence.

**Four companion slots for every diagram** (diagrams are never isolated; they must have supporting text):

| Slot | Content |
|---|---|
| Conclusion | One sentence: what judgment the reader should take away |
| Legend | Semantics of colors/line styles/symbols (three states, role colors, arrow directions) |
| Source | Basis (material reference / evidence number / reconciliation table section) |
| Action | Next step / items to confirm / owner |

**Subordination when embedded in narrative skills**: when an architecture diagram is embedded in a proposal as a page component, follow `presentation-content-design`'s container (container determines reading) and density decisions — decide the container first, then choose the diagram; do not draw in isolation. Example: container=stage (presentation) → one diagram per screen, conclusion first; container=chapters (long proposal) → pair the diagram with an evidence ledger for expandable basis lookup.

**Page composition declaration (D-122, 2026-08-14)**: architecture diagram pages declare `composition: [architecture_board]` in the spec (or composites such as `[architecture_board, evidence_ledger]`); verify mechanically checks the page actually has an architecture-class diagram; schema validates the enum before rendering. Example:

```yaml
# 单图主张页（stage 容器，一页一屏）
pages:
  - id: arch_overview
    title: "整体架构总图"
    composition: [architecture_board]
    elements:
      - type: diagram
        diagram_type: architecture
        subtype: 4a          # 或 layered / platform_hub / deployment
        # 每图附件四槽位：结论/图例/来源/行动 一并提供

# 架构板 + 证据台账组合体（chapters 容器，可展开查依据）
pages:
  - id: arch_with_evidence
    title: "架构与依据"
    composition: [architecture_board, evidence_ledger]
    elements:
      - type: diagram
        diagram_type: architecture
        subtype: layered
      - type: evidence_ledger
        items:
          - {num: "E-01", claim: "...", status: "已核对"}
```

**4A pass line** (mechanically re-checked by review dimension 5): real entities + boundaries + interfaces + flows — missing any of the four fails structural completeness.

## Output Delivery

- Proposal: `output/{客户}/{客户}_架构蓝图_v{N}.html`
- Product mapping: `output/{客户}/{客户}_{产品名}_产品映射_v{N}.html`
- HTML first → user confirmation → then PPT

## Glossary

| Abbreviation | Meaning |
|---|---|
| AD/AG/APP | Application domain/group/level-1 module |
| ABB | Systematized APQC L4 activities (collaboration units requiring a process owner to coordinate multiple people) |
| CBM | IBM componentized business model |
| APQC PCF | Process classification framework |
| TOGAF ADM | The Open Group Architecture Framework - Architecture Development Method |
| ArchiMate | Enterprise architecture modeling language (three layers: business/application/technology) |
| SOR/SOI | Steady-state IT / agile IT |
| RACI | Responsible/Accountable/Consulted/Informed |
