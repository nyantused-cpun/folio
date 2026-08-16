---
name: delivery-pipeline
version: "1.2"
description: "交付流水线：HTML 先行 -> 用户确认 -> 再出 PPT/DOCX/报价。Orchestrates the delivery flow: HTML first, user confirms, then PPT/DOCX/quote."
---

# Delivery Pipeline

This skill orchestrates the mandatory delivery order: **HTML first → user confirms → PPT/DOCX/quote**. It exists because AI tends to skip steps or jump straight to PPT, which breaks the anti-hallucination defenses (defense 3 spec block + defense 4 verify fallback).

## When to Invoke

- User says: generate proposal / make HTML / make PPT / make a report / produce a quote / generate spec
- User mentions a client name + any generation verb
- User uploads client material and asks for a deliverable

Do NOT invoke for: pure retrieval (`recall`/`status`/`pending`), file reading, or single-step `verify`.

## Pipeline Steps

The order below is canonical — never reorder or skip.

### Step 1 — Session start (MANDATORY first call)

```bash
python _cli.py session-start "<用户输入>" --client <客户名>
```

Read the output: `level` (Creative/L5/L4/L3), `context_summary`, `recall`, `warnings`. If `level == L3`, `spec.confirmed` is required before any generation. If session-start fails, fall back manually: read `.folio/logs/task_history.json` + `_knowledge/clients/{客户}/context.md`.

Output a context summary to the user: "Last time we did xxx, pending yyy; continue?"

### Step 2 — Theme guard (refresh when switching topics)

```bash
python _cli.py theme-guard <客户名>
```

Session-start and generation commands already inject `[PERMANENT-*]` constraints internally. This step only needs a manual refresh **before writing spec (new task/topic switch)**, and the constraints must be pasted at the HEAD of the answer. For long conversations, refresh faithfully every 10 turns with `theme-guard <客户名> --turn <N>`.

### Step 3 — Content design then spec generation (L3 hard gate)

**Content design** (optional, not mandatory): when reorganizing content from client materials, consult the container/component/layout mapping tables in the `presentation-content-design` skill to define "how each page tells its story" first (recommended; acceptance is mechanically covered by review dimension 5 + verify density check).

Spec is the contract. Without `confirmed: true`, `html-build`/`docx-build`/`quote-build`/`pptd-gen` raise `RenderBlockedError`. Generation commands and field rules see `spec-writing-guide`.

After generating a draft spec, **show it to the user** and ask for confirmation. Only set `confirmed: true` after the user agrees.

### Step 4 — HTML build (HTML first, dual-source output D-088)

```bash
python _cli.py html-build <spec.yml> <output.html> --client <客户名> [--style education|enterprise|tech|gov] [--pptd <工程目录>] [--html-only] [--inline-editor]
```

One command outputs both `.html` + `.pptd` project (the source for PPT). HTML has built-in editing (toolbar: edit / color / export / reset, D-091).

Output path must follow the naming convention `{客户}_{类型}_{版本}.{格式}`, e.g. `蓝海集团_需求分析与能力矩阵_v0.html`. Output lands in `output/{客户}/`.

After generation, the CLI auto-runs `verify` + theme-guard/theme coverage check (defense 4). Read the report. If permanent-theme coverage reports missing items, fix the spec and rebuild.

### Step 5 — User confirmation gate (HARD STOP)

**Stop here.** Show the HTML to the user and explicitly ask: "HTML generated; please confirm whether to continue with PPT?" Do NOT proceed to PPT/DOCX/quote until the user confirms. This is the single most violated rule — enforce it.

### Step 6 - PPT / DOCX / quote (only after confirmation)

**PPT's only official route** (D-088/D-090): `html-build` already produced the `.pptd` project; after confirmation, run `pptd-build` directly to convert to rich-media PPT. Old routes `ppt-build` / `html-to-ppt` / `ppt-page` are retired (D-090; calling them prints a deprecation notice).

