# Lanting (Folio) · Product Brief v4.0 (DSH-native edition)

> **A material-generation engine that lives inside DSH** — 15 native tools · session-protocol automation · swap the methodology, not the engine
> v4.0 · 2026-08-16 · Companion to the Technical Whitepaper v4.0

## 1. Summary

**One command installs 15 native tools. Session discipline becomes mechanical.**

Folio is a material-generation engine for consultants. It breaks the long-running job of "writing proposals, building decks, quoting, and remembering every client" into five stages; everything mechanical runs as deterministic code, and you only make judgments and confirmations.

| Metric | Value |
|---|---|
| Native tools | 15 (9 memory-side + 6 quality-side) |
| Keys to start | 0 (image reading and web search are covered by DSH natively) |
| Session close | Event-driven (auto-save on session disposal) |

Three selling points:

- **DSH-native fit**: tools, guard, mode and events all use official extension points — no kernel forks
- **Swappable methodology**: Folio Packs change the industry by swapping the methodology pack; third parties only write YAML and a handbook
- **Extreme specialization**: 20 pages of material in, four formats out with quality gates, every deliverable passing 5 mechanical checks

## 2. Why DSH

**Three things GUI tools cannot change, DSH can.**

| Pain | Impact | Folio's answer |
|---|---|---|
| Prompts given to the AI cannot be changed | Hard-coded in Codex-style tools | Lanting mode is a version-controlled configuration: people, workflows and industries can be swapped independently |
| Tools are command-line black boxes | Parameters guessed, errors read from logs | 15 commands become schema-validated native tool cards; wrong input is blocked and explained |
| Session discipline depends on AI memory | Forgets to save, forgets to audit | New sessions auto-remind the entry protocol; session close auto-saves the client profile |
| Two memories drift apart | Host logs and client files disconnected | Client name is extracted from tool calls; auto-filed into the profile on session close |

## 3. Five-layer architecture

**The kernel stays untouched; the DSH layer gets thicker.** The L0 kernel remains platform-agnostic (works in Trae, Kimi, terminals); L1–L4 are DSH-native plugin layers built entirely on official extension points.

| Layer | Contents |
|---|---|
| L4 Methodology · Folio Packs | Skills as methodology · light/standard/deep tiers · third parties write only YAML |
| L3 Events · Session protocol | Auto reminder on new session · auto save on close · automatic client-name extraction |
| L2 Tools · 15 native tools | 9 memory-side · 6 quality-side · schema validation + structured returns |
| L1 Mode · Lanting preset | Custom persona · five-stage SOP injection · standard blueprint (Windows-compatible) |
| L0 Kernel · 63 commands | Deterministic rendering · quality-gate chain · platform-agnostic |

## 4. A real collaboration in 8 steps

**Material in, proposal out — mechanically guarded at every step.**

1. **Entry protocol** — new session auto-reminder, level detection and recall
2. **Material intake** — client profile, chunking, dual-path indexing
3. **Asking before assuming** — asks when unsure, quotes the source text
4. **Skeleton first** — spec gate blocks generation before confirmation
5. **Generate HTML** — PPT engineering project generated from the same source
6. **Mechanical QA** — format, coverage, independent review
7. **You approve, then PPT** — native shapes, client-editable
8. **Auto archive** — session close auto-saves

## 5. Three ways to use it, compared

| Scenario | DSH-native (v4) | CLI add-on (v3) | Other GUI |
|---|---|---|---|
| Check client status | `folio_status` tool card | type commands in pwsh | AI browses files |
| Pre-generation confirmation | spec gate + tool hints | spec gate relies on AI memory | no mechanism |
| Session close | event-driven auto-save | AI must remember | no mechanism |
| Change AI prompts | preset config file | edit instruction files | cannot change |
| Block bad operations | guard plugin blocks mechanically | relies on discipline | no mechanism |

## 6. Capability list

| Layer | Item | What it does |
|---|---|---|
| Mode | Lanting preset | persona + five-stage SOP, standard blueprint (Windows PTY compatible) |
| Tools · Memory | `folio_recall` / `folio_read` / `folio_graph_query` and 6 more | status, recall, reading files, graph queries |
| Tools · Memory | `folio_session_start` / `folio_save` / `folio_load` / `folio_pending` | entry protocol, save, load, to-dos |
| Tools · Quality | `folio_verify` / `folio_review` / `folio_cite_audit` | mechanical gates, independent review, citation audit |
| Tools · Quality | `folio_audit` / `folio_theme_verify` / `folio_spec_diff` | system audit, theme coverage, spec comparison |
| Events | folio-events plugin | entry reminder, client-name extraction, auto-save on close |
| Guard | `@nyantused/folio-dsh-tools/guard` (formerly presales-guard, merged 2026-08-16) | blocks direct writes, non-CLI Python calls and shell direct writes |
| Kernel | 63 CLI commands | deterministic rendering and quality gates, platform-agnostic |

## 7. Roadmap

- **v1.0 released** (2026-08-15): skills + guard + install script
- **P1 landed** (2026-08-15): 15 tools + event plugin
- **v1.0.2 released** (2026-08-16): CI pipeline, contributor-friendly infrastructure, bilingual demo outputs
- **v1.2 planned**: Lanting mode v2 + graph projection
- **v1.3 planned**: sidebar panel + Packs manager

## 8. Getting started

**Prerequisites**: Windows 10/11, PowerShell, Python ≥ 3.10, Git and network access to PyPI. Node.js is not required; PowerPoint is optional (only `--shots` needs it). API keys are optional — zero keys is a supported L0 setup.

1. **Install**: run `setup/install.ps1` (kernel) → `setup/install-folio-plugins.ps1 -Install` (plugin layer) → restart dsh web
2. **Use**: a new session auto-injects the entry protocol reminder; just ask "which folio tools do I have"
3. **Swap**: install the Folio Pack for your industry; change the SOP section of the preset for your way of working
