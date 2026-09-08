# -*- coding: utf-8 -*-
"""世界书直生模块：直接从真源生成 client_index.md（M2-R1）。

M2-R1：client_index.md（世界书）不再经过 client_graph.json，改为直接读：
- _knowledge/clients/{client}/decisions.md
- _knowledge/clients/{client}/outputs_index.json
- _knowledge/clients/{client}/insights/ 或全局 INSIGHTS_DIR
- 可选 preferences.md / context.md 背景

R1-3 固定段序：
1. # {客户} 世界书
2. ## 客户背景
3. ## 决策时间线
4. ## 产出物版本表
5. ## 待办 / 悬而未决

R1-5：生成时在 front matter 记录 _source_hashes，供 audit 新鲜度检查。

预算/优先级（I-8 已实现）：决策时间线按“permanent > 最近 task”优先级丢尾，
总条数受 TIMELINE_MAX_ITEMS 预算约束；句子不截半由 _clean_text 保证。
"""
import os
import re
import json
import hashlib

import _paths
from _graph import (
    _split_decision_blocks,
    _extract_decision_nodes,
    _file_hash,
    _normalize_output_title,
)


__all__ = [
    "build_worldbook",
    "read_source_hashes",
    "compute_source_hashes",
    "is_client_session_task",
]


# 时间线条目摘要上限；超过后只在句子边界截断，绝不切半句。
TIMELINE_SUMMARY_MAX_CHARS = 240
# task 决策最新条数（R1-3）
RECENT_TASK_LIMIT = 10
# I-8 丢尾预算：决策时间线总条数上限（permanent > 最近 task，超预算从低优先级丢）
TIMELINE_MAX_ITEMS = 50
# 版本表用 normalized title 系列；避免同一系列 html/xlsx 混淆，按 file_type 分组
_ENGINEERING_NOISE_RE = re.compile(
    # 明确内部工程/工具/CLI/沉淀/迁移指针才过滤；不用裸“测试”二字，保护客户测试计划决策。
    r"review\s*FAIL|审查未通过|审查失败|已迁.*代码修改|工程侧剥离|全文见.*代码修改|"
    r"架构图\s+skill\s*沉淀|skill\s*沉淀|"
    r"需求清单转\s*xlsx|openpyxl\s*临时方案|"
    r"UI\s*规范.*CLI\s*下沉|CLI\s*下沉计划|"
    r"单元测试|unit[-\s]*test|回归测试|"
    r"CLI\s*(?:子命令|命令|工具|化|下沉|迁移)",
    re.IGNORECASE,
)
_CLIENT_SESSION_TASK_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}#")
_DEPRECATED_STATUS_RE = re.compile(r"已废弃|removed|superseded")


def _clean_text(value, max_chars=None):
    """压缩换行/多个空格；超过 max_chars 时优先在句子边界截断。"""
    if not value:
        return ""
    text = re.sub(r"\s*\n\s*", " ", str(value)).strip()
    if max_chars is None or len(text) <= max_chars:
        return text
    # 找 max_chars 前的最后一个句末标点，保证不切半句
    for punct in "。！？；\n":
        idx = text.rfind(punct, 0, max_chars)
        if idx >= max_chars * 0.5:
            return text[:idx + 1].strip()
    # 找不到句末标点则保留全文，宁可长也不截半句
    return text


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def compute_source_hashes(client_dir, insights_dir=None):
    """计算真源哈希：decisions.md / outputs_index.json / insights。"""
    hashes = {}
    decisions_path = os.path.join(client_dir, "decisions.md")
    oij_path = os.path.join(client_dir, "outputs_index.json")
    if os.path.exists(decisions_path):
        hashes["decisions.md"] = _file_hash(decisions_path)
    if os.path.exists(oij_path):
        hashes["outputs_index.json"] = _file_hash(oij_path)
    if insights_dir is None:
        insights_dir = _paths.INSIGHTS_DIR
    if os.path.isdir(insights_dir):
        client_name = os.path.basename(os.path.abspath(client_dir))
        h = hashlib.md5(usedforsecurity=False)
        for fname in sorted(os.listdir(insights_dir)):
            if fname.startswith(f"{client_name}_") and fname.endswith(".md"):
                h.update(fname.encode("utf-8"))
                h.update(_file_hash(os.path.join(insights_dir, fname)).encode("utf-8"))
        hashes["insights"] = h.hexdigest()
    return hashes


