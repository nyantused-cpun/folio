# -*- coding: utf-8 -*-
"""_cloud_llm 联网搜索子模块（T9 拆分自 _cloud_llm.py，2026-09-01）。
承载：tavily_search / byte_search / web_search。"""
import os
from urllib.parse import urlparse

# --- #57/Q2 方案A（2026-09-06）：改从 _cloud_transport 真源取 _post_json，
# 不再依赖母文件（旧 from _cloud_llm import 与母文件尾部 re-export 互为导入环）。
# 命名空间绑定保持不变：存量测试 patch(search_mod, "_post_json") 仍命中。
from _cloud_transport import _post_json

def _get_tavily_key():
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key or not key.isascii():
        return None
    return key


def _get_volcengine_keys():
    ak = os.environ.get("VOLCENGINE_ACCESS_KEY", "").strip()
    sk = os.environ.get("VOLCENGINE_SECRET_KEY", "").strip()
    api_key = os.environ.get("ASK_ECHO_SEARCH_INFINITY_API_KEY", "").strip()
    return ak, sk, api_key


def _byte_search_ready():
    """byte_search 可用判定：api_key 或 AK/SK 双 key 齐备（与 byte_search 门禁同口径）。

    旧 web_search 用 any() 单 key 即判可用，与 byte_search「api_key 或
    AK+SK 缺一不可」的要求不一致，只配一半 key 会被误判可用、实际调用才报未配置。
    """
    ak, sk, api_key = _get_volcengine_keys()
    return bool(api_key) or bool(ak and sk)


def tavily_search(query, max_results=5):
    """调用 Tavily 搜索 API（第一检索引擎）。
    
    返回: (results_list, http_status_code) 或 (None, status_code)
    """
    key = _get_tavily_key()
    if not key:
        print("[search] Tavily API key 未配置")
        return None, 0

    url = "https://api.tavily.com/search"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
    }

    data, status = _post_json(url, headers, payload, timeout=30)
    if not data:
        print(f"[search] Tavily 请求失败: HTTP {status}")
        return None, status

    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "") or r.get("raw_content", ""),
            "score": r.get("score", 0),
            "source": "tavily",
        })
    return results, status


def byte_search(query, max_results=5):
    """调用豆包搜索（火山引擎 Search Infinity，第二检索引擎）。

    API 文档：https://www.volcengine.com/docs/87772/2272953
    """
    ak, sk, api_key = _get_volcengine_keys()

    if not api_key and (not ak or not sk):
        print("[search] 字节搜索 API key 未配置（需要 ASK_ECHO_SEARCH_INFINITY_API_KEY 或 VOLCENGINE_ACCESS_KEY/SECRET_KEY）")
        return None

    # API Key 接入（推荐）
    if api_key:
        url = "https://open.feedcoopapi.com/search_api/web_search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "Query": query,
            "SearchType": "web",
            "Count": max_results,
        }
    # AK/SK 接入（TOP 网关）
    else:
        url = "https://mercury.volcengineapi.com?Action=WebSearch&Version=2025-01-01"
        headers = {
            "Content-Type": "application/json",
            "X-Volcengine-Access-Key": ak,
            "X-Volcengine-Secret-Key": sk,
        }
        payload = {
            "Query": query,
            "SearchType": "web",
            "Count": max_results,
        }

    data, status = _post_json(url, headers, payload, timeout=30)
    if not data:
        print(f"[search] 字节搜索请求失败: HTTP {status}")
        return None

    # 检查 API 层错误
    err = data.get("ResponseMetadata", {}).get("Error")
    if err:
        print(f"[search] 字节搜索 API 错误: {err.get('Code', '')} {err.get('Message', '')}")
        return None

    results = []
    for r in data.get("Result", {}).get("WebResults", []):
        results.append({
            "title": r.get("Title", ""),
            "url": r.get("Url", ""),
            "content": r.get("Summary", "") or r.get("Snippet", ""),
            "score": r.get("RankScore", 0),
            "source": "byte_search",
        })
    return results


def web_search(query, max_results=5, engines=None):
    """联网搜索：支持多引擎融合。
    
    engines: 指定引擎列表，如 ["tavily", "byte_search"]，None 时自动检测可用引擎。
    返回合并后的结果列表，按 score 降序。
    
    降级策略：优先使用 Tavily，如果配额用完（429错误）则自动降级到字节搜索。
    """
    if engines is None:
        engines = []
        if _get_tavily_key():
            engines.append("tavily")
        if _byte_search_ready():
            engines.append("byte_search")
        if not engines:
            print("[search] 未配置任何搜索引擎 key（TAVILY_API_KEY / ASK_ECHO_SEARCH_INFINITY_API_KEY / VOLCENGINE_ACCESS_KEY），联网搜索不可用")
            print("  提示：在 .env 中配置，或运行 python _cli.py key-doctor 检查")
            return None

    all_results = []
    tavily_quota_exceeded = False
    
    for engine in engines:
        try:
            if engine == "tavily":
                # 如果 Tavily 配额已用完，跳过
                if tavily_quota_exceeded:
                    print("[search] Tavily 配额已用完，跳过")
                    continue
                results, status = tavily_search(query, max_results)
                # 检测 Tavily 429 错误（配额用完）
                if status == 429:
                    tavily_quota_exceeded = True
                    print("[search] Tavily 配额已用完（HTTP 429），降级到字节搜索")
                    continue
                if results:
                    all_results.extend(results)
            elif engine == "byte_search":
                results = byte_search(query, max_results)
                if results:
                    all_results.extend(results)
                    # 如果字节搜索成功且之前 Tavily 配额用完，记录日志
                    if tavily_quota_exceeded:
                        print("[search] 字节搜索成功，已降级使用")
            else:
                continue
        except Exception as e:
            print(f"[search] 引擎 {engine} 调用异常: {e}")
            # 如果 Tavily 异常且是配额相关错误，标记配额用完
            if engine == "tavily" and "429" in str(e):
                tavily_quota_exceeded = True
                print("[search] Tavily 配额异常（429），标记配额已用完")
            continue

    if not all_results:
        print("[search] 所有引擎均返回空结果")
        return None

    # URL 去重（同一 URL 只保留 score 最高的）
    seen_urls = {}
    for r in all_results:
        url = r.get("url", "")
        if not url:
            continue
        if url not in seen_urls or r.get("score", 0) > seen_urls[url].get("score", 0):
            seen_urls[url] = r
    all_results = list(seen_urls.values())

    # 英文域名加权：非 .cn 域名加 0.1 bonus
    # 域后缀匹配（正确性 P3）：旧子串 ".cn" in url 会把 *.cn.example.com 这类
    # URL 误判为 .cn 域错失加权；urlparse 取 hostname 后按域后缀判定
    for r in all_results:
        url = r.get("url", "")
        host = urlparse(url).hostname or url.split("/")[0]
        if host and not host.lower().endswith(".cn"):
            r["score"] = r.get("score", 0) + 0.1

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results[:max_results]