# -*- coding: utf-8 -*-
"""召回模块：BM25 + Embedding 双路召回 + RRF 融合 + 关键词降级。

从 _session.py 拆分（候选 4 · 模块化），依赖 _context；
read_chunk 按需使用 _graph._split_decision_blocks（及 _embed_index）。
"""
import os
import json
import re

from _paths import SCRIPT_DIR
from _context import list_clients, get_context_path


__all__ = [
    # 常量
    "_RECALL_CONFIG",
    # 函数
    "_load_recall_config",
    "recall", "_keyword_fallback", "_embedding_recall",
    "_rrf_fuse", "_dedup_by_doc", "_apply_bm25_seats",
    "_detect_client_from_path", "_read_snippet", "read_chunk",
]


def _load_recall_config():
    """加载召回参数配置（recall_config.yml）。文件不存在或损坏时用默认值。

    P0-1 修复：默认值与 recall_config.yml 保持一致。
    - rrf.k: 10（与 yaml 一致，原 60 会导致 rank 差异被压平）
    - rrf.fallback_threshold: 0.05（与 yaml 一致，缺失时降级特性会静默失效）
    """
    config_path = os.path.join(SCRIPT_DIR, "recall_config.yml")
    defaults = {
        "rrf": {"k": 10, "fallback_threshold": 0.05},
        "embedding": {"threshold": 0.1, "top_k": 20},
        "bm25": {"top_k": 20},
        "rerank": {"top_k": 5},
        "bm25_seat": {"enabled": True, "top_docs": 3, "min_score_ratio": 0.95},
    }
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for section, vals in defaults.items():
            if section not in data:
                data[section] = vals
            else:
                for k, v in vals.items():
                    if k not in data[section]:
                        data[section][k] = v
        return data
    except Exception:
        return defaults


_RECALL_CONFIG = _load_recall_config()


