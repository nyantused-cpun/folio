# -*- coding: utf-8 -*-
"""M3-F3 goal 闭环 CLI 侧测试。

F3-2：生成链失败清单回流 session_state.json.lastReview（尽力而为，不改退出码）。
F3-4：token 预算软告警（触阈值提醒，不阻断）。
"""
import json
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import _cli_generate
import _state


@pytest.fixture()
def state_file(tmp_path, monkeypatch):
    """隔离 session_state.json 到 tmp。"""
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(_state, "SESSION_STATE_PATH", str(path))
    return path


def _read_last_review(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["clients"]["测试客户F3"]["lastReview"]


# ============================================================
# F3-2：_record_last_review
# ============================================================
class TestRecordLastReview:
    def test_writes_last_review_to_state_file(self, state_file):
        _cli_generate._record_last_review(
            "测试客户F3", "FAIL", ["verify 未通过: output/x.html", "L3 未覆盖: 数据治理"],
            "html-build verify")
        review = _read_last_review(state_file)
        assert review["verdict"] == "FAIL"
        assert review["issues"][0].startswith("verify 未通过")
        assert review["issues"][1] == "L3 未覆盖: 数据治理"
        assert review["at"], "应写入时间戳"

    def test_issue_cap_and_truncation(self, state_file):
        issues = [f"问题{i}" for i in range(30)] + ["", "   "]
        issues.append("x" * 500)
        _cli_generate._record_last_review("测试客户F3", "FAIL", issues, "review")
        review = _read_last_review(state_file)
        assert len(review["issues"]) == 20, "最多保留 20 条"
        assert all(review["issues"]), "空 issue 应被剔除"
        assert all(len(i) <= 300 for i in review["issues"]), "单条截断到 300"

    def test_no_client_noop(self, state_file):
        _cli_generate._record_last_review(None, "FAIL", ["x"], "review")
        _cli_generate._record_last_review("", "FAIL", ["x"], "review")
        assert not state_file.exists(), "无客户时不写文件"

    def test_corrupt_state_file_still_records(self, state_file):
        state_file.write_text("{corrupt", encoding="utf-8")
        _cli_generate._record_last_review("测试客户F3", "ERROR", ["boom"], "review")
        review = _read_last_review(state_file)
        assert review["verdict"] == "ERROR"

    def test_never_raises_when_set_state_fails(self, state_file, monkeypatch, capsys):
        def boom(client, **kw):
            raise OSError("disk full")
        monkeypatch.setattr(_state, "set_state", boom)
        # 不应抛异常
        _cli_generate._record_last_review("测试客户F3", "FAIL", ["x"], "review")
        assert "回流失败" in capsys.readouterr().out


# ============================================================
# F3-2：_fail_closed_review 回流接线（FAIL/ERROR -> exit 2 + lastReview）
# ============================================================
class TestFailClosedReviewRecords:
    def test_fail_records_then_exit2(self, state_file):
        with pytest.raises(SystemExit) as ei:
            _cli_generate._fail_closed_review(
                {"verdict": "FAIL", "issues": ["缺少数据治理页"]},
                client_name="测试客户F3", source="html-build review")
        assert ei.value.code == 2
        review = _read_last_review(state_file)
        assert review["verdict"] == "FAIL"
        assert review["issues"] == ["缺少数据治理页"]

    def test_none_result_records_error(self, state_file):
        with pytest.raises(SystemExit) as ei:
            _cli_generate._fail_closed_review(None, client_name="测试客户F3")
        assert ei.value.code == 2
        review = _read_last_review(state_file)
        assert review["verdict"] == "ERROR"

    def test_skip_and_pass_do_not_record(self, state_file):
        _cli_generate._fail_closed_review({"verdict": "SKIP"}, client_name="测试客户F3")
        _cli_generate._fail_closed_review(
            {"verdict": "PASS", "issues": []}, client_name="测试客户F3")
        assert not state_file.exists(), "SKIP/PASS 不回流"


# ============================================================
# F3-2：_blocked_issue_summary
# ============================================================
class TestBlockedIssueSummary:
    def test_theme_degraded_and_plain(self):
        blocked = [
            {"theme": "数据治理", "priority": "critical"},
            {"page": 3, "index": 1, "type": "chart", "target": "text", "message": "后端不支持"},
            "纯文本问题",
        ]
        out = _cli_generate._blocked_issue_summary(blocked)
        assert out[0] == "L3 未覆盖: 数据治理"
        assert out[1].startswith("渲染降级: 3 elements[1] chart -> text")
        assert out[2] == "纯文本问题"

    def test_empty_and_none(self):
        assert _cli_generate._blocked_issue_summary([]) == []
        assert _cli_generate._blocked_issue_summary(None) == []


# ============================================================
# F3-4：_budget_soft_warning
# ============================================================
class TestBudgetSoftWarning:
    def test_warns_when_over_threshold(self, monkeypatch, capsys):
        import _cloud_llm
        monkeypatch.setenv("CLI_BUDGET_WARN_TOKENS", "1000")
        monkeypatch.setattr(_cloud_llm, "get_usage_summary",
                            lambda month=None: {"total_calls": 12, "total_tokens": 2000, "by_provider": {}})
        _cli_generate._budget_soft_warning()
        out = capsys.readouterr().out
        assert "[预算]" in out
        assert "2000" in out and "1000" in out

    def test_silent_under_threshold(self, monkeypatch, capsys):
        import _cloud_llm
        monkeypatch.setenv("CLI_BUDGET_WARN_TOKENS", "1000")
        monkeypatch.setattr(_cloud_llm, "get_usage_summary",
                            lambda month=None: {"total_calls": 1, "total_tokens": 10, "by_provider": {}})
        _cli_generate._budget_soft_warning()
        assert "[预算]" not in capsys.readouterr().out

    def test_disabled_by_zero(self, monkeypatch, capsys):
        import _cloud_llm
        monkeypatch.setenv("CLI_BUDGET_WARN_TOKENS", "0")
        monkeypatch.setattr(_cloud_llm, "get_usage_summary",
                            lambda month=None: {"total_calls": 9, "total_tokens": 99999, "by_provider": {}})
        _cli_generate._budget_soft_warning()
        assert "[预算]" not in capsys.readouterr().out

    def test_never_raises(self, monkeypatch, capsys):
        import _cloud_llm
        monkeypatch.setenv("CLI_BUDGET_WARN_TOKENS", "1000")
        def boom(month=None):
            raise RuntimeError("x")
        monkeypatch.setattr(_cloud_llm, "get_usage_summary", boom)
        _cli_generate._budget_soft_warning()  # 不应抛
        assert "[预算]" not in capsys.readouterr().out
