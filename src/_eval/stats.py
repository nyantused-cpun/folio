# -*- coding: utf-8 -*-
"""评测统计工具（T8 最小实现）。

- paired_bootstrap_ci：配对 bootstrap 95% CI
- wilcoxon_signed_rank_pvalue：Wilcoxon 符号秩检验（正态近似）

不依赖 scipy，避免新增重依赖。
"""
import math
import random


def _normal_cdf(x):
    """标准正态 CDF（erf 近似）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def paired_bootstrap_ci(pairs, n_boot=2000, alpha=0.05, seed=None):
    """对配对差异做 bootstrap 重采样，返回 (ci_low, ci_high, mean_diff)。

    pairs: [(a, b), ...]；diff = a - b。
    """
    diffs = [a - b for a, b in pairs]
    if not diffs:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(diffs)
    boot_means = []
    for _ in range(n_boot):
        sample_mean = sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        boot_means.append(sample_mean)
    boot_means.sort()
    lo_idx = int(round((alpha / 2.0) * n_boot)) - 1
    hi_idx = int(round((1.0 - alpha / 2.0) * n_boot)) - 1
    lo_idx = max(0, min(n_boot - 1, lo_idx))
    hi_idx = max(0, min(n_boot - 1, hi_idx))
    return (boot_means[lo_idx], boot_means[hi_idx], sum(diffs) / n)


def wilcoxon_signed_rank_pvalue(a, b):
    """Wilcoxon 符号秩检验（双侧，正态近似）。返回 p 值。

    输入等长配对序列；差值为 0 的样本剔除。
    """
    if len(a) != len(b) or len(a) == 0:
        return 1.0
    diffs = [x - y for x, y in zip(a, b, strict=False) if x != y]
    n = len(diffs)
    if n == 0:
        return 1.0

    abs_diffs = sorted((abs(d), i) for i, d in enumerate(diffs))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs_diffs[j + 1][0] == abs_diffs[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[abs_diffs[k][1]] = avg_rank
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, diffs, strict=False) if d > 0)
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0
    if var == 0:
        return 1.0
    z = (w_plus - mean) / math.sqrt(var)
    p = 2.0 * (1.0 - _normal_cdf(abs(z)))
    return max(0.0, min(1.0, p))