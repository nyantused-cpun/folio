# Lanting (Folio) · Product Brief v6.0

> **A material-generation engine that lives inside your AI host** — 15 native tools · session-protocol automation · swap the methodology, not the engine
> v6.0 · 2026-09-09 · Corresponds to release **v2.0.0** (2026-09-08)
> Companion to the [Technical Whitepaper v6.0](兰亭_技术白皮书_v6.0.md) / [README](../README.md) / [Migration Guide v2.0](MIGRATION_v2.0.md)

## 1. Summary

**One command installs 15 native tools. Session discipline becomes mechanical.**

Folio is a material-generation engine for consultants. It breaks the long-running job of "writing proposals, building decks, quoting, and remembering every client" into five stages; everything mechanical runs as deterministic code, and you only make judgments and confirmations.

| Metric | Value |
|---|---|
| Shape | Host-agnostic CLI kernel + optional DSH enhancement layer |
| CLI commands | 87 (release-face count; 11 on the main chain) |
| DSH native tools | 15 `folio_*` tools (17 on the dev line, shipping next release) |
| Search tools | 6 `search_*` tools |
| Graphics / elements / themes | 37 diagram types / 39 elements / 7 themes |
| Entry cost | Zero API keys (L0); one embedding key unlocks semantic recall (L1) |
| Platform | Windows 10/11 + PowerShell + Python ≥ 3.10; **Node.js not required** |

## 2. The Problem It Solves

A consultant's work is long-horizon: from client materials to a deliverable, you retrieve history, align on facts, produce multiple versions, and remember each client's hard constraints. With AI, the biggest risk is not "not smart enough" — it is that **the model invents facts, forgets early constraints, and mistakes plausible for true**.

Folio's answer: **mechanize everything that can be mechanized.**

- Rendering, retrieval, parsing, indexing, gating, and auditing all run as deterministic code.
- The model only handles understanding, judgment, and language.
- Every critical step has a mechanical gate. If something is wrong, it is blocked — not merely "reminded" by a prompt.

## 3. Five-Stage Value Chain

| Stage | What it does |
|---|---|
| **Intake** | Client onboarding, inbox archiving, tender/PDF/PPT parsing, chunking, dual-path indexing |
| **Chronicle** | Decision records, client profiles, worldbook, semantic recall (pure BM25 fallback by default) |
| **Craft** | Skill routing, scenario outlines, theme guard, de-AI style; methodology is swappable |
| **Press** | spec protocol → HTML / PPTX / DOCX / quote from one source of truth |
| **Proof** | confirmed gate, verify, independent review, citation audit, aesthetic/narrative observation |

## 4. Three Selling Points

### 1. Machines do the mechanical; the model does the judgment

- **spec gate**: an unconfirmed spec cannot be rendered (`confirmed: true` + hash sidecar).
- **Theme guard**: client hard constraints live in `decisions.md` and are injected into the HEAD before generation — they survive long conversations.
- **Independent review**: a separate LLM session scores the output; fail-closed (non-zero exit on failure).
- **Delivery gate**: a crafted page that fails review cannot be shipped to PPT.

### 2. Swap the methodology, not the engine

Methodology is packaged as replaceable **Folio Packs** (YAML + SKILL.md). Marketing, investment analysis, strategy consulting — swap a pack, not the engine. `skills/packs-authoring` walks you through authoring a pack, no coding required.

### 3. Zero keys to start, unlock as you go

- **L0**: no keys needed for the full pipeline (HTML / PPT / DOCX / quote).
- **L1**: one embedding key unlocks semantic recall.
- **L2**: vision/search keys unlock visual and web capabilities in standalone CLI use.
- Under DSH, the host's native capabilities cover vision, search, and independent review (`LLM_MODE=host`).

## 5. Installation

```powershell
git clone https://github.com/nyantused-cpun/folio.git folio
cd folio
.\setup\install.ps1                  # venv + deps + config + self-check
# Optional but recommended — DSH plugin layer:
.\setup\install-folio-plugins.ps1 -Install   # 15 tools + event plugin + guard
# Restart dsh web, then just say "build me a proposal for XX" in a new session
```

## 6. Delivery Pipeline

```
client materials → intake → requirement analysis → spec draft → user confirmation
→ HTML first → user confirmation → PPT / DOCX / quote
```

**HTML first** is a hard discipline: get the content right in the browser before converting. The `deliver` orchestrator pauses at the confirmation gate.

## 7. Quality and Security

| Area | How |
|---|---|
| Content review | 5-dimension scoring + adversarial / parallel / incremental / screenshot modes, fail-closed |
| Mechanical checks | verify (structure / density / layout / theme / citations) + audit (14 modes) + size ratchet |
| Regression baseline | 37 gold render baselines, four-dimension signatures |
| Read boundary | read commands are locked to the workspace; out-of-tree access needs an explicit flag |
| Deserialization | unsigned pickles are rejected |
| Office documents | Word COM macro execution is disabled |
| Desensitization | 17-word client-name gate + binary office-document parsing + hash pins |

## 8. DSH Compatibility

| Item | Status |
|---|---|
| Release anchor | DSH **0.1.0-rc.8** (`verifiedAgainst` + peer dependency) |
| Dev line | **0.1.2-rc.1** compatibility layer ready (`folio-events` three-level event-read fallback); ships next release |
| Without DSH | The CLI kernel still works (L0); you just lose the tool face / guard / session protocol |

## 9. Known Limitations (Honestly)

- **Windows-first**: macOS / Linux install scripts are pending (PRs welcome).
- **Excel formatted tables and formulas**: not yet supported (PRs welcome).
- **`--shots` screenshot inspection**: requires local PowerPoint; HTML / DOCX / quote are unaffected.
- **Release-face numbers**: docs say 90 modules / 87 commands / 191 test files; the repo measures 109 py / 91 add_parser / 192 test files — to be unified next release.
- **`context.md` body is still an AI summary**: write-side evidence gating is in place; the full fix is an "event excerpt + AI summary" dual track.

## 10. Roadmap

- **v2.1**: sync the DSH 0.1.2-rc.1 compatibility layer; ship `folio_confirm` / `folio_reflect`; unify release-face numbers.
- **Community**: Excel formatting/formulas; Linux/macOS ports.
- **Product**: methodology-pack contract (`domain-pack.yml`); cross-client knowledge transfer.

---

> Folio = a folio: bind the materials a client throws at you into a deliverable you can hand over.