# ---- 兼容 no-op 参数退役（W1 记忆收敛遗留 → 0907 计划 L6 清偿）----
# use_graph_expansion 曾以签名占位兼容旧调用方（M2-R2 图扩展移除，R4 ablation
# 零增量裁决）；2026-09-07 调用方（_cli_cmds_mem / _recall_eval / CLI 旗标 /
# tests）全部清零，参数正式从签名删除。回退锚点：git 历史。
def recall(input_text, force_keyword=False, client_name=None, rerank=True,
           use_embedding=True, return_results=False, client_filter=None,
           permanent_only=False, use_aliases=True,
           use_query_rewrite=True):
    """召回相关历史项目。BM25 + Embedding 双路召回 + RRF 融合。

    client_name: 指定客户时用其别名展开查询，并在索引层按客户隔离搜索
    rerank: True 时调云端 LLM 精排
    use_embedding: True 时启用 Embedding 语义召回（需要 ZHIPU_API_KEY）
    return_results: True 时返回结构化结果列表（RAG 注入用），False 时只打印
    client_filter: True 时在索引层只搜索 client_name 客户的文档。
                   None（默认）时自动按是否有 client_name 决定。
    permanent_only: True 时只保留 permanent 决策（task 决策排除；非决策结果不受影响）
    use_aliases: True 时对指定客户展开别名（默认）；False 时不展开。
    use_query_rewrite: True 时启用查询改写（T2，默认）；False 时不改写（A0 基线/评测用）。


    返回（return_results=True 时）：
        [{"client", "score", "path", "snippet", "parent_context",
          "source", "mode", "degraded"}, ...] 或 None
        source: "客户=X | 文档=Y"（现有 print 的来源标注数据化）
        mode: 实际生效链路（"BM25 + Embedding RRF" / "BM25" / "Embedding" / "关键词降级"）
        degraded: 任一降级路径触发即 True（请求 Embedding 无返回 / RRF 阈值 / 依赖缺失 / 关键词 fallback）
        decision 结果额外带 persistence / scope（P6-2：缺失默认 permanent / client）
    """
    # T9：降级状态跟踪。任一降级路径（见下方分支）触发后置 True，
    # 结果 item 的 "degraded" 键随之置位，供 folio_recall / RAG 注入识别质量折扣。
    degraded = False
    if not force_keyword:
        try:
            from _bm25 import query_bm25  # noqa: F401  # 可用性探测（调用在 query 路径）
            # P2-3: client_name 未指定时自动从查询文本检测
            if not client_name:
                try:
                    from _aliases import detect_client_in_query
                    detected = detect_client_in_query(input_text)
                    if detected:
                        client_name = detected
                        print(f"[recall] 自动检测到客户: {client_name}")
                except Exception as e:
                    # P1-3：原静默 pass，改为打印警告（不影响主流程）
                    print(f"[warn] 客户自动检测失败: {e}")

            # I-2 T2 查询改写：高置信单路（用改写查询），低置信双路（原 0.4 + 改写 0.6）
            # 失败/禁用回退原查询，degraded 标记 REWRITE_FALLBACK
            _queries = [(input_text, 1.0)]
            _rewrite = None
            _qr_cfg = _RECALL_CONFIG.get("query_rewrite", {}) or {}
            if use_query_rewrite and _qr_cfg.get("enabled", True):
                from _query_rewrite import rewrite_query
                _rw = rewrite_query(input_text, client=client_name)
                _rewrite = {
                    "rewritten": _rw.get("rewritten", input_text),
                    "confidence": _rw.get("confidence", 0.0),
                    "changes": _rw.get("changes", []),
                    "degraded": _rw.get("degraded", []),
                }
                if _rw.get("degraded"):
                    degraded = True
                _thr = _qr_cfg.get("confidence_threshold", 0.6)
                if _rewrite["confidence"] >= _thr:
                    _queries = [(_rewrite["rewritten"], 1.0)]
                else:
                    _queries = [(input_text, 0.4), (_rewrite["rewritten"], 0.6)]
                    print(f"[query-rewrite] 低置信({_rewrite['confidence']:.2f}<{_thr}) "
                          f"双路：原查询 0.4 + 改写 0.6")

            # 别名展开（查询侧）——逐条查询
            if client_name and use_aliases:
                try:
                    from _aliases import load_client, normalize_query_with_aliases
                    aliases = load_client(client_name)
                    _queries = [
                        (normalize_query_with_aliases(
                            q, client_name=client_name, aliases=aliases,
                            use_aliases=True), w)
                        for q, w in _queries
                    ]
                except Exception as e:
                    print(f"[warn] {client_name} 别名加载失败: {e}")

            # client_filter 自动决策：未显式指定时，有 client_name 就开启索引层隔离
            if client_filter is None:
                client_filter = client_name
            # 索引层过滤参数：传客户名给 BM25/Embedding 在 top_k 选取前过滤
            index_filter = client_name if client_filter else None
            if index_filter:
                print(f"[recall] 索引层按客户隔离: {index_filter}")

            # I-1 出域开关：客户 cloud_policy 覆盖调用方参数（recall 与云端层同源解析）
            #   off → 仅 BM25+本地（熔断 Embedding/Chat/Rerank），degraded 标记质量折扣
            #   embedding_only → 熔断 Chat/Rerank（Embedding 放行）
            if client_name:
                from _cloud_llm import resolve_cloud_policy as _rcp
                _cloud_policy = _rcp(client_name)
                if _cloud_policy == "off":
                    if use_embedding or rerank:
                        print(f"[cloud-policy] 客户 {client_name} 出域关闭（off）："
                              f"仅 BM25+本地处理，云端 Embedding/Rerank 熔断")
                    use_embedding = False
                    rerank = False
                    degraded = True
                elif _cloud_policy == "embedding_only":
                    if rerank:
                        print(f"[cloud-policy] 客户 {client_name} 仅 embedding 出域"
                              f"（embedding_only）：Chat/Rerank 熔断")
                    rerank = False

            # I-2 T7：逐查询检索（BM25 + Embedding 并发 → 硬隔离 → RRF 融合）
            _groups = []
            _last_s = None
            cross_client_filtered = 0
            mode = None
            for _q, _w in _queries:
                _s = _single_query_retrieve(
                    _q, index_filter, use_embedding, client_name, _RECALL_CONFIG)
                _last_s = _s
                degraded = degraded or _s["degraded"]
                cross_client_filtered += _s["cross_client_filtered"]
                if _s["results"]:
                    _groups.append((_s["results"], _w))
                if mode is None and _s["mode"]:
                    mode = _s["mode"]
            if cross_client_filtered > 0:
                print(f"[recall] 硬隔离: 丢弃 {cross_client_filtered} 条跨客户候选"
                      f"（cross_client_filtered={cross_client_filtered}）")

            # 合并：单查询直接用；多查询（低置信双路）按 0.4/0.6 加权 RRF 合并
            if len(_groups) == 1:
                results = _groups[0][0]
            elif len(_groups) > 1:
                results = _rrf_fuse_weighted(_groups, k=_RECALL_CONFIG["rrf"]["k"])
                mode = f"{mode} (双查询)"
            else:
                results = None
                mode = None
            base_mode = mode  # T9：rerank 前的基础链路，作为结果 item["mode"]（不含 rerank 后缀）

            # 关键词降级：RRF 最高分低于阈值时降级到关键词模式
            if results and _RECALL_CONFIG.get("rrf", {}).get("fallback_threshold"):
                max_score = results[0][1] if results else 0
                if max_score < _RECALL_CONFIG["rrf"]["fallback_threshold"]:
                    print(f"[RRF 最高分 {max_score:.4f} < 阈值 {_RECALL_CONFIG['rrf']['fallback_threshold']}, 降级到关键词模式]")
                    return _keyword_fallback(input_text, return_results, permanent_only=permanent_only)

            if results:
                # 铁律加权：decision 类型结果 RRF/BM25 分数 ×1.3（决策排前面）
                boosted = []
                for _p, _s in results:
                    if "decisions.md" in str(_p):
                        boosted.append((_p, _s * 1.3))
                    else:
                        boosted.append((_p, _s))
                boosted.sort(key=lambda x: x[1], reverse=True)
                results = boosted

                # 去重：同一文档（path 去掉 #anchor）只保留最高分 chunk
                dedup_cfg = _RECALL_CONFIG.get("dedup", {})
                if dedup_cfg.get("enabled", True):
                    results = _dedup_by_doc(results,
                                            max_per_doc=dedup_cfg.get("max_per_doc", 1))

                # BM25 强信号保底席位（gq006 型融合挤压治理，消融裁决 2026-09-05）：
                # 仅在单查询链路启用（按 _queries 判定——双查询即使一路空结果，
                # 剩余单路也不是消融验证的单查询形态，保守跳过；P1-5）
                _seat_cfg = _RECALL_CONFIG.get("bm25_seat", {})
                if (_seat_cfg.get("enabled") and len(_queries) == 1
                        and _last_s is not None):
                    results = _apply_bm25_seats(
                        results, _last_s.get("bm25_leg"),
                        top_docs=_seat_cfg.get("top_docs", 3),
                        min_score_ratio=_seat_cfg.get("min_score_ratio", 0.95))

                # 补全 client 和 snippet（两级检索：先读 2000 字 -> extract_attention 摘要）
                # M2-R2：图扩展已从召回链路移除（R4 ablation 证明零增量），
                # 不再读取 client_graph.json，也不再向结果附加 graph_expansions。
                from _compress import extract_attention

                enriched = []
                for path, score in results[:3]:  # top 3（从 5 降为 3）
                    client = _detect_client_from_path(path)
                    raw = _read_snippet(path, 2000)
                    snippet = extract_attention(raw) if raw else ""

                    # P0: 父子回溯 -- 命中 section 时读取 parent session 上下文
                    parent_context = ""
                    path_str = str(path)
                    if "#session" in path_str and "#section" in path_str:
                        _parts = path_str.split("#")
                        if len(_parts) >= 3 and _parts[1].startswith("session"):
                            _parent_spec = _parts[0] + "#" + _parts[1]
                            _parent_raw = _read_snippet(_parent_spec, 3000)
                            if _parent_raw and _parent_raw != raw:
                                parent_context = extract_attention(_parent_raw)

                    item = {"client": client, "score": score,
                             "path": path, "snippet": snippet,
                             "parent_context": parent_context,
                             "source_type": _classify_source_type(path)}
                    if item["source_type"] == "decision":
                        item["persistence"] = _extract_persistence(raw)
                        item["scope"] = _extract_scope(raw)

                    enriched.append(item)

                # P6-2：--permanent-only —— 只保留 permanent 决策（task 决策排除）
                if permanent_only:
                    before = len(enriched)
                    enriched = [e for e in enriched
                                if e.get("source_type") != "decision"
                                or e.get("persistence") == "permanent"]
                    if before != len(enriched):
                        print(f"[recall] permanent-only 过滤: {before} -> {len(enriched)}")

                # 客户过滤：只保留指定客户的结果
                if client_filter and client_name:
                    before = len(enriched)
                    enriched = [e for e in enriched if e["client"] == client_name]
                    if before != len(enriched):
                        print(f"[recall] 客户过滤: {before} -> {len(enriched)}（仅保留 {client_name}）")

                # 精排（可选）：优先 Silicon Flow BGE-Reranker，失败降级到 LLM rerank
                if rerank and len(enriched) > 1:
                    try:
                        from _cloud_llm import rerank as llm_rerank, siliconflow_rerank
                        ranked = siliconflow_rerank(
                            input_text,
                            [(e["client"], e["score"], e["path"], e["snippet"])
                             for e in enriched],
                            top_k=_RECALL_CONFIG["rerank"]["top_k"],
                            alpha=_RECALL_CONFIG["rerank"].get("alpha", 0.7),
                            client_name=client_name
                        )
                        if ranked is not None:
                            print(f"[{mode}] BGE-Reranker 精排中...")
                            mode += " + BGE-Rerank"
                        else:
                            print(f"[{mode}] LLM rerank 精排中（SiliconFlow 未配置或失败）...")
                            ranked = llm_rerank(
                                input_text,
                                [(e["client"], e["score"], e["path"], e["snippet"])
                                 for e in enriched],
                                top_k=_RECALL_CONFIG["rerank"]["top_k"],
                                client_name=client_name
                            )
                            mode += " + LLM rerank"
                        # P0: rerank 后保留 parent_context + source_type + persistence
                        _path_to_meta = {e["path"]: e for e in enriched}
                        enriched = [{"client": c, "score": s, "path": p, "snippet": sn,
                                     "parent_context": _path_to_meta.get(p, {}).get("parent_context", ""),
                                     "source_type": _path_to_meta.get(p, {}).get("source_type", "unknown")}
                                    for c, s, p, sn in ranked]
                        for _item in enriched:
                            _meta = _path_to_meta.get(_item["path"], {})
                            if _meta.get("persistence"):
                                _item["persistence"] = _meta["persistence"]
                            if _meta.get("scope"):
                                _item["scope"] = _meta["scope"]
                    except Exception as e:
                        print(f"[rerank] 失败: {e}，返回原序")
                        enriched = enriched[:3]
                else:
                    enriched = enriched[:3]  # top 3（改动7：从 5 降为 3）

                # T9：来源锚 + 模式 + 降级标记（纯加法，不删不改既有键——
                # folio_recall 工具 / RAG 注入消费这些 dict）
                for _item in enriched:
                    _doc_name = os.path.basename(str(_item["path"]).split("#")[0])
                    _item["source"] = f"客户={_item['client']} | 文档={_doc_name}"
                    _item["mode"] = base_mode
                    _item["degraded"] = degraded

                print(f"=== {mode} 检索结果 ===")
                # 报价引用约束：检测是否涉及报价/价格，提示来源标注
                quote_keywords = ["报价", "价格", "单价", "费用", "万元", "元/", "报价单", "预算"]
                has_quote = any(kw in input_text for kw in quote_keywords)
                if has_quote:
                    print("[报价引用约束] 本次检索涉及价格信息，引用时必须标注：客户名+文档名+版本")
                    print("[报价引用约束] 不同客户的价格严禁混用；如检索结果无精确匹配，需人工确认")
                # 人读路径：降级时每条结果行前缀 [降级]（不再只在过程日志里闪一次）
                _deg_prefix = "[降级] " if degraded else ""
                _type_labels = {"decision": "铁律", "preference": "偏好", "session": "会话",
                                "reference": "参考", "output": "产出", "method": "方法论",
                                "unknown": "其他"}
                for item in enriched:
                    _tl = _type_labels.get(item.get("source_type", "unknown"), "其他")
                    _pl = f"·{item.get('persistence', '')}" if item.get("persistence") else ""
                    print(f"\n{_deg_prefix}[{item['client']}] 分数: {item['score']:.3f}")
                    print(f"{_deg_prefix}  [{_tl}{_pl}] 路径: {item['path']}")
                    print(f"{_deg_prefix}  来源: {item['source']}")
                    print(f"{_deg_prefix}  片段: {item['snippet']}")
                    # P0: 父级上下文
                    if item.get("parent_context"):
                        print(f"{_deg_prefix}  父级上下文: {item['parent_context']}")

                # I-2 T7：查询 trace 落盘（失败不阻断召回）
                try:
                    from _query_trace import write_query_trace
                    write_query_trace({
                        "query": input_text,
                        "client": client_name,
                        "rewritten": (_rewrite or {}).get("rewritten"),
                        "rewrite_confidence": (_rewrite or {}).get("confidence"),
                        "rewrite_changes": (_rewrite or {}).get("changes", []),
                        "rewrite_degraded": (_rewrite or {}).get("degraded", []),
                        "mode": base_mode,
                        "degraded": degraded,
                        "n_results": len(enriched),
                        "cross_client_filtered": cross_client_filtered,
                    })
                except Exception:
                    pass

                if return_results:
                    return enriched
                return

            print("[BM25 索引不存在且 Embedding 不可用，使用关键词模式]")
        except ImportError as e:
            print(f"[降级] 缺少依赖 {e.name}，使用关键词模式")

    # 关键词 fallback（P6-2：permanent_only 一并传导，降级路径不静默失效）
    return _keyword_fallback(input_text, return_results, permanent_only=permanent_only)


