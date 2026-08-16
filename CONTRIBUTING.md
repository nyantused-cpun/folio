# Contributing to Folio

感谢你考虑为 Folio 贡献。本仓库对贡献者友好是设计目标，三类贡献都欢迎：

1. **提交 Issue**：bug 报告、功能建议、文档纠错；
2. **改进 skill**：修正一个方法论 skill 的内容；
3. **发布方法论包（Folio Packs）**：把一套咨询方法论做成可复用包——这是本项目最欢迎的贡献类型，不需要懂代码。

## 快速开始

> 环境要求：Windows 10/11 + PowerShell + Python ≥ 3.10（安装脚本自动探测 `py`/`python`/`python3`）；Node.js 不需要；`pptd-build --shots` 截图目检才需要本机 PowerPoint。

```powershell
git clone https://github.com/nyantused-cpun/folio.git folio
cd folio
.\setup\install.ps1     # 建 venv + 装依赖 + 生成 .env + 自检
```

- 零配置即可跑（L0 能力等级）；升级语义召回按 `docs/能力配置引导` 配 1 个 key。
- 测试：
  ```powershell
  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # 首次
  .venv\Scripts\python.exe -m pytest tests
  ```
  （tests 里不带客户数据，全部可公开运行；密度检查用例在无 playwright 时自动跳过。）

## 提交 Issue

- **Bug**：用 `bug_report` 模板，写明复现步骤、期望行为、实际行为、`key-doctor` 输出；
- **功能建议**：说明场景 + 解决什么问题，比具体方案更重要；
- **方法论包**：先看 `skills/packs-authoring`（它本身就是教你怎么写的 skill），把包放进 `skills/` 或独立仓库均可。

## 提交 PR

1. 从 `master` 开分支，命名 `fix/`、`feat/` 或 `pack/` 前缀；
2. 改动尽量小：一个 PR 一个主题；
3. 文本改动不需要测试；代码改动请跑相关测试并说明；
4. 涉及客户可见文案时，遵守 `skills/de-ai-style` 的检查项（禁用词、证据边界）；
5. 用 PR 模板填写。

## 风格约定

- 中文为主要文档语言（DSH 社区主力语言），代码注释保留中英混合现状；
- 命名：模块五段名见 README（Intake / Chronicle / Craft / Press / Proof）；
- 不用"售前助手"称呼本产品（那是历史内部名），对外统一「兰亭（Folio）」。

## 语言策略（Language policy）

**面向 agent 的指令内容默认用英文**——skills 正文、preset 的 SOP、AGENTS 类指令等只有 agent 读、人不读；英文跨中英文模型都稳定、token 更省，也不受中文分词与编码差异影响。

- **例外（保留中文）**：禁用词表、语感样本、客户名/行业名示例等必须逐字匹配的中文素材；
- **SKILL.md 的 description**：允许中英各一句短触发词（中文用户口语触发 + 英文模型匹配）；
- **人读文档**（README / docs / RELEASE_NOTES / CHANGELOG）：保持中英双语入口，不套用本策略；
- **核心提示词保持精简**：只写约束、边界与例外，不写推理过程，不堆砌背景叙述。

## 许可

MIT。提交即同意以 MIT 许可发布你的贡献。
