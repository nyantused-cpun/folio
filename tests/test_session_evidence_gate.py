# -*- coding: utf-8 -*-
"""save_session 证据守门集成测试（P0 · T2）。

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
"""

import os

import _session
import _memory_guard as mg
import _context


# ============================================================
# parse_args
# ============================================================
class TestParseArgsEvidence:
    def test_evidence_parsed(self):
        r = _session.parse_args(["--evidence=file:a.html;user:微信确认"])
        assert r["evidence"] == "file:a.html;user:微信确认"
        assert r["strict_evidence"] is False

    def test_strict_evidence_true_variants(self):
        for v in ("1", "true", "yes", "TRUE", "Yes", " 1 "):
            r = _session.parse_args(["--strict-evidence=" + v])
            assert r["strict_evidence"] is True, v

    def test_strict_evidence_false_variants(self):
        for v in ("0", "false", "no", "abc", ""):
            r = _session.parse_args(["--strict-evidence=" + v])
            assert r["strict_evidence"] is False, v

    def test_strict_evidence_default_false(self):
        r = _session.parse_args([])
        assert r["strict_evidence"] is False
        assert r["evidence"] == ""

    def test_legacy_four_keys_unchanged(self):
        r = _session.parse_args([
            "--input=描述", "--decisions=决策", "--outputs=产出", "--pending=待办",
        ])
        assert r["input_desc"] == "描述"
        assert r["decisions"] == "决策"
        assert r["outputs"] == "产出"
        assert r["pending"] == "待办"
        # 新增键存在且默认
        assert r["evidence"] == ""
        assert r["strict_evidence"] is False


# ============================================================
# save_session 守门集成（blocked 路径零副作用）
# ============================================================
class TestSaveSessionGate:
    def test_strict_blocked_returns_false_and_no_side_effect(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        clients.mkdir()
        # 守门在 ensure_client_dir 之前返回；重定向两个结构化写入目标到 tmp，
        # 万一守门位置错了也不会写真实 _knowledge / task_history。
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))

        result = _session.save_session(
            "不存在的测试客户ZZZ",
            decisions="测试决策",
            evidence="file:不存在的文件zzz.txt",
            strict_evidence=True,
        )
        assert result is False
        assert not os.path.exists(clients / "不存在的测试客户ZZZ")


# ============================================================
# gate_entry 联动（注入 tmp 路径，三分支）
# ============================================================
class TestGateEntryIntegration:
    def test_warn_no_evidence(self):
        r = mg.gate_entry("某决策", "", "某客户")
        assert r["verdict"] == "warn"
        assert r["marker"] == "（待补证据）"
        assert r["counts"] == {"total_refs": 0, "passed": 0, "failed": 0}

    def test_warn_unverified(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry(
            "某决策", "file:a.html;file:missing.html", "某客户",
            base_dir=str(tmp_path),
        )
        assert r["verdict"] == "warn"
        assert "证据待核" in r["marker"]
        assert r["counts"]["passed"] == 1
        assert r["counts"]["failed"] == 1

    def test_ok_all_pass(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry("某决策", "file:a.html", "某客户", base_dir=str(tmp_path))
        assert r["verdict"] == "ok"
        assert r["marker"] == ""
        assert r["counts"] == {"total_refs": 1, "passed": 1, "failed": 0}


# ============================================================
# marker 渲染纯逻辑
# ============================================================
class TestRenderDecisionsWithMarker:
    def test_appends_marker(self):
        assert _session._render_decisions_with_marker(
            "决策A", "（待补证据）") == "决策A（待补证据）"

    def test_no_marker(self):
        assert _session._render_decisions_with_marker("决策A", "") == "决策A"

    def test_empty_decisions(self):
        assert _session._render_decisions_with_marker("", "（待补证据）") == ""
        assert _session._render_decisions_with_marker(None, "（待补证据）") is None
