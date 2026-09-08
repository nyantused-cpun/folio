# -*- coding: utf-8 -*-
"""BM25 检索：rank_bm25 封装。
中文分词：jieba 为主，单字补充未登录词。"""
import os
import re

import jieba

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR
CACHE_DIR = os.path.join(SCRIPT_DIR, "_knowledge", ".cache")
BM25_INDEX_PATH = os.path.join(CACHE_DIR, "bm25_index.pkl")

# P2：内存缓存，避免每次查询都从磁盘 load pkl
_INDEX_CACHE = None

# 领域词典：咨询/汇报常见术语，jieba 默认词典可能切不开
_DOMAIN_TERMS = [
    "数据架构", "应用架构", "技术架构", "业务架构", "信息安全",
    "协同办公", "客户关系", "供应链", "数字化", "智能化",
    "私有化部署", "微服务", "中台", "低代码", "流程引擎",
    "权限管理", "单点登录", "数据隔离", "并发", "可用性",
    "灾备", "容灾", "运维", "监控", "审计",
    "招投标", "需求分析", "能力矩阵", "架构设计",
]
for _term in _DOMAIN_TERMS:
    jieba.add_word(_term)


def _client_from_path(path):
    """从路径提取结构化客户名（T4：BM25 索引构建期写入 clients 字段）。

    优先精确匹配 `clients/{客户}/` 目录；docs 方法论归「方法论」；
    其余非客户路径返回空串（查询带客户过滤时不会命中）。
    """
    m = re.search(r'[/\\]clients[/\\]([^/\\]+)[/\\]', str(path))
    if m:
        return m.group(1)
    if "docs" in str(path) and "clients" not in str(path):
        return "方法论"
    return ""


def _doc_title_from_path(path):
    """从 path 提取文档标题（T3：BM25 多字段 title 字段）。"""
    base = os.path.basename(str(path).split("#")[0])
    return os.path.splitext(base)[0]


def _section_from_text(text):
    """从 chunk 文本提取 section 字段：首个 Markdown 标题文本。"""
    for line in (text or "").splitlines():
        if re.match(r'^#{1,6}\s', line):
            return re.sub(r'^#{1,6}\s+', '', line).strip()
    return ""


def _build_bm25_or_none(tokenized, k1, b):
    """构造 BM25Okapi；字段全为空时返回 None（rank_bm25 空语料会除零）。"""
    if not any(t for t in tokenized):
        return None
    from rank_bm25 import BM25Okapi
    return BM25Okapi(tokenized, k1=k1, b=b)


def _tokenize(text):
    """jieba 分词为主，保留英文词和数字。单字中文补充（兜底未登录词）。

    策略：
    1. jieba.cut 切中文词组（保留语义）
    2. 英文按词切（[a-zA-Z]+）——只补 jieba 未覆盖的（差集，防双计）
    3. 数字串保留（\\d+）——只补 jieba 未覆盖的（差集，防双计）
    4. 单字中文保留（兜底未登录词，如人名/缩写）
    """
    if not text:
        return []

    tokens = []

    # jieba 分词（中文词组）
    jieba_tokens = [t.strip() for t in jieba.cut(text, cut_all=False)
                    if t.strip() and t.strip() not in (" ", "\n", "\r", "\t")]
    tokens.extend(jieba_tokens)

    # C-B1：jieba 对连续英文/数字通常已产出相同 token，
    # 正则结果只补差集（jieba 切碎或未覆盖的），避免英文/数字双计虚高权重。
    jieba_norm = {t.lower() for t in jieba_tokens}

    en_words = re.findall(r'[a-zA-Z]+', text)
    tokens.extend(w for w in en_words if w.lower() not in jieba_norm)

    numbers = re.findall(r'\d+', text)
    tokens.extend(n for n in numbers if n not in jieba_norm)

    # 单字中文兜底（jieba 未切出的生僻字/人名）
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    # 只补单字（已在 jieba 词组中的单字不重复加）
    jieba_set = set(t for t in tokens if len(t) == 1)
    for ch in cn_chars:
        if ch not in jieba_set:
            tokens.append(ch)

    return tokens


