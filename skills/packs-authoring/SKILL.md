---
name: packs-authoring
version: "1.0"
description: 要创作或发布方法论包时调用。Use when publishing a domain pack for Folio.
---

# Packs Authoring: Folio Pack Creation Guide

Folio methodologies are swappable, composable packs. This skill teaches you how to create a methodology pack (Folio Pack) from scratch — no coding required, only the ability to describe your methodology.

**One-liner**: A methodology pack = outline (what sections to split materials into) × constraints (what cannot be written) × samples (what correct output looks like).

## When to Use

- User says "I want to make a marketing methodology pack" / "switch to investment analysis" / "publish a methodology pack";
- You want to distill your own consulting framework into a reusable asset.

## Pack Structure (v0.1 Form; Contract v0.2 Frozen)

```
my-pack/
├── domain-pack.yml      # 包声明（manifest，v0.2 起机械校验）
├── outlines/            # 场景大纲（每个场景一个 outline.yml）
│   └── 整体方案/outline.yml
├── skills/              # 本包专属的方法论 skill（可选）
└── samples/             # 1-2 份样例 spec（"长什么样算对"）
```

## Creation Workflow (Scaffolding, One Q&A at a Time)

Collect information in order; write each item into the pack as soon as it is answered:

1. **Pack name and scenario**: What scenario does this pack serve? (e.g. "marketing plan") → create directory `my-pack/outlines/市场营销方案/`
2. **Section skeleton**: What sections does a standard plan consist of? (current state → goals → strategy → plan → budget?) For each section, answer three questions:
   - What problem does this section solve?
   - What facts should be extracted from client materials?
   - What content must **not** appear?
3. **Outline file**: Follow the format of existing outline.yml files under `_knowledge/templates/outlines/` (scene/structure/prompt trio).
4. **Constraint list**: This domain's ironclad rules (banned words, must-cover topics, gate parameters) — per `docs/产品定位与三卖点` §5 boundary rule 2: **packs must carry gate parameters**.
5. **Samples**: Run spec-gen on public case materials and put the outputs in `samples/`.
6. **Validation checklist** (self-check, manual in v0.1):
   - [ ] `outline.yml` can be read by outline-to-spec (`python _cli.py outline-list` shows your scenario)
   - [ ] Run sample materials through spec → html-build → output is viewable
   - [ ] No real client data in the pack (desensitization check)
   - [ ] Copy passes de-ai-style checks (banned words/evidence boundaries)

## Publishing

- Standalone GitHub repo (recommended) or submit under the Folio repo's `skills/`;
- In the README state clearly: what problem it solves, who it is for, how to install (copy outline directory + declaration);
- Submit to the awesome list for inclusion.

## Why This Design

- **Low barrier**: pack = data files (YAML + samples), no code — modeled on anthropics/skills' template-skill and the DSH community dsh-plugin-development meta-skill pattern;
- **Verifiable**: `domain-pack validate` (v0.2) will mechanically validate pack structure; until then use the checklist above as the manual fallback;
- **Composable**: packs combine via outlines + constraints; mechanisms go into the kernel, content into packs (boundary decision rule 3).
