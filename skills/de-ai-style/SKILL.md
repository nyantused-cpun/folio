---
name: de-ai-style
version: "1.1"
description: 生成或改写客户可见文案时调用。Use when generating or rewriting client-facing copy.
---

# De-AI Style

> Goal: produce copy that reads like a consultant wrote it, not like a model generated it.
> The single source of the word lists is `_paths.py` (`BANNED_WORDS` / `BANNED_PHRASES`); this file describes the process and judgment.

## When to Invoke

**Invoke**: when writing/generating/revising client-facing copy such as proposals, HTML, PPT, quotes, or reports; when reworking style issues found in review.
**Do not invoke**: engineering code, internal analysis, or process-oriented conversation with the user.

## Mandatory Chain (Already Exists; Don't Rebuild)

| Timing | Mechanism | Enforcement |
|---|---|---|
| Before generation | `_cli_guards` → `_style_guard.pre_check()`: returns antipattern list and requires reading `_knowledge/me/style_samples/` first | Blocks generation on failure |
| After generation | `_review.py` independent review dimension 3 "De-AI Style": local banned-word scan + LLM style judgment | FAIL sends it back for rework |
| Any time, manual | `python _cli.py style-check <文件>` | Advisory |

## Banned Words and Banned Patterns

- **Banned words (8)**: 赋能 / 抓手 / 闭环 / 生态 / 打通 / 全方位 / 一站式 / 卓越
- **Banned patterns (4)**: 综上所述 / 总而言之 / 不难看出 / 可以说
- **Dynamic word list**: `_knowledge/snippets/antipattern/*.md` — one word per line, auto-loaded by `_style_guard`; **add words without changing code**.

## `_style_guard` Pattern Detection (Regex, Checkable via style-check)

| Pattern | Signature | Fix |
|---|---|---|
| Triple parallelism | 不仅…更…还… | Short sentences; one info point per sentence |
| Jargon | 命中禁用词库 | Use concrete verbs ("缩短周期" instead of "提升效率") |
| Summary sentence | 综上所述/由此可见/总的来说 | Delete it; PPT doesn't need it |
| Flowery adjectives | 领先的/世界级的/顶级的/无与伦比的 | Delete adjectives; give facts |
| Symmetrical sentence | 既要…又要… | Pick one focus |
| Over-structuring | 首先/其次/再次/第一第二 | Transition naturally; don't force numbering |
| Symmetrical skeleton | 不是…而是/不在于…而在于/既是…也是…更是/与其说…不如说 | State the conclusion directly; don't set up a strawman or force triple structure |
| Fake reveal | 看似/表面…本质/背后/其实 | State facts directly; don't create an "appearance vs essence" reveal |
| Era opener | 随着…的快速发展/在当今…时代 | Cut the opener; get to the point |
| Essence claim | 真正…的是/本质上/核心在于/底层逻辑 | Give the subject and facts directly; don't elevate into a summary |

## Language Feel (More Important Than Banned Words)

The word lists only prevent the lowest-level failures; the real AI flavor lives in structure and habits. **Read `_knowledge/me/style_samples/` before writing**:

- Short sentences, conclusion first, one info point per sentence
- Use verbs instead of adjectives; always pair numbers with units
- Don't stack words, don't inflate significance, don't blur attribution ("随着…的快速发展", "在当今数字化时代")
- Remove vendor names: replacement rules are in `_knowledge/me/profile.md` (金蝶→ERP、泛微→OA/BPM 平台……); vendor names appear only in competitive comparisons

### Language-Feel Diagnosis (Six Questions, Self-Check Before Writing)

1. Too complete — every angle is covered, but no real situation feels alive
2. Too smooth — transitions are seamless, conflict disappears, rhythm is uniform
3. Too abstract — nouns like value/capability/insight replace visible facts
4. Too objective — nobody says who saw what, who made the decision, or what the plan's judgment is
5. Too good at summarizing — ends by elevating upward instead of landing on actions/consequences/unresolved questions
6. Flat after cleanup — the AI flavor is gone, but no concrete sentence is memorable

### Prevent Over-Fixing (Know When to Stop)

- Don't ban punctuation globally: keep colons/dashes/lists/numbering when useful (especially HTML/PPT proposals)
- Don't force internet slang, memes, or exaggerated colloquialisms
- Don't fabricate scenes: never write facts, numbers, cases, dates, or quotes the client didn't provide
- Don't rewrite every sentence: keep clear sentences as-is
- Don't delete professional terms the audience needs: define them, or tie them to a real case
- Don't turn the proposal into loose chatter: proposals can be structured and still human
- Don't replace AI flavor with chicken-soup flavor: "more literary" must also mean "more precise"

### First Distinguish Content Debt from Language Debt

- Content debt: missing facts, no real cases, no judgment, unclear audience, unsupported judgment → fill in content first
- Language debt: AI clichés, overly neat structure, too many connectives, elevating endings → then fix language

Fixing only language debt makes empty words emptier; the most common "AI flavor" in proposals is actually content debt.

### Delete First, Then Rewrite (Many AI-Flavored Sentences Carry No Information)

When you meet an empty sentence, delete it first rather than forcing a rewrite. "这不仅提升了体验，也为后续发展奠定了基础" — without concrete facts, delete the whole sentence. Then ask four questions:

