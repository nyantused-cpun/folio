# 兰亭（Folio）· 咨询/汇报材料生成引擎

> **材料生成引擎 + 可组合方法论包，首发深度适配 DSH。**
> Folio = 对开本/作品集：把客户扔进来的材料，装订成能送达的汇报材料。

Folio 是给 AI 宿主（DeepSeek Harness / Trae / Kimi 等）外挂的**长程任务执行引擎**，特化于一件事：从客户材料到咨询/汇报交付物的全链路——接入材料 → 建立记忆 → 应用方法论 → 生成产出 → 守住质量。

**引擎做机械的，AI 做判断的，云端模型做按需补位的。** 凡是「错了要重来、客户可见、可复现」的环节全部由确定性代码执行，模型只在判断、理解、生成语言处出手。

---

## 快速开始（≤5 分钟）

```powershell
# 1. 获取
git clone <repo-url> folio
cd folio

# 2. 一条命令安装内核（建 venv + 装依赖 + 生成配置 + 自检）
.\setup\install.ps1

# 3. DSH 插件层（可选但推荐）：15 个原生工具 + 会话协议事件 + agent preset + L0 守卫
.\setup\install-folio-plugins.ps1 -Install

# 4. 看自检结果
#    输出示例：✅ Python 3.12  ✅ 依赖齐全  ⚠️ PPT 转换工具链未装（HTML/DOCX 不受影响）
#              当前能力等级 L0：零 key 可跑（DSH 下读图/搜索/审查走宿主原生）
```

装完后：重启 DSH → 开新会话 → 直接说「帮我做一份 XX 方案」。引擎的 skills 会被 DSH 自动识别。

**零配置起步**：不配任何 key 也能跑（L0）；配 1 个 embedding key 解锁语义召回（L1）；配读图/搜索 key 解锁独立 CLI 场景（L2）。每个能力槽位的取舍见 [docs/能力配置引导](docs/能力配置引导_v1_2026-08-15.md)。

## 能力等级（装多少用多少）

| 等级 | 配置 | 得到什么 |
|---|---|---|
| L0 | 无 | 切片 + BM25 + 生成渲染 + 质量门禁；DSH 下读图/搜索/独立审查走宿主原生 |
| L1 | +1 个 embedding key | 语义召回（"那个做化工的客户"→ 找到对应档案） |
| L2 | +读图/搜索 key | 独立 CLI 场景全量（非 DSH 宿主） |

## PPT 转换工具链（v0.1 说明）

HTML / DOCX / 报价三种格式零外部依赖，装完即用。**PPT 转换**依赖 node 工具链（HTML→PPTX 转换器）：install 脚本会检测 node，缺失时标黄提示但不阻断安装——其余功能不受影响。工具链本身随 v0.2 发布（vendor 或 npm 分发），v0.1 期间 PPT 由 `html-build` 同源生成 `.pptd` 工程，转换步骤见 install 输出提示。

## 产品结构：五段价值链

| # | 模块 | 做什么 |
|---|---|---|
| 1 | 接入材料（Intake） | 把客户扔进来的材料变成可检索的资产（建档·解析·切片·索引） |
| 2 | 建立记忆（Chronicle） | 跨会话记住项目事实与决策（决策记录·世界书·语义召回） |
| 3 | 应用方法论（Craft） | 按可替换的方法论框架把材料拆成事实（skill 路由·大纲·主题守卫） |
| 4 | 生成产出（Press） | 从事实渲染成四格式交付物（HTML/PPTX/DOCX/报价，同源） |
| 5 | 守住质量（Proof） | 机械检查 + 独立审查双层防幻觉（门禁·verify·review·引用审计） |

## 三大卖点

1. **深度适配 DSH**：skill 原生识别 + 守卫插件 + 15 个原生工具 + 会话协议事件插件 + agent preset，两条命令装齐；
2. **方法论可换可组合**：换领域不换引擎——咨询/市场营销/投资分析的方法论以 Folio Packs 形式即插即换（楷书=轻包 / 行书=标准包 / 草书=重包），欢迎社区发布；
3. **极致特化的长程任务**：20 页材料进，四格式带质量门自动出，会话结束自动存档审计。

## 目录结构

