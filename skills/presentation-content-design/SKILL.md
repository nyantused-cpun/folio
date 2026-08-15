---
name: presentation-content-design
version: "1.1"
description: "汇报材料表达设计方法论：容器→组件→构图→仿真五步工序，输出'每页讲法'的内容设计。作为 outline-to-spec / spec-gen 的推荐前置（按需，非强制）。当用户说做方案/做汇报/生成 HTML/做 PPT（信息化咨询/汇报材料）时调用。Use before outline-to-spec and spec-gen. v1.1: 定位调整——五步工序从强制锁降为推荐方法论，验收端已由 review 第 5 维 + verify 密度检查机械化兜底（2026 检索校准：模型可自行推理的通用方法论不设过程锁）。"
---

# Presentation Content Design

> 本文件是目录页，不是百科全书。方法论详情按需读 [reference.md](./reference.md) 对应锚点。

## When to Invoke

**调用**：做方案 / 做汇报 / 生成 HTML / 做 PPT / 出信息化咨询/汇报材料，且内容需要从客户材料重新组织（非微调已有产出）。
**不调用**：架构图专项（走 `architecture-diagram-builder`）；编辑已有产出物；纯检索/读文件；工程类 HTML。

**定位**：本 skill 是 `outline-to-spec` / `spec-gen` 的**推荐前置**（按需，非强制锁）。它提供"每页怎么讲"的选型方法，spec 只是内容设计的落地格式。模型可自行组织内容时不必走完整工序；**查表价值 > 流程价值**——容器/组件/版式映射是项目特定知识，模型推理不出来。

## 解决什么问题

我们的链路是「材料 → spec-gen 一步映射 → 渲染 → verify」，中间缺一个显式的**内容设计**环节——先想每页怎么讲、内容是什么关系，再落 spec 字段。目前这一步全凭 AI 临场发挥。

排版问题的根源大多不是渲染器画错，而是**讲法选错**：该用对比矩阵的用了卡片墙，该用证据台账的用了大段文字。渲染层（`ui-design-system`）只能约束"壳"的规范，约束不了"这页该用什么讲法"——那是本 skill 的职责。

## 执行顺序（推荐工序 · 五步）

> 验收端已机械化（review 第 5 维 + verify 反同壳/密度，2026-08-13），过程端不设锁。模型可自行组织内容时按需走完整工序；复杂/陌生场景建议走完。每步有输出物，做哪步读 reference.md 对应章节，不一次性读整个文件。

```
Step 1: 容器定读法 → 给谁看、什么阅读行为 → 选定容器
        读 reference.md#containers（容器 A-D + 局部布局 E-K）
        输出：container 决策 + 理由（一句话）

Step 2: 组件定细节 → 逐页问"这段内容是什么关系" → 选定组件
        读 reference.md#components（组件库 + 缺口组件降级方案）
        输出：每页组件清单（页 → 组件 → 承担的信息关系）

Step 3: 仿真建直觉 → 能画的不用文字，能点的不贴截图
        读 reference.md#simulation（Static / Interactive / Guided Demo + 反馈选型表）
        输出：每页仿真级别（Static / Interactive / Guided Demo / 无）

Step 4: 模板定版式 → 构图母板决定信息在页面上的组织逻辑
        读 reference.md#composition（12 种母板 + 组合体写法）
        复杂页面读 reference.md#template-families（十大配方卡）
        输出：每页构图母板 + 与 P01-P16 版式的映射
        **落 spec**：页面声明 `composition` 字段（D-122，枚举见下方速查表，
        多值=组合体）；verify 会在渲染前机械检查"声明母板 ↔ 页面构件"匹配

Step 5: 质量门验收 → 对照验收清单逐条过
        读 reference.md#quality-gate（反退化清单 + 及格线 + 八项检查）
        输出：验收结果（review 第 5 维 / verify 密度检查会在渲染后机械化复验）
```

**关键约束**：
- Step 1-5 是顺序工序（推荐按序）；做哪一步读 reference.md 对应章节。
- 内容设计是否走完整工序由模型按任务复杂度判断（新材料重组的复杂方案推荐走；微调/模板化生成可不走）。
- spec 生成后发现讲法问题，回到 Step 2-4 改内容设计，不直接在 spec 上补丁。

## 构图母板速查（Step 4 落 spec 用，D-122）

`composition` 字段枚举（完整语义读 reference.md#composition）：

| 枚举值 | 母板 | 页面应有构件（verify 机械提示依据） |
|---|---|---|
| `full_claim` | 全幅主张 | hero / action_title 大标题 |
| `editorial_columns` | 编辑式分栏 | info_cards / pullquote / view_cards |
| `architecture_board` | 架构板 | diagram architecture 类（4a/layered/integration/deployment/platform_hub…） |
| `evidence_ledger` | 证据台账 | evidence_ledger / info_cards |
| `flow_spine` | 流程脊柱 | diagram flow 类（swimlane/cross_system/parallel…） |
| `scenario_sequence` | 场景序列 | 多段 section_tag + action_title |
| `data_narrative` | 数据叙事 | stat_cards / kpi_cards / table |
| `product_simulation` | 仿真产品 | simulation 组件 |
| `timeline_gantt` | 时间线甘特 | diagram timeline 类（module_gantt/milestone_gantt） |
| `comparison_matrix` | 对比矩阵 | table / fit_gap / cbm / raci |
| `decision_board` | 决策板 | callout_block / 决策类图 |
| `capability_graph` | 能力图谱 | capability_map / platform_hub |

