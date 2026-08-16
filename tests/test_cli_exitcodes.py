# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""错误路径退出码回归测试。

背景：多个命令的错误路径曾是 print 错误信息后裸 return（exit 0），
自动化 Hook / AI 无法凭退出码判断失败。修复后统一：错误路径 exit != 0，
review 判 FAIL exit 2。
"""

import os
import sys

import pytest


def _run_main(argv, monkeypatch):
    """以给定 argv 调用 _cli.main()，断言其抛出 SystemExit 并返回退出码。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    # main() 会置 _PRESALES_CLI_INVOKED=1；手动保存/还原，避免污染其他测试
    # （monkeypatch.delenv 对不存在的变量不记录还原点，事后赋值会泄漏）
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        with pytest.raises(SystemExit) as exc_info:
            _cli.main()
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved
    return exc_info.value.code


def _run_main_allow_success(argv, monkeypatch):
    """同 _run_main，但允许成功路径（无 SystemExit 时返回 None）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


class TestErrorExitCodes:
    """错误路径必须非 0 退出。"""

    def test_graph_query_unknown_client_exits_1(self, monkeypatch):
        code = _run_main(["_cli.py", "graph-query", "不存在的客户xyz"], monkeypatch)
        assert code == 1

    def test_style_check_missing_file_exits_1(self, monkeypatch):
        code = _run_main(["_cli.py", "style-check", "不存在的文件xyz.html"], monkeypatch)
        assert code == 1

    def test_chunk_read_missing_file_exits_1(self, monkeypatch):
        code = _run_main(["_cli.py", "chunk-read", "不存在的文件xyz.md#1"], monkeypatch)
        assert code == 1

    def test_theme_guard_task_scope_without_task_id_exits_1(self, monkeypatch):
        code = _run_main(
            ["_cli.py", "theme-guard", "通用", "--set", "测试主题", "--scope", "task"],
            monkeypatch,
        )
        assert code == 1

    def test_review_missing_file_exits_1(self, monkeypatch):
        code = _run_main(["_cli.py", "review", "不存在的文件xyz.html"], monkeypatch)
        assert code == 1

    def test_review_fail_verdict_exits_2(self, monkeypatch, tmp_path):
        out = tmp_path / "a.html"
        out.write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr("_review.review", lambda **kw: {"verdict": "FAIL"})
        code = _run_main(["_cli.py", "review", str(out)], monkeypatch)
        assert code == 2

    def test_embed_rebuild_without_key_exits_1(self, monkeypatch):
        """缺 ZHIPU_API_KEY 时应 fail-fast（曾空跑数百批无效重试）。

        置空而非删除：import 时 _load_dotenv 会把 .env 里的 key 重新填入
        不存在的环境变量；空串不会被覆盖，且在检查中为 falsy。
        """
        monkeypatch.setenv("ZHIPU_API_KEY", "")
        monkeypatch.setenv("GLM_API_KEY", "")
        monkeypatch.setenv("SILICONFLOW_API_KEY", "")  # P1 起 SF 也是有效 provider，必须一并置空
        code = _run_main(["_cli.py", "embed-rebuild"], monkeypatch)
        assert code == 1


class TestKeyDoctor:
    """key-doctor：来源表 + 双源冲突提示 + key 脱敏。"""

    def test_lists_keys_and_masks_value(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".env").write_text(
            'ZHIPU_API_KEY="test-key-abcdef1234567890"\n', encoding="utf-8")
        monkeypatch.setattr("_cli_audit.SCRIPT_DIR", str(tmp_path))
        monkeypatch.delenv("ZHIPU_API_KEY", raising=False)  # 让 .env 生效
        # delenv 对已存在变量会正确还原，但 import 阶段 _load_dotenv 可能已注入，确保干净
        os.environ.pop("ZHIPU_API_KEY", None)
        code = _run_main_allow_success(["_cli.py", "key-doctor", "--no-probe"], monkeypatch)
        assert code in (None, 0)
        out = capsys.readouterr().out
        assert "ZHIPU_API_KEY" in out
        assert "test-k***7890" in out
        assert "test-key-abcdef1234567890" not in out  # 完整 key 不回显

    def test_conflict_warn_when_env_differs_from_dotenv(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".env").write_text(
            'ZHIPU_API_KEY="old-stale-key-000000"\n', encoding="utf-8")
        monkeypatch.setattr("_cli_audit.SCRIPT_DIR", str(tmp_path))
        monkeypatch.setenv("ZHIPU_API_KEY", "new-env-key-111111")
        code = _run_main_allow_success(["_cli.py", "key-doctor", "--no-probe"], monkeypatch)
        assert code in (None, 0)
        out = capsys.readouterr().out
        assert "双源冲突" in out
        assert "old-stale-key-000000" not in out
        assert "new-env-key-111111" not in out


class TestParserDispatchConsistency:
    """parser 注册命令与 dispatch 必须一致（audit 曾硬编码 52 长期误报）。"""

    def test_parser_matches_dispatch(self):
        import _cli
        parser = _cli.build_parser()
        sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
        assert set(sub.choices.keys()) == set(_cli._build_dispatch().keys())

    def test_deprecated_count(self):
        import _cli
        assert len(_cli._DEPRECATED) == 22

    def test_handoff_deprecated_exits_1(self, monkeypatch, capsys):
        code = _run_main(["_cli.py", "handoff", "通用"], monkeypatch)
        assert code == 1
        assert "已废弃" in capsys.readouterr().out


class TestCompactBackup:
    """compact 截断 task_history 前必须留 .bak（曾无备份不可恢复）。"""

    def test_compact_creates_bak_and_truncates(self, monkeypatch, tmp_path):
        import json
        import _paths
        clients = tmp_path / "clients"
        logs = tmp_path / "logs"
        (clients / "测试客户").mkdir(parents=True)
        logs.mkdir()
        hist = [{"project": "client:测试客户", "n": i} for i in range(15)]
        (logs / "task_history.json").write_text(json.dumps(hist), encoding="utf-8")
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_paths, "LOGS_DIR", str(logs))
        code = _run_main_allow_success(["_cli.py", "compact", "测试客户", "--keep", "10"], monkeypatch)
        assert code in (None, 0)
        assert (logs / "task_history.json.bak").exists()
        kept = json.loads((logs / "task_history.json").read_text(encoding="utf-8"))
        assert len(kept) == 10


class TestHtmlToPptGuards:
    """html-to-ppt 与其他生成命令同一防护链（曾无 pre_check / 无白名单 / verify 不阻断）。"""

    def test_missing_input_exits_1(self, monkeypatch):
        code = _run_main(
            ["_cli.py", "html-to-ppt", "不存在的文件.html", "output/通用/x.pptx"], monkeypatch)
        assert code == 1

    def test_output_outside_whitelist_blocked(self, monkeypatch, tmp_path):
        html = tmp_path / "in.html"
        html.write_text(
            "<html><body><div class='ppt-page'>x</div></body></html>", encoding="utf-8")
        code = _run_main(["_cli.py", "html-to-ppt", str(html), "C:/evil/x.pptx"], monkeypatch)
        assert code == 1


class TestWebSearchNoKey:
    """未配置搜索 key 时必须明说（曾伪装成'无结果'，AI 会据此回答用户'网上没有'）。"""

    def test_no_engine_explicit_message(self, monkeypatch, capsys):
        for var in ("TAVILY_API_KEY", "ASK_ECHO_SEARCH_INFINITY_API_KEY",
                    "VOLCENGINE_ACCESS_KEY", "VOLCENGINE_SECRET_KEY"):
            monkeypatch.setenv(var, "")
        from _cloud_llm import web_search
        assert web_search("测试") is None
        assert "未配置任何搜索引擎" in capsys.readouterr().out


class TestMinimaxConfig:
    """MiniMax 双平台：MINIMAX_BASE_URL 端点覆盖 + <think> 标签剥离。"""

    def test_base_url_env_override(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
        import importlib
        import _cloud_llm
        try:
            importlib.reload(_cloud_llm)
            assert _cloud_llm.PROVIDERS["minimax"]["base_url"] == "https://api.minimaxi.com/v1"
        finally:
            monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
            importlib.reload(_cloud_llm)

    def test_strip_think(self):
        from _cloud_llm import _strip_think
        assert _strip_think("<think>推理过程</think>\n正文") == "正文"
        assert _strip_think("没有标签") == "没有标签"
        assert _strip_think("") == ""
        assert _strip_think("<think>多行\n推理</think>  结果  ") == "结果"


class TestQuoteConfirmedGate:
    """quote-build 与 Renderer 同一 confirmed 门（此前可从未确认 spec 直接生成报价）。"""

    def _mk_spec(self, tmp_path, data):
        import yaml
        spec = tmp_path / "q.yml"
        spec.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return str(spec)

    def test_unconfirmed_spec_blocked(self, monkeypatch, tmp_path):
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        spec = self._mk_spec(tmp_path, {"client": "测试", "confirmed": False})
        code = _run_main(["_cli.py", "quote-build", spec, "output/通用/q"], monkeypatch)
        assert code == 1

    def test_missing_confirmed_field_blocked(self, monkeypatch, tmp_path):
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        spec = self._mk_spec(tmp_path, {"client": "测试"})
        code = _run_main(["_cli.py", "quote-build", spec, "output/通用/q"], monkeypatch)
        assert code == 1


class TestVisionDescribeJson:
    """vision-describe --format json：结构化输出带 source_image（进 spec 引用用）。"""

    def test_json_format_wraps_source(self, monkeypatch, tmp_path, capsys):
        img = tmp_path / "a.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")  # vision_chat 会被 mock，文件只需存在
        monkeypatch.setattr("_cli.vision_chat",
                            lambda *a, **kw: '{"summary": "一张测试图", "objects": ["矩形"]}')
        code = _run_main_allow_success(
            ["_cli.py", "vision-describe", str(img), "--format", "json"], monkeypatch)
        assert code in (None, 0)
        out = capsys.readouterr().out
        assert '"source_image"' in out
        assert "一张测试图" in out


class TestVisionCache:
    """P-vision-5：识图结果缓存——重复截图跳过上传。"""

    def test_cache_roundtrip(self, monkeypatch, tmp_path):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "VISION_CACHE", str(tmp_path / "vc.json"))
        _cloud_llm._vision_cache_put("k1", "描述1")
        assert _cloud_llm._vision_cache_get("k1") == "描述1"
        assert _cloud_llm._vision_cache_get("missing") is None

    def test_cache_lru_eviction(self, monkeypatch, tmp_path):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "VISION_CACHE", str(tmp_path / "vc.json"))
        counter = {"t": 0.0}

        def fake_time():
            counter["t"] += 1.0
            return counter["t"]

        monkeypatch.setattr(_cloud_llm.time, "time", fake_time)
        limit = _cloud_llm.VISION_CACHE_MAX_ENTRIES
        for i in range(limit + 5):
            _cloud_llm._vision_cache_put(f"k{i}", f"desc{i}")
        cache = _cloud_llm._vision_cache_load()
        assert len(cache) == limit
        for i in range(5):  # 最早的 5 条被淘汰
            assert f"k{i}" not in cache
        assert f"k{limit + 4}" in cache

    def test_vision_chat_cache_hit_skips_upload(self, monkeypatch, tmp_path):
        import hashlib
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "VISION_CACHE", str(tmp_path / "vc.json"))
        monkeypatch.setattr(_cloud_llm, "_get_api_key", lambda cfg, p="": "fake-key")

        def _fail_post(*a, **kw):
            raise AssertionError("缓存命中时不应发起网络请求")

        monkeypatch.setattr(_cloud_llm, "_post_json", _fail_post)
        img = tmp_path / "a.png"
        raw = b"\x89PNG\r\n\x1a\n"
        img.write_bytes(raw)
        key = hashlib.sha256(raw).hexdigest()
        _cloud_llm._vision_cache_put(key, "缓存描述")
        assert _cloud_llm.vision_chat("请描述", str(img)) == "缓存描述"


class TestOutputWhitelistCLI:
    """§八 3.5：输出白名单前置校验的 CLI 阻断路径（明确提示 + exit 1）。

    spec-gen / outline-to-spec 的默认输出在 cwd 根目录（spec_gen.yml /
    spec_draft.yml），不在 output/ 白名单内——选"明确提示"而非隐式改默认路径，
    故不传 --output 即被阻断。
    """

    def _mk_spec(self, tmp_path, data):
        import yaml
        spec = tmp_path / "spec.yml"
        spec.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return str(spec)

    def test_spec_gen_default_output_blocked(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        code = _run_main(["_cli.py", "spec-gen", str(tmp_path / "m.txt")], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_outline_to_spec_default_output_blocked(self, monkeypatch, capsys):
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        code = _run_main(["_cli.py", "outline-to-spec", "整体信息化规划"], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_quote_build_output_outside_blocked(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        spec = self._mk_spec(tmp_path, {"client": "测试", "confirmed": True})
        code = _run_main(
            ["_cli.py", "quote-build", spec, str(tmp_path / "q")], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_quote_spec_gen_output_outside_blocked(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr("_cli._run_pre_check", lambda **kw: {"ok": True})
        code = _run_main(
            ["_cli.py", "quote-spec-gen", str(tmp_path),
             str(tmp_path / "quote_spec.yml")], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_cite_audit_default_report_outside_blocked(self, monkeypatch, tmp_path, capsys):
        """cite-audit 默认报告跟随 spec 目录；spec 不在 output/ 下时阻断并提示。"""
        spec = self._mk_spec(tmp_path, {"pages": [{"title": "p", "elements": []}]})
        code = _run_main(["_cli.py", "cite-audit", spec], monkeypatch)
        assert code == 1
        assert "白名单" in capsys.readouterr().out

    def test_cite_audit_output_inside_allowed(self, monkeypatch, tmp_path):
        """--output 指向 output/ 下时正常落盘。"""
        import shutil
        from _cli_infra import SCRIPT_DIR
        out_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_cite_test")
        os.makedirs(out_dir, exist_ok=True)
        try:
            spec = self._mk_spec(tmp_path, {"pages": [{"title": "p", "elements": []}]})
            out = os.path.join(out_dir, "审查报告.md")
            code = _run_main_allow_success(
                ["_cli.py", "cite-audit", spec, "--output", out], monkeypatch)
            assert code in (None, 0)
            assert os.path.exists(out)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


class TestKeywordFallback:
    """recall 关键词降级链：缺 jieba 时降级路径不能再崩（曾二次 ImportError）。"""

    def test_fallback_works_without_bm25(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "_bm25", None)  # 模拟缺 jieba（_bm25 顶层 import jieba）
        from _recall import _keyword_fallback
        results = _keyword_fallback("报价", return_results=True)
        assert isinstance(results, list)