def _keyword_fallback(input_text, return_results=False, permanent_only=False):
    """关键词 fallback 检索。优先 jieba 分词，缺失时降级为正则粗分（兼容中文）。

    permanent_only=True（P6-2）：只允许 permanent 决策块参与匹配/返回——
    context.md/preferences.md 与 task 决策一律不参与，杜绝降级路径把临时决策当证据。
    """
    try:
        from _bm25 import _tokenize
    except ImportError:
        def _tokenize(text):
            """无 jieba 时的兜底分词：英文/数字整词 + 中文二元组（配合子串匹配）。"""
            tokens = []
            for w in re.findall(r'[a-zA-Z0-9]+|[一-鿿]+', text):
                if len(w) >= 2 and '一' <= w[0] <= '鿿':
                    tokens.extend(w[i:i + 2] for i in range(len(w) - 1))
                else:
                    tokens.append(w)
            return tokens

    words = _tokenize(input_text)
    if not words:
        print("请提供关键词")
        return [] if return_results else None

    scores = {}
    content_cache = {}  # P1：缓存已读内容，避免结果输出时重复读磁盘
    from _paths import CLIENTS_DIR
    for client in list_clients():
        if permanent_only:
            # P6-2：仅用 permanent 决策块参与匹配（跳过 context/preferences/task 决策）
            dec_path = os.path.join(CLIENTS_DIR, client, "decisions.md")
            ctx_path = dec_path
            if not os.path.exists(dec_path):
                continue
            try:
                from _embed_index import _split_decision_chunks, _decision_block_meta
                dec_text = open(dec_path, "r", encoding="utf-8").read()
                content_parts = []
                for _i, blk in _split_decision_chunks(dec_text):
                    if _decision_block_meta(blk)["persistence"] == "permanent":
                        content_parts.append(blk)
            except Exception:
                continue
            if not content_parts:
                continue  # 该客户无 permanent 决策，不参与匹配
        else:
            ctx_path = get_context_path(client)
            if not os.path.exists(ctx_path):
                continue
            content_parts = []
            with open(ctx_path, "r", encoding="utf-8") as f:
                content_parts.append(f.read())
            for filename in ("decisions.md", "preferences.md"):
                extra_path = os.path.join(CLIENTS_DIR, client, filename)
                if os.path.exists(extra_path):
                    with open(extra_path, "r", encoding="utf-8") as f:
                        content_parts.append(f.read())
        content = "\n".join(content_parts)
        content_lower = content.lower()
        score = sum(1 for w in words if w.lower() in content_lower)
        if score > 0:
            scores[client] = score
            content_cache[client] = content

    if not scores:
        print("未找到匹配的项目")
        return [] if return_results else None

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    print("=== 关键词检索结果 ===")
    results = []
    for client, score in sorted_items[:5]:
        ctx_path = get_context_path(client)
        content = content_cache[client]
        print(f"\n[降级] [{client}] 命中词数: {score}")
        print(f"[降级]   {content[:80]}")
        # T9：关键词降级链路固定携带 source/mode/degraded（关键词模式 = 质量打折）
        doc_name = os.path.basename(str(ctx_path).split("#")[0])
        item = {"client": client, "score": float(score),
                "path": ctx_path, "snippet": content[:200],
                "source": f"客户={client} | 文档={doc_name}",
                "mode": "关键词降级", "degraded": True}
        # P6-2：permanent-only 降级结果标注 decision 维度（render 展示 [permanent·scope]）
        if permanent_only:
            item["source_type"] = "decision"
            item["persistence"] = "permanent"
            item["scope"] = "client"
        results.append(item)
    return results if return_results else None


