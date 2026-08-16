// @nyantused/folio-dsh-tools L0 守卫模块
//
// 由原 @presales/dsh-guard 合并进 @nyantused/folio-dsh-tools（2026-08-16）：
// - 两者都挂在 profile 层（host 全局），guard 监听 root scope 事件的要求不变；
// - 安装 @nyantused/folio-dsh-tools 即同时获得 15 个工具 + L0 守卫；
// - 原 guard 的 name/inject 外壳不再需要，统一由 folio-tools 的 entry 提供。
//
// 行为契约（对齐 Trae Hook 层的两条机械拦截）：
// 1. fs/write-intent + fs/edit-intent：拦 output/ 与 refs/ 直写
//    （产出物必须经 CLI 生成；refs 只读）
// 2. tools/pre-execute：拦非 CLI 的 python 直调
//    （纪律：一律 .venv/Scripts/python.exe _cli.py，禁 python xxx.py / -m / -c）
//
// 接口依据（本机 @deepseek-ai/dsh 0.1.0-rc.6 源码逐行核实）：
// - ctx.on + ctx.waterfall 是同一事件总线的读写两端（dsh-tool-fs lib/index.js:658/809
//   触发 "fs/write-intent"/"fs/edit-intent"，handler 链 next() 续链、throw 拒绝）
// - "tools/pre-execute" 瀑布（dsh-tools lib/index.js:3098）gate 语义：
//   {kind:"allow"} 放行 / {kind:"deny", reason} 拒绝 / {kind:"ask", reason} 审批
// - 本环境 approval 禁用 → 一律直接 deny + 明确原因，不依赖 ask

