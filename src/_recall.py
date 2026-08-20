# -*- coding: utf-8 -*-
"""召回模块：BM25 + Embedding 双路召回 + RRF 融合 + 关键词降级。

从 _session.py 拆分（候选 4 · 模块化），依赖 _context + _graph。
"""
import os
import json
import re

from _paths import SCRIPT_DIR
from _context import list_clients, get_context_path
from _graph import _expand_graph_2hop, _find_pivot_nodes


__all__ = [
    # 常量
    "_RECALL_CONFIG",
    # 函数
    "_load_recall_config",
    "recall", "_keyword_fallback", "_embedding_recall",
    "_rrf_fuse", "_dedup_by_doc",
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


def recall(input_text, force_keyword=False, client_name=None, rerank=True,
           use_embedding=True, return_results=False, client_filter=None):
    """召回相关历史项目。BM25 + Embedding 双路召回 + RRF 融合。

    client_name: 指定客户时用其别名展开查询，并在索引层按客户隔离搜索
    rerank: True 时调云端 LLM 精排
    use_embedding: True 时启用 Embedding 语义召回（需要 ZHIPU_API_KEY）
    return_results: True 时返回结构化结果列表（RAG 注入用），False 时只打印
    client_filter: True 时在索引层只搜索 client_name 客户的文档。
                   None（默认）时自动按是否有 client_name 决定。

    返回（return_results=True 时）：
        [{"client", "score", "path", "snippet", "parent_context",
          "source", "mode", "degraded"}, ...] 或 None
        source: "客户=X | 文档=Y"（现有 print 的来源标注数据化）
        mode: 实际生效链路（"BM25 + Embedding RRF" / "BM25" / "Embedding" / "关键词降级"）
        degraded: 任一降级路径触发即 True（请求 Embedding 无返回 / RRF 阈值 / 依赖缺失 / 关键词 fallback）
    """
    # T9：降级状态跟踪。任一降级路径（见下方分支）触发后置 True，
    # 结果 item 的 "degraded" 键随之置位，供 folio_recall / RAG 注入识别质量折扣。
    degraded = False
    if not force_keyword:
        try:
            from _bm25 import query_bm25
            # 别名展开（查询侧）
            query_text = input_text
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

            if client_name:
                try:
                    from _aliases import load_client, expand_text
                    aliases = load_client(client_name)
                    query_text = expand_text(input_text, aliases)
                except Exception as e:
                    print(f"[warn] {client_name} 别名加载失败: {e}")

            # client_filter 自动决策：未显式指定时，有 client_name 就开启索引层隔离
            if client_filter is None:
                client_filter = client_name
            # 索引层过滤参数：传客户名给 BM25/Embedding 在 top_k 选取前过滤
            index_filter = client_name if client_filter else None
            if index_filter:
                print(f"[recall] 索引层按客户隔离: {index_filter}")

            # BM25 + Embedding 并发检索（两路不相互依赖）
            emb_results = None
            if use_embedding:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as pool:
                    bm25_future = pool.submit(query_bm25, query_text, top_k=_RECALL_CONFIG["bm25"]["top_k"], client_filter=index_filter)
                    emb_future = pool.submit(_embedding_recall, query_text, top_k=_RECALL_CONFIG["embedding"]["top_k"], client_filter=index_filter)
                    bm25_results = bm25_future.result()
                    emb_results = emb_future.result()
            else:
                bm25_results = query_bm25(query_text, top_k=_RECALL_CONFIG["bm25"]["top_k"], client_filter=index_filter)

            # T9：降级检测 —— 请求了 Embedding 但该路无返回（内部降级：索引模型不一致 /
            # 无 API key / 无索引 / 异常均以 None 返回）。双路缺一路 = 结果质量打折，必须可见。
            if use_embedding and emb_results is None:
                degraded = True
            # 监工补充（对称规则，B 批报告指出）：BM25 路无返回（索引缺失/损坏
            # return None）同样 = 缺一路，单腿 Embedding 结果也必须标降级。
            if bm25_results is None:
                degraded = True

            # RRF 融合
            if bm25_results is not None and emb_results:
                results = _rrf_fuse(bm25_results, emb_results, k=_RECALL_CONFIG["rrf"]["k"])
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
            base_mode = mode  # T9：rerank 前的基础链路，作为结果 item["mode"]（不含 rerank 后缀）

            # 关键词降级：RRF 最高分低于阈值时降级到关键词模式
            if results and _RECALL_CONFIG.get("rrf", {}).get("fallback_threshold"):
                max_score = results[0][1] if results else 0
                if max_score < _RECALL_CONFIG["rrf"]["fallback_threshold"]:
                    print(f"[RRF 最高分 {max_score:.4f} < 阈值 {_RECALL_CONFIG['rrf']['fallback_threshold']}, 降级到关键词模式]")
                    return _keyword_fallback(input_text, return_results)

            if results:
                # 去重：同一文档（path 去掉 #anchor）只保留最高分 chunk
                dedup_cfg = _RECALL_CONFIG.get("dedup", {})
                if dedup_cfg.get("enabled", True):
                    results = _dedup_by_doc(results,
                                            max_per_doc=dedup_cfg.get("max_per_doc", 1))

                # 补全 client 和 snippet（两级检索：先读 2000 字 -> extract_attention 摘要）
                # 改动7：图扩展召回 -- Pivot Search + BFS 2跳（每客户只算一次）
                from _compress import extract_attention

                # 图扩展：按客户缓存，避免同 query 重复计算
                _graph_exp_cache = {}  # {client: [exp_lines]}
                def _get_graph_expansions(cli):
                    if cli in _graph_exp_cache:
                        return _graph_exp_cache[cli]
                    exps = []
                    try:
                        from _paths import client_graph_path
                        gp = client_graph_path(cli)
                        if os.path.exists(gp):
                            with open(gp, "r", encoding="utf-8") as gf:
                                g = json.load(gf)
                            pivots = _find_pivot_nodes(input_text, g, top_k=2)
                            seen_ids = set()
                            for pv in pivots:
                                n = pv["node"]
                                if n["id"] in seen_ids:
                                    continue
                                seen_ids.add(n["id"])
                                # local 层：命中节点本身，读 summary（实质内容）
                                tag = {"output": "产出物", "decision": "决策"}.get(
                                    n["type"], n["type"])
                                s = (n.get("summary") or "").strip()
                                exps.append(
                                    f"  ├─ [命中·{tag}] {n['title']}"
                                    + (f"：{s}" if s else "")
                                )
                                # global 层：沿 supersedes / revised_from 串脉络；
                                # 其余边作普通关联，均读 summary
                                for exp in _expand_graph_2hop(gp, n["id"]):
                                    if exp["id"] in seen_ids:
                                        continue
                                    seen_ids.add(exp["id"])
                                    es = (exp.get("summary") or "").strip()
                                    if exp["edge_type"] in ("supersedes", "revised_from",
                                                            "indirectly_revised_from"):
                                        label = f"脉络·{exp['edge_type']}"
                                    else:
                                        label = f"关联·{exp['edge_type']}"
                                    exps.append(
                                        f"  ├─ [{label}] {exp['title']}"
                                        + (f"：{es}" if es else "")
                                    )
                            exps = exps[:6]
                    except Exception:
                        pass
                    _graph_exp_cache[cli] = exps
                    return exps

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
                             "parent_context": parent_context}

                    # 图扩展：只附加到第一条结果（避免重复噪音）
                    if not enriched and client:
                        ge = _get_graph_expansions(client)
                        if ge:
                            item["graph_expansions"] = ge

                    enriched.append(item)

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
                            alpha=_RECALL_CONFIG["rerank"].get("alpha", 0.7)
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
                                top_k=_RECALL_CONFIG["rerank"]["top_k"]
                            )
                            mode += " + LLM rerank"
                        # P0: rerank 后保留 parent_context
                        _path_to_parent = {e["path"]: e.get("parent_context", "")
                                           for e in enriched}
                        enriched = [{"client": c, "score": s, "path": p, "snippet": sn,
                                     "parent_context": _path_to_parent.get(p, "")}
                                    for c, s, p, sn in ranked]
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
                for item in enriched:
                    print(f"\n{_deg_prefix}[{item['client']}] 分数: {item['score']:.3f}")
                    print(f"{_deg_prefix}  路径: {item['path']}")
                    print(f"{_deg_prefix}  来源: {item['source']}")
                    print(f"{_deg_prefix}  片段: {item['snippet']}")
                    # P0: 父级上下文
                    if item.get("parent_context"):
                        print(f"{_deg_prefix}  父级上下文: {item['parent_context']}")
                    # 图扩展结果
                    for exp_line in item.get("graph_expansions", []):
                        print(exp_line)

                if return_results:
                    return enriched
                return

            print("[BM25 索引不存在且 Embedding 不可用，使用关键词模式]")
        except ImportError as e:
            print(f"[降级] 缺少依赖 {e.name}，使用关键词模式")

    # 关键词 fallback
    return _keyword_fallback(input_text, return_results)


