# Spec 协议 v1（spec.yml 字段与行为单一事实源）

> 版本 v1 · 2026-07-20 · 状态：生效
> 上游：内部协议重构计划 §六（Phase 1 协议层收敛），本文档是其 §6.4 交付物；该计划文档不随发布版分发
> 代码事实源：`_renderer/elements.py`（字段兼容 + 能力矩阵 + 降级文本）、`_renderer/schema.py`（全量校验）；本文与代码冲突时以代码为准并回修本文
> 读者：所有写 spec 的人与 AI。流程入口（confirmed 门禁、生成命令）见 `skills/spec-writing-guide/SKILL.md`，本协议只管"字段怎么写、写了会怎样"

---

## 1. 顶层字段

以 `_renderer/__init__.py`（HTML/DOCX）与 `_pptd_gen.py`（PPTD）实际读取为准。

| 字段 | 必填 | 缺省 | 说明 |
|------|------|------|------|
| `confirmed` | 是（生成前） | `false` | 确认门禁。未设 `true` 时所有 `*-build` 抛 `RenderBlockedError`（`src/_cli_guards.py:16-21`，判定单点 `src/_cli_guards.py:6-13`）。只能由人工确认后添加，AI 不得自设 |
| `client_name` | 否 | — | **存在但为空字符串时阻断生成**（`_renderer/__init__.py:101-102`）；不写该字段则不检查 |
| `project` | 否 | — | 信息字段，渲染器不消费（outline-to-spec 写入，`_outline_to_spec.py:352`） |
| `style` | 否 | `enterprise` | 风格名：`education / enterprise / tech / gov`（`_renderer/__init__.py:112`）。注意：v1 中 HTML 端不消费 styles.json（重构计划 §一），`--style` 仅影响 PPTD/报价 |
| `author` | 否 | `""` | 顶层作者。`document.author` 缺省时的回退（`_renderer/__init__.py:165,213`）；PPTD 封面也读（`_pptd_gen.py:245-255`） |
| `date` | 否 | `""` | 顶层日期。`document.cover.date` 缺省时的回退（`_renderer/__init__.py:170`）；PPTD 封面也读（`_pptd_gen.py:261-262`） |
| `document.title` | 建议 | `"方案文档"` | 主标题（`_renderer/__init__.py:211,404`；PPTD `_pptd_gen.py:75`） |
| `document.subtitle` | 否 | `""` | 副标题（`_renderer/__init__.py:212,409`） |
| `document.author` | 否 | 回退顶层 `author` | 文档级作者，优先于顶层（`_renderer/__init__.py:165,213`） |
| `document.cover` | 否 | — | 封面配置，见 §1.1 |
| `pages` | 是 | `[]` | 页面数组，见 §2（`_renderer/__init__.py:114`） |
| `format` | 否 | `{}` | DOCX 招标格式，见 §1.2（`_renderer/__init__.py:115`） |
| `definition_of_done` | 否 | `[]` | Sprint Contract 验收标准，生成前打印供 review 对照（`_renderer/__init__.py:106-110`） |
| `theme.colors` | 否 | 内置 9 色 | HTML 配色覆盖：`heading/primary/h2/subtitle/muted/table_header_bg/border/card_bg/card_title`（`_renderer/__init__.py:266-278`） |

### 1.1 document.cover（HTML 暗色照片封面 + PPTD 封面）

| 字段 | 缺省 | 说明 |
|------|------|------|
| `template` | — | 为 `dark-photo` 时 HTML 启用 T1 暗色照片封面（`_renderer/__init__.py:214-215`） |
| `background_image` | `""` | 背景照片（相对 HTML 的路径） |
| `logo_image` | `""` | logo（深底用反白稿）；PPTD 封面 logo 也读此字段（`_pptd_gen.py:741`） |
| `veil` / `veil_opacity` | `#0A1540` / `0.8` | 罩层色与不透明度 |
| `confidential` | `""` | 右上机密标注，空则不显示 |
| `show_author` / `show_date` | `false` | 是否在封面显示作者/日期（PPTD 缺省 `true`，`_pptd_gen.py:245,261`） |
| `date` | 回退顶层 `date` | 封面日期 |

