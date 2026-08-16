---
name: consulting-grill
version: "1.0"
description: 带证据召回的咨询追问。Use when stress-testing client plans or confirming requirement understanding.
---

# consulting-grill: Evidence-Recalling Consulting Grill

## Core Idea

Ordinary grilling skills can only reason from what the user says. consulting-grill actively recalls the client's raw materials (meeting notes, technical requirements, bid/tender documents, etc.) during the grill and uses snippet citations to correct or supplement the user's understanding.

**One-liner**: Neither you nor I decide; the raw material decides.

## Startup Prerequisites

1. At session start, run `python _cli.py session-start "<用户输入>" --client <客户名>` to load context
2. Run `python _cli.py theme-guard <客户>` to get the permanent rules (HEAD injection)
3. Put the permanent rules at the start of answers and check them throughout the grill

## Grill Rhythm (Keep Original Grilling Rhythm)

Keep interviewing the user about every aspect of the plan until we reach shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one. Attach your recommended answer to every question.

**Ask one question at a time** and wait for the user's feedback before continuing. Asking multiple questions at once makes people lose direction.

Do not execute the plan until the user confirms we have reached shared understanding.

## Core Difference from Normal Grilling: Recall Before Asking

### When to Trigger Recall

When the user's statement touches any of the following, **recall first, then continue grilling**:

1. **Client needs/metrics** (e.g. "client needs 5000 concurrent users") -> recall technical requirements/meeting notes to verify
2. **Solution direction/focus** (e.g. "solution focuses on collaboration") -> recall requirements document to verify
3. **Constraints** (e.g. "ignore data isolation") -> recall raw materials to check for omissions
4. **Technology choices** (e.g. "use microservices architecture") -> recall technical requirements to check for explicit direction

### How to Recall

```bash
python _cli.py recall "<关键词>" --client <客户名>
```

- Get the raw text from the `snippet` field of recall results
- If the snippet is insufficient, use `python _cli.py read <path#anchor>` to read the full passage
- 3-5 results are enough; no need for the full set

### Three Behaviors After Recall

| Recall result | Behavior | Example |
|---------|------|------|
| Matches the user's statement | Confirm, then continue to the next level | "Raw material #p12 confirms 3000 concurrent users; let's continue with the scaling plan" |
| Conflicts with the user's statement | **Cite the snippet and correct actively** | "Wait, 蓝海集团_技术要求_v2.docx#p12 says 3000 concurrent users, not 5000 — did you misremember?" |
| No results | Ask the user to confirm the source | "I found no support for '5000 concurrent users' in the raw materials. Where did that number come from?" |

### Theme-Guard Linkage

During the grill, at the end of each branch check:
- Does the current discussion direction cover the permanent rules?
- Was any permanent rule missed?

If something is missing, proactively remind: "We covered collaboration, but the client rule that data isolation is a hard requirement has not been covered yet. Shall we look at it now?"

## Grill Structure (Design Tree)

Grill layer by layer in this order, recalling first at each layer:

1. **Requirement understanding layer**: What problem is the client solving? What is the core pain? (recall meeting notes to verify)
2. **Solution direction layer**: How do we plan to solve it? What is the big direction? (recall technical requirements to verify)
3. **Capability scope layer**: Which modules exactly? Where are the boundaries? (recall requirements document to verify)
4. **Constraint check layer**: Are all permanent rules covered? Any omissions? (theme-guard check)
5. **Delivery confirmation layer**: What are the deliverables? Delivery order? (confirm shared understanding)

## Output Format

Whenever you recall during a question, use this format:

```
[证据] 来源：蓝海集团_技术要求_v2.docx#p12
内容：...原始文本片段...

基于以上证据，我的问题是：
xxx？
（推荐答案：yyy）
```

If no recall was triggered (pure logic question), ask directly.

## Relationship with CLI

- **This skill is for the discussion phase**: use it when the AI and user discuss solution direction and requirement understanding
- **Generation still goes through CLI**: after reaching consensus, follow `python _cli.py new <客户>` -> spec -> html-build
- **Recall results are not auto-injected into generation**: recalls during discussion are temporary; generation-time evidence injection is separate (injected at the spec stage; see decisions.md)

## Notes

- Recall results may be incomplete (BM25 tokenization and chunk granularity affect this); do not rely on them 100%. No recall result does not mean the client never said it; ask the user to confirm
- Snippet length is limited (200 chars); use the `read` command to read the full passage for key evidence
- Don't recall for its own sake; pure logic/architecture choice questions do not need raw material recall
- Every recall must be followed by a text reply; never stay silent
