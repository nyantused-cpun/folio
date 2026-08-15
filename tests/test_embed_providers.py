# -*- coding: utf-8 -*-
"""embedding 双 provider（P1）回归测试：选择顺序 + 端点路由 + 模型不一致降级。"""



class TestCurrentEmbedProvider:
    """provider 选择顺序：智谱 → SiliconFlow → None。"""

    def test_zhipu_priority(self, monkeypatch):
        monkeypatch.setenv("ZHIPU_API_KEY", "zk")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk")
        from _cloud_llm import current_embed_provider
        assert current_embed_provider() == ("zhipu", "embedding-3")

    def test_siliconflow_fallback(self, monkeypatch):
        monkeypatch.setenv("ZHIPU_API_KEY", "")
        monkeypatch.setenv("GLM_API_KEY", "")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk")
        from _cloud_llm import current_embed_provider
        assert current_embed_provider() == ("siliconflow", "BAAI/bge-m3")

    def test_none_when_no_key(self, monkeypatch):
        for v in ("ZHIPU_API_KEY", "GLM_API_KEY", "SILICONFLOW_API_KEY"):
            monkeypatch.setenv(v, "")
        from _cloud_llm import current_embed_provider
        assert current_embed_provider() is None

    def test_embed_batch_uses_siliconflow_url(self, monkeypatch):
        """缺智谱 key 时 embed_batch 走 SiliconFlow 端点与模型。"""
        monkeypatch.setenv("ZHIPU_API_KEY", "")
        monkeypatch.setenv("GLM_API_KEY", "")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
        import _cloud_llm
        captured = {}

        def fake_post(url, headers, payload, timeout=30):
            captured["url"] = url
            captured["payload"] = payload
            return ({"data": [{"index": 0, "embedding": [0.1, 0.2]}]}, 200)

        monkeypatch.setattr(_cloud_llm, "_post_json", fake_post)
        vecs = _cloud_llm.embed_batch(["测试"])
        assert vecs == [[0.1, 0.2]]
        assert captured["url"] == _cloud_llm.SILICONFLOW_EMBED_URL
        assert captured["payload"]["model"] == "BAAI/bge-m3"

    def test_embed_batch_no_key_returns_none(self, monkeypatch):
        for v in ("ZHIPU_API_KEY", "GLM_API_KEY", "SILICONFLOW_API_KEY"):
            monkeypatch.setenv(v, "")
        from _cloud_llm import embed_batch
        assert embed_batch(["x"]) is None


class TestProviderSwitchRebuild:
    """build_embedding_index 检测到 provider 切换时必须全量重建（不能增量复用旧向量）。"""

    def test_switch_clears_existing_vectors(self, monkeypatch, tmp_path, capsys):
        import _embed_index
        import numpy as np
        import json
        # 旧索引：embedding-3 模型（新格式 npy+json）
        monkeypatch.setattr(_embed_index, "CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(_embed_index, "EMBED_MATRIX_PATH", str(tmp_path / "embeddings_matrix.npy"))
        monkeypatch.setattr(_embed_index, "EMBED_INDEX_PATH", str(tmp_path / "embeddings_index.json"))
        monkeypatch.setattr(_embed_index, "EMBED_CACHE_PATH", str(tmp_path / "embeddings_cache.pkl"))
        np.save(str(tmp_path / "embeddings_matrix.npy"), np.array([[0.1, 0.2]], dtype=np.float32))
        with open(str(tmp_path / "embeddings_index.json"), "w") as f:
            json.dump({"paths": ["old.md#1"], "model": "embedding-3", "dim": 2,
                       "meta": {"old.md#1": {"chars": 1, "mtime": 1}}}, f)
        # 当前只有 SiliconFlow（模型不同）→ 应打印全量重建提示
        monkeypatch.setenv("ZHIPU_API_KEY", "")
        monkeypatch.setenv("GLM_API_KEY", "")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "sk")
        monkeypatch.setattr(_embed_index, "scan_corpus", lambda: [])
        _embed_index.build_embedding_index()
        assert "全量重建" in capsys.readouterr().out


class TestEmbeddingModelMismatch:
    """索引模型与当前 provider 不一致时，_embedding_recall 退回而不是静默错配。"""

    def _write_npy_index(self, cache_dir, vectors_dict, model):
        """helper：写入 npy+json 索引文件。"""
        import numpy as np
        import json
        paths = list(vectors_dict.keys())
        matrix = np.array([vectors_dict[p] for p in paths], dtype=np.float32)
        np.save(str(cache_dir / "embeddings_matrix.npy"), matrix)
        with open(str(cache_dir / "embeddings_index.json"), "w") as f:
            json.dump({"paths": paths, "model": model, "dim": int(matrix.shape[1]),
                       "meta": {}}, f)

    def test_mismatch_degrades_to_none(self, monkeypatch, tmp_path, capsys):
        import _recall
        # 伪造 SiliconFlow 模型索引
        cache_dir = tmp_path / "_knowledge" / ".cache"
        cache_dir.mkdir(parents=True)
        self._write_npy_index(cache_dir, {"clients/测试/doc.md#1": [0.1, 0.2, 0.3]}, "BAAI/bge-m3")
        monkeypatch.setattr(_recall, "SCRIPT_DIR", str(tmp_path))
        # 当前 provider 是智谱（与索引模型不一致）
        monkeypatch.setenv("ZHIPU_API_KEY", "zk")
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "embed", lambda *a, **kw: [0.1, 0.2, 0.3])
        result = _recall._embedding_recall("测试")
        assert result is None
        assert "不一致" in capsys.readouterr().out

    def test_match_proceeds_normally(self, monkeypatch, tmp_path):
        import _recall
        cache_dir = tmp_path / "_knowledge" / ".cache"
        cache_dir.mkdir(parents=True)
        self._write_npy_index(cache_dir, {"clients/测试/doc.md#1": [1.0, 0.0, 0.0]}, "embedding-3")
        monkeypatch.setattr(_recall, "SCRIPT_DIR", str(tmp_path))
        monkeypatch.setenv("ZHIPU_API_KEY", "zk")
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "embed", lambda *a, **kw: [1.0, 0.0, 0.0])
        results = _recall._embedding_recall("测试")
        assert results and results[0][1] > 0.9  # 同向向量余弦相似度 ≈ 1
