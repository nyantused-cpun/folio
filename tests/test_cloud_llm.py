# -*- coding: utf-8 -*-
"""_cloud_llm chat 重试与 prompt 组装回归测试（P0-1 撞墙兜底 / thinking hint）。

全程 mock _post_json 与 provider 链，不触真实 API。
"""

import sys
import types

import _cloud_llm


def _stub_providers(monkeypatch, providers):
    """固定 provider fallback 链 + API key，屏蔽 token 用量落盘。"""
    monkeypatch.setattr(_cloud_llm, "_get_available_providers", lambda: providers)
    monkeypatch.setattr(_cloud_llm, "_get_provider",
                        lambda: (providers[0], _cloud_llm.PROVIDERS[providers[0]]))
    monkeypatch.setattr(_cloud_llm, "_get_api_key", lambda cfg, name="": "fake-key")
    monkeypatch.setattr(_cloud_llm, "_log_usage", lambda *a, **k: None)
    # #43 卫生熔断用独立字典，防真实模块级连击跨测试累积
    monkeypatch.setattr(_cloud_llm, "_PROVIDER_FAIL_STREAK", {})


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
        # 截断且 content 为空不是可用回答，应返回 None（与调用方判失败一致）
        assert len(calls) == 1
        assert calls[0]["max_tokens"] == 24000
        assert result is None


