# -*- coding: utf-8 -*-
"""C-A4 回归：_verify 占位符正则 TODO 词边界（0907 修复计划）。

历史缺陷：TODO 分支写作 ``TODO:?示例文字``——只有「TODO(:)示例文字」整串
才命中，独立 TODO / TODO:任意文字 永漏检。修复为 ``\\bTODO(?:示例文字)?\\b``：
- 独立 TODO、TODO:重构、TODO：重构（全角冒号）均命中；
- 「TODO示例文字」旧命中行为保持；
- TODOLIST / todorov / autodoc 等粘连词不误报（\\b 词边界）；
- 大小写语义以代码现状为准：整条正则沿用 re.IGNORECASE。
存量交付物实测 output/*.html 裸 TODO 零命中，修复不翻旧账。
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _verify import check_placeholder_residual


def _has_hit(text, needle=None):
    hits = check_placeholder_residual(text)
    if not hits:
        return False
    if needle is None:
        return True
    return any(needle in h for h in hits)


# ---------- 应命中（修复目标） ----------

def test_bare_todo_hit():
    assert _has_hit("备注：TODO", "TODO")


def test_todo_ascii_colon_hit():
    assert _has_hit("TODO:重构此页", "TODO")


def test_todo_fullwidth_colon_hit():
    assert _has_hit("TODO：重构此页", "TODO")


def test_todo_lowercase_hit():
    """大小写语义以现状为准：整条正则 IGNORECASE，小写同命中。"""
    assert _has_hit("<!-- todo: 补数据 -->", "todo")


def test_todo_shili_kept():
    """旧命中行为保持：TODO示例文字 / TODO: 示例文字。"""
    assert _has_hit("TODO示例文字", "TODO示例文字")
    assert _has_hit("TODO: 示例文字", "TODO")


# ---------- 不应命中（词边界防误报） ----------

def test_todo_glued_words_no_false_positive():
    assert not _has_hit("TODOLIST 已清空")
    assert not _has_hit("文献：Todorov 1990")
    assert not _has_hit("见 autodoc 章节")
    assert not _has_hit("METHOD list")


# ---------- 其余占位符分支不回归 ----------

def test_other_alternatives_kept():
    assert _has_hit("此处占位", "占位")
    assert _has_hit("细节待补充", "待补充")
    assert _has_hit("方案待定", "待定")
    assert _has_hit("Lorem ipsum dolor", "Lorem ipsum")
    assert _has_hit("Services One", "Services One")


def test_hit_message_format():
    hits = check_placeholder_residual("TODO 待办与占位符")
    assert len(hits) == 1
    assert hits[0].startswith("占位符残留：")
    assert "TODO" in hits[0] and "占位" in hits[0]


def test_no_hit_returns_empty():
    assert check_placeholder_residual("正常交付文案，无任何遗留标记") == []
