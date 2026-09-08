# -*- coding: utf-8 -*-
"""B6 Wave1 审查管线止血回归（W1-1 / W1-2 / W1-4）。

全程 mock LLM、日志与预算文件路径（tmp_path 隔离），
不触真实 API、不读写真实 _knowledge/clients/ 数据。
"""

import json
import threading

import pytest

import _paths
import _review


def _make_output(tmp_path):
    out = tmp_path / "t.html"
    out.write_text("<html><body>正文内容</body></html>", encoding="utf-8")
    return str(out)


def _pass_payload():
    return json.dumps({
        "verdict": "PASS",
        "scores": {"设计": 3, "原创": 3, "工艺": 3, "功能": 3, "结构": 3, "总分": 15},
        "issues": [],
        "summary": "ok",
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# W1-1（#37）：review 初调 max_tokens 2000→3000 + task=post_generate_review
#（reasoning 降档本体在 _cloud_llm.TASK_THINKING_OVERRIDE，payload 级断言见
#  tests/test_cloud_llm.py::TestTaskThinkingOverride）
# ---------------------------------------------------------------------------
class TestW1ReviewCallSignature:
    def test_review_passes_review_task_and_max_tokens(self, monkeypatch, tmp_path):
        import _cloud_llm
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return _pass_payload()

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = _make_output(tmp_path)
        assert _review.review(out, quiet=True)["verdict"] == "PASS"
        assert captured.get("task") == "post_generate_review"
        assert captured.get("max_tokens") == 3000, "W1-1：2000→3000，effective 9000 拉开与 12000 重试线距离"


# ---------------------------------------------------------------------------
# W1-2：审查预算熔断——同日连续 3 次 ERROR 停止发起 LLM 调用，防白烧 token
# ---------------------------------------------------------------------------
class TestW1ReviewBudgetFuse:
    def _isolate(self, monkeypatch, tmp_path):
        """日志与预算状态文件全部 monkeypatch 到 tmp，不触真实 .folio/logs。"""
        monkeypatch.setattr(_paths, "REVIEW_LOG", str(tmp_path / "review_log.json"))
        monkeypatch.setattr(_review, "_review_budget_path",
                            lambda: str(tmp_path / "review_budget.json"))

    def test_three_errors_then_fuse_without_llm_call(self, monkeypatch, tmp_path):
        """mock chat 连续 3 次失败 → 第 4 次不发起 LLM 调用，直接熔断 ERROR。"""
        import _cloud_llm
        calls = {"n": 0}

        def fake_chat(**kwargs):
            calls["n"] += 1
            return None  # 模拟 LLM 不可得（ERROR≠FAIL）

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        self._isolate(monkeypatch, tmp_path)
        out = _make_output(tmp_path)
        for _ in range(3):
            assert _review.review(out, quiet=True)["verdict"] == "ERROR"
        assert calls["n"] == 3
        r4 = _review.review(out, quiet=True)
        assert calls["n"] == 3, "熔断后不得再发起 LLM 调用"
        assert r4["verdict"] == "ERROR"
        assert "审查预算熔断" in r4["summary"]
        assert "ERROR≠FAIL" in r4["summary"]
        assert "请稍后重试或人工审查" in r4["summary"]

    def test_pass_resets_counter(self, monkeypatch, tmp_path):
        """两次 ERROR 后任一次 PASS → 计数归零，之后再次 ERROR 只从 1 累计、不立即熔断。"""
        import _cloud_llm
        calls = {"n": 0}

        def fake_chat(**kwargs):
            calls["n"] += 1
            # 第 1、2、4 次失败；第 3 次 PASS（归零点）；第 5 次 PASS（验证未熔断）
            return None if calls["n"] in (1, 2, 4) else _pass_payload()

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        self._isolate(monkeypatch, tmp_path)
        out = _make_output(tmp_path)
        assert _review.review(out, quiet=True)["verdict"] == "ERROR"
        assert _review.review(out, quiet=True)["verdict"] == "ERROR"
        assert _review._read_budget(None)["consecutive_errors"] == 2
        assert _review.review(out, quiet=True)["verdict"] == "PASS"
        assert _review._read_budget(None)["consecutive_errors"] == 0, "PASS 应归零"
        # 归零后再失败：从 1 重新累计；下次审查仍正常发起 LLM 调用（1 < 阈值 3）
        assert _review.review(out, quiet=True)["verdict"] == "ERROR"
        assert _review._read_budget(None)["consecutive_errors"] == 1
        assert _review.review(out, quiet=True)["verdict"] == "PASS"
        assert calls["n"] == 5, "计数 1 < 阈值 3，不得熔断"

    def test_cross_day_resets(self, monkeypatch, tmp_path):
        """昨日已熔断（date≠今天）→ 今天首次审查正常发起 LLM 调用，不受昨日计数影响。"""
        import _cloud_llm
        calls = {"n": 0}

        def fake_chat(**kwargs):
            calls["n"] += 1
            return _pass_payload()

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        self._isolate(monkeypatch, tmp_path)
        _review._write_budget(None, {"date": "2026-01-01", "consecutive_errors": 3})
        out = _make_output(tmp_path)
        r = _review.review(out, quiet=True)
        assert calls["n"] == 1, "跨日应重置，不得沿用昨日计数熔断"
        assert r["verdict"] == "PASS"

    def test_fail_closed_review_prints_fuse_message(self, capsys):
        """CLI _fail_closed_review：熔断 ERROR 时补一行明确文案，退出码语义不变（exit 2）。"""
        from _cli_generate import _fail_closed_review
        with pytest.raises(SystemExit) as exc_info:
            _fail_closed_review(
                {"verdict": "ERROR", "issues": [],
                 "summary": "审查预算熔断：连续 3 次审查不可得——ERROR≠FAIL"
                            "（内容未必有问题，是审查服务不可得），请稍后重试或人工审查"},
                client_name=None)
        assert exc_info.value.code == 2
        out = capsys.readouterr().out
        assert "审查预算熔断" in out
        assert "fail-closed exit 2" in out

    def test_fail_closed_review_no_fuse_line_for_plain_error(self, capsys):
        """普通 ERROR（非熔断）不追加熔断文案。"""
        from _cli_generate import _fail_closed_review
        with pytest.raises(SystemExit):
            _fail_closed_review(
                {"verdict": "ERROR", "issues": [], "summary": "LLM 调用失败（无可用 provider）"},
                client_name=None)
        assert "审查预算熔断" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# W1-4（#41）：review_log 并发写保护——双会话并发写无丢失无损坏
# ---------------------------------------------------------------------------
class TestW1ReviewLogConcurrency:
    def test_double_thread_20_writes_no_loss_no_corruption(self, monkeypatch, tmp_path):
        """双线程各写 10 条：最终 20 条全在、JSON 可解析、锁文件随写入释放。"""
        monkeypatch.setattr(_paths, "REVIEW_LOG", str(tmp_path / "review_log.json"))
        errors = []

        def worker(tid):
            try:
                for i in range(10):
                    _review.write_review_log(
                        {"verdict": "PASS", "scores": {}, "issues": [],
                         "summary": f"w{tid}-{i}"},
                        f"out_{tid}_{i}.html", f"客户{tid}")
            except Exception as e:  # pragma: no cover - 并发异常本测试要抓
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发写不应抛异常: {errors}"
        with open(tmp_path / "review_log.json", encoding="utf-8") as f:
            entries = json.load(f)  # JSON 损坏会在此抛错
        assert len(entries) == 20, "并发写不得丢条目（旧实现整文件重写互相覆盖）"
        summaries = {e["summary"] for e in entries}
        assert len(summaries) == 20, "条目不得被覆盖重复"
        assert not (tmp_path / ".review_log.lock").exists(), "锁文件应随写入完成释放"

    def test_lock_failure_warns_without_raising(self, monkeypatch, tmp_path, capsys):
        """锁最终获取失败：print 明确警告、不抛异常（维持不阻断语义）。"""
        monkeypatch.setattr(_paths, "REVIEW_LOG", str(tmp_path / "review_log.json"))
        monkeypatch.setattr("_save_lock.acquire_save_lock", lambda *a, **k: None)
        # 不应抛异常
        _review.write_review_log(
            {"verdict": "PASS", "scores": {}, "issues": [], "summary": "s"},
            "a.html", None)
        out = capsys.readouterr().out
        assert "不阻断" in out
        assert ".review_log.lock" in out
        assert not (tmp_path / "review_log.json").exists(), "未获锁不得绕锁写日志"
