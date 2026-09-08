# -*- coding: utf-8 -*-
"""B2 回归：bid-parse 注入防护三条（P2-6 + 对抗审查 D 路）。

①system prompt 带「忽略文中指令」条款；②裸 json.loads → _parse_json 容错；
③score 类型防护（null/字符串/负值不炸 sum、不入虚假分值）。
"""

import _bid_parse as bp


class TestSafeScore:
    def test_none_and_string_and_bool_and_negative(self):
        assert bp._safe_score(None) == 0
        assert bp._safe_score("30分") == 0
        assert bp._safe_score(True) == 0
        assert bp._safe_score(-5) == 0
        assert bp._safe_score(5) == 5
        assert bp._safe_score(2.5) == 2.5

    def test_total_score_no_typeerror(self):
        scoring = [
            {"item": "a", "score": 10},
            {"item": "b", "score": None},      # 曾 TypeError
            {"item": "c", "score": "30分"},    # 曾 TypeError
            "垃圾条目",                          # 非 dict 跳过
            {"item": "d", "score": 5},
        ]
        assert bp._total_score(scoring) == 15


class TestPromptInjectionGuard:
    """两个 system prompt 必须带「忽略文中指令」条款。"""

    def _extract(self, monkeypatch, payload):
        import _cloud_llm
        captured = {}

        def fake_chat(prompt, system="", **kw):
            captured["system"] = system
            return payload

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        return captured

    def test_scoring_prompt_has_ignore_instruction_clause(self, monkeypatch):
        captured = self._extract(
            monkeypatch, '{"scoring": [{"item": "方案", "score": 30}]}')
        out = bp._extract_scoring("无评分关键词的普通文本")
        assert out[0]["item"] == "方案"
        assert "忽略" in captured["system"]

    def test_disqual_prompt_has_ignore_instruction_clause(self, monkeypatch):
        import _cloud_llm
        captured = {}

        def fake_chat(prompt, system="", **kw):
            captured["system"] = system
            return '{"items": ["资质不全"]}'
        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        text = "废标：未按招标文件要求盖章。"
        bp._extract_qualifications(text)
        assert "忽略" in captured["system"]


class TestTolerantJsonParse:
    def test_fenced_json_still_parses(self, monkeypatch):
        """LLM 带围栏返回曾静默空结果入库（裸 json.loads 失败）。"""
        import _cloud_llm
        payload = '```json\n{"scoring": [{"item": "方案", "score": 30}]}\n```'
        monkeypatch.setattr(_cloud_llm, "chat", lambda *a, **kw: payload)
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        out = bp._extract_scoring("普通文本")
        assert out == [{"item": "方案", "score": 30}]

    def test_garbage_returns_empty_not_crash(self, monkeypatch):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", lambda *a, **kw: "完全不是JSON")
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        assert bp._extract_scoring("普通文本") == []