def _insert_front_matter(content, source_hashes):
    """在 client_index.md 顶部写入 YAML front matter 记录 _source_hashes。"""
    lines = ["---", "_source_hashes:"]
    for key in ("decisions.md", "outputs_index.json", "insights"):
        if key in source_hashes:
            lines.append(f"  {key}: {source_hashes[key]}")
    lines.append("---")
    return "\n".join(lines) + "\n" + content.lstrip("\n")


def read_source_hashes(md_path):
    """从 client_index.md front matter 读 _source_hashes。"""
    if not md_path or not os.path.exists(md_path):
        return {}
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    m = re.match(
        r"^---\s*\n(?P<body>.*?)\n---\s*\n",
        text,
        re.DOTALL,
    )
    if not m:
        return {}
    hashes = {}
    for line in m.group("body").splitlines():
        mm = re.match(r"\s*_source_hashes:\s*$", line)
        if mm:
            continue
        kv = re.match(r"\s+([A-Za-z0-9_./-]+):\s*([0-9a-f]+)", line)
        if kv:
            hashes[kv.group(1)] = kv.group(2)
    return hashes


def is_client_session_task(node):
    """判断 scope=task 条目是否为「客户会话 task」而非工程 task。

    真实数据（2026-08-30 盘点）：
    - 客户会话 task 条目由 append_session_decision 写入：task_id=YYYY-MM-DD#第N次，
      source="user:会话决策"。
    - 工程/工具型 task 条目缺少该 source 或 task_id 为时间戳/D-xxx 等非会话标识。
    """
    md = node.get("metadata", {}) or {}
    source = md.get("source", "") or ""
    task_id = md.get("task_id", "") or ""
    return bool(
        "user:会话决策" in source
        or "#第" in task_id
        or _CLIENT_SESSION_TASK_ID_RE.match(task_id)
    )


def _is_noise_decision(node, block=None):
    """显式噪音分类器：review FAIL/审查失败、跨客户迁移指针、内部工程过程条目。

    注意：不再以 task_id 前缀/source 是否为“用户:会话决策”来排除客户 task。
    客户项目 task（scope=task）是客户全景的一部分；只有命中明确噪音规则才过滤。
    """
    md = node.get("metadata", {}) or {}
    title = node.get("title", "") or ""
    summary = node.get("summary", "") or ""
    decision_text = md.get("decision_text", "") or ""
    haystack = " ".join([title, summary, decision_text, block or ""])
    return bool(_ENGINEERING_NOISE_RE.search(haystack))


def _is_deprecated_or_superseded(node, block=None):
    """排除 superseded/removed/已废弃/未决冲突块。"""
    md = node.get("metadata", {}) or {}
    status = md.get("status", "") or ""
    superseded_by = md.get("superseded_by", "") or ""
    if _DEPRECATED_STATUS_RE.search(status) or superseded_by:
        return True
    if block and ("<!-- conflict: pending -->" in block or "状态**：已废弃" in block):
        return True
    return False


def _parse_decision_nodes(client_dir):
    """读 decisions.md，附上原始 block 文本供噪音/废弃判断。"""
    decisions_path = os.path.join(client_dir, "decisions.md")
    if not os.path.exists(decisions_path):
        return []
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []
    nodes = _extract_decision_nodes(content)
    blocks = _split_decision_blocks(content)[1:]
    # 过滤出真正以决策标题开头的块；与 _extract_decision_nodes 顺序一致
    valid_blocks = []
    for block in blocks:
        stripped = block.strip()
        if re.match(r"^(?:## 决策|### D-|## \[?\d{4}-\d{2}-\d{2}\]?)", stripped):
            valid_blocks.append(block)
    return list(zip(nodes, valid_blocks[:len(nodes)], strict=False))


