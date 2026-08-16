# -*- coding: utf-8 -*-
"""BM25 检索：rank_bm25 封装。
中文分词：jieba 为主，单字补充未登录词。"""
import os
import re

import jieba

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
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


def _tokenize(text):
    """jieba 分词为主，保留英文词和数字。单字中文补充（兜底未登录词）。

    策略：
    1. jieba.cut 切中文词组（保留语义）
    2. 英文按词切（[a-zA-Z]+）
    3. 数字串保留（\d+）
    4. 单字中文保留（兜底未登录词，如人名/缩写）
    """
    if not text:
        return []

    tokens = []

    # jieba 分词（中文词组）
    jieba_tokens = list(jieba.cut(text, cut_all=False))
    tokens.extend(t.strip() for t in jieba_tokens if t.strip() and t.strip() not in (" ", "\n", "\r", "\t"))

    # 英文按词切（jieba 可能切碎英文，重新提取保证完整性）
    en_words = re.findall(r'[a-zA-Z]+', text)
    tokens.extend(en_words)

    # 数字串
    numbers = re.findall(r'\d+', text)
    tokens.extend(numbers)

    # 单字中文兜底（jieba 未切出的生僻字/人名）
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    # 只补单字（已在 jieba 词组中的单字不重复加）
    jieba_set = set(t for t in tokens if len(t) == 1)
    for ch in cn_chars:
        if ch not in jieba_set:
            tokens.append(ch)

    return tokens


def build_bm25_index(corpus_paths, corpus_texts, k1=1.5, b=0.75):
    """构建 BM25 索引。k1/b 可从 recall_config.yml 传入。"""
    from rank_bm25 import BM25Okapi

    os.makedirs(CACHE_DIR, exist_ok=True)
    tokenized = [_tokenize(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)

    from _paths import safe_pickle_dump
    safe_pickle_dump({"paths": corpus_paths, "bm25": bm25}, BM25_INDEX_PATH)

    # P2：重建后清除内存缓存，下次查询重新加载
    global _INDEX_CACHE
    _INDEX_CACHE = None

    print(f"[BM25] 索引已保存: {BM25_INDEX_PATH} ({len(corpus_paths)} 文档)")
    return bm25


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
    paths = _INDEX_CACHE["paths"]
    bm25 = _INDEX_CACHE["bm25"]

    tokens = _tokenize(query_text)
    if not tokens:
        return []

    scores = bm25.get_scores(tokens)

    # 按客户过滤：在 top_k 选取前只保留该客户的文档
    # 精确匹配 clients/{客户名}/ 目录，避免子串误匹配
    if client_filter:
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
    texts = ["蓝海集团多工厂排产问题", "某化工集团CRM风险管理"]
    build_bm25_index(paths, texts)
    r = query_bm25("排产", top_k=2)
    print("BM25 query result:", r)
