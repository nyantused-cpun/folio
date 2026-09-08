# -*- coding: utf-8 -*-
"""M1 F0 CLI 验证链 fail-closed（F0-1..F0-15）测试。

故障注入三例：
- verify 崩溃 -> 生成命令 exit != 0
- review FAIL/ERROR -> 生成命令 exit == 2
- 并发 save + theme-guard 写锁无丢更新（save_lock）
全部使用 monkeypatch / tmp_path，不依赖真实客户数据/网络。
"""

import json
import os
import sys
import threading

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


def _run_main(argv, monkeypatch):
    """调用 _cli.main()，返回退出码（成功无 SystemExit 返回 None / 0）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return 0
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _write_spec(tmp_path, pages=None, confirmed=True, client_name=None, tax_rate=None):
    import yaml
    spec = {
        "confirmed": confirmed,
        "document": {"title": "F0 测试文档"},
        "pages": pages or [],
    }
    if tax_rate is not None:
        spec["tax_rate"] = tax_rate
    if client_name is not None:
        spec["client_name"] = client_name
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    if confirmed:
        import hashlib
        import json
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        sidecar = tmp_path / "spec.confirm.json"
        sidecar.write_text(json.dumps({"spec_sha256": digest}),
                           encoding="utf-8")
    return str(p)


def _mock_generate_pipeline(monkeypatch):
    """mock 生成链路外围，保留真实 Renderer 渲染。"""
    import _cli_generate
    monkeypatch.setattr(_cli_generate, "_run_pre_check",
                        lambda client_name=None: {"ok": True})
    monkeypatch.setattr(_cli_generate, "_run_post_check", lambda *a, **k: None)
    monkeypatch.setattr("_renderer.html_editor_injector.inject", lambda *a, **k: None)
    # F3-2 起 html-build/docx-build/pptd-build 以 return_blocked=True 消费
    # blocked_coverage，桩返回 (ok, blocked_coverage) 元组（布尔语境下等价 True）。
    monkeypatch.setattr("_verify_hook.run_single", lambda *a, **k: (True, []))
    monkeypatch.setattr(_cli_generate, "_auto_review",
                        lambda *a, **k: {"verdict": "PASS", "issues": [], "summary": "ok"})


# ============================================================
# F0-1：不再因 confirmed 自动跳过；--skip-review 显式跳过；FAIL/ERROR exit 2
# ============================================================
class TestF0_1AutoReviewSkip:
    def test_confirmed_spec_does_not_auto_skip_by_default(self, tmp_path, monkeypatch):
        """confirmed=true + 无禁用词也不再自动 SKIP，必须显式 --skip-review。"""
        from _cli_guards import _auto_review
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        spec = _write_spec(tmp_path, pages=[{"title": "页", "elements": []}])
        calls = {"n": 0}

        def fake_review(**kw):
            calls["n"] += 1
            return {"verdict": "PASS", "issues": [], "summary": "ok"}

        monkeypatch.setattr("_review.review", fake_review)
        r = _auto_review(str(out), client_name=None, spec_path=spec)
        assert calls["n"] == 1
        assert r["verdict"] == "PASS"

    def test_explicit_skip_review_writes_skip_without_llm(self, tmp_path, monkeypatch):
        from _cli_guards import _auto_review
        out = tmp_path / "out.html"
        out.write_text("<html></html>", encoding="utf-8")
        calls = {"n": 0}
        monkeypatch.setattr("_review.review", lambda **kw: calls.__setitem__("n", calls["n"] + 1) or {"verdict": "PASS"})
        monkeypatch.setattr("_review.write_review_log", lambda *a, **k: None)
        spec = _write_spec(tmp_path, pages=[])
        r = _auto_review(str(out), client_name="测试客户F0", spec_path=spec, skip_review=True)
        assert calls["n"] == 0
        assert r["verdict"] == "SKIP"

    def test_html_build_review_fail_exits_2(self, monkeypatch, tmp_path):
        """生成链 review FAIL -> exit 2。"""
        import _cli_generate
        out_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_review_fail")
        os.makedirs(out_dir, exist_ok=True)
        try:
            spec = _write_spec(tmp_path, pages=[{"id": "p1", "title": "页", "elements": [
                {"type": "text", "content": "内容"}]}])
            _mock_generate_pipeline(monkeypatch)
            monkeypatch.setattr(_cli_generate, "_auto_review",
                                lambda *a, **k: {"verdict": "FAIL", "issues": ["x"], "summary": "bad"})
            out = os.path.join(out_dir, "a.html")
            code = _run_main(["_cli.py", "html-build", spec, out, "--html-only"], monkeypatch)
            assert code == 2
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_html_build_review_error_exits_2(self, monkeypatch, tmp_path):
        """生成链 review ERROR/None -> exit 2。"""
        import _cli_generate
        out_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_review_error")
        os.makedirs(out_dir, exist_ok=True)
        try:
            spec = _write_spec(tmp_path, pages=[{"id": "p1", "title": "页", "elements": [
                {"type": "text", "content": "内容"}]}])
            _mock_generate_pipeline(monkeypatch)
            monkeypatch.setattr(_cli_generate, "_auto_review", lambda *a, **k: None)
            out = os.path.join(out_dir, "a.html")
            code = _run_main(["_cli.py", "html-build", spec, out, "--html-only"], monkeypatch)
            assert code == 2
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)


# ============================================================
# F0-3/F0-4：verify 返回值接收 + 异常 fail-closed exit 1
# ============================================================
class TestF0_3F0_4VerifyFailClosed:
    def _run_spec_gen(self, tmp_path, monkeypatch, verify_result):
        import _cli_generate
        import _outline_to_spec
        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda **kw: {"ok": True})
        out_path = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_spec_gen_verify.yml")

        def fake_build(scene, files, client_name="", output_path=None):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("confirmed: true\n")
            return output_path

        monkeypatch.setattr(_outline_to_spec, "build_spec_from_outline", fake_build)
        monkeypatch.setattr("_verify_hook.run_single", verify_result)
        return out_path

    def test_spec_gen_verify_false_exits_1(self, monkeypatch, tmp_path, capsys):
        out_path = self._run_spec_gen(tmp_path, monkeypatch, lambda *a, **k: False)
        try:
            code = _run_main(
                ["_cli.py", "spec-gen", str(tmp_path / "m.txt"), "--output", out_path],
                monkeypatch)
            assert code == 1
            assert "verify 失败" in capsys.readouterr().out
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

    def test_spec_gen_verify_crash_exits_1(self, monkeypatch, tmp_path, capsys):
        def boom(*a, **k):
            raise RuntimeError("崩溃")
        out_path = self._run_spec_gen(tmp_path, monkeypatch, boom)
        try:
            code = _run_main(
                ["_cli.py", "spec-gen", str(tmp_path / "m.txt"), "--output", out_path],
                monkeypatch)
            assert code == 1
            assert "无法验证" in capsys.readouterr().out
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

    def test_html_build_verify_crash_exits_1(self, monkeypatch, tmp_path):
        """故障注入：html-build verify 崩溃 -> 非零退出。"""
        out_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_verify_crash")
        os.makedirs(out_dir, exist_ok=True)
        try:
            spec = _write_spec(tmp_path, pages=[{"id": "p1", "title": "页", "elements": [
                {"type": "text", "content": "内容"}]}])
            _mock_generate_pipeline(monkeypatch)
            monkeypatch.setattr("_verify_hook.run_single",
                                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("verify crash")))
            out = os.path.join(out_dir, "a.html")
            code = _run_main(["_cli.py", "html-build", spec, out, "--html-only"], monkeypatch)
            assert code == 1
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_quote_build_verify_crash_exits_1(self, monkeypatch, tmp_path):
        """故障注入：quote-build verify 崩溃 -> 非零退出。"""
        import _cli_generate
        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda **kw: {"ok": True})
        spec = _write_spec(tmp_path, pages=[], tax_rate=0.06)
        out_base = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_quote_crash")

        class _QB:
            def build(self, spec):
                return object()
        monkeypatch.setattr("_quote_data.QuoteBuilder", _QB)
        monkeypatch.setattr("_quote_html.render_html", lambda *a, **k: None)

        def boom(*a, **k):
            raise RuntimeError("verify crash")
        monkeypatch.setattr("_verify_hook.run_single", boom)

        try:
            code = _run_main(["_cli.py", "quote-build", spec, out_base, "--format", "html"], monkeypatch)
            assert code == 1
        finally:
            for ext in (".html", ".xlsx"):
                p = out_base + ext
                if os.path.exists(p):
                    os.remove(p)


# ============================================================
# F0-5：_run_post_check critical 缺失 exit2 / 无主题 exit1
# ============================================================
class TestF0_5PostCheckFailClosed:
    def test_critical_missing_exits_2(self, tmp_path, monkeypatch):
        import _theme_guard
        import _cli_guards
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        monkeypatch.setattr(_theme_guard, "pre_check",
                            lambda client: {"themes": [{"theme": "铁律", "priority": "critical"}]})
        monkeypatch.setattr(_theme_guard, "check_coverage",
                            lambda text, themes: {"covered": [], "missing": [{"theme": "铁律", "priority": "critical"}], "warnings": []})
        with pytest.raises(SystemExit) as e:
            _cli_guards._run_post_check(str(out), client_name="测试客户")
        assert e.value.code == 2

    def test_no_themes_exits_1(self, tmp_path, monkeypatch):
        import _theme_guard
        import _cli_guards
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        monkeypatch.setattr(_theme_guard, "pre_check", lambda client: {"themes": []})
        with pytest.raises(SystemExit) as e:
            _cli_guards._run_post_check(str(out), client_name="测试客户")
        assert e.value.code == 1


# ============================================================
# F0-2：audit review_log FAIL/ERROR 检查
# ============================================================
class TestF0_2AuditReviewLog:
    def _make_review_log(self, tmp_path, monkeypatch, entries):
        import _cli_audit
        log_dir = tmp_path / ".folio" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "review_log.json").write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_cli_audit, "_REVIEW_LOG", str(log_dir / "review_log.json"))
        return _cli_audit._audit_review_log

    def test_fail_latest_makes_audit_fail(self, tmp_path, monkeypatch):
        fn = self._make_review_log(tmp_path, monkeypatch, [
            {"verdict": "PASS", "client": "A", "file": "a.html", "issues": []},
            {"verdict": "FAIL", "client": "A", "file": "b.html", "issues": ["x"]},
        ])
        assert fn(client_name="A") is False

    def test_latest_pass_overrides_earlier_fail(self, tmp_path, monkeypatch):
        fn = self._make_review_log(tmp_path, monkeypatch, [
            {"verdict": "FAIL", "client": "A", "file": "a.html", "issues": ["x"]},
            {"verdict": "PASS", "client": "A", "file": "b.html", "issues": []},
        ])
        assert fn(client_name="A") is True


# ============================================================
# F0-6：run_single 暴露 blocked_coverage（含 degraded）
# ============================================================
class TestF0_6BlockedCoverage:
    def test_return_blocked_contains_coverage_missing(self, tmp_path, monkeypatch):
        import _verify_hook
        import _theme_guard
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        monkeypatch.setattr("_verify.auto_verify", lambda path, client_name="", **_kw: (True, "ok"))
        monkeypatch.setattr(_verify_hook, "write_log", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_print_result", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "update_task_history", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_auto_snippet_capture", lambda *a, **k: None)
        monkeypatch.setattr(_theme_guard, "pre_check",
                            lambda client: {"themes": [{"theme": "铁律"}]})
        monkeypatch.setattr(_theme_guard, "check_coverage",
                            lambda text, themes: {"covered": [], "missing": [{"theme": "铁律", "priority": "high"}], "warnings": []})
        ok, blocked = _verify_hook.run_single(
            str(out), client_name="测试客户", return_blocked=True)
        assert ok is True
        assert any(m.get("theme") == "铁律" for m in blocked)

    def test_degraded_included_in_blocked_coverage(self, tmp_path, monkeypatch):
        import _verify_hook
        from _renderer.elements import RenderReport
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        monkeypatch.setattr("_verify.auto_verify", lambda path, client_name="", **_kw: (True, "ok"))
        monkeypatch.setattr(_verify_hook, "write_log", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_print_result", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "update_task_history", lambda *a, **k: None)
        monkeypatch.setattr(_verify_hook, "_auto_snippet_capture", lambda *a, **k: None)
        report = RenderReport()
        report.degrade("p1", 0, "diagram", "docx", "降级说明")
        ok, blocked = _verify_hook.run_single(
            str(out), client_name=None, render_report=report, return_blocked=True)
        assert ok is True
        assert any(b.get("type") == "diagram" for b in blocked)


# ============================================================
# F0-7：cite-audit --strict exit2；deliver 强制 strict
# ============================================================
class TestF0_7CiteAuditStrict:
    def _spec_with_missing_source(self, tmp_path):
        spec = {
            "pages": [{
                "title": "页",
                "elements": [{"type": "text", "content": "正文"}],
                "evidence": [{"source": "__no_such_file__.md", "snippet": "x"}],
            }]
        }
        import yaml
        p = tmp_path / "spec.yml"
        p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        return str(p)

    def test_strict_missing_source_exits_2(self, monkeypatch, tmp_path):
        spec = self._spec_with_missing_source(tmp_path)
        code = _run_main(["_cli.py", "cite-audit", spec, "--strict",
                          "--output", os.path.join(SCRIPT_DIR, "output", "通用", "_f0_cite.md")],
                         monkeypatch)
        assert code == 2

    def test_non_strict_missing_source_does_not_exit_2(self, monkeypatch, tmp_path):
        spec = self._spec_with_missing_source(tmp_path)
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_cite_non_strict.md")
        try:
            code = _run_main(["_cli.py", "cite-audit", spec, "--output", out], monkeypatch)
            assert code == 0
        finally:
            if os.path.exists(out):
                os.remove(out)

    def test_deliver_forces_cite_strict(self, monkeypatch, tmp_path):
        import subprocess
        out_html = os.path.join(SCRIPT_DIR, "output", "通用", "_f0_deliver_v1.html")
        pptd_dir = os.path.splitext(out_html)[0]
        os.makedirs(pptd_dir, exist_ok=True)
        with open(os.path.join(pptd_dir, "deck.pptd"), "w", encoding="utf-8") as f:
            f.write("fake")
        calls = []

        def fake_call(cmd, **kw):
            calls.append(cmd)
            return 0

        monkeypatch.setattr(subprocess, "call", fake_call)
        spec = _write_spec(tmp_path, pages=[])
        try:
            code = _run_main(
                ["_cli.py", "deliver", spec, out_html, "--client", "通用"], monkeypatch)
            assert code == 0
        finally:
            import shutil
            # 只清理本测试专属产物目录/文件，不能 rmtree(父目录 output/通用/)
            shutil.rmtree(pptd_dir, ignore_errors=True)
            if os.path.exists(out_html):
                os.remove(out_html)
        cite_calls = [c for c in calls if "cite-audit" in c]
        assert cite_calls
        assert "--strict" in cite_calls[0]


# ============================================================
# F0-8：save_decision + update_task_history 共用 .save_lock，并发无丢更新
# ============================================================
class TestF0_8SaveLockWrites:
    def test_save_decision_and_update_history_no_lock_residue(self, tmp_path, monkeypatch):
        import _theme_guard
        import _verify_hook
        clients = tmp_path / "clients"
        clients.mkdir()
        task_history = tmp_path / "task_history.json"
        monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_verify_hook, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_verify_hook, "TASK_HISTORY", str(task_history))
        # 隔离守卫：update_task_history 内部会 write_log，LOGS_DIR 必须一并隔离，
        # 否则真实 .folio/logs/verify_LOG_*.log 被测试污染（2026-08-30 实证）
        monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(tmp_path / "logs"))
        task_history.write_text(json.dumps([{"project": "client:测试客户F0", "verify": {}}]),
                                encoding="utf-8")

        _theme_guard.save_decision("测试客户F0", "并发决策", "值1")
        _verify_hook.update_task_history(
            str(tmp_path / "out.html"), True, "html", client_name="测试客户F0")
        assert not (clients / "测试客户F0" / ".save_lock").exists()
        assert "并发决策" in (clients / "测试客户F0" / "decisions.md").read_text(encoding="utf-8")
        assert os.path.exists(task_history)

    def test_save_decision_lock_failure_returns_none_and_no_write(self, tmp_path, monkeypatch, capsys):
        import _theme_guard
        import _save_lock
        clients = tmp_path / "clients"
        clients.mkdir()
        monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_save_lock, "acquire_save_lock",
                            lambda client_dir, **kw: None)
        result = _theme_guard.save_decision("测试客户F0", "锁失败主题", "内容")
        assert result is None
        assert not (clients / "测试客户F0" / "decisions.md").exists()
        assert "获取保存锁失败" in capsys.readouterr().out

    def test_concurrent_save_and_theme_guard_writes_all(self, tmp_path, monkeypatch):
        """并发 save_decision 多线程同时在 decisions.md 追加，锁保证不丢更新。"""
        import _theme_guard
        import _verify_hook
        clients = tmp_path / "clients"
        clients.mkdir()
        task_history = tmp_path / "task_history.json"
        monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_verify_hook, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_verify_hook, "TASK_HISTORY", str(task_history))
        # 隔离守卫：同上，write_log 走真实 LOGS_DIR 会污染真实 verify 日志
        monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(tmp_path / "logs"))
        (clients / "测试客户F0").mkdir(exist_ok=True)
        task_history.write_text(json.dumps([{"project": "client:测试客户F0", "verify": {}}]),
                                encoding="utf-8")

        errors = []
        barrier = threading.Barrier(2)

        def writer_decisions():
            try:
                barrier.wait()
                for i in range(5):
                    _theme_guard.save_decision("测试客户F0", f"决策{i}", f"内容{i}")
            except Exception as e:  # pragma: no cover - only for failure visibility
                errors.append(e)

        def writer_history():
            try:
                barrier.wait()
                for i in range(5):
                    _verify_hook.update_task_history(
                        str(tmp_path / f"out{i}.html"), True, "html", client_name="测试客户F0")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        t1 = threading.Thread(target=writer_decisions)
        t2 = threading.Thread(target=writer_history)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        assert not (clients / "测试客户F0" / ".save_lock").exists()
        dec = (clients / "测试客户F0" / "decisions.md").read_text(encoding="utf-8")
        assert dec.count("## [") == 5
        history = json.loads(task_history.read_text(encoding="utf-8"))
        assert len(history[-1].get("verify", {})) == 5


# ============================================================
# F0-9/F0-12：session-start 降级 [warn] + usage_summary；audit 本月用量
# ============================================================
class TestF0_9F0_12SessionStart:
    def test_json_has_recall_degraded_warn_and_usage_summary(self, monkeypatch, capsys, tmp_path):
        import _cli
        fake = {
            "level": "L4", "mode": "collaborative", "context_summary": "x",
            "client_index": "", "recall": [
                {"client": "A", "score": 0.9, "path": "x", "snippet": "",
                 "degraded": True}
            ],
            "warnings": [], "head_context": "", "tail_checklist": "",
            "recent_task_decisions": [],
        }
        monkeypatch.setattr("_cli_cmds_qa.auto_for_input", lambda *a, **kw: fake)
        monkeypatch.setattr("_cloud_llm.get_usage_summary",
                            lambda *a, **kw: {"total_calls": 3, "total_tokens": 100, "by_provider": {}})
        args = type("A", (), {"client": None, "json": True, "input": "x"})()
        _cli.cmd_session_start(args)
        payload = json.loads(capsys.readouterr().out)
        assert payload["recall_degraded"] is True
        assert any("召回链路存在降级" in w for w in payload["warnings"])
        assert payload["usage_summary"]["total_calls"] == 3

    def test_text_prints_degraded_warn(self, monkeypatch, capsys):
        import _cli
        fake = {
            "level": "L4", "mode": "collaborative", "context_summary": "x",
            "client_index": "", "recall": [{"client": "A", "score": 0.9, "path": "x",
                                            "snippet": "", "degraded": True}],
            "warnings": [], "head_context": "", "tail_checklist": "",
            "recent_task_decisions": [],
        }
        monkeypatch.setattr("_cli_cmds_qa.auto_for_input", lambda *a, **kw: fake)
        monkeypatch.setattr("_cloud_llm.get_usage_summary", lambda *a, **kw: {})
        args = type("A", (), {"client": None, "json": False, "input": "x"})()
        _cli.cmd_session_start(args)
        out = capsys.readouterr().out
        assert "[warn] 召回链路存在降级" in out

    def test_audit_prints_monthly_usage(self, monkeypatch, capsys, tmp_path):
        import json as _json

        import _cli_audit
        from types import SimpleNamespace
        # 封闭化：不依赖仓库真实 review 状态（历史 FAIL 会误伤本测试），
        # 用临时 review_log 的 PASS 记录验证「audit --mode review 打印用量」本身。
        log = tmp_path / "review_log.json"
        log.write_text(_json.dumps([{"verdict": "PASS", "file": "demo.html"}]),
                       encoding="utf-8")
        monkeypatch.setattr(_cli_audit, "_REVIEW_LOG", str(log))
        monkeypatch.setattr("_cloud_llm.get_usage_summary",
                            lambda *a, **kw: {"total_calls": 7, "total_tokens": 700,
                                              "by_provider": {"mock": {"calls": 7, "tokens": 700}}})
        code = None
        try:
            _cli_audit.cmd_audit(SimpleNamespace(mode="review", client=None))
        except SystemExit as e:
            code = e.code
        out = capsys.readouterr().out
        assert code == 0
        assert "本月 LLM 用量" in out


# ============================================================
# F0-10：handoff 死代码删除
# ============================================================
class TestF0_10HandoffRemoved:
    def test_no_handoff_symbols(self):
        import _cli
        import _session
        assert "handoff" not in _cli._DEPRECATED
        assert not hasattr(_session, "generate_handoff_packet")
        assert not hasattr(_session, "check_handoff_packet")

    def test_session_start_no_handoff_consumer(self):
        import _cli
        import inspect
        src = inspect.getsource(_cli.cmd_session_start)
        assert "handoff_packet" not in src
        assert "generate_handoff_packet" not in src


# ============================================================
# F0-11：save 前 context.md 超 200 行自动 compact
# ============================================================
class TestF0_11SaveAutoCompact:
    def test_save_calls_compact_when_context_over_limit(self, tmp_path, monkeypatch):
        import _session
        import _context
        import _theme_guard
        import _aliases
        clients = tmp_path / "clients"
        clients.mkdir()
        d = clients / "测试客户F0"
        d.mkdir(parents=True)
        ctx = d / "context.md"
        ctx.write_text("# 项目上下文\n\n" + "\n".join(f"line {i}" for i in range(220)),
                       encoding="utf-8")
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
        calls = {"n": 0}
        monkeypatch.setattr(_session, "compact", lambda client, **kw: calls.__setitem__("n", calls["n"] + 1))
        monkeypatch.setattr(_session, "update_outputs_index", lambda *a, **k: 0)
        _session.save_session("测试客户F0", input_desc="test", light=True)
        assert calls["n"] == 1


# ============================================================
# F0-13：pre-sales preset 注入 REQUIRE_SKILL_SENTINEL=1
# ============================================================
class TestF0_13SkillSentinelPreset:
    def test_preset_bootstrap_injects_sentinel(self):
        boot = os.path.join(SCRIPT_DIR, ".dsh", "preset", "pre-sales", "tool-bootstrap.mjs")
        with open(boot, "r", encoding="utf-8") as f:
            src = f.read()
        assert "REQUIRE_SKILL_SENTINEL" in src
        assert "= '1'" in src or "= \"1\"" in src


# ============================================================
# F0-14：review prompt 防 monitor evasion 判据
# ============================================================
class TestF0_14ReviewPromptAntiGaming:
    def test_review_prompt_contains_anti_evasion(self, monkeypatch, tmp_path):
        import _review
        out = tmp_path / "out.html"
        out.write_text("<html><body>内容</body></html>", encoding="utf-8")
        captured = {}

        def fake_chat(prompt, **kw):
            captured["prompt"] = prompt
            return json.dumps({"verdict": "PASS", "issues": [], "summary": "ok"})

        monkeypatch.setattr("_cloud_llm.chat", fake_chat)
        monkeypatch.setattr("_cloud_llm.LLM_MODE", "api")
        monkeypatch.setattr("_review.write_review_log", lambda *a, **k: None)
        _review.review(str(out), quiet=True)
        assert "防 monitor evasion" in captured["prompt"]
        assert "gaming" in captured["prompt"]


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
