# @folio/dsh-tools —— 兰亭 CLI 命令工具化插件

> P1 实施（2026-08-14）。把兰亭「模型决策点」命令注册为 DSH 原生工具；生成型机械命令（html-build/pptd-*/docx-build/quote-* 等）留 pwsh。

## 1. 工具面（15 个）

- **记忆面 9**：folio_status / folio_pending / folio_recall / folio_read / folio_chunk_read / folio_graph_query / folio_session_start / folio_save / folio_load
- **质量面 6**：folio_verify / folio_review / folio_cite_audit / folio_audit / folio_theme_verify / folio_spec_diff

每个工具 = `defineTool({name, description, parameters, output, execute})`；execute 走 `ctx.subprocess.spawn([PYTHON, "_cli.py", ...args])`（vision-bridge 已验证模式），CLI 支持 `--json` 的命令结构化返回，其余返回 stdout 文本。value 恒为 `{ok, exitCode, output, error?}`。

## 2. 接口依据

- `ctx.tools.register` / `defineTool`：dsh-tools 官方注册面（rc.6 逐行核实）；注册层 = 调用方 ctx scope（profile 层 = host 全局）；
- `ctx.subprocess.spawn`：argv/cwd/stdio.maxBytes/graceMs + `proc.collected.stdout.readFrom(0).text`；
- `ctx.timeout`：fiber 生命周期计时器；
- guard 兼容：工具 spawn 不经过 pwsh/bash exec（与 guard 的 tools/pre-execute 无交叉）；命令形态保持 `.venv python _cli.py`，满足 guard CLI 白名单（单测含正则断言）。

## 3. 目录

```
.dsh/folio-tools/
  index.js        插件体（runCli + makeCliTool + apply）
  defs.js         TOOL_DEFS 纯数据（零依赖，可独立单测）
  cordis.patch.yml 激活 patch（无 id insert，profile 层引用）
  package.json
  test/run-check.mjs  沙箱内自检（无 spawn）；用户终端可跑 node --test 变体
  README.md
```

## 4. 验证

- 沙箱内：`node --check index.js defs.js` + `node test/run-check.mjs`（2026-08-14：10/10 通过）；
- 运行级（待 dsh web 重启）：新会话问模型「你有哪些 folio_ 工具」；直接调 folio_status 应返回客户状态 JSON。

## 5. 已知限制

- host 插件改动需重启 `dsh web` 生效；
- `review`/`cite-audit`/`audit all` 是 LLM 重操作（timeoutMs 300s）；`folio_review` 云端审查依赖能力槽 key 或 DSH 子代理补位；
- 工具输出为 CLI stdout 直传，超长输出由 DSH 工具结果剪枝（8192 字符）兜底。

## 6. 变更记录

- 0.1.0-rc.1（2026-08-14）：M1+M2——15 工具（记忆面 9 + 质量面 6），defs 模块化 + 沙箱内自检脚本。
