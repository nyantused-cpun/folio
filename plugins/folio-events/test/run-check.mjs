// @nyantused/folio-dsh-events 纯逻辑自检（沙箱内可跑：无 spawn）
import assert from "node:assert/strict";
import { extractClientFromToolCall, makeCooldown, makeSessionStartGate } from "../state.js";

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

console.log("== folio-events state 自检 ==");

check("extractClientFromToolCall：folio_session_start 取 client", () => {
  assert.equal(
    extractClientFromToolCall({ type: "tool/call", data: { name: "folio_session_start", arguments: { client: "示例客户乙" } } }),
    "示例客户乙",
  );
});

check("extractClientFromToolCall：folio_save 取 client", () => {
  assert.equal(
    extractClientFromToolCall({ type: "tool/call", name: "folio_save", data: { args: { client: "通用" } } }),
    "通用",
  );
});

check("extractClientFromToolCall：其他工具忽略", () => {
  assert.equal(extractClientFromToolCall({ type: "tool/call", data: { name: "pwsh", arguments: { command: "x" } } }), null);
  assert.equal(extractClientFromToolCall({ type: "user/message", data: {} }), null);
  assert.equal(extractClientFromToolCall(null), null);
});

check("extractClientFromToolCall：arguments 为 JSON 字符串兜底", () => {
  assert.equal(
    extractClientFromToolCall({ type: "tool/call", data: { name: "folio_save", arguments: '{"client":"示例客户甲"}' } }),
    "示例客户甲",
  );
});

check("extractClientFromToolCall：client 缺失/空串返回 null", () => {
  assert.equal(extractClientFromToolCall({ type: "tool/call", data: { name: "folio_save", arguments: {} } }), null);
  assert.equal(extractClientFromToolCall({ type: "tool/call", data: { name: "folio_save", arguments: { client: "" } } }), null);
});

check("makeCooldown：冷却窗口内只放行一次", () => {
  const c = makeCooldown(1000);
  assert.equal(c.should("a", 100), true);
  assert.equal(c.should("a", 500), false);
  assert.equal(c.should("a", 1099), false);
  assert.equal(c.should("a", 1100), true);
});

check("makeCooldown：不同 key 互不影响 + clear 重置", () => {
  const c = makeCooldown(1000);
  assert.equal(c.should("a", 100), true);
  assert.equal(c.should("b", 100), true);
  c.clear("a");
  assert.equal(c.should("a", 200), true);
});

check("makeSessionStartGate：同会话只放行一次，不同会话互不影响", () => {
  const gate = makeSessionStartGate();
  assert.equal(gate.should("sess-1"), true, "首次放行");
  assert.equal(gate.should("sess-1"), false, "重复触发忽略（修 2 条排队消息）");
  assert.equal(gate.should("sess-2"), true, "不同会话不受影响");
});

check("makeSessionStartGate：空 id 不误伤 + 容量淘汰最旧", () => {
  const gate = makeSessionStartGate(2);
  assert.equal(gate.should(""), true);
  assert.equal(gate.should("a"), true);
  assert.equal(gate.should("b"), true);
  assert.equal(gate.should("c"), true);
  assert.equal(gate.has("a"), false, "最早记录被淘汰");
  assert.equal(gate.has("b"), true);
  assert.equal(gate.has("c"), true);
});

console.log(`== 结果: ${passed} 通过 / ${failed} 失败 ==`);
process.exit(failed > 0 ? 1 : 0);
