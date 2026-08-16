---
name: decision-recording
version: "1.0"
description: "用户说记一下或 AI 识别关键决策时调用。Records key decisions to decisions.md with persistence + scope fields."
---

# Decision Recording

Decisions are the project's memory. Without them, AI re-litigates the same questions every session and drifts from client constraints. This skill enforces the `persistence` + `scope` field convention that powers `theme-guard` HEAD injection.

## When to Invoke

- User says: note this down / record decision / log this / decisions
- AI detects a key decision during work:
  - Architecture / scope decisions (e.g. "7 系统一次性切换")
  - Business rule confirmations (e.g. "ERP 不动")
  - Client explicit preferences (e.g. "教育蓝主题色 #1a365d")
  - Naming conventions (e.g. "客户文件夹用蓝海集团, 官方名蓝海控股")
- Before `python _cli.py save <客户>` at session end — review the session for unrecorded decisions

Do NOT invoke for: transient task state (use `context.md`), pure material extraction (use `customer-material-onboarding`), or style tweaks already in `preferences.md`.

## The persistence + scope Model

From `src/_theme_guard.py:9-13`:

| persistence | scope | Meaning | Loaded by theme-guard? |
|---|---|---|---|
| `permanent` | `client` | Iron rule: always applies across sessions and tasks | ✅ Always |
| `permanent` | `task` | Task constraint: fixed for the whole current task | ✅ Only when task_id matches |
| `task` | `client` | (rare) temporary client-level constraint | ❌ Only with only_permanent=False |
| `task` | `task` | Temporary task constraint; archived when the task ends | ❌ Only with only_permanent=False + task_id match |

