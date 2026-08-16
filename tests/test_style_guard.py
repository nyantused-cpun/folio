# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""_style_guard 回归测试：正向必命中 + 负向防误报（2026-08-14 去AI化调研落地）。

范式来源：human-copywrite tests/eval（require/forbid 正则 + self-test）、
qu-ai-wei eval-manifest（"必须保留/禁止出现"断言）。
"""

from _style_guard import check, _get_all_patterns


def _names(issues):
    return {i["name"] for i in issues}


def test_all_patterns_loads_dynamic_dictionaries():
    """self-test：硬编码 + 动态词库合并后，新词库必须都在检测表里。"""
    names = set(_get_all_patterns().keys())
    for expected in ("significance_inflation", "abstract_subject",
                     "meta_narrative", "evidence_overclaim", "vague_attribution"):
        assert expected in names, f"动态词库 {expected} 未加载进检测表"


def test_ai_heavy_text_hits_multiple():
    """self-test：AI 味重样本必须命中 ≥3 类（防正则退化失效）。"""
    text = ("在当今数字化时代，科技赋能企业转型。本方案旨在成功验证市场需求，"
            "这不是效率问题，而是系统问题，看似简单，本质深刻，"
            "标志着公司开启新篇章。")
    names = _names(check(text))
    assert len(names) >= 3, f"AI 味样本命中过少: {names}"


def test_clean_text_hits_nothing():
    """self-test：干净样本必须 0 命中（防误报泛滥）。"""
    text = ("先评审再交付。测试验证通过，最佳实践是先出大纲。"
            "我们提供数据安全保障，支持数据共享。系统上线后工单下降 40%。")
    assert check(text) == [], f"干净样本被误报: {check(text)}"


def test_abstract_subject():
    assert "abstract_subject" in _names(check("时代呼唤数字化转型"))


def test_meta_narrative():
    assert "meta_narrative" in _names(check("本方案将从三个方面展开"))


def test_evidence_overclaim():
    assert "evidence_overclaim" in _names(check("成功验证了市场需求"))


def test_significance_inflation():
    assert "significance_inflation" in _names(check("这标志着公司开启新篇章"))


def test_pivot_skeleton_hits():
    """对称骨架：不是…而是 / 不在于…而在于 / 既是…也是…更是。"""
    assert "对称骨架" in _names(check("这不是效率问题，而是系统问题"))
    assert "对称骨架" in _names(check("问题不在于工具，而在于流程"))
    assert "对称骨架" in _names(check("既是技术升级，也是管理变革，更是文化重塑"))


def test_fake_reveal_hits():
    assert "假揭示" in _names(check("看似简单，本质复杂"))


def test_normal_sop_not_hit():
    """负向：SOP/正常用法不误报。"""
    for text in (
        "先评审再交付",
        "测试验证通过",
        "这是最佳实践",
        "深度分析后给出全面评估",
        "不仅支持导入，而且支持导出",  # 正常递进关联词，不是翻案腔
    ):
        issues = check(text)
        for i in issues:
            assert i["name"] not in ("对称骨架", "假揭示", "evidence_overclaim",
                                     "significance_inflation"), f"误报 {text!r}: {i['name']}"


def test_scope_exclusion_hits_at_prompt_level_only():
    """范围排除句（"这不是退款，而是撤销授权"）命中对称骨架属预期——
    机械正则无法区分引语/法定表述，只做提示级，由 AI 人工判断是否保留。"""
    issues = check("这不是退款，而是撤销尚未结算的授权")
    assert "对称骨架" in _names(issues)  # 提示级命中，不硬阻断


def test_dynamic_loader_skips_non_dictionary_files():
    """附带发现修复：README / pytest 笔记的散文行不得混进词库。"""
    from _style_guard import _load_antipatterns_from_dir
    extra = _load_antipatterns_from_dir()
    assert "README" not in extra
    assert "pytest-monkeypatch-delenv" not in extra
    for fname, cfg in extra.items():
        for w in cfg["pattern"].split("|"):
            assert len(w) <= 40, f"{fname} 含超长散文行: {w[:20]}..."
            assert not w.startswith(">"), f"{fname} 含引用行: {w[:20]}..."