class TestEmptyContentFallback:
    """deepseek 等 thinking provider 可能把配额耗在 reasoning 上、content 为空。

    空 content 不是可用回答，必须继续 fallback 到下一个 provider，而不是当作
    成功返回空串——否则 review 会误报「LLM 调用失败（无可用 provider）」。"""

    def test_empty_content_falls_back_to_next_provider(self, monkeypatch):
        _stub_providers(monkeypatch, ["deepseek", "minimax"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(payload["model"])
            # 第一次撞 length 触发同 provider 加倍重试；第二次仍只有 reasoning、
            # 无正文（真实 deepseek 通道病），应放弃 deepseek 切到 minimax
            if len(calls) <= 2:
                return _length_truncated()
            return _ok("备用通道 OK")

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=1000)
        assert result == "备用通道 OK"
        assert calls == ["deepseek-v4-flash", "deepseek-v4-flash", "MiniMax-M3"], \
            "deepseek 两次空 content 后应切到 minimax"

    def test_whitespace_content_falls_back(self, monkeypatch):
        _stub_providers(monkeypatch, ["deepseek", "minimax"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(payload["model"])
            if len(calls) == 1:
                return _ok("   \n  ")
            return _ok("备用通道 OK")

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=1000)
        assert result == "备用通道 OK"
        assert calls == ["deepseek-v4-flash", "MiniMax-M3"]

    def test_all_providers_empty_returns_none(self, monkeypatch):
        _stub_providers(monkeypatch, ["deepseek", "minimax"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(payload["model"])
            return _length_truncated()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=1000)
        assert result is None
        # 每家 provider：第一次 length -> 触发重试 -> 第二次仍 empty -> 放弃
        assert len(calls) == 4


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


class TestTaskThinkingOverride:
    """W1-1（#37）：task 级 thinking 覆盖——review 降档 medium，其余维持全局默认。

    背景：deepseek reasoning_effort=max 时思维链烧光 completion 配额，review
    初调撞墙加倍到 12000 仍 length 截断（审查通道不可用）。TASK_THINKING_OVERRIDE
    在 chat() 内后写覆盖 THINKING_PAYLOAD，只收窄不放宽。
    """

    def test_review_task_downgrades_deepseek_effort(self, monkeypatch):
        """post_generate_review + deepseek：reasoning_effort 覆盖为 medium，thinking 仍开。"""
        _stub_providers(monkeypatch, ["deepseek"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=3000, task="post_generate_review")
        assert result == "OK"
        assert calls[0]["reasoning_effort"] == "medium"
        assert calls[0]["thinking"] == {"type": "enabled"}, "降档只动 effort，thinking 不关"

    def test_generate_task_keeps_max(self, monkeypatch):
        """无 override 条目的生成类 task：deepseek 仍 reasoning_effort=max。"""
        _stub_providers(monkeypatch, ["deepseek"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=100, task="html_generate")
        assert result == "OK"
        assert calls[0]["reasoning_effort"] == "max"

    def test_provider_not_in_override_unchanged(self, monkeypatch):
        """override 表未列的 provider（zhipu）：review task 也不注入覆盖，行为不变。"""
        _stub_providers(monkeypatch, ["zhipu"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", max_tokens=100, task="post_generate_review")
        assert result == "OK"
        assert "reasoning_effort" not in calls[0], "zhipu 未列入 override，不应被波及"
        assert calls[0]["thinking"] == {"type": "enabled"}


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


class TestModelOverride:
    """F5-2：chat 支持 model 覆盖（review 独立模型分离）。"""

    def test_model_override_reaches_payload(self, monkeypatch):
        _stub_providers(monkeypatch, ["mimo"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", provider="mimo", model="custom-review-model",
                                 max_tokens=100)
        assert result == "OK"
        assert calls[0]["model"] == "custom-review-model"

    def test_provider_override_limits_fallback_chain(self, monkeypatch):
        _stub_providers(monkeypatch, ["zhipu", "deepseek"])
        calls = []

        def _fake_post(url, headers, payload, timeout=30):
            calls.append(dict(payload))
            return _ok()

        monkeypatch.setattr(_cloud_llm, "_post_json", _fake_post)
        result = _cloud_llm.chat("prompt", provider="zhipu", model="glm-5.2",
                                 max_tokens=100)
        assert result == "OK"
        assert len(calls) == 1, "指定 provider 后不应 fallback"
        assert calls[0]["model"] == "glm-5.2"


class TestUsageSummaryRobustness:
    """get_usage_summary 单条损坏行跳过+计数告警，不中止全量统计（P3 基础设施）。"""

    def _write_log(self, tmp_path, lines):
        log = tmp_path / "llm_usage.jsonl"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(log)

    def test_corrupt_line_skipped_not_abort(self, monkeypatch, tmp_path, capsys):
        """坏行之后的记录必须继续入账（旧实现 try 包整个循环，坏行吞掉其后全部）。"""
        monkeypatch.setattr(_cloud_llm, "USAGE_LOG", self._write_log(tmp_path, [
            '{"time": "2026-09-01 10:00:00", "provider": "zhipu", "total_tokens": 100}',
            'this is { not json',
            '{"time": "2026-09-02 10:00:00", "provider": "zhipu", "total_tokens": 50}',
            '123',
            '{"time": "2026-08-01 10:00:00", "provider": "deepseek", "total_tokens": 999}',
        ]))
        summary = _cloud_llm.get_usage_summary()
        assert summary["total_calls"] == 3
        assert summary["total_tokens"] == 1149
        assert summary["by_provider"]["zhipu"] == {"calls": 2, "tokens": 150}
        assert summary["by_provider"]["deepseek"]["tokens"] == 999
        out = capsys.readouterr().out
        assert "2 条损坏行" in out, "损坏行应计数告警留痕"

    def test_month_filter_still_works_with_corrupt_lines(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(_cloud_llm, "USAGE_LOG", self._write_log(tmp_path, [
            '{"time": "2026-09-01 10:00:00", "provider": "zhipu", "total_tokens": 100}',
            'corrupted',
            '{"time": "2026-08-01 10:00:00", "provider": "deepseek", "total_tokens": 999}',
        ]))
        summary = _cloud_llm.get_usage_summary("2026-09")
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 100

    def test_clean_log_no_warning(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(_cloud_llm, "USAGE_LOG", self._write_log(tmp_path, [
            '{"time": "2026-09-01 10:00:00", "provider": "zhipu", "total_tokens": 10}',
        ]))
        summary = _cloud_llm.get_usage_summary()
        assert summary["total_calls"] == 1
        assert "损坏行" not in capsys.readouterr().out, "无坏行不应打告警"


class _FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {}


def _install_fake_requests(monkeypatch, resp):
    """替身 requests 模块：post 恒返回 resp，全程离线。"""
    fake = types.ModuleType("requests")
    fake.post = lambda *a, **k: resp
    monkeypatch.setitem(sys.modules, "requests", fake)


class TestErrorEchoDebugGate:
    """_post_json 错误响应体为服务器可控内容：默认不回显，DEBUG_REMOTE_ECHO=1 才回显。"""

    _SECRET_BODY = "SECRET-ERROR-BODY"

    def _post_once(self, monkeypatch):
        _install_fake_requests(monkeypatch, _FakeResp(400, self._SECRET_BODY))
        return _cloud_llm._post_json("https://fake.example/v1", {}, {}, timeout=1)

    def test_body_not_echoed_by_default(self, monkeypatch, capsys):
        monkeypatch.delenv("DEBUG_REMOTE_ECHO", raising=False)
        data, status = self._post_once(monkeypatch)
        assert data is None and status == 400
        out = capsys.readouterr().out
        assert "HTTP 400" in out
        assert self._SECRET_BODY not in out, "响应体不应默认回显（服务器可控内容）"

    def test_body_echoed_with_debug_switch(self, monkeypatch, capsys):
        monkeypatch.setenv("DEBUG_REMOTE_ECHO", "1")
        _data, status = self._post_once(monkeypatch)
        assert status == 400
        assert self._SECRET_BODY in capsys.readouterr().out


class TestHostPromptTruncation:
    """host_prompt 默认只记长度+前 80 字符，DEBUG_REMOTE_ECHO=1 才输出全文（安全 P3）。"""

    def _host_mode(self, monkeypatch):
        monkeypatch.setenv("LLM_MODE", "host")
        monkeypatch.setattr(_cloud_llm, "LLM_MODE", "host")

    def test_prompt_truncated_by_default(self, monkeypatch, capsys):
        self._host_mode(monkeypatch)
        monkeypatch.delenv("DEBUG_REMOTE_ECHO", raising=False)
        prompt = "HEAD-MARKER" + "x" * 100 + "TAIL-SECRET-MATERIAL"
        assert _cloud_llm.host_prompt("task", prompt) is None
        out = capsys.readouterr().out
        assert "HEAD-MARKER" in out, "前 80 字符预览仍可见"
        assert "TAIL-SECRET-MATERIAL" not in out, "材料全文不应落会话日志"
        assert f"长度={len(prompt)}" in out
        assert "DEBUG_REMOTE_ECHO" in out, "应提示全文回显开关"

    def test_debug_switch_echoes_full_prompt(self, monkeypatch, capsys):
        self._host_mode(monkeypatch)
        monkeypatch.setenv("DEBUG_REMOTE_ECHO", "1")
        prompt = "HEAD" + "x" * 100 + "TAIL-SECRET-MATERIAL"
        _cloud_llm.host_prompt("task", prompt)
        assert "TAIL-SECRET-MATERIAL" in capsys.readouterr().out


class TestProviderHygieneFuse:
    """#43：provider 卫生熔断——key 存在但失效的连败 provider 进程内让位。

    附册 §1.2：无 key 的 provider 本就零成本（available 列表已过滤），要防的
    是「key 存在但失效」每轮先撞一次死链。成功清零，新进程自动重试。
    """

    def test_fail_streak_skips_provider_after_max(self, monkeypatch):
        _stub_providers(monkeypatch, ["zhipu", "deepseek"])
        monkeypatch.setattr(_cloud_llm, "_PROVIDER_FAIL_STREAK", {})
        calls = []

        def fake_post(url, headers, payload, timeout=30):
            calls.append(url)
            if "deepseek" not in url:
                return (None, 401)  # zhipu key 失效
            return _ok("from-deepseek")

        monkeypatch.setattr(_cloud_llm, "_post_json", fake_post)
        for _ in range(3):
            assert _cloud_llm.chat("hi") == "from-deepseek"
        assert sum(1 for u in calls if "deepseek" not in u) == 3
        calls.clear()
        assert _cloud_llm.chat("hi") == "from-deepseek"
        assert all("deepseek" in u for u in calls)  # 第 4 次起 zhipu 零调用

    def test_success_resets_streak(self, monkeypatch):
        _stub_providers(monkeypatch, ["zhipu", "deepseek"])
        monkeypatch.setattr(_cloud_llm, "_PROVIDER_FAIL_STREAK", {"zhipu": 2})

        def fake_post(url, headers, payload, timeout=30):
            if "deepseek" in url:
                return _ok("from-deepseek")
            return _ok("z-ok")  # 失效 key 恢复

        monkeypatch.setattr(_cloud_llm, "_post_json", fake_post)
        assert _cloud_llm.chat("hi") == "z-ok"
        assert _cloud_llm._PROVIDER_FAIL_STREAK["zhipu"] == 0
