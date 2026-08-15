# -*- coding: utf-8 -*-
"""Embedding 索引构建：扫描所有客户文件 → 批量 embedding → 存 numpy 矩阵。

依赖：_cloud_llm.embed_batch（智谱 embedding-3）
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "_knowledge", ".cache")
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
        }
        with open(EMBED_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        # 迁移成功，重命名旧文件
        os.replace(EMBED_CACHE_PATH, EMBED_CACHE_PATH + ".bak")
        print(f"[embed] 已迁移 pkl → npy+json（{len(paths)} 个向量）")
    except Exception as e:
        print(f"[embed] 迁移失败（保留旧 pkl）: {e}")


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
        "model": model,
        "dim": int(matrix.shape[1]) if matrix.ndim == 2 and matrix.shape[0] > 0 else 0,
        "meta": meta,
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
        vectors = {p: matrix[i].tolist() for i, p in enumerate(paths)}
        return vectors, index.get("meta", {}), index.get("model", "")
    except Exception as e:
        print(f"[embed] 索引加载失败: {e}")
        return {}, {}, ""


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


def _sliding_window_chunks(text, chunk_size=500, overlap=200):
    """滑动窗口分块，带重叠。处理超大段落和边界情况。

    过滤噪声 chunk：纯页码标记、纯符号、极短无实词。
    """
    paragraphs = text.split('\n\n')
    result = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 标题行（# 开头）触发新 chunk：标题保留在 chunk 开头作为主题，
        # 避免被下方 len(para)<20 的极短过滤当成噪声丢弃（表格碎片因此失去归属）
        if re.match(r'^#{1,6}\s', para):
            if current and not _is_noise_chunk(current):
                result.append(current.strip())
            current = para
            continue
        if len(para) < 20:
            continue
        # 超大段落单独处理：直接截断为 chunk_size 块
        if len(para) > chunk_size:
            if current:
                if not _is_noise_chunk(current):
                    result.append(current.strip())
                current = ""
            for i in range(0, len(para), chunk_size - overlap):
                chunk = para[i:i + chunk_size]
                if not _is_noise_chunk(chunk):
                    result.append(chunk)
            continue
        # 正常段落：累加到 chunk_size
        if len(current) + len(para) > chunk_size and current:
            if not _is_noise_chunk(current):
                result.append(current.strip())
            current = current[-overlap:] + "\n\n" + para
        else:
            current += ("\n\n" + para) if current else para
    if current.strip():
        if not _is_noise_chunk(current):
            result.append(current.strip())
    return result


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

    for client in os.listdir(clients_dir):
        client_dir = os.path.join(clients_dir, client)
        if not os.path.isdir(client_dir) or client.startswith("_"):
            continue

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
                    chunks = _sliding_window_chunks(text, chunk_size=800, overlap=200)
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
    METHOD_DOCS = (
        "build_journey.md",
        "表达设计方法论与PPT母版调研_2026-08-12.md",
        "spec_protocol_v1.md",
        "diagram_visual_design_v1_2026-07-19.md",
        "dev_plan_visual_v3_2026-08-11.md",
        "视觉规范v3.0_讨论与实施记录_2026-08-11.md",
    )
    docs_dir = os.path.join(SCRIPT_DIR, "docs")
    # D-122：叙事/4A skill 方法论一并进索引（专家化——生成前召回
    # 十二种构图母板与 4A 及格线）
    METHOD_SKILL_FILES = (
        os.path.join(SCRIPT_DIR, ".trae", "skills",
                     "presentation-content-design", "SKILL.md"),
        os.path.join(SCRIPT_DIR, ".trae", "skills",
                     "presentation-content-design", "reference.md"),
        os.path.join(SCRIPT_DIR, ".trae", "skills",
                     "architecture-diagram-builder", "SKILL.md"),
    )
    all_method_files = [os.path.join(docs_dir, dn) for dn in METHOD_DOCS]
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
                win = _sliding_window_chunks(chunk, chunk_size=800, overlap=200)
                for wi, wtext in enumerate(win):
                    paths.append(f"{dpath}#h{i}#w{wi}")
                    texts.append(wtext)
        except Exception as e:
            warnings.append(f"方法论文档 {os.path.basename(dpath)} 解析失败: {e}")

    # 行业知识库（_knowledge/industries/）
    industries_dir = os.path.join(SCRIPT_DIR, "_knowledge", "industries")
    if os.path.isdir(industries_dir):
        for fname in os.listdir(industries_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(industries_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                chunks = re.split(r'(?=\n##\s)', content)
                for i, chunk in enumerate(chunks):
                    chunk = chunk.strip()
                    if not chunk or len(chunk) < 20:
                        continue
                    paths.append(f"{fpath}#h{i}")
                    texts.append(chunk)
            except Exception as e:
                warnings.append(f"industries/{fname} 解析失败: {e}")

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
            for p, v, t, m in zip(batch_paths, vecs, batch_texts, batch_mtimes, strict=False):
                vectors[p] = v
                meta[p] = {"chars": len(t), "mtime": m}
            print("    → OK")
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
