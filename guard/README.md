# presales-guard · Folio L0 守卫插件

## 1. 这是什么

把 Trae Hook 层的两条机械拦截平移到 DSH：`fs/write-intent` 拦 output/ 交付物与 refs/ 的直写（产出物必须经 CLI 生成、参考材料只读）；`tools/pre-execute` 拦非 CLI 的 python 直调（一律 `.venv/Scripts/python.exe _cli.py`）。

与项目现有防线的关系：Trae = Hook（L0）；DSH = 本插件（L0' 增强）+ file policy 沙箱 + CLI 进程内守门 + 会话结束 `audit --mode all`。本插件失败时自动降级到后两层（fail-open 语义与 Hook 一致）。

## 2. 兼容性

| 项 | 值 |
|---|---|
| 支持的 DSH 版本 | 0.1.0-rc.6（mainline commit：本机 `dsh -V` 安装包） |
| 最后验证日期 | 2026-08-14（接口逐行核实：`fs/write-intent`/`fs/edit-intent` 见 dsh-tool-fs lib/index.js:658/809；`tools/pre-execute` 见 dsh-tools lib/index.js:3098；gate 语义 kind=allow/deny/ask 见 :3300-3340） |
| 验证证据 | L1 源码级（已读）；L4 运行级（**待做**：加载实测需重启 dsh web，见 §5） |
| 升级策略 | DSH 升级后重跑 §5 的四步复测；接口漂移参考 dsh-plugin-radar 兼容报告 |

## 3. 安装（profile 层，勿装 agent preset 层）

守卫必须装 **profile 层**（preset 的 isolate realm 会挡住 host 工具注册表）。

方式 A（推荐，无包管理器依赖）——profile 的 `cordis.patch.yml` 顶层行：

```yaml
- insert:
    - id: presales-guard
      name: "@presales/dsh-guard"
      config: {}
```

⚠ 必须用无 id 的 `insert` 写法：patch 层语义是 id 定向覆盖/disable/insert（`cordis-plugin-include` `applyEntryPatches`，rc.6 源码核实），顶层直写 `- id/name/config` 会被当作非 insert 补丁，命中不存在的 id 时仅 warning 并被跳过，插件永不挂载。

官方范本背书（2026-08-15）：`dsh-external/dsh-tool-search` 的 `cordis.patch.yml` 使用同款写法，且展示了两个补充模式——entry 行的 `config` 可省略（无配置时）；一个 bundle 可挂多个 entry（用 package exports 子路径，如 `'@deepseek-ai/dsh-tool-search/invariant'`）：

```yaml
- insert:
    - id: tool-search
      name: '@deepseek-ai/dsh-tool-search'
    - id: tool-search-invariant
      name: '@deepseek-ai/dsh-tool-search/invariant'
```

并把本目录软链/复制到 profile 可解析位置（`~/.dsh/profiles/<name>/node_modules/@presales/dsh-guard`），或

方式 B（npm 分发后）：

```
dsh plugin --profile web add @presales/dsh-guard
```

## 4. 行为契约

- 拦 `output/**/*.{html,pptx,docx,xlsx}` 直写与一切 `refs/**` 写/改（项目内路径）
- 拦 pwsh/bash 里除 `python.exe _cli.py ...` 外的 python 直调
- approval 禁用环境下：直接 deny + 明确原因，不依赖 ask
- 项目外路径不拦（交给 file policy 沙箱）

## 5. 五步复测 SOP（每次 DSH 升级后）

1. `dsh --profile web --dump-config` 无 warning、presales-guard 行在 profile 树
2. 新会话：pwsh 直接 `python -c "print(1)"` → 应被 deny 且 reason 含 presales-guard
3. 新会话：pwsh 跑 `.venv/Scripts/python.exe _cli.py status` → 应放行
4. 新会话：write 工具直写 `output/xxx/xxx.html` → 应被拒；write `output/xxx/spec.yml`（中间产物）→ 应放行
5. 新会话：pwsh 跑 `Set-Content "output/xxx/测试.html" -Value x`（或 `>` 重定向写 output 交付物）→ 应被 deny（0.1.0-rc.2 新增 shell 直写检测；2026-08-14 L4 实测旧版此处是缺口）

## 6. 已知限制

- `tools/pre-execute` 只拦 pwsh/bash 两个 shell 工具的 command 参数；agent 若通过其他途径执行 python（如 defineTool 封装的 CLI 命令）不在本插件拦截面（那是 CLI 进程内守门职责）
- shell 直写检测是命令字符串正则（写操作符 + 受保护路径段 + 交付物后缀），非沙箱级隔离；刻意构造的绕过（变量拼接路径、cmd /c 内层命令）不在检测面——守卫是提示性 deny，沙箱 + CLI 守门 + audit 三层缺一不可
- 守卫是提示性 deny（模型可见 reason），不是沙箱级隔离；沙箱逃逸 PoC（dsh-security-pocs）说明 file policy 本身有已知弱点——因此本插件 + CLI 守门 + audit 三层缺一不可

## 7. 目录

```
.dsh/guard/
  index.js      插件本体（~120 行）
  package.json  包元数据（peerDependencies 对齐 rc.6）
  README.md     本文档
.dsh/preset/pre-sales/    agent preset 事实源（subagent_flash 工具）
.dsh/setup/presales-setup.ps1  一键安装/卸载/验证（原子写+锁+dry-run）
```

## 8. 归属与许可

Folio 项目内部插件（D-127）。MIT。

## 9. 变更记录

- 0.1.0-rc.1（2026-08-14）：初版。接口锚定 rc.6；运行级验证待 dsh web 重启后执行（§5 SOP）。
- 0.1.0-rc.2（2026-08-14）：补 shell 直写检测（checkShellWrite：写操作符 × output|inbox|refs 路径段；L4 实测旧版 pwsh Set-Content 直写 output/ 交付物绕开 fs/write-intent 事件面）。发布版 PROJECT_DIR 默认值改 process.cwd()（不硬编码作者路径）。运行级验证待 dsh web 重启后执行（§5 SOP 第 5 步）。