## 三个选型原则

1. **容器看阅读行为**——读者是逐屏滚动、按章节跳读、还是被演示带着走
2. **组件看内容关系**——这段内容是举证、分工、风险、计划还是决策，而不是"哪个壳好看"
3. **模板看信息关系**——页面信息的主次/对比/时序关系决定构图母板，不是随机排

**反堆砌纪律**：一页里每个区域必须承担明确角色（主判断 / 主关系 / 辅助证据 / 例证 / 来源 / 行动），不为显得丰富而堆组件。

## 风格方向（定材料气质时）

八类风格 = 八套叙事语言（构图重心 + 字阶 + 空间节奏 + 图示语言 + 控件语言五样一起动），读 [reference.md#styles](./reference.md#styles-八类风格方向八套叙事语言不是八件衣服)。与我们 4 style + 4 theme（配色字体包）是补充关系，落地映射待决策。

## 质量门速查（Step 5 验收）

> 已下沉：以下规则已机械化为 review 第 5 维 + verify 反同壳/密度检查（观察模式，2026-08-13）。完整规则读 reference.md#quality-gate。

- [ ] 每页有明确结论：判断 + 解释 + 例证，不能只有标题
- [ ] 数据带口径和来源：单位、周期、业务语境、变化原因缺一不可
- [ ] 无空洞结论："提升效率""加强协同"这类没有对象和数字的套话
- [ ] 连续页面换壳：禁止同一套卡片/分栏从头用到尾
- [ ] 密度受控：无溢出/裁切、无无意义大空白（容量预算预防 + 渲染后兜底）
- [ ] 每个 EXHIBIT 有材料或内容设计支撑（防幻觉铁律不变）

## 与现有 Skill 的边界

| Skill | 管什么 | 与本 skill 的关系 |
|---|---|---|
| 本 skill | **怎么讲**（容器/组件/构图/仿真 → 内容设计） | spec 生成前的默认前置 |
| `architecture-diagram-builder` | 架构图单一物种的表达方法论 | 平行 skill；页面含架构图时其页面设计服从本 skill 的内容设计 |
| `spec-writing-guide` | spec 字段怎么写 | 本 skill 的下游：内容设计落定后按它写字段 |
| `ui-design-system` | 渲染器吃什么（版式/theme/容量预算） | 本 skill 的下游：壳的规范，不管讲法 |
| `delivery-pipeline` | 交付顺序（HTML 先行→确认→PPT） | 编排层：本 skill 是其 Step 3（spec 生成）之前的可选前置 |
| `de-ai-style` | 文案去 AI 味 | 正交：文案层面，任何生成都适用 |

## 工具与流程集成

| 阶段 | 动作 |
|---|---|
| 内容设计 | 五步工序 → 输出内容设计（对话内呈现，不落 spec） |
| 设计确认 | 复杂方案建议用户过目内容设计（spec 确认门强制，内容设计确认按需） |
| spec 生成 | `python _cli.py spec-gen <材料> --client <客户> --output <spec.yml>`（按内容设计填充） |
| 渲染校验 | `html-build` → `verify` / `review`（质量门规则的机械检查端） |
| 会话结束 | `python _cli.py save <客户>` |

## 已定项（2026-08-13 拍板，B-1 七条全按推荐）

| # | 项 | 定论 |
|---|---|---|
| 1 | container 字段 | ✅ scroll/chapters/stage/report，默认 scroll |
| 2 | 第一批 5 组件 | ✅ 证据台账/风险登记/RACI/决策板/甘特（B-3~B-7） |
| 3 | 质量门下沉 | ✅ review 第 5 维 + verify 反同壳/密度（观察模式） |
| 4 | 仿真组件 | ⏸️ 挂起，预留 simulation 字段（B-8） |
| 5 | scenario:training | ✅ 加 |
| 6 | 接入门禁 | ✅ 已进生成前必读 skill 清单 |
| 7 | 沉淀纪律 | ✅ 见 #extension-discipline |

## container 四值选型（Step 1 容器定读法）

| container | 阅读行为 | 适用 | 推荐版式 | 禁忌 |
|---|---|---|---|---|
| scroll | 单长页逐屏滚动 | 单页方案、高管速览 | P01/P03/P04/P08/P11 | P02 章节页、P12 目录页 |
| chapters | 按目录跳读 | 长方案、需求分析 | P02/P12 + P03~P10 | 无（最灵活） |
| stage | 一页一屏翻页演示 | 宣讲、汇报现场 | P01~P11 + P16 | 长滚动叙事 |
| report | 文档式线性深读 | 研究报告、白皮书 | P03/P07/P09/P10 + 文字元素 | P05/P06 大图为主 |

> 完整版式映射见 reference.md#containers。

## training scenario 触发条件

`scenario: training` 用于培训/教学型材料（ZSW 学习工作坊 C 风格）。触发：内容目标是「教会概念/流程/操作」而非「汇报结论」。页面骨架 = 学习动作先行（目标→例题→练习→反馈→迁移），密度中偏低。风格卡见 reference.md#training。

## 沉淀纪律

新行业/新客户只沉淀：对象、术语、角色、证据、字段、常见问题。不沉淀：固定配色、页面数量、卡片布局。详见 reference.md#extension-discipline。
