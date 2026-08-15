# -*- coding: utf-8 -*-
"""LLM 提取缓存回归测试（§八 3.3）。

key = sha256(材料 hash + 章节 + role + children + prompt_hint + client
             + evidence + prompt 版本 + provider/model)。
evidence 直接进入 prompt，按 key 设计其变化必须触发重取（安全优先决策）。
缓存文件损坏时降级为无缓存，不报错。
"""
import json

import pytest

import _outline_to_spec
from _outline_to_spec import extract_section_content

_FAKE_RESP = ('{"title": "提取标题", "content": "正文",'
              ' "key_points": ["要点"], "data": [], "source_quote": ""}')
_FAKE_RESULT = {"title": "提取标题", "content": "正文",
                "key_points": ["要点"], "data": [], "source_quote": ""}


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    """隔离缓存文件到 tmp + 计数 fake chat，返回计数器。"""
    monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH",
                        str(tmp_path / "llm_extract_cache.json"))
    import _cloud_llm
    calls = {"n": 0}

    def _fake_chat(prompt, **kwargs):
        calls["n"] += 1
        return _FAKE_RESP

    monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)
    return calls


def _section():
    return {"section": "客户痛点", "role": "pain_points",
            "children": ["成本高", "效率低"], "prompt": "写实在一点"}


class TestExtractCache:
    def test_second_call_hits_cache(self, cache_env, capsys):
        """同输入第二次不调 LLM。"""
        sec = _section()
        r1 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
        r2 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
        assert cache_env["n"] == 1
        assert r1 == r2 == _FAKE_RESULT
        out = capsys.readouterr().out
        assert "命中 LLM 提取缓存" in out
        assert "客户痛点" in out  # 提示含章节名

    def test_materials_change_triggers_refetch(self, cache_env):
        extract_section_content(_section(), "材料A" * 1000)
        extract_section_content(_section(), "材料B" * 1000)
        assert cache_env["n"] == 2

    def test_section_change_triggers_refetch(self, cache_env):
        sec2 = _section()
        sec2["children"] = ["另一个子要点"]
        extract_section_content(_section(), "材料" * 1000)
        extract_section_content(sec2, "材料" * 1000)
        assert cache_env["n"] == 2

    def test_evidence_change_triggers_refetch(self, cache_env):
        """evidence 直接进 prompt → 入 key：变化重取，相同命中。"""
        ev1 = [{"source": "a.md#1", "snippet": "证据一", "parent_context": ""}]
        ev2 = [{"source": "b.md#2", "snippet": "证据二", "parent_context": ""}]
        extract_section_content(_section(), "材料" * 1000, evidence_chunks=ev1)
        extract_section_content(_section(), "材料" * 1000, evidence_chunks=ev2)
        assert cache_env["n"] == 2
        extract_section_content(_section(), "材料" * 1000, evidence_chunks=ev1)
        assert cache_env["n"] == 2  # 第三条命中 ev1 的缓存

    def test_prompt_version_bump_triggers_refetch(self, cache_env, monkeypatch):
        extract_section_content(_section(), "材料" * 1000)
        assert cache_env["n"] == 1
        monkeypatch.setattr(_outline_to_spec, "PROMPT_VERSION", "v2")
        extract_section_content(_section(), "材料" * 1000)
        assert cache_env["n"] == 2

    def test_corrupted_cache_file_falls_back(self, cache_env, tmp_path, capsys):
        """损坏缓存文件不崩：按无缓存继续调 LLM，成功后重写为合法缓存。"""
        cache_file = tmp_path / "llm_extract_cache.json"
        cache_file.write_text("{ 这不是合法 json", encoding="utf-8")
        result = extract_section_content(_section(), "材料" * 1000)
        assert result == _FAKE_RESULT
        assert cache_env["n"] == 1
        assert "提取缓存读取失败" in capsys.readouterr().out
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert any(entry.get("section") == "客户痛点"
                   for entry in data["entries"].values())

    def test_failed_extraction_not_cached(self, cache_env, monkeypatch):
        """提取失败（chat 返回 None）不写缓存，修复后重跑正常调 LLM。"""
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", lambda *a, **k: None)
        assert extract_section_content(_section(), "材料" * 1000) is None

        calls = {"n": 0}

        def _ok(prompt, **kwargs):
            calls["n"] += 1
            return _FAKE_RESP

        monkeypatch.setattr(_cloud_llm, "chat", _ok)
        assert extract_section_content(_section(), "材料" * 1000) == _FAKE_RESULT
        assert calls["n"] == 1
