# -*- coding: utf-8 -*-
"""T8 评测统计工具测试。"""

from _eval import paired_bootstrap_ci, wilcoxon_signed_rank_pvalue


class TestBootstrapCI:
    def test_known_difference(self):
        pairs = [(1.0, 0.0)] * 100
        lo, hi, mean = paired_bootstrap_ci(pairs, n_boot=500, seed=1)
        assert abs(mean - 1.0) < 1e-9
        assert lo <= mean <= hi

    def test_empty_returns_zero(self):
        assert paired_bootstrap_ci([]) == (0.0, 0.0, 0.0)


class TestWilcoxon:
    def test_obvious_difference_is_significant(self):
        a = [10.0] * 20
        b = [0.0] * 20
        p = wilcoxon_signed_rank_pvalue(a, b)
        assert p < 0.05

    def test_identical_returns_one(self):
        a = [1.0, 2.0, 3.0]
        assert wilcoxon_signed_rank_pvalue(a, a) == 1.0

    def test_length_mismatch_returns_one(self):
        assert wilcoxon_signed_rank_pvalue([1.0], []) == 1.0