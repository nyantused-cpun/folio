---
name: ui-design-system
version: "1.0"
description: "HTML/PPT/UI 规范/布局/配色/页眉页脚时调用。Unified UI spec for headers/footers, layout, colors, and component patterns across HTML and PPT outputs."
---

# UI Design System

UI skeleton spec for deliverables. Renderer fixed parts (slide master / HTML head) are controlled by `_renderer/` code; this Skill defines the **non-fixed parts**: header/footer structure, layout grid, color references, component patterns, debug workflow.

## 1. Header/Footer Spec

### HTML

- **header**: `<header>` tag, containing title (h1) + subtitle (p.subtitle) + gradient divider (`border-bottom: 3px solid var(--accent)`)
- **footer**: `<footer>` tag, containing author + date + version
- Content-type tweaks:
  - Architecture diagram: header adds breadcrumb (客户名 > 系统名 > 架构图)
  - Requirements list: header adds version marker (v0/v1/终稿)
  - Portal prototype: header adds nav bar (首页 / 功能 / 报价)

### PPT

- **Top bar**: `header_bar` background color (styles.json `slides.header_bar`) + title text + page number on the right
- **Bottom bar**: divider (`footer_border` color) + date on the left + client name on the right
- Architecture diagram pages: top bar adds "第 N 层" marker

## 2. Layout Rules

- **Grid system**: 12-column grid, 24px gutter
- **Spacing scale**: 4 / 8 / 16 / 24 / 32 / 48px (Tailwind: gap-1 to gap-12)
- **Responsive breakpoint**: 768px (mobile single column)
- **Max width**: max-w-6xl (1152px), centered content
- **Card spacing**: 24px (large screens) / 16px (small screens)

## 3. Color Guidelines

Reference CSS variable names from `_renderer/styles.json`; do not redefine color values.

### Variable mapping

| styles.json path | CSS variable | Use |
|---|---|---|
| `colors.primary` | `--primary` | Titles, header background |
| `colors.accent` | `--accent` | CTA buttons, highlights, emphasis |
| `colors.background` | `--bg` | Page background |
| `html.card_bg` | `--card-bg` | Card background |
| `html.border` | `--border` | Borders, dividers |
| `html.heading_color` | `--heading` | Heading text color |
| `html.text_color` | `--text` | Body text color |

### Disabled colors

- Pure black `#000000`: banned as large-area background (except gov style)
- Pure white `#FFFFFF`: banned as large-area background; use `#f7fafc` / `#f8fafc`
- High-saturation red/green/blue: only for status markers (success/warning/error), not decoration

### Accent color use cases

- `accent`: CTA buttons, highlighted text, icons, dividers
- `primary`: title text, header background, table header background
- Do not use `accent` for large-area backgrounds

## 4. Component Patterns

### Card

```css
.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  padding: 24px;
}
```

### Table

- Header: `table_header_bg` background + white text
- Zebra stripes: even rows `rgba(0,0,0,0.02)` background
- hover: `rgba(0,0,0,0.05)` background
- Border radius: only outer container; cells no individual radius

### Timeline

- Left vertical line: 2px solid `--accent`
- Node dot: 12px, `--accent` background, 3px white border
- Right content: card style, 24px indent

### Tree diagram

- Indent: 20px/level
- Connector: 1px solid `--border`, L-shaped
- Collapse arrow: CSS triangle, 8px

### Standard component CSS snippets

Can reference the component class names above directly in the `custom_css` field of the HTML spec.

## 5. Debug Guidelines

- **HTML debug**: `python _cli.py html-build <spec> --client <客户>` then open the output file in a browser
- **PPT debug**: edit a page via HTML editable mode (`html-build` dual output), then rebuild with `python _cli.py pptd-build <工程目录>/<主>.pptd`; old commands `ppt-page`/`ppt-build`/`html-to-ppt` retired (D-090)
- **After styles.json changes**: rebuild to apply (Renderer re-reads styles.json on each `Renderer.__init__`)
- **verify checks format only**: not UI quality. UI quality is reviewed by `python _cli.py review <文件> --client <客户>`
- **Color check**: use browser dev tools to verify CSS variables load correctly

## 4 UI Style Options

