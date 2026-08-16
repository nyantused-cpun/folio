// @nyantused/folio-dsh-tools 纯函数自检脚本（沙箱内可跑：无 spawn、无外部依赖）
// 用户终端可另跑 node --test test/cli-bridge.test.mjs（同一断言集合）。
import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { TOOL_DEFS } from "../defs.js";
import { createGuardRules } from "../guard.js";

const byName = Object.fromEntries(TOOL_DEFS.map((d) => [d.name, d]));
const CLI_WHITELIST_RE = /python\.exe"?\s+_cli\.py(?:\s+\S+)*\s*$/i;
// PROJECT_DIR 仅作测试桩（纯字符串断言，无需真实存在）：从本文件位置推导，
// 不硬编码作者机器路径。
const PROJECT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PYTHON = PROJECT_DIR.replace(/\\/g, "/") + "/.venv/Scripts/python.exe";
const cliCommandString = (def, args) => [PYTHON, "_cli.py", ...def.buildArgs(args)].join(" ");

const rules = createGuardRules(PROJECT_DIR);
const inProject = (name, command, extra = {}) => ({
  name,
  arguments: { command, ...extra },
  agent: { session: { header: { cwd: PROJECT_DIR } } },
});
const outsideProject = (name, command) => ({
  name,
  arguments: { command },
  agent: { session: { header: { cwd: "C:/other" } } },
});

let passed = 0;
let failed = 0;
const check = (label, fn) => {
  try {
    fn();
    passed += 1;
    console.log(`  ✓ ${label}`);
  } catch (e) {
    failed += 1;
    console.log(`  ✗ ${label}\n    ${e.message}`);
  }
};

console.log("== folio-tools defs 自检 ==");

check("全部 15 个工具已注册（记忆面 9 + 质量面 6）", () => {
  assert.deepEqual(Object.keys(byName).sort(), [
    "folio_audit", "folio_chunk_read", "folio_cite_audit", "folio_graph_query",
    "folio_load", "folio_pending", "folio_read", "folio_recall", "folio_review",
    "folio_save", "folio_session_start", "folio_spec_diff", "folio_status",
    "folio_theme_verify", "folio_verify",
  ]);
});

check("无参命令 buildArgs", () => {
  assert.deepEqual(byName.folio_status.buildArgs({}), ["status", "--json"]);
  assert.deepEqual(byName.folio_pending.buildArgs({}), ["pending"]);
});

check("单参数命令 buildArgs", () => {
  assert.deepEqual(byName.folio_read.buildArgs({ file: "docs/a.md" }), ["read", "docs/a.md"]);
  assert.deepEqual(byName.folio_chunk_read.buildArgs({ file_path: "docs/a.md#锚点" }), ["chunk-read", "docs/a.md#锚点"]);
  assert.deepEqual(byName.folio_load.buildArgs({ client: "示例客户甲" }), ["load", "示例客户甲"]);
});

check("recall 全参数 buildArgs", () => {
  assert.deepEqual(
    byName.folio_recall.buildArgs({ keywords: ["化工", "设备"], client: "示例客户乙", rerank: true, no_client_filter: true }),
    ["recall", "化工", "设备", "--client", "示例客户乙", "--rerank", "--no-client-filter", "--json"],
  );
  assert.equal(byName.folio_recall.buildArgs({ keywords: "单词" })[1], "单词");
});

check("graph-query 全参数 buildArgs", () => {
  assert.deepEqual(
    byName.folio_graph_query.buildArgs({ client: "通用", type: "decision", node: "n1", edges: "n1" }),
    ["graph-query", "通用", "--node", "n1", "--type", "decision", "--edges", "n1", "--json"],
  );
});

check("session-start buildArgs", () => {
  assert.deepEqual(
    byName.folio_session_start.buildArgs({ user_input: "帮我做方案", client: "示例客户乙" }),
    ["session-start", "帮我做方案", "--client", "示例客户乙", "--json"],
  );
});

check("save extra 键值 buildArgs", () => {
  assert.deepEqual(
    byName.folio_save.buildArgs({ client: "示例客户乙", input: "完成架构图", decisions: "两步走", outputs: "o/x.html", pending: "等确认" }),
    ["save", "示例客户乙", "--input=完成架构图", "--decisions=两步走", "--outputs=o/x.html", "--pending=等确认"],
  );
});

check("质量面 buildArgs（verify/review/cite-audit/audit/theme-verify/spec-diff）", () => {
  assert.deepEqual(byName.folio_verify.buildArgs({ file: "output/x/x.html" }), ["verify", "output/x/x.html"]);
  assert.deepEqual(
    byName.folio_review.buildArgs({ output_file: "output/x/x.html", client: "示例客户乙", spec: "s.yml", adversarial: true, parallel: true }),
    ["review", "output/x/x.html", "--client", "示例客户乙", "--spec", "s.yml", "--adversarial", "--parallel"],
  );
  assert.deepEqual(
    byName.folio_cite_audit.buildArgs({ spec: "s.yml", client: "示例客户乙", output: "output/x/报告.md" }),
    ["cite-audit", "s.yml", "--client", "示例客户乙", "--output", "output/x/报告.md"],
  );
  assert.deepEqual(byName.folio_audit.buildArgs({ mode: "all" }), ["audit", "--mode", "all"]);
  assert.deepEqual(byName.folio_audit.buildArgs({}), ["audit"]);
  assert.deepEqual(byName.folio_theme_verify.buildArgs({ file: "output/x/x.html", client: "示例客户乙" }), ["theme-verify", "output/x/x.html", "示例客户乙"]);
  assert.deepEqual(byName.folio_spec_diff.buildArgs({ spec_a: "a.yml", spec_b: "b.yml" }), ["spec-diff", "a.yml", "b.yml"]);
});

check("guard CLI 白名单兼容（5 个抽样命令）", () => {
  const samples = [
    cliCommandString(byName.folio_status, {}),
    cliCommandString(byName.folio_recall, { keywords: ["化工"], client: "示例客户乙", rerank: true }),
    cliCommandString(byName.folio_save, { client: "示例客户乙", input: "含中文与空格 内容" }),
    cliCommandString(byName.folio_read, { file: "docs/PROJECT_DESIGN.md" }),
    cliCommandString(byName.folio_graph_query, { client: "通用", type: "decision" }),
  ];
  for (const s of samples) assert.ok(CLI_WHITELIST_RE.test(s), `guard 白名单应放行: ${s}`);
});

check("required 参数可被 buildArgs 消费（不抛异常）", () => {
  for (const def of TOOL_DEFS) {
    for (const [k, v] of Object.entries(def.parameters)) {
      if (v && typeof v === "object" && v.required) {
        const fake = { [k]: v.type === "array" ? ["x"] : v.type === "boolean" ? true : "x" };
        assert.doesNotThrow(() => def.buildArgs(fake), `${def.name}.buildArgs(${k})`);
      }
    }
  }
});

console.log("== guard 纯函数自检 ==");

check("isProtectedWrite：output 交付物拦截 / refs 拦截 / 中间产物放行 / 项目外放行", () => {
  assert.equal(rules.isProtectedWrite(`${PROJECT_DIR}/output/x/测试.html`), true);
  assert.equal(rules.isProtectedWrite(`${PROJECT_DIR}/output/x/测试.pptx`), true);
  assert.equal(rules.isProtectedWrite(`${PROJECT_DIR}/refs/a.md`), true);
  assert.equal(rules.isProtectedWrite(`${PROJECT_DIR}/output/x/spec.yml`), false);
  assert.equal(rules.isProtectedWrite("C:/other/output/x/测试.html"), false);
});

check("checkPythonExec：非 CLI python 直调 deny / CLI 白名单放行 / 项目外放行", () => {
  const denied = rules.checkPythonExec(inProject("pwsh", "python -c \"print(1)\""));
  assert.equal(denied?.kind, "deny");
  assert.match(denied.reason, /folio-guard/);
  assert.equal(rules.checkPythonExec(inProject("pwsh", `${PROJECT_DIR}/.venv/Scripts/python.exe _cli.py status`)), null);
  assert.equal(rules.checkPythonExec(outsideProject("pwsh", "python -c \"print(1)\"")), null);
});

check("checkShellWrite：shell 直写 output 交付物 deny / refs 操作 deny / 普通命令放行", () => {
  const out = rules.checkShellWrite(inProject("pwsh", `Set-Content "${PROJECT_DIR}/output/x/测试.html" -Value x`));
  assert.equal(out?.kind, "deny");
  assert.match(out.reason, /output/);
  const refs = rules.checkShellWrite(inProject("pwsh", `Remove-Item "${PROJECT_DIR}/refs/a.md"`));
  assert.equal(refs?.kind, "deny");
  assert.match(refs.reason, /refs/);
  assert.equal(rules.checkShellWrite(inProject("pwsh", "Get-ChildItem .")), null);
});

check("isCommandInProject：cwd/workdir 项目内 true / 项目外 false / 相对路径 false", () => {
  assert.equal(rules.isCommandInProject(inProject("pwsh", "echo hi")), true);
  assert.equal(rules.isCommandInProject({
    name: "pwsh",
    arguments: { command: "echo hi", workdir: `${PROJECT_DIR}/sub` },
    agent: { session: { header: { cwd: "C:/elsewhere" } } },
  }), true);
  assert.equal(rules.isCommandInProject(outsideProject("pwsh", "echo hi")), false);
  assert.equal(rules.isCommandInProject({
    name: "pwsh",
    arguments: { command: "echo hi", workdir: "relative/path" },
  }), false);
});

console.log(`== 结果: ${passed} 通过 / ${failed} 失败 ==`);
process.exit(failed > 0 ? 1 : 0);