def _embedding_recall(query_text, top_k=20, client_filter=None, client_name=None):
    """Embedding 语义召回。返回 [(path, score), ...] 或 None。

    client_filter: 指定客户名时，只搜索该客户的文档（在相似度计算前过滤）。
    client_name: 透传给云端 embed 供出域熔断（I-1）。
    存储格式：numpy .npy 矩阵 + JSON 路径映射（加载 ~10ms，余弦计算向量化）。
    """
    try:
        from _cloud_llm import embed
        import numpy as np

        query_vec = embed(query_text, client_name=client_name)
        if not query_vec:
            return None

        # 加载 embedding 索引（npy + json）
        cache_dir = os.path.join(SCRIPT_DIR, "_knowledge", ".cache")
        matrix_path = os.path.join(cache_dir, "embeddings_matrix.npy")
        index_path = os.path.join(cache_dir, "embeddings_index.json")

        # 旧格式自动迁移
        if not os.path.exists(matrix_path):
            from _embed_index import _migrate_pkl_to_npy
            _migrate_pkl_to_npy()

        if not os.path.exists(matrix_path) or not os.path.exists(index_path):
            return None

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        matrix = np.load(matrix_path)

        paths = index.get("paths", [])
        if not paths or matrix.shape[0] == 0:
            return None

        # 索引模型与当前 provider 不一致时向量空间不兼容，退回 BM25（防静默错配）
        from _cloud_llm import current_embed_provider
        _provider = current_embed_provider()
        _cache_model = index.get("model", "")
        if _provider and _cache_model and _cache_model != _provider[1]:
            print(f"[降级] 索引模型({_cache_model})与当前 embedding provider({_provider[1]})不一致，"
                  f"退回 BM25。运行 python _cli.py embed-rebuild --force 重建")
            return None

        # 按客户过滤：优先用索引构建期写入的结构化 clients 字段，
        # 旧索引缺失时回退到精确匹配 clients/{客户名}/ 目录。
        paths_arr = np.array(paths)
        if client_filter:
            stored_clients = index.get("clients")
            if stored_clients and len(stored_clients) == len(paths):
                mask = np.array([c == client_filter for c in stored_clients])
            else:
                _client_pat = re.compile(rf'[/\\]clients[/\\]{re.escape(client_filter)}[/\\]')
                mask = np.array([bool(_client_pat.search(p)) for p in paths])
            if not mask.any():
                return []
            matrix = matrix[mask]
            paths_arr = paths_arr[mask]

        # 向量化余弦相似度（一次矩阵乘法替代 N 次 Python 循环）
        q = np.array(query_vec, dtype=np.float32)
        q_norm = q / (np.linalg.norm(q) + 1e-10)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
        sims = (matrix / norms) @ q_norm  # (N,)

        # 阈值过滤 + top_k
        threshold = _RECALL_CONFIG["embedding"]["threshold"]
        valid = sims > threshold
        if not valid.any():
            return []
        valid_indices = np.where(valid)[0]
        valid_sims = sims[valid_indices]
        # 取 top_k
        if len(valid_indices) > top_k:
            top_idx = np.argpartition(valid_sims, -top_k)[-top_k:]
            top_idx = top_idx[np.argsort(valid_sims[top_idx])[::-1]]
        else:
            top_idx = np.argsort(valid_sims)[::-1]

        return [(paths_arr[valid_indices[i]], float(valid_sims[i])) for i in top_idx]

    except Exception as e:
        print(f"[embedding] 召回失败: {e}")
        return None


