# @nyantused/folio-dsh-events —— 兰亭会话协议事件插件

> P1 实施 M3（2026-08-14）。把 AGENTS.md 会话纪律机械化（「纪律变机械」第一步）。

## 1. 行为面（v1.0.1 两条）

| 触发 | 事件（官方词汇） | 行为 |
|---|---|---|
| 新会话 | `agent/session-start`（notification） | `agent.followup(createUserMessage(...))` 注入入口协议提醒，唤醒模型跑 folio_session_start |
| 会话关闭 | `agent/disposed`（notification） | 从 `agent.session.events` 倒序扫描 `tool/call`（folio_session_start/folio_save 的 arguments）提取客户名，自动 spawn `.venv python _cli.py save <client>`（60s 冷却防重复事件）——会话结束协议机械触发 |

> 作用域隔离（2026-08-15）：本插件挂在 pre-sales preset 层，仅「售前助手」模式生效；原 `session/event` 实时观察依赖 root scope 广播，preset 内收不到，故改为 disposed 时扫描会话事件。

## 2. 接口依据（rc.8 逐行核实）

- `agent/session-start` / `agent/disposed`：dsh-agent 官方 live 词汇（non-vetoing）；
- `tool/call` 会话事件形状 `{turn, step, callId, name, arguments}`：dsh-agent-loop `appendToolCall`（`session.append("tool/call", ...)`）；
- `agent.followup(message)`：dsh-agent 入队原语（next-turn FIFO 唤醒）；
- `createUserMessage`：dsh-llm/message 依赖最小入口（mint MessageId，形状正确）；
- spawn 形态保持 guard CLI 白名单契约（`.venv python _cli.py`）。

## 3. v1 刻意不做（v2 候选）

- `turn/end` 中途冷却 save：中途 save 与模型手动 folio_save 写竞态（task_history/context.md 无跨进程锁），dispose 时机是协议正点，先只做它；
- `agent/session-start` 自动执行入口协议（自动跑 recall/load）：v1 只注入提醒（客户名需模型从用户消息判断）；v2 可在提醒被消费后由模型行为数据驱动自动化。

## 4. 验证

- 沙箱内：`node --check index.js state.js` + `node test/run-check.mjs`（2026-08-14：7/7 通过；2026-08-20：rc.8 源码复核 + import 冒烟通过）；
- 运行级（待 dsh web 重启）：新会话第一条消息后应出现【兰亭入口协议】提醒；会话关闭后宿主日志出现 `[folio-events] auto-save` 行。

## 5. 已知限制

- host 插件改动需重启 `dsh web` 生效；
- 客户名提取依赖模型调用过 folio_session_start/folio_save（否则 dispose 时无客户名、跳过自动 save——日志会注明）；
- 事件 payload 形状按 rc.8 源码 + 防御式解析编写，DSH 升级后需按漂移复测（verifiedAgainst 记录在 package.json）。

## 6. 目录

```
plugins/folio-events/
  index.js         插件体
  state.js         纯逻辑（extractClientFromToolCall/makeCooldown，零依赖）
  cordis.patch.yml 激活 patch（preset 层挂载由 install-folio-plugins.ps1 管理，此文件仅供参考）
  package.json
  test/run-check.mjs
  README.md
```

## 7. 变更记录

- 0.1.0-rc.1（2026-08-14）：M3 初版——三条行为 + 纯逻辑单测；冷却器首次调用放行 bug 当场修复。
- 1.0.1（2026-08-15）：作用域隔离改造——插件移入 pre-sales preset 层；`session/event` 实时观察改为 `agent/disposed` 扫描 `agent.session.events` 提取客户名；发布版保留 `FOLIO_HOME`/上溯 `_cli.py` 路径解析，不硬编码作者路径。
