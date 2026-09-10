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

/**
 * 每会话只放行一次的幂等门（入口提醒用）。
 *
 * 背景：`agent/session-start` 在 0.1.5 实测会触发两次，导致界面出现「2 条排队消息」。
 * 以会话 id 为键，第一次放行、重复触发忽略；空 id 不误伤（返回 true，由调用方用
 * WeakSet 兜底）。容量有界，超出后淘汰最早记录，避免长驻宿主内存无界增长。
 */
export function makeSessionStartGate(maxTracked = 1000) {
  const limit = Number.isInteger(maxTracked) && maxTracked > 0 ? maxTracked : 1000;
  const seen = new Set();
  return {
    /** 该会话是否首次触发；同一 id 第二次起返回 false。 */
    should(sessionId) {
      if (typeof sessionId !== "string" || sessionId.length === 0) return true;
      if (seen.has(sessionId)) return false;
      seen.add(sessionId);
      if (seen.size > limit) {
        const oldest = seen.values().next().value;
        if (oldest !== undefined) seen.delete(oldest);
      }
      return true;
    },
    /** 该会话是否已被放行过（供排查/测试）。 */
    has(sessionId) {
      return seen.has(sessionId);
    },
    clear() {
      seen.clear();
    },
  };
}
