# Contributing to Folio

感谢你考虑为 Folio 贡献。本仓库对贡献者友好是设计目标，三类贡献都欢迎：

1. **提交 Issue**：bug 报告、功能建议、文档纠错；
2. **改进 skill**：修正一个方法论 skill 的内容；
3. **发布方法论包（Folio Packs）**：把一套咨询方法论做成可复用包——这是本项目最欢迎的贡献类型，不需要懂代码。

## 快速开始

```powershell
git clone <repo-url> folio
cd folio
.\setup\install.ps1     # 建 venv + 装依赖 + 生成 .env + 自检
```

- 零配置即可跑（L0 能力等级）；升级语义召回按 `docs/能力配置引导` 配 1 个 key。
- 测试：`.venv\Scripts\python.exe -m pytest tests`（tests 里不带客户数据，全部可公开运行）。

## 提交 Issue

- **Bug**：用 `bug_report` 模板，写明复现步骤、期望行为、实际行为、`key-doctor` 输出；
- **功能建议**：说明场景 + 解决什么问题，比具体方案更重要；
- **方法论包**：先看 `skills/packs-authoring`（它本身就是教你怎么写的 skill），把包放进 `skills/` 或独立仓库均可。

## 提交 PR

1. 从 `main` 开分支，命名 `fix/`、`feat/` 或 `pack/` 前缀；
2. 改动尽量小：一个 PR 一个主题；
3. 文本改动不需要测试；代码改动请跑相关测试并说明；
4. 涉及客户可见文案时，遵守 `skills/de-ai-style` 的检查项（禁用词、证据边界）；
5. 用 PR 模板填写。

## 风格约定

- 中文为主要文档语言（DSH 社区主力语言），代码注释保留中英混合现状；
- 命名：模块五段名见 README（Intake / Chronicle / Craft / Press / Proof）；
- 不用"售前助手"称呼本产品（那是历史内部名），对外统一「兰亭（Folio）」。

## 许可

MIT。提交即同意以 MIT 许可发布你的贡献。
