// @nyantused/folio-dsh-tools：兰亭 CLI 命令工具化（P1 实施，2026-08-14；guard 子入口 2026-08-16）
//
// 设计依据（兰亭xDSH原生插件化深度适配方案 §3 中工具化拍板）：
//   判据 = 命令是不是「模型的决策点」。记忆面/质量面是模型高频决策点 → 工具化；
//   生成型机械命令（html-build/pptd-*/docx-build/quote-* 等）留 pwsh。
//
// 接口依据（本机 @deepseek-ai/dsh 0.1.0-rc.6 源码逐行核实）：
//   - ctx.tools.register(defineTool(...))：dsh-tools 官方注册面；分层=调用方 ctx 的 scope
//     （本插件 apply 于 profile 层 = host 层全局注册，与 vision-bridge 同）；
//   - ctx.subprocess.spawn(spec)：vision-bridge 已验证模式（spec.argv/cwd/stdio.maxBytes/graceMs/
//     signal + proc.collected.stdout.readFrom(0).text + proc.done）；
//   - ctx.timeout：fiber 生命周期计时器（卸载自动清理）；
//   - 工具执行不经过 pwsh/bash exec → 与 guard 的 tools/pre-execute（只查 pwsh/bash）无交叉；
//     但 spawn 命令形态保持 .venv python _cli.py，与 guard CLI 白名单同一契约。
//   - guard 合并：原 @presales/dsh-guard 作为本包的子入口 `@nyantused/folio-dsh-tools/guard` 提供
//     （见 guard-entry.js），主入口只注册 15 个工具。安装时可按拓扑分别挂载：
//     preset 层挂主入口（工具限售前模式），profile 层挂 guard 子入口（守卫收 root 事件）。
//
// 输出协议：CLI 多数命令支持 --json 结构化输出（status/recall/graph-query/session-start）；
//   不支持 --json 的命令返回 stdout 原文（模型读文本）。工具 value 恒为
//   { ok, exitCode, output, error? }，render 折叠为文本。

import { defineTool } from "@deepseek-ai/dsh-tools";
import { TOOL_DEFS } from "./defs.js";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const name = "folio-tools";
const inject = ["tools", "subprocess", "timer"];

// Folio 安装根解析（发布版）：env 优先，其次从本包位置向上找 _cli.py（发布仓库
// 结构 plugins/folio-tools/ → 上溯 2 层即仓库根），最后回退会话工作目录。
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

/** spawn venv python _cli.py，返回 { exitCode, out, err }。 */
async function runCli(ctx, args, opts = {}) {
  const { timeoutMs = 90000, maxOut = 2 * 1024 * 1024 } = opts;
  const spec = {
    argv: [PYTHON, "_cli.py", ...args],
    cwd: PROJECT_DIR,
    stdio: {
      stdin: "ignore",
      stdout: { maxBytes: maxOut },
      stderr: { maxBytes: 512 * 1024 },
    },
    graceMs: 8000,
    env: { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
  };
  const proc = ctx.subprocess.spawn(spec);
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

/** 组装一个 CLI 桥工具（value={ok,exitCode,output,error?}，render=文本）。 */
function makeCliTool(ctx, def) {
  return defineTool({
    name: def.name,
    description: def.description,
    parameters: def.parameters,
    output: {
      schema: { type: "json" },
      render: (_args, value) => [
        {
          type: "text",
          text: value && value.ok
            ? String(value.output ?? "")
            : `[folio] ${def.name} 失败(exit ${value && value.exitCode}): ${value && value.error ? String(value.error) : "未知错误"}`,
        },
      ],
    },
    timeoutMs: def.opts.timeoutMs ?? 90000,
    async execute(args, exec) {
      const cliArgs = def.buildArgs(args);
      const r = await runCli(ctx, cliArgs, def.opts);
      const ok = r.exitCode === 0;
      return {
        ok,
        exitCode: r.exitCode,
        output: r.out.trim() || "",
        ...(ok ? {} : { error: (r.err || r.out || "").trim().slice(0, 2000) }),
      };
    },
  });
}

function apply(ctx) {
  for (const def of TOOL_DEFS) {
    ctx.tools.register(makeCliTool(ctx, def));
  }
  // 注意：L0 守卫不在这里安装。守卫由子入口 `@nyantused/folio-dsh-tools/guard` 提供
  // （guard-entry.js），以便按拓扑挂 profile 层；主入口可安全挂 preset 层。
}

export { apply, inject, name };
