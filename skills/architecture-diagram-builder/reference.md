# Architecture Diagram Builder - Reference

Companion detailed methodology for [SKILL.md](./SKILL.md). SKILL.md is the entry point (quick lookup); this file is the detail (read on demand).

---

## methodology: Methodology Foundations

> Shared base for four-domain design: viewpoints, layering skeleton, numbering rules. See each domain section for details.

### Two Viewpoints and the Translation Mechanism

- **APQC is the process viewpoint** (landing object = people): focuses on how business flows. Even without information systems, people can complete work with Excel and calculators.
- **4A is the system viewpoint** (landing object = systems): focuses on how systems replace human work.
- **The APQC-to-4A translation mechanism is "automation"**: work that can replace people → functional item; work that cannot → excluded. Automation has two dimensions—automation (replaces human execution, e.g. automatic balance calculation) + intelligence (replaces human judgment, e.g. automatic risk-control approval).
- **Key principle**: process levels are decided by organizational division of labor, not by the performer—even if AI fully replaces human collaboration, the activity remains L4 in the process.

(Source: [discussions/2026-07-07 APQC to 4A mapping deep dive](./discussions/2026-07-07_APQC到4A映射深度讨论.md))

### Four-Domain Layering Skeleton

| Domain | Layers | Details section |
|---|---|---|
| BA Business Architecture | APQC L1 Category → L2 Group → L3 Process → L4 Activity → L5 Task (APQC officially provides only through L3; L4/L5 are filled by the enterprise) | #BA |
| DA Data Architecture | L1 Data Domain → L2 Subject → L3 Conceptual Entity → L4 Logical Entity → L5 Attribute | #DA |
| AA Application Architecture | AD → AG → APP → ABB → Functional Item → Functional Sub-Item (6 layers) | #AA |
| TA Technology Architecture | Three horizontals, two verticals + deployment nodes | #TA |

The full APQC ↔ 4A 6-layer correspondence table (organizational-division viewpoint vs system viewpoint) is in #function-identification.

### APQC L1 Reference

Operating processes (direct value creation): 1.0 Vision & Strategy / 2.0 Products & Services Development / 3.0 Marketing & Sales / 4.0 Products & Services Delivery / 5.0 Customer Service

Management and support processes (support operations): 6.0 Human Capital / 7.0 Information Technology / 8.0 Financial Resources / 9.0 Assets / 10.0 Risk & Compliance / 11.0 External Relationships / 12.0 Business Capabilities

Usage: do not invent categories—map directly to APQC L1, then streamline by enterprise size and industry (merge or omit). Per-category explanations, streamlining examples (100-person chemical company vs large-group auto-parts), and client-facing wording are in `_knowledge/refs/apqc_pcf.md`.

### L Numbering and Step Numbering Rules

- **Level numbering**: L1-L5 indicate layering depth, used for cross-domain alignment (APQC L4 = 4A ABB, APQC L5 = 4A functional item).
- **Step numbering**: design steps use 1.0/2.0/3.0; sub-steps use 1.1/1.2 second-level nesting (checklist structure items are mandatory checks).
- Every design step must have an "Input / Task / Output" triplet; at the end of each section run the three-property validation (completeness / reasonableness / integration).

---

## execution-flow: Execution Flow and Locking Mechanism

### Three Phases and Execution Order

Three phases: ① write documents (Step 1-7) → ② merge check (Step 8-9) → ③ draw diagrams (Step 10). Do not generate any HTML before phase 1 completes; do not enter phase 3 if phase 2 fails; if phase 3 finds document issues, return to phase 1 to fix—do not edit directly in HTML.

Document order: requirements identification → BA → DA → AA → TA → governance evolution → product mapping. **Parallel work is forbidden.** Reason: BA is the input; DA/AA depend on BA's business objects and process steps; TA depends on AA's APP list; parallel generation means each domain invents its own view, so cross-domain mismatches are inevitable.

### Locking Mechanism (🔒)

After each step, output a **lock list**; user confirmation is required before the next step. Lock list = the key conclusions produced by this step and the comparison baseline for the next step's cross-domain check.

Format (one table per domain):

| Field | Content |
|---|---|
| Step | e.g. Step 2 BA |
| Deliverable | Document/list name delivered by this step |
| Key items | Atomic items for the next step to compare—BA: L1 domain list + process step list + business object list; DA: conceptual entity list; AA: APP/ABB/functional item list; TA: deployment node list |
| Status | Pending confirmation / Confirmed (with confirmation date) |

Rules:

- Enter the next step only when status is "Confirmed"; if the user objects, return to modify and re-lock.
- Scope is the current session only; cross-session continuation requires re-confirmation (prevents continuing from memory).
- If an error is found after locking, return to the corresponding step to fix, then chain re-check all subsequent steps.

### Incremental Cross-Domain Checks

Run the corresponding cross-domain check immediately after each lock; do not defer to the end:

- After DA lock: BA→DA (business object = conceptual entity, same name)
- After AA lock: BA→AA (process step has corresponding APP) + DA→AA (logical entity has corresponding functional item)
- After TA lock: AA→TA (every APP has a corresponding deployment node)

Check rules and failure handling see #cross-domain. Incremental checks verify "adjacent domains align"; phase-2 cross-domain total check verifies "global self-consistency" (transitive consistency, scope closure, gap discovery, terminology drift); the two do not duplicate.

---

## BA: Business Architecture Complete Design Steps

### Principles (3-5)

| ID | Principle | Meaning |
|---|---|---|
| OP-1 | Strategy-driven | Business architecture must be derived from enterprise strategy, not reverse-engineered from existing systems |
| OP-2 | Value-oriented | Every business capability must correspond to quantifiable business value |
| OP-3 | End-to-end | Processes must cover the complete chain from trigger to completion, not truncated |
| OP-4 | Clear objects | Business objects must have explicit definitions (who creates / who uses / who maintains) |
| OP-5 | Role separation | Decision roles / execution roles / supervision roles must be separated |

### Input

- Enterprise strategy documents (vision / objectives / critical success factors)
- Existing business process documents (AS-IS)
- Organization structure (departments / positions / responsibilities)
- Industry best practices (APQC / industry benchmarks)

### Design Steps

| Step | Task | Output |
|---|---|---|
| 1.0 | Value chain analysis | Value chain diagram (primary value streams + support activities) |
| 2.0 | Business capability identification | Business capability list (L1/L2/L3 layered) |
| 3.0 | Process architecture design | Process architecture diagram (L1 process groups / L2 processes / L3 activities) |
| 4.0 | Business object list | Business object table (name / definition / creator / user) |
| 5.0 | Role-responsibility matrix | RACI matrix (roles × process steps) |

### 1.0 Value Chain Analysis

**How**:
- Primary value streams: end-to-end chain from customer need to customer satisfaction (e.g. "order to cash")
- Support activities: HR / finance / IT / procurement, etc.
- Output: value chain diagram (landscape; primary value streams on top, support activities below)

**Checks**:
- [ ] Do primary value streams cover the full chain from trigger to completion?
- [ ] Does every support activity map to a link in the primary value stream?

### 2.0 Business Capability Identification

**How**:
- L1 capability: strategy-level capability (e.g. "procurement management", corresponding to APQC L1 Category)
- L2 capability: domain-level capability (e.g. "supplier management", corresponding to APQC L2 Group)
- L3 capability: activity-level capability (e.g. "supplier onboarding", corresponding to APQC L3 Process)

> **Terminology clarification**: an L3 capability is called an "activity-level capability" (it is a capability, not a process activity). Process-level terminology is in 3.0. Do not mix the word "activity" between the two.

**Checks**:
- [ ] Does every L1 capability have explicit business value?
- [ ] Does every L2/L3 belong to exactly one parent capability?

### 3.0 Process Architecture Design

