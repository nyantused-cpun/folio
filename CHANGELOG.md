# Changelog

> 版本线说明：本仓库记录**对外发布线**（Folio），与内部工作区版本线（售前助手 v3.x）相互独立、不对齐。只有值得对外说的事才升版本。

## [未发布] - 2026-08-16

### 修复

- **发布版路径契约统一为「仓库根 = 用户工作区」**：根级 `_cli.py` 转发入口（插件/guard/skills 的 `python _cli.py` 口径全部可用）；`.env`、output、inbox、_knowledge、.folio 从 `src/` 内迁回仓库根；`load-skill`/`skills-sync` 兼容发布版根 `skills/` 布局。
- **PPT 后端口径更正**：README/RELEASE_NOTES/install.ps1 由「依赖 node」更正为自研 python-pptx 后端（`--shots` 截图需本机 PowerPoint）。
- **skill 废弃命令清理**：`ui-design-system` 与 `spec-writing-guide` 中残留的 `ppt-page`/`ppt-build` 用法改为 `html-build` 双输出 + `pptd-build`（D-090）。
- **文档冲突清理**：技术白皮书事件机制更新为 `agent/disposed` 扫描；产品定位 8 命令工具化更正为 15 个；guard 版本对外口径统一为「随 folio-dsh-tools 1.1.0 分发」；README 死链/测试数/版本状态修正；preset 移除内部模型硬编码。
- **启动降噪**：`_check_env` 不再每次刷缺失 key 警告（零 key 是正常状态；建议配置集中在 key-doctor 与 .env.example/能力配置引导）。

## [1.0.1] - 2026-08-15

### 修复

- **guard 0.1.0-rc.4（作用域隔离）**：guard 保持 profile 全局挂载（L0 防线不能进 preset），但 shell/python 拦截仅对「售前项目内」命令生效（`isCommandInProject` 按会话 cwd/workdir 判定），解决「切项目被兰亭污染」；发布版保留 `FOLIO_HOME` / `process.cwd()` 路径解析，不硬编码作者路径。
- **@nyantused/folio-dsh-events 1.0.1（作用域隔离改造）**：插件移入 pre-sales preset 层；原 `session/event` 实时观察（preset 内收不到 root scope 广播）改由 `agent/disposed` 扫描 `agent.session.events` 提取客户名。
- **inbox 命名统一**：`src/_inbox_scan.py` 由 `_inbox` 改 `inbox`（无下划线=用户 I/O，下划线=引擎私有）。

### 新增

- **agent preset 入仓**：`preset/agent.cordis.yml` 模板（`__FOLIO_HOME__` 占位），`install-folio-plugins.ps1` 安装时自动落盘/替换占位符；README 快速开始补第二条插件安装命令。
- **社区生态 / 友情链接**：README 新增社区插件对照与 v1.1 优先补全清单；`setup/install-community-plugins.ps1` 提供 `-DryRun`/`-Verify` 入口（暂缓启用，装而未挂）。
- **install-all**：默认只装自研插件（guard + folio-tools + folio-events），`-IncludeCommunity` 显式开启社区插件（仍受暂缓保护）。

### 说明

- vision-bridge 未随本次开源分发（内部能力）；需要时自备并手工在 preset 补一行。
- 原 `[1.0.1](rc)` 章节（2026-08-14 插件层）内容已随 v1.0.0 正式发布，移至文末附注。

## [1.0.0] - 2026-08-15

首个正式发布。内核经多年内部实战迭代（60+ 命令、1000+ 测试用例），本次以兰亭（Folio）品牌开源。

### 核心能力（五段价值链）

- **接入材料（Intake）**：客户建档、inbox 归档、招标/PDF/PPT 解析、切片与双路索引（BM25 + 可选语义索引）
- **建立记忆（Chronicle）**：决策记录、客户档案、世界书知识图、语义召回（零配置降级纯 BM25）
- **应用方法论（Craft）**：skill 路由 + 场景大纲 + 主题守卫 + 去 AI 化；方法论可换可组合（Folio Packs，创作指南见 `skills/packs-authoring`）
- **生成产出（Press）**：spec 协议 → HTML / PPTX / DOCX / 报价同源双输出；33 种图形、10 种页面构件、16 种版式
- **守住质量（Proof）**：confirmed 门禁、verify、独立审查（review/adversarial）、引用审计、美学/讲法观察

### 宿主适配

- 深度适配 DSH：skills 原生识别、L0 守卫插件、agent preset、能力分级（L0 零 key 起步）
- `LLM_MODE=host`：DSH 下 5 个 LLM 命令不依赖云端 key，推理交由宿主 AI 执行
- 读图/搜索/独立审查在 DSH 下由宿主原生覆盖；独立 CLI 场景按能力插槽逐级解锁（见 `docs/能力配置引导`）

## 附：v1.0.0 插件层 rc 明细（2026-08-14，已随 1.0.0 正式发布）

P1 插件层随 v1.0 发布线合入 `plugins/`（运行级验证待 dsh web 重启后执行，见各插件 README §验证）。

### 新增

- **`@nyantused/folio-dsh-tools`**：15 个 DSH 原生工具（defineTool 注册）——记忆面 9（status/pending/recall/read/chunk-read/graph-query/session-start/save/load）+ 质量面 6（verify/review/cite-audit/audit/theme-verify/spec-diff）；参数 schema 校验 + subprocess 桥 + 结构化输出；工具定义纯数据表（defs.js）可独立单测
- **`@nyantused/folio-dsh-events`**：会话协议事件插件——`agent/session-start` 注入入口协议提醒、`session/event` 提取客户名、`agent/disposed` 自动 save（60s 冷却）；纯逻辑（state.js）单测覆盖
- **`setup/install-folio-plugins.ps1`**：幂等安装/验证/卸载（Junction ×2 + cordis.patch.yml insert，原子写 + 锁 + 备份）
- 发布版插件 Folio 安装根自动解析（env FOLIO_HOME 优先，其次包位置上溯找 _cli.py，不硬编码路径）

### 修复

- **guard 0.1.0-rc.2**：补 shell 直写检测（checkShellWrite：写操作符 × output|inbox|refs 路径段）——L4 实测旧版 pwsh `Set-Content` 直写 output/ 交付物可绕开 `fs/write-intent` 事件面；发布版 PROJECT_DIR 默认改 `process.cwd()`

### 质量与安全

- 防幻觉防线：生成前门禁 + 生成后 verify + 独立审查 + 会话审计
- 去 AI 化机械检查（禁词库、证据边界、语感样本）
- 全库脱敏：发布版不含任何客户数据；测试基线已裁剪

### 已知限制（v1.0）

- 首发平台 Windows；macOS/Linux 安装脚本待补
- PPT 转换为自研 python-pptx 后端（`PPTD_BACKEND=python_pptx`）；`--shots` 截图目检需本机 PowerPoint，无则跳过（HTML/DOCX/报价不受影响）
- `domain-pack.yml` 方法论包契约（机械校验）计划 v1.1
