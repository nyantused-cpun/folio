---
name: customer-material-onboarding
version: "1.0"
description: "新客户入库：建目录、摄入参考材料、提取决策、重建索引。当用户说新客户 / 入库 / 上传材料 / 接单时调用。Onboards a new client: creates directory structure, ingests materials into refs/, extracts decisions, rebuilds indexes."
---

# Customer Material Onboarding

Standardizes how a new client enters the knowledge base. Without this skill, AI tends to dump files in `inbox/` and forget to create `context.md`/`decisions.md`/`aliases.yml`, leaving the client half-onboarded and breaking later retrieval.

## When to Invoke

- User mentions a client name not yet in `_knowledge/clients/`
- User uploads a file (docx/pdf/xlsx/md) that looks like client material
- User says: 新客户 / 入库 / 整理材料 / 建客户档案 / 接单
- `session-start` returns a client name with no matching directory

Do NOT invoke for: existing client follow-up (use `delivery-pipeline`), generic snippet saving, or output file management.

## Standard Client Directory Structure

Every client MUST have this structure. Missing files indicate incomplete onboarding.

```
_knowledge/clients/{客户}/
├── context.md            # 会话历史 + 关键背景
├── decisions.md          # 决策记录（带 persistence + scope 字段）
├── aliases.yml           # 客户别名（系统名 / 业内名 / 简称）
├── outputs_index.json    # 该客户产出物索引
├── preferences.md        # 客户偏好（风格 / 禁用词 / 主题色）
└── refs/                 # 参考材料原文
    ├── *.docx / *.pdf / *.xlsx / *.md
    └── _txt/             # 可选：纯文本提取结果
```

## Onboarding Steps

### Step 1 — Confirm client name

Extract client name from user input. If ambiguous (e.g. "蓝海控股" vs "蓝海集团"), ask the user which name to use as the folder name, and record the other as an alias in `aliases.yml`.

### Step 2 — Create directory structure

If `_knowledge/clients/{客户}/` does not exist:

```bash
python _cli.py new <客户名> [--scene <场景名>] [--html] [--quote]
```

`new` handles: mkdir → classify → parse → outline-to-spec draft. If you only need the skeleton (no spec yet), manually create the directories and empty files:

```bash
mkdir -p "_knowledge/clients/{客户}/refs"
```

Then create empty `context.md`, `decisions.md`, `aliases.yml`, `outputs_index.json` (`{}`), `preferences.md`.

### Step 3 — Move materials to refs/

User-provided files belong in `_knowledge/clients/{客户}/refs/`, NEVER in `inbox/` long-term. `inbox/` is for transient input only.

Naming: keep original filename if meaningful; otherwise rename to `{客户}_{材料类型}_{日期或版本}.{格式}`, e.g. `蓝海集团_分项功能清单_20251226V2.0.xlsx`.

For binary formats (docx/pdf/xlsx), optionally extract plain text to `refs/_txt/{basename}.txt` for faster retrieval.

### Step 4 — Full-text read and extract

Read each material fully (禁止凭前 N 字符下结论 — see project rules):

```bash
python _cli.py read <文件路径>
```

For multiple files, iterate. Extract:
- **Business background** → append to `context.md`
- **Key decisions / constraints / scope** → append to `decisions.md` (see `decision-recording` skill for format)
- **System names / vendor names / aliases** → append to `aliases.yml`
- **Style preferences / forbidden words / theme colors** → append to `preferences.md`

### Step 5 — Build aliases

```bash
python _cli.py aliases --client <客户名> --edit
```

Record at minimum: official name, common name, short name, system names mentioned. Aliases power `recall` and `theme-guard` keyword matching.

### Step 6 — Rebuild indexes

After materials land in `refs/`, rebuild both indexes so `recall` can find them:

```bash
python _cli.py index-rebuild
python _cli.py embed-rebuild
```

Use `--force` only for full rebuilds (slow). For incremental adds, omit `--force`.

Verify a single file's chunking:

```bash
python _cli.py chunk-inspect <文件路径>
```

### Step 7 — Initialize theme guard

If the client has permanent constraints (e.g. "ERP 不动", "UMU 必须替换"), record them in `decisions.md` with `persistence: permanent` and `scope: client`, then:

```bash
python _cli.py theme-guard <客户名>
```

This loads `[PERMANENT-CLIENT]` constraints into the HEAD context for all subsequent generation.

### Step 8 — Verify onboarding completeness

Checklist before declaring onboarding done:

- [ ] `context.md` has at least one section with business background
- [ ] `decisions.md` exists (can be empty if no decisions yet, but file must exist)
- [ ] `aliases.yml` has the client's own names
- [ ] `refs/` contains the original materials
- [ ] `index-rebuild` and `embed-rebuild` ran without errors
- [ ] `recall "<客户名>"` returns the new materials

## Input/Output Contract

- **Input**: client name + 1+ material files (in `inbox/` or user-provided paths)
- **Output**: complete client directory under `_knowledge/clients/{客户}/` + indexed materials
- **Side effects**: `index.json` and embedding index updated; `task_history.json` updated on `save`

## Examples

### Example 1 — New client with one docx

User: "这是蓝海集团的需求文档，帮我入库"

1. Confirm folder name = `蓝海集团`
2. `python _cli.py new 蓝海集团` (creates skeleton + draft spec)
3. Move `需求文档.docx` from `inbox/` to `_knowledge/clients/蓝海集团/refs/`
4. `python _cli.py read _knowledge/clients/蓝海集团/refs/需求文档.docx`
5. Extract background → `context.md`, constraints → `decisions.md`, system names → `aliases.yml`
6. `python _cli.py aliases --client 蓝海集团 --edit`
7. `python _cli.py index-rebuild && python _cli.py embed-rebuild`
8. `python _cli.py chunk-inspect 需求文档.docx` (verify chunking)
9. Run completeness checklist

### Example 2 — Existing client, add material

User: "蓝海集团又给了一份痛点汇总，加进去"

1. Skip Step 2 (directory exists)
2. Move file to `_knowledge/clients/蓝海集团/refs/`
3. `python _cli.py read <file>`
4. Extract new decisions / pain points → append to existing `decisions.md` / `context.md`
5. `python _cli.py embed-rebuild` (incremental)
6. `python _cli.py theme-guard 蓝海集团` (refresh if new permanent constraints added)

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `recall` does not return new material | Index not rebuilt | Run `index-rebuild` then `embed-rebuild` |
| `chunk-inspect` shows empty chunks | File binary / encoding issue | Extract text to `refs/_txt/{name}.txt`, rebuild |
| `new` command fails | Client name has special chars | Use `_safe_filename` rules: keep CJK + alnum + `_-` |
| Duplicate client directory (e.g. `蓝海集团` + `蓝海控股`) | Naming inconsistency | Pick one as canonical, other as alias; merge or symlink |
| `aliases.yml` parse error | Bad YAML (tabs / unquoted colons) | Validate YAML, quote values with special chars |
| Material left in `inbox/` | Step 3 skipped | Move to `refs/` immediately; `inbox/` allows no residual |

## Notes

- **去厂商名**: when recording system names in `aliases.yml`, write system names (e.g. "协同办公系统") not vendor names (e.g. "泛微 e-cology"). Vendor names go in a `vendor_names` field if needed for reference.
- **全文读取**: never conclude from the first N characters. Use `read` to load the full document.
- **Decisions format**: see `decision-recording` skill — every entry needs `persistence` + `scope` fields.