def build_bm25_index(corpus_paths, corpus_texts, k1=1.5, b=0.75):
    """构建 BM25 索引（T3：多字段 title/section/text 加权）。k1/b 可从 recall_config.yml 传入。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    tokenized = [_tokenize(t) for t in corpus_texts]
    titles = [_tokenize(_doc_title_from_path(p)) for p in corpus_paths]
    sections = [_tokenize(_section_from_text(t)) for t in corpus_texts]
    bm25_text = _build_bm25_or_none(tokenized, k1=k1, b=b)
    bm25_title = _build_bm25_or_none(titles, k1=1.2, b=0.5)
    bm25_section = _build_bm25_or_none(sections, k1=1.5, b=0.75)

    from _paths import safe_pickle_dump
    # P3-6：原子写——先写 tmp 再 os.replace，中断不会用半截 pkl 顶掉旧索引。
    # safe_pickle_dump 的 HMAC 签名只覆盖 payload 与路径无关，换名写入不影响校验
    # （照 _embed_index._save_npy 的 tmp+replace 范式）。
    payload = {
        "paths": corpus_paths,
        "clients": [_client_from_path(p) for p in corpus_paths],
        "bm25": bm25_text,        # 旧字段兼容
        "bm25_title": bm25_title,
        "bm25_section": bm25_section,
        "bm25_text": bm25_text,
    }
    tmp_path = BM25_INDEX_PATH + ".tmp"
    safe_pickle_dump(payload, tmp_path)
    os.replace(tmp_path, BM25_INDEX_PATH)

    # P2：重建后清除内存缓存，下次查询重新加载
    global _INDEX_CACHE
    _INDEX_CACHE = None

    print(f"[BM25] 索引已保存: {BM25_INDEX_PATH} ({len(corpus_paths)} 文档)")
    return bm25_text


def query_bm25(query_text, top_k=20, client_filter=None):
    """BM25 查询。返回 [(path, score), ...] 或 None（索引不存在）。

    client_filter: 指定客户名时，只搜索该客户的文档（在 top_k 选取前过滤）。
    """
    global _INDEX_CACHE

    if _INDEX_CACHE is None:
        if not os.path.exists(BM25_INDEX_PATH):
            return None
        from _paths import safe_pickle_load
        try:
            _INDEX_CACHE = safe_pickle_load(BM25_INDEX_PATH)
        except Exception as e:
            # 索引损坏（截断/篡改/签名不匹配）不炸 recall，降级让调用方走关键词模式
            print(f"[降级] BM25 索引加载失败（{type(e).__name__}: {e}），退回关键词模式。"
                  f"运行 python _cli.py index 重建")
            return None
        if _INDEX_CACHE is None:
            # P1-1 fail-closed：无签名/签名不匹配被拒绝加载，同样降级不炸 recall
            print("[降级] BM25 索引无有效 HMAC 签名，已拒绝加载，退回关键词模式。"
                  "运行 python _cli.py index 重建")
            return None
    paths = _INDEX_CACHE["paths"]
    bm25 = _INDEX_CACHE["bm25"]

    tokens = _tokenize(query_text)
    if not tokens:
        return []

    # T3：多字段 BM25 加权；字段为空/旧索引时回退单文本字段
    bm25_title = _INDEX_CACHE.get("bm25_title")
    bm25_section = _INDEX_CACHE.get("bm25_section")
    bm25_text = _INDEX_CACHE.get("bm25_text")
    if bm25_text is not None:
        scores = [0.0] * len(paths)
        if bm25_title is not None:
            _title_scores = bm25_title.get_scores(tokens)
            scores = [s + 2.0 * x for s, x in zip(scores, _title_scores, strict=False)]
        if bm25_section is not None:
            _section_scores = bm25_section.get_scores(tokens)
            scores = [s + 1.5 * x for s, x in zip(scores, _section_scores, strict=False)]
        _text_scores = bm25_text.get_scores(tokens)
        scores = [s + 1.0 * x for s, x in zip(scores, _text_scores, strict=False)]
    else:
        scores = bm25.get_scores(tokens)

    # 按客户过滤：优先用索引构建期写入的结构化 clients 字段，
    # 旧索引缺失时回退到精确匹配 clients/{客户名}/ 目录，避免子串误匹配。
    if client_filter:
        stored_clients = _INDEX_CACHE.get("clients") if isinstance(_INDEX_CACHE, dict) else None
        if stored_clients and len(stored_clients) == len(paths):
            candidate_indices = [i for i, c in enumerate(stored_clients) if c == client_filter]
        else:
            _client_pat = re.compile(rf'[/\\]clients[/\\]{re.escape(client_filter)}[/\\]')
            candidate_indices = [i for i, p in enumerate(paths) if _client_pat.search(p)]
    else:
        candidate_indices = range(len(scores))

    top_indices = sorted(candidate_indices, key=lambda i: scores[i], reverse=True)[:top_k]

    results = []
    for idx in top_indices:
        if scores[idx] <= 0:
            continue
        results.append((paths[idx], float(scores[idx])))
    return results


if __name__ == "__main__":
    paths = ["doc1", "doc2"]
    texts = ["蓝海多工厂排产问题", "蓝海集团CRM风险管理"]
    build_bm25_index(paths, texts)
    r = query_bm25("排产", top_k=2)
    print("BM25 query result:", r)
