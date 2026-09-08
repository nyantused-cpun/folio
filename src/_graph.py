# -*- coding: utf-8 -*-
"""版本链索引模块：client_graph.json 构建与查询。

M2-R2：client_graph.json 定位为版本链索引（version lineage）/历史调试资产，
不再参与自动召回链路。
M2-R1：client_index.md（世界书）已由 _worldbook.build_worldbook 直读真源生成，
本模块不再写 client_index.md。
从 _session.py 拆分（候选 4 · 模块化），无内部依赖（叶子模块）。
"""
import os
import json
import re
from datetime import datetime


__all__ = [
    # 常量
    "DECISION_SUBTYPES",
    # 函数
    "_infer_decision_subtype",
    "_split_decision_blocks", "_extract_decision_nodes", "_extract_output_nodes", "_extract_insight_nodes",
    "_infer_edges", "_materialize_transitive_edges", "_consolidate_decisions",
    "_file_hash",
    "build_client_graph", "_full_build", "_incremental_update",
    "_write_graph", "query_graph", "search_graph_nodes",
    "add_graph_node", "add_graph_edge",
]


# ============================================================
# 版本链索引：client_graph.json（历史/调试资产）；世界书由 _worldbook.py 直生
# ============================================================

# ── P0 决策单轨化：统一决策标题切分（三种格式）──────────────────────────
# 格式1：## 决策 N：标题
# 格式2：### D-NNN · 标题
# 格式3：## [YYYY-MM-DD] 标题 或 ## YYYY-MM-DD：标题（早期客户遗留格式）
# 本正则/切分函数是「统一决策解析器」的唯一事实源，
# _theme_guard / _memory_guard 复用（不再各自维护一份不完整正则）。
DECISION_HEADING_SPLIT_RE = re.compile(
    r'(?=^(?:## 决策 \d+|### D-\d+|## \[?\d{4}-\d{2}-\d{2}\]?))',
    re.MULTILINE,
)


def _split_decision_blocks(content):
    """按三种决策标题格式切块，返回块列表。

    第一个块通常是文件头（如 `# 客户 决策记录`，不以决策标题开头），
    调用方应跳过；其余每个块以决策标题行开头。
    """
    return DECISION_HEADING_SPLIT_RE.split(content or "")


# 决策子类型关键词映射（改动2）
# 顺序即优先级：tie 时前面的胜出
DECISION_SUBTYPES = {
    "commercial":   ["预算", "报价", "商务", "合同", "金额"],
    "architecture": ["架构", "IAM", "SSO", "门户", "系统", "技术"],
    "scope":        ["甩项", "砍", "新增", "扩写", "范围", "裁剪"],
    "requirement":  ["需求", "功能", "清单", "能力"],
    "process":      ["合并", "重出", "重构", "路线", "流程"],
}


def _infer_decision_subtype(text):
    """从决策标题和内容推断子类型（按关键词出现次数取最高分，tie 时按 dict 顺序）。"""
    best_subtype = "general"
    best_count = 0
    for subtype, keywords in DECISION_SUBTYPES.items():
        count = sum(text.count(kw) for kw in keywords)
        if count > best_count:
            best_count = count
            best_subtype = subtype
    return best_subtype

def _normalize_output_title(title):
    """归一化产出标题：去扩展名 + 去版本号片段，用于判断是否同一文档系列。"""
    if not title:
        return ""
    base = re.sub(r'\.[^.]+$', '', title)              # 去扩展名
    base = re.sub(r'[_\-]?v\d+(?:\.\d+)*', '', base)   # 去 v1 / _v2.9.7 / -v3 等
    return base


def _same_output_series(out1, out2):
    """判断两个 output 是否同一文档系列（同文件类型 + 归一化标题相同）。"""
    if out1["metadata"].get("file_type") != out2["metadata"].get("file_type"):
        return False
    t1 = _normalize_output_title(out1.get("title", ""))
    t2 = _normalize_output_title(out2.get("title", ""))
    return bool(t1) and t1 == t2


