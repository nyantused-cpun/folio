# -*- coding: utf-8 -*-
"""召回质量评估器（recall-eval）核心逻辑。

L5 级确定性评估器，只读 recall() 返回的结构化结果做判定，不改召回算法。
本模块纯函数为主，可独立单测。run_eval 静默调 recall，单条失败不中断。

实施依据：docs/dev_plan_recall_eval_2026-07-19.md
任务清单：docs/dev_plan_recall_eval_tasks_2026-07-19.md Issue 1+2+4
"""

import os
import json
from datetime import datetime

__all__ = [
    "DEFAULT_EVAL_SET_PATH",
    "DEFAULT_BASELINE_PATH",
    "FALLBACK_MARKER",
    "DEFAULT_TOLERANCES",
    "load_eval_set",
    "normalize_path",
    "is_hit",
    "detect_fallback",
    "compute_metrics",
    "run_eval",
    "save_baseline",
    "compare_baseline",
    "estimate_api_calls",
]

DEFAULT_EVAL_SET_PATH = os.path.join("_knowledge", "eval", "golden_queries.yml")
DEFAULT_BASELINE_PATH = os.path.join("_knowledge", "eval", "baseline.json")

# recall 在 RRF 最高分 < 阈值时打印此标志（_recall.py:136）
FALLBACK_MARKER = "降级到关键词模式"

# 回归门禁默认容差（首次 baseline 跑完后可校准写回 baseline.json）
# Hit@3 容差 -5pp（0.05），MRR 容差 -0.05
DEFAULT_TOLERANCES = {"hit_at_3": 0.05, "mrr": 0.05}


# ===== Issue 1：纯函数核心 =====


def normalize_path(p):
    """路径规范化：统一分隔符 -> /、去工作目录前缀、去 ./ 前缀、去 #anchor 后缀、strip、小写。

    大小写不敏感比较（Windows 文件系统不敏感 + 评估集 expect 手填可能不一致）。
    recall() 返回的 path 可能是绝对路径（<工作目录>\\_knowledge\\...），
    expect 是相对路径（_knowledge/...），去工作目录前缀后才能匹配。
    """
    if not p:
        return ""
    s = str(p).strip()
    s = s.replace("\\", "/")
    # 去工作目录前缀（绝对路径 -> 相对路径）
    cwd = os.getcwd().replace("\\", "/").rstrip("/")
    if s.startswith(cwd + "/"):
        s = s[len(cwd) + 1:]
    while s.startswith("./"):
        s = s[2:]
    if "#" in s:
        s = s.split("#", 1)[0]
    return s.strip().lower()


def load_eval_set(path):
    """读 YAML 评估集，返回 list[dict]。

    每条字段：id / query / client(可选) / expect(list[str]，可为空=负样本) / note(可选)。
    缺 id/query/expect 报 ValueError；文件不存在报 FileNotFoundError。
    """
    import yaml  # venv 已有 PyYAML

    if not os.path.exists(path):
        raise FileNotFoundError(f"评估集不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"评估集根节点必须是 list，实际 {type(data).__name__}")

    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"第 {i+1} 条不是 dict: {item!r}")
        for k in ("id", "query", "expect"):
            if k not in item:
                raise ValueError(f"第 {i+1} 条缺字段 '{k}': {item!r}")
        expect = item["expect"]
        if expect is None:
            expect = []
        if not isinstance(expect, list):
            raise ValueError(
                f"第 {i+1} 条 expect 必须是 list，实际 {type(expect).__name__}"
            )
        out.append(
            {
                "id": str(item["id"]),
                "query": str(item["query"]),
                "client": item.get("client"),
                "expect": [str(p) for p in expect],
                "note": item.get("note", ""),
            }
        )
    return out


def is_hit(result_paths, expect):
    """命中判定：返回第一个命中的排位（0-based）。

    - expect 为空（负样本）-> 永远 None
    - 未命中 -> None
    - 命中 -> 排位整数（0-based）
    """
    if not expect:
        return None
    norm_expect = {normalize_path(p) for p in expect}
    for rank, rp in enumerate(result_paths):
        if normalize_path(rp) in norm_expect:
            return rank
    return None


def detect_fallback(stdout_buf):
    """检测 stdout 缓冲里是否出现 fallback 降级标志。"""
    if not stdout_buf:
        return False
    return FALLBACK_MARKER in stdout_buf