export function createGuardRules(projectDir) {
  const PROJECT_DIR = String(projectDir || process.cwd());

  const PROTECTED_RE = /(?:^|[\\/])(output|_inbox)(?:[\\/]|$)/;
  const REFS_RE = /(?:^|[\\/])refs(?:[\\/]|$)/;
  const DELIVERABLE_RE = /\.(html|pptx|docx|xlsx)$/i;
  // CLI 白名单：venv python 跑 _cli.py（含子命令）放行
  const CLI_WHITELIST_RE = /python\.exe"?\s+_cli\.py(?:\s+\S+)*\s*$/i;
  const PYTHON_CALL_RE = /\bpython(?:\.exe)?\b/i;
  // shell 直写受保护路径检测（2026-08-14 L4 实测：fs/write-intent 只覆盖 dsh 文件工具，
  // pwsh Set-Content 直写 output/ 完全绕开——此处补 shell 命令面）
  const SHELL_MUTATE_CMDS =
    /\b(Set-Content|Add-Content|Out-File|Tee-Object|Export-Csv|Export-Clixml|New-Item|Remove-Item|Move-Item|Rename-Item|Copy-Item|robocopy|xcopy|cp|mv|rm|tee|dd|cat)\b|\[io\.file\]::(WriteAll|AppendAll|Delete|Move|Copy)|>>?/i;
  // 命令字符串里的相对路径段（命令中不含项目绝对路径时用）
  const CMD_PROTECTED_RE = /(?:^|[\s"'\\/])(output|inbox|_inbox)(?:[\s"'\\/]|$)/i;
  const CMD_REFS_RE = /(?:^|[\s"'\\/])(refs)(?:[\s"'\\/]|$)/i;

  function normalizePath(p) {
    return String(p ?? "").replace(/\\/g, "/").toLowerCase();
  }

  // 项目内自检（2026-08-15 作用域隔离修复）：guard 保持全局挂载（fs/write-intent 事件
  // 从 root scope 发出，preset 内监听不到，L0 防线不能进 preset），但所有 shell 拦截
  // 必须只对「售前项目内」的命令生效——其他 workspace/项目的 python 直调与 output 直写
  // 一律放行，避免兰亭生态污染其他项目。
  // 判据：会话工作区（exec.agent.session.header.cwd，官方先例见 dsh-agent-loop
  // systemPrompt.variable("cwd")）或其绝对 workdir 落在 PROJECT_DIR 内。无法判断时
  // 视为项目外（放行，宁缺毋滥——guard 的本职是项目纪律，不是全局安全）。
  function isCommandInProject(exec) {
    const p = normalizePath(PROJECT_DIR);
    const candidates = [
      exec?.agent?.session?.header?.cwd,
      exec?.arguments?.workdir,
    ];
    for (const raw of candidates) {
      if (typeof raw !== "string" || !raw.trim()) continue;
      const n = normalizePath(raw.trim());
      if (!/^[a-z]:\//.test(n) && !n.startsWith("/")) continue; // 相对路径不可靠，跳过
      if (n === p || n.startsWith(p + "/")) return true;
    }
    return false;
  }

  function isProtectedWrite(p) {
    const n = normalizePath(p);
    if (!n.includes(normalizePath(PROJECT_DIR))) return false; // 项目外不拦（file policy 管）
    const rel = n.slice(normalizePath(PROJECT_DIR).length).replace(/^[/\\]+/, "");
    if (REFS_RE.test(rel)) return true;                        // refs 只读
    if (PROTECTED_RE.test(rel) && DELIVERABLE_RE.test(rel)) return true; // output 交付物直写
    return false;
  }

  function checkPythonExec(exec) {
    if (exec.name !== "pwsh" && exec.name !== "bash") return null;
    if (!isCommandInProject(exec)) return null; // 售前项目外：不拦（作用域隔离）
    const cmd = String(exec.arguments?.command ?? "");
    if (!PYTHON_CALL_RE.test(cmd)) return null;
    if (CLI_WHITELIST_RE.test(cmd)) return null;
    return {
      kind: "deny",
      reason: "[folio-guard] 禁止直接调用 python（项目纪律：一律 .venv/Scripts/python.exe _cli.py <命令>，其余脚本须走 CLI 或先与用户确认）"
    };
  }

  // shell 命令写受保护路径检测：dsh 的 fs/write-intent 只覆盖 write/edit 工具，
  // pwsh/bash 子进程的 Set-Content/Out-File/> 等直写完全绕开事件面（L4 实测确认）。
  // 命令内路径版（v3，修复 0.1.0-rc.2 漏判）：交付物后缀用词边界 \b 而非 $ 锚定——
  // 整条命令里 .html 后面往往还跟 -Value/编码等尾巴，$ 锚定会漏判（rc.2 L4 实测暴露）。
  // CLI 白名单命令不受此限（引擎自写 output 合法）。
  function checkShellWrite(exec) {
    if (exec.name !== "pwsh" && exec.name !== "bash") return null;
    if (!isCommandInProject(exec)) return null; // 售前项目外：不拦（作用域隔离）
    const cmd = String(exec.arguments?.command ?? "");
    if (!SHELL_MUTATE_CMDS.test(cmd)) return null;
    const n = normalizePath(cmd);
    const hasDeliverableSuffix = /\.(html|pptx|docx|xlsx)\b/i.test(n);
    if (CMD_REFS_RE.test(n)) {
      return {
        kind: "deny",
        reason: "[folio-guard] 禁止 shell 操作 refs/（只读目录；文件操作请用 DSH 的 write/edit 工具或 _cli.py）"
      };
    }
    if (hasDeliverableSuffix && CMD_PROTECTED_RE.test(n)) {
      return {
        kind: "deny",
        reason: "[folio-guard] 禁止 shell 直写 output/ 交付物（必须经 CLI 生成；文件操作请用 DSH 的 write/edit 工具或 _cli.py）"
      };
    }
    return null;
  }

  function install(ctx) {
    ctx.on("fs/write-intent", (target, _exec, next) => {
      const p = target?.displayPath ?? target ?? "";
      if (isProtectedWrite(p)) {
        throw new Error(`[folio-guard] 直写受保护路径被拒: ${p}（output/ 交付物必须经 CLI 生成；refs/ 只读）`);
      }
      return next();
    });
    ctx.on("fs/edit-intent", (target, _exec, next) => {
      const p = target?.displayPath ?? target ?? "";
      if (isProtectedWrite(p)) {
        throw new Error(`[folio-guard] 直改受保护路径被拒: ${p}（output/ 交付物必须经 CLI 生成；refs/ 只读）`);
      }
      return next();
    });
    ctx.on("tools/pre-execute", (exec, next) => {
      const gate = checkPythonExec(exec) || checkShellWrite(exec);
      if (gate) return gate;
      return next();
    });
  }

  return {
    install,
    isProtectedWrite,
    checkPythonExec,
    checkShellWrite,
    isCommandInProject,
  };
}
