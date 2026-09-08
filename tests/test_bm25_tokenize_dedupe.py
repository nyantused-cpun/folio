# -*- coding: utf-8 -*-
"""C-B1：_bm25._tokenize 英文/数字差集补充，防双计回归测试。

背景：旧实现把正则提取的全部英文词/数字串整体追加到 jieba 结果之后，
jieba 已产出的相同 token 被双计，英文/数字词权重虚高、BM25 打分移位。
新实现：正则结果只补 jieba 未覆盖的差集（strip/小写规范化后比较）。
"""
import re

import _bm25


class TestEnNumberDedupe:
    def test_en_word_not_double_counted_when_jieba_covers(self):
        tokens = _bm25._tokenize("蓝海集团 2026年 CRM系统升级 v2.1 排产计划")
        assert tokens.count("CRM") == 1  # jieba 已产出 CRM，正则不再重复追加
        assert tokens.count("2026") == 1  # 数字同理

    def test_number_not_double_counted(self):
        tokens = _bm25._tokenize("2026-09-07 数字化 招标")
        assert tokens.count("2026") == 1
        assert tokens.count("09") == 1
        assert tokens.count("07") == 1

    def test_regex_fallback_still_fills_jieba_missed_tokens(self):
        # jieba 把 "v2.1" 当作一个 token，正则切碎的 v / 2 / 1 必须补上（兜底不失效）
        tokens = _bm25._tokenize("蓝海集团 2026年 CRM系统升级 v2.1 排产计划")
        assert "v" in tokens
        assert tokens.count("2") == 1
        assert tokens.count("1") == 1

    def test_whitespace_normalized_before_diff(self):
        # jieba token 带空白时，差集比较仍应识别为已覆盖
        tokens = _bm25._tokenize("CRM 风险管理")
        assert tokens.count("CRM") == 1
        assert "风险管理" in tokens


class TestChineseBehaviorUnchanged:
    def test_domain_dict_terms_still_whole(self):
        tokens = _bm25._tokenize("数据架构 需求分析")
        assert "数据架构" in tokens  # 领域词典整词保留
        assert "需求分析" in tokens

    def test_single_char_fallback_intact(self):
        tokens = _bm25._tokenize("甲乙方")
        for ch in "甲乙方":
            assert ch in tokens  # 单字中文兜底仍在

    def test_empty_text(self):
        assert _bm25._tokenize("") == []
        assert _bm25._tokenize(None) == []


class TestNoResidualDoubleCount:
    """结构性断言：任意样本文本中，英文词/数字串在最终 token 列表里计数 == 1
    （jieba 已覆盖）或仍由正则兜底但绝不来自重复追加。"""

    def test_sample_text_has_no_en_number_duplication(self):
        sample = "蓝海集团 2026年 CRM系统升级 v2.1 排产计划"
        tokens = _bm25._tokenize(sample)
        for w in set(re.findall(r'[a-zA-Z]+', sample)) | set(re.findall(r'\d+', sample)):
            assert tokens.count(w) == 1, f"{w} 双计: count={tokens.count(w)}"
