// @folio/dsh-events：兰亭会话协议事件插件（P1 实施 M3，2026-08-14）
//
// 把 AGENTS.md 的会话纪律机械化（「纪律变机械」第一步）：
//   1. agent/session-start → 注入入口协议提醒（每新会话自动唤醒模型跑 folio_session_start）
//   2. session/event → 观察工具调用提取客户名（folio_session_start/folio_save 的 client 参数）
//   3. agent/disposed → 会话关闭自动 save（会话结束协议的机械触发）
//
// 接口依据（本机 @deepseek-ai/dsh 0.1.0-rc.6 逐行核实）：
//   - agent/session-start、agent/disposed：dsh-agent 官方 live 词汇（non-vetoing notification）；
//   - session/event：dsh-session 官方 live 服务事件（post-commit append 通知，持久事件镜像）；
//   - agent.followup(message)：dsh-agent 官方入队原语（next-turn FIFO 唤醒）；消息用
//     dsh-llm/message 的 createUserMessage 构造（mint MessageId，形状正确）；
//   - spawn 形态保持 .venv python _cli.py（guard CLI 白名单同一契约）。
//
// 设计边界（v1 刻意不做）：
//   - turn/end 中途冷却 save 留 v2：中途 save 与模型手动的 folio_save 有写竞态
//     （task_history/context.md 无跨进程锁），dispose 时机是协议正点，先只做它。

import { createUserMessage } from "@deepseek-ai/dsh-llm/message";
import { extractClientFromToolCall, makeCooldown } from "./state.js";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const name = "folio-events";
const inject = ["subprocess", "timer"];

// Folio 安装根解析（发布版）：env 优先，其次从本包位置向上找 _cli.py，最后回退 cwd。
function resolveProjectDir() {
  if (process.env.FOLIO_HOME) return process.env.FOLIO_HOME;
  if (process.env.DSH_PROJECT_DIR) return process.env.DSH_PROJECT_DIR;
  if (process.env.PRESALES_PROJECT_DIR) return process.env.PRESALES_PROJECT_DIR;
  try {
    let dir = dirname(fileURLToPath(import.meta.url));
    for (let i = 0; i < 5; i++) {
      if (existsSync(resolve(dir, "_cli.py"))) return dir;
      dir = dirname(dir);
    }
  } catch { /* noop */ }
  return process.cwd();
}

const PROJECT_DIR = resolveProjectDir();
const PYTHON = PROJECT_DIR.replace(/\\/g, "/") + "/.venv/Scripts/python.exe";

const SAVE_COOLDOWN_MS = 60_000; // 同会话 dispose 事件可能重复，60s 冷却

const SESSION_START_NOTE =
  "【兰亭入口协议】新会话已开始。请先调用 folio_session_start 工具（user_input=用户第一条消息原文，client=客户名）完成判层级+加载上下文+语义召回，再开始工作。同客户连续对话可跳过；若本会话非客户任务（如工程开发），可忽略本提醒。" +
  "\n" +
  "（本提醒由 folio-events 插件自动注入，无需用户记忆。）";

async function runCli(ctx, args, timeoutMs = 120000) {
  const proc = ctx.subprocess.spawn({
    argv: [PYTHON, "_cli.py", ...args],
    cwd: PROJECT_DIR,
    stdio: {
      stdin: "ignore",
      stdout: { maxBytes: 2 * 1024 * 1024 },
      stderr: { maxBytes: 512 * 1024 },
    },
    graceMs: 8000,
    env: { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  });
  let stopTimer;
  if (timeoutMs > 0) stopTimer = ctx.timeout(() => proc.terminate(), timeoutMs);
  try {
    const outcome = await proc.done;
    const out = proc.collected.stdout ? proc.collected.stdout.readFrom(0).text : "";
    const err = proc.collected.stderr ? proc.collected.stderr.readFrom(0).text : "";
    return { exitCode: outcome.exitCode, out, err };
  } finally {
    if (stopTimer) stopTimer();
  }
}

function apply(ctx) {
  const clientBySession = new Map(); // sessionId -> client
  const saveCooldown = makeCooldown(SAVE_COOLDOWN_MS);

  // ── 1) 新会话入口协议提醒 ────────────────────────────────────────────────
  ctx.on("agent/session-start", (payload) => {
    const agent = payload?.agent;
    if (!agent || typeof agent.followup !== "function") return;
    try {
      const msg = createUserMessage({
        content: [{ type: "text", text: SESSION_START_NOTE }],
        source: { kind: "folio-events", note: "session-start" },
      });
      agent.followup(msg);
    } catch (err) {
      console.error("[folio-events] 入口提醒注入失败（放行会话）:", err);
    }
  });

  // ── 2) 会话事件观察：提取客户名 ──────────────────────────────────────────
  ctx.on("session/event", (evt) => {
    try {
      const client = extractClientFromToolCall(evt);
      if (client) {
        // sessionId 关联：事件可能带 session 引用（第二参数）或 agent 域内已知
        const sessionId =
          evt.sessionId ??
          evt.session?.id ??
          evt.data?.sessionId ??
          (typeof evt.source === "object" && evt.source.sessionId);
        if (sessionId) clientBySession.set(String(sessionId), client);
        // 无 sessionId 时：记录「最近客户」兜底（dispose 时若查不到精确 id 用之）
        if (!sessionId) clientBySession.set("*last", client);
      }
    } catch (err) {
      console.error("[folio-events] 事件观察失败:", err);
    }
  });

  // ── 3) 会话关闭自动 save ────────────────────────────────────────────────
  ctx.on("agent/disposed", (payload) => {
    const agent = payload?.agent;
    const sessionId = String(agent?.id ?? agent?.session?.id ?? "");
    const client = clientBySession.get(sessionId) ?? clientBySession.get("*last");
    if (!client) {
      console.log(`[folio-events] 会话 ${sessionId || "?"} 关闭，未识别客户名，跳过自动 save`);
      return;
    }
    if (!saveCooldown.should(`save:${sessionId || client}`)) return;
    console.log(`[folio-events] 会话 ${sessionId || "?"} 关闭 → 自动 save 客户「${client}」`);
    runCli(ctx, ["save", client])
      .then((r) => {
        console.log(
          `[folio-events] auto-save ${client}: exit=${r.exitCode}${r.exitCode !== 0 ? " err=" + String(r.err || r.out).slice(0, 300) : ""}`,
        );
      })
      .catch((err) => console.error("[folio-events] auto-save 异常:", err));
  });
}

export { apply, inject, name };