**How**:
- L1 process groups: correspond to APQC L1 Category (see [APQC L1 reference](#apqc-l1-reference))
- L2 processes: correspond to APQC L2 Group
- L3 subprocesses: correspond to APQC L3 Process
- L4 activities: actually extracted from client materials (APQC does not provide L4)
- L5 tasks: actually extracted from client materials (APQC does not provide L5; task is the input to BA 5.1 task→service mapping)
- Output: process architecture diagram (tree or swimlane)

**Checks**:
- [ ] Does every process have explicit trigger and completion conditions?
- [ ] Are interfaces between processes clear (input/output)?

### 4.0 Business Object List

**How**:
- Extract business objects from every process step (e.g. "procurement request form")
- For each object record: name / definition / creator / user / maintainer
- Output: business object table

**Checks**:
- [ ] Does every business object have an explicit creator?
- [ ] Does every business object have an explicit user?

### 5.0 Role-Responsibility Matrix

**How**:
- X-axis: process steps (L3 activities)
- Y-axis: roles (positions)
- Cells: R (responsible) / A (accountable) / C (consulted) / I (informed)
- Output: RACI matrix

**Checks**:
- [ ] Does every process step have exactly one R (responsible)?
- [ ] Does every process step have exactly one A (accountable)?

### Validation (Three Properties · Design-Time Self-Check)

| Validation dimension | Check item | Typical criterion |
|---|---|---|
| Completeness | Does it cover all business processes? | All L1 capabilities have corresponding processes |
| Completeness | Is 5.1 process-service-document mapping diagram produced? | BA must produce this diagram (MANDATORY); BA is incomplete without it |
| Reasonableness | Is granularity reasonable? | L3 activities can be assigned to specific positions |
| Integration | Interface with data/application architecture | Business objects have corresponding conceptual entities in DA |

### 5.1 BA→AA Mapping: Task to System Service (MANDATORY · Core Bridge from Business to IT)

**Positioning**: This is the mapping methodology from business architecture to application architecture. An enterprise management system is essentially the digitalization of business processes. After a business process is decomposed into minimal tasks, each task must be judged "does it need IT support and what IT support", producing the application-service candidate list as AA input. **Complete the 5.1 derivation first, then draw the 5.2 mapping diagram.**

**Generic chain**:

```
业务流（BA 3.0 产出）
  ↓ 拆到最小任务
task 级任务清单
  ↓ 逐个 task 判断「执行方式」
IT 系统支持服务候选清单（AA 7.0 应用服务设计的输入）
  ↓ 聚合成模块 + 判粒度
IT 系统架构（AA 6 层 + TA）
```

**Core rule: every task must determine its execution mode**

| Execution mode | Judgment criteria | Maps to | Example |
|---|---|---|---|
| **System automatic** | No human intervention; system executes by rules | → Application service (standalone function) | Budget-occupancy validation, voucher push, approval flow |
| **Manual operation** | Pure human decision; system does not intervene | → Workflow node (not a standalone service) | Approval decision, investment judgment, budget adjustment |
| **Human-machine collaboration** | Human fills form/confirms; system processes | → Form function (part of an application service) | Fill budget form, enter invoice, confirm reconciliation |

**Forbidden**: treat a "manual operation" task as an application service. For example, "approval decision" is a human action, not a system service; the system only provides an "approval flow" service to support it.

**Mapping steps**:

1. **List tasks**: continue decomposing L3 activities from BA 3.0 to task level (each task is a minimal executable action)
2. **Determine execution mode**: mark each task as "system automatic / manual / human-machine collaboration"
3. **Extract service candidates**: system-automatic + human-machine collaboration tasks → extract as application-service candidates
4. **Cluster into modules**: group related services into APP candidates (granularity judgment see [#function-identification](#function-identification))
5. **Output to AA**: the application-service candidate list is the input to AA 1.0 AD/AG/APP initial classification

**Example** (a group's budget expense control):

| task (from BA 3.0) | Execution mode | Maps to | Notes |
|---|---|---|---|
| Prepare investment budget | Human-machine collaboration | Budget preparation service (form function) | Human fills equipment details; system calculates amount |
| Budget occupancy validation | System automatic | Budget occupancy service (application service) | System validates automatically by rules |
| Approval decision | Manual operation | Workflow node (not standalone service) | Human decides; system only routes |
| Push voucher to ERP | System automatic | Voucher push service (application service) | System pushes automatically |

**Checks**:
- [ ] Is every task marked with its execution mode?
- [ ] Are all system-automatic + human-machine collaboration tasks extracted as service candidates?
- [ ] Are manual-operation tasks avoided being treated as standalone application services?

### 5.2 Process-Service-Document Mapping Diagram (MANDATORY · BA Must Produce · Draw after 5.1)

**Positioning**: The bridging layer between BA→AA→DA. Based on ArchiMate's three-layer modeling language, it visualizes the mapping among business processes, application services, and data objects. This is a mandatory BA deliverable, **output after the 5.1 task→system service derivation**, verifying the mapping lands completely.

**Trigger**: Must be output after 5.1 derivation; no special user request needed.

**Input**:
- BA process architecture (L1 process groups / L2 processes / L3 activities)
- BA business object list
- AA application service list (SVC)

**Output**: three-layer mapping diagram (business process layer + application service layer + document flow layer) + colored connection relationships (HTML single page)

**ArchiMate three-layer definitions**:

| Layer | ArchiMate element type | What goes here | Color marker | Example |
|---|---|---|---|---|
| **Layer 1: Business process** | Behavior element (business process / business function / business event) | Actions actively initiated by business people | Blue = manual operation, orange = decision/approval, green = system automatic | QCA project initiation request, investment budget preparation, procurement request |
| **Layer 2: Application service** | Behavior element (application service / application function) | System capabilities inferred backward from process nodes | One color per service | QCA approval service, budget preparation service, budget occupancy service |
| **Layer 3: Document flow** | Passive structure element (business object / data object) | Business documents/data entities operated by services | — | QCA approval form, investment budget form, budget code, procurement request form |

**6-step drawing method**:

| Step | Task | Key points |
|---|---|---|
| 1 Split phases | Split 3-6 phases by business-state transitions | Split by "unknown → known → opportunity → order → operation", not by system |
| 2 Mark nodes | 3-5 dots per phase, arrows in sequence | Blue = manual operation, orange = decision/approval, green = system automatic |
| 3 Extract services | Infer system capabilities from nodes, abstract 5-8 services | Ask "what system capability supports this node?" |
| 4 List documents | List business/data objects operated by services | Ask "what documents does this service produce/update?" |
| 5 Connect colored lines | Three-layer connections: process → service → document | Process node ──triggers──→ application service ──operates──→ document object |
| 6 Mark exceptions | Exception/return flows with red dashed lines | e.g. budget-insufficient rejection, approval return |

**Key rules**:
- **Forbidden** to put system-automatic tasks (e.g. "budget occupancy validation", "voucher push") in the business process layer. They are application services, not business processes.
- The business process layer only contains actions actively initiated by business people (fill forms, submit requests) and approval decision nodes.
- The application service layer contains all system capabilities, including automatic validation, calculation, push, etc.
- The document flow layer contains produced business documents; connections go from services to documents, not from processes to documents.

**Layout parameters**: overall width 1500px, phase ≥ 260px, node 16px, arrow ≥ 32px, labels below nodes.

**Checks**:
- [ ] 3-6 phases, 3-5 nodes per phase
- [ ] 5-8 services, names no longer than 8 characters
- [ ] Number of documents consistent with BA business object list
- [ ] Node labels do not overlap (widen or reduce nodes)
- [ ] Line crossings ≤ 3 (adjust service order)
- [ ] Exception/return flows marked with red dashed lines
- [ ] Three layers strictly match ArchiMate element types (process = behavior element, service = behavior element, document = passive structure element)

**Note**: This diagram is a simplified BA+AA+DA; it does not replace the full four-architecture deliverable. After the client approves processes and services, supplement the complete BA/AA/DA.

### 5.3 Automation Improvement Analysis (Reverse View of 5.1 Mapping · Value Demonstration)

**Positioning**: This is the **reverse view** of BA 5.1 task→system service mapping. 5.1 looks forward at "which system functions do business processes need"; 5.3 looks backward at "how much manual work can system functions replace". It is not independent analysis—it is further refinement and value demonstration of the 5.1 mapping table.

**Default premise**: System functions inherently carry automation capabilities—e.g. the budget preparation function defaults to automatic budget aggregation, otherwise the system cannot run. 5.3 does not ask "can the system automate?" but "relative to the current manual baseline, how much can the system replace?"

**Analysis object**: BA 5.1 tasks marked "manual operation" and "human-machine collaboration" (system-automatic tasks are already automated and need no further analysis).

**How**:
1. **List current manual tasks**: filter "manual operation" and "human-machine collaboration" from 5.1's task list
2. **AI suggests automation solutions**: initial match against the common automation technology list
3. **Consultant adjusts**: consultant confirms or corrects AI suggestions based on product capability / technical solution
4. **Mark replacement degree**: full replacement / partial replacement (human review) / no replacement (requires human judgment)
5. **Output**: automation improvement list

**Common automation technology list** (AI initial match by table, consultant adjusts):

| Technology | Manual action it solves | Applicable tasks |
|---|---|---|
| OCR recognition | Manual entry of tickets/documents | Invoice entry, contract entry, expense form filling |
| Rule engine | Manual rule-based calculation/validation | Budget aggregation, expense validation, quota calculation |
| RPA | Manual cross-system transfer/entry | Voucher push, data sync, report aggregation |
| API integration | Manual cross-system data transfer | Data push between systems, status sync |
| Workflow engine | Manual approval routing | Approval flow, task assignment, reminders |
| Auto archiving | Manual sorting/archiving | Document archiving, voucher archiving |

**Automation improvement list template**:

| task | Current execution | AI-suggested automation solution | Consultant adjustment | Replacement degree | Hours saved (optional) |
|---|---|---|---|---|---|
| Invoice info entry | Manual upload + manual fill | OCR recognizes invoice fields | Consultant confirms product support | Partial (human review) | High |
| Budget statistics | Manual aggregation | Rule engine auto-aggregation | Consultant confirms calculation rules | Full | High |
| Approval decision | Manual decision | — | Cannot replace (requires human judgment) | None | — |
| Document archiving | Manual archiving | RPA auto-archiving | Consultant confirms RPA feasibility | Full | Medium |
| Budget occupancy validation | Manual quota check | Rule engine auto-validation | Consultant confirms validation rules | Full | High |

**Key rules**:
- Not all manual tasks can be automated—tasks requiring human brains such as approval decisions and investment judgment are marked "no replacement"
- Replacement degree has three tiers: full replacement / partial replacement (human review) / no replacement
- Consultant input is key—AI does initial match against the technology list; consultant confirms or corrects based on product capability
- System functions default to basic automation (e.g. budget preparation includes aggregation); 5.3 only analyzes "incremental automation value relative to the current baseline"

**Who consumes the output**:
- **Evolution roadmap (Step 6)**: automation improvement list = basis for phase 1/phase 2 projects (high-replacement items in phase 1, partial-replacement items in phase 2)
- **Product mapping (Step 7)**: product functions corresponding to automation solutions (OCR corresponds to invoice recognition module)
- **ROI**: replacement degree × manual hours = labor cost saved (to persuade the client to buy)

**Checks**:
- [ ] Does it cover all 5.1 "manual operation" and "human-machine collaboration" tasks?
- [ ] Is every task marked with replacement degree?
- [ ] Did the consultant confirm/adjust the AI-suggested automation solutions?
- [ ] Do "no replacement" tasks state the reason (requires human judgment/decision)?

### 5.4 Business Architecture Overview (Optional · Client Reporting)

**Positioning**: A visual overview of BA 1.0-5.3. Output when the client needs "one diagram to understand the whole business architecture"; not a mandatory deliverable. Use the `.biz-arch-flow` component (component 9).

**Trigger**: Output when the client explicitly asks for a "business architecture overview" or "one diagram to understand processes".

**Input**: BA 1.0 value chain + 3.0 process architecture + 5.1 task→service mapping

**Output**: numbered box chain (about 6 phases) + bottom execution band (key control points)

**Checks**:
- [ ] 5-8 phases, each with numbered circle + box + description
- [ ] Bottom execution band marks key control points (e.g. budget occupancy/deduction)
- [ ] Colors distinguish phase types (blue = data / red = approval / purple = control / orange = output)

### 5.5 Special Flow Diagram (Optional · Client-Specific Processes)

**Positioning**: When the client has special processes (e.g. three-entry budget preparation, multi-channel order flow), show them with a dedicated flow diagram. Use the `.tri-entry-flow` component (component 10) or another suitable process component.

**Trigger**: Output when client materials contain "multi-entry" / "multi-branch" / "special process".

**Input**: client's special process description

**Output**: layered flow diagram (entry layer → middle layer → step layer → output layer)

**Checks**:
- [ ] Number of entries matches client description
- [ ] Every step has explicit preconditions and outputs
- [ ] Control points (e.g. mandatory control rules) are explicitly marked

---

## DA: Data Architecture Complete Design Steps

### Principles (5)

| ID | Principle | Meaning |
|---|---|---|
| OP-1 | Object-oriented management | Data is organized around business objects, not systems |
| OP-2 | Global view | Data architecture covers all enterprise data, not a single project |
| OP-3 | Classification compliance | Data must follow standard classification (data domain/subject/entity) |
| OP-4 | Conceptual entity structured | Conceptual entities must have explicit attribute definitions |
| OP-5 | Data servitization same-source sharing | Same data stored once, shared through services |

### Input

- Business object list from business architecture
- Data dictionary of existing systems
- Data standard documents (if any)
- Industry data models (if any)

### 5-Layer Data Asset Catalog

| Layer | Name | Meaning | Example |
|---|---|---|---|
| L1 | Data domain | Top-level classification | Finance data domain |
| L2 | Data subject | Grouping within domain | Budget data subject |
| L3 | Conceptual entity | Data-ized business object | Budget form |
| L4 | Logical entity | Entity with attributes | Budget form (ID/amount/status/...) |
| L5 | Attribute | Entity field | Budget form.ID (VARCHAR(20)) |

### Design Steps

| Step | Task | Output |
|---|---|---|
| 1.0 | Asset catalog (incl. subject domains) | 5-layer data asset catalog table |
| 2.0 | Conceptual model | Conceptual entity relationship diagram (ER diagram, no attributes) |
| 3.0 | Logical model (third normal form) | Logical entity relationship diagram (with attributes + primary/foreign keys) |
| 4.0 | Data distribution | Data flow diagram / data source diagram / CRUD matrix |
| 5.0 | Overall blueprint | Cross-domain subject-domain model (enterprise-level data blueprint) |

### 1.0 Asset Catalog

**How**:
- Start from the business object list in business architecture
- Layer by data domain → data subject → conceptual entity
- Output: 5-layer catalog table

**Checks**:
- [ ] Does every L3 conceptual entity (DA-L3) correspond to a BA business object?
- [ ] Does every L2 data subject belong to exactly one L1 data domain?

### 2.0 Conceptual Model

**How**:
- Draw relationships among L3 conceptual entities (1:1 / 1:N / M:N)
- Do not draw attributes; only entities and relationships
- Output: conceptual ER diagram

**Checks**:
- [ ] Does every relationship have explicit direction and cardinality?
- [ ] Are there orphan entities (entities with no relationship)?

### 3.0 Logical Model

**How**:
- Add attributes on top of the conceptual model
- Normalize to third normal form (eliminate redundancy)
- Define primary/foreign keys
- Output: logical ER diagram

**Checks**:
- [ ] Does every entity have a primary key?
- [ ] Does every foreign key map to another entity's primary key?

### 4.0 Data Distribution

**How**:
- Data flow diagram: flow of data between systems
- Data source diagram: source system of each data item
- CRUD matrix: create/read/update/delete relationships between business documents × data entities
- Output: three diagrams/tables

**Checks**:
- [ ] Does every data entity have an explicit source system?
- [ ] Does the CRUD matrix cover all business documents?

### 5.0 Overall Blueprint

**How**:
- Cross-domain subject-domain model: show relationships among all data domains
- Output: enterprise-level data blueprint

**Checks**:
- [ ] Does it cover all L1 data domains?
- [ ] Are inter-domain relationships clear?

### Validation (Three Properties)

| Validation dimension | Check item | Typical criterion |
|---|---|---|
| Completeness | Does it cover all business objects? | All BA business objects have corresponding L3 conceptual entities |
| Reasonableness | Is granularity reasonable? | L5 attributes can guide database design |
| Integration | Interface with application architecture | L4 logical entities have corresponding functional items in AA |

---

## AA: Application Architecture Complete Design Steps

### Principles (3)

| ID | Principle | Meaning |
|---|---|---|
| OP-1 | Layered decoupling | Applications are organized by layers (domain/group/module), loosely coupled between layers |
| OP-2 | Experience-driven | Application design starts from user experience, not technology |
| OP-3 | Service-based implementation | Application functions are exposed through services, supporting reuse |

### Input

- Business architecture process architecture diagram + business object list
- Data architecture conceptual entity list
- Existing system list
- Functional requirements list

### 6-Layer Application Architecture Elements

| Layer | Name | Meaning | Judgment criteria | Example |
|---|---|---|---|---|
| AD | Application domain | Enterprise-level application grouping | Corresponds to BA L1 capability domain | Budget expense-control domain |
| AG | Application group | Grouping within domain | Corresponds to BA L2 capability group | Budget preparation group |
| APP | Level-1 module | Complete support for a single business capability | Has an independent business use case (who uses / what it does / what it outputs) | Budget control application |
| ABB | Level-2 module | **Systematization of APQC L4 activity** | **Collaboration unit requiring the process owner to coordinate multiple people** | Budget occupancy approval |
| Functional item | Function point | **A task that ends when assigned to one person** | **The minimal work unit the system replaces** | Automatic balance calculation |
| Functional sub-item | Implementation method | Concrete implementation of a functional item | How the system replaces (automation/intelligence) | Auto aggregation + deduction |

**Key principles**:
- **ABB boundary = process owner's coordination scope**: multi-person collaboration coordinated by one owner = one ABB
- **Functional item boundary = minimal task assignment unit**: ends when assigned to one person = functional item; needs coordination with others = ABB
- **Process levels are decided by organizational division of labor, not by the performer**: even if AI fully replaces human collaboration, the activity remains L4 in the process
- **Make cross-layer connections explicit (D-6)**: layered architecture diagrams (4A layered / layered) must mark inter-layer data flows/call relationships; pure stacked layers are not allowed—mark at least one inter-layer connection between every pair of layers (data flow direction + call relationship). Layers are "who calls whom, what data is passed", not isolated stacked color blocks

### 8-Step Design

| Step | Task | Output |
|---|---|---|
| 1.0 | Initial AD/AG/APP classification | Application domain/group/module list |
| 2.0 | Initial ABB identification | Level-2 module list |
| 3.0 | Functional item identification | Functional item list |
| 4.0 | Functional sub-item cleanup | Functional sub-item list |
| 5.0 | Adjust partitioning | Adjusted application architecture (merge/split) |
| 6.0 | Business relationship description | RACI matrix (roles × functions) |
| 7.0 | Application service design | Service list (interface definitions) |
| 8.0 | System adaptation and integration | Integration architecture diagram |

### 1.0 Initial AD/AG/APP Classification (Top-down)

**How**:
- Derive AD from BA L1 business capabilities
- Derive AG from L2 business capabilities
- Derive APP from L3 business capabilities (L3 provides process framework)
- Derive ABB from L4 activities (L4 activities decomposed into collaboration units)
- Output: AD/AG/APP list

**Checks**:
- [ ] Does every AD correspond to a BA L1 capability?
- [ ] Does every AG belong to exactly one AD?
- [ ] Does every APP have an independent business use case (who uses / what it does / what it outputs)?

### 2.0 Initial ABB Identification

**How**:
- Decompose ABB from APP (by business object or process step)
- Output: ABB list

**Checks**:
- [ ] Does every ABB belong to exactly one APP?

### 3.0 Functional Item Identification (Bottom-up)

**How**:
- Extract functional item candidates from every business process step
- Infer CRUD functions from business objects
- Infer functions from data architecture logical entities
- Output: functional item list

**Checks**:
- [ ] Is every functional item independently testable (has input/processing/output)?
- [ ] Are functional sub-items avoided being promoted to functional item level?

**Functional identification details** → [function-identification](#function-identification)

### 4.0 Functional Sub-Item Cleanup

**How**:
- Define an implementation method for each functional item (graphical / Excel import / API...)
- Output: functional sub-item list

**Checks**:
- [ ] Is every functional sub-item an implementation method of a functional item (not an independent function)?

### 5.0 Adjust Partitioning

**How**:
- Use CBM's "high cohesion, low coupling" principle to validate APP boundaries
- Merge/split/adjust
- Output: adjusted application architecture

**Checks**:
- [ ] Is every APP highly cohesive (internal functions closely related)?
- [ ] Are APPs loosely coupled (clear interfaces)?

### 6.0 Business Relationship Description

**How**:
- RACI matrix: roles × functional items
- Output: RACI matrix table

**Checks**:
- [ ] Does every functional item have exactly one R (responsible)?

### 7.0 Application Service Design

**How**:
- Define services (interfaces) exposed by APPs
- Output: service list (service name / input / output / caller)

**Checks**:
- [ ] Does every service have explicit inputs and outputs?

### 8.0 System Adaptation and Integration

**How**:
- Draw call relationships among APPs
- Draw integration relationships between APPs and external systems
- Mark three elements for each integration interface (D-6): **direction** (who calls whom) + **protocol/port** (what it uses) + **failure boundary** (what happens if it breaks)
- Output: integration architecture diagram

**Checks**:
- [ ] Are integration interfaces of every APP clear?
- [ ] Does every integration interface have all three elements (direction / protocol-port / failure boundary)?

### Validation (Three Properties)

| Validation dimension | Check item | Typical criterion |
|---|---|---|
| Completeness | Does it cover all business processes? | All BA process steps have corresponding functional items |
| Reasonableness | Is granularity reasonable? | APPs can be assigned to development teams |
| Integration | Interface with technology architecture | Every APP has a corresponding deployment node in TA |

---

## TA: Technology Architecture Complete Design Steps

### Principles (3-5)

| ID | Principle | Meaning |
|---|---|---|
| OP-1 | Standardization | Technology choices follow enterprise standards; do not introduce new technologies casually |
| OP-2 | Scalability | Architecture supports horizontal scaling for business growth |
| OP-3 | High availability | Critical systems 99.9% availability |
| OP-4 | Security and compliance | Meets industry security standards (MLPS/ISO27001) |
| OP-5 | Cost control | Technology choices consider total cost of ownership (TCO) |

### Input

- Application architecture APP list + deployment requirements
- Existing infrastructure list
- Technology stack constraints (enterprise standards)
- Security and compliance requirements

### 6-Step Design

| Step | Task | Output |
|---|---|---|
| 1.0 | Technology framework | Technology stack selection (language/framework/middleware) |
| 2.0 | Technology components | Component list (database/cache/message queue...) |
| 3.0 | Technology services | Service list (authentication/logging/monitoring...) |
| 4.0 | Technology platform | Three-horizontal-two-vertical platform diagram |
| 5.0 | Deployment nodes | Deployment architecture diagram |
| 6.0 | Overall blueprint | Technology architecture blueprint |

### 1.0 Technology Framework

**How**:
- Determine technology stack (language/framework/middleware) from the AA APP list
- Mark the technology stack used by each APP
- Follow enterprise technology standards; do not introduce new technologies casually
- Output: technology stack selection table (APP / language / framework / middleware / rationale)

**Example**:

| APP | Language | Framework | Middleware | Rationale |
|---|---|---|---|---|
| Budget management | Java | Spring Boot | OA Platform | Client already has OA Platform; reuse it |
| Voucher push | Java | Spring Boot | ERP PO | Standard ERP integration method |

**Checks**:
- [ ] Is every APP marked with its technology stack?
- [ ] Do technology choices comply with enterprise standards?
- [ ] Do newly introduced technologies have sufficient rationale?

### 2.0 Technology Components

**How**:
- List technology components used by the system (database/cache/message queue/file storage/search engine...)
- Mark each component's purpose and hosted APPs
- Output: component list (component / type / purpose / hosted APP)

**Example**:

| Component | Type | Purpose | Hosted APP |
|---|---|---|---|
| MySQL | Database | Store budget data | Budget management |
| Redis | Cache | Cache budget occupancy status | Budget control |
| RabbitMQ | Message queue | Async voucher push processing | Voucher push |
| MinIO | File storage | Store attachments | Budget management |

**Checks**:
- [ ] Is every technology component marked with purpose and hosted APP?
- [ ] Are component choices consistent with 1.0 technology framework?

### 3.0 Technology Services

**How**:
- List technology services required by the system (authentication/authorization/logging/monitoring/configuration/task scheduling...)
- Mark each service's implementation method (build in-house / purchase / cloud service)
- Output: technology service list (service / purpose / implementation method / user)

**Example**:

| Service | Purpose | Implementation method | User |
|---|---|---|---|
| Unified authentication | Single sign-on | Built into OA Platform | All APPs |
| Centralized logging | Log collection | ELK self-built | All APPs |
| Monitoring and alerting | System monitoring | Prometheus+Grafana | Operations team |
| Task scheduling | Scheduled tasks | Quartz | Voucher push |

**Checks**:
- [ ] Is every technology service marked with implementation method?
- [ ] Do authentication/authorization services cover all APPs?

### 4.0 Technology Platform (Three Horizontals, Two Verticals)

**Three horizontals**:
- Infrastructure layer: cloud/compute/storage/network
- Digital platform layer: data middle platform / business middle platform / technology middle platform
- Public service layer: authentication/message/file/log

**Two verticals**:
- Operations: monitoring/alerting/automation
- Information security: firewall/encryption/audit

### 5.0 Deployment Nodes

**How**:
- Each AA APP maps to one deployment node (server/container/cluster)
- Mark the APP, SVC, specification, and high-availability plan hosted by the node
- Output: deployment architecture diagram (node groups + hosting relationships + connections)

### 6.0 Overall Blueprint

**How**:
- Integrate 1.0-5.0 outputs into one overall technology architecture diagram
- Includes: technology stack + components + services + three horizontals/two verticals + deployment nodes + integration relationships
- Output: technology architecture blueprint (one overview diagram + legend)

**Checks**:
- [ ] Does the blueprint integrate all 1.0-5.0 outputs?
- [ ] Is the legend complete (color/line/icon meanings)?
- [ ] Can every APP be traced from the blueprint to its technology stack, components, services, and deployment nodes?

### Validation (Three Properties)

| Validation dimension | Check item | Typical criterion |
|---|---|---|
| Completeness | Does it cover all APP deployment needs? | All APPs have corresponding deployment nodes |
| Reasonableness | Are technology choices reasonable? | Complies with enterprise standards + cost controlled |
| Integration | Interface with external systems | Integration interfaces are technically feasible and have all three elements (direction / protocol-port / failure boundary) |

---

## governance: Governance Responsibility Matrix and Evolution Roadmap

> Positioning: optional section requiring human decisions; AI only produces a draft.
> Default form is the "responsibility and system coverage matrix" (adapted to enterprise management → information system scenarios); the three-governance × three-dimension is enabled only when a group-level client reports the governance system.

### Responsibility and System Coverage Matrix (Default)

Answers one question: **after the system goes live, who owns each process, each data type, and each module?**

| Business object/process | Process Owner | Supporting APP/module | Deployment node |
|---|---|---|---|
| Budget form | Finance manager | Budget preparation APP | OA Platform app server |
| Invoice | Finance specialist | Invoice registration APP | OA Platform app server |
| Procurement request form | Procurement officer | Budget occupancy APP | OA Platform app server |

**Hard rule: the governance section must not invent new content.** Every matrix row must come from already locked BA/AA/TA documents and the #cross-domain reconciliation table:

- Business object/process: from BA 4.0 business object list / 3.0 process architecture
- Process Owner: from the R (responsible) in BA 5.0 RACI matrix
- Supporting APP/module + deployment node: from AA/TA and cross-domain reconciliation results
- Rows not in the reconciliation table: first fill the corresponding domain, then add to the matrix

Division of labor with the 5.2 process-service-document mapping diagram: 5.2 verifies "whether processes land on system capabilities" (behavioral view, service granularity); this matrix answers "who is responsible and in which module" (management view, APP granularity). Two slices of the same mapping; data must be consistent.

### Group-Level Variant: Three Governance × Three Dimensions (Optional · Only for group-level clients reporting governance systems to senior management; not default for mid/small clients)

> Source: operator/very-large-enterprise EA blueprint reference (`_knowledge/templates/outlines/架构图/reference.md` instance 2), not default in this scenario.

**Two-leg model**: left leg (technology) = BA/AA/DA/TA; right leg (governance) = architecture governance / project governance / operations governance; feet (implementation) = implementation division of labor + institutional norms.

**Three governance × three dimensions 9-grid** (answer at least 6; if fewer, state which grid the client's current state does not support):

|  | Organization (who is responsible) | Process (what mechanism) | Skills (what capability) |
|---|---|---|---|
| Architecture governance | Architecture committee / architect role | Architecture review, compliance check, exception request | EA methods (TOGAF / ArchiMate) |
| Project governance | PMO / project owner | Project initiation gate, milestone review, change management | CMMI / IPD / PMP / Prince2 |
| Operations governance | Operations owner / data steward | Release process, inspection, SLA assessment | ITIL / SFIA5 |

Governance system three layers: L1 three governance → L2 subordinate modules (e.g. architecture governance includes "enterprise architecture control / SOA governance / cloud governance / architecture evolution implementation governance") → atomic capabilities (CMMI / IPD / PMP / Prince2 / SFIA5 etc.).

**Two-mode IT decision** (used when setting governance scope for systems):

| Decision dimension | Steady state (SOR) | Agile state (SOI) |
|---|---|---|
| Business characteristics | Clear strategy / mature processes | Trial-and-error exploration / rapid iteration |
| IT characteristics | Standardized / centralized | Distributed / DevOps |
| Decision process | IPD / CMMI | Scrum / DevOps |
| KPI | Stable operations / cost control | Time-to-market / innovation rate |
| Governance | Centralized + federated hybrid | Business-unit based |

### Evolution Roadmap (Must Answer 5 Steps, No Skipping)

Fixed chain: **gap diagnosis → key tasks → project portfolio → roadmap → value estimate**.

- Skipping steps hides value: do not jump straight to a roadmap without gap analysis; a roadmap without gaps has no foundation.
- Value estimates must correspond to the earlier gaps—how much each gap is resolved, not new items.
- Pain points mentioned in the first section must be traceable on the value page.

**As-Is → To-Be comparison axis (D-6 · weak timeline upgrade)**: the evolution roadmap should not only draw "what to do in the future"—first draw a comparison axis of "what it is now" → "what it will become", with each phase comparing As-Is current state vs To-Be target in two columns, so the change is visible at a glance.

**Phase gates (D-6 · every phase must state entry/exit conditions)**: every phase (P1/P2/P3…) must clearly state:

| Phase | Entry conditions | Exit conditions | Responsibility | Risks and recommendations |
|---|---|---|---|---|
| P1 | Current-state diagnosis complete, key gaps defined | Core data connected, main process connection acceptance | Project team | Data migration risk → recommend pilot first |

> Phase gate = objective conditions that determine "can we enter the next phase", not empty phrases like "complete phase 1". Pair with B-7 milestone_gantt (task tracks × milestones × dependencies, laid out by week) to replace weak timelines with ≤4 milestones (see SKILL.md combined-figure guidance).

Three detail levels:

| Form | Applicable to | Content |
|---|---|---|
| A Simple version (5 pages) | Reporting to executives | Only draw P1/P2/P3 three main lines + time windows |
| B Full version (10+ pages) | Project initiation / feasibility study | Gap 2D table → key tasks (A1-An) → urgency × importance + strategic × potential ranking → project portfolio (P1-Pn) → roadmap → project cards (each card answers purpose/scope/cycle/resources/risks/benefits) → budget summary → implementation plan |
| C Time-window version | Reporting wording | 0-3 months current-state research/architecture diagnosis → 3-6 months phase 1 (core data + process connection) → 6-12 months phase 2 (platform build + application migration) → 12-24 months phase 3 (governance system + full rollout) → 24+ months continuous optimization |

---

## function-identification: Functional Identification Deep Dive (CBM/APQC)

> This is the **AA methodology reference library** (AA sub-step, not an independent Step). The useful parts are operating rules (granularity judgment + functional identification steps); methodology theory details are in [methodology](#methodology-methodology-foundations).

### CBM Summary (Exception Path Only)

IBM CBM (Component Business Model, 2003) = 3 rows (Direct strategy / Control management / Execute) × N columns (business capabilities) 2D table for capability derivation. **Use only when the client talks about "capability systems"**; use "high cohesion, low coupling" to validate APP boundaries. Theory details omitted; not needed for diagramming.

### APQC PCF Deep Dive

APQC PCF (Process Classification Framework) is a cross-industry process classification framework with a 5-layer structure. **L1-L3 are APQC standard references; L4-L5 are enterprise-filled (APQC does not provide them)**:

| Layer | Name | Defined by | Meaning | Example |
|---|---|---|---|---|
| L1 | Category | APQC standard | Top-level classification (13) | 9.0 Manage financial resources |
| L2 | Group | APQC standard | Process group | Budget management |
| L3 | Process | APQC standard | Process | Budget preparation and execution |
| L4 | Activity | **Enterprise-filled** | Activity | Invoice registration (example, not APQC standard) |
| L5 | Task | **Enterprise-filled** | Task | Check invoice info / enter into system (example, not APQC standard) |

**Correspondence with 4A** (inferred by this skill, not any official standard):

| APQC | 4A | Organizational-division viewpoint | System viewpoint |
|---|---|---|---|
| L1 Category | AD application domain | Main value chain | Enterprise-level application grouping |
| L2 Group | AG application group | Business model grouping | Application grouping within domain |
| L3 Process | APP level-1 module | End-to-end process | Complete support for an independent business capability |
| **L4 Activity** | **ABB level-2 module** | **Cross-person collaboration unit** (requires process owner coordination) | **Systematization of collaboration activities** |
| **L5 Task** | **Functional item** | **Single-person task** (ends when assigned to one person) | **Minimal work unit the system replaces** |
| — | **Functional sub-item** | No correspondence | How the system replaces (automation/intelligence) |

**L4 vs L5 judgment criteria**:
- **L4 (ABB)**: requires cross-person/cross-role/cross-department collaboration, with a process owner responsible for coordinating progress
- **L5 (functional item)**: ends when assigned to one person (or one position); no further coordination needed
- Even if there is only BPM and no OA, and people manually check Excel to complete collaboration, the activity is still L4

### Functional Identification Steps (APQC Default / CBM Exception)

**First decide path** (default APQC; switch to CBM only when the client talks about "capability systems", see [methodology primary/secondary rule 2](#methodology-methodology-foundations)):

| Client type | Material characteristics | Path | Derivation starting point |
|---|---|---|---|
| Process-driven (default) | Talks about "business process", "process steps", "flow" | **APQC path** (process derivation) | Business process steps |
| Capability-driven (exception) | Talks about "business capability", "core capability", "capability system" | **CBM path** (capability derivation) | Business capability list |

**APQC path** (default · main path for enterprise management systems, use with [BA 5.2 section](#52-process-service-document-mapping-diagram-mandatory-ba-must-produce-draw-after-51)):
1. Start from BA 5.2's application-service candidate list, traverse tasks to extract functional item candidates (Bottom-up)
2. Infer CRUD functions from business objects (Bottom-up)
3. Merge/split/adjust, validate APP boundaries with APQC process classification

**CBM path** (exception · only when client talks about capability systems):
1. Derive AD/AG/APP from BA L1/L2/L3 capabilities (BA-CAP-L1/L2/L3) (Top-down)
2. Infer CRUD functions from business objects (Bottom-up)
3. Merge/split/adjust, validate APP boundaries with CBM "high cohesion, low coupling" principle

### Granularity Judgment Rules

> See the definitions and judgment criteria in [6-layer application architecture elements](#6-layer-application-architecture-elements). Here only anti-pattern examples.

| Layer | Anti-pattern |
|---|---|
| **APP** | Promoting a functional item to APP level (e.g. "OCR recognition" is not an APP) |
| **ABB** | Decomposing an ABB into functional items (e.g. "budget occupancy approval" is not a functional item; it is a cross-person collaboration unit) |
| **Functional item** | Promoting a functional sub-item to functional item (e.g. "graphical fill-in" is not a functional item) |
| **Functional sub-item** | Treating an implementation method as a function (e.g. "Excel import" is not an independent function) |

### Example: Three-Track Classification of Invoice Registration

| Methodology | Classification | Level | Meaning |
|---|---|---|---|
| IBM CBM | Execute-level activity | Activity within a business component | Concrete work item, not an independent component |
| APQC PCF | Activity (L4) | Layer 4 of process classification | Cross-person collaboration unit, requires process owner coordination |
| 4A architecture | ABB (level-2 module) | Layer 4 of application architecture | Systematization of APQC L4 activity |

**Key insights**:
- CBM's "activity (Execute)" ≈ APQC's "Process (L3)" ≈ 4A's "AG application group"
- CBM's "sub-activity" ≈ APQC's "Activity (L4)" ≈ 4A's "**ABB level-2 module**"
- All three describe "a tightly related set of work items"
- But granularity differs: CBM is coarsest (strategy view), APQC is medium (process view), 4A is finest (system implementation view)

### CBM Capability Matrix Diagram (Optional · Packaged Software Sales Showing Capability Coverage)

**Positioning**: Output when the client is capability-driven, or packaged software sales need to show "which client business domains the software covers". Use the `.cbm-matrix` component (component 11).

**Triggers**:
- Client talks about "business capability", "core capability", "capability system" (capability-driven)
- Packaged software sales need to show capability coverage
- Client asks for "one matrix diagram to understand capability distribution"

**Input**: CBM three layers (decision strategy / management operations / support services) × management domain division + system tag annotations

**Output**: 3-row × N-column matrix diagram; each cell contains capability item + system tag badge + red-frame investment focus

**Checks**:
- [ ] Strictly 3 management rows (decision strategy / management operations / support services)
- [ ] Each cell marked with system tag (green = covered / blue = new platform / orange = new module / purple = other system)
- [ ] Investment focus highlighted with red frame (★ marker)
- [ ] Legend immediately follows the diagram

---

## product-mapping: Product Mapping Trio (Packaged Software Sales Only)

### Core Idea

You are a packaged software salesperson, not designing architecture from scratch. Your architecture diagram = **client requirements × software functions** correspondence.

4A is a methodology language; your product is an engineering language; the two cannot be force-fitted. The product mapping trio is an additional deliverable independent of the 4A architecture diagram.

### The Trio

| Deliverable | Meaning | Analogy | Output form |
|---|---|---|---|
| **Solution Architecture Diagram** | Shows how your software modules map to client business processes | ERP FI/CO/SD/MM mapping diagram | Architecture diagram (annotate your software modules on the 4A diagram) |
| **Business Capability Map** | Client business capabilities → your software module mapping table | ERP Capability Map | Mapping table (Excel/Markdown) |
| **Fit-Gap Analysis** | Client requirements vs your software standard functions, marking Fit / Partial / Gap | ERP Fit-Gap analysis | Analysis table (Excel/Markdown) |

### Mapping Steps

| Step | Task | Output |
|---|---|---|
| 1.0 | Extract 4A requirements from client materials | Client requirements list (BA/DA/AA/TA) |
| 2.0 | Extract 4A capabilities from your software function list | Software capability list |
| 3.0 | Create mapping table: client requirement → software function | Mapping table (marked Fit / Partial / Gap) |
| 4.0 | Draw diagram: annotate your software modules on the standard 4A architecture diagram | Product architecture diagram |

### 1.0 Extract 4A Requirements from Client Materials

**How**:
- BA requirements: extract from client business process documents (process steps / business objects / roles)
- DA requirements: extract from client data standard documents (data entities / data sources)
- AA requirements: extract from client functional requirements list (function points / integration requirements)
- TA requirements: extract from client technical constraint documents (deployment environment / security requirements)
- Output: 4A requirements list

### 2.0 Extract 4A Capabilities from Your Software Function List

**How**:
- What modules does your software have (corresponding to AA APPs)
- What functions does each module have (corresponding to AA functional items)
- What data entities does your software support (corresponding to DA conceptual entities)
- Your software technology stack (corresponding to TA technology components)
- Output: software capability list

### 3.0 Create the Mapping Table

**How**:
- X-axis: client requirements (4A requirements list)
- Y-axis: software functions (software capability list)
- Cells: Fit (standard function satisfies) / Partial (partially satisfies, needs customization) / Gap (does not satisfy)
- Gap items must state: custom development / third-party integration / not currently supported
- Output: mapping table

**Example**:

| Client requirement | Software function | Relationship | Notes |
|---|---|---|---|
| Three-entry budget preparation (0702/0902/0904) | OA Platform budget preparation module | ✅ Fit | Supported by standard function |
| 1006 mandatory occupancy | OA Platform budget execution module | ✅ Fit | Supported by standard function |
| Push voucher to ERP | OA Platform integration interface module | ✅ Fit | Supported by standard function |
| Independent Europe-region assessment | ? | ❌ Gap | Needs custom development or state not supported |

### 4.0 Draw the Diagram: Product Architecture Diagram

**How**:
- On the standard 4A architecture diagram, annotate "this is our software module"
- Use different colors: Fit (green) / Partial (yellow) / Gap (red)
- Output: product architecture diagram

### Output Location

- Place the product mapping trio after the 4A architecture diagrams (show methodology architecture first, then product mapping)
- Naming: `{客户}_{产品名}_产品映射_v{N}.html`

### Validation Checklist

- [ ] Is every client requirement marked Fit / Partial / Gap?
- [ ] Do Gap items all state handling (customization/integration/not supported)?
- [ ] Does the product architecture diagram clearly mark software module locations?
- [ ] Does the mapping table cover all 4A requirements?

---

## requirements: Requirements Identification Steps

### Core Problem

How does AI extract architecture information from client materials (PPT/documents/interview records)? The current skill assumes AI already knows what to draw, but the actual workflow is:

```
客户材料（PPT/文档/访谈）
    ↓ 需求识别
4A 信息清单（BA/DA/AA/TA 各有什么）
    ↓ 架构设计
4 张架构图
```

### Requirements Identification Steps

| Step | Task | Output |
|---|---|---|
| 1.0 | Material classification | Material classification table (which are BA/DA/AA/TA materials) |
| 2.0 | Information extraction | 4A information list (which materials support each domain) |
| 3.0 | Gap analysis | Gap list (which 4A domains lack material support) |
| 4.0 | Association mapping | 4A association table (cross-domain mapping relationships) |
| 5.0 | Priority ranking | Design order (which domain to do first) |

### 1.0 Material Classification

**How**:
- First classify material form: **mixed material** (transcripts/interview notes) vs **single material** (requirements list / product manual / policy document)
- Classify single materials by supported domain:
  - BA materials: business process documents / organization structure / strategy documents
  - DA materials: data standard documents / data dictionary / data model / business document sample forms
  - AA materials: system list / functional requirements list / integration requirements
  - TA materials: technology stack documents / deployment environment documents / security requirements
- **Do not classify mixed materials as a whole**: one sentence in a transcript may contain BA ("three approval lines") + AA ("OA Platform needs budget control") + TA ("ERP only does FI/CO"). Such materials are read in full first, then split into domains by topic during 2.0 information extraction
- Output: material classification table

**Key principle**: client conversation is naturally mixed; you cannot require the conversation to follow the methodology. AI's job is to split structured information from messy conversation, not to require the client to speak in 4A categories.

**Example**:

| Material | Form | Supported domains | Handling |
|---|---|---|---|
| Financial requirements communication transcript.txt | Mixed | BA+AA+TA | Read in full; split by topic in 2.0 |
| Budget preparation and execution management.docx | Mixed | BA+AA | Read in full; split by topic in 2.0 |
| Investment budget list.xlsx | Single | DA | Classify directly |
| ERP interface document.docx | Single | AA+DA | Classify directly |
| Financial policy.docx | Single | BA | Classify directly |

### 2.0 Information Extraction

**How**:
- Extract key information from each material type
- BA extracts: business objects / process steps / roles
- DA extracts: conceptual entities / data sources / data standards
- AA extracts: function points / integration requirements / system list
- TA extracts: technology components / deployment nodes / security requirements
- Output: 4A information list

### 3.0 Gap Analysis

**How**:
- Distinguish two gap types:
  - **Document gap**: a 4A domain lacks material support; needs additional interview or documents
  - **Scope gap**: scope the client actively excluded (e.g. "Europe region not assessed for now"); no material needed, but mark it to avoid AI mistakenly trying to fill it
- Document gaps mark what needs to be added and how to obtain it
- Scope gaps mark the exclusion reason; later steps do not cover them
- Output: gap list (two types)

**Example**:

**Document gaps (need materials)**

| 4A domain | Existing material support | Gap | Need to add |
|---|---|---|---|
| BA | Transcript + financial policy | Missing QCA header sample form | Wait for Chen Dapeng to provide after meeting |
| DA | Investment budget list + project budget list | Missing complete budget subject list | Wait for Ma Dan to provide categories + details |
| AA | Transcript + budget preparation demo | None | — |
| TA | Transcript | Missing deployment environment info | Need IT interview |

**Scope gaps (actively excluded, do not fill)**

| Excluded scope | Reason | Impact |
|---|---|---|
| Europe region | Multi-language/multi-currency needs separate assessment | Current 4A architecture does not cover Europe-region business |

### 4.0 Association Mapping

**How**:
- BA business object → DA conceptual entity (same thing, different viewpoint)
- BA process step → AA functional item (process-driven function)
- DA logical entity → AA functional item (data-driven function)
- AA APP → TA deployment node (application-driven technology)
- Output: 4A association table

**Detailed association rules** → [cross-domain](#cross-domain)

### 5.0 Priority Ranking

**How**:
- Usual order: BA → DA → AA → TA → governance
- Reason: BA is input; DA/AA depend on BA; TA depends on AA
- Output: design order

### Validation Checklist

- [ ] Are all client materials classified (including mixed-material identification)?
- [ ] Are mixed materials (transcripts/interviews) read in full and split into domains by topic?
- [ ] Is key information extracted from each material type?
- [ ] Are AA function points pre-judged for granularity (candidate APP / candidate functional item)?
- [ ] Are gaps distinguished between document gaps (need materials) and scope gaps (actively excluded)?
- [ ] Are scope gaps marked with exclusion reason and not covered in later steps?
- [ ] Is the 4A association table created?
- [ ] Is the design order determined?

---

## scenario-walkthrough: Scenario Walkthrough Validation (D-6 · Required in Phase 2 · Most Important)

### Core Problem

Cross-domain reconciliation only proves "the four diagrams are internally consistent", not "the architecture can run the business". Scenario walkthrough walks 3-5 key business scenarios end-to-end through each 4A layer to validate **external validity**—the architecture is not just paper-consistent but can actually carry the client's real business actions.

### How

1. Select 3-5 key business scenarios (cover core main processes + at least 1 exception/boundary scenario, e.g. "expense reimbursement", "budget addition", "cross-system reconciliation failure").
2. Walk each scenario through the 4A layers one by one and output a walkthrough table (scenario action chain reference: user's original words → intent recognition → information prefill → rule validation → human confirmation → system write-back → result evidence):

| Layer | Walkthrough question | Record |
|---|---|---|
| BA | Which process step chain does the scenario correspond to? Who does it? | Step chain + roles |
| AA | Which APP/functional item handles each step? | APP/functional item name |
| DA | Which data entities are read/written in each step? Flow? | Entity + read/write |
| TA | Which deployment nodes run it? What interface/protocol? | Node + protocol |

3. "Breaks" found during walkthrough (a layer has no handler) or "misalignments" (names do not match between layers) are gaps; backfill the corresponding documents before entering phase 3.

### Validation

- [ ] All 3-5 scenarios walked through completely; every cell in the walkthrough table can be filled
- [ ] Every scenario chain has a handler at every 4A layer; no breaks
- [ ] Gaps found in walkthrough have been backfilled into documents (not "defer to later")

---

## cross-domain: 4A Cross-Domain Rules

### Core Problem

The 4 architecture diagrams are not independent; they have explicit association relationships. When AI makes the 4 diagrams, it must check cross-domain consistency, not guess from context.

### Association Rules

> **Cross-domain reconciliation uses names, not L numbers** (see [L numbering and step numbering rules](#l-numbering-and-step-numbering-rules)). The L numbers in the table below only indicate positions within that domain and are not used for cross-domain comparison.

| Relationship | Rule (reconcile by name) | Check point | Example |
|---|---|---|---|
| BA → DA | BA business object = DA conceptual entity | "Invoice" as a BA business object must be a same-name conceptual entity in DA | BA "budget form" → DA "budget form" conceptual entity |
| BA → AA | BA process step = AA APP identification input | "Invoice registration" as a BA process step must have a corresponding APP in AA | BA "invoice registration" process → AA "invoice registration" APP |
| DA → AA | DA logical entity = object operated by AA functional items | DA "invoice table" → AA "invoice entry/validation/archive" functions operate on it | DA "budget form table" → AA "budget preparation/adjustment" functions operate on it |
| AA → TA | Every AA APP → TA deployment node | "Invoice registration" APP → TA "application server" node | AA "budget preparation" APP → TA "OA Platform app server" |
| All four → governance | Owner of all four = organizational design in governance | DA data owner = governance "data steward" role | BA process owner = governance "process administrator" role |

### Cross-Domain Consistency Checklist

- [ ] Every BA business object has a same-name conceptual entity in DA
- [ ] Every BA process step has a corresponding APP in AA
- [ ] Every DA logical entity has a functional item in AA operating on it
- [ ] Every AA APP has a corresponding deployment node in TA
- [ ] Owners of all four have corresponding roles in the governance section
- [ ] The same business object has the same name across the 4 diagrams (consistent terminology)

### Example: A Group's Budget Expense-Control System

| BA business object | DA conceptual entity | AA function | TA deployment node | Governance owner |
|---|---|---|---|---|
| Budget form | Budget form | Budget preparation APP | OA Platform app server | Finance manager |
| Invoice | Invoice | Invoice registration APP | OA Platform app server | Finance specialist |
| Procurement request form | Procurement request form | Budget occupancy APP | OA Platform app server | Procurement officer |
| Contract | Contract | Contract registration APP | OA Platform app server | Contract administrator |
| Payment request form | Payment request form | Payment consumption APP | OA Platform app server | Finance specialist |

### Terminology Consistency Rules

- The same business object must have the same name across the 4 diagrams
- If BA calls it "budget form", DA cannot call it "budget form document", AA cannot call it "budget preparation form"
- When terminology is inconsistent, use BA's naming as authoritative (BA is the source)

### Handling Check Failures

- If a BA business object has no corresponding DA conceptual entity → add the DA conceptual entity
- If a BA process step has no corresponding APP in AA → add the AA APP
- If a DA logical entity has no corresponding function in AA → add the AA functional item
- If an AA APP has no corresponding deployment node in TA → add the TA deployment node
- If an owner of the four has no corresponding role in governance → add the governance organizational design

---

## composition-extras: Central Ecosystem Topology and Multi-Tenant Governance Diagram Narratives (D-6 · Skill Layer · No Renderer Changes)

Narratives for two high-frequency consulting diagram types (no renderer changes; assemble from existing diagram subtypes or hand-write in PPT):

### Central Ecosystem Topology (Platform-Type Clients)

**Applicable**: client is platform/hub type (ERP platform, middle platform, API gateway) and needs to explain "core hub + peripheral roles + interface direction + governance ring".

**Structure**:
- Core hub: central large card (platform name + core module chip)
- Peripheral roles: ≤6 role cards surrounding (supplier/customer/channel/regulator/internal system), connections stop at the hub edge
- Interface direction: each connection marks direction (who calls whom) + protocol/port + failure boundary (integration three elements)
- Governance ring: outer ring marks governance rules (onboarding/data sovereignty/billing/security compliance)

**Reuse**: diagram `architecture/platform_hub` (center-surround-right integration) carries the main structure; governance ring uses legend slot `legend` + attachment slot `notes`.

### Multi-Tenant Governance Diagram (Group-Type Clients)

**Applicable**: group-type clients need to explain "organization hierarchy + tenant boundaries + data isolation".

**Structure**:
- Organization hierarchy: left column group/subsidiary/business-unit three-level tree
- Tenant boundary: each tenant is an independent boundary box (data/configuration/permission isolation); list that tenant's applications and data inside the box
- Data isolation: mark isolation policy on boundaries between tenants (physical isolation / logical isolation / shared table + tenant field)

**Reuse**: diagram `architecture/layered` (layers) + `relationship/org_tree` (organization hierarchy); tenant boundaries use `layered`'s layer boxes, isolation policies written as inter-layer connection annotations (make cross-layer connections explicit).

---

## appendix: Common Anti-Patterns

### Architecture Diagram Anti-Patterns

- ❌ Directly listing "we will build an XX system" (missing the principles + inputs + deliverables triplet)
- ❌ Replacing "architecture" with "solution" / "technical proposal" (architecture has methodology meaning, not a strategy document)
- ❌ Confusing "application architecture" with "application module list" (the former is layered, the latter is a list)
- ❌ Skipping the "principles" page and jumping straight to steps (each architecture type needs at least 3-6 principles explained first)
- ❌ Embedding company logos / system screenshots in architecture diagrams (unless provided by the client as illustrations)
- ❌ Drawing "current state → blueprint" as two side-by-side diagrams without addressing the gap analysis in between
- ❌ Missing one of the three governance dimensions (architecture/project/operations) in the governance section

### Functional Identification Anti-Patterns

- ❌ Promoting a functional item to APP level (e.g. "OCR recognition" is not an APP; "invoice registration" is an APP)
- ❌ Promoting a functional sub-item to functional item level (e.g. "Excel import" is a sub-item, not a functional item)
- ❌ Treating a business object as a function (e.g. "invoice" is an object; "invoice entry" is a function)
- ❌ Treating an implementation method as a function (e.g. "graphical fill-in" is a sub-item, not a functional item)

### Cross-Domain Consistency Anti-Patterns

- ❌ The four 4A diagrams are independent and cross-domain consistency is not checked
- ❌ The same business object is called different names across the 4 diagrams
- ❌ BA business object has no corresponding DA conceptual entity
- ❌ AA APP has no corresponding TA deployment node

### Product Mapping Anti-Patterns

- ❌ Hiding Gap items in product mapping without marking them (Gap must be explicitly marked + state handling)
- ❌ Force-fitting 4A methodology language and product engineering language (the two cannot be one-to-one)
- ❌ Putting product mapping before the 4A architecture diagrams (should be after; methodology first, then product)

---

## rendering: Visual Rendering Spec

> **Split into a separate file**: the visual rendering spec (CSS classes, component library, color schemes, etc.) has been split into [styles.md](./styles.md).
>
> **When to use**: after writing the 4A documents and passing the merge check, read styles.md when drawing the diagrams at the end.

## checklist: Validation Checklist (Post-Generation Total Check · Any Failure Must Be Redone)

**Structure**
- [ ] Block 1 explains "principles" first, not directly jumping to steps
- [ ] Step numbering uses 1.0/2.0/3.0 + 1.1/1.2 second-level nesting
- [ ] Every step has "Input/Task/Output" triplet
- [ ] Three-property validation appears at the end of each section

**Domain-specific**
- [ ] DA must produce the 5-layer asset catalog (L1-L5)
- [ ] AA must produce the 6-layer diagram (AD/AG/APP/ABB/function/sub-item)
- [ ] TA must produce three horizontals, two verticals
- [ ] Every governance matrix row has Owner + supporting module and is consistent with the cross-domain reconciliation table
- [ ] Evolution must answer 5 steps without skipping

**Functional identification**
- [ ] Every APP has an independent business use case
- [ ] Every ABB belongs to exactly one APP
- [ ] Functional items are independently testable
- [ ] Functional sub-items are implementation methods, not independent functions

**Cross-domain**
- [ ] BA business objects have corresponding DA conceptual entities
- [ ] BA process steps have corresponding AA APPs
- [ ] DA logical entities have corresponding AA functional items
- [ ] Every AA APP has a corresponding TA deployment node
- [ ] Terminology consistent (same object has same name across the 4 diagrams)

**Product mapping (if any)**
- [ ] Every requirement marked Fit/Partial/Gap
- [ ] Gap items state handling

**General**
- [ ] Do not bind to a client industry name
- [ ] No banned words (赋能/抓手/闭环/生态/打通/全方位/一站式/卓越)
- [ ] Run style-check + theme-verify
