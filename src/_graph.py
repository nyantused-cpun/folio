# -*- coding: utf-8 -*-
"""世界书模块：client_graph.json + client_index.md 构建与查询。

从 _session.py 拆分（候选 4 · 模块化），无内部依赖（叶子模块）。
"""
import os
import json
import re
from datetime import datetime


__all__ = [
    # 常量
    "DECISION_SUBTYPES", "_STOPWORDS",
    # 函数
    "_infer_decision_subtype", "_extract_keywords",
    "_extract_decision_nodes", "_extract_output_nodes", "_extract_insight_nodes",
    "_infer_edges", "_materialize_transitive_edges", "_consolidate_decisions",
    "_generate_client_index", "_file_hash",
    "build_client_graph", "_full_build", "_incremental_update",
    "_write_graph", "query_graph", "_expand_graph_2hop", "_find_pivot_nodes",
    "add_graph_node", "add_graph_edge",
]


# ============================================================
# 世界书：client_graph.json + client_index.md（spec 第三块）
# ============================================================

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

# 中文停用词（边推断关键词匹配时过滤）- 用集合存储完整词而非单字符
_STOPWORDS = {"的", "在", "了", "和", "与", "及", "或", "而", "但", "也",
              "要", "就", "都", "还", "又", "不", "这", "那", "个",
              "把", "被", "让", "使", "往", "向", "从", "对", "给", "为",
              "以", "是", "着", "过"}


