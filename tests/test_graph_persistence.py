# -*- coding: utf-8 -*-
"""graph decision 节点 persistence/scope 解析（曾硬编码 permanent+client）。

与 _theme_guard 同一套正则：显式字段按真实值，缺省按 permanent/client 向后兼容。
"""

from _graph import _extract_decision_nodes


class TestDecisionPersistence:
    def test_explicit_task_scope_parsed(self):
        content = """### D-001 · 报价只走清单价
- **日期**: 2026-07-01
- **决策**: 报价以清单价为准
- **理由**: 客户要求
- **persistence: task**
- **scope: task**
- **task_id: 20260701_120000**
"""
        nodes = _extract_decision_nodes(content)
        assert len(nodes) == 1
        assert nodes[0]["metadata"]["persistence"] == "task"
        assert nodes[0]["metadata"]["scope"] == "task"

    def test_explicit_permanent_client_parsed(self):
        content = """## 决策 2：交付必须 HTML 先行
- **日期**: 2026-07-02
- **决策内容**: HTML 先行，确认后再出 PPT
- **推论**: 减少返工
- **persistence: permanent**
- **scope: client**
"""
        nodes = _extract_decision_nodes(content)
        assert len(nodes) == 1
        assert nodes[0]["metadata"]["persistence"] == "permanent"
        assert nodes[0]["metadata"]["scope"] == "client"

    def test_missing_fields_default_permanent_client(self):
        content = """## 决策 1：旧决策无字段
- **日期**: 2026-05-01
- **决策内容**: 沿用旧格式
- **推论**: 历史原因
"""
        nodes = _extract_decision_nodes(content)
        assert len(nodes) == 1
        assert nodes[0]["metadata"]["persistence"] == "permanent"
        assert nodes[0]["metadata"]["scope"] == "client"


class TestDecisionDedupeKey:
    """D-116：decision 去重键——编号用 num；格式3（num=0）用 (date, title)。"""

    def _node(self, num, date, title):
        return {"type": "decision", "id": "x", "title": title,
                "metadata": {"decision_num": num, "date": date}}

    def test_num_key(self):
        from _graph import _decision_dedupe_key
        assert _decision_dedupe_key(self._node(7, "", "标题A")) == ("num", 7)
        assert _decision_dedupe_key(self._node(7, "", "标题B")) == ("num", 7)

    def test_format3_key_uses_date_title(self):
        from _graph import _decision_dedupe_key
        n1 = self._node(0, "2026-08-12", "4A 架构 skill 方法论内核增补")
        n2 = self._node(0, "2026-08-12", "4A 架构 skill 方法论内核增补")
        n3 = self._node(0, "2026-08-13", "4A 架构 skill 方法论内核增补")
        assert _decision_dedupe_key(n1) == _decision_dedupe_key(n2)
        assert _decision_dedupe_key(n1) != _decision_dedupe_key(n3)