def _extract_decision_nodes(decisions_content):
    """从 decisions.md 提取 decision 节点。

    兼容三种格式：
    - 格式1：## 决策 N：标题 + 字段列表（日期/来源/决策内容/推论/影响范围）
    - 格式2：### D-NNN · 标题 + 字段列表（日期/背景/决策/被否方案/persistence/scope/影响）
    - 格式3：## 日期：标题 或 ## [日期] 标题 + 字段列表（早期客户遗留格式）
    """
    nodes = []
    # 统一决策解析器：兼容三种格式切分（## 决策 N / ### D-NNN / ## 日期，可带 []）
    blocks = _split_decision_blocks(decisions_content)
    for block in blocks:
        block_stripped = block.strip()
        # 格式1：## 决策 N：标题
        if block_stripped.startswith("## 决策"):
            title_match = re.match(r'## 决策 (\d+)：?(.+)', block_stripped)
            title = title_match.group(2).strip() if title_match else "未命名决策"
            decision_num = int(title_match.group(1)) if title_match else 0
        # 格式2：### D-NNN · 标题
        elif block_stripped.startswith("### D-"):
            title_match = re.match(r'### D-(\d+)\s*[·•.]\s*(.+)', block_stripped)
            title = title_match.group(2).strip() if title_match else "未命名决策"
            decision_num = int(title_match.group(1)) if title_match else 0
        # 格式3：## 日期：标题 或 ## [日期] 标题
        elif re.match(r'^## \[?\d{4}-\d{2}-\d{2}\]?', block_stripped):
            title_match = re.match(r'^## \[?\d{4}-\d{2}-\d{2}\]?\s*[：:．.\-]?\s*(.*)',
                                   block_stripped)
            title = title_match.group(1).strip() if title_match and title_match.group(1) else "未命名决策"
            decision_num = 0
        else:
            continue

        # 提取日期
        date_match = re.search(r'\*\*日期\*\*[：:]\s*(\S+)', block)
        date = date_match.group(1).strip() if date_match else ""
        if not date:
            # 格式3：日期在标题行
            title_date = re.match(r'^## \[?(\d{4}-\d{2}-\d{2})\]?', block_stripped)
            if title_date:
                date = title_date.group(1)

        # 提取决策内容（兼容"决策内容"和"决策"两种字段名）
        content_match = re.search(r'\*\*决策(?:内容)?\*\*[：:]\s*(.+?)(?=\n-\s*\*\*|\n---|\Z)',
                                  block, re.DOTALL)
        decision_text = content_match.group(1).strip() if content_match else ""

        # 提取推论（reason，兼容"推论"和"理由"两种字段名）
        reason_match = re.search(r'\*\*(?:推论|理由|背景)\*\*[：:]\s*(.+?)(?=\n-\s*\*\*|\n---|\Z)',
                                  block, re.DOTALL)
        reason = reason_match.group(1).strip().replace("\n  - ", " ") if reason_match else ""

        # 提取 persistence / scope（与 _theme_guard 同一正则；缺省 permanent/client 向后兼容）
        pers_match = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', block)
        persistence = pers_match.group(1).strip().lower() if pers_match else "permanent"
        scope_match = re.search(r'[-*]\s*\*{0,2}scope\*{0,2}\s*[：:]\s*(\w+)', block)
        scope = scope_match.group(1).strip().lower() if scope_match else "client"

        # M2-R1：世界书直生需要的附加元数据（来源/task_id/状态/pending），
        # 不改变既有 graph 行为，仅补充字段供 _worldbook 使用。
        source_match = re.search(r'[-*]\s*\*{0,2}来源\*{0,2}\s*[：:]\s*(.+)', block)
        source = source_match.group(1).strip() if source_match else ""
        task_id_match = re.search(r'[-*]\s*\*{0,2}task_id\*{0,2}\s*[：:]\s*([^\s*]+)', block)
        task_id = task_id_match.group(1).strip() if task_id_match else ""
        status_match = re.search(r'[-*]\s*\*{0,2}状态\*{0,2}\s*[：:]\s*([^\n]+)', block)
        status = status_match.group(1).strip() if status_match else ""
        superseded_match = re.search(r'[-*]\s*\*{0,2}superseded_by\*{0,2}\s*[：:]\s*(\S+)', block)
        superseded_by = superseded_match.group(1).strip() if superseded_match else ""
        # 待补/待确认/遗留/待办（一行一条）
        pending_items = []
        for label in ("待补", "待确认", "遗留", "待办"):
            for m in re.finditer(
                    rf'[-*]\s*\*{{0,2}}{label}\*{{0,2}}\s*[：:]\s*(.+)', block):
                pending_items.append(m.group(1).strip())

        summary = decision_text[:200] if decision_text else title

        # 子类型推断（改动2）
        subtype = _infer_decision_subtype(title + " " + decision_text)

        node = {
            "id": f"n{len(nodes)+1:03d}",
            "type": "decision",
            "title": title,
            "summary": summary,
            "details_path": f"decisions.md#{title[:30]}",
            "metadata": {
                "date": date,
                "reason": reason[:300],
                "persistence": persistence,
                "scope": scope,
                "subtype": subtype,
                "decision_num": decision_num,
                "source": source,
                "task_id": task_id,
                "status": status,
                "superseded_by": superseded_by,
                "pending_items": pending_items,
                "decision_text": decision_text,
            },
            "created": date,
            "updated": date,
        }
        nodes.append(node)
    return nodes


def _decision_dedupe_key(node):
    """decision 节点去重键（D-116）：有编号用编号；无编号（格式3）用 (date, title)。

    修复 P1-4：格式3 决策 decision_num=0，旧逻辑只按 num 去重导致每次 save 重复追加。
    """
    md = node.get("metadata", {}) or {}
    num = md.get("decision_num", 0)
    if num:
        return ("num", num)
    return ("title", md.get("date", "") or "", node.get("title", "") or "")


def _extract_output_nodes(outputs_index, client_name):
    """从 outputs_index.json 提取 output 节点 + client_profile 节点。"""
    output_nodes = []
    profile_node = None

    if not outputs_index:
        return output_nodes, profile_node

    # client_profile 节点
    if isinstance(outputs_index, dict):
        industry = outputs_index.get("industry", "")
        core_need = outputs_index.get("core_requirement",
                                       outputs_index.get("core_need", ""))
        client_official = outputs_index.get("client_official_name", client_name)
        if industry or core_need:
            profile_node = {
                "id": "n000",
                "type": "client_profile",
                "title": f"{client_official}客户背景",
                "summary": f"{industry} | 核心需求: {core_need[:100]}" if core_need else industry,
                "details_path": "outputs_index.json",
                "metadata": {
                    "industry": industry,
                    "core_need": core_need,
                    "scale": (outputs_index.get("scope") or {}).get("sheets", "") if isinstance(outputs_index.get("scope"), dict) else "",
                },
                "created": outputs_index.get("first_session_date", ""),
                "updated": outputs_index.get("last_update", ""),
            }

        # output 节点
        outputs = outputs_index.get("outputs", [])
        for _i, out in enumerate(outputs):
            # W1-5：missing（已归档/缺失）条目不建节点——悬空路径不进版本链
            if isinstance(out, dict) and out.get("missing"):
                continue
            # 兼容两种格式：字符串（文件路径）或 dict（结构化）
            if isinstance(out, str):
                file_path = out
                title = os.path.basename(file_path)
                version = ""
                status = ""
                out_type = ""
                date = ""
            else:
                file_path = out.get("file", "")
                title = os.path.basename(file_path) if file_path else out.get("type", "未命名产出")
                version = out.get("version", "")
                status = out.get("status", "")
                out_type = out.get("type", "")
                date = out.get("date", "")

            output_nodes.append({
                "id": f"n{len(output_nodes)+1:03d}",
                "type": "output",
                "title": title,
                "summary": f"{out_type} {version} ({status})".strip(),
                "details_path": file_path,
                "metadata": {
                    "version": version,
                    "status": status,
                    "file_type": os.path.splitext(file_path)[1].lstrip("."),
                    "date": date,
                },
                "created": date,
                "updated": date,
            })

    return output_nodes, profile_node


