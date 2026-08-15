---
name: delivery-pipeline
version: "1.2"
description: "交付流水线：HTML 先行 -> 用户确认 -> 再出 PPT/DOCX/报价。当用户说生成方案 / 做方案 / 生成 HTML / 做 PPT / 生成报价时调用。Orchestrates the delivery flow: HTML first, user confirms, then PPT/DOCX/quote. v1.2: 内容设计改为按需参考（验收端已机械化，过程不设锁），spec 命令细节收敛到 spec-writing-guide；v1.1: 对齐 D-088/D-090。"
---

# Delivery Pipeline

This skill orchestrates the mandatory delivery order: **HTML first → user confirms → PPT/DOCX/quote**. It exists because AI tends to skip steps or jump straight to PPT, which breaks the anti-hallucination defenses (防线 3 spec 阻断 + 防线 4 verify 兜底).

## When to Invoke

- User says: 生成方案 / 出 HTML / 做 PPT / 做汇报 / 出报价 / 生成 spec
- User mentions a client name + any generation verb
- User uploads client material and asks for a deliverable

Do NOT invoke for: pure retrieval (`recall`/`status`/`pending`), file reading, or single-step `verify`.

## Pipeline Steps

The order below is canonical — never reorder or skip.

### Step 1 — Session start (MANDATORY first call)

```bash
python _cli.py session-start "<用户输入>" --client <客户名>
```

Read the output: `level` (创意/L5/L4/L3), `context_summary`, `recall`, `warnings`. If `level == L3`, spec.confirmed is required before any generation. If session-start fails, fall back manually: read `.trae/logs/task_history.json` + `_knowledge/clients/{客户}/context.md`.

Output a context summary to the user: "上次做了 xxx，待办 yyy，要继续吗？"

### Step 2 — Theme guard (切换话题时刷新)

```bash
python _cli.py theme-guard <客户名>
```

Session-start 与生成命令内部已自动注入 `[PERMANENT-*]` 约束。本步只在**写 spec 前（新任务/切换话题）**需要人工刷新一次，且约束必须贴在回答 HEAD。长对话每 10 轮用 `theme-guard <客户名> --turn <N>` 保真刷新。

### Step 3 — Content design then spec generation (L3 hard gate)

**内容设计**（按需，非强制）：从客户材料重新组织内容时，参考 `presentation-content-design` skill 的容器/组件/版式映射表先定「每页怎么讲」（推荐；验收由 review 第 5 维 + verify 密度检查机械化兜底）。

Spec is the contract. Without `confirmed: true`, `html-build`/`docx-build`/`quote-build`/`pptd-gen` raise `RenderBlockedError`. 生成命令与字段规则见 `spec-writing-guide`。

After generating a draft spec, **show it to the user** and ask for confirmation. Only set `confirmed: true` after the user agrees.

### Step 4 — HTML build (HTML 先行，同源双输出 D-088)

```bash
python _cli.py html-build <spec.yml> <output.html> --client <客户名> [--style education|enterprise|tech|gov] [--pptd <工程目录>] [--html-only] [--inline-editor]
```

一次同出 `.html` + `.pptd` 工程（PPT 的源头）。HTML 自带可编辑能力（工具条：编辑/配色/导出/重置，D-091）。

Output path must follow the naming convention `{客户}_{类型}_{版本}.{格式}`, e.g. `蓝海集团_需求分析与能力矩阵_v0.html`. Output lands in `output/{客户}/`.

After generation, the CLI auto-runs `verify` + theme-guard/主题覆盖检查 (防线 4). Read the report. If permanent-theme coverage reports missing items, fix the spec and rebuild.

### Step 5 — User confirmation gate (HARD STOP)

**Stop here.** Show the HTML to the user and explicitly ask: "HTML 已生成，请确认是否继续做 PPT？" Do NOT proceed to PPT/DOCX/quote until the user confirms. This is the single most violated rule — enforce it.

### Step 6 - PPT / DOCX / quote (only after confirmation)

**PPT 唯一正式路线**（D-088/D-090）：`html-build` 已同出 `.pptd` 工程，确认后直接 `pptd-build` 转富媒体 PPT。旧路线 `ppt-build` / `html-to-ppt` / `ppt-page` 已退役（D-090，调用只打印废弃提示）。

```bash
# 富媒体 PPT：pptd 工程 -> 原生连接符/图形的正式 PPT
python _cli.py pptd-build <工程目录>/<主>.pptd [--check-only] [--shots] [--client <客户名>]
# 一键编排（协调逻辑外置，P1-5）：spec -> html-build -> pptd-build
python _cli.py deliver <spec.yml> <输出.html> [--pptd <工程目录>] [--shots] [--client <客户名>]
```

- `--shots` 逐页导出 PNG 目检；`--inline-editor`（html-build 侧）把编辑器内联进 HTML。
- 需要独立工程骨架（不走 html-build 双输出）时：`python _cli.py pptd-gen <spec.yml> --client <客户> --name <项目名> [--style <样式>] [--logo <logo路径>] [--final-page]`。

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
4. `html-build spec.yml output/蓝海集团/蓝海集团_方案_v0.html --client 蓝海集团`（同出 .pptd 工程）
5. Show HTML, ask "继续做 PPT 吗？"
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
| 主题覆盖检查 reports low coverage | Spec content missing permanent-theme keywords | Read `theme-guard` output, add missing keywords to spec, rebuild |
| `verify` reports file too small / empty | Renderer silently failed | Check `_renderer/` logs, re-run with valid spec |
| `ppt-build` / `html-to-ppt` / `ppt-page` prints 废弃提示 | These commands retired (D-090) | Use `html-build` dual output + `pptd-build` (or `deliver`) |
| User asks for PPT directly without HTML | Pipeline violation | Explain "HTML 先行" rule, generate HTML first |

## Defense Layers (context, do not bypass)

| Layer | Mechanism | This skill's role |
|---|---|---|
| L1 | Entry MD rules | Step 1 loads them via session-start |
| L2 | CLI env var + spec.confirmed | Step 3 enforces spec gate |
| L3 | This skill | Orchestrates the order |
| L4 | verify + theme-verify auto-run | Step 4 reads the report |
