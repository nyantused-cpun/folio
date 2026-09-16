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
// 2. tools/pre-execute：拦非 CLI 的 python 直调 + shell 直写受保护路径
//    （纪律：一律 .venv/Scripts/python.exe _cli.py）
//
// v3（2026-09-16，与内部工作区 guard 0.1.0-rc.7 同源）：**命令位匹配**，修字面误拦。
// v1.1.0 的两处判定按「字面出现」工作，只读命令会被当违规：
//   · `PYTHON_CALL_RE` 无前置断言 + CLI 白名单整条命令 `$` 锚定 →
//     `Write-Output "评审提到 python 直调"`、`Select-String -Pattern python` 被误判为直调；
//     `.venv python _cli.py x 2>&1 | head` 因尾巴失配被误拦（守卫提示与行为自相矛盾）。
//   · `SHELL_MUTATE_CMDS` 含 `cat`（读取器）与裸 `>>?`，且任意位置匹配 →
//     `Select-String -Path refs/a.md -Pattern "Remove-Item"`、`find output -name "*.xlsx" 2>/dev/null`
//     被判成 shell 直写。
// 修法：python 与 shell 写命令**只在命令位**才算真调用——段首 / 命令分隔符后 / 子表达式起始 /
// 调用运算符 `&` / 赋值右值 / 嵌套壳（`cmd /c`、`pwsh -c`、`bash -c`）/ `Start-Process|Start-Job` 之后；
// 参数位与字符串里的字样一律不算。`cat` 移出写命令词表；重定向只在目标本身受保护时才拦。
// ⚠ 刻意**未**随内部线同步的差异（公开线保持更严，勿当漏项）：内部线的 `SAFE_MODULES` 安全模块白名单
//     与 `--version` 豁免不引入——公开线只认 `python _cli.py` 这一条通道。
//
// 接口依据（本机 @deepseek-ai/dsh 0.1.0-rc.8 源码逐行核实）：
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

  // ---- 命令位识别（v3）----
  // 命令位 = 段首 / 命令分隔符后 / 子表达式起始 / 调用运算符 `&` / 赋值右值 /
  //          嵌套壳（cmd /c、pwsh -c、bash -c）/ Start-Process|Start-Job 之后。
  const CMD_POS_PREFIX =
    "(?:^|[\\n;&|(){}`]|\\$\\()\\s*(?:&\\s*)?(?:\\$[\\w.:]+\\s*=\\s*)?" +
    "(?:(?:Start-Process|Start-Job)\\s+|cmd(?:\\.exe)?\\s+/c\\s+|(?:pwsh|powershell|bash|sh)(?:\\.exe)?\\s+(?:-c|-Command|/c)\\s+)?";
  // 解释器 token：裸名 / 带路径 / 带引号（引号内允许空格）/ **绝对路径含空格**
  // （安装根常带空格，如 `D:/My Projects/folio/.venv/Scripts/python.exe`）。绝对路径分支要求
  // 路径以分隔符结尾再接解释器名，因此 `/usr/bin/grep -r python .` 这类参数位字样不被误当调用。
  const PY_BIN =
    "(?:\"[^\"]*?python(?:3(?:\\.\\d+)?)?(?:\\.exe)?\"|'[^']*?python(?:3(?:\\.\\d+)?)?(?:\\.exe)?'|(?:[A-Za-z]:[\\\\/]|/)[^\"'|;&(){}`]*[\\\\/]python(?:3(?:\\.\\d+)?)?(?:\\.exe)?|[\\w./\\\\~:-]*python(?:3(?:\\.\\d+)?)?(?:\\.exe)?)";
  const PY_BOUNDARY = "(?=[\\s;&|)\\}\\]['\"`]|$)";
  const PYTHON_CALL_RE = new RegExp(CMD_POS_PREFIX + PY_BIN + PY_BOUNDARY, "i");
  // 真 CLI 调用 = 命令位解释器 token 紧邻 `_cli.py` 路径 token（不再「整条命令 $ 锚定」）
  const CLI_CALL_RE = new RegExp(
    CMD_POS_PREFIX + PY_BIN + "\\s+(?:\"[^\"]*_cli\\.py\"|'[^']*_cli\\.py'|[^\\s\"']*_cli\\.py)\\b",
    "i"
  );

  // ---- shell 写识别（v3）----
  // 写命令词表只认命令位（v1.1.0 的任意位置匹配会把 `-Pattern "Remove-Item"` 误判）；
  // `cat` 是读取器、不在表内；裸 `>>?` 不再视作写（改由下方重定向目标精确判定）。
  // 词尾 `(?=[^\w-]|$)` 防止 `cpx`/`md5`/`rmdir` 这类前缀误命中，同时容忍 `Remove-Item;` / `rm x`。
  const SHELL_MUTATE_RE = new RegExp(
    CMD_POS_PREFIX +
      "(?:Set-Content|Add-Content|Out-File|Tee-Object|Export-Csv|Export-Clixml|New-Item|Remove-Item|Move-Item|Rename-Item|Copy-Item|robocopy|xcopy|cp|mv|rm|tee|dd|sc|ac|ni|touch|copy|mkdir|md|rmdir|rd|del|erase|ren|rename|move)(?=[^\\w-]|$)|" +
      CMD_POS_PREFIX +
      "\\[io\\.file\\]::(?:WriteAll\\w*|AppendAll\\w*|AppendText|Create\\w*|OpenWrite|Delete|Move|Copy)\\b",
    "i"
  );
  // 文件重定向 `> out.html` / `>> "D:/a b/out.html"`：排除 fd 重定向（2>&1 / 2>err 主体为 fd 号时）。
  // v3：目标改为「引号优先」捕获——带空格的绝对路径用 `[^\s]+` 只能截到半个路径会漏拦。
  const REDIRECT_RE = /(?:^|[\s;|&(])(?:>>|>)(?!\s*&?\d)\s*(?:"([^"]+)"|'([^']+)'|([^\s"'&|;>]+))/g;

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

    // 按命令分隔符切段（|| && | ;）逐段判定——一段里有合规 CLI 调用不再拖累其余段
    for (const seg of cmd.split(/\|\||&&|[|;]/)) {
      if (!PYTHON_CALL_RE.test(seg)) continue; // v3：命令位无解释器 → 不是调用
      if (CLI_CALL_RE.test(seg)) continue;     // 解释器 + `_cli.py` 相邻 → 合规 CLI 调用
      return {
        kind: "deny",
        reason: "[folio-guard] 禁止直接调用 python（项目纪律：一律 .venv/Scripts/python.exe _cli.py <命令>，其余脚本须走 CLI 或先与用户确认）"
      };
    }
    return null;
  }

  // shell 命令写受保护路径检测：dsh 的 fs/write-intent 只覆盖 write/edit 工具，
  // pwsh/bash 子进程的 Set-Content/Out-File/> 等直写完全绕开事件面（L4 实测确认）。
  // v3：a. 命令位写出词表命中 → 全命令粗查受保护路径；b. 重定向目标精确提取后单独判定。
  function checkShellWrite(exec) {
    if (exec.name !== "pwsh" && exec.name !== "bash") return null;
    if (!isCommandInProject(exec)) return null; // 售前项目外：不拦（作用域隔离）
    const cmd = String(exec.arguments?.command ?? "");

    if (SHELL_MUTATE_RE.test(cmd)) {
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
    }

    REDIRECT_RE.lastIndex = 0;
    let m;
    while ((m = REDIRECT_RE.exec(cmd)) !== null) {
      const raw = m[1] ?? m[2] ?? m[3];
      if (!raw) continue;
      const t = normalizePath(raw);
      if (REFS_RE.test(t)) {
        return {
          kind: "deny",
          reason: `[folio-guard] 禁止重定向写入 refs/（只读目录）: ${raw}`
        };
      }
      if (PROTECTED_RE.test(t) && DELIVERABLE_RE.test(t)) {
        return {
          kind: "deny",
          reason: `[folio-guard] 禁止重定向写入 output/ 交付物（必须经 CLI 生成）: ${raw}`
        };
      }
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
