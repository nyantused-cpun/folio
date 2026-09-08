# -*- coding: utf-8 -*-
"""S6 P2 卫生群回归测试（2026-09-07，docs/视觉生产线_全量历史审查总报告_2026-09-07 §4.8）。

覆盖：
1. CONTENT_Y_MAX 公共单源（_renderer.spacing，切断 lint→_pptd_gen 私有 import）
2. 文本高度估算单源（spacing.estimate_text_height，lint/生成器同源 + 行距显式参数）
3. _review._write_budget 持锁读-合并-写（复用 _save_lock，锁获取失败不阻断）
5. tests/test_diagram.py test_cards_v2_page_maps_info_cards 环境变量条件还原
   （子集序回归：曾无条件 pop 外部预设的 _PRESALES_CLI_INVOKED）
6. check_diagram_level 接 verify_yaml 打印面（与 deliver receipt 同口径）
"""
import json
import os

import _layout_lint
import _pptd_parts
import _review
import _theme_guard
import _verify
from _renderer import spacing


# ---------------------------------------------------------------------------
# 1. CONTENT_Y_MAX 公共单源
# ---------------------------------------------------------------------------

class TestContentYMaxSingleSource:
    def test_spacing_is_definition_site(self):
        assert spacing.CONTENT_Y_MAX == 674

    def test_parts_alias_is_same_object(self):
        assert _pptd_parts._CONTENT_Y_MAX is spacing.CONTENT_Y_MAX

    def test_lint_clamp_line_is_same_object(self):
        assert _layout_lint._CLAMP_LINE is spacing.CONTENT_Y_MAX

    def test_gen_reexport_unchanged(self):
        """_pptd_gen 经 _pptd_parts re-import 的面不变（并发代理所有权边界）。"""
        import _pptd_gen
        assert _pptd_gen._CONTENT_Y_MAX == spacing.CONTENT_Y_MAX

    def test_dead_code_removed(self):
        assert not hasattr(_theme_guard, "detect_decision_trigger")
        assert not hasattr(_theme_guard, "count_skipped_conflicts")
        assert not hasattr(_theme_guard, "DECISION_TRIGGERS")
        assert not hasattr(_theme_guard, "_LAST_SKIPPED_CONFLICTS")


# ---------------------------------------------------------------------------
# 2. 文本高度估算单源
# ---------------------------------------------------------------------------

class TestEstimateTextHeightSingleSource:
    def test_empty_text_one_line(self):
        assert spacing.estimate_text_height("", 14, 1.65, 1048) == 14 * 1.65

    def test_pure_cjk_matches_legacy_char_count(self):
        """常见宽度/字号组合下与旧字符数口径行数一致（回归锚：test_estimate_text_height_positive）。"""
        text = "短文本" * 100
        h = spacing.estimate_text_height(text, 14, 1.65, 1048)
        assert h == _pptd_parts._estimate_text_height(text, 14, 1.65, 1048)
        assert h > 14 * 1.65  # 多行须显著高于单行

    def test_ascii_mixed_uses_halfwidth_coefficient(self):
        """半角按 0.55×font 计宽（统一前字符数口径对 ASCII 高估，行数更多）。"""
        text = "ROI KPI " * 30  # 240 半角字符
        lines_est = spacing.estimate_text_height(text, 14, 1.3, 1048) / (14 * 1.3)
        lines_legacy = max(1, -(-len(text) // (1048 // 14)))
        assert lines_est < lines_legacy

    def test_html_tags_stripped(self):
        a = spacing.estimate_text_height("<b>加粗</b>文本", 14, 1.3, 1048)
        b = spacing.estimate_text_height("加粗文本", 14, 1.3, 1048)
        assert a == b

    def test_empty_paragraph_counts_one_line(self):
        h = spacing.estimate_text_height("甲\n\n乙", 14, 1.3, 1048)
        assert h == 3 * 14 * 1.3

    def test_line_height_explicit(self):
        text = "一行"
        h13 = spacing.estimate_text_height(text, 14, 1.3, 1048)
        h165 = spacing.estimate_text_height(text, 14, 1.65, 1048)
        assert h13 == 14 * 1.3
        assert h165 == 14 * 1.65

    def test_parts_delegate_same_result(self):
        text = "跨系统凭证推送与三单匹配稽核"
        assert (_pptd_parts._estimate_text_height(text, 14, 1.65, 1120)
                == spacing.estimate_text_height(text, 14, 1.65, 1120))

    def test_lint_message_lines_consistent(self):
        """lint 从统一入口反推行数，消息口径不漂移。"""
        seg = "一二三四五六七八九十"
        w, fs = 100.0, 14.0
        est_h = spacing.estimate_text_height(seg, fs, _layout_lint.LINE_HEIGHT, w)
        lines = int(round(est_h / (fs * _layout_lint.LINE_HEIGHT)))
        import math
        assert lines == max(1, math.ceil(spacing.est_text_w(seg, fs) / w))


# ---------------------------------------------------------------------------
# 3. _write_budget 持锁
# ---------------------------------------------------------------------------

class TestWriteBudgetLock:
    def _patch_path(self, monkeypatch, tmp_path):
        p = str(tmp_path / "review_budget.json")
        monkeypatch.setattr("_review._review_budget_path", lambda: p)
        return p

    def test_write_under_lock_preserves_other_clients(self, monkeypatch, tmp_path):
        path = self._patch_path(monkeypatch, tmp_path)
        _review._write_budget("甲", {"date": "2026-09-07", "consecutive_errors": 1})
        _review._write_budget("乙", {"date": "2026-09-07", "consecutive_errors": 2})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["甲"]["consecutive_errors"] == 1
        assert data["乙"]["consecutive_errors"] == 2
        # 锁文件已释放（不残留）
        assert not (tmp_path / ".review_budget.lock").exists()

    def test_lock_failure_non_blocking(self, monkeypatch, tmp_path, capsys):
        """锁获取失败（双会话并发）：不抛异常、不写盘、打印告警（不阻断语义）。"""
        path = self._patch_path(monkeypatch, tmp_path)
        calls = []

        def fake_acquire(lock_dir, timeout=None, stale_after=None,
                         lock_name=None):
            calls.append(lock_name)
            return None

        monkeypatch.setattr("_save_lock.acquire_save_lock", fake_acquire)
        _review._write_budget("甲", {"date": "2026-09-07", "consecutive_errors": 1})
        assert not os.path.exists(path)
        assert ".review_budget.lock" in calls
        assert "预算状态写入失败" in capsys.readouterr().out

    def test_lock_uses_dedicated_lockfile(self, monkeypatch, tmp_path):
        path = self._patch_path(monkeypatch, tmp_path)
        calls = []

        def fake_acquire(lock_dir, timeout=None, stale_after=None,
                         lock_name=None):
            calls.append(lock_name)
            return -1  # 任意非 None fd（不真正建文件）

        monkeypatch.setattr("_save_lock.acquire_save_lock", fake_acquire)
        monkeypatch.setattr("_save_lock.release_save_lock",
                            lambda *a, **kw: calls.append("released"))
        _review._write_budget("甲", {"date": "2026-09-07", "consecutive_errors": 1})
        assert calls == [".review_budget.lock", "released"]
        with open(path, encoding="utf-8") as f:
            assert json.load(f)["甲"]["consecutive_errors"] == 1


# ---------------------------------------------------------------------------
# 5. test_diagram 环境变量隔离（子集序回归）
# ---------------------------------------------------------------------------

class TestCliInvokedEnvIsolation:
    def _run_cards_v2_test(self, tmp_path):
        import test_diagram
        test_diagram.TestV15FieldFixes().test_cards_v2_page_maps_info_cards(tmp_path)

    def test_preserves_preexisting_flag(self, tmp_path):
        """子集序回归：外部已设 _PRESALES_CLI_INVOKED（如 baseline_kit import
        时 setdefault）时，跑完该用例变量必须仍在——曾无条件 pop 致后续
        test_baseline 6 例抛 NotInvokedViaCLIError。"""
        # 本测试自身也走保存/条件还原，不误删外层预设
        saved = os.environ.get("_PRESALES_CLI_INVOKED")
        os.environ["_PRESALES_CLI_INVOKED"] = "1"
        try:
            self._run_cards_v2_test(tmp_path)
            assert os.environ.get("_PRESALES_CLI_INVOKED") == "1"
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved

    def test_unset_still_unset_after(self, tmp_path):
        # 需先清空再验证「unset 进 unset 出」；结束时保存/条件还原
        saved = os.environ.get("_PRESALES_CLI_INVOKED")
        os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            self._run_cards_v2_test(tmp_path)
            assert "_PRESALES_CLI_INVOKED" not in os.environ
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved


# ---------------------------------------------------------------------------
# 6. check_diagram_level 接 verify 打印面
# ---------------------------------------------------------------------------

class TestDiagramLevelPrintSurface:
    def _write_spec(self, tmp_path, pages):
        import yaml
        p = tmp_path / "spec.yml"
        p.write_text(yaml.safe_dump({
            "confirmed": True, "theme": "consulting_kpmg", "pages": pages,
        }, allow_unicode=True), encoding="utf-8")
        return str(p)

    def _harvey(self):
        return {"type": "diagram", "diagram_type": "matrix",
                "subtype": "harvey_balls", "title": "供应商比选",
                "rows": ["功能覆盖"], "columns": ["我方方案"],
                "cells": [{"row": "功能覆盖", "col": "我方方案", "value": 4}]}

    def test_diagram_summary_printed(self, tmp_path):
        path = self._write_spec(tmp_path, [{
            "id": "p1", "title": "对比", "layout": "P07",
            "elements": [self._harvey()],
        }])
        ok, msg = _verify.verify_yaml(path)
        assert "图级校验 1 图" in msg
        assert "错误 0" in msg

    def test_no_diagram_no_segment(self, tmp_path):
        path = self._write_spec(tmp_path, [{
            "id": "p1", "title": "对比", "layout": "P07",
            "elements": [{"type": "table", "headers": ["项"],
                          "rows": [["甲"]]}],
        }])
        ok, msg = _verify.verify_yaml(path)
        assert "图级校验" not in msg

    def test_reexport_face(self):
        """_verify re-import 面与 deliver receipt 同函数对象。"""
        from _verify_checks import check_diagram_level
        assert _verify.check_diagram_level is check_diagram_level
