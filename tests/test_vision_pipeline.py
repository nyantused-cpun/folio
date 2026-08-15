# -*- coding: utf-8 -*-
"""识图管线本地 mock 测试：缓存命中 / 多格式 / 并发写。

不依赖真实 API——monkeypatch 掉 _post_json（网络）和 _get_api_key，
VISION_CACHE / USAGE_LOG 重定向到 tmp_path，避免污染真实日志与缓存。
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor


def _mock_vision(monkeypatch, tmp_path, desc, captured=None):
    """通用 mock：注入假 key + 假网络，重定向缓存/用量日志，返回调用计数器。"""
    import _cloud_llm

    monkeypatch.setattr(_cloud_llm, "VISION_CACHE", str(tmp_path / "vision_cache.json"))
    monkeypatch.setattr(_cloud_llm, "USAGE_LOG", str(tmp_path / "llm_usage.jsonl"))
    monkeypatch.setattr(_cloud_llm, "_get_api_key", lambda cfg, p="": "fake-key")

    call_count = {"n": 0}

    def fake_post(url, headers, payload, timeout=30):
        call_count["n"] += 1
        if captured is not None:
            captured.append(payload)
        return {
            "choices": [{"message": {"content": desc, "reasoning_content": "思考过程"}}],
            "usage": {
                "prompt_tokens": 100, "completion_tokens": 50,
                "prompt_tokens_details": {"image_tokens": 200},
                "completion_tokens_details": {"reasoning_tokens": 10},
            },
        }, 200

    monkeypatch.setattr(_cloud_llm, "_post_json", fake_post)
    return _cloud_llm, call_count


class TestVisionPipeline:
    def test_duplicate_screenshot_hits_cache(self, monkeypatch, tmp_path):
        """重复截图（同内容不同文件名）：第二次命中缓存，不发起网络请求。"""
        _cloud_llm, call_count = _mock_vision(monkeypatch, tmp_path, "重复截图描述")

        content = b"\x89PNG\r\n\x1a\n" + b"same-screenshot-bytes" * 10
        a = tmp_path / "shot_a.png"
        b = tmp_path / "shot_b.png"  # 文件名不同，字节完全相同
        a.write_bytes(content)
        b.write_bytes(content)

        r1 = _cloud_llm.vision_chat("描述这张截图", str(a))
        r2 = _cloud_llm.vision_chat("描述这张截图", str(b))

        assert r1 == "重复截图描述"
        assert r2 == "重复截图描述"
        assert call_count["n"] == 1  # 第二次命中缓存，未调网络

    def test_svg_and_heic_mime(self, monkeypatch, tmp_path):
        """svg / heic 不压缩直发，data URL mime 正确。"""
        captured = []
        _cloud_llm, _ = _mock_vision(monkeypatch, tmp_path, "多格式描述", captured)

        cases = [
            ("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "svg+xml"),
            ("b.heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", "heic"),
        ]
        for fname, content, expect_mime in cases:
            p = tmp_path / fname
            p.write_bytes(content)
            desc = _cloud_llm.vision_chat("描述", str(p))
            assert desc == "多格式描述"
            img_url = captured[-1]["messages"][1]["content"][1]["image_url"]["url"]
            assert f"image/{expect_mime};base64," in img_url

    def test_concurrent_cache_writes_no_loss(self, monkeypatch, tmp_path):
        """并发识别多张图（模拟 read_batch 4 线程），缓存条目不丢。"""
        _cloud_llm, _ = _mock_vision(monkeypatch, tmp_path, "并发描述")

        n = 30
        raws = [f"fake-image-{i}".encode() for i in range(n)]
        keys = {hashlib.sha256(raw).hexdigest() for raw in raws}
        paths = []
        for i, raw in enumerate(raws):
            p = tmp_path / f"img{i}.png"
            p.write_bytes(raw)
            paths.append(str(p))

        results = [None] * n

        def worker(idx):
            results[idx] = _cloud_llm.vision_chat("描述", paths[idx])

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(worker, range(n)))

        assert all(r == "并发描述" for r in results)
        cache = _cloud_llm._vision_cache_load()
        assert len(cache) == n          # 并发写不丢条目
        assert keys <= set(cache.keys())  # 每个图片 hash 都在
