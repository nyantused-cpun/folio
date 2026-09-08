# -*- coding: utf-8 -*-
import pytest
"""P3「基础设施/云端」批回归测试（全库审查报告 2026-09-06 §五）。

覆盖：_semantic_catalog 绝对路径（P3-1）/ web_search 双 key 判定（P3-5）/
.cn 域后缀匹配（P3-6）/ _backup 清理失败告警（P3-7）。
全程 stub _post_json，不触真实网络。
"""

import os

import _backup
import _cloud_llm  # noqa: F401 须先于 _cloud_llm_search 导入（后者被前者尾部 re-export，反向导入成环）
import _paths
import _semantic_catalog
import _cloud_llm_search as search_mod


# ============================================================
# P3-1 _semantic_catalog：DEFAULT_CATALOG_PATH 绝对路径（_paths 单一数据源）
# ============================================================
class TestCatalogPathSingleSource:
    def test_default_path_is_absolute_in_script_dir(self):
        p = _semantic_catalog.DEFAULT_CATALOG_PATH
        assert os.path.isabs(p), "默认目录路径不应依赖 cwd"
        assert p.startswith(_paths.SCRIPT_DIR), "应从 _paths.SCRIPT_DIR 拼接"

    def test_load_catalog_cwd_independent(self, tmp_path, monkeypatch):
        """从任意 cwd 加载真实目录都不再「能力目录不存在」（旧相对路径病灶）。"""
        monkeypatch.chdir(tmp_path)
        catalog = _semantic_catalog.load_catalog()
        assert "error" not in catalog, catalog.get("error")
        assert catalog.get("schema_version") == "1"


# ============================================================
# P3-5 web_search 可用性判定与 byte_search 双 key 门禁同口径
# ============================================================
_BYTE_PAYLOAD = ({"Result": {"WebResults": [
    {"Title": "t1", "Url": "https://example.com/a", "Summary": "s1", "RankScore": 2.0},
]}}, 200)


def _clear_engine_keys(monkeypatch):
    for env in ("TAVILY_API_KEY", "ASK_ECHO_SEARCH_INFINITY_API_KEY",
                "VOLCENGINE_ACCESS_KEY", "VOLCENGINE_SECRET_KEY"):
        monkeypatch.delenv(env, raising=False)


class TestByteSearchAvailability:
    def test_partial_keys_not_deemed_available(self, monkeypatch, capsys):
        """只配 AK（无 SK、无 api_key）：旧 any() 误判可用，实际调用才报未配置。"""
        _clear_engine_keys(monkeypatch)
        monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak-only")
        calls = []

        def _must_not_call(*a, **k):
            calls.append(1)
            return _BYTE_PAYLOAD

        monkeypatch.setattr(search_mod, "_post_json", _must_not_call)
        result = search_mod.web_search("查询")
        assert result is None
        assert calls == [], "半配置 key 不应把 byte_search 列为可用并发起调用"
        assert "未配置任何搜索引擎 key" in capsys.readouterr().out

    def test_dual_keys_deemed_available(self, monkeypatch):
        _clear_engine_keys(monkeypatch)
        monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
        monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
        monkeypatch.setattr(search_mod, "_post_json", lambda *a, **k: _BYTE_PAYLOAD)
        result = search_mod.web_search("查询")
        assert result and result[0]["url"] == "https://example.com/a"

    def test_api_key_alone_deemed_available(self, monkeypatch):
        _clear_engine_keys(monkeypatch)
        monkeypatch.setenv("ASK_ECHO_SEARCH_INFINITY_API_KEY", "api-key")
        seen = {}

        def _fake_post(url, *a, **k):
            seen["url"] = url
            return _BYTE_PAYLOAD

        monkeypatch.setattr(search_mod, "_post_json", _fake_post)
        result = search_mod.web_search("查询")
        assert result
        assert "feedcoopapi" in seen["url"], "api_key 通道应走 Search Infinity 接口"


# ============================================================
# P3-6 .cn 加权改域后缀匹配（urlparse hostname endswith）
# ============================================================
def _tavily_payload(url_scores):
    return ({"results": [
        {"title": "t", "url": u, "content": "c", "score": s} for u, s in url_scores
    ]}, 200)


def _run_web_search(monkeypatch, url_scores):
    _clear_engine_keys(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(search_mod, "_post_json",
                        lambda *a, **k: _tavily_payload(url_scores))
    return search_mod.web_search("查询")


class TestCnDomainSuffixBonus:
    def test_real_cn_domain_no_bonus(self, monkeypatch):
        result = _run_web_search(monkeypatch, [("https://www.gov.cn/news", 1.0)])
        assert result[0]["score"] == 1.0, ".cn 域名不应加英文加权"

    def test_substring_cn_not_treated_as_domain(self, monkeypatch):
        """*.cn.example.com 含子串 ".cn" 但域后缀是 .com：应拿加权（旧子串匹配漏加）。"""
        result = _run_web_search(monkeypatch, [("https://abc.cn.example.com/page", 1.0)])
        assert result[0]["score"] == 1.1

    def test_com_domain_gets_bonus(self, monkeypatch):
        result = _run_web_search(monkeypatch, [("https://example.com/a", 1.0)])
        assert result[0]["score"] == 1.1


# ============================================================
# P3-7 _backup 清理旧版本失败：中文告警留痕，不中止主流程
# ============================================================
class TestBackupCleanupWarning:
    def _prepare(self, tmp_path, old_versions=4):
        f = tmp_path / "doc.html"
        f.write_text("内容", encoding="utf-8")
        versions = tmp_path / ".versions"
        versions.mkdir()
        for i in range(old_versions):
            (versions / f"doc.html.2026010{i}_000000").write_text("old", encoding="utf-8")
        return f, versions

    def test_cleanup_failure_warns_not_abort(self, tmp_path, monkeypatch, capsys):
        f, _versions = self._prepare(tmp_path)

        def _boom(path):
            raise OSError("文件被占用")

        monkeypatch.setattr(_backup.os, "remove", _boom)
        bak = _backup.backup_before_generate(str(f), max_versions=2)
        assert bak == str(f) + ".bak", "清理失败不应中止备份主流程"
        out = capsys.readouterr().out
        assert "旧版本清理失败" in out, "失败应中文告警留痕"

    def test_cleanup_success_removes_oldest(self, tmp_path, capsys):
        f, versions = self._prepare(tmp_path)
        bak = _backup.backup_before_generate(str(f), max_versions=2)
        assert bak is not None
        remaining = [p.name for p in versions.iterdir() if p.name.startswith("doc.html.")]
        assert len(remaining) == 2, "4 旧 + 1 新 = 5，应只保留最近 2 版"
        assert "旧版本清理失败" not in capsys.readouterr().out


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