### 1.2 format（DOCX 招标格式，仅 docx-build 消费）

| 字段 | 缺省 | 说明 |
|------|------|------|
| `body_font` | `仿宋_GB2312` | 正文字体（`_renderer/__init__.py:445`） |
| `body_size` | `16` | 正文字号（pt） |
| `line_spacing` | `28` | 固定行距（pt） |
| `first_line_indent` | `2` | 首行缩进字符数 |
| `margin.{top,bottom,left,right}` | — | 页边距（cm） |
| `dark_bid` | `false` | 暗标模式：不写作者/页眉信息（`_renderer/__init__.py:415`） |
| `numbering` / `toc` | — | 任一存在时触发 COM 后处理（需 pywin32，`_renderer/__init__.py:431-438`） |

## 2. 页面（pages[]）字段

```yaml
pages:
  - id: p01            # 页面唯一标识；渲染报告/降级定位用（PPTD 缺省回退 p01/p02…，_pptd_gen.py:929）
    title: "页标题"     # HTML <h2> / DOCX level-1 heading / PPTD 页标题
    composition:       # 可选：构图母板声明（D-122，presentation-content-design 十二种讲法）
      - data_narrative #   枚举见 _renderer/schema.py COMPOSITIONS；多值=组合体写法
    elements: [...]    # 元素数组，见 §3-§5
```

`layout` 字段由 outline-to-spec 写入（`_outline_to_spec.py:304,322`），**协议 v1 三端渲染器均不消费**，仅为生成器参考信息；页面内容完全由 `elements[]` 决定。

`composition`（D-122，2026-08-14）为**讲法声明字段**：渲染器不消费，schema 校验枚举合法性（`_renderer/schema.py: _validate_page_composition`），verify 观察模式机械检查"声明母板 ↔ 页面构件"匹配（`_verify.py: check_composition_fit`，失配仅 [观察] 不阻断）。十二种母板：full_claim / editorial_columns / architecture_board / evidence_ledger / flow_spine / scenario_sequence / data_narrative / product_simulation / timeline_gantt / comparison_matrix / decision_board / capability_graph。

## 3. 元素总览与三端能力矩阵

合法元素共 10 种，`KNOWN_ELEMENT_TYPES` 从 CAPABILITIES 派生（`_renderer/schema.py:61`）。能力矩阵照抄 `_renderer/elements.py:25-40`：

| 元素 type | HTML | DOCX | PPTD | 不支持端降级行为 |
|-----------|:----:|:----:|:----:|------------------|
| `text` | ✅ | ✅ | ✅ | — |
| `bullets` | ✅ | ✅ | ✅ | — |
| `cards` | ✅ | ✅ | ✅ | — |
| `table` | ✅ | ✅ | ✅ | — |
| `phases` | ✅ | ✅ | ✅ | — |
| `pullquote` | ✅ | ✅ | ✅ | — |
| `heading` | ✅ | ✅ | ✅ | — |
| `architecture_4a` | 降级 | ✅ | 降级 | `[4A 架构图] 本节内容请见 Word 版` |
| `diagram` | ✅ | 降级 | ✅ | `[架构图：{title}] 请见 HTML/PPT 版` |
| `product_intro_placeholder` | ✅ | 降级 | ✅ | `[产品介绍占位：{title}]` |

要点：

- **写 spec 时按目标端选元素**：要出 DOCX 的 spec 不要用 `architecture_4a` 以外的图类元素期望出图——`diagram`/`product_intro_placeholder` 在 DOCX 端只有一行降级文本；`architecture_4a` 只在 DOCX 端有原生渲染。
- 降级文本由 `degrade_text` 单点产出（`_renderer/elements.py:169-183`），绝不静默跳过；每次降级进渲染报告（见 §6.4）。

## 4. 逐元素字段表

字段兼容只在 `_renderer/elements.py` 的 normalize 层做（渲染器不再各自兼容）。**新写 spec 一律用正典字段**；兼容字段仅为存量 spec 保留。

### 4.1 text — 段落文本