def _decision_sort_key(node):
    md = node.get("metadata", {}) or {}
    return (
        md.get("date", "") or "",
        md.get("decision_num", 0),
    )


def _select_timeline(decision_pairs):
    """permanent(scope=client) 全列 + 非噪音 task 最近 10 条。

    按评审修正：客户项目 task 决策不再因缺少“user:会话决策”或
    “YYYY-MM-DD#第N次”被排除；task 是否进入世界书只由显式噪音分类器决定。
    """
    permanent = []
    task = []
    for node, block in decision_pairs:
        if _is_noise_decision(node, block) or _is_deprecated_or_superseded(node, block):
            continue
        md = node.get("metadata", {}) or {}
        persistence = md.get("persistence", "permanent")
        scope = md.get("scope", "client")
        if persistence == "permanent":
            if scope == "client":
                permanent.append((node, block))
        elif persistence == "task":
            task.append((node, block))
    permanent.sort(key=lambda pair: _decision_sort_key(pair[0]), reverse=True)
    task.sort(key=lambda pair: _decision_sort_key(pair[0]), reverse=True)
    # I-8 丢尾预算：permanent(scope=client) 全列优先，剩余预算给最近 task；
    # 超预算从低优先级丢（先 task，再最旧 permanent）。句子不截半由 _clean_text 保证。
    budget = TIMELINE_MAX_ITEMS
    if len(permanent) >= budget:
        permanent = permanent[:budget]
        task = []
    else:
        task = task[:min(RECENT_TASK_LIMIT, budget - len(permanent))]
    return permanent, task


def _format_timeline_line(node, idx):
    md = node.get("metadata", {}) or {}
    title = _clean_text(node.get("title", ""), 120) or "未命名决策"
    summary = _clean_text(md.get("decision_text") or node.get("summary", ""),
                          TIMELINE_SUMMARY_MAX_CHARS)
    date = md.get("date", "") or node.get("created", "") or ""
    prefix = f"{idx}. [{date}] {title}" if date else f"{idx}. {title}"
    if not summary or summary == title:
        return prefix
    return f"{prefix}：{summary}"