def _extract_insight_nodes(client_name, insights_dir):
    """从 insights 目录提取 insight 节点。"""
    nodes = []
    if not os.path.isdir(insights_dir):
        return nodes

    for fname in sorted(os.listdir(insights_dir)):
        if not fname.startswith(f"{client_name}_") or not fname.endswith(".md"):
            continue
        fpath = os.path.join(insights_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        # 提取关键洞察和建议
        key_finding = ""
        suggestion = ""
        sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
        for sec in sections:
            if "关键洞察" in sec[:20]:
                lines = sec.strip().split("\n")
                key_finding = "\n".join(lines[1:]).strip()[:200]
            elif "建议" in sec[:15]:
                lines = sec.strip().split("\n")
                suggestion = "\n".join(lines[1:]).strip()[:200]

        # 提取日期（从文件名）
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
        date = date_match.group(1) if date_match else ""

        if key_finding or suggestion:
            nodes.append({
                "id": f"n{len(nodes)+1:03d}",
                "type": "insight",
                "title": f"洞察 {date}",
                "summary": key_finding or suggestion,
                "details_path": fpath,
                "metadata": {
                    "key_finding": key_finding,
                    "suggestion": suggestion,
                },
                "created": date,
                "updated": date,
            })
    return nodes


def _infer_edges(nodes):
    """自动推断边关系。"""
    edges = []
    profile = next((n for n in nodes if n["type"] == "client_profile"), None)

    # output -> client_profile (produced_by)
    for n in nodes:
        if n["type"] == "output" and profile:
            edges.append({"from": n["id"], "to": profile["id"],
                          "type": "produced_by", "note": ""})

    # output 版本迭代 (revised_from): 归一化标题相同的同文档不同版本
    outputs = [n for n in nodes if n["type"] == "output"]
    for i, out1 in enumerate(outputs):
        for out2 in outputs[i+1:]:
            if _same_output_series(out1, out2):
                # 较新的 -> 较旧的
                if out1["created"] >= out2["created"]:
                    edges.append({"from": out1["id"], "to": out2["id"],
                                  "type": "revised_from", "note": ""})
                else:
                    edges.append({"from": out2["id"], "to": out1["id"],
                                  "type": "revised_from", "note": ""})

    # 显式版本链：决策标题/摘要含"修订决策 N" -> supersedes
    decisions = [n for n in nodes if n["type"] == "decision"]
    for dec in decisions:
        match = re.search(r'修订决策\s*(\d+)', dec["title"] + " " + dec.get("summary", ""))
        if match:
            target_num = int(match.group(1))
            # 找编号为 target_num 的决策
            for target_dec in decisions:
                # 从 details_path 提取决策编号
                m = re.search(r'决策\s*(\d+)', target_dec.get("title", ""))
                if m and int(m.group(1)) == target_num:
                    edges.append({"from": dec["id"], "to": target_dec["id"],
                                  "type": "supersedes", "note": "title match"})
                    break

    # 传递性物化：仅 revised_from 版本链（indirectly_revised_from）；
    # 不物化 supersedes 的任意传递（M2-R2）。
    edges = _materialize_transitive_edges(edges, "revised_from")

    # 保留 stale 标记（P4 洞察过期检测）；M2-R2 已删除自动 supersedes 猜测。
    edges = _consolidate_decisions(nodes, edges)

    return edges


def _consolidate_decisions(nodes, edges):
    """保留洞察过期 stale 标记；M2-R2 已移除自动 supersedes 猜测规则。

    原规则（同 subtype + 不同日期 + 关键词重叠 >= 2 => 自动 supersedes）
    已删除，避免图产生不可审计的伪版本链。显式“修订决策 N”的 supersedes
    推断仍在 _infer_edges 中保留。
    """
    from datetime import datetime, timedelta

    # Insight stale 检测：90 天未更新（无论是否有决策都要跑）
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    for n in nodes:
        if n["type"] == "insight":
            created = n.get("created", "")
            if created and created < cutoff:
                n.setdefault("metadata", {})["stale"] = True

    return edges


def _materialize_transitive_edges(edges, edge_type="revised_from"):
    """对指定类型的边做 2 跳传递物化。
    A revised_from B, B revised_from C => A indirectly_revised_from C
    """
    direct = [(e["from"], e["to"]) for e in edges if e["type"] == edge_type]
    if not direct:
        return edges
    # 建邻接表
    adj = {}
    for f, t in direct:
        adj.setdefault(f, set()).add(t)
    # 2 跳物化：f -> t1 -> t2 则 f indirectly t2
    indirect = set()
    for f, t1 in direct:
        if t1 in adj:
            for t2 in adj[t1]:
                if t2 != f:  # 避免环
                    indirect.add((f, t2))
    existing = {(e["from"], e["to"], e["type"]) for e in edges}
    for f, t in indirect:
        if (f, t, "indirectly_revised_from") not in existing:
            edges.append({"from": f, "to": t,
                          "type": "indirectly_revised_from",
                          "note": "transitive inference"})
    return edges


def _file_hash(filepath):
    """计算文件内容的 hash（用于增量检测）。"""
    import hashlib
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
    except Exception:
        return ""


def build_client_graph(client_name):
    """从现有文件构建/更新 client_graph.json（版本链索引，不写 client_index.md）。

    增量更新（改动4）：
    - 对比源文件 hash，未变则跳过
    - decisions.md 按决策编号检测新增
    - outputs_index.json 按 file 字段检测新增/修改/删除
    - manual:true 的节点和边保留
    """
    from _paths import (client_graph_path, client_index_path,
                        INSIGHTS_DIR, CLIENTS_DIR)

    client_path = os.path.join(CLIENTS_DIR, client_name)
    if not os.path.isdir(client_path):
        return {"client": client_name, "nodes": [], "edges": []}

    decisions_path = os.path.join(client_path, "decisions.md")
    oij_path = os.path.join(client_path, "outputs_index.json")

    # ---- 增量检测：对比 source hashes ----
    new_hashes = {}
    if os.path.exists(decisions_path):
        new_hashes["decisions.md"] = _file_hash(decisions_path)
    if os.path.exists(oij_path):
        new_hashes["outputs_index.json"] = _file_hash(oij_path)
    # insights 目录 hash
    if os.path.isdir(INSIGHTS_DIR):
        import hashlib
        h = hashlib.md5(usedforsecurity=False)
        for fname in sorted(os.listdir(INSIGHTS_DIR)):
            if fname.startswith(f"{client_name}_") and fname.endswith(".md"):
                h.update(fname.encode("utf-8"))
                h.update(_file_hash(os.path.join(INSIGHTS_DIR, fname)).encode("utf-8"))
        new_hashes["insights"] = h.hexdigest()

    graph_path = client_graph_path(client_name)
    existing_graph = None
    if os.path.exists(graph_path):
        try:
            with open(graph_path, "r", encoding="utf-8") as f:
                existing_graph = json.load(f)
        except Exception:
            existing_graph = None

    # 如果 hashes 相同，跳过
    if existing_graph and existing_graph.get("_source_hashes") == new_hashes:
        return existing_graph

    # ---- 判断走全量重建还是增量更新 ----
    # 旧 graph 没有 _source_hashes 字段时走全量重建（修复历史 ID 冲突）
    is_incremental = (existing_graph and existing_graph.get("nodes")
                      and existing_graph.get("_source_hashes"))

    if is_incremental:
        return _incremental_update(client_name, existing_graph, new_hashes,
                                    decisions_path, oij_path, INSIGHTS_DIR,
                                    client_graph_path, client_index_path)
    else:
        # 全量重建
        return _full_build(client_name, decisions_path, oij_path, INSIGHTS_DIR,
                           client_graph_path, client_index_path, new_hashes)


def _full_build(client_name, decisions_path, oij_path, insights_dir,
                graph_path_fn, index_path_fn, source_hashes):
    """全量构建 client_graph.json（版本链索引；client_index.md 由 _worldbook 负责）。"""
    nodes = []
    edges = []

    # 1. client_profile + output 节点
    outputs_index = {}
    if os.path.exists(oij_path):
        try:
            with open(oij_path, "r", encoding="utf-8") as f:
                outputs_index = json.load(f)
        except Exception:
            pass

    output_nodes, profile_node = _extract_output_nodes(outputs_index, client_name)
    if profile_node:
        nodes.append(profile_node)
    nodes.extend(output_nodes)

    # 2. decision 节点（D-116：全量构建同样按去重键幂等）
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions_content = f.read()
            decision_nodes = _extract_decision_nodes(decisions_content)
            seen = set()
            for dn in decision_nodes:
                key = _decision_dedupe_key(dn)
                if key not in seen:
                    seen.add(key)
                    nodes.append(dn)
        except Exception:
            pass

    # 3. insight 节点
    insight_nodes = _extract_insight_nodes(client_name, insights_dir)
    nodes.extend(insight_nodes)

    # ---- 改动0：ID 全局重分配 ----
    for i, node in enumerate(nodes):
        if not node["id"].startswith("m"):
            node["id"] = f"n{i:03d}"

    # 4. 推断边（节点 id 已重分配，_infer_edges 直接用新 id 生成边）
    edges = _infer_edges(nodes)

    # 5. index_summary
    industry = ""
    if profile_node:
        industry = profile_node["metadata"].get("industry", "")
    decision_count = len([n for n in nodes if n["type"] == "decision"])
    output_count = len([n for n in nodes if n["type"] == "output"])
    index_summary = (f"{client_name}（{industry}），"
                     f"共 {decision_count} 条决策、{output_count} 个产出物。")

    graph = {
        "client": client_name,
        "industry": industry,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "index_summary": index_summary,
        "nodes": nodes,
        "edges": edges,
        "_source_hashes": source_hashes,
    }

    _write_graph(graph, graph_path_fn, index_path_fn, client_name)
    return graph


def _incremental_update(client_name, existing_graph, new_hashes,
                         decisions_path, oij_path, insights_dir,
                         graph_path_fn, index_path_fn):
    """增量更新：保留已有节点和 manual 数据，只追加/更新变更部分。

    D-116：先对现有图做 decision 键去重自愈（清洗历史膨胀的重复节点与连边），
    再按去重键检测新增。
    """
    existing_nodes = existing_graph.get("nodes", [])
    existing_edges = existing_graph.get("edges", [])

    # ---- D-116 自愈：现有 decision 节点按去重键清洗（保留首个）----
    seen_decision_keys = set()
    drop_ids = set()
    healed_nodes = []
    for n in existing_nodes:
        if n["type"] == "decision":
            key = _decision_dedupe_key(n)
            if key in seen_decision_keys:
                drop_ids.add(n["id"])
                continue
            seen_decision_keys.add(key)
        healed_nodes.append(n)
    if drop_ids:
        existing_nodes = healed_nodes
        existing_edges = [e for e in existing_edges
                          if e.get("from") not in drop_ids
                          and e.get("to") not in drop_ids]

    # 分离 manual 数据
    manual_nodes = [n for n in existing_nodes if n.get("manual") is True]
    manual_edges = [e for e in existing_edges if e.get("manual") is True]

    # ---- decisions 增量：按去重键对账（D-116 键集合；B3 补编辑/删除传播）----
    # 提取成功才对账（decisions_ok）：失败不传播删除、不记 hash（下次重试防固化）
    new_decision_nodes = []
    stale_decision_ids = set()
    decisions_ok = False
    all_decision_nodes = []
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions_content = f.read()
            all_decision_nodes = _extract_decision_nodes(decisions_content)
            decisions_ok = True
        except Exception:
            pass
    if decisions_ok:
        fresh_by_key = {}
        for d in all_decision_nodes:
            key = _decision_dedupe_key(d)
            fresh_by_key[key] = d
            if key not in seen_decision_keys:
                new_decision_nodes.append(d)
                seen_decision_keys.add(key)  # 批内去重
        for n in existing_nodes:
            if n["type"] != "decision" or n.get("manual"):
                continue
            key = _decision_dedupe_key(n)
            fresh = fresh_by_key.get(key)
            if fresh is None:
                # key 已不在当前 decisions.md -> 编辑改号/删除，传播移除
                stale_decision_ids.add(n["id"])
            else:
                # 同 key 内容漂移（编辑）：原位刷新字段，保留节点 id 与连边
                n["title"] = fresh["title"]
                n["summary"] = fresh["summary"]
                n["details_path"] = fresh["details_path"]
                n["metadata"] = fresh["metadata"]
                n["updated"] = datetime.now().strftime("%Y-%m-%d")

    # ---- outputs 增量：按 file 检测新增/修改/删除 ----
    # outputs_index_ok：文件存在但读失败/格式异常 = 状态未知，原样保留存量
    # output 节点（瞬时读失败曾把全部产出误标 removed 且 hash 照记固化）
    outputs_index_ok = True
    new_outputs_index = None
    if os.path.exists(oij_path):
        try:
            with open(oij_path, "r", encoding="utf-8") as f:
                new_outputs_index = json.load(f)
            if not isinstance(new_outputs_index, dict):
                outputs_index_ok = False
        except Exception:
            outputs_index_ok = False

    new_output_files = set()
    new_output_map = {}  # file -> out dict
    if outputs_index_ok and isinstance(new_outputs_index, dict):
        for out in new_outputs_index.get("outputs", []):
            if isinstance(out, dict):
                # W1-5：missing（已归档/缺失）条目不进增量产出集，
                # 对应存量节点落入下方「不在新文件中」分支标 removed
                # （与全量重建 _extract_output_nodes 的过滤口径一致）
                if out.get("missing"):
                    continue
                f = out.get("file", "")
            else:
                f = out
            if f:
                new_output_files.add(f)
                new_output_map[f] = out

    # 检测已有 output 节点的状态变化
    updated_nodes = []
    removed_count = 0
    for n in existing_nodes:
        if n["type"] != "output":
            continue
        if not outputs_index_ok:
            updated_nodes.append(n)
            continue
        # 从 details_path 或 title 找 file
        f = n.get("details_path", "") or n.get("title", "")
        if f in new_output_files:
            # 仍存在 -> 检查是否修改
            out_data = new_output_map.get(f)
            if isinstance(out_data, dict):
                new_status = out_data.get("status", "")
                old_status = n["metadata"].get("status", "")
                if new_status and new_status != old_status:
                    n["metadata"]["status"] = new_status
                    n["updated"] = datetime.now().strftime("%Y-%m-%d")
        else:
            # 不在新文件中 -> 标记 removed
            if n["metadata"].get("status") != "removed":
                n["metadata"]["status"] = "removed"
                n["updated"] = datetime.now().strftime("%Y-%m-%d")
                removed_count += 1
        updated_nodes.append(n)

    # 新增的 output 节点
    existing_output_files = set()
    for n in existing_nodes:
        if n["type"] == "output":
            f = n.get("details_path", "") or n.get("title", "")
            existing_output_files.add(f)

    new_output_nodes = []
    for f in new_output_files:
        if f not in existing_output_files:
            out_data = new_output_map.get(f, f)
            # 复用 _extract_output_nodes 的逻辑
            single_outputs = {"outputs": [out_data]}
            nodes_from_single, _ = _extract_output_nodes(single_outputs, client_name)
            new_output_nodes.extend(nodes_from_single)

    # ---- insights 增量：按文件名检测新增 ----
    existing_insight_files = set()
    for n in existing_nodes:
        if n["type"] == "insight":
            existing_insight_files.add(n.get("details_path", ""))

    new_insight_nodes = []
    all_insight_nodes = _extract_insight_nodes(client_name, insights_dir)
    for ins in all_insight_nodes:
        if ins.get("details_path", "") not in existing_insight_files:
            new_insight_nodes.append(ins)

    # ---- 合并：已有节点（保留 + 更新）+ 新节点 + manual ----
    # 保留非 manual 的已有节点（已在上面更新了 output 的 status）
    kept_nodes = [n for n in existing_nodes if not n.get("manual")]
    # 但只保留非 output 的已有节点（output 已经在 updated_nodes 中处理了）；
    # stale 决策（编辑改号/删除）不保留（B3 传播移除）
    kept_non_output = [n for n in kept_nodes if n["type"] != "output"
                       and n["id"] not in stale_decision_ids]

    all_new_nodes = new_decision_nodes + new_output_nodes + new_insight_nodes

    # 给新节点分配 ID（取 max + 1）
    max_num = 0
    for n in existing_nodes:
        if n["id"].startswith("n") and n["id"][1:].isdigit():
            max_num = max(max_num, int(n["id"][1:]))
        elif n["id"].startswith("m") and n["id"][1:].isdigit():
            max_num = max(max_num, int(n["id"][1:]))

    for i, node in enumerate(all_new_nodes):
        node["id"] = f"n{max_num + i + 1:03d}"

    merged_nodes = kept_non_output + updated_nodes + all_new_nodes + manual_nodes

    # ---- 重新推断边（全量重算，因为新节点需要推断边）----
    edges = _infer_edges(merged_nodes)
    # 保留 manual 边
    edges.extend(manual_edges)

    # 更新 index_summary
    industry = existing_graph.get("industry", "")
    decision_count = len([n for n in merged_nodes if n["type"] == "decision"])
    output_count = len([n for n in merged_nodes if n["type"] == "output"])
    index_summary = (f"{client_name}（{industry}），"
                     f"共 {decision_count} 条决策、{output_count} 个产出物。")

    # P2（B3）：只记处理成功的源 hash——decisions 提取 / outputs_index 读失败
    # 不落对应 hash，下次 hash 不匹配自动重试；旧逻辑「先记 hash 后处理、
    # 失败照记」曾让失败固化（编辑/删除永不传播）
    saved_hashes = dict(new_hashes)
    if not decisions_ok:
        saved_hashes.pop("decisions.md", None)
    if not outputs_index_ok:
        saved_hashes.pop("outputs_index.json", None)

    graph = {
        "client": client_name,
        "industry": industry,
        "created": existing_graph.get("created", datetime.now().strftime("%Y-%m-%d")),
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "index_summary": index_summary,
        "nodes": merged_nodes,
        "edges": edges,
        "_source_hashes": saved_hashes,
    }

    _write_graph(graph, graph_path_fn, index_path_fn, client_name)
    return graph


def _atomic_write_json(path, data):
    """原子写 JSON：先写同目录 tmp 再 os.replace（P3-6，照 _embed_index
    _save_npy 的 tmp+replace 范式）——中断只留 .tmp 残片，不会留下半截
    client_graph.json 让加载侧 json.load 直接炸掉。"""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _write_graph(graph, graph_path_fn, index_path_fn, client_name):
    """写 client_graph.json（版本链索引）。

    M2-R1：client_index.md 不再由 _graph 生成，改由 _worldbook.build_worldbook
    直读真源单独负责。index_path_fn 仅保留参数兼容旧调用方，不使用。
    """
    try:
        os.makedirs(os.path.dirname(graph_path_fn(client_name)), exist_ok=True)
        _atomic_write_json(graph_path_fn(client_name), graph)
    except Exception as e:
        print(f"[graph-build] 写 client_graph.json 失败: {e}")


def search_graph_nodes(client_name, query, include_removed=False):
    """按自由文本搜索节点标题/摘要（大小写不敏感）。

    简单匹配策略：把 query 按空白拆成 tokens，任一 token 出现在
    title + summary 中即返回该节点（不做排序/重排，适合人工调试）。
    """
    from _paths import client_graph_path

    graph_path = client_graph_path(client_name)
    if not os.path.exists(graph_path):
        return {"client": client_name, "nodes": [], "edges": [], "error": "graph not found"}

    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except Exception as e:
        return {"client": client_name, "nodes": [], "edges": [], "error": str(e)}

    nodes = graph.get("nodes", [])
    if not include_removed:
        nodes = [n for n in nodes if n.get("metadata", {}).get("status") != "removed"]

    q = (query or "").strip()
    if not q:
        return {"client": client_name, "nodes": [], "edges": [], "error": "empty query"}

    tokens = [t.lower() for t in q.split() if t]
    matched = []
    for n in nodes:
        text = f"{n.get('title', '')} {n.get('summary', '')}".lower()
        if any(t in text for t in tokens):
            matched.append(n)
    return {"client": client_name, "nodes": matched, "edges": []}


def query_graph(client_name, node_id=None, node_type=None, edges_of=None, include_removed=False):
    """查询 client_graph.json 中的节点和边。

    - node_id: 指定节点 ID，返回该节点 + 关联边
    - node_type: 按类型过滤节点
    - edges_of: 返回与指定节点关联的所有边
    """
    from _paths import client_graph_path

    graph_path = client_graph_path(client_name)
    if not os.path.exists(graph_path):
        return {"client": client_name, "nodes": [], "edges": [], "error": "graph not found"}

    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except Exception as e:
        return {"client": client_name, "nodes": [], "edges": [], "error": str(e)}

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # 默认不返回 status:removed 的节点（D-028）
    if not include_removed:
        nodes = [n for n in nodes if n.get("metadata", {}).get("status") != "removed"]

    # 按节点 ID 查询
    if node_id:
        matched = [n for n in nodes if n["id"] == node_id]
        related_edges = [e for e in edges if e["from"] == node_id or e["to"] == node_id]
        return {"client": client_name, "nodes": matched, "edges": related_edges}

    # 按类型过滤
    if node_type:
        nodes = [n for n in nodes if n["type"] == node_type]

    # 按边的关联节点查询
    if edges_of:
        related_edges = [e for e in edges if e["from"] == edges_of or e["to"] == edges_of]
        return {"client": client_name, "nodes": nodes, "edges": related_edges}

    return {"client": client_name, "nodes": nodes, "edges": edges}


def add_graph_node(client_name, node_type, title, summary=""):
    """人工调试：手动添加版本链索引节点到 client_graph.json。

    返回 {"node": 新节点, "graph": 更新后的 graph}
    """
    from _paths import client_graph_path

    graph_path = client_graph_path(client_name)
    if not os.path.exists(graph_path):
        # graph 不存在，先 build
        build_client_graph(client_name)

    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except Exception:
        graph = {"client": client_name, "nodes": [], "edges": []}

    nodes = graph.get("nodes", [])
    # 生成新 ID（n=自动节点，m=手动节点，两种前缀都要统计否则 m 前缀会撞号）
    max_num = 0
    for n in nodes:
        nid = n.get("id", "")
        if len(nid) > 1 and nid[0] in ("n", "m") and nid[1:].isdigit():
            max_num = max(max_num, int(nid[1:]))
    # 手动添加的节点用 m 前缀避免冲突
    new_id = f"m{max_num + 1:03d}"

    now = datetime.now().strftime("%Y-%m-%d")
    new_node = {
        "id": new_id,
        "type": node_type,
        "title": title,
        "summary": summary[:200] if summary else title,
        "details_path": "",
        "metadata": {},
        "created": now,
        "updated": now,
        "manual": True,
    }
    nodes.append(new_node)
    graph["nodes"] = nodes
    graph["updated"] = now

    try:
        _atomic_write_json(graph_path, graph)
    except Exception as e:
        print(f"[graph-add] 写 client_graph.json 失败: {e}")

    return {"node": new_node, "graph": graph}


def add_graph_edge(client_name, from_id, to_id, edge_type, note=""):
    """手动添加边到 client_graph.json。

    返回 {"edge": 新边, "graph": 更新后的 graph}
    """
    from _paths import client_graph_path

    graph_path = client_graph_path(client_name)
    if not os.path.exists(graph_path):
        return {"edge": None, "error": "graph not found, run graph-build first"}

    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except Exception as e:
        return {"edge": None, "error": str(e)}

    edges = graph.get("edges", [])
    new_edge = {"from": from_id, "to": to_id, "type": edge_type, "note": note, "manual": True}
    edges.append(new_edge)
    graph["edges"] = edges
    graph["updated"] = datetime.now().strftime("%Y-%m-%d")

    try:
        _atomic_write_json(graph_path, graph)
    except Exception as e:
        print(f"[graph-link] 写 client_graph.json 失败: {e}")

    return {"edge": new_edge, "graph": graph}
