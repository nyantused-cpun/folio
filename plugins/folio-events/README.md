# @folio/dsh-events —— 兰亭会话协议事件插件

> P1 实施 M3（2026-08-14）。把 AGENTS.md 会话纪律机械化（「纪律变机械」第一步）。

## 1. 行为面（v1 三条）

| 触发 | 事件（官方词汇） | 行为 |
|---|---|---|
| 新会话 | `agent/session-start`（notification） | `agent.followup(createUserMessage(...))` 注入入口协议提醒，唤醒模型跑 folio_session_start |
| 会话运行中 | `session/event`（live，post-commit append） | 观察 `tool/call` 事件，从 folio_session_start/folio_save 的 arguments 提取客户名，记 sessionId→client |
| 会话关闭 | `agent/disposed`（notification） | 对已知客户名自动 spawn `.venv python _cli.py save <client>`（60s 冷却防重复事件）——会话结束协议机械触发 |

## 2. 接口依据（rc.6 逐行核实）

- `agent/session-start` / `agent/disposed`：dsh-agent 官方 live 词汇（non-vetoing）；
- `session/event`：dsh-session 官方 live 服务事件（post-commit append 通知，持久事件镜像）；
- `agent.followup(message)`：dsh-agent 入队原语（next-turn FIFO 唤醒）；
- `createUserMessage`：dsh-llm/message 依赖最小入口（mint MessageId，形状正确）；
- spawn 形态保持 guard CLI 白名单契约（`.venv python _cli.py`）。

## 3. v1 刻意不做（v2 候选）

- `turn/end` 中途冷却 save：中途 save 与模型手动 folio_save 写竞态（task_history/context.md 无跨进程锁），dispose 时机是协议正点，先只做它；
- `agent/session-start` 自动执行入口协议（自动跑 recall/load）：v1 只注入提醒（客户名需模型从用户消息判断）；v2 可在提醒被消费后由模型行为数据驱动自动化。

## 4. 验证

- 沙箱内：`node --check index.js state.js` + `node test/run-check.mjs`（2026-08-14：7/7 通过）；
- 运行级（待 dsh web 重启）：新会话第一条消息后应出现【兰亭入口协议】提醒；会话关闭后宿主日志出现 `[folio-events] auto-save` 行。

## 5. 已知限制

- host 插件改动需重启 `dsh web` 生效；
- 客户名提取依赖模型调用过 folio_session_start/folio_save（否则 dispose 时无客户名、跳过自动 save——日志会注明）；
- 事件 payload 形状按 rc.6 源码 + 防御式解析编写，DSH 升级后需按漂移复测（verifiedAgainst 记录在 package.json）。

## 6. 目录

```
.dsh/folio-events/
  index.js         插件体
  state.js         纯逻辑（extractClientFromToolCall/makeCooldown，零依赖）
  cordis.patch.yml 激活 patch
  package.json
  test/run-check.mjs
  README.md
```

## 7. 变更记录

- 0.1.0-rc.1（2026-08-14）：M3 初版——三条行为 + 纯逻辑单测；冷却器首次调用放行 bug 当场修复。
