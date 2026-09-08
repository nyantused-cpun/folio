# -*- coding: utf-8 -*-
"""云端 HTTP 传输层（#57/Q2 方案A 最小下沉，2026-09-06 自 _cloud_llm.py 迁出）。

承载：_post_json（POST + 指数退避重试）与调试回显门控
（_DEBUG_ECHO_ENV / _debug_echo_enabled）。仅依赖标准库，
供 _cloud_llm / _cloud_llm_search / _cloud_llm_vision 共用，
消除子模块反向依赖母文件的 mother→vision→mother 导入环。

patch 纪律（B4 theme 教训）：新测试打点一律指向本模块真源
（patch _cloud_transport._post_json），勿 patch 消费方转载名。
"""
import os
import json
import time

# ============================================================
# 调试回显开关（安全审查 P3）：错误响应体 / host-mode prompt 均为
# 服务器或客户材料可控内容，默认不回显全文，仅显式打开时输出。
# 复用 _cli_cmds_qa web-search 回显门控同款 DEBUG_REMOTE_ECHO，单一开关统一口径
# ============================================================
_DEBUG_ECHO_ENV = "DEBUG_REMOTE_ECHO"


def _debug_echo_enabled():
    """调试回显开关：DEBUG_REMOTE_ECHO 显式打开（1/true/yes）才回显可控内容。"""
    return os.environ.get(_DEBUG_ECHO_ENV, "").strip().lower() in ("1", "true", "yes")


def _post_json(url, headers, payload, timeout=30, max_retries=3):
    """发 POST 请求，带指数退避重试。返回 (json_dict, http_status) 或 (None, status)。"""
    try:
        import requests
    except ImportError:
        print("[cloud_llm] 需要 requests 库：pip install requests")
        return None, 0

    last_status = 0
    for attempt in range(max_retries):
        try:
            # 用 data + encode 确保 UTF-8 编码，避免 latin-1 问题
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            resp = requests.post(url, headers=headers, data=body, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), 200
            if resp.status_code == 429 or resp.status_code >= 500:
                last_status = resp.status_code
                wait = 2 ** attempt
                print(f"[cloud_llm] HTTP {resp.status_code}，{wait}s 后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            # 响应体为服务器可控内容（安全审查 P3）：默认只报状态码不回显，
            # 防 HTML/日志注入与密钥等敏感信息落会话日志
            if _debug_echo_enabled():
                print(f"[cloud_llm] HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                print(f"[cloud_llm] HTTP {resp.status_code}（响应体回显需设 {_DEBUG_ECHO_ENV}=1）")
            return None, resp.status_code
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[cloud_llm] 请求异常: {e}，{wait}s 后重试")
                time.sleep(wait)
            else:
                print(f"[cloud_llm] 请求失败（已重试 {max_retries} 次）: {e}")
                return None, 0
    return None, last_status