def _keyword_fallback(input_text, return_results=False):
    """关键词 fallback 检索。优先 jieba 分词，缺失时降级为正则粗分（兼容中文）。"""
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
    for client in list_clients():
        ctx_path = get_context_path(client)
        if not os.path.exists(ctx_path):
            continue
        with open(ctx_path, "r", encoding="utf-8") as f:
            content = f.read()
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
        results.append({"client": client, "score": float(score),
                         "path": ctx_path, "snippet": content[:200],
                         "source": f"客户={client} | 文档={doc_name}",
                         "mode": "关键词降级", "degraded": True})
    return results if return_results else None


def _embedding_recall(query_text, top_k=20, client_filter=None):
    """Embedding 语义召回。返回 [(path, score), ...] 或 None。

    client_filter: 指定客户名时，只搜索该客户的文档（在相似度计算前过滤）。
    存储格式：numpy .npy 矩阵 + JSON 路径映射（加载 ~10ms，余弦计算向量化）。
    """
    try:
        from _cloud_llm import embed
        import numpy as np

        query_vec = embed(query_text)
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

        # 按客户过滤：numpy 布尔索引（精确匹配 clients/{客户名}/ 目录）
        paths_arr = np.array(paths)
        if client_filter:
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
    # P1-11：按客户名长度降序匹配，避免 "蓝" 先于 "蓝海" 匹配（示例：客户名「蓝海集团」）
    clients = sorted(list_clients(), key=len, reverse=True)
    for client in clients:
        if client in path:
            return client
    return "?"


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
            return chunks[idx][:max_chars]
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

    anchor = parts[1]

    # 数字格式锚点：复用 _read_snippet 逻辑
    if (anchor.startswith("p") or anchor.startswith("session")
            or anchor.startswith("h") or anchor.startswith("sheet")):
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
