---
name: presentation-content-design
version: "1.1"
description: "做方案/汇报/HTML/PPT 时调用五步内容设计。Use before outline-to-spec and spec-gen for presentation and report content design."
---

# Presentation Content Design

> This file is an index, not an encyclopedia. Read the relevant [reference.md](./reference.md) anchor on demand.

## When to Invoke

**Invoke**: when making proposals / reports / HTML / PPT or producing IT consulting/report materials, and content needs to be reorganized from client materials (not minor edits to existing output).
**Do not invoke**: architecture-diagram-only tasks (use `architecture-diagram-builder`); editing existing outputs; pure retrieval/reading files; engineering HTML.

**Positioning**: This skill is a **recommended prerequisite** (on demand, not a hard lock) for `outline-to-spec` / `spec-gen`. It provides selection methods for "how each page is told"; spec is just the output format for content design. If the model can organize content itself, it need not run the full process; **lookup value > process value**—container/component/layout mappings are project-specific knowledge the model cannot infer.

## What Problem It Solves

Our chain is "materials → one-step spec-gen mapping → render → verify"; it lacks an explicit **content design** step—decide how each page is told and how content relates before filling spec fields. Currently this step relies on AI improvisation.

Most layout problems stem not from renderer errors but from **wrong telling mode**: a comparison matrix should be used but a card wall is used; an evidence ledger should be used but long paragraphs are used. The rendering layer (`ui-design-system`) only constrains the "shell"; it cannot constrain "what telling mode this page should use"—that is this skill's job.

## Execution Order (Recommended Five-Step Process)

> Acceptance is mechanized (review dimension 5 + verify anti-same-shell/density, 2026-08-13); process has no lock. Run the full process as needed when the model can organize content itself; complex/unfamiliar scenarios recommended. Each step has an output; read the matching reference.md section, not the whole file at once.

```
Step 1: Choose container by reading behavior -> who sees it, what reading behavior -> select container
        Read reference.md#containers (containers A-D + local layouts E-K)
        Output: container decision + reason (one sentence)

Step 2: Choose components by details -> ask per page "what relationship is this content" -> select components
        Read reference.md#components (component library + fallback for missing components)
        Output: per-page component list (page -> component -> information relationship it carries)

Step 3: Build intuition with simulation -> draw what can be drawn, make clickable what can be clicked instead of screenshots
        Read reference.md#simulation (Static / Interactive / Guided Demo + feedback selection table)
        Output: per-page simulation level (Static / Interactive / Guided Demo / none)

Step 4: Choose template for layout -> composition board decides how information is organized on the page
        Read reference.md#composition (12 boards + composite patterns)
        Complex pages read reference.md#template-families (ten recipe cards)
        Output: per-page composition board + mapping to P01-P16 layouts
        **Write spec**: page declares `composition` field (D-122; enum in quick table below,
        multiple values = composite); verify mechanically checks "declared board <-> page components" before render

Step 5: Quality-gate acceptance -> go through checklist item by item
        Read reference.md#quality-gate (anti-degradation list + passing line + eight checks)
        Output: acceptance result (review dimension 5 / verify density check re-checks mechanically after render)
```

**Key constraints**:
- Steps 1-5 are sequential (recommended in order); read the corresponding reference.md section for each step.
- Whether to run the full process is judged by the model based on task complexity (recommended for complex new-material reorganization; optional for fine-tuning/templated generation).
- If telling-mode issues are found after spec generation, go back to Steps 2-4 to revise content design; do not patch spec directly.

## Composition Board Quick Reference (for Step 4 spec, D-122)