| 字段 | 正典/兼容 | 说明 |
|------|-----------|------|
| `content` | 正典 ← `content\|text` | 段落内容（`elements.py:57-62`） |
| `role` | 原样带出 | 缺省 `""`；HTML 端 v1 不按 role 区分样式 |

必填规则（`schema.py:141-142`）：`content` 非空。

### 4.2 bullets — 项目符号列表

| 字段 | 说明 |
|------|------|
| `items` | 字符串列表；非 list 归一到空列表（`elements.py:65-67`） |

必填规则（`schema.py:143-145`）：`items` 非空列表。HTML 端用 `div.bullet` 而非 `ul/li`（dom-to-pptx 计高 bug，`_renderer/__init__.py:328-331`）。

### 4.3 cards — 卡片组

| 字段 | 说明 |
|------|------|
| `cards[].title` | 卡片标题 |
| `cards[].body` | 卡片正文 |
| `cards[].tag` | 标签（HTML 端渲染，缺省 `""`） |
| `cards[].highlight` | 高亮行（HTML 端渲染，缺省 `""`） |

normalize 后每卡四键齐全缺省 `""`（`elements.py:70-82`）。必填规则（`schema.py:146-152`）：`cards` 非空列表，且每卡 `title` 非空。注意：DOCX/PPTD 端 v1 只渲染 title/body。

### 4.4 table — 表格

| 字段 | 说明 |
|------|------|
| `headers` | 表头字符串列表 |
| `rows` | 行数组，每行是字符串列表；标量行归一为单格行（`elements.py:85-94`） |

必填规则（`schema.py:153-161`）：`headers` 非空列表；每行列数须与 `headers` 列数齐。

### 4.5 phases — 阶段/路线图

| 字段 | 正典/兼容 | 说明 |
|------|-----------|------|
| `phases[].name` | 正典 ← `name\|label\|phase\|title` | 阶段名（`label` 是 HTML/DOCX 旧写法，`phase`/`title` 是 outline-to-spec 旧写法） |
| `phases[].desc` | 正典 ← `desc\|goal` | 阶段描述（`goal` 是旧写法） |
| `phases[].actions` | 正典 ← `actions\|items` | 行动项列表，缺省 `[]`（`items` 是旧写法） |

兼容只在 normalize 层做（`elements.py:97-118`）。必填规则（`schema.py:162-169`）：`phases` 非空列表，且每阶段 `name` 非空（四个兼容键均取不到即报错）。
端差异：PPTD 端只发 `name`/`desc`，**不发 `actions`**（`_pptd_gen.py:396-398`）——要出 PPT 的 spec 别把关键内容只写进 actions。

### 4.6 pullquote — 引文

| 字段 | 说明 |
|------|------|
| `content` | 引文内容 |
| `cite` | 署名，缺省 `""` |

normalize（`elements.py:121-126`）。必填规则（`schema.py:170-172`）：`content` 非空。DOCX 端为缩进斜体引文 + `—— cite` 署名行（`_renderer/__init__.py:526-535`）。

### 4.7 heading — 元素级标题

| 字段 | 正典/兼容 | 说明 |
|------|-----------|------|
| `text` | 正典 ← `text\|title\|content` | 标题文字 |
| `level` | 缺省 `2`，normalize 钳到 1-7 | 层级（`elements.py:129-138`） |

必填规则（`schema.py:173-184`）：`text` 非空；`level` 若给出须为 1-7 整数（normalize 会静默钳/回退，schema 显式报出）。
端差异：HTML 端在页面 h1/h2 之下整体 +2，元素 level 1 → `<h3>`，level ≥4 → `<h6>`（`_renderer/__init__.py:319-323`）；DOCX 端 `add_heading(level)`；PPTD 端字号 `max(16, 24-(level-1)*2)` 主色粗体（`_pptd_gen.py:347-365`）。

### 4.8 architecture_4a — 4A 架构分层（仅 DOCX 原生）

| 字段 | 说明 |
|------|------|
| `layers[].name` | 层名（如 业务架构 BA） |
| `layers[].components` | 层内组件列表（DOCX 渲染为项目符号） |