styles.json defines 4 styles; AI selects by client industry/scenario (write into spec's `style` field, or override with `--style` at html-build time):

| Style | Scenario | Keywords | Features |
|------|---------|------|------|
| `education` | 教育/学校 | 教育/学校/校园/师生 | 深蓝白、楷体仿宋 |
| `enterprise` | 企业咨询/汇报 | IT/信息化/咨询/战略/汇报/高管 | 深蓝白、Microsoft YaHei |
| `tech` | 科技/互联网/Demo | demo/演示/极简/原型/POC/科技 | 暗色主题、Noto Sans SC |
| `gov` | 政府公文 | 政府/公文/机关/政务 | 黑红白、仿宋公文体 |

If uncertain, AI should ask the user which style (default enterprise).

## Relationship with architecture-diagram-builder

- This Skill: generic UI skeleton (headers/footers, layout, basic components, color guidance)
- `architecture-diagram-builder/styles.md`: architecture-diagram-specific visuals (6-layer architecture elements, swimlanes, Fit-Gap colors)
- Complementary, no overlap. Architecture diagram pages follow both.

## diagram graphic element layout constraints (27 types, v1.2 final)

Single source of truth: `docs/diagram_visual_design_v1_2026-07-19.md`. Key points:

- **Colors**: blue+green low-saturation variables (no hex literals); semantic color discipline—blue=main/baseline, green=system/target, orange=decision/partial, red=exception (<5%), purple/cyan/gray=architecture layers, cyan=documents
- **Fonts**: Chinese Microsoft YaHei / Latin Helvetica (fallback Arial); titles and emphasis bold (600-700)
- **Technical split**: 8 connector types (flow 5 + ER 2 + data_flow) inline SVG; 19 container types div/table + flex/grid
- **Alignment discipline**: row/column alignment must be bound by grid structure; no three-column independent stacking with hand-written margins (#24 business capability tree lesson)
- **PPT mapping**: all connectors use native connector/preset shape (§4.1 contract); no images, no freeform custGeom
- Each diagram uses its own `<section class="diagram">` container + `.dg-title` + optional `.dg-desc`

## v2.0 theme tokens (frozen 2026-07-25; consulting_kpmg / legacy_bluegreen packages)

spec writes only the theme name (`theme: consulting_kpmg | legacy_bluegreen`, default legacy), no hex literals; rendering side uses CSS variables (`--t-` prefix), no hardcoding.

### consulting_kpmg v2 tokens (2026-08-13 saturation/de-gray upgrade)

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

legacy_bluegreen = v1.2 frozen blue-green adopted as-is (old spec default; visuals unchanged).

### Three-state usage discipline

- Three states appear as a group: green solid = lit / vermilion-orange = partial / red dashed = gap; **gaps must be drawn** (lit contrast is visible only then)
- Coverage expression: drop thin coverage bars; use one large percentage + lit score (`88% · 点亮 15/17`, 24px/800/tabular-nums, colored by state)
- If role colors >2, a legend is required (flow_rows auto-generates; other diagrams hand-write legend_bar)

### Projection safety principles

- Projector reflected light + ambient light wash colors: medium-high saturation + lightness contrast (30-70% saturation range)
- Three-state colors high distinction + projection safe (2026-08-13 saturation/de-gray: gap gray changed to red for visibility; do not change values above)
- No light-gray low-contrast text; dashed lines ≥1.5px dark gray (light dashes disappear in projection)
- chip/badge border 1.5px (readable when projected)

### Chinese typography details

- All-Chinese large titles drop one font size (hero 30px, action_title 21px)
- Numbers: `font-variant-numeric: tabular-nums` (`.num` class)
- Size tiers: page title 20-24 / section title 16-18 / body 12-14 / note 10-11 (px)
- Single-line text (titles/labels/numbers/nav) must set `wrap: false` on the pptd side;
  text box height ≥ fontSize × 1.3 × N lines + paragraph spacing; overflow fix priority: tighten copy > wrap > enlarge box height

### v3.0 Chinese typography additions (2026-08-11, signal blueprint + colleague experience)

- Pangu spacing: add spaces between Chinese and Latin text (`使用 Claude`, not `使用Claude`)
- All-Chinese large titles have no period; body line-height 1.6-1.8, titles 1.2-1.3
- Chinese has no italic axis: emphasize with color (--t-accent) + weight, not `font-style: italic`
- Line breaking: body always `word-break: normal; overflow-wrap: normal` (prevents breaking like 「80000多家」; already applied globally in page_chrome)
- Chinese title size tiers: ≤8 characters use large size; 3+ lines drop one tier (px system, see above)

### v3.0 anti-AI-slop visual checklist (2026-08-11, informed by frontend-slides + huashu-design)

Check before generating any HTML/PPT; rework if any violation:

| Check | Rule |
|--------|------|
| Title font | Ban Inter/Roboto/Arial as display fonts (body OK) |
| Colors | Ban purple gradient on white background; ban large pure-black background + white text stacking |
| Icons | Ban emoji as functional icons (use semantic color blocks/geometry) |
| Cards | Ban the same "rounded card + left colored border" combination |
| Title position | Proposal body titles must be left-aligned; centered only on covers |
| Spacing | Ban stacked double horizontal padding (align with P0 rule) |

## 6. Aesthetic review framework (three-layer gap diagnosis, finalized 2026-07-31)

When reviewing deliverable screenshots (HTML/PPT), diagnose the root cause of "looks simple/not premium" using these three layers, **not just surface items like misalignment/colors/whitespace**; benchmark against old material density:

1. **Page-level layout language missing as a whole**: does the page have a complete design language—gradient hero banner (with version/date/subject meta), top tab nav, section numbers (一、二、三 + diamond decoration), top-left EX-XX number + top-right header, bottom legend bar, bottom three-column info cards, inline red emphasis text; or is it "figure is figure, page is page", with a diagram isolated on a white page with only dg-title + figure body?
2. **Diagram as single item vs composite**: old material one "diagram" = flowchart + legend + bottom three info cards; CBM matrix = numbered labels + dark header + red-bordered badge array + legend bar. Does the renderer's diagram element only have one figure, without stats / legend / notes / callout attachment slots?
3. **Single visual vocabulary**: do multiple subtypes share one node language (white background blue border + left color bar + sequence dots), making every page feel the same; are there grouping hierarchies, numeric emphasis, balanced whitespace?

Output format: A. Diagnosis (against the three layers item by item) B. Prioritized actionable improvements (specific: what element to add / what style to change).

Usage: `python _cli.py vision-describe <截图> --prompt "<第1/2/3层问题 + 输出格式>"`.
If vision-describe returns empty (visual key not configured / agent multimodal / network failure), must explicitly tell the user "visual self-check not run"; do not claim it ran; fall back to manual screenshot spot checks.
State medium differences objectively (16:9 PPT pages vs long-scroll HTML pages), but PPT must achieve old-material density.
