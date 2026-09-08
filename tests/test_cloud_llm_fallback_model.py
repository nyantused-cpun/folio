# -*- coding: utf-8 -*-
"""P1-16 回归：chat() fallback 各轮必须用当轮 provider 自家模型名。

曾 `model = model or cfg.get(...)` 在循环内复改参数——首轮取到 provider A
默认模型后，fallback 到 provider B 时仍带 A 的模型名请求 B 的 API。
"""
import _cloud_llm as cl


def _mk_providers():
    return {
        "prova": {"base_url": "https://a.example", "chat_model": "model-a",
                  "reasoning_model": "model-a-r"},
        "provb": {"base_url": "https://b.example", "chat_model": "model-b",
                  "reasoning_model": "model-b-r"},
    }


def _patch_env(monkeypatch, providers, post_fn):
    monkeypatch.setattr(cl, "PROVIDERS", providers)
    monkeypatch.setattr(cl, "_get_api_key", lambda cfg, name: f"key-{name}")
    monkeypatch.setattr(cl, "_get_provider", lambda: ("prova", None))
    monkeypatch.setattr(cl, "_get_available_providers", lambda: ["prova", "provb"])
    monkeypatch.setattr(cl, "_post_json", post_fn)
    monkeypatch.setattr(cl, "_log_usage", lambda *a, **kw: None)


def test_fallback_uses_each_provider_own_model(monkeypatch):
    """主 provider 失败 → fallback 请求 payload.model 必须是 B 自家默认。"""
    sent_models = []

    def fake_post(url, headers, payload, timeout=30):
        sent_models.append(payload["model"])
        if payload["model"] == "model-a":
            return None, 500
        return {"choices": [{"message": {"content": "ok"}}], "usage": {}}, 200

    _patch_env(monkeypatch, _mk_providers(), fake_post)
    out = cl.chat("hello", model_type="chat")
    assert out == "ok"
    assert sent_models == ["model-a", "model-b"]


def test_explicit_model_only_first_round(monkeypatch):
    """显式 model 覆盖仅首轮生效；fallback 轮用当轮 provider 默认。"""
    sent_models = []

    def fake_post(url, headers, payload, timeout=30):
        sent_models.append(payload["model"])
        if payload["model"] == "custom-x":
            return None, 500
        return {"choices": [{"message": {"content": "ok"}}], "usage": {}}, 200

    _patch_env(monkeypatch, _mk_providers(), fake_post)
    out = cl.chat("hello", model_type="chat", model="custom-x")
    assert out == "ok"
    assert sent_models == ["custom-x", "model-b"]