无 normalize（原样消费）。必填规则（`schema.py:188-197`）：`layers` 非空列表，每层 `name` 非空。
端差异：DOCX 原生渲染层名加粗 + 组件符号列表（`_renderer/__init__.py:536-546`）；HTML/PPTD 降级为 `[4A 架构图] 本节内容请见 Word 版` 并进 report.degraded（`_renderer/__init__.py:373-377`、`_pptd_gen.py:405-420`）。**建议只用于 DOCX 场景的 spec**；要出 HTML/PPT 的架构图请改用 `diagram`（`architecture/4a` 或 `layered` 子类型）。

### 4.9 diagram — 结构化图形（27 种子类型）

字段详见 §5。DOCX 端降级为 `[架构图：{title}] 请见 HTML/PPT 版`（title 缺省 `未命名`）。

### 4.10 product_intro_placeholder — 产品介绍占位卡

| 字段 | 说明 |
|------|------|
| `title` | 必填（`schema.py:86-89`） |
| `hint` / `keywords` | 占位卡提示信息（渲染管线消费） |

HTML/PPTD 渲染为占位卡（`_renderer.diagram` 管线）；DOCX 端降级为 `[产品介绍占位：{title}]`。

## 5. diagram 元素字段表

通用必填（`schema.py:97-127`）：`diagram_type`、`subtype`、`title` 三者必填；`subtype` 必须属于对应 `diagram_type`；各子类型另有专有必填字段，照抄 `_renderer/schema.py:19-57`（DIAGRAM_SCHEMA）：

| diagram_type | subtype | 专有必填字段 |
|--------------|---------|--------------|
| flow | `sequence` | `steps` |
| flow | `cross_system` | `systems`, `steps` |
| flow | `swimlane` | `lanes`, `steps` |
| flow | `parallel` | `sources`, `merge` |
| flow | `decision` | `steps` |
| architecture | `4a` | `layers` |
| architecture | `layered` | `layers` |
| architecture | `integration` | 双形态：`source`+`target`（点对点）或 `hub`+`systems`（总线），二选一 |
| architecture | `biz_overview` | `domains` |
| architecture | `platform_hub` | `center`, `satellites`（`right` 可选，D-094） |
| architecture | `deployment` | `zones` |
| architecture | `biz_it_mapping` | `mappings` |
| matrix | `fit_gap` | `requirements`, `products`, `cells` |
| matrix | `raci` | `roles`, `tasks` |
| matrix | `crud` | `docs`, `entities`, `cells` |
| matrix | `cbm` | `rows` |
| matrix | `capability_map` | `sections` |
| timeline | `horizontal` | `milestones` |
| timeline | `vertical` | `milestones` |
| timeline | `module_gantt` | `columns`, `groups`（`markers` 可选，D-095） |
| relationship | `er_conceptual` | `entities`, `relations` |
| relationship | `er_logical` | `entities`, `relations` |
| relationship | `data_flow` | `nodes`, `flows` |
| relationship | `org_tree` | `root` |
| relationship | `value_chain` | `primary` |
| relationship | `biz_capability_tree` | `groups` |
| relationship | `process_service_doc_mapping` | `processes`, `services`, `documents`, `mappings` |
| relationship | `cross_4a_reconcile` | `terms` |
| relationship | `automation_table` | `tasks` |

各子类型的字段语义与画法见内部视觉规范文档（不随发布版分发）。写作约定：**一页一图**（PPTD content 页无分页，多张大图溢出页面）。

## 6. 行为规则

### 6.1 confirmed 门禁

- 判定单点：`src/_cli_guards.is_confirmed`（`src/_cli_guards.py:6-13`），全项目 4 处检查点都走这里，不得各自 `spec.get("confirmed")`。
- 未确认：抛 `RenderBlockedError`，生成硬阻断（`src/_cli_guards.py:16-21`）。
- 生成器（spec-gen / outline-to-spec / quote-spec-gen）产出的草稿一律不带 `confirmed: true`，须人工确认后手动添加。

### 6.2 client_name 空值阻断

`client_name` 字段存在但为空 → 抛 `RenderBlockedError`（`_renderer/__init__.py:101-102`）。要么写真名，要么不写该字段。

### 6.3 未知 type：报错 + verify FAIL（v1 行为变更）