`composition` field enum (full semantics in reference.md#composition):

| Enum | Board | Page components expected (verify mechanical hint basis) |
|---|---|---|
| `full_claim` | 全幅主张 | hero / action_title large title |
| `editorial_columns` | 编辑式分栏 | info_cards / pullquote / view_cards |
| `architecture_board` | 架构板 | diagram architecture types (4a/layered/integration/deployment/platform_hub…) |
| `evidence_ledger` | 证据台账 | evidence_ledger / info_cards |
| `flow_spine` | 流程脊柱 | diagram flow types (swimlane/cross_system/parallel…) |
| `scenario_sequence` | 场景序列 | multiple section_tag + action_title |
| `data_narrative` | 数据叙事 | stat_cards / kpi_cards / table |
| `product_simulation` | 仿真产品 | simulation component |
| `timeline_gantt` | 时间线甘特 | diagram timeline types (module_gantt/milestone_gantt) |
| `comparison_matrix` | 对比矩阵 | table / fit_gap / cbm / raci |
| `decision_board` | 决策板 | callout_block / decision-type diagrams |
| `capability_graph` | 能力图谱 | capability_map / platform_hub |

## Three Selection Principles

1. **Container by reading behavior**—does the reader scroll screen by screen, jump by chapter, or follow a presentation?
2. **Component by content relationship**—is this content evidence, division of labor, risk, plan, or decision, not "which shell looks good"?
3. **Template by information relationship**—page information priority/comparison/sequence determines the composition board, not random arrangement.

**Anti-stuffing discipline**: every region on a page must play a clear role (main judgment / main relationship / supporting evidence / example / source / action); do not stack components to look rich.

## Style Direction (When Setting Material Tone)

Eight style categories = eight narrative languages (composition focus + type scale + spatial rhythm + visual language + control language move together), read [reference.md#styles](./reference.md#styles). They complement our 4 style + 4 theme (color/font packages); concrete mapping pending decision.

## Quality Gate Quick Reference (Step 5 acceptance)

> Moved down: these rules are mechanized as review dimension 5 + verify anti-same-shell/density checks (observation mode, 2026-08-13). Full rules in reference.md#quality-gate.

- [ ] Each page has a clear conclusion: judgment + explanation + example, not just a title
- [ ] Data has scope and source: unit, period, business context, and reason for change are all required
- [ ] No hollow conclusions: clichés like "提升效率""加强协同" without object and numbers
- [ ] Consecutive pages change shells: do not use the same card/column set from start to finish
- [ ] Density controlled: no overflow/clipping, no meaningless large whitespace (capacity budget prevention + post-render fallback)
- [ ] Every EXHIBIT has material or content-design support (anti-hallucination rule unchanged)

## Boundaries with Existing Skills

| Skill | Owns | Relationship to this skill |
|---|---|---|
| This skill | **How to tell** (container/component/composition/simulation → content design) | Default prerequisite before spec generation |
| `architecture-diagram-builder` | Expression methodology for architecture diagrams as a single species | Parallel skill; when a page contains architecture diagrams, its page design follows this skill's content design |
| `spec-writing-guide` | How to write spec fields | Downstream: after content design is settled, write fields per it |
| `ui-design-system` | What the renderer consumes (layout/theme/capacity budget) | Downstream: shell spec, does not manage telling mode |
| `delivery-pipeline` | Delivery order (HTML first → confirm → PPT) | Orchestration layer: optional prerequisite before its Step 3 (spec generation) |
| `de-ai-style` | Removes AI flavor from copy | Orthogonal: applies to any generated copy |

## Tool and Process Integration

| Stage | Action |
|---|---|
| Content design | Five-step process → output content design (presented in conversation; not written to spec) |
| Design confirmation | For complex proposals, suggest user review content design (spec confirmation gate is mandatory; content design confirmation optional) |
| Spec generation | `python _cli.py spec-gen <材料> --client <客户> --output <spec.yml>` (fill based on content design) |
| Render validation | `html-build` → `verify` / `review` (mechanical checks for quality-gate rules) |
| Session end | `python _cli.py save <客户>` |

## Decisions (2026-08-13 confirmed, all seven B-1 items per recommendation)

| # | Item | Decision |
|---|---|---|
| 1 | container field | ✅ scroll/chapters/stage/report, default scroll |
| 2 | First 5 components | ✅ 证据台账/风险登记/RACI/决策板/甘特（B-3~B-7） |
| 3 | Quality gate moved down | ✅ review dimension 5 + verify anti-same-shell/density (observation mode) |
| 4 | Simulation components | ⏸️ Pending, reserved simulation field (B-8) |
| 5 | scenario:training | ✅ Added |
| 6 | Access gate | ✅ Already added to pre-generation required skill list |
| 7 | Sedimentation discipline | ✅ See #extension-discipline |

## container Four-Value Selection (Step 1 container reading mode)

| container | Reading behavior | Use for | Recommended layouts | Avoid |
|---|---|---|---|---|
| scroll | single long page, scroll screen by screen | single-page proposals, executive overviews | P01/P03/P04/P08/P11 | P02 chapter pages, P12 TOC pages |
| chapters | jump by TOC | long proposals, requirements analysis | P02/P12 + P03~P10 | none (most flexible) |
| stage | one page per screen, flip through | presentations, on-site reporting | P01~P11 + P16 | long scrolling narrative |
| report | document-style linear deep reading | research reports, white papers | P03/P07/P09/P10 + text elements | P05/P06 image-led |

> Full layout mapping in reference.md#containers.

## training scenario trigger

`scenario: training` is for training/teaching materials (ZSW learning workshop style C). Trigger: content goal is "teach concepts/processes/operations" rather than "report conclusions". Page skeleton = learning actions first (goal → example → exercise → feedback → transfer), medium-low density. Style card in reference.md#training.

## Sedimentation Discipline

For new industries/clients, only sediment: objects, terminology, roles, evidence, fields, common questions. Do not sediment: fixed colors, page counts, card layouts. See reference.md#extension-discipline.