def _build_background(client_name, client_dir, outputs_index):
    """客户背景段：profile 字段缺失时显式标「待补」。"""
    if not isinstance(outputs_index, dict):
        outputs_index = {}
    official = outputs_index.get("client_official_name", "")
    industry = outputs_index.get("industry", "")
    core_need = outputs_index.get("core_requirement", "") or outputs_index.get("core_need", "")
    scope_raw = outputs_index.get("scope", "")
    if isinstance(scope_raw, dict):
        scope_parts = [
            f"{k}={v}" for k, v in (
                ("sheets", scope_raw.get("sheets", "")),
                ("subsystems", scope_raw.get("subsystems", "")),
                ("function_points", scope_raw.get("function_points", "")),
            ) if v
        ]
        scope_text = _clean_text("；".join(scope_parts), 240) if scope_parts else ""
    else:
        scope_text = _clean_text(scope_raw, 160)

    context_path = os.path.join(client_dir, "context.md")
    context_text = ""
    if os.path.exists(context_path):
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                context_text = f.read()
        except Exception:
            context_text = ""
    # 从 context.md 常见格式补公司全称/主营业务（虚构示例集团格式）
    if not official:
        m = re.search(r"\|\s*公司全称\s*\|\s*([^|]+)\|", context_text)
        if m:
            official = m.group(1).strip()
    if not official:
        m = re.search(r"^[-*]\s*客户名称\s*[：:][ \t]*(.+)", context_text, re.MULTILINE)
        if m and not m.group(1).strip().startswith("-"):
            official = m.group(1).strip()
    if not industry:
        m = re.search(r"\|\s*行业\s*\|\s*([^|]+)\|", context_text)
        if m:
            industry = m.group(1).strip()

    pref_path = os.path.join(client_dir, "preferences.md")
    pref_brief = ""
    if os.path.exists(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                pref_text = f.read()
            # 只取第一行正文（跳过 # 标题/空行），避免把整张偏好表塞进背景
            pref_lines = [ln.strip() for ln in pref_text.splitlines()
                          if ln.strip() and not ln.strip().startswith("#")]
            pref_brief = _clean_text(pref_lines[0] if pref_lines else "", 160)
        except Exception:
            pref_brief = ""

    lines = ["## 客户背景"]
    for label, value in [
        ("客户全称", official),
        ("行业", industry),
        ("核心需求", core_need),
        ("规模/范围", scope_text),
        ("偏好摘要", pref_brief),
    ]:
        lines.append(f"- {label}：{_clean_text(value, 240) if value else '待补'}")
    return lines


def _build_output_version_table(outputs_index):
    """产出物版本表：每个系列只列最新版 + 版本数。"""
    if not isinstance(outputs_index, dict):
        outputs_index = {}
    outputs = outputs_index.get("outputs", [])
    if not isinstance(outputs, list):
        outputs = []
    groups = {}
    for out in outputs:
        # 兼容旧格式：outputs 里直接存字符串文件路径
        if isinstance(out, str):
            file_path = out
            version = ""
            status = ""
            date = ""
        elif isinstance(out, dict):
            if out.get("missing"):
                continue  # W1-5：已归档/缺失条目不入世界书版本表
            file_path = out.get("file", "") or ""
            version = out.get("version", "") or ""
            status = out.get("status", "") or ""
            date = out.get("date", "") or ""
        else:
            continue
        if not file_path:
            continue
        title = os.path.basename(file_path) if file_path else out.get("type", "") if isinstance(out, dict) else ""
        normalized = _normalize_output_title(title)
        file_type = os.path.splitext(file_path)[1].lstrip(".").lower()
        if not normalized:
            continue
        key = (normalized, file_type)
        groups.setdefault(key, []).append({
            "version": version,
            "status": status,
            "date": date,
            "type": out.get("type", "") if isinstance(out, dict) else "",
            "file_path": file_path,
        })

    lines = ["## 产出物版本表"]
    if not groups:
        lines.append("- 暂无产出物")
        return lines

    rows = []
    for (normalized, file_type), group in groups.items():
        # 按日期/版本排序，取最新
        group = sorted(group, key=lambda o: (
            o.get("date", "") or "",
            _normalize_version(o.get("version", "")),
        ))
        latest = group[-1]
        rows.append({
            "series": normalized,
            "type": file_type or "?",
            "latest": latest.get("version", "") or "（无版本号）",
            "count": len(group),
            "status": latest.get("status", "") or "待补",
            "date": latest.get("date", "") or "待补",
        })
    rows.sort(key=lambda r: r["date"], reverse=True)
    lines.append("| 系列 | 类型 | 最新版 | 版本数 | 状态 | 日期 |")
    lines.append("|------|------|--------|--------|------|------|")
    for r in rows:
        lines.append(
            f"| {r['series']} | {r['type']} | {r['latest']} | {r['count']} "
            f"| {r['status']} | {r['date']} |"
        )
    return lines


def _normalize_version(version):
    """把 v10/v2 等转成可排序数字；无版本号放最前。"""
    if not version:
        return (0, "")
    m = re.match(r"^v?(\d+(?:\.\d+)*)$", str(version).strip())
    if m:
        return (2, tuple(int(x) for x in m.group(1).split(".")))
    return (1, str(version))


def _build_pending(outputs_index, decision_pairs):
    """待办 / 悬而未决：outputs_index.pending_outputs + 决策待补/待确认/遗留。"""
    items = []
    if isinstance(outputs_index, dict):
        for p in outputs_index.get("pending_outputs", []) or []:
            if isinstance(p, str):
                items.append(p)
            elif isinstance(p, dict):
                type_label = p.get("type", "") or ""
                trigger = p.get("trigger", "") or p.get("value", "") or p.get("status", "")
                if type_label and trigger:
                    items.append(f"{type_label}：{_clean_text(trigger, 160)}")
                elif type_label:
                    items.append(type_label)
                elif trigger:
                    items.append(_clean_text(trigger, 160))

    # 从决策块取待补/待确认/遗留，最多 8 条
    pending_from_decisions = []
    for node, block in decision_pairs:
        if _is_noise_decision(node, block) or _is_deprecated_or_superseded(node, block):
            continue
        md = node.get("metadata", {}) or {}
        for item in md.get("pending_items", []) or []:
            text = _clean_text(item, 160)
            if text:
                pending_from_decisions.append(f"[{node.get('title', '')[:30]}] {text}")
        if len(pending_from_decisions) >= 8:
            break
    pending_from_decisions = pending_from_decisions[:8]
    items.extend(pending_from_decisions)

    lines = ["## 待办 / 悬而未决"]
    if not items:
        lines.append("- 暂无待办")
        return lines
    for item in items:
        lines.append(f"- {item}")
    return lines


def build_worldbook(client_name, client_dir=None, insights_dir=None, output_path=None):
    """直读真源生成 client_index.md 并写盘。

    client_dir 提供时默认写入该目录下的 client_index.md（采样/tmp 安全）；
    也可用 output_path 显式指定目标文件。返回生成的 markdown 文本。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    if client_dir is None:
        client_dir = os.path.join(_paths.CLIENTS_DIR, client_name)
    if not os.path.isdir(client_dir):
        raise FileNotFoundError(f"客户目录不存在: {client_dir}")

    decisions_path = os.path.join(client_dir, "decisions.md")
    oij_path = os.path.join(client_dir, "outputs_index.json")
    if not os.path.exists(decisions_path) and not os.path.exists(oij_path):
        raise FileNotFoundError(f"客户缺少真源 (decisions.md / outputs_index.json): {client_name}")

    outputs_index = _read_json(oij_path) if os.path.exists(oij_path) else {}
    decision_pairs = _parse_decision_nodes(client_dir)

    lines = [f"# {client_name} 世界书", ""]
    lines.extend(_build_background(client_name, client_dir, outputs_index))
    lines.append("")

    permanent, task = _select_timeline(decision_pairs)
    total = len(permanent) + len(task)
    lines.append(
        f"## 决策时间线（共 {total} 条：permanent {len(permanent)} 条全列，"
        f"task 最近 {len(task)} 条）"
    )
    idx = 0
    for node, _ in permanent:
        idx += 1
        lines.append(_format_timeline_line(node, idx))
    for node, _ in task:
        idx += 1
        lines.append(_format_timeline_line(node, idx))
    lines.append("")

    lines.extend(_build_output_version_table(outputs_index))
    lines.append("")

    lines.extend(_build_pending(outputs_index, decision_pairs))

    content = "\n".join(lines).rstrip("\n") + "\n"
    source_hashes = compute_source_hashes(client_dir, insights_dir=insights_dir)
    content = _insert_front_matter(content, source_hashes)

    # 生产调用 build_worldbook(client_name)：写入 _paths.client_index_path。
    # 采样/测试传入 client_dir 时，必须写入该临时目录，避免触碰真实客户数据。
    if output_path is not None:
        index_path = output_path
    elif client_dir is not None:
        index_path = os.path.join(client_dir, "client_index.md")
    else:
        index_path = _paths.client_index_path(client_name)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content