def _hard_filter_client(results, client_filter):
    """融合入口硬隔离：丢弃任何非当前 client 的候选，返回 (保留结果, 丢弃数)。

    T4：即使 BM25/Embedding 内部已过滤，这里仍做第二道防线并计数，
    cross_client_filtered > 0 时上层告警。
    """
    if not client_filter or not results:
        return results, 0
    kept = []
    filtered = 0
    for path, score in results:
        if _detect_client_from_path(path) == client_filter:
            kept.append((path, score))
        else:
            filtered += 1
    return kept, filtered


def _rrf_fuse(bm25_results, emb_results, k=10):
    """RRF (Reciprocal Rank Fusion) 融合两路检索结果。

    RRF score = Σ 1/(k + rank_i)
    bm25_results / emb_results: [(path, score), ...]
    返回: [(path, rrf_score), ...] 按 RRF 分数降序
    """
    scores = {}
    for rank, (path, _) in enumerate(bm25_results):
        scores[path] = scores.get(path, 0) + 1.0 / (k + rank + 1)
    for rank, (path, _) in enumerate(emb_results):
        scores[path] = scores.get(path, 0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _rrf_fuse_weighted(groups, k=10):
    """对多组 (results, weight) 做加权 RRF 合并（I-2 T2 双路用）。

    groups: [(results, weight), ...]，results 为已排序 [(path, score), ...]
    RRF score = Σ weight * 1/(k + rank_i)
    返回: [(path, rrf_score), ...] 按分数降序
    """
    scores = {}
    for results, weight in groups:
        for rank, (path, _) in enumerate(results):
            scores[path] = scores.get(path, 0) + weight * 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _single_query_retrieve(query_text, index_filter, use_embedding, client_name, config):
    """单个查询检索：BM25(+Embedding) 并发 → 硬隔离 → RRF 融合（I-2 抽取）。

    返回 dict: results / mode / degraded / cross_client_filtered / bm25_leg。
    内部降级（缺路/无索引）返回 None 结果并标 degraded，与旧内联逻辑一致。
    """
    from _bm25 import query_bm25
    emb_results = None
    if use_embedding:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            bm25_future = pool.submit(
                query_bm25, query_text, top_k=config["bm25"]["top_k"],
                client_filter=index_filter)
            emb_future = pool.submit(
                _embedding_recall, query_text, top_k=config["embedding"]["top_k"],
                client_filter=index_filter, client_name=client_name)
            bm25_results = bm25_future.result()
            emb_results = emb_future.result()
    else:
        bm25_results = query_bm25(
            query_text, top_k=config["bm25"]["top_k"], client_filter=index_filter)

    # T9：降级检测 —— 请求了 Embedding 但该路无返回 / BM25 路无返回 = 缺一路
    degraded = False
    if use_embedding and emb_results is None:
        degraded = True
    if bm25_results is None:
        degraded = True

    # T4 硬隔离：融合入口第二道防线，丢弃跨客户候选并计数
    cross_client_filtered = 0
    if index_filter:
        bm25_results, _bm25_cross = _hard_filter_client(bm25_results, index_filter)
        emb_results, _emb_cross = _hard_filter_client(emb_results, index_filter)
        cross_client_filtered = _bm25_cross + _emb_cross

    if bm25_results is not None and emb_results:
        results = _rrf_fuse(bm25_results, emb_results, k=config["rrf"]["k"])
        mode = "BM25 + Embedding RRF"
    elif bm25_results is not None:
        results = bm25_results
        mode = "BM25"
    elif emb_results:
        results = emb_results
        mode = "Embedding"
    else:
        results = None
        mode = None
    return {
        "results": results,
        "mode": mode,
        "degraded": degraded,
        "cross_client_filtered": cross_client_filtered,
        "bm25_leg": bm25_results,  # BM25 强信号保底席位用（融合前原始排名）
    }


def _apply_bm25_seats(results, bm25_leg, top_docs=3, min_score_ratio=0.95, top_n=3):
    """BM25 强信号保底席位（gq006 型融合挤压治理，golden 消融裁决 2026-09-05）。

    门控：BM25 路第 top_docs 个文档的分数 ≥ min_score_ratio × top1 分数
    （前 N 个文档近乎并列 = 词条级强匹配信号，embedding 路泛词文档不应
    将其挤出最终 top_n）。门控通过时，保证这 N 个文档各占一个 top_n 席位：
    缺席文档用其在 results 中的最高位 chunk 替换 top_n 内最低位非席位文档。
    门控不满足 / 席位已在 top_n / 任一路为空时原样返回（零干预）。

    results: [(path, score), ...] 已按分数降序（boost+dedup 后）
    bm25_leg: [(path, score), ...] BM25 路原始排名（融合前）
    """
    if not results or not bm25_leg or top_docs < 1:
        return results
    seat_docs = []
    for p, _s in bm25_leg:
        d = str(p).split("#")[0]
        if d not in seat_docs:
            seat_docs.append(d)
        if len(seat_docs) >= top_docs:
            break
    if len(seat_docs) < top_docs:
        return results
    top1_score = bm25_leg[0][1]
    if top1_score <= 0:
        return results
    nth_score = next((s for p, s in bm25_leg
                      if str(p).split("#")[0] == seat_docs[top_docs - 1]), None)
    if nth_score is None or nth_score < min_score_ratio * top1_score:
        return results
    out = list(results)
    for d in seat_docs:
        topn_docs = {str(p).split("#")[0] for p, _s in out[:top_n]}
        if d in topn_docs:
            continue
        best = next(((p, s) for p, s in out if str(p).split("#")[0] == d), None)
        if best is None:
            continue
        for i in range(min(top_n, len(out)) - 1, -1, -1):
            if str(out[i][0]).split("#")[0] not in seat_docs:
                # 消融语义（simulate_seats.apply_seat）：原地替换、displaced 丢弃、
                # 其余同 doc chunk 去重删除。曾把 displaced 插回 i+1——列表变长
                # 会把其他席位文档挤 top_n 外（P1-4，与消融验证对象不一致）
                out[i] = best
                out = out[:i + 1] + [x for x in out[i + 1:]
                                     if str(x[0]).split("#")[0] != d]
                break
    return out


def _dedup_by_doc(results, max_per_doc=1):
    """按文档路径去重：同一文档（path 去掉 #anchor）只保留最高分 chunk。

    results: [(path_with_anchor, score), ...] 已按分数降序
    max_per_doc: 每个文档最多保留几个 chunk（默认 1）
    返回: [(path_with_anchor, score), ...] 去重后列表
    """
    doc_count = {}
    kept = []
    for path, score in results:
        doc_key = str(path).split("#")[0]
        if doc_count.get(doc_key, 0) >= max_per_doc:
            continue
        doc_count[doc_key] = doc_count.get(doc_key, 0) + 1
        kept.append((path, score))
    return kept


def _detect_client_from_path(path):
    """从路径中检测客户名（D-121：docs 方法论文档归「方法论」）。"""
    # D-121：docs 方法论白名单文档无客户归属，显示为「方法论」
    if "docs" in path and "clients" not in path:
        return "方法论"
    # P1-11：按客户名长度降序匹配，避免 "超" 先于 "蓝海" 匹配
    clients = sorted(list_clients(), key=len, reverse=True)
    for client in clients:
        if client in path:
            return client
    return "?"


def _classify_source_type(path):
    """判断召回结果的来源类型与可信度（供 RAG 注入与渲染标注）。

    类型语义：
      decision   — decisions.md 决策/铁律，最高可信度
      preference — preferences.md 客户偏好，高可信度
      session    — context.md 会话历史，中等可信度（可能过时）
      reference  — refs/ 参考材料，原文引用
      output     — outputs/ 历史产出，可能已过时
      method     — docs/ 方法论文档，规范参考
    """
    path_str = str(path)
    if "decisions.md" in path_str:
        return "decision"
    if "preferences.md" in path_str:
        return "preference"
    if "context.md" in path_str:
        return "session"
    if "refs" in path_str and "clients" in path_str:
        return "reference"
    if "outputs" in path_str or "output" in path_str:
        return "output"
    if "docs" in path_str:
        return "method"
    return "unknown"


def _extract_persistence(raw):
    """从决策块原始文本提取 persistence 字段（缺失默认 permanent，向后兼容）。"""
    m = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', raw or "")
    return m.group(1).strip().lower() if m else "permanent"


def _extract_scope(raw):
    """从决策块原始文本提取 scope 字段（缺失默认 client，向后兼容）。"""
    m = re.search(r'[-*]\s*\*{0,2}scope\*{0,2}\s*[：:]\s*(\w+)', raw or "")
    return m.group(1).strip().lower() if m else "client"


def _read_snippet(path_spec, max_chars=200):
    """从 path#anchor 读片段。支持二进制文件（pptx/pdf/docx）通过 _pipeline 缓存读取。"""
    parts = str(path_spec).split("#")
    fpath = parts[0]
    if not os.path.exists(fpath):
        return ""
    ext = os.path.splitext(fpath)[1].lower()
    # 文本文件直接读
    if ext in (".txt", ".md", ".yml", ".yaml", ".json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return ""
    else:
        # 二进制文件走 _pipeline 缓存
        try:
            from _pipeline import read_full
            _, cache_path = read_full(fpath)
            if cache_path and os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                return f"(无法读取 {ext} 文件)"
        except Exception:
            return "(读取失败)"

    if len(parts) == 1:
        return content[:max_chars]

    anchor = parts[1]
    if anchor.startswith("p"):
        # refs 滑动窗口分块：用和切片侧一致的 _sliding_window_chunks 还原
        try:
            from _embed_index import _sliding_window_chunks
            chunks = _sliding_window_chunks(content, chunk_size=800, overlap=200)
            idx = int(anchor[1:]) if anchor[1:].isdigit() else 0
            if idx < len(chunks):
                return chunks[idx][:max_chars]
        except Exception:
            pass
        # 兜底：按页码切（向后兼容旧索引）
        page_chunks = re.split(r'(?==== 第 \d+ 页 ===)', content)
        idx = int(anchor[1:]) if anchor[1:].isdigit() else 0
        if idx < len(page_chunks):
            return page_chunks[idx][:max_chars]
    elif anchor.startswith("session"):
        # 可能是 #session{N} 或 #session{N}#section{M}
        sessions = re.split(r'(?=## \[\d{4}-\d{2}-\d{2}\])', content)
        s_idx = int(anchor[7:]) if anchor[7:].isdigit() else 0
        if s_idx < len(sessions):
            session_text = sessions[s_idx]
            # 检查是否有 section 锚点
            if len(parts) > 2 and parts[2].startswith("section"):
                sec_idx = int(parts[2][7:]) if parts[2][7:].isdigit() else 0
                sections = re.split(r'(?=\n###\s)', session_text)
                if sec_idx < len(sections):
                    return sections[sec_idx][:max_chars]
            return session_text[:max_chars]
    elif anchor.startswith("h"):
        chunks = re.split(r'(?=\n##\s)', content)
        idx = int(anchor[1:]) if anchor[1:].isdigit() else 0
        if idx < len(chunks):
            # P3：方法论 #h{i}#w{wi} 锚点——向量命中的是章内滑动窗口 wi，
            # 忽略窗口号会把整章从头截断，rerank 文本与向量命中窗口不一致。
            # 保守回退：窗口号缺失/非法/越界/还原失败一律退回整章旧行为，
            # 不改变正常召回排序路径。
            if len(parts) > 2 and parts[2].startswith("w") and parts[2][1:].isdigit():
                try:
                    from _embed_index import _sliding_window_chunks
                    wins = _sliding_window_chunks(chunks[idx], chunk_size=800, overlap=200)
                    w_idx = int(parts[2][1:])
                    if 0 <= w_idx < len(wins):
                        return wins[w_idx][:max_chars]
                except Exception:
                    pass
            return chunks[idx][:max_chars]
    elif anchor.startswith("d"):
        # decisions.md 决策块（P6-1：与切片侧共用 _split_decision_chunks，
        # 跳过 conflict: pending / 已废弃 块；旧索引指向被跳过块时返回过滤说明）
        try:
            from _graph import _split_decision_blocks as _raw_split
            from _embed_index import _split_decision_chunks, _DEPRECATED_RE, _sliding_window_chunks
            idx = int(anchor[1:]) if anchor[1:].isdigit() else 0
            # P2-10：#d{i}#w{j} 超长块滑动窗口子块——还原具体窗口，与切片侧一致
            window_idx = None
            if len(parts) > 2 and parts[2].startswith("w") and parts[2][1:].isdigit():
                window_idx = int(parts[2][1:])
            for c_idx, text in _split_decision_chunks(content):
                if c_idx == idx:
                    if window_idx is None:
                        return text[:max_chars]
                    wins = _sliding_window_chunks(text, chunk_size=1800, overlap=200)
                    if 0 <= window_idx < len(wins):
                        return wins[window_idx][:max_chars]
                    return text[:max_chars]
            raw_blocks = _raw_split(content)[1:]  # 跳过文件头
            if 0 <= idx < len(raw_blocks):
                raw = raw_blocks[idx]
                if "<!-- conflict: pending -->" in raw or _DEPRECATED_RE.search(raw):
                    return "(该决策条目已废弃或处于未决冲突，已从召回索引过滤)"
        except Exception:
            pass
        return content[:max_chars]
    elif anchor.startswith("sheet"):
        # xlsx 结构化分块：#sheet{N}#row{M}
        # 用 _pipeline.read_xlsx_structured 重新读，定位到具体行
        try:
            from _pipeline import read_xlsx_structured
            row_chunks = read_xlsx_structured(fpath)
            row_anchor = "#".join(parts[1:])  # sheet{N}#row{M}
            for chunk_text, a in row_chunks:
                if a == row_anchor:
                    return chunk_text[:max_chars]
            # 兜底：返回第一个匹配 sheet 的行
            for chunk_text, a in row_chunks:
                if a.startswith(anchor):
                    return chunk_text[:max_chars]
        except Exception:
            pass
        return content[:max_chars]
    return content[:max_chars]


def read_chunk(path_spec, max_chars=10000):
    """按 path#anchor 读完整 chunk 全文（不限 200 字）。

    支持标题文本锚点（破坏点 2 修复）：如果锚点不是数字格式，
    按 ## [日期] 标题 或 ## 决策 N 标题 文本搜索匹配段落。
    """
    parts = str(path_spec).split("#")
    fpath = parts[0]
    if not os.path.exists(fpath):
        return f"(文件不存在: {fpath})"

    ext = os.path.splitext(fpath)[1].lower()
    if ext in (".txt", ".md", ".yml", ".yaml", ".json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return "(读取失败)"
    else:
        try:
            from _pipeline import read_full
            _, cache_path = read_full(fpath)
            if cache_path and os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                return f"(无法读取 {ext} 文件)"
        except Exception:
            return "(读取失败)"

    if len(parts) == 1:
        return content[:max_chars]

    # I-3 批3 顺带项：analysis/ 三区表 chunk-read 与语料口径一致——只还原
    # confirmed 条目（draft/开放问题/框架缺口不回读，防假设自我强化污染）
    if "/analysis/" in fpath.replace("\\", "/"):
        try:
            from _embed_index import _parse_analysis_confirmed
            _warns = []
            _confirmed = _parse_analysis_confirmed(
                content, _warns, os.path.basename(fpath))
            if _confirmed is None:
                return "(三区表格式损坏，fail-closed 不回读: " + "; ".join(_warns[:2]) + ")"
            return ("\n".join(_confirmed)[:max_chars]
                    or "(该三区表无 confirmed 条目，未确认内容不回读)")
        except Exception:
            pass

    anchor = parts[1]

    # 数字格式锚点：复用 _read_snippet 逻辑（含 decisions.md 的 #d{i} 块锚点）
    if (anchor.startswith("p") or anchor.startswith("session")
            or anchor.startswith("h") or anchor.startswith("sheet")
            or anchor.startswith("d")):
        return _read_snippet(path_spec, max_chars)

    # 标题文本锚点：按 ## [日期] 标题 或 ## 决策 N 标题 搜索
    sections = re.split(r'(?=^##\s)', content, flags=re.MULTILINE)
    for sec in sections:
        header = sec.strip().split("\n")[0] if sec.strip() else ""
        if anchor in header:
            return sec[:max_chars]

    # 再尝试 ## 决策 N：标题 格式
    for sec in sections:
        if anchor in sec[:200]:
            return sec[:max_chars]

    # 兜底：全文搜索
    idx = content.find(anchor)
    if idx >= 0:
        start = max(0, idx - 200)
        return content[start:start + max_chars]

    return content[:max_chars]