历史行为是静默跳过（元素消失、用户无感知）。v1 起：

1. **schema 校验报错**：`未知元素类型 'xxx'（合法值：…）`，合法值列表随 CAPABILITIES 更新（`schema.py:80-84`）；错误进 `report.warnings` 并打印，**不阻断生成**（`_renderer/__init__.py:122-129`）。
2. **渲染端跳过**：三端对未知 type 不产出任何内容，进 `report.skipped`（`_renderer/__init__.py:384-386,552-554`、`_pptd_gen.py:431-433`）。
3. **verify 判 FAIL**：`skipped` 非空即产出不完整，verify 结果强制 FAIL 并列出页面/序号/类型/原因（`_verify_hook.py:175-180`）。

所以拼错的 type（如 `bullet`、`Heading`）与协议外 type（如旧 spec 的 `tree`/`chart`/`actions`）现在都会让 verify FAIL——写 spec 只用 §3 表中的 10 种。

### 6.4 降级行为与降级文本

不支持端输出显式降级文本（`degrade_text`，`_renderer/elements.py:169-183`）：

| 元素 | 降级端 | 产出文本 |
|------|--------|----------|
| `architecture_4a` | HTML、PPTD | `[4A 架构图] 本节内容请见 Word 版` |
| `diagram` | DOCX | `[架构图：{title}] 请见 HTML/PPT 版`（title 缺省 `未命名`） |
| `product_intro_placeholder` | DOCX | `[产品介绍占位：{title}]` |

每次降级进 `report.degraded`；verify 不因此 FAIL，但逐条打印 `[warn] [降级]` 明细（`_verify_hook.py:184-186`）。降级是"告知后的替代"，不是错误——但写 spec 时应按 §3 能力矩阵避免不必要的降级。

### 6.5 schema 校验不阻断生成

`validate_spec` 逐元素返回错误列表（`schema.py:200-207`），渲染器初始化时全部进 `report.warnings` 并打印 `[spec校验] …`，生成继续——非法元素由渲染层按 §6.3/§6.4 路径处理。校验自身异常也不阻断（`_renderer/__init__.py:122-129`）。

### 6.6 outline-to-spec LLM 提取失败

章节提取失败不再静默丢章节：保留该页并放一个 text 占位元素（`（本章节内容提取失败，请重新运行 outline-to-spec 或手动补充）`），同时打印警告（`_outline_to_spec.py:296-308`）。看到占位页意味着需要重跑或手补，不要把占位文本确认进正式 spec。

### 6.7 输出路径白名单

生成产出只能写入项目 `output/` 目录（commonpath 目录级比较，防前缀兄弟目录绕过），否则抛 `OutputPathNotAllowedError`（`src/_renderer/__init__.py`）。

### 6.8 渲染报告（RenderReport）

三端渲染共用 `RenderReport` 收集 `skipped` / `degraded` / `warnings`（`_renderer/elements.py:186-243`），CLI 在生成后打印摘要（`_cli_generate.py:66-67,283-284`），verify 消费语义见 §6.3/§6.4。**任何元素都不会静默消失**——写了的元素要么渲染、要么显式降级、要么进 skipped 让 verify FAIL。

## 7. 版本说明

- **v1（2026-07-20）**：首版协议。随重构 Phase 1 落地：`_renderer/elements.py` 协议层新增（能力矩阵 10 元素 × 3 端、normalize 单点、degrade_text、RenderReport）、`schema.py` 扩展为全量校验（8 种基础元素必填规则 + 未知 type 报错）、三端渲染器接入协议层（HTML 补 heading、DOCX 补 pullquote + diagram/placeholder 降级、PPTD 补 heading + architecture_4a 降级）、verify 消费渲染报告。
- **与重构计划的关系**：本文档源自内部协议重构计划（"为什么改、分几步改"的计划文档不随发布版分发）；本文档是"字段怎么写"的规范性参考，随协议演进持续更新。
- **演进预期**：Phase 2（样式收敛、pptd 溢出防线、elementId 唯一化）不改变本协议的字段层；若新增元素类型或调整能力矩阵，先改 `_renderer/elements.py` 再回修本文并升版本号。
