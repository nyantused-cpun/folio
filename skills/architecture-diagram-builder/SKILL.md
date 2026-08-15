---
name: architecture-diagram-builder
version: "5.0"
description: "Enterprise-architecture diagram construction methodology. Invoke when user says 架构图/蓝图架构/整体信息化规划/数据架构/应用架构/技术架构/治理架构. Use before outline-to-spec."
---

# Architecture Diagram Builder

> 本文件是目录页，不是百科全书。方法论详情按需读 [reference.md](./reference.md) 对应锚点。

## When to Invoke

**调用**：架构图 / 蓝图架构 / 整体信息化规划 / 数据架构 / 应用架构 / 技术架构 / 治理架构 / 演进路线 / EA 架构管控。
**不调用**：单纯流程图、技术栈图、单页 UI 截图、已有现成架构图只需微调。

**流程-服务映射图**：BA 5.1 task→系统服务推导完成后必须输出此图（MANDATORY），验证映射是否落地。画法见 [reference.md#BA](./reference.md#ba业务架构完整设计步骤) 末尾 5.2 节。

## 解决什么问题

AI 画架构图时常犯的 5 个错，本 skill 用锁定清单 + 逐步跨域检查机制逐个防住：

| # | 常见错误 | 为什么是错 | 本 skill 怎么防 |
|---|---|---|---|
| 1 | 跳过原则直接给步骤 | 没讲清设计准则，图能画出来但无逻辑根基，换需求就不知道怎么调 | 每类架构必须先出 3-6 条原则，才允许给步骤 |
| 2 | 4A 四图各画各的，不查跨域一致性 | 同一业务对象在四张图里叫不同名字，看图的人对不上 | 每步输出锁定清单，下一步必须拿清单逐项比对 |
| 3 | 功能项和 APP 粒度搞反 | 把"OCR 识别"这种小功能当 APP，"收票登记"这种完整业务能力反而当功能项 | 功能识别三轨对照表 + 粒度判断规则（APP=有独立用例；功能项=分配给一个人就结束的任务） |
| 4 | 产品映射藏 Gap 项 | 只标 Fit 让方案看起来好，Gap 不标或标了不说怎么处理 | 每个需求必须标 Fit/Partial/Gap，Gap 项必须说明处理方式 |
| 5 | 治理脱离对账结果新造内容 | 治理章写空泛管控体系，不回答"每条流程谁负责、跑在哪个模块"，和对账表对不上 | 治理矩阵每行必须有 Owner + 支撑模块，且全部来自 cross-domain 对账表（集团级汇报才启用三治×三维） |

方法论基础见 [reference.md#methodology](./reference.md#methodology方法论基础)。

## 场景分流（首次接触先问方向）

| 场景 | 输出形态 | 颗粒度 |
|---|---|---|
| 给老板看的架构蓝图 | HTML 单页 + 4A 总览图 + 演进路线 | L1-L2，重结论轻细节 |
| 内部用的需求清单 | HTML 分域详述 + APP/功能项清单 + 跨域关联表 | L3-L5，重细节可落地 |
| 成品软件销售 | 4A 架构图 + 产品映射三件套（Fit-Gap） | 方法论 + 产品对应 |
| 培训/教学型架构讲解 | 先仿真建直觉（场景穿透）→ 再抽象分层（4A 分层图） | L1-L2，学习动作先行 |
| 平台型客户（中心生态） | 中心生态拓扑图：核心枢纽 + 外围角色 + 接口方向 + 治理环 | L1-L2，重生态关系与接口方向 |
| 集团型客户（多租户） | 多租户治理图：组织层级 + 租户边界 + 数据隔离 | L2-L3，重租户隔离与治理边界 |

## 工具与流程集成（MANDATORY）

本 skill 是本项目的子组件，必须走 CLI 工作流：

| 阶段 | 命令 | 说明 |
|---|---|---|
| 会话开始 | `python _cli.py session-start "<输入>" --client <客户>` | 判层级 + 加载历史 + 主题刷新 |
| 客户铁律 | `python _cli.py theme-guard <客户>` | HEAD 注入客户永久铁律 |
| 读材料 | `python _cli.py read <文件>` / 环境可用的文档读取工具 | 全文读取，禁止凭前 N 字符下结论 |
| 生成 HTML | `python _cli.py html-build <spec> --client <客户>` | spec 须设 confirmed:true，否则阻断 |
| 校验 | `python _cli.py verify <文件>` + `theme-verify <文件> <客户>` | 生成后自动跑，失败必须重做 |
| 会话结束 | `python _cli.py save <客户>` | 写 task_history + 更新 index |

渲染规范（CSS/配色/画法）见 [reference.md#rendering](./reference.md#rendering视觉渲染规范)，按需读取。

## 执行顺序（MANDATORY · 三阶段流程）

> **三阶段**：① 写文档 → ② 合并检查 → ③ 画图
>
> **核心原则**：先完成所有文档内容，确保跨域一致性，最后才生成 HTML 架构图。

```
─── 阶段一：写文档 ───
Step 1: 需求识别 → reference.md#requirements（需求识别步骤）→ 4A 需求清单 + 缺口清单

Step 2: 业务架构文档(BA) → reference.md#BA（业务架构完整设计步骤）
  · 分层原则 + APQC L1 参照见 reference.md#methodology
  · 5.1 task→系统服务推导 → 5.2 流程-服务-单据映射 → 5.3 自动化提升清单
  → 🔒 锁定 BA 文档 → 用户确认 → 才进 Step 3

Step 3: 数据架构文档(DA) → reference.md#DA（数据架构完整设计步骤）→ 5 层资产目录 + 概念模型
  → 🔒 锁定 DA 文档 → 跨域检查 BA→DA → 用户确认 → 才进 Step 4

Step 4: 应用架构文档(AA) → reference.md#AA（应用架构完整设计步骤）→ 6 层应用架构
  · 功能识别方法论见 reference.md#function-identification（AA 子步骤：粒度判断 + 三轨对照）
  → 🔒 锁定 AA 文档 → 跨域检查 BA→AA + DA→AA → 用户确认 → 才进 Step 5

Step 5: 技术架构文档(TA) → reference.md#TA（技术架构完整设计步骤）→ 三横两纵 + 部署架构
  → 🔒 锁定 TA 文档 → 跨域检查 AA→TA → 用户确认 → 才进 Step 6

Step 6: 治理 + 演进文档（可选 · 需人决策 · AI 只出草稿）→ reference.md#governance（责任矩阵 + 演进路线）→ 治理演进草稿供人决策

Step 7: 产品映射文档(如有) → reference.md#product-mapping（产品映射三件套）→ 三件套

─── 阶段二：合并检查 ───
Step 8: 场景穿透验证（D-6 · 外部有效性）→ reference.md#scenario-walkthrough（场景穿透验证）→ 穿透表
  选 3-5 个关键业务场景沿 4A 各层端到端穿透，查断点/错位——证明架构能跑通业务，不只内部自洽
  → 🔒 穿透表通过 → 才进 Step 9

Step 9: 跨域总检查（全局自洽 · 与逐步检查不重复）→ reference.md#cross-domain（4A 关联规则）→ 全链路关联表 + 自洽核对
  查逐步检查查不出的：传递一致性、范围闭合、遗漏发现、术语漂移
  → 🔒 所有文档通过检查 → 才进阶段三

Step 10: 校验清单 → reference.md#checklist（校验清单）
  → 🔒 所有校验项通过 → 才进阶段三

─── 阶段三：画图 ───
Step 11: 生成 HTML 架构图
  · 读取 [styles.md](./styles.md) 获取视觉渲染规范（CSS 类、组件库、配色方案）
  · 根据已确认的文档内容，生成对应的 HTML 架构图
  · 每个 EXHIBIT 必须有对应的文档内容支撑
  · 禁止在画图阶段修改文档内容（如需修改，回到阶段一）
```

**关键约束**：
- 阶段一完成前，不生成任何 HTML 架构图
- 阶段二未通过，不进入阶段三
- 阶段三发现文档问题，必须回到阶段一修改，不能直接在 HTML 中改

**关键规则**：
1. 做哪一步就读 reference.md 对应章节，不一次性读整个文件。
2. 禁止并行生成 BA/DA/AA/TA。
3. **锁定机制（🔒）**：每步完成后输出锁定清单，等用户确认才能进下一步。格式与跨域检查规则见 [reference.md#execution-flow](./reference.md#execution-flow执行流与锁定机制)。作用域：仅当前会话有效，跨会话续作需重新确认。
4. 逐步跨域检查，不是最后才检查。

## 组合体写法（图是组合体，不是单件）

架构图不从孤立一张图出发，而是「架构板 + 配套组件」的组合体。三种高频组合：

| 组合 | 架构板 | 配套组件 | 解决什么 |
|---|---|---|---|
| 架构板 + 证据台账 | 分层架构图 | `evidence_ledger`（B-3） | 每个设计决策挂依据编号，答辩"依据是什么"可追溯 |
| 架构板 + 责任矩阵 | 分层/治理架构图 | `raci_matrix`（B-5） | 治理架构强制配对，每条流程谁负责、跑在哪个模块 |
| 演进路线 + 里程碑甘特 | 演进路线图 | `milestone_gantt`（B-7） | 替换 ≤4 里程碑弱 timeline，任务轨×依赖按周铺 |

**架构证据链（D-6 · 设计决策挂证据编号）**：每个设计决策挂证据编号（`EV-<序号>`），来源 = 客户需求条目 / 材料出处。答辩「依据是什么」时凭编号现场翻 `evidence_ledger`（B-3）台账，不靠回忆。证据编号在架构文档里与 B-3 台账的 `num` 一一对应——图上标注编号，台账列证据全文，形成「图 → 编号 → 证据」的可追溯链。

**每图附件四槽位**（图不孤立，必有配套文字）：

| 槽位 | 内容 |
|---|---|
| 结论 | 一句话：这张图要让人带走什么判断 |
| 图例 | 颜色/线型/符号的语义（三态、角色色、箭头方向） |
| 来源 | 依据（材料出处 / 证据编号 / 对账表章节） |
| 行动 | 下一步 / 待确认项 / 责任人 |

**嵌入叙事 skill 的服从关系**：架构图作为页面组件嵌入方案时，服从 `presentation-content-design` 的 container（容器定读法）与密度决策——先定容器再选图，不孤立画图。示例：container=stage（汇报现场）时架构图一页一屏、结论先行；container=chapters（长方案）时架构图配证据台账、可展开查依据。

**页面 composition 声明（D-122，2026-08-14）**：架构图页在 spec 里声明 `composition: [architecture_board]`（或组合体如 `[architecture_board, evidence_ledger]`），verify 机械检查该页确有 architecture 类 diagram；渲染前 schema 校验枚举。示例：

```yaml
# 单图主张页（stage 容器，一页一屏）
pages:
  - id: arch_overview
    title: "整体架构总图"
    composition: [architecture_board]
    elements:
      - type: diagram
        diagram_type: architecture
        subtype: 4a          # 或 layered / platform_hub / deployment
        # 每图附件四槽位：结论/图例/来源/行动 一并提供

# 架构板 + 证据台账组合体（chapters 容器，可展开查依据）
pages:
  - id: arch_with_evidence
    title: "架构与依据"
    composition: [architecture_board, evidence_ledger]
    elements:
      - type: diagram
        diagram_type: architecture
        subtype: layered
      - type: evidence_ledger
        items:
          - {num: "E-01", claim: "...", status: "已核对"}
```

**4A 及格线**（review 第 5 维机械复验）：真实实体 + 边界 + 接口 + 流向——四要素缺一即不达结构完整度。

## 输出落地

- 方案：`output/{客户}/{客户}_架构蓝图_v{N}.html`
- 产品映射：`output/{客户}/{客户}_{产品名}_产品映射_v{N}.html`
- 先 HTML → 用户确认 → 再 PPT

## 术语表

| 缩写 | 含义 |
|---|---|
| AD/AG/APP | 应用域/组/一级模块 |
| ABB | APQC L4 活动的系统化（需要流程 owner 协调多人的协作单元） |
| CBM | IBM 组件化业务模型 |
| APQC PCF | 流程分类框架 |
| TOGAF ADM | The Open Group Architecture Framework - Architecture Development Method |
| ArchiMate | 企业架构建模语言（三层：业务/应用/技术） |
| SOR/SOI | 稳态 IT/敏态 IT |
| RACI | 主责/决策/咨询/知情 |
