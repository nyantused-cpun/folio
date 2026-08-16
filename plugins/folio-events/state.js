// @nyantused/folio-dsh-events 纯逻辑模块（零外部依赖，可独立单测）

/** 从 tool/call 会话事件提取客户名（folio_session_start / folio_save 的 client 参数）。 */
export function extractClientFromToolCall(evt) {
  if (!evt || evt.type !== "tool/call") return null;
  const name = evt.data?.name ?? evt.name;
  if (name !== "folio_session_start" && name !== "folio_save") return null;
  const args = evt.data?.arguments ?? evt.data?.args ?? evt.arguments;
  if (args && typeof args === "object" && typeof args.client === "string" && args.client) {
    return args.client;
  }
  // 兜底：arguments 为 JSON 字符串
  if (typeof args === "string") {
    try {
      const parsed = JSON.parse(args);
      if (parsed && typeof parsed.client === "string" && parsed.client) return parsed.client;
    } catch { /* noop */ }
  }
  return null;
}

/** 冷却器：同 key 在 cooldownMs 内只放行一次。 */
export function makeCooldown(cooldownMs) {
  const lastAt = new Map();
  return {
    /** 若距上次放行不足 cooldownMs 返回 false；否则记录并放行。首次调用恒放行。 */
    should(key, now = Date.now()) {
      const has = lastAt.has(key);
      const last = lastAt.get(key) ?? 0;
      if (has && now - last < cooldownMs) return false;
      lastAt.set(key, now);
      return true;
    },
    clear(key) {
      lastAt.delete(key);
    },
  };
}