```bash
# 富媒体 PPT：pptd 工程 -> 原生连接符/图形的正式 PPT
python _cli.py pptd-build <工程目录>/<主>.pptd [--check-only] [--shots] [--client <客户名>]
# 一键编排（协调逻辑外置，P1-5）：spec -> html-build -> pptd-build
python _cli.py deliver <spec.yml> <输出.html> [--pptd <工程目录>] [--shots] [--client <客户名>]
```

- `--shots` exports per-page PNGs for visual inspection; `--inline-editor` (html-build side) embeds the editor into the HTML.
- For standalone project skeletons (not via html-build dual output): `python _cli.py pptd-gen <spec.yml> --client <客户> --name <项目名> [--style <样式>] [--logo <logo路径>] [--final-page]`.

DOCX:
```bash
python _cli.py docx-build <spec.yml> <output.docx> --client <客户名>
```

Quote:
```bash
python _cli.py quote-build <spec.yml> <output> --template <版式名> --format html|xlsx|all --client <客户名>
```

### Step 7 — Session end (MANDATORY)

```bash
python _cli.py save <客户名>
```

Then record key decisions to `_knowledge/clients/{客户}/decisions.md` (see `decision-recording` skill). Check `inbox/` for residual `.py/.log/.tmp` files — none allowed.

## Input/Output Contract

- **Input**: user request string + optional client material file path
- **Output**: deliverable in `output/{客户}/` + updated `task_history.json` + `decisions.md` entries
- **Naming**: `{客户}_{类型}_{版本}.{格式}`

## Examples

### Example 1 — Standard HTML proposal

User: "帮蓝海集团生成一份 HTML 方案"

1. `session-start "帮蓝海集团生成一份 HTML 方案" --client 蓝海集团`
2. `theme-guard 蓝海集团`
3. (spec already exists and confirmed) → skip spec-gen
4. `html-build spec.yml output/蓝海集团/蓝海集团_方案_v0.html --client 蓝海集团` (also outputs `.pptd` project)
5. Show HTML, ask "Continue with PPT?"
6. (user says yes) → `pptd-build output/蓝海集团/蓝海集团_方案_v0/蓝海集团_方案_v0.pptd --client 蓝海集团`
7. `save 蓝海集团`

### Example 2 — New client from material

User: "这是蓝海集团的需求文档，帮我出方案"

1. `session-start "..."` (no --client, extract from input)
2. Move material to `_knowledge/clients/蓝海集团/refs/` (see `customer-material-onboarding` skill)
3. `spec-gen <材料> --client 蓝海集团 --output spec.yml`
4. Show draft spec, ask for confirmation → user confirms → set `confirmed: true`
5. `theme-guard 蓝海集团`
6. `html-build ...`
7. STOP at confirmation gate

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RenderBlockedError: spec not confirmed` | spec.yml lacks `confirmed: true` | Ask user to confirm spec, then set field |
| `NotInvokedViaCLIError` | Tried to `import _renderer` directly | All generation must go through `python _cli.py` |
| Theme coverage check reports low coverage | Spec content missing permanent-theme keywords | Read `theme-guard` output, add missing keywords to spec, rebuild |
| `verify` reports file too small / empty | Renderer silently failed | Check `_renderer/` logs, re-run with valid spec |
| `ppt-build` / `html-to-ppt` / `ppt-page` prints deprecation notice | These commands retired (D-090) | Use `html-build` dual output + `pptd-build` (or `deliver`) |
| User asks for PPT directly without HTML | Pipeline violation | Explain "HTML first" rule, generate HTML first |

## Defense Layers (context, do not bypass)

| Layer | Mechanism | This skill's role |
|---|---|---|
| L1 | Entry MD rules | Step 1 loads them via session-start |
| L2 | CLI env var + spec.confirmed | Step 3 enforces spec gate |
| L3 | This skill | Orchestrates the order |
| L4 | verify + theme-verify auto-run | Step 4 reads the report |
