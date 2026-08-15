# -*- coding: utf-8 -*-
"""注意力压缩：长文档分段摘要 + 历史会话压缩。
保留高注意力权重内容（数字/标题/决策词/待办词/结论句/首尾段）。"""
import re

ATTENTION_PATTERNS = [
    r'\d+[%万千百十亿万\.]+',
    r'^#+\s',
    r'^===.+===',
    r'(决定|采用|否决|确认|选定|放弃)',
    r'(待办|下次|确认|跟进|未完成)',
    r'(因此|所以|综上|建议|推荐)',
]

_COMPILED = [re.compile(p) for p in ATTENTION_PATTERNS]


def _is_attention_line(line):
    for pat in _COMPILED:
        if pat.search(line):
            return True
    return False


def extract_attention(chunk):
    """从一段文本提取注意力要点。保留高权重行 + 首尾行。"""
    lines = [line for line in chunk.split('\n') if line.strip()]
    if not lines:
        return ""

    kept = []
    kept.append(lines[0])
    for line in lines[1:-1]:
        if _is_attention_line(line):
            kept.append(line)
    if len(lines) > 1:
        kept.append(lines[-1])

    # P3：移除死代码 else chunk[:200]，kept 至少含首行不会为空
    return '\n'.join(kept)


def split_by_structure(text):
    """按章节/页切分。优先 === 第N页 === / ## 标题 / 空行段。"""
    chunks = re.split(r'(?=\n===.+===\n)', text)
    if len(chunks) > 1:
        return chunks

    chunks = re.split(r'(?=\n##\s)', text)
    if len(chunks) > 1:
        return chunks

    return text.split('\n\n')


def compress_document(text, max_chars=8000):
    """长文档压缩：分段摘要 + 注意力保留。超长则递归压缩。"""
    if len(text) <= max_chars:
        return text

    chunks = split_by_structure(text)
    compressed_chunks = [extract_attention(c) for c in chunks if c.strip()]

    result = "\n\n".join(compressed_chunks)
    if len(result) > max_chars:
        if len(result) >= len(text):
            return result[:max_chars]
        return compress_document(result, max_chars)
    return result


def summarize_for_attention(text, max_chars=2000):
    """供 _pipeline.read_full 调用的摘要入口。"""
    return compress_document(text, max_chars)