1. Name-swap test: if you swap in any competitor's proposal name, does this sentence still hold? If yes = no information; add mechanism/number/tradeoff.
2. Contradiction test: would anyone argue the opposite? "我们重视质量" nobody opposes = empty; "上线后工单下降 40%" invites challenge.
3. Then what: push the fact to a consequence the reader can act on. "系统支持数据对接" → "财务不用再手工导表".
4. State boundaries: proposals must state limits, assumptions, and what is not covered. A page full of "全面提升" sounds like sales; "本期不覆盖移动端" sounds like a consultant.

### Nominalized Verb Shells (Soft Guidance, Not in the Word List)

"进行优化/实现增长/做出选择/提供保障/给予支持/采取措施/加以改进" — these "empty verb + abstract noun" shells should return to concrete actions: who, what changed to what, and what result.
Example: "我们围绕用户反馈开展产品体验优化" → "本周先改两个问题：登录慢，导出表格易失败".
But "提供数据安全保障" and "实现数据共享" are normal writing; don't mechanically break them.

### Report Page Titles Should State a Judgment, Not a Section Name

"客户续费慢" instead of "客户成功体系待升级"; "结构化输出让结果可审计" instead of "方案价值". One main judgment per page, supported by bullet points.

## Evidence Boundaries and Claim Strength (More Important Than the Word Lists)

The easiest AI flavor in proposals is not word choice; it's writing plans as if they were already verified. Before writing, ask about every conclusion: does it stay within what the evidence can prove? If not, downgrade the wording.

Evidence → strongest supported conclusion:
- Pilot/internal-test data → "早期试用反馈积极"; cannot write "全面验证/市场认可"
- Correlation/co-occurrence → cannot write causation ("上线后工单下降" ≠ "系统直接导致下降")
- Product capability plan → "支持/可实现"; cannot write "已落地/已达标"
- Vendor claim/whitepaper → "厂商宣称"; cannot write "已被证实"
- Theory/architecture design → "设计上可支撑"; cannot write "性能已验证" (no actual measurement)

High-risk claim words (use only with actual measurement/source; otherwise delete or downgrade):
验证、证实、表明、证明、必将、唯一、最佳、绝对、彻底、完美、成功验证、充分证明、强烈需求、市场认可、真实需求

Safer phrasings (downgrade without losing accuracy):
- "这说明…" → only when the evidence directly measures that conclusion
- "至少可以说明…" / "从现有材料看…"
- "厂商宣称…" / "该数据支持早期兴趣，但不能证明…"

## Fact-Skeleton Discipline (When Polishing a Draft)

When the user gives a draft for polishing, first extract the "fact skeleton": list the client pain points, numbers, commitments, and conclusions as a few lines. During rewriting, **do not add, remove, or change** these facts; only change wording. After finishing, check each line against the skeleton: was anything tampered with, lost, or added? When style perfection conflicts with factual discipline, factual discipline wins.

## Self-Review During Generation (Final Anti-AI Pass)

After the first revision, look back only at the sentences you changed and check each:
1. Did I add fake profound structures (不是…而是…/真正…的是)?
2. Did I inflate ordinary facts into significance (标志着/体现了/充分证明)?
3. Did I add aphorisms, parallelism, or pretty metaphors?
4. Did I add numbers/scenarios/examples without a source?
5. Did I delete distinctive phrasing from the client's original text?

Finally cold-read the whole text and ask: "Where is the reader most likely to notice this was written by AI?" Then revise targeted. The second scan only fixes problems you introduced; don't rewrite unchanged text along the way.

## Discipline for Expanding the Word List

- To add a word: just add a `.md` file under `_knowledge/snippets/antipattern/`; it takes effect immediately
- Existing category files: `jargon.md` (internet/marketing jargon) / `empty_modifiers.md` (vague adjectives) / `vague_attribution.md` (vague attribution and era openers) / `filler_transitions.md` (filler connectives) / `significance_inflation.md` (inflated symbolism and elevation) / `abstract_subject.md` (abstract-subject proxies) / `meta_narrative.md` (meta-narrative and self-justifying) / `evidence_overclaim.md` (evidence overclaiming)
- User explicit exemptions: 无缝、落地 (normal words in context); 生态 (EA terminology context, e.g. 「中心生态拓扑图」, architecture-diagram-builder scenario)

### Three-Tier Standard for Adding Words (Aligned with human-copywrite edit bar + ai-write-flow P0/P1/P2)

- **Must delete** (goes into mechanical word list/regex, hit on a single use): chat residue, meta-narrative, evidence overclaiming, abstract subject — almost never used in normal expression, no protected exceptions.
- **Change only in clusters** (soft guidance, only if ≥2 occurrences or high density): empty good words (高效/强大/完善), significance inflation (标志着/体现) — a single use may be normal; clustering reveals AI flavor.
- **Context judgment** (not in the word list; human decides during AI editing): dashes, bold, lists, nominalized verbs (进行/提供/给予 + abstract noun), first person — many normal uses; mechanical blocking would cause false positives.

Only add to the word list when all three conditions are met: high frequency (repeated in proposals) + low false-positive (normal consultant expression almost never uses it) + no protected exceptions (no context such as "quotes/legal phrasing" that must be kept). Everything else stays soft guidance.
**False-positive lesson**: don't add everyday high-frequency words like 深度/全面/有效 (P2 once had false-positive floods and removed them); don't collect "先…再…" — it is normal in SOP scenarios.