def _extract_keywords(text, min_len=2):
    """提取中文关键词（2字以上片段），去停用词。"""
    if not text:
        return set()
    # 取连续中文字符片段
    segments = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    result = set()
    for seg in segments:
        for i in range(len(seg) - min_len + 1):
            piece = seg[i:i+min_len]
            if piece not in _STOPWORDS:
                result.add(piece)
    return result


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
    # 兼容三种格式切分：## 决策 N / ### D-NNN / ## 日期（可带 []）
    blocks = re.split(r'(?=^(?:## 决策 \d+|### D-\d+|## \[?\d{4}-\d{2}-\d{2}\]?))',
                      decisions_content, flags=re.MULTILINE)
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
            # 兼容两种格式：字符串（文件路径）或 dict（结构化）
            if isinstance(out, str):
                file_path = out
                title = os.path.basename(file_path)
                version = ""
                status = ""
                out_type = ""
                date = ""
                method = ""
            else:
                file_path = out.get("file", "")
                title = os.path.basename(file_path) if file_path else out.get("type", "未命名产出")
                version = out.get("version", "")
                status = out.get("status", "")
                out_type = out.get("type", "")
                date = out.get("date", "")
                method = out.get("method", "")

            output_nodes.append({
                "id": f"n{len(output_nodes)+1:03d}",
                "type": "output",
                "title": title,
                "summary": f"{out_type} {version} ({status})".strip(),
                "details_path": file_path,
                "metadata": {
                    "version": version,
                    "status": status,
                    "method": method,
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

    # output -> method (used_method)
    for n in nodes:
        method = n["metadata"].get("method", "") if n["type"] == "output" else ""
        if method:
            # 找或建 method 节点
            method_node = next((m for m in nodes if m["type"] == "method"
                                and m["title"] == method), None)
            if method_node:
                edges.append({"from": n["id"], "to": method_node["id"],
                              "type": "used_method", "note": ""})

    # ---- 改动1：补边推断（decided_by / supersedes / triggers）----

    decisions = [n for n in nodes if n["type"] == "decision"]

    # decided_by: output -> decision（关键词重叠）
    for out in outputs:
        out_kw = _extract_keywords(out["title"])
        if not out_kw:
            continue
        for dec in decisions:
            dec_kw = _extract_keywords(dec["title"])
            if out_kw & dec_kw:
                edges.append({"from": out["id"], "to": dec["id"],
                              "type": "decided_by", "note": "keyword match"})
                break  # 每个output只关联一个最匹配的decision

    # supersedes: decision -> decision（标题含"修订决策 N"）
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

    # triggers: decision -> output（日期 <= + 关键词重叠）
    for dec in decisions:
        dec_kw = _extract_keywords(dec["title"])
        if not dec_kw:
            continue
        for out in outputs:
            out_kw = _extract_keywords(out["title"])
            if not out_kw:
                continue
            if not (dec_kw & out_kw):
                continue
            # 日期检查：决策日期 <= 产出物日期
            dec_date = dec.get("created", "")
            out_date = out.get("created", "")
            if dec_date and out_date and dec_date <= out_date:
                edges.append({"from": dec["id"], "to": out["id"],
                              "type": "triggers", "note": "keyword+date match"})

    # ---- 改动3：传递性物化（indirectly_revised_from）----
    edges = _materialize_transitive_edges(edges, "revised_from")

    # ---- P4: Consolidate —— 同 subtype + 不同日期 + 关键词重叠 => supersedes ----
    edges = _consolidate_decisions(nodes, edges)

    return edges


def _consolidate_decisions(nodes, edges):
    """Consolidate：检测同 subtype 决策的时间覆盖关系。

    规则：
    - 同 subtype + 不同日期 + 标题关键词重叠 >= 2 => 新决策 supersedes 旧决策
    - 同日期的决策不互相覆盖（同一次会话提取的互补决策）
    - 被覆盖的决策标记 metadata.superseded_by
    - 90 天未被引用的 insight 标记 stale
    """
    from datetime import datetime, timedelta

    # Insight stale 检测：90 天未更新（无论是否有决策都要跑）
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    for n in nodes:
        if n["type"] == "insight":
            created = n.get("created", "")
            if created and created < cutoff:
                n.setdefault("metadata", {})["stale"] = True

    decisions = [n for n in nodes if n["type"] == "decision"
                 and n.get("metadata", {}).get("status") != "removed"]
    if len(decisions) < 2:
        return edges

    # 按 subtype 分组
    by_subtype = {}
    for d in decisions:
        sub = d.get("metadata", {}).get("subtype", "general")
        by_subtype.setdefault(sub, []).append(d)

    existing_supersedes = {(e["from"], e["to"]) for e in edges if e["type"] == "supersedes"}
    new_edges = []

    for sub, group in by_subtype.items():
        if len(group) < 2:
            continue
        # 按日期排序
        group.sort(key=lambda x: x.get("created", ""))
        # 两两比较：新 vs 旧
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                older = group[i]
                newer = group[j]
                # 同日期不覆盖
                if older.get("created", "") == newer.get("created", ""):
                    continue
                # 关键词重叠检测
                older_kw = _extract_keywords(older.get("title", "") + " " + older.get("summary", ""))
                newer_kw = _extract_keywords(newer.get("title", "") + " " + newer.get("summary", ""))
                overlap = older_kw & newer_kw
                if len(overlap) >= 2:
                    pair = (newer["id"], older["id"])
                    if pair not in existing_supersedes:
                        new_edges.append({
                            "from": newer["id"], "to": older["id"],
                            "type": "supersedes",
                            "note": f"auto-consolidate: same subtype '{sub}', overlap={len(overlap)}"
                        })
                        existing_supersedes.add(pair)
                        # 标记旧决策被覆盖
                        older.setdefault("metadata", {})["superseded_by"] = newer["id"]

    return edges + new_edges


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


def _generate_client_index(graph):
    """从 client_graph.json 生成 client_index.md（≤ 80 行）。"""
    client = graph.get("client", "")
    summary = graph.get("index_summary", "")
    nodes = graph.get("nodes", [])

    lines = [f"# {client} 索引", ""]
    if summary:
        lines.append(f"> {summary}")
        lines.append("")

    # client_profile
    profiles = [n for n in nodes if n["type"] == "client_profile"]
    if profiles:
        lines.append("## 客户背景")
        for p in profiles:
            lines.append(f"- {p['summary']} -> [详情]({p.get('details_path', '')})")
        lines.append("")

    # 决策时间线（共 N 条，最近 10 条，排除被覆盖的）
    decisions = [n for n in nodes if n["type"] == "decision"
                 and n["metadata"].get("status") != "removed"
                 and not n["metadata"].get("superseded_by")]  # P4: 排除已被覆盖
    decisions.sort(key=lambda x: x.get("created", ""), reverse=True)
    superseded_count = len([n for n in nodes if n["type"] == "decision"
                            and n.get("metadata", {}).get("superseded_by")])
    if decisions:
        header = f"## 决策时间线（共 {len(decisions)} 条有效"
        if superseded_count:
            header += f"，{superseded_count} 条已被覆盖"
        header += "，最近 10 条）"
        lines.append(header)
        for i, d in enumerate(decisions[:10], 1):
            date = d.get("created", "")
            lines.append(f"{i}. [{date}] {d['title']} - {d['summary'][:150]}")
        lines.append("")

    # 产出物（共 N 个，最近 8 个）
    outputs = [n for n in nodes if n["type"] == "output"
               and n["metadata"].get("status") != "removed"]
    outputs.sort(key=lambda x: x.get("created", ""), reverse=True)
    if outputs:
        lines.append(f"## 产出物（共 {len(outputs)} 个，最近 8 个）")
        lines.append("| 版本 | 标题 | 状态 | 日期 |")
        lines.append("|------|------|------|------|")
        for o in outputs[:8]:
            v = o["metadata"].get("version", "")
            s = o["metadata"].get("status", "")
            d = o.get("created", "")
            lines.append(f"| {v} | {o['title'][:40]} | {s} | {d} |")
        lines.append("")

    # 洞察（最近 5 条，排除 stale）
    insights = [n for n in nodes if n["type"] == "insight"
                and not n.get("metadata", {}).get("stale")]  # P4: 排除过期
    if insights:
        lines.append("## 洞察")
        for ins in insights[:5]:
            lines.append(f"- [{ins.get('created', '')}] {ins['summary'][:120]}")
        lines.append("")

    # 方法论
    methods = [n for n in nodes if n["type"] == "method"]
    if methods:
        lines.append("## 方法论使用记录")
        lines.append("| 方法论 | 使用次数 | 最近使用 |")
        lines.append("|--------|---------|---------|")
        for m in methods:
            count = m["metadata"].get("usage_count", 0)
            last = m["metadata"].get("last_used", "")
            lines.append(f"| {m['title']} | {count} | {last} |")
        lines.append("")

    # 截断到 120 行
    if len(lines) > 120:
        lines = lines[:119] + ["...(完整列表见 client_graph.json)"]

    return "\n".join(lines)


def _file_hash(filepath):
    """计算文件内容的 hash（用于增量检测）。"""
    import hashlib
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
    except Exception:
        return ""


def build_client_graph(client_name):
    """从现有文件构建/更新 client_graph.json + client_index.md。

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
    """全量构建 client_graph.json + client_index.md（含 ID 重分配）。"""
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

    # ---- decisions 增量：按去重键检测新增（D-116，复用自愈步骤的键集合）----
    new_decision_nodes = []
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                decisions_content = f.read()
            all_decision_nodes = _extract_decision_nodes(decisions_content)
            for d in all_decision_nodes:
                key = _decision_dedupe_key(d)
                if key not in seen_decision_keys:
                    new_decision_nodes.append(d)
                    seen_decision_keys.add(key)  # 批内去重
        except Exception:
            pass

    # ---- outputs 增量：按 file 检测新增/修改/删除 ----
    new_outputs_index = {}
    if os.path.exists(oij_path):
        try:
            with open(oij_path, "r", encoding="utf-8") as f:
                new_outputs_index = json.load(f)
        except Exception:
            pass

    new_output_files = set()
    new_output_map = {}  # file -> out dict
    if isinstance(new_outputs_index, dict):
        for out in new_outputs_index.get("outputs", []):
            if isinstance(out, dict):
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
    # 但只保留非 output 的已有节点（output 已经在 updated_nodes 中处理了）
    kept_non_output = [n for n in kept_nodes if n["type"] != "output"]

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

    graph = {
        "client": client_name,
        "industry": industry,
        "created": existing_graph.get("created", datetime.now().strftime("%Y-%m-%d")),
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "index_summary": index_summary,
        "nodes": merged_nodes,
        "edges": edges,
        "_source_hashes": new_hashes,
    }

    _write_graph(graph, graph_path_fn, index_path_fn, client_name)
    return graph


def _write_graph(graph, graph_path_fn, index_path_fn, client_name):
    """写 client_graph.json + client_index.md。"""
    try:
        os.makedirs(os.path.dirname(graph_path_fn(client_name)), exist_ok=True)
        with open(graph_path_fn(client_name), "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[graph-build] 写 client_graph.json 失败: {e}")

    index_md = _generate_client_index(graph)
    try:
        with open(index_path_fn(client_name), "w", encoding="utf-8") as f:
            f.write(index_md)
    except Exception as e:
        print(f"[graph-build] 写 client_index.md 失败: {e}")


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


def _expand_graph_2hop(graph_path, node_id):
    """图扩展召回：从指定节点出发，沿边扩展 2 跳，返回关联节点列表。

    返回 [{"id", "title", "summary", "type", "edge_type", "hops"}, ...]
    hops=1 表示直接关联，hops=2 表示间接关联。
    """
    if not os.path.exists(graph_path):
        return []
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = json.load(f)
    except Exception:
        return []

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_map = {n["id"]: n for n in nodes}

    if node_id not in node_map:
        return []

    def _entry(target, edge_type, hops):
        return {
            "id": target["id"],
            "title": target.get("title", ""),
            "summary": target.get("summary", ""),
            "type": target.get("type", ""),
            "edge_type": edge_type,
            "hops": hops,
        }

    result = []
    visited = {node_id}

    # 1 跳：直接关联的节点
    hop1_ids = set()
    for e in edges:
        if e["from"] == node_id and e["to"] not in visited:
            hop1_ids.add(e["to"])
            target = node_map.get(e["to"])
            if target:
                result.append(_entry(target, e["type"], 1))
                visited.add(e["to"])
        elif e["to"] == node_id and e["from"] not in visited:
            hop1_ids.add(e["from"])
            target = node_map.get(e["from"])
            if target:
                result.append(_entry(target, e["type"], 1))
                visited.add(e["from"])

    # 2 跳：从 1 跳节点再扩展
    for hop1_id in list(hop1_ids):
        for e in edges:
            other_id = None
            if e["from"] == hop1_id and e["to"] not in visited:
                other_id = e["to"]
            elif e["to"] == hop1_id and e["from"] not in visited:
                other_id = e["from"]
            if other_id:
                target = node_map.get(other_id)
                if target:
                    result.append(_entry(target, e["type"], 2))
                    visited.add(other_id)

    return result


def _find_pivot_nodes(query_text, graph, top_k=3):
    """Pivot Search：用查询文本关键词匹配图节点，返回 top_k 个入口节点。

    匹配逻辑：query 关键词与节点 title+summary 关键词的交集大小排序。
    跳过 status=removed 的节点。
    优先返回有边连接的节点（孤立节点扩展无意义）。
    返回 [{"node": node_dict, "score": overlap_count}, ...]
    """
    if not query_text:
        return []
    query_kw = _extract_keywords(query_text)
    if not query_kw:
        return []

    # 预计算有边的节点集合
    connected_ids = set()
    for e in graph.get("edges", []):
        connected_ids.add(e["from"])
        connected_ids.add(e["to"])

    scored = []
    for n in graph.get("nodes", []):
        if n.get("metadata", {}).get("status") == "removed":
            continue
        node_text = n.get("title", "") + " " + n.get("summary", "")
        node_kw = _extract_keywords(node_text)
        overlap = len(query_kw & node_kw)
        if overlap > 0:
            # 有边连接的节点加分（确保扩展有意义）
            bonus = 1 if n["id"] in connected_ids else 0
            # output 节点优先（local 层优先命中具体产出物，而非工程决策）
            type_bonus = 1 if n["type"] == "output" else 0
            scored.append({"node": n, "score": overlap + bonus + type_bonus})

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def add_graph_node(client_name, node_type, title, summary="", method=""):
    """手动添加节点到 client_graph.json。

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

    metadata = {}
    if method:
        metadata["method"] = method

    now = datetime.now().strftime("%Y-%m-%d")
    new_node = {
        "id": new_id,
        "type": node_type,
        "title": title,
        "summary": summary[:200] if summary else title,
        "details_path": "",
        "metadata": metadata,
        "created": now,
        "updated": now,
        "manual": True,
    }
    nodes.append(new_node)
    graph["nodes"] = nodes
    graph["updated"] = now

    try:
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
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
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[graph-link] 写 client_graph.json 失败: {e}")

    return {"edge": new_edge, "graph": graph}
