# -*- coding: utf-8 -*-
"""Embedding 索引构建：扫描所有客户文件 → 批量 embedding → 存 numpy 矩阵。

依赖：_cloud_llm.embed_batch（智谱 embedding-3-pro）
存储：_knowledge/.cache/
  - embeddings_matrix.npy  — (N, dim) float32 矩阵
  - embeddings_index.json — {"paths": [...], "model": str, "dim": int, "meta": {path: {chars, mtime}}}
旧格式 embeddings_cache.pkl 首次运行时自动迁移。

切分策略（v2: 分块升级）：
- context.md 按会话块切 → 再按 ### 切小节（parent-child）
- outputs/*.md 按章节切
- refs/* 按滑动窗口切（chunk_size=800, overlap=200）
"""
import os
import re
import time
import json

import numpy as np

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR, list_client_dirs
CACHE_DIR = os.path.join(SCRIPT_DIR, "_knowledge", ".cache")

# P6/P1-2：决策块锚点方案版本。decisions.md 切片从「含文件头的旧 enumerate」改为
# 三格式 + 跳过废弃/冲突块后，旧索引里的 #d 锚点会错位；升级时若检测到方案版本
# 不一致则强制全量重建，杜绝「旧锚点静默读成别的决策块」。
ANCHOR_SCHEME = "decisions-d-v3"
# 新格式
EMBED_MATRIX_PATH = os.path.join(CACHE_DIR, "embeddings_matrix.npy")
EMBED_INDEX_PATH = os.path.join(CACHE_DIR, "embeddings_index.json")
# 旧格式（迁移用）
EMBED_CACHE_PATH = os.path.join(CACHE_DIR, "embeddings_cache.pkl")