def compute_metrics(per_query):
    """计算评估指标。

    参数：
        per_query: list[dict]，每条至少含：
            id, query, expect(list), results(list[dict] 含 path),
            hit_rank(int|None), is_negative(bool), fallback(bool), error(str|None)

    返回：
        {
            "total": int,                 # 正样本总数
            "hit_at_1": float,            # 命中且 rank==0 的占比
            "hit_at_3": float,            # 命中且 rank<3 的占比（核心指标）
            "mrr": float,                 # 命中排位倒数均值
            "neg_total": int,
            "neg_pass_no_hit": int,       # 负样本无命中（通过）
            "neg_pass_fallback": int,     # 负样本触发降级（通过）
            "neg_fail": int,              # 负样本有命中且未降级（不通过）
            "misses": [{id, query, top3_paths, error?}],
        }
    """
    total = 0
    hit1 = 0
    hit3 = 0
    mrr_sum = 0.0
    neg_total = 0
    neg_pass_no_hit = 0
    neg_pass_fallback = 0
    neg_fail = 0
    misses = []

    for item in per_query:
        if item.get("error"):
            # 失败条目不参与指标统计，但记入 misses 供人工分析
            misses.append(
                {
                    "id": item["id"],
                    "query": item["query"],
                    "top3_paths": [],
                    "error": item["error"],
                }
            )
            continue

        is_neg = item.get("is_negative", False)
        hit_rank = item.get("hit_rank")
        fallback = item.get("fallback", False)

        if is_neg:
            neg_total += 1
            if fallback:
                neg_pass_fallback += 1
            elif hit_rank is None:
                neg_pass_no_hit += 1
            else:
                # 负样本有命中且未触发降级 = 不通过
                neg_fail += 1
            continue

        total += 1
        if hit_rank is not None:
            if hit_rank == 0:
                hit1 += 1
            if hit_rank < 3:
                hit3 += 1
            mrr_sum += 1.0 / (hit_rank + 1)
        else:
            misses.append(
                {
                    "id": item["id"],
                    "query": item["query"],
                    "top3_paths": [
                        r.get("path", "") for r in item.get("results", [])[:3]
                    ],
                }
            )

    return {
        "total": total,
        "hit_at_1": round(hit1 / total, 4) if total else 0.0,
        "hit_at_3": round(hit3 / total, 4) if total else 0.0,
        "mrr": round(mrr_sum / total, 4) if total else 0.0,
        "neg_total": neg_total,
        "neg_pass_no_hit": neg_pass_no_hit,
        "neg_pass_fallback": neg_pass_fallback,
        "neg_fail": neg_fail,
        "misses": misses,
    }


# ===== Issue 2：run_eval 执行器 =====


def run_eval(eval_set, *, rerank=False, use_embedding=True, limit=None):
    """对评估集每条 query 静默调 recall()，返回结构化结果。

    参数：
        eval_set: list[dict]，来自 load_eval_set
        rerank / use_embedding: 透传给 recall（三链路由调用方分三次调）
        limit: 只跑前 N 条（调试用）

    返回：
        {
            "chain": "rrf"|"rerank"|"bm25_only",
            "config": <recall_config.yml 快照 dict>,
            "per_query": [...],
            "metrics": {...},  # compute_metrics 输出
        }
    """
    import io
    import contextlib

    from _session import recall
    from _recall import _load_recall_config

    config = _load_recall_config()
    if limit is not None:
        eval_set = eval_set[:limit]

    if rerank:
        chain = "rerank"
    elif not use_embedding:
        chain = "bm25_only"
    else:
        chain = "rrf"

    per_query = []
    for item in eval_set:
        entry = {
            "id": item["id"],
            "query": item["query"],
            "client": item.get("client"),
            "expect": item["expect"],
            "is_negative": len(item["expect"]) == 0,
            "results": [],
            "hit_rank": None,
            "fallback": False,
            "error": None,
        }
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                results = recall(
                    item["query"],
                    client_name=item.get("client"),
                    rerank=rerank,
                    use_embedding=use_embedding,
                    return_results=True,
                    client_filter=None,  # 让 recall 自动决策
                )
            entry["results"] = results or []
            entry["fallback"] = detect_fallback(buf.getvalue())
            entry["hit_rank"] = is_hit(
                [r.get("path", "") for r in entry["results"]],
                item["expect"],
            )
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"

        per_query.append(entry)

    return {
        "chain": chain,
        "config": config,
        "per_query": per_query,
        "metrics": compute_metrics(per_query),
    }


def estimate_api_calls(n_queries, *, rerank=False, use_embedding=True):
    """预估云端 API 调用次数（用于成本守门）。

    - embedding（rrf / rerank 链路）：每 query 1 次
    - rerank（仅 rerank 链路）：每 query 多 1 次
    - bm25_only 链路：0 次
    """
    calls = 0
    if use_embedding:
        calls += n_queries  # embedding 调用
    if rerank:
        calls += n_queries  # SiliconFlow rerank
    return calls


# ===== Issue 4：baseline 落盘 + gate 门禁 =====


def save_baseline(report, path=DEFAULT_BASELINE_PATH, tolerances=None):
    """把评估报告写为 baseline.json。

    report: dict，键含 chains（三链路 metrics）+ config
    tolerances: 可选，覆盖默认容差
    """
    tol = dict(DEFAULT_TOLERANCES)
    if tolerances:
        tol.update(tolerances)

    baseline = {
        "created_at": datetime.now().isoformat(),
        "config": report.get("config", {}),
        "chains": report.get("chains", {}),
        "tolerances": tol,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    return baseline


def compare_baseline(current_chains, baseline, tolerances=None):
    """对比当前指标与 baseline，返回 (passed, diffs)。

    每条链路比较 hit_at_3 和 mrr，下降超容差 -> 该项 fail。
    baseline 缺该链路 -> 跳过（不算回归）。
    config 不一致由调用方单独处理（只告警不阻断）。
    """
    tol = dict(DEFAULT_TOLERANCES)
    if tolerances:
        tol.update(tolerances)
    # baseline 自身容差优先
    tol.update(baseline.get("tolerances", {}))

    base_chains = baseline.get("chains", {})
    diffs = []
    passed = True
    for chain_name, cur_metrics in current_chains.items():
        base_metrics = base_chains.get(chain_name)
        if base_metrics is None:
            continue
        for metric in ("hit_at_3", "mrr"):
            base_v = base_metrics.get(metric)
            cur_v = cur_metrics.get(metric)
            if base_v is None or cur_v is None:
                continue
            delta = cur_v - base_v
            tol_v = tol.get(metric, 0.05)
            ok = delta >= -tol_v
            if not ok:
                passed = False
            diffs.append(
                {
                    "chain": chain_name,
                    "metric": metric,
                    "baseline": base_v,
                    "current": cur_v,
                    "delta": round(delta, 4),
                    "tolerance": tol_v,
                    "passed": ok,
                }
            )
    return passed, diffs
