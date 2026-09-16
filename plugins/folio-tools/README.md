# @nyantused/folio-dsh-tools —— 兰亭 CLI 命令工具化 + L0 守卫插件

> P1 实施（2026-08-14）；L0 守卫合并（2026-08-16）。把兰亭「模型决策点」命令注册为 DSH 原生工具；生成型机械命令（html-build/pptd-*/docx-build/quote-* 等）留 pwsh。安装本包即同时获得 15 个工具 + L0 守卫（原 `@presales/dsh-guard`）。

## 1. 工具面（15 个）

- **记忆面 9**：folio_status / folio_pending / folio_recall / folio_read / folio_chunk_read / folio_graph_query / folio_session_start / folio_save / folio_load
- **质量面 6**：folio_verify / folio_review / folio_cite_audit / folio_audit / folio_theme_verify / folio_spec_diff

每个工具 = `defineTool({name, description, parameters, output, execute})`；execute 走 `ctx.subprocess.spawn([PYTHON, "_cli.py", ...args])`（vision-bridge 已验证模式），CLI 支持 `--json` 的命令结构化返回，其余返回 stdout 文本。value 恒为 `{ok, exitCode, output, error?}`。

## 1.1 守卫面（L0，原 @presales/dsh-guard）

- `fs/write-intent` / `fs/edit-intent`：拦 `output/**/*.{html,pptx,docx,xlsx}` 直写与一切 `refs/**` 写/改（项目内路径）
- `tools/pre-execute`：python 直调与 shell 写受保护路径都按**命令位**判定（段首 / 命令分隔符后 / 子表达式 / `&` / 赋值右值 / 嵌套壳 `cmd /c`·`pwsh -c` / `Start-Process`）——参数位与字符串里的字样（叙述文本、检索模式串）不再误伤（v3，2026-09-16）
- 作用域隔离：shell/python 拦截仅对「售前项目内」命令生效，其他 workspace/项目完全放行
- **刻意与内部线不同的更严口径**：只认 `python _cli.py` 一条通道——不引入内部线的 `SAFE_MODULES`（`python -m pytest/pip`）与 `--version` 豁免（测试已锁定，勿当漏项）

## 2. 接口依据

- `ctx.tools.register` / `defineTool`：dsh-tools 官方注册面（rc.8 逐行核实）；注册层 = 调用方 ctx scope（profile 层 = host 全局）；
- `ctx.subprocess.spawn`：argv/cwd/stdio.maxBytes/graceMs + `proc.collected.stdout.readFrom(0).text`；
- `ctx.timeout`：fiber 生命周期计时器；
- guard 兼容：工具 spawn 不经过 pwsh/bash exec（与 guard 的 tools/pre-execute 无交叉）；命令形态保持 `.venv python _cli.py`，满足 guard CLI 白名单（单测含正则断言）。

## 3. 目录

```
.dsh/folio-tools/
  index.js        插件体（runCli + makeCliTool + apply + 安装守卫）
  defs.js         TOOL_DEFS 纯数据（零依赖，可独立单测）
  guard.js        L0 守卫纯函数 + install（零依赖，可独立单测）
  guard-entry.js  @nyantused/folio-dsh-tools/guard 子入口（profile 层挂载用）
  cordis.patch.yml 激活 patch（工具 + guard 两个 entry）
  package.json
  test/run-check.mjs  沙箱内自检（无 spawn）；用户终端可跑 node --test 变体
  README.md
```

## 4. 验证

- 沙箱内：`node --check index.js defs.js guard.js` + `node test/run-check.mjs`（2026-08-14：10/10 通过；2026-08-16 增补 guard 纯函数断言；2026-08-20：rc.8 源码复核 + import 冒烟通过；**2026-09-16：guard v3 命令位语义 + 真实守卫判定改造后 17/17 通过**）；
- 运行级（待 dsh web 重启）：新会话问模型「你有哪些 folio_ 工具」；直接调 folio_status 应返回客户状态 JSON；
- 守卫运行级：新会话 pwsh 直接 `python -c "print(1)"` 应被 deny；`.venv/Scripts/python.exe _cli.py status` 应放行。

## 5. 已知限制

- host 插件改动需重启 `dsh web` 生效；
- `review`/`cite-audit`/`audit all` 是 LLM 重操作（timeoutMs 300s）；`folio_review` 云端审查依赖能力槽 key 或 DSH 子代理补位；
- 工具输出为 CLI stdout 直传，超长输出由 DSH 工具结果剪枝（8192 字符）兜底。

## 6. 变更记录

- 0.1.0-rc.1（2026-08-14）：M1+M2——15 工具（记忆面 9 + 质量面 6），defs 模块化 + 沙箱内自检脚本。
- 1.1.0（2026-08-16）：合并原 @presales/dsh-guard 为 guard.js，安装本包即同时获得 L0 守卫；package.json files/keywords 同步更新。
- 1.1.1（2026-09-16）：**守卫 v3 命令位匹配**（与内部线 guard `0.1.0-rc.7` 同源）——修掉两处按「字面出现」判定的假阳性：① python 判定无前置断言 + CLI 白名单整条命令 `$` 锚定 → 叙述/检索文本被当直调、`_cli.py … 2>&1 | head` 因尾巴失配被误拦；② `SHELL_MUTATE_CMDS` 含 `cat`（读取器）与裸 `>>?` 且在任意位置匹配 → 只读检索 `refs/` 与 `find output -name "*.xlsx" 2>/dev/null` 被判成 shell 直写。另修两处**路径带空格**盲区（绝对路径含空格解释器漏放、引号重定向目标被截断）。测试由「白名单正则副本」改为**真实守卫判定** + v3 反例（17/17）。**未随内部线同步的差异（刻意更严）**：不引入 `SAFE_MODULES`/`--version` 豁免。
