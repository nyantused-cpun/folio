# Release Notes · Folio (兰亭) v1.0.2

**Folio（兰亭）— a document-generation engine for consultants, built natively for DSH.**

Folio turns client materials into deliverable consulting documents through a five-stage pipeline: intake (archive, parse, chunk, index), chronicle (per-client memory with decision records and knowledge graphs), craft (swappable methodology packs), press (HTML / PPTX / DOCX / quote generated from one source of truth), and proof (mechanical gates, independent review, citation audit).

It ships as a native DeepSeek Harness plugin stack: 15 first-party tools (`folio_*`) with schema-validated parameters, a session-protocol event plugin (auto session-start reminders, auto-save on session close), an L0 guard plugin that blocks direct writes to deliverable paths and non-CLI Python calls, and a custom agent preset ("兰亭 mode") with a swappable persona. The engine kernel stays host-agnostic — the same CLI works in Trae and Kimi — while the DSH layer is pure official extension points, zero forks.

Methodology is replaceable without touching code: Folio Packs (light / standard / deep) are YAML + SKILL.md, so switching domains means swapping a pack, not rewriting the engine. Zero API keys to start under DSH — reading images, web search, and independent review ride the host's native capabilities (`LLM_MODE=host`).

---

> **材料生成引擎 + 可组合方法论包，首发深度适配 DSH。**
> Folio = 对开本/作品集：把客户扔进来的材料，装订成能送达的汇报材料。

Folio 是给 AI 宿主（DeepSeek Harness / Trae / Kimi 等）外挂的**长程任务执行引擎**，特化于一件事：从客户材料到咨询/汇报交付物的全链路——接入材料 → 建立记忆 → 应用方法论 → 生成产出 → 守住质量。

**引擎做机械的，AI 做判断的，云端模型做按需补位的。** 凡是「错了要重来、客户可见、可复现」的环节全部由确定性代码执行，模型只在判断、理解、生成语言处出手。

## v1.0.2（2026-08-16）社区友好与双语示例

- CI 流水线（pytest + 插件 JS 自检）；Issue feature_request 模板 + PR 模板标准位；
- `requirements-dev.txt`；文档 clone 地址替换为真实仓库；CONTRIBUTING 分支口径修正；
- 运行时目录去宿主化：`.trae` → `.folio`；skills 自动挂载（skills-sync）；
- 中英双语示例产出（HTML + PPTX）与英文产品说明；README 环境要求清单。

## v1.0.1（2026-08-16）更新

- guard 作用域隔离 + 并入 `@nyantused/folio-dsh-tools`（1.1.0，`/guard` 子入口，profile 层挂载）；
- `@folio/dsh-*` 包名迁移为 `@nyantused/folio-dsh-*`；agent preset 入仓；
- 发布版路径契约统一为「仓库根 = 用户工作区」：根级 `_cli.py` 转发入口、`.env`/output/inbox/_knowledge 锚根、skills 双布局兼容。

## v1.0.0（2026-08-15）首个正式发布

内核经多年内部实战迭代（63 个 CLI 命令、1000+ 测试用例），本次以兰亭（Folio）品牌开源。

### 五段价值链

| 模块 | 做什么 |
|---|---|
| 接入材料（Intake） | 客户建档、inbox 归档、招标/PDF/PPT 解析、切片与双路索引（BM25 + 可选语义索引） |
| 建立记忆（Chronicle） | 决策记录、客户档案、世界书知识图、语义召回（零配置降级纯 BM25） |
| 应用方法论（Craft） | skill 路由 + 场景大纲 + 主题守卫 + 去 AI 化；方法论可换可组合（Folio Packs） |
| 生成产出（Press） | spec 协议 → HTML / PPTX / DOCX / 报价同源双输出；33 种图形、16 种版式 |
| 守住质量（Proof） | confirmed 门禁、verify、独立审查（review/adversarial）、引用审计、美学/讲法观察 |

### DSH 深度适配（P1 插件层随本版发布）

- **15 个原生工具**（`@nyantused/folio-dsh-tools`）：记忆面 9 + 质量面 6，defineTool 注册、参数 schema 校验、结构化返回
- **会话协议事件插件**（`@nyantused/folio-dsh-events`）：新会话自动提醒入口协议、工具调用提取客户名、会话关闭自动保存档案
- **L0 守卫**（随 `@nyantused/folio-dsh-tools` 1.1.0 分发，`/guard` 子入口挂 profile 层）：拦产出物直写、拦非 CLI python 直调、补 shell 直写检测
- **agent preset**：兰亭模式（persona + 五段 SOP + 精选工具）
- **LLM_MODE=host**：DSH 下 5 个 LLM 命令不依赖云端 key，推理交由宿主 AI 执行；读图/搜索/独立审查由宿主原生覆盖——**零 key 起步**

### 质量与安全

- 防幻觉防线：生成前门禁 + 生成后 verify + 独立审查 + 会话审计
- 去 AI 化机械检查（禁词库、证据边界、语感样本）
- 全库脱敏：发布版不含任何客户数据；测试基线已裁剪

### 已知限制（v1.0）

- 首发平台 Windows；macOS/Linux 安装脚本待补
- PPT 转换为自研 python-pptx 后端（不依赖 node）；`--shots` 截图目检需本机 PowerPoint（HTML/DOCX/报价不受影响）
- `domain-pack.yml` 方法论包契约（机械校验）计划 v1.1

## 快速开始

```powershell
git clone https://github.com/nyantused-cpun/folio.git folio
cd folio
.\setup\install.ps1        # 建 venv + 装依赖 + 生成配置 + 自检
# DSH 插件层（可选，建议装）：
.\setup\install-folio-plugins.ps1 -Install   # 15 工具 + 事件插件 + 守卫
# 重启 dsh web 后，新会话直接说「帮我做一份 XX 方案」
```

## 鸣谢

- DSH（DeepSeek Harness）社区：[awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) / [awesome-deepseek-harness](https://github.com/0xsline/awesome-deepseek-harness)
- 方法论渊源：APQC PCF、TOGAF 4A、CBM、ArchiMate（详见产品定位文档）

---

## Awesome 列表收录描述（复制即用）

**awesome-dsh-plugin / awesome-deepseek-harness 条目**：

> **Folio（兰亭）** —— 咨询/汇报材料生成引擎，首发深度适配 DSH。五段价值链（接入材料→建立记忆→应用方法论→生成产出→守住质量）全链路确定性化；15 个 DSH 原生工具 + 会话协议事件插件 + L0 守卫插件；方法论可换可组合（Folio Packs）；LLM host 模式零 key 起步。安装：`setup/install.ps1` + `setup/install-folio-plugins.ps1`。
