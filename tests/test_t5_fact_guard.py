# -*- coding: utf-8 -*-
"""T5 fact_guard 模块测试。

覆盖：数字归一化、实体白名单、guard_check 提取、隔离区队列读写。
"""

import _fact_guard


class TestNormalizeNum:
    def test_chinese_number(self):
        assert _fact_guard.normalize_num("一百二十三") == "123"
        assert _fact_guard.normalize_num("五十") == "50"
        assert _fact_guard.normalize_num("零") == "0"

    def test_percent(self):
        assert _fact_guard.normalize_num("百分之五十") == "50%"

    def test_date(self):
        assert _fact_guard.normalize_num("2026年9月1日") == "2026-09-01"


class TestGuardCheck:
    def test_extract_numbers_and_entities(self):
        whitelist = {"数据架构", "微服务"}
        result = _fact_guard.guard_check(
            "本方案采用数据架构与微服务，预算 100 万元，占比百分之五十。",
            whitelist=whitelist,
        )
        assert "100" in result["numbers"]
        assert "50%" in result["normalized_numbers"]
        assert "数据架构" in result["entities"]
        assert "微服务" in result["entities"]
        assert result["violations"] == []


class TestGuardQueue:
    def test_enqueue_and_list(self, tmp_path, monkeypatch):
        queue_file = tmp_path / "guard_queue.jsonl"
        monkeypatch.setattr(_fact_guard, "GUARD_QUEUE_PATH", str(queue_file))
        _fact_guard.enqueue_guard_item({"id": "g1", "text": "x"})
        _fact_guard.enqueue_guard_item({"id": "g2", "text": "y"})
        items = _fact_guard.list_guard_queue()
        assert [i["id"] for i in items] == ["g1", "g2"]

    def test_missing_queue_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            _fact_guard, "GUARD_QUEUE_PATH", str(tmp_path / "no.jsonl")
        )
        assert _fact_guard.list_guard_queue() == []