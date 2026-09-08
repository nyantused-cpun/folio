# -*- coding: utf-8 -*-
"""W1-3 save_decision 同日同题去重（防灌水）测试。

背景：review FAIL 每轮 save_decision(topic="review FAIL: {basename}") 纯追加，
同题灌水（示例集团 ×12/蓝海 ×5/验收 ×3），confidence 0.5 条目占召回前排。
机制：同日同题（归一化压空白）命中 -> 原块尾追加「复发」行，不新增块。

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
monkeypatch 只改 _theme_guard.CLIENTS_DIR（模块级常量），不碰 _paths 真实常量。
"""

import _save_lock
import _theme_guard


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(tmp_path))
    return tmp_path / "测试客户" / "decisions.md"


def _read(path):
    return path.read_text(encoding="utf-8")


# ============================================================
# 同日同题：归并为复发行，不新增块
# ============================================================
class TestSameDaySameTopicMerge:
    def test_double_call_single_block_with_recurrence_2(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        content = _read(path)
        # 只有一块（防灌水核心断言）
        assert content.count("## [") == 1
        # 复发行：原始块计第 1 次，复发归并后是第 2 次发生
        assert "- **复发**: 第 2 次（" in content
        assert "最新 issues: " in content
        # 原块字段原样保留
        assert "- **决策**: 产出 x 审查未通过" in content
        assert "- **confidence**: 0.5" in content

    def test_triple_call_counts_up_still_single_block(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        for _ in range(3):
            _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        content = _read(path)
        assert content.count("## [") == 1
        assert "- **复发**: 第 2 次（" in content
        assert "- **复发**: 第 3 次（" in content
        assert content.count("- **复发**: 第") == 2

    def test_whitespace_normalized_topic_merges(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        # 多一个空格的同名异写 -> 归一化后同题，仍归并
        _theme_guard.save_decision("测试客户", "review FAIL:  方案.html", "产出 x 审查未通过")
        assert _read(path).count("## [") == 1

    def test_review_flood_latest_reason_lands_in_last_line(self, tmp_path, monkeypatch):
        """_finalize_review 灌水场景：同题多轮、issues 每轮不同 -> 最新一轮在末条复发行。"""
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过", reason="旧问题A; 旧问题B")
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过", reason="新问题C")
        content = _read(path)
        assert content.count("## [") == 1
        assert "最新 issues: 新问题C" in content
        assert "旧问题A" in content  # 首轮 issues 保留在「理由」行，决策依据不丢


# ============================================================
# 不归并的情形
# ============================================================
class TestNoMergeCases:
    def test_different_topic_no_merge(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "报价口径", "100万")
        _theme_guard.save_decision("测试客户", "交付节奏", "两周")
        content = _read(path)
        assert content.count("## [") == 2
        assert "- **复发**" not in content

    def test_different_day_no_merge(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        # 预置昨日同题块（决策内容相同 -> 不触发冲突流）
        path.parent.mkdir(parents=True)
        path.write_text(
            "# 测试客户 决策记录\n"
            "\n## [2026-09-05] review FAIL: 方案.html\n"
            "- **决策**: 产出 x 审查未通过\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
            "- **confidence**: 0.5\n",
            encoding="utf-8")
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        content = _read(path)
        # 跨日不归并：昨日块 + 今日新块，无复发行
        assert content.count("## [") == 2
        assert "- **复发**" not in content

    def test_conflict_flow_not_merged(self, tmp_path, monkeypatch):
        """同日同题不同内容走冲突流（新增 ⚠️ 块），不做复发归并。"""
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "报价口径", "100万")
        _theme_guard.save_decision("测试客户", "报价口径", "200万")
        content = _read(path)
        assert content.count("## [") == 2
        assert "<!-- conflict: pending -->" in content
        assert "- **复发**" not in content


# ============================================================
# reason 渲染：首条一行 + 截断 80 字
# ============================================================
class TestReasonRendering:
    def test_multiline_reason_takes_first_line(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过",
            reason="第一行问题\n第二行问题")
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过",
            reason="第一行问题\n第二行问题")
        content = _read(path)
        assert "最新 issues: 第一行问题\n" in content
        assert "第二行问题" not in content.split("- **复发**")[1]

    def test_long_reason_truncated_to_80_chars(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        long_issue = "长" * 120
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过", reason=long_issue)
        _theme_guard.save_decision(
            "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过", reason=long_issue)
        content = _read(path)
        line = [ln for ln in content.splitlines() if "- **复发**" in ln][0]
        issue_part = line.split("最新 issues: ", 1)[1]
        assert len(issue_part) == 80

    def test_empty_reason_placeholder(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过", reason="")
        assert "最新 issues: (未记录)" in _read(path)


# ============================================================
# 锁行为不变（F0-8 保留）
# ============================================================
class TestLockBehaviorUnchanged:
    def test_held_lock_returns_none_and_no_merge(self, tmp_path, monkeypatch):
        path = _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
        before = _read(path)
        client_dir = str(tmp_path / "测试客户")
        fd = _save_lock.acquire_save_lock(client_dir, timeout=1.0)
        assert fd is not None
        try:
            result = _theme_guard.save_decision(
                "测试客户", "review FAIL: 方案.html", "产出 x 审查未通过")
            assert result is None  # 锁失败返回 None，不假装成功
        finally:
            _save_lock.release_save_lock(client_dir, fd)
        assert _read(path) == before  # 零写入

    def test_merge_holds_and_releases_lock(self, tmp_path, monkeypatch):
        _isolate(tmp_path, monkeypatch)
        _theme_guard.save_decision("测试客户", "报价口径", "100万")
        _theme_guard.save_decision("测试客户", "报价口径", "100万")
        # 归并路径走完无锁残留
        assert not (tmp_path / "测试客户" / ".save_lock").exists()
