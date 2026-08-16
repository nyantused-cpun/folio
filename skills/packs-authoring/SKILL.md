---
name: packs-authoring
version: "1.0"
description: 方法论包（Folio Packs）创作指南。当用户想发布方法论包、把 Folio 用于新领域（市场营销/投资分析/战略咨询等）、或问"方法论怎么换"时调用。教用户把一套咨询方法论做成可复用包：结构化问答生成包骨架 + 校验清单。Use when someone wants to publish a domain pack for Folio.
---

# Packs Authoring：方法论包创作指南

Folio 的方法论是可换可组合的包。本 skill 教你从零做一个方法论包（Folio Pack），不需要懂代码——只需要会描述你的方法论。

**一句话**：方法论包 = 大纲（把材料拆成什么章节）× 约束（什么不能写）× 样例（长什么样算对）。

## 何时用

- 用户说"我想做市场营销的方法论包" / "换成投资分析的" / "发布方法论包"；
- 想把一套自己的咨询框架沉淀成可复用资产。

## 包的结构（v0.1 形态，契约 v0.2 冻结）

```
my-pack/
├── domain-pack.yml      # 包声明（manifest，v0.2 起机械校验）
├── outlines/            # 场景大纲（每个场景一个 outline.yml）
│   └── 整体方案/outline.yml
├── skills/              # 本包专属的方法论 skill（可选）
└── samples/             # 1-2 份样例 spec（"长什么样算对"）
```

## 创作流程（脚手架式，一问一答）

按顺序收集信息，每答完一项就落一项到包里：

1. **包名与场景**：这个包服务什么场景？（如"市场营销方案"）→ 建目录 `my-pack/outlines/市场营销方案/`
2. **章节骨架**：一份标准方案由哪些章节组成？（现状 → 目标 → 策略 → 计划 → 预算？）每章回答三个问题：
   - 这章要解决什么问题？
   - 从客户材料里提取什么事实？
   - 什么内容**不该**出现？
3. **大纲文件**：按 `_knowledge/templates/outlines/` 里现有 outline.yml 的格式写（scene/structure/prompt 三件套）。
4. **约束清单**：这个领域的铁律（禁词、必须覆盖的主题、门禁参数）——照 `docs/产品定位与三卖点` §5 边界第 2 条：**包必须携带门禁参数**。
5. **样例**：用公开案例材料跑一遍 spec-gen，把产物放进 `samples/`。
6. **验证清单**（自检，v0.1 人工执行）：
   - [ ] outline.yml 能被 outline-to-spec 读取（`python _cli.py outline-list` 能看到你的场景）
   - [ ] 用样例材料跑通 spec → html-build → 产出可看
   - [ ] 包内没有客户真实数据（脱敏检查）
   - [ ] 文案过 de-ai-style 检查（禁用词/证据边界）

## 发布

- 独立 GitHub 仓库（推荐）或提交到 Folio 仓库的 `skills/` 下；
- README 里写清：解决什么问题、适合谁、怎么装（拷 outline 目录 + 声明）；
- 提交 awesome 列表收录。

## 为什么这样设计

- **门槛**：包 = 数据文件（YAML + 样例），不碰代码——参照 anthropics/skills 的 template-skill 与 DSH 社区 dsh-plugin-development 的元 skill 模式；
- **可验证**：`domain-pack validate`（v0.2）将机械校验包结构；在此之前用上方的验证清单人工兜底；
- **组合**：包之间靠大纲 + 约束组合，机制入内核、内容入包（边界决策第 3 条）。
