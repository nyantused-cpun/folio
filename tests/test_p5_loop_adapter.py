# -*- coding: utf-8 -*-
"""P5 长文本创作循环适配测试。

覆盖：
- build_head_context 压缩：permanent 铁律 ≤6 行（前 4 条 + 计数）
- _print_review / _print_adversarial_review：stdout 只打印前 10 条 issues +
  「完整 N 条见 review_log.json」
"""

from _theme_guard import build_head_context
from _review import _print_review, _print_adversarial_review


def _theme(i, title, persistence="permanent", scope="client", priority="high"):
    return {
        "id": f"t{i:03d}", "theme": title, "description": f"desc{i}",
        "persistence": persistence, "scope": scope, "task_id": None,
        "priority": priority, "source_date": "2026-08-01",
    }


class TestBuildHeadContextCompress:
    def test_single_theme_compact(self):
        head = build_head_context([_theme(0, "铁律A")])
        lines = [ln for ln in head.splitlines() if ln.strip()]
        assert lines[0] == "=== 核心约束刷新 ==="
        assert "[PERMANENT-CLIENT] 铁律A" in lines[1]
        assert len(lines) <= 6

    def test_many_themes_truncated_with_count(self):
        themes = [_theme(i, f"铁律{i}") for i in range(10)]
        head = build_head_context(themes)
        lines = [ln for ln in head.splitlines() if ln.strip()]
        assert len(lines) <= 6, f"HEAD 应 ≤6 行，实得 {len(lines)}"
        assert "共 10 条永久铁律" in lines[-1]
        # 前 4 条在，第 5+ 条只进计数不展开
        assert any("铁律0" in ln for ln in lines)
        assert not any("铁律7" in ln for ln in lines)

    def test_empty_returns_empty(self):
        assert build_head_context([]) == ""


class TestReviewStdoutTruncation:
    def _issues(self, n):
        return [f"问题{i}：内容{i}" for i in range(1, n + 1)]

    def test_print_review_truncates_to_10(self, capsys):
        result = {"verdict": "FAIL", "scores": {}, "summary": "s",
                  "issues": self._issues(15), "theme_coverage": {}}
        _print_review(result, "output/x/方案.html")
        out = capsys.readouterr().out
        assert "问题 (15)" in out
        assert "问题1" in out and "问题10" in out
        assert "问题11" not in out
        assert "完整 15 条见" in out

    def test_print_adversarial_truncates_to_10(self, capsys):
        result = {"verdict": "FAIL", "summary": "s", "issues": self._issues(12)}
        _print_adversarial_review(result, "output/x/方案.html")
        out = capsys.readouterr().out
        assert "发现问题 (12)" in out
        assert "问题10" in out and "问题11" not in out
        assert "完整 12 条见" in out

    def test_few_issues_not_truncated(self, capsys):
        result = {"verdict": "PASS", "scores": {}, "summary": "s",
                  "issues": self._issues(3), "theme_coverage": {}}
        _print_review(result, "output/x/方案.html")
        out = capsys.readouterr().out
        assert "问题3" in out
        assert "完整" not in out