**Backward compatibility**: entries without `persistence`/`scope` fields default to `permanent + client` (so old iron rules don't silently disappear). But always write the fields explicitly for new entries.

## Decision Entry Format (canonical)

Write to `_knowledge/clients/{客户}/decisions.md`. Append to the file, do not rewrite existing entries.

```markdown
## [YYYY-MM-DD] <topic>
- **决策**: <one-sentence decision content>
- **理由**: <why this way>
- **否决方案**: <why not the alternative, if any>
- **来源**: <user input / material file / AI inference>
- **影响范围**: <what this affects downstream>
- **层级**: L4
- **persistence: permanent**
- **scope: client**
```

For `scope: task`, add `- **task_id: <id>**` (use `YYYYMMDD_HHMMSS` or a meaningful task name).

### Field rules

- **决策** — one sentence, the actual decision. Not "discussed X", but "X = Y".
- **理由** — why this way. Required (project rule: preserve decision rationale).
- **否决方案** — why NOT the alternative. Optional but strongly recommended for architecture decisions.
- **来源** — traceability: user quote / material file path / "AI 推断".
- **影响范围** — what downstream work changes because of this.
- **层级** — `L3`/`L4`/`L5`, matches the session level when the decision was made.
- **persistence** — `permanent` or `task`.
- **scope** — `client` or `task`.

## How to Record

### Option A — CLI command (preferred for explicit user requests)

```bash
python _cli.py theme-guard <客户名> --set "<topic>" --scope client
```

This calls `_theme_guard.save_decision()` which writes the canonical format. Use when user explicitly says "note this down" with a clear topic.

### Option B — Manual append (for AI-detected decisions during work)

Use the Edit tool to append to `_knowledge/clients/{客户}/decisions.md`. Follow the canonical format exactly. The `theme-guard` parser uses regex on `persistence:` and `scope:` fields — keep the format `**persistence: <value>**` (with the asterisks and colon).

### Option C — Session-end batch review

Before `save <客户>`, scan the session for unrecorded decisions. If found, append them in batch using Option B, then run `save`.

## Input/Output Contract

- **Input**: decision topic + content + reason + (optional) rejected alternative + source
- **Output**: appended entry in `_knowledge/clients/{客户}/decisions.md`
- **Side effects**: `theme-guard <客户>` will pick up `permanent` entries on next call; `theme-verify` will check keyword coverage in generated files

## Examples

### Example 1 — Permanent client constraint (user explicit)

User: "记一下，ERP 这套不动，这次只做上面 7 个系统的替换迁移"

1. Confirm: this is an iron rule (cross-session, cross-task)
2. Append to `_knowledge/clients/蓝海集团/decisions.md`:

```markdown
## [2026-07-04] ERP 与基础 IM 不替换
- **决策**: ERP 和 IM 在本次系统迁移中保持不变，仅替换 7 个上层系统
- **理由**: ERP 是财务底座，动则牵一发动全身；IM 已深度使用，无替换价值
- **否决方案**: 全量替换 ERP —— 风险与周期不可控
- **来源**: 用户明示
- **影响范围**: 所有方案中 ERP 出现在"集成对象"而非"替换对象"；预算不含 ERP 许可
- **层级**: L4
- **persistence: permanent**
- **scope: client**
```

3. Run `python _cli.py theme-guard 蓝海集团` to verify it loads as `[PERMANENT-CLIENT]`

### Example 2 — Task-scoped constraint

User: "这次 PPT 用教育蓝主题色 #1a365d"

1. This is task-scoped (only this PPT, not all future deliverables)
2. Append:

```markdown
## [2026-07-04] PPT 主题色
- **决策**: 本次 PPT 使用教育蓝 #1a365d
- **理由**: 客户偏好，教育局背景
- **来源**: 用户明示
- **影响范围**: 本次 PPT 配色；不影响 HTML 方案（HTML 已生成）
- **层级**: L3
- **persistence: task**
- **scope: task**
- **task_id: 20260704_ppt_color**
```

### Example 3 — AI-detected architecture decision

During spec review, AI notices the spec lists "asset management" as a core system, but the user previously said all 7 systems are parallel. AI should:

1. Flag the inconsistency to the user
2. After user confirms "对，7 系统并列，不突出资产管理"
3. Record:

```markdown
## [2026-07-04] 7 系统并列展示
- **决策**: CBM 矩阵中 7 个系统并列展示，不将资产管理作为核心系统突出
- **理由**: 客户明确表态 7 系统同等优先级；避免误导客户对范围的理解
- **否决方案**: 突出资产管理 —— 与客户表态冲突，可能引发范围争议
- **来源**: AI 推断 + 用户确认
- **影响范围**: 所有 CBM 矩阵 / 系统架构图 / 能力矩阵的渲染
- **层级**: L4
- **persistence: permanent**
- **scope: client**
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `theme-guard` doesn't load the new entry | Field format wrong | Must be `**persistence: permanent**` (asterisks + colon + space + value) |
| Entry appears as `task` instead of `permanent` | Field missing or typo | Add `**persistence: permanent**` explicitly; default is permanent but don't rely on it |
| `theme-verify` reports keyword not covered | Decision keywords not in generated content | Either add keywords to spec content, or the decision is too narrow (consider if it's really permanent) |
| Duplicate decisions recorded | Same decision re-recorded across sessions | Before recording, `grep` decisions.md for the topic; if exists, update the existing entry instead of appending |
| Old format entries (no persistence/scope) | Pre-migration decisions | Leave them — backward compat treats them as permanent+client. Only add fields when editing them |

## Anti-patterns (do NOT)

- Record transient state as `permanent` (e.g. "今天的会议纪要" — that's `context.md`)
- Record without `理由` (project rule: preserve decision rationale)
- Use `scope: task` without `task_id` (parser will synthesize one from timestamp, but meaningful ids are better)
- Rewrite existing entries (append-only; if wrong, add a new entry that supersedes it)
- Record decisions the user didn't actually make (AI inference must be marked as `来源: AI 推断` and confirmed with user first)
- Put decisions in `context.md` — `theme-guard` only scans `decisions.md`
