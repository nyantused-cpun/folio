# -*- coding: utf-8 -*-
"""_cloud_llm chat 重试与 prompt 组装回归测试（P0-1 撞墙兜底 / thinking hint）。

全程 mock _post_json 与 provider 链，不触真实 API。
"""

import _cloud_llm


def _stub_providers(monkeypatch, providers):
    """固定 provider fallback 链 + API key，屏蔽 token 用量落盘。"""
    monkeypatch.setattr(_cloud_llm, "_get_available_providers", lambda: providers)
    monkeypatch.setattr(_cloud_llm, "_get_provider",
                        lambda: (providers[0], _cloud_llm.PROVIDERS[providers[0]]))
    monkeypatch.setattr(_cloud_llm, "_get_api_key", lambda cfg, name="": "fake-key")
    monkeypatch.setattr(_cloud_llm, "_log_usage", lambda *a, **k: None)


def _ok(content="OK"):
    return ({"choices": [{"finish_reason": "stop", "message": {"content": content}}],
             "usage": {}}, 200)


def _length_truncated():
    return ({"choices": [{"finish_reason": "length", "message": {"content": ""}}],
             "usage": {}}, 200)


class TestMaxTokensRetry:
    """finish_reason=length -> max_tokens 加倍重试（上限 16000，覆盖 thinking 余量）。"""

    def test_thinking_effective_12000_retries(self, monkeypatch):
        """thinking 余量后 effective=4000×3=12000 撞 length 后触发重试。

        回归：旧上限 8000 时 12000 > 8000 永远进不了重试分支（死代码），
        架构章节（最需要撞墙重试）享受不到兜底。"""
        _stub_providers(monkeypatch, ["zhipu"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _length_truncated() if len(calls) == 1 else _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", system="sys", max_tokens=4000)
        assert result == "OK"
        assert len(calls) == 2, "撞 length 应重试一次"
        assert calls[0]["max_tokens"] == 12000  # 4000 × THINKING_TOKEN_MULTIPLIER
        assert calls[1]["max_tokens"] == 16000  # min(12000×2, MAX_TOKENS_RETRY_CEILING)

    def test_retry_capped_at_ceiling(self, monkeypatch):
        """已超上限时不再重试（避免无意义加倍/死循环）。"""
        _stub_providers(monkeypatch, ["zhipu"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _length_truncated()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", system="sys", max_tokens=8000)
        # effective = max(8000×3, 4000) = 24000 > 16000：不触发重试，
        # 截断响应按原样解析返回（content 为空串）
        assert len(calls) == 1
        assert calls[0]["max_tokens"] == 24000
        assert result == ""


class TestChineseThinkingHint:
    """中文思考 hint：fallback 循环内不重复追加；非 thinking provider 不加。"""

    def test_hint_not_duplicated_across_fallback(self, monkeypatch):
        """两个 thinking provider 连续尝试：system 里 hint 各出现且仅出现一次。"""
        _stub_providers(monkeypatch, ["zhipu", "deepseek"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            if len(calls) == 1:
                return None, 500  # 主 provider 失败 -> fallback
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", system="你是助手", max_tokens=100)
        assert result == "OK"
        assert len(calls) == 2
        for payload in calls:
            sys_msg = payload["messages"][0]["content"]
            assert sys_msg.startswith("你是助手")
            assert sys_msg.count("请务必使用中文进行思考过程") == 1, \
                "hint 在 fallback 循环内重复追加（旧 system 就地改 bug）"

    def test_no_hint_for_non_thinking_provider(self, monkeypatch):
        """非 thinking provider（mimo）不加中文思考 hint。"""
        _stub_providers(monkeypatch, ["mimo"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", system="你是助手", max_tokens=100)
        assert result == "OK"
        sys_msg = calls[0]["messages"][0]["content"]
        assert sys_msg == "你是助手"


class TestHostMode:
    """LLM_MODE=host：chat/vision_chat 不调云端，打印 prompt 由宿主 AI 执行。"""

    def test_host_mode_returns_none_and_prints_prompt(self, monkeypatch, capsys):
        """host 模式：chat 返回 None，stdout 打印 [host-mode ...] 提示与 prompt。"""
        monkeypatch.setenv("LLM_MODE", "host")
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "host")
        result = _cloud_llm.chat("hello prompt", system="sys", task="test_task")
        captured = capsys.readouterr()
        assert result is None
        assert "[host-mode" in captured.out
        assert "hello prompt" in captured.out

    def test_vision_chat_host_mode_returns_none(self, monkeypatch, capsys):
        """host 模式：vision_chat 返回 None，stdout 打印 task 与 image。"""
        monkeypatch.setenv("LLM_MODE", "host")
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "host")
        result = _cloud_llm.vision_chat("describe this", "fake.png", task="vision")
        captured = capsys.readouterr()
        assert result is None
        assert "[host-mode" in captured.out
        assert "image=fake.png" in captured.out

    def test_cloud_mode_default_still_calls_api(self, monkeypatch):
        """未设 host（cloud 默认）时 chat 走原云端路径。"""
        monkeypatch.delenv("LLM_MODE", raising=False)
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "cloud")
        _stub_providers(monkeypatch, ["mimo"])
        monkeypatch.setattr(_cloud_llm, "_post_json", lambda *a, **k: _ok())
        result = _cloud_llm.chat("prompt", max_tokens=100)
        assert result == "OK"