```
folio/
├── src/          # 内核（63 个 CLI 命令 + 渲染器 + 检索/记忆/质量链）
├── skills/       # 11 个方法论 skill（含 packs-authoring 创作指南）
├── guard/        # 历史独立守卫插件（已并入 plugins/folio-tools 的 @nyantused/folio-dsh-tools/guard 子入口，保留作参考）
├── plugins/      # DSH 插件层：folio-tools（15 个原生工具）+ folio-events（会话协议，preset 挂载）
├── preset/       # 兰亭 agent preset 模板（install-folio-plugins.ps1 安装时落盘/替换占位符）
├── setup/        # 一键安装脚本（install.ps1 内核 + install-folio-plugins.ps1 插件层）
├── docs/         # 定位 / 能力引导 / usage 快速上手教程
└── tests/        # 测试套件（63 个文件；基线含客户材料已裁，见下）
```

## 测试

```powershell
.venv\Scripts\python.exe -m pytest tests
```

> 说明：原始测试基线（golden specs）含真实客户材料，发布版已裁剪；渲染回归测试可自行用虚构材料重建基线（`tests/baseline_kit.py` 的思路，见仓库历史）。

## 快速上手

30 分钟跑通第一份方案：见 [docs/usage.md](docs/usage.md)（虚构客户全流程教程，零 key）。

## 文档

- [产品说明 v4.0（DSH 原生版）](docs/兰亭_产品说明_v4.0.md)：它是什么、怎么装、为什么选 DSH——15 个原生工具 + 会话协议自动执行 + 换方法论不换引擎
- [技术白皮书 v4.0（DSH 原生版）](docs/兰亭_技术白皮书_v4.0.md)：工具管线、事件机制、记忆双轨、已知限制如实说
- [产品定位与三卖点](docs/产品定位与三卖点_2026-08-15.md)：定位纲领、五段价值链、命名族
- [能力配置引导](docs/能力配置引导_v1_2026-08-15.md)：6 个能力槽位怎么配、不配会怎样、外部怎么补位

## 方法论包（Folio Packs）

想给 Folio 换一套方法论（市场营销/投资分析/战略咨询）？`skills/packs-authoring` 就是教你创作的 skill——问答式生成包骨架，不需要写代码。欢迎发布你的方法论包。

## 社区生态 / 友情链接（持续维护）

Folio 聚焦「长程材料生成」，不重复造社区已经做好的轮子。以下社区项目可作为互补、对照或迁移入口；具体兼容性请以各仓库 README 与 [awesome-dsh-plugins](https://github.com/AdamPlatin123/awesome-dsh-plugins) 的 L0-L4 兼容报告为准。

- **Awesome 目录**
  - [AdamPlatin123/awesome-dsh-plugins](https://github.com/AdamPlatin123/awesome-dsh-plugins) — 全量雷达 + 每日兼容性追踪
  - [dsh-external](https://github.com/dsh-external) — 社区插件 org
- **已在兰亭路线中**
  - [DSH-better-sidebar](https://github.com/omdsh-dev/DSH-better-sidebar) — 右侧预览 / 迷你 IDE 工作台
  - dsh-at-file — 输入框 `@文件` 快捷引用（见 awesome 目录）
  - [dsh-vision-toolkit](https://raw.githubusercontent.com/Anionex/dsh-vision-toolkit/main/README.zh.md) — 社区读图全家桶，可作 vision-bridge 对照
- **互补增强（优先补全）**
  - [DSH-better-sidebar](https://github.com/omdsh-dev/DSH-better-sidebar) — 右侧预览区 / 迷你 IDE 工作台（P0）
    - dsh-github-connector — GitHub 集成（P0，见 awesome 目录）
    - context-vista — Token 可视化（P0，见 awesome 目录）
    - dsh-agent-teams — 团队可视化 / 多 Agent 面板（P0，见 awesome 目录）
    - dsh-undo / dsh-record-replay / dsh-obsidian-export / dsh-share（P1 按需）
- **参考 / 对照**
  - ~~dsh-plugin-claude-bridge / dsh-claude-move~~（Claude 生态适配暂不考虑）
  - dsh-memory-evolve（长期记忆设计参考）
  - ModLens / dsh-qwen-mm（社区读图方案参考）

> 详细对比见 [docs/社区插件排查与兰亭友情链接建议_2026-08-15.md](docs/社区插件排查与兰亭友情链接建议_2026-08-15.md)。

P0 社区插件（右侧预览 / GitHub / Token / 团队）脚本已提供，但 **2026-08-15 起暂缓启用（装而未挂）**：peer 依赖在 profile node_modules 缺失或双副本会引发 `dsh-scope Symbol` 分裂，官方 plugin 通道稳定后再开启。当前不要直接跑 `-Install`，可先 `-DryRun` / `-Verify` 看计划：

```powershell
pwsh .\setup\install-community-plugins.ps1 -DryRun
pwsh .\setup\install-community-plugins.ps1 -Verify
```

脚本会从 awesome-dsh-plugins 自动解析仓库、clone 到 `~/.dsh/community-plugins/`、建 Junction 并写 patch，最后重启 `dsh web` 生效。

## 兼容性与生态取舍

> 2026-08-15 对外口径：让使用者一眼知道 Folio 与 DSH 版本的绑定关系、社区插件为什么没直接引入、平台现状。

### 1. 版本对齐

- 当前对齐 **DSH 0.1.0-rc.6**（本机 `dsh -V` 实测）；插件 peer 依赖为 `@deepseek-ai/dsh-agent ^0.1.0-rc.6`、`@deepseek-ai/dsh-tools ^0.1.0-rc.6`、`@deepseek-ai/cordis ^4.0.1`。
- 所有接口按 rc.6 源码逐行核实；DSH 升级后请重跑插件验证（`setup/install-folio-plugins.ps1 -Verify`）。

### 2. 社区插件：看了什么、为什么没直接装

我们调研过 DSH 社区约 200+ 插件，最终没有直接引入，原因分三类：

| 类别 | 代表插件 | 结论 |
|---|---|---|
| 能力重叠 | dsh-memory-evolve、ModLens / dsh-vision-toolkit / dsh-qwen-mm、dsh-my-rsi | 兰亭已有自研实现（记忆/召回、vision-bridge、guard），只作参考，不替换 |
| 兼容风险 | DSH-better-sidebar、dsh-github-connector、context-vista、dsh-agent-teams | P0 想用，但暂缓启用（装而未挂）：peer 依赖双副本/Symbol 分裂，官方 plugin 通道稳定前不启用 |
| 方向排除 | dsh-plugin-claude-bridge / dsh-claude-move | Claude 生态适配暂不考虑 |

- 我们**借鉴了社区 `defineTool` 封装模式**，但 15 个 `folio_*` 工具全部自研；
- 分发基建（marisa / dsh-hub / dsh-plugin-radar）作为参考，官方无统一方案前不引入。

### 3. 极简模式与平台

- 兰亭 preset 设计上对齐 DSH 官方 **minimal 蓝本**（不挂 code 工具、无冗余，塑造专用平台体验）；
- 实际基线采用 **standard 模板 + 精选工具**（禁用 codex/claude 等），原因是官方 minimal 在 Windows 上存在 PTY 兼容问题（`terminal inspection is unsupported on platform win32`）——这是对 Windows 的兼容性修正，不是偏离方向；
- 当前 **首发 Windows**；macOS/Linux 安装脚本（install.sh）在 v1.1 路线中。

### 4. Linux / macOS 适配

目前 Folio 面向 Windows 首发。**欢迎其他开发者贡献 macOS/Linux 的安装脚本与环境适配**；如果官方 DSH 工具链在跨平台上更成熟，我们也乐意等官方完善后跟进。

## 状态与路线

- **v1.0.0（当前）**：首个正式发布——五段价值链全链路 + DSH 深度适配 + LLM host 模式（0 key 起步）+ 安装脚本/自检。变更见 [CHANGELOG.md](CHANGELOG.md)。
- **v1.1 优先补全（开源后第一波）**
  1. 右侧预览区：接入 DSH-better-sidebar（或自研 folio-preview 兜底）
  2. GitHub 集成：`dsh-github-connector` 或自研 `folio_github` 工具
  3. Token 可视化：`context-vista` 或自研会话 Token 面板
  4. 团队可视化：`dsh-agent-teams` 或基于 DSH subagent 事件的自研面板
- **v1.1 其余规划**：`domain-pack.yml` 方法论包契约（机械校验）+ 市场营销冒烟包 + PPT 工具链正式分发
  - 实施细节见 [docs/兰亭P0插件补全计划_2026-08-15.md](docs/兰亭P0插件补全计划_2026-08-15.md)
- 平台：Windows 首发（macOS/Linux 安装脚本待补，欢迎社区贡献 install.sh / 环境适配；或等待官方工具链更成熟后跟进）；PPT 转换工具链要求见安装脚本输出

## 许可证

MIT · 中文名「兰亭」取自《兰亭集序》——材料亦可成章。