def _migrate_pkl_to_npy():
    """一次性迁移：旧 pkl → 新 npy+json。成功后重命名 pkl 为 .bak。"""
    if not os.path.exists(EMBED_CACHE_PATH) or os.path.exists(EMBED_MATRIX_PATH):
        return
    try:
        from _paths import safe_pickle_load
        cache = safe_pickle_load(EMBED_CACHE_PATH)
        vectors = cache.get("vectors", {})
        if not vectors:
            return
        paths = list(vectors.keys())
        matrix = np.array([vectors[p] for p in paths], dtype=np.float32)
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.save(EMBED_MATRIX_PATH, matrix)
        index = {
            "paths": paths,
            "model": cache.get("model", "unknown"),
            "dim": int(matrix.shape[1]) if matrix.ndim == 2 else 0,
            "meta": cache.get("meta", {}),
            "anchor_scheme": ANCHOR_SCHEME,
        }
        with open(EMBED_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        # 迁移成功，重命名旧文件
        os.replace(EMBED_CACHE_PATH, EMBED_CACHE_PATH + ".bak")
        print(f"[embed] 已迁移 pkl → npy+json（{len(paths)} 个向量）")
    except Exception as e:
        print(f"[embed] 迁移失败（保留旧 pkl）: {e}")


def _client_from_path(path):
    """从路径提取结构化客户名（T4：embedding 索引构建期写入 clients 字段）。"""
    m = re.search(r'[/\\]clients[/\\]([^/\\]+)[/\\]', str(path))
    if m:
        return m.group(1)
    if "docs" in str(path) and "clients" not in str(path):
        return "方法论"
    return ""


def _doc_title_from_path(path):
    """从 path 提取文档标题（T3 元数据注入）。"""
    import os as _os
    base = _os.path.basename(str(path).split("#")[0])
    return _os.path.splitext(base)[0]


def _section_from_text(text):
    """从 chunk 文本提取 section 字段：首个 Markdown 标题文本。"""
    for line in (text or "").splitlines():
        if re.match(r'^#{1,6}\s', line):
            return re.sub(r'^#{1,6}\s+', '', line).strip()
    return ""


def _vector_defect(v, expected_dim=None):
    """坏向量检查：返回缺陷描述文本，好向量返回 None（P3-5 fail-closed）。

    NaN/inf 向量与任何向量的余弦相似度都是 NaN，排序后永远召不回——
    静默丢证据；维度不一致的向量会把整个矩阵写成 ragged/保存时抛错。
    两类坏向量一律拒绝，不给静默入索引的机会。
    """
    if v is None:
        return "None"
    try:
        arr = np.asarray(v, dtype=np.float32)
    except (TypeError, ValueError) as e:
        return f"不可转数组({e})"
    if arr.ndim != 1 or arr.shape[0] == 0:
        return f"形状非法{tuple(arr.shape)}"
    if expected_dim is not None and arr.shape[0] != int(expected_dim):
        return f"维度不一致({arr.shape[0]} != {int(expected_dim)})"
    if not bool(np.all(np.isfinite(arr))):
        return "含 NaN/inf"
    return None


def _save_npy(vectors: dict, meta: dict, model: str):
    """将 vectors dict 写入 npy + json（原子写入）。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    paths = list(vectors.keys())
    if paths:
        matrix = np.array([vectors[p] for p in paths], dtype=np.float32)
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
    # 先写临时文件再 rename，防止中断导致损坏
    # np.save 会自动为不带 .npy 后缀的文件名追加 .npy，故 tmp 路径必须显式带 .npy
    tmp_npy = EMBED_MATRIX_PATH + ".tmp.npy"
    np.save(tmp_npy, matrix)
    os.replace(tmp_npy, EMBED_MATRIX_PATH)
    index = {
        "paths": paths,
        "clients": [_client_from_path(p) for p in paths],
        "doc_titles": [meta.get(p, {}).get("title", "") if isinstance(meta.get(p), dict) else "" for p in paths],
        "sections": [meta.get(p, {}).get("section", "") if isinstance(meta.get(p), dict) else "" for p in paths],
        "doc_dates": [meta.get(p, {}).get("doc_date", "") if isinstance(meta.get(p), dict) else "" for p in paths],
        "model": model,
        "dim": int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] > 0 else 0,
        "meta": meta,
        "anchor_scheme": ANCHOR_SCHEME,  # P1-2：切片方案版本，升级即全量重建
    }
    tmp_json = EMBED_INDEX_PATH + ".tmp"
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    os.replace(tmp_json, EMBED_INDEX_PATH)


def _load_npy():
    """加载 npy+json 索引。返回 (vectors_dict, meta, model) 或 ({}, {}, '')。"""
    if not os.path.exists(EMBED_MATRIX_PATH) or not os.path.exists(EMBED_INDEX_PATH):
        return {}, {}, ""
    try:
        with open(EMBED_INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
        matrix = np.load(EMBED_MATRIX_PATH)
        paths = index.get("paths", [])
        if len(paths) != matrix.shape[0]:
            print("[embed] 警告: paths 与矩阵行数不一致，重建索引")
            return {}, {}, ""
        # P3-5：维度一致性校验（fail-closed）——声明维度与矩阵对不上即拒绝加载
        if matrix.ndim != 2:
            print(f"[embed] 警告: 矩阵维度异常({matrix.shape})，重建索引")
            return {}, {}, ""
        idx_dim = index.get("dim")
        if matrix.shape[0] > 0 and idx_dim and int(idx_dim) != matrix.shape[1]:
            print(f"[embed] 警告: 索引声明维度({idx_dim})与矩阵实际维度({matrix.shape[1]})不一致，重建索引")
            return {}, {}, ""
        # P3-5：NaN/inf 校验（fail-closed）——坏行拒绝并告警，不让它静默
        # 变成永不召回的死向量；剔除后下次构建按 mtime/缺向量自动补齐
        finite_rows = np.isfinite(matrix).all(axis=1) if matrix.size else np.ones(matrix.shape[0], dtype=bool)
        if not bool(finite_rows.all()):
            bad_rows = np.flatnonzero(~finite_rows)
            _bad_show = paths[bad_rows[0]] if len(paths) > bad_rows[0] else f"行{bad_rows[0]}"
            print(f"[embed] 警告: 矩阵含 {len(bad_rows)} 个 NaN/inf 坏向量，已拒绝"
                  f"（如 {_bad_show}），建议重建索引")
            matrix = matrix[finite_rows]
            paths = [p for p, k in zip(paths, finite_rows, strict=False) if k]
        vectors = {p: matrix[i].tolist() for i, p in enumerate(paths)}
        return vectors, index.get("meta", {}), index.get("model", "")
    except Exception as e:
        print(f"[embed] 索引加载失败: {e}")
        return {}, {}, ""


def _load_npy_anchor_scheme():
    """读取索引 json 里的 anchor_scheme（缺失=旧方案 legacy）。失败返回 ''。"""
    try:
        if not os.path.exists(EMBED_INDEX_PATH):
            return ""
        with open(EMBED_INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
        return index.get("anchor_scheme", "")
    except Exception:
        return ""


def _is_noise_chunk(text):
    """判断 chunk 是否为噪声内容（应过滤掉）。

    规则：
    1. 纯页码标记（如 "=== 第 3 页 ==="）
    2. 纯数字/纯符号/纯空白
    3. 极短且无实词（<10 字且无中文实词）
    """
    import re
    stripped = text.strip()
    if not stripped:
        return True

    # 纯页码标记
    if re.match(r'^(={2,}\s*第\s*\d+\s*页\s*={2,}\s*)+$', stripped):
        return True

    # 去掉所有空白和标点后看内容
    cleaned = re.sub(r'[\s\W]', '', stripped)
    if not cleaned:
        return True

    # 极短且无中文实词（<10 字符）
    if len(stripped) < 10:
        cn_chars = re.findall(r'[\u4e00-\u9fff]', stripped)
        if len(cn_chars) < 3:
            return True

    return False


# 分块器版本（T1：v2 起短段落并入相邻块，不再丢 <20 字字段落；
# C-B2：v3 起标题边界感知——标题未并入正文段落前不可单独成块）
CHUNKER_VERSION = "v3"
# 确需丢弃的噪声块审计日志（T1：可审计，不静默丢）
DROPPED_LOG_PATH = os.path.join(CACHE_DIR, "dropped_paragraphs.log")


def _doc_hash(text):
    """计算文档/文本的稳定短哈希，用于分块元数据与丢弃审计。"""
    import hashlib
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _write_dropped_log(source_text, chunk_text):
    """把被噪声过滤丢弃的块追加到 dropped_paragraphs.log（JSONL，可审计）。"""
    try:
        os.makedirs(os.path.dirname(DROPPED_LOG_PATH), exist_ok=True)
        with open(DROPPED_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "doc_hash": _doc_hash(source_text),
                "chunker_version": CHUNKER_VERSION,
                "text": chunk_text[:200],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _is_heading_only_block(text):
    """块是否仅由 Markdown 标题行组成（无正文段落）（C-B2）。

    按 \\n\\n 拆段后每段都是 #{1,6} 标题行才算；空段忽略。
    """
    parts = [p.strip() for p in (text or "").split('\n\n') if p.strip()]
    return bool(parts) and all(re.match(r'^#{1,6}\s', p) for p in parts)


def _sliding_window_chunks_v2(text, chunk_size=500, overlap=200,
                              write_dropped_log=False):
    """滑动窗口分块 v2：短段落并入相邻块，返回带元数据的块 dict 列表。

    每个块含：
      - text: 块文本
      - chunk_id: 块序号（从 0 开始，与路径锚点 p{i}/w{j} 对齐）
      - doc_hash: 源文本短哈希
      - chunker_version: 当前分块器版本
      - prev_block_id: 上一非噪声块 id（首块为 None）

    保留旧行为中的噪声过滤：确需丢弃时若 write_dropped_log=True，
    追加到 dropped_paragraphs.log，而不是静默丢弃。

    C-B2 标题边界感知：标题块在没有并入至少一个正文段落之前不可单独
    成 chunk——flush 时若 current 仅含标题行，则暂存（held_heading），
    待后续正文到达时并为其块首；文档以裸标题收尾时并入上一 chunk；
    全文无正文可并时允许落单（无可并对象）。
    """
    paragraphs = text.split('\n\n')
    raw_chunks = []
    pending_short = []
    current = None
    held_heading = None

    def _flush_current():
        # flush 点统一走这里：标题独占的 current 不落 raw_chunks，
        # 连续标题时与已暂存标题合并为一个标题块继续等待正文。
        nonlocal current, held_heading
        if current is None:
            return
        if _is_heading_only_block(current):
            held_heading = (held_heading + "\n\n" + current
                            if held_heading is not None else current)
        else:
            raw_chunks.append(current)
        current = None

    def _absorb_held_into_current():
        # 正文段落到达：held 非 None 时 current 必为 None 或仅含标题，
        # 把暂存标题并为其块首（保持文档顺序）。
        nonlocal current, held_heading
        if held_heading is None:
            return
        current = (held_heading if current is None
                   else held_heading + "\n\n" + current)
        held_heading = None

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 标题行（# 开头）触发新 chunk：标题保留在 chunk 开头作为主题
        if re.match(r'^#{1,6}\s', para):
            if current is not None and pending_short:
                current += "\n\n" + "\n\n".join(pending_short)
                pending_short = []
            _flush_current()
            current = para
            if pending_short:
                # 无前一块时，短句并入标题块，避免被丢弃
                current = "\n\n".join(pending_short) + "\n\n" + current
                pending_short = []
            continue
        # <20 字字段落不再直接丢弃：先挂起，并入相邻块
        if len(para) < 20:
            pending_short.append(para)
            continue
        if pending_short:
            para = "\n\n".join(pending_short) + "\n\n" + para
            pending_short = []
        # 超大段落单独处理：直接截断为 chunk_size 块
        if len(para) > chunk_size:
            _flush_current()
            for i in range(0, len(para), chunk_size - overlap):
                piece = para[i:i + chunk_size]
                if held_heading is not None:
                    # 标题并入超大段落首切片，避免落单
                    piece = held_heading + "\n\n" + piece
                    held_heading = None
                raw_chunks.append(piece)
            continue
        # 正常段落：累加到 chunk_size
        if current is not None and len(current) + len(para) > chunk_size:
            if _is_heading_only_block(current):
                # 标题 + 本段同块（标题短，合并后略超 chunk_size 可接受），标题不落单
                _absorb_held_into_current()
                current = current + "\n\n" + para
            else:
                raw_chunks.append(current)
                current = current[-overlap:] + "\n\n" + para
        else:
            _absorb_held_into_current()
            current = (current + "\n\n" + para) if current else para

    if pending_short:
        if current is not None:
            current += "\n\n" + "\n\n".join(pending_short)
        else:
            current = "\n\n".join(pending_short)
        pending_short = []
        # 尾部短句使 current 含正文：先吸收暂存标题，防止其滞留落单
        _absorb_held_into_current()
    if current is not None and _is_heading_only_block(current):
        # 文档以裸标题收尾：降级为 held，尝试与上一 chunk 合并
        held_heading = (held_heading + "\n\n" + current
                        if held_heading is not None else current)
        current = None
    if held_heading is not None:
        # 裸标题收尾：并入上一 chunk；全文无正文可并时允许落单
        if raw_chunks:
            raw_chunks[-1] = raw_chunks[-1] + "\n\n" + held_heading
        else:
            raw_chunks.append(held_heading)
        held_heading = None
    if current is not None:
        raw_chunks.append(current)

    chunks = []
    prev_block_id = None
    for raw in raw_chunks:
        if _is_noise_chunk(raw):
            if write_dropped_log:
                _write_dropped_log(text, raw)
            continue
        chunk_id = len(chunks)
        chunks.append({
            "text": raw.strip(),
            "chunk_id": chunk_id,
            "doc_hash": _doc_hash(text),
            "chunker_version": CHUNKER_VERSION,
            "prev_block_id": prev_block_id,
        })
        prev_block_id = chunk_id
    return chunks


def _sliding_window_chunks(text, chunk_size=500, overlap=200,
                           write_dropped_log=False):
    """滑动窗口分块，带重叠。处理超大段落和边界情况（v2 行为）。

    过滤噪声 chunk：纯页码标记、纯符号、极短无实词（确需丢弃时写审计日志）。
    返回兼容的 list[str]；需要块元数据请调用 _sliding_window_chunks_v2。
    """
    return [c["text"]
            for c in _sliding_window_chunks_v2(
                text, chunk_size=chunk_size, overlap=overlap,
                write_dropped_log=write_dropped_log)]


# 已废弃状态行（resolve_conflict 写入后跳过，与 _theme_guard._DEPRECATED_RE 一致）
_DEPRECATED_RE = re.compile(r'[-*]\s*\*{0,2}状态\*{0,2}\s*[：:]\s*已废弃')


def _split_decision_chunks(content):
    """把 decisions.md 切成可检索决策块列表 [(idx, text), ...]（P6-1）。

    统一三格式切分（## 决策 N / ### D-NNN / ## [日期]，复用 _graph 统一解析器）；
    跳过 `conflict: pending` 与 `已废弃` 块（防止把废弃决策当证据召回）。
    idx 为原块序号（跳过文件头后的顺序），切片侧与读取侧（_recall._read_snippet/
    read_chunk 的 #d{i} 锚点）共用同一函数保证索引对齐。
    """
    from _graph import _split_decision_blocks
    blocks = _split_decision_blocks(content or "")
    out = []
    for i, block in enumerate(blocks[1:]):  # 跳过文件头（# 客户 决策记录）
        b = block.strip()
        if not b or len(b) < 20:
            continue
        if "<!-- conflict: pending -->" in b or _DEPRECATED_RE.search(b):
            continue
        out.append((i, b))
    return out


def _decision_block_meta(block_text):
    """提取决策块的 persistence / scope / status 元数据（P6-2，切分前调用，子块继承）。

    缺失默认 permanent / client（与 _theme_guard 向后兼容口径一致）。
    返回 {"persistence": str, "scope": str}。
    """
    pers = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', block_text)
    scope = re.search(r'[-*]\s*\*{0,2}scope\*{0,2}\s*[：:]\s*(\w+)', block_text)
    return {
        "persistence": pers.group(1).strip().lower() if pers else "permanent",
        "scope": scope.group(1).strip().lower() if scope else "client",
    }


def _append_md_chunks(fpath, paths, texts, warnings, label):
    """读取单个 .md，按 ## 切分以 #h{i} 锚点入语料（全局内容，不做客户别名展开）。"""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        for i, chunk in enumerate(re.split(r'(?=\n##\s)', content)):
            chunk = chunk.strip()
            if not chunk or len(chunk) < 20:
                continue
            paths.append(f"{fpath}#h{i}")
            texts.append(chunk)
    except Exception as e:
        warnings.append(f"{label} 解析失败: {e}")


# 三区表（I-3 B3）：analysis/*.md 条目级过滤——仅「确认事实」区 [confirmed] 条目进语料。
# 确认状态机械标记 = 行首 `- [confirmed]` / `- [draft]`（契约见 _knowledge/templates/analysis_template.md）。
_ANALYSIS_ENTRY_RE = re.compile(r'^-\s*\[(confirmed|draft)\]\s*(.+)$')
_ANALYSIS_SECTIONS = ("确认事实", "开放问题", "框架缺口")


def _count_analysis_rows(lines):
    """统计开放问题/框架缺口区条目数（`- ` 行 + 表格数据行，表头/分隔行不计）。"""
    n = 0
    header_skipped = False
    for s in lines:
        if re.match(r'^[-*]\s', s):
            n += 1
        elif s.startswith("|"):
            if set(s) <= set("|-: "):
                continue  # 分隔行
            if not header_skipped:
                header_skipped = True
                continue  # 表头
            n += 1
    return n


def _split_analysis_sections(content):
    """按 ## 小节切分三区表，只收 _ANALYSIS_SECTIONS 三区（值 = strip 后行列表）。

    B4 结构校验（_verify_checks.check_analysis_structure）与语料解析共用，
    保证两侧对「固定小节」的判定逐字节一致。
    """
    sections = {}
    cur = None
    for raw in content.splitlines():
        s = raw.strip()
        m = re.match(r'^##\s+(.+)$', s)
        if m:
            name = m.group(1).strip()
            cur = name if name in _ANALYSIS_SECTIONS else None
            if cur and cur not in sections:
                sections[cur] = []
            continue
        if cur:
            sections[cur].append(s)
    return sections


def _parse_analysis_confirmed(content, warnings, label):
    """解析三区表，返回 confirmed 条目文本列表；格式损坏 -> None（fail-closed，WARN 已打）。

    规则：
    - 缺「## 确认事实」固定小节 -> None（非三区表格式）；
    - 确认事实区内每个条目行（`-`/`*` 开头）必须带 [confirmed]/[draft] 机械标记，
      无标记 = 无法判定确认状态 -> None（宁可整文件不进语料，不可放进未确认内容）；
    - draft 条目与开放问题/框架缺口两区不进语料，排除条数经 warnings 可见
      （I-3「未确认不入召回」——防 AI 假设自我强化污染）。
    """
    sections = _split_analysis_sections(content)
    if "确认事实" not in sections:
        warnings.append(f"语料排除: {label}（格式损坏 fail-closed：缺「确认事实」固定小节）")
        return None
    confirmed = []
    draft_n = 0
    for s in sections["确认事实"]:
        em = _ANALYSIS_ENTRY_RE.match(s)
        if em:
            if em.group(1) == "confirmed":
                confirmed.append(f"- {em.group(2).strip()}")
            else:
                draft_n += 1
        elif re.match(r'^[-*]\s', s):
            warnings.append(f"语料排除: {label}（格式损坏 fail-closed：确认事实区存在无状态标记条目）")
            return None
    if draft_n:
        warnings.append(f"语料排除: {label} 确认事实区 draft 条目 {draft_n} 条（未确认不入召回）")
    for sec in ("开放问题", "框架缺口"):
        n = _count_analysis_rows(sections.get(sec, []))
        if n:
            warnings.append(f"语料排除: {label} {sec}区 {n} 条（未确认不入召回）")
    return confirmed


def scan_corpus_with_warnings():
    """扫描所有客户文件，返回 (corpus, warnings)。

    P1-2 修复：抽取为公共函数，供 scan_corpus / rebuild_bm25_index_all 共用，
    消除 _session.py 与 _embed_index.py 之间 90% 重复的分块逻辑。

    返回:
        corpus: [(path, text), ...]
        warnings: [str, ...] 解析失败的文件清单
    """
    clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if not os.path.isdir(clients_dir):
        return [], []

    paths = []
    texts = []
    warnings = []

    # P3：import 提到循环外，避免每次迭代重复导入
    try:
        from _aliases import load_client, expand_text
    except Exception:
        load_client = None
        expand_text = None
    try:
        from _pipeline import READERS
    except Exception:
        READERS = {}

    # 无客户时 cases/industries 等客户循环外的分支也需要 aliases 有定义（P6-4）
    aliases = None

    # #48/D2：读端客户枚举收口 _paths.list_client_dirs（跳过 _internal/ 内部账本目录）
    for client in list_client_dirs(clients_dir=clients_dir):
        client_dir = os.path.join(clients_dir, client)

        try:
            aliases = load_client(client) if load_client else {}
        except Exception as e:
            aliases = {}
            warnings.append(f"{client}/aliases 加载失败: {e}")

        ctx_path = os.path.join(client_dir, "context.md")
        if os.path.exists(ctx_path):
            try:
                with open(ctx_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 二级分块：先按会话切，再按 ### 切小节
                sessions = re.split(r'(?=## \[\d{4}-\d{2}-\d{2}\])', content)
                for s_idx, session_text in enumerate(sessions):
                    session_text = session_text.strip()
                    if not session_text or len(session_text) < 20:
                        continue
                    # 会话内按 ### 切小节
                    sections = re.split(r'(?=\n###\s)', session_text)
                    # 如果没有 ### 小节，整段作为一个 chunk
                    if len(sections) <= 1:
                        expanded = expand_text(session_text, aliases) if aliases else session_text
                        paths.append(f"{ctx_path}#session{s_idx}")
                        texts.append(expanded)
                    else:
                        for sec_idx, section in enumerate(sections):
                            section = section.strip()
                            if not section or len(section) < 20:
                                continue
                            expanded = expand_text(section, aliases) if aliases else section
                            paths.append(f"{ctx_path}#session{s_idx}#section{sec_idx}")
                            texts.append(expanded)
            except Exception as e:
                warnings.append(f"{client}/context.md 解析失败: {e}")

        # decisions.md 按统一三格式决策条目分块（P6：跳过废弃/冲突块，元数据切分前提取）
        dec_path = os.path.join(client_dir, "decisions.md")
        if os.path.exists(dec_path):
            try:
                with open(dec_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for i, block in _split_decision_chunks(content):
                    # P6-2：persistence/scope 在切分前提取，滑动窗口子块继承
                    meta = _decision_block_meta(block)
                    meta_prefix = f"[{meta['persistence']}·{meta['scope']}] "
                    # 超长块（如旧格式多个决策并成一块）用滑动窗口二次切分
                    sub_blocks = []
                    if len(block) > 2000:
                        sub_blocks = _sliding_window_chunks(block, chunk_size=1800, overlap=200,
                                                            write_dropped_log=True)
                    else:
                        sub_blocks = [block]
                    for j, sub in enumerate(sub_blocks):
                        sub = sub.strip()
                        if not sub or len(sub) < 20:
                            continue
                        expanded = expand_text(meta_prefix + sub, aliases) if aliases else (meta_prefix + sub)
                        paths.append(f"{dec_path}#d{i}#w{j}" if len(sub_blocks) > 1 else f"{dec_path}#d{i}")
                        texts.append(expanded)
            except Exception as e:
                warnings.append(f"{client}/decisions.md 解析失败: {e}")

        # preferences.md 全文入索引（客户偏好，高价值检索目标）
        pref_path = os.path.join(client_dir, "preferences.md")
        if os.path.exists(pref_path):
            try:
                with open(pref_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if len(content) >= 20:
                    expanded = expand_text(content, aliases) if aliases else content
                    paths.append(f"{pref_path}#full")
                    texts.append(expanded)
            except Exception as e:
                warnings.append(f"{client}/preferences.md 解析失败: {e}")

        # keynote.md 基调卡（I-3 A7：人批准的 permanent 资产，不受未确认排除约束）
        kn_path = os.path.join(client_dir, "keynote.md")
        if os.path.exists(kn_path):
            try:
                with open(kn_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if len(content) >= 20:
                    expanded = expand_text(content, aliases) if aliases else content
                    paths.append(f"{kn_path}#full")
                    texts.append(expanded)
            except Exception as e:
                warnings.append(f"{client}/keynote.md 解析失败: {e}")

        # analysis/ 三区表（I-3 B3）：仅确认事实区 [confirmed] 条目进语料，
        # draft/开放问题/框架缺口不进——「未确认不入召回」；读取/解析失败 fail-closed
        analysis_dir = os.path.join(client_dir, "analysis")
        if os.path.isdir(analysis_dir):
            for fname in sorted(os.listdir(analysis_dir)):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(analysis_dir, fname)
                label = f"{client}/analysis/{fname}"
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    warnings.append(f"语料排除: {label}（读取失败 fail-closed: {e}）")
                    continue
                entries = _parse_analysis_confirmed(content, warnings, label)
                if not entries:
                    continue  # None=fail-closed；[]=无 confirmed 条目
                text = "## 确认事实（confirmed 条目，已过销售复核）\n" + "\n".join(entries)
                expanded = expand_text(text, aliases) if aliases else text
                paths.append(f"{fpath}#confirmed")
                texts.append(expanded)

        outputs_dir = os.path.join(client_dir, "outputs")
        if os.path.isdir(outputs_dir):
            for fname in os.listdir(outputs_dir):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(outputs_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    chunks = re.split(r'(?=\n##\s)', content)
                    for i, chunk in enumerate(chunks):
                        chunk = chunk.strip()
                        if not chunk or len(chunk) < 20:
                            continue
                        expanded = expand_text(chunk, aliases) if aliases else chunk
                        paths.append(f"{fpath}#h{i}")
                        texts.append(expanded)
                except Exception as e:
                    warnings.append(f"{fname} 解析失败: {e}")

        refs_dir = os.path.join(client_dir, "refs")
        if os.path.isdir(refs_dir):
            # 递归扫描 refs 子目录（如 _txt/ 语义切片产物），只索引文本文件；
            # 跳过图片子目录（页级切片，索引价值低且触发 vision API）。
            # diffs 子目录由下方单独分支处理，此处跳过避免重复索引。
            _text_exts = {".txt", ".md", ".docx", ".pdf", ".pptx", ".xlsx"}
            for root, dirs, files in os.walk(refs_dir):
                dirs[:] = [d for d in dirs if d != "diffs"]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in _text_exts:
                        continue
                    reader = READERS.get(ext)
                    if not reader:
                        continue
                    try:
                        # xlsx 走结构化按行分块，保留报价单的行完整性
                        if ext == ".xlsx":
                            from _pipeline import read_xlsx_structured
                            row_chunks = read_xlsx_structured(fpath)
                            for chunk_text, anchor in row_chunks:
                                expanded = expand_text(chunk_text, aliases) if aliases else chunk_text
                                paths.append(f"{fpath}#{anchor}")
                                texts.append(expanded)
                            continue
                        text = reader(fpath)
                    except Exception as e:
                        warnings.append(f"{client}/refs/{fname} 读取失败: {e}")
                        continue
                    # v3: 滑动窗口分块带 overlap，chunk_size=800 适配咨询长文档段落
                    chunks = _sliding_window_chunks(text, chunk_size=800, overlap=200,
                                                    write_dropped_log=True)
                    for i, chunk in enumerate(chunks):
                        expanded = expand_text(chunk, aliases) if aliases else chunk
                        paths.append(f"{fpath}#p{i}")
                        texts.append(expanded)

        # diff 记录（refs/diffs/*.txt）-- spec 5.1.3：纳入索引供 recall 搜索
        diffs_dir = os.path.join(client_dir, "refs", "diffs")
        if os.path.isdir(diffs_dir):
            for fname in os.listdir(diffs_dir):
                if not fname.endswith(".txt"):
                    continue
                fpath = os.path.join(diffs_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if len(content) < 20:
                        continue
                    expanded = expand_text(content, aliases) if aliases else content
                    paths.append(f"{fpath}#d0")
                    texts.append(expanded)
                except Exception as e:
                    warnings.append(f"{client}/refs/diffs/{fname} 读取失败: {e}")

        # client_index.md（世界书索引）-- spec 破坏点 1：纳入索引供 recall 搜索
        ci_path = os.path.join(client_dir, "client_index.md")
        if os.path.exists(ci_path):
            try:
                with open(ci_path, "r", encoding="utf-8") as f:
                    content = f.read()
                chunks = re.split(r'(?=\n##\s)', content)
                for i, chunk in enumerate(chunks):
                    chunk = chunk.strip()
                    if not chunk or len(chunk) < 20:
                        continue
                    expanded = expand_text(chunk, aliases) if aliases else chunk
                    paths.append(f"{ci_path}#h{i}")
                    texts.append(expanded)
            except Exception as e:
                warnings.append(f"{client}/client_index.md 解析失败: {e}")

    # docs 方法论白名单（D-121：AI 生成前自动召回项目自己的方法论——
    # 表达设计/构图母板/spec 协议/图视觉规范/十大实践；不扫 CHANGELOG 等
    # 过程文档，避免稀释客户证据召回）
    # P6-3：白名单配置化（本常量是唯一配置源），并匹配「docs 根 + docs/archive
    # 双路径」——已归档的方法论文档不静默失效（如视觉规范 v3.0 已移入 archive）。
    METHOD_DOCS = (
        "build_journey.md",
        "表达设计方法论与PPT母版调研_2026-08-12.md",
        "spec_protocol_v1.md",
        "diagram_visual_design_v1_2026-07-19.md",
        "dev_plan_visual_v3_2026-08-11.md",
        "视觉规范v3.0_讨论与实施记录_2026-08-11.md",
    )
    docs_dir = os.path.join(SCRIPT_DIR, "docs")
    docs_archive_dir = os.path.join(docs_dir, "archive")
    # D-122：叙事/4A skill 方法论一并进索引（专家化——生成前召回
    # 十二种构图母板与 4A 及格线）
    METHOD_SKILL_FILES = (
        os.path.join(SCRIPT_DIR, ".folio", "skills",
                     "presentation-content-design", "SKILL.md"),
        *(
            os.path.join(SCRIPT_DIR, ".folio", "skills",
                         "presentation-content-design", "references", fn)
            for fn in ("containers.md", "components.md", "composition.md",
                       "template-families.md", "quality-gate.md", "styles.md")
        ),
        os.path.join(SCRIPT_DIR, ".folio", "skills",
                     "architecture-diagram-builder", "SKILL.md"),
    )
    all_method_files = []
    for dn in METHOD_DOCS:
        for base in (docs_dir, docs_archive_dir):
            p = os.path.join(base, dn)
            if os.path.exists(p):
                all_method_files.append(p)
                break
    all_method_files += [sf for sf in METHOD_SKILL_FILES
                         if os.path.exists(sf)]
    for dpath in all_method_files:
        if not os.path.exists(dpath):
            continue
        try:
            with open(dpath, "r", encoding="utf-8") as f:
                content = f.read()
            chunks = re.split(r'(?=\n##\s)', content)
            for i, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk or len(chunk) < 40:
                    continue
                # 滑窗分块（与 refs 一致）：单章可能超 embedding token 上限，
                # 整章直送会触发 API 400（D-121 实测：25767 字符块整批失败）
                win = _sliding_window_chunks(chunk, chunk_size=800, overlap=200,
                                             write_dropped_log=True)
                for wi, wtext in enumerate(win):
                    paths.append(f"{dpath}#h{i}#w{wi}")
                    texts.append(wtext)
        except Exception as e:
            warnings.append(f"方法论文档 {os.path.basename(dpath)} 解析失败: {e}")

    # 行业知识库（_knowledge/industries/）
    industries_dir = os.path.join(SCRIPT_DIR, "_knowledge", "industries")
    if os.path.isdir(industries_dir):
        for fname in os.listdir(industries_dir):
            if fname.endswith(".md"):
                _append_md_chunks(os.path.join(industries_dir, fname), paths, texts,
                                  warnings, f"industries/{fname}")

    # 域卡（_knowledge/domains/）与方法论（_knowledge/methodology/）——
    # I-3 A7 语料断点修复：专家资产对检索层可见。
    # 排除：domains 下 *_草稿.md 过程稿；methodology 下 ppt-refs/（外部 PPT
    # 提取件，非正式方法件）与 _ 开头目录（模板/提取缓存）。排除经 warnings 可见。
    domains_dir = os.path.join(SCRIPT_DIR, "_knowledge", "domains")
    if os.path.isdir(domains_dir):
        for fname in os.listdir(domains_dir):
            if not fname.endswith(".md"):
                continue
            if fname.endswith("_草稿.md"):
                warnings.append(f"语料排除: domains/{fname}（过程稿）")
                continue
            _append_md_chunks(os.path.join(domains_dir, fname), paths, texts,
                              warnings, f"domains/{fname}")
    meth_dir = os.path.join(SCRIPT_DIR, "_knowledge", "methodology")
    if os.path.isdir(meth_dir):
        for root, dirs, files in os.walk(meth_dir):
            for d in list(dirs):
                if d.startswith("_") or d == "ppt-refs":
                    warnings.append(f"语料排除: methodology/{d}/（外部提取件/模板目录）")
                    dirs.remove(d)
            for fname in files:
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, meth_dir).replace(os.sep, "/")
                    _append_md_chunks(fpath, paths, texts, warnings, f"methodology/{rel}")

    # 案例卡（_knowledge/cases/）——P6-4：加入索引（.md，锚点 #h{i}）
    # P2-9：cases 属全局内容，不做客户别名展开（避免被上个客户映射污染）
    cases_dir = os.path.join(SCRIPT_DIR, "_knowledge", "cases")
    if os.path.isdir(cases_dir):
        for fname in os.listdir(cases_dir):
            if fname.endswith(".md"):
                _append_md_chunks(os.path.join(cases_dir, fname), paths, texts,
                                  warnings, f"cases/{fname}")

    return list(zip(paths, texts, strict=False)), warnings


def scan_corpus():
    """扫描所有客户文件，返回 [(path, text), ...]。

    P1-2：薄封装 scan_corpus_with_warnings，丢弃 warnings（向后兼容）。
    需要 warnings 的调用方请直接用 scan_corpus_with_warnings()。
    """
    corpus, _ = scan_corpus_with_warnings()
    return corpus


def build_embedding_index(batch_size=50, force=False):
    """构建 embedding 索引。增量更新：只 embedding 新增或修改过的文档。

    P0-9：用 path+mtime 判断是否需要重新 embedding（对齐 _pipeline 的缓存策略）。
    断点续传：每批完成后立即保存 npy+json，中断后下次重跑从未处理位置继续。
    """
    from _cloud_llm import embed_batch

    os.makedirs(CACHE_DIR, exist_ok=True)

    # 旧格式自动迁移
    _migrate_pkl_to_npy()

    existing_vectors, existing_meta, old_model = {}, {}, ""
    if not force:
        existing_vectors, existing_meta, old_model = _load_npy()
        # provider 切换后旧向量与新模型空间不兼容，必须全量重建（不能增量复用）
        from _cloud_llm import current_embed_provider
        _cur = current_embed_provider()
        if _cur and old_model and old_model != _cur[1]:
            print(f"[embed] provider 已切换（{old_model} -> {_cur[1]}），向量空间不兼容，全量重建")
            existing_vectors, existing_meta = {}, {}
        # P1-2：决策块锚点方案版本不一致（切片改过），旧 #d 锚点已错位——全量重建
        if existing_vectors and _load_npy_anchor_scheme() != ANCHOR_SCHEME:
            print(f"[embed] 切片锚点方案已升级（{_load_npy_anchor_scheme() or 'legacy'} -> {ANCHOR_SCHEME}），"
                  f"旧 #d 锚点错位风险，全量重建索引")
            existing_vectors, existing_meta = {}, {}

    corpus = scan_corpus()
    if not corpus:
        print("[embed] 无可索引内容")
        return

    print(f"[embed] 扫描到 {len(corpus)} 个文档块")

    # P0-9：用 path+mtime 判断是否需要重新 embedding
    # meta[path] 存 {"chars": N, "mtime": M}，文件修改后 mtime 变化 → 重新 embed
    def _get_mtime(path_key):
        """从锚点路径提取实际文件路径并取 mtime。"""
        fpath = path_key.split("#")[0]
        try:
            return os.path.getmtime(fpath)
        except (OSError, ValueError):
            return 0

    to_embed = []
    for p, t in corpus:
        cur_mtime = _get_mtime(p)
        old_meta = existing_meta.get(p, {})
        old_mtime = old_meta.get("mtime", 0) if isinstance(old_meta, dict) else 0
        if p not in existing_vectors or cur_mtime != old_mtime:
            to_embed.append((p, t, cur_mtime))

    if not to_embed:
        print(f"[embed] 所有文档已索引且未变更（{len(existing_vectors)} 个），无需更新")
        return {"vectors": existing_vectors, "meta": existing_meta,
                "model": old_model, "dim": len(next(iter(existing_vectors.values()))) if existing_vectors else 0}

    print(f"[embed] 需 embedding {len(to_embed)} 个文档（已有 {len(existing_vectors)} 个）")

    vectors = dict(existing_vectors)
    meta = dict(existing_meta)

    total_batches = (len(to_embed) + batch_size - 1) // batch_size
    from _cloud_llm import current_embed_provider
    _provider = current_embed_provider()
    _model_name = _provider[1] if _provider else "unknown"

    # P3-5：维度基准——增量时取已有合格向量的维度，全新构建由首个合格向量定义
    _ref_dim = None
    for _v in vectors.values():
        if _vector_defect(_v) is None:
            _ref_dim = len(np.asarray(_v, dtype=np.float32))
            break

    def _save_cache():
        """每批后立即保存 npy+json（断点续传）。"""
        _save_npy(vectors, meta, _model_name)

    for bi in range(total_batches):
        batch = to_embed[bi * batch_size: (bi + 1) * batch_size]
        batch_paths = [p for p, _, _ in batch]
        batch_texts = [t for _, t, _ in batch]
        batch_mtimes = [m for _, _, m in batch]

        print(f"  批次 {bi+1}/{total_batches} ({len(batch)} 个文档)...")
        try:
            vecs = embed_batch(batch_texts)
            if not vecs or len(vecs) != len(batch):
                print(f"    → 失败：返回 {0 if not vecs else len(vecs)} 个向量，预期 {len(batch)}")
                continue
            accepted = 0
            for p, v, t, m in zip(batch_paths, vecs, batch_texts, batch_mtimes, strict=False):
                # P3-5：坏向量 fail-closed 拒绝——维度不一致/NaN/inf 不入索引，
                # 只拒绝本条，不中断整批（保留旧向量，下次构建按 mtime 重试）
                defect = _vector_defect(v, expected_dim=_ref_dim)
                if defect:
                    print(f"    → 拒绝坏向量 {p}: {defect}")
                    continue
                if _ref_dim is None:
                    _ref_dim = len(np.asarray(v, dtype=np.float32))
                vectors[p] = v
                meta[p] = {
                    "chars": len(t),
                    "mtime": m,
                    "title": _doc_title_from_path(p),
                    "section": _section_from_text(t),
                    "doc_date": "",
                }
                accepted += 1
            print(f"    → OK（{accepted}/{len(batch)} 入索引）" if accepted != len(batch) else "    → OK")
        except Exception as e:
            print(f"    -> 失败: {e}")

        # 断点续传：每批完成后立即保存，中断后下次重跑从未处理位置继续
        _save_cache()

        if bi < total_batches - 1:
            time.sleep(0.5)

    # 过期向量清理：不在当前 corpus 中的 path 全部删除
    current_paths = set(p for p, _ in corpus)
    stale = [p for p in vectors if p not in current_paths]
    for p in stale:
        del vectors[p]
        if p in meta:
            del meta[p]
    if stale:
        print(f"[embed] 清理 {len(stale)} 个过期向量")

    _save_cache()

    cache_dim = len(next(iter(vectors.values()))) if vectors else 0
    print(f"\n[embed] 索引已保存: {EMBED_MATRIX_PATH}")
    print(f"  总向量数: {len(vectors)}")
    print(f"  维度: {cache_dim}")
    return {"vectors": vectors, "meta": meta, "model": _model_name, "dim": cache_dim}


def get_stats():
    """返回索引统计信息。"""
    # 新格式优先
    if os.path.exists(EMBED_INDEX_PATH):
        try:
            with open(EMBED_INDEX_PATH, "r", encoding="utf-8") as f:
                index = json.load(f)
            return {
                "exists": True,
                "count": len(index.get("paths", [])),
                "dim": index.get("dim", 0),
                "model": index.get("model", ""),
            }
        except Exception as e:
            return {"exists": False, "count": 0, "dim": 0, "error": str(e)}
    # 旧格式兼容（未迁移）
    if os.path.exists(EMBED_CACHE_PATH):
        try:
            from _paths import safe_pickle_load
            cache = safe_pickle_load(EMBED_CACHE_PATH)
            return {
                "exists": True,
                "count": len(cache.get("vectors", {})),
                "dim": cache.get("dim", 0),
                "model": cache.get("model", ""),
            }
        except Exception as e:
            return {"exists": False, "count": 0, "dim": 0, "error": str(e)}
    return {"exists": False, "count": 0, "dim": 0}


def inspect_chunks(file_path):
    """检查某文件的分块结果，返回每个 chunk 的路径、字符数、预览。"""
    corpus = scan_corpus()
    results = []
    norm_path = file_path.replace("/", os.sep).replace("\\", os.sep)
    for path, text in corpus:
        if norm_path in path:
            preview = text[:120].replace('\n', ' ').replace('\r', '')
            results.append({
                "path": path,
                "chars": len(text),
                "preview": preview,
            })
    return results


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    build_embedding_index(force=force)
