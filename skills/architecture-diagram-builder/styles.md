# Visual Rendering Spec (styles.md)

> This file is split from reference.md and dedicated to visual rendering of HTML architecture diagrams.
> **When to use**: read this file after finishing the 4A documents and passing merge checks, when drawing diagrams from the final documents.

---

## v4.0 Major Change: Shared Visual Language Delegated

**The single source of truth for colors, semantic colors, fonts, stacked rows, integration double-frames, timelines, Fit-Gap three-color, and mapping components (`archimate`/`automation`/`cross-table`/`fit-table`) has moved to `docs/diagram_visual_design_v1_2026-07-19.md`** (27 diagram visual specs v1.2).

When drawing 4A architecture diagrams:
- General visual rules (colors/fonts/semantic-color discipline) → read design spec §1-§2
- Swimlane/stacked/integration/timeline/matrix/mapping drawing → read design spec §3 (matching subtype entry)
- **This file keeps only architecture-diagram-builder-specific content**: 6-layer architecture element system, principle cards, simple columns, rendering rules, EXHIBIT conventions

Division between the two systems:
- Hand-drawn 4A architecture diagrams (this skill's workflow) → this file + design spec
- Spec structured diagrams (`type: diagram`, html-build dual output) → design spec + `_renderer/diagram/`

---

## Core Principles

1. **Guarantee pixel-perfect consistency between HTML and PPT**: write HTML/CSS directly, do not use declarative syntax like Mermaid, so rendering is fully controlled
2. **Use only blue + green**; no orange/red/yellow (except special cases such as Fit-Gap)
3. **Blue background with white/black text** is primary; green is auxiliary
4. **Unified fonts**: Chinese Microsoft YaHei, Western Helvetica (fallback Arial), bold headings
5. **Minimum font size 12px**, recommended 14px, readable when projected
6. **Use background colors to distinguish layers**, fewer borders

Colors and CSS variables: follow **design tokens in `docs/diagram_visual_design_v1_2026-07-19.md` §2** (low-saturation blue `#1B5E8A` / green `#2F7D5F` system + semantic-color discipline).

---

## 6-Layer Architecture Elements (Blue + Green · v6 Confirmed)

| Layer | Background | Text | Description |
|---|---|---|---|
| AD application domain | `--blue` dark blue background | White text | Outermost large container wrapping everything |
| AG application group | `--blue-light` light blue background | `--blue` blue text | Nested inside AD |
| APP level-1 module | `--blue` dark blue background | White text | Card title, centered, 3-column grid |
| ABB level-2 module | `--green` dark green background | White text | Grid left column fixed 110px |
| Function item | `--green-light` light green background | `--green` green text | Grid right column, flex wrap |
| Function subitem | White background | `--text-sub` gray text | Not drawn, document only |

**Layout rules**:
- AD: wrap the whole architecture diagram in `.ad-box` dark blue large container
- AG: nest `.ag-box` light blue inside AD
- APP: use `.app-grid` 3-column grid; each APP is an `.app-card` white card
- APP title `.app-name` centered
- ABB rows use `.abb-row` Grid layout: left column ABB fixed 110px, right column function items adaptive
- Core APP gets `.core` class (red border); new APP gets `.new-app` class (green border)

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

## Architecture-Diagram-Specific Components

### Simple Column Lanes (for BA, Not Process Swimlanes)

> A simple div-column layout for listing points by role in BA documents.
> **For process swimlane diagrams (with nodes and arrows), use design spec §3.1 flow/swimlane (SVG).**

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

### Principle Cards

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

## Rendering Rules

1. **Every section must have a diagram**: text bullets alone are not enough; include nested div boxes or HTML tables
2. **No Mermaid**: all diagrams use HTML/CSS nested div boxes
3. **Nested div boxes use CSS classes**: `.ad-box` / `.ag-box` / `.app-card` / `.abb-row` / `.func-item`
4. **Tables must use three-color marking** (Fit-Gap scenarios): Fit green background / Partial yellow background / Gap red background (drawing: design spec §3.3 fit_gap)
5. **Every diagram must have a title**: above each nested box, use `### EXHIBIT N: 标题`
6. **Unified colors**: only blue + green, no orange/red/yellow (except Fit-Gap)
7. **Layout**: AD large container → AG nested → APP 3-column grid cards → ABB rows aligned with Grid (left 110px + right adaptive)
8. **Soft colors**: use low-saturation palette, avoid overly vivid colors
9. **Alignment discipline**: row/column alignment is bound by grid structure; do not hand-write margins to fake alignment with independent stacked columns (same rule as design spec §3.5)

### Exception-Flow Rules (reference.md §5.2 Mandatory)

Exception flows / return flows in EXHIBIT 6 (process-service-document) **must** be marked with red dashed lines using `.exception-note`.
Drawing for the four EXHIBIT 6-9 mapping diagrams (`.archimate` / `.automation-table` / `.cross-table` / `.fit-table`):
**Follow design spec §3.5 matching subtypes** (process_service_doc_mapping / automation_table / cross_4a_reconcile / fit_gap), with consistent color semantics (blue=manual/BA · green=system/AA · cyan=document/TA · purple=DA · orange=decision/partial · red=exception/gap).

---

## Document Version

- **Version**: v4.0 (2026-07-19 · shared visual language delegated to `docs/diagram_visual_design_v1`; this file keeps the architecture-diagram-specific system)
- **Created**: 2026-07-07
- **History**: v3.0 reduced saturation + card grid layout + ABB row alignment; v3.1 added TA stacked colors + EXHIBIT 6/7/8/9 mapping components; v4.0 removed content duplicated with the design spec (color variables/stacked rows/integration double-frames/timeline/Fit-Gap/mapping components)
- **Purpose**: visual rendering spec for HTML architecture diagrams (architecture-diagram-builder-specific layer)
- **Confirmation status**: user confirmed v6 UI; v4.0 delegation structure
