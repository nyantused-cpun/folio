# -*- coding: utf-8 -*-
"""上下文召回一期评测基建（T8）。

提供配对 bootstrap 与 Wilcoxon 符号秩检验的最小纯 Python 实现。
"""
from _eval.stats import paired_bootstrap_ci, wilcoxon_signed_rank_pvalue

__all__ = ["paired_bootstrap_ci", "wilcoxon_signed_rank_pvalue"]