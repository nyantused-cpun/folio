# -*- coding: utf-8 -*-
"""_memory_guard 单元测试（P0 · T1）。

全部用 tmp_path 造假文件，绝不读写真实 _knowledge/ 客户目录。
"""

import _memory_guard as mg


# ============================================================
# parse_source_refs
# ============================================================
class TestParseSourceRefs:
    def test_empty_and_none(self):
        assert mg.parse_source_refs("") == []
        assert mg.parse_source_refs(None) == []

    def test_file_with_anchor(self):
        refs = mg.parse_source_refs("file:output/蓝海集团/方案_v1.html#p3")
        assert refs == [{
            "kind": "file",
            "value": "output/蓝海集团/方案_v1.html",
            "anchor": "p3",
            "raw": "file:output/蓝海集团/方案_v1.html#p3",
        }]

    def test_file_backslash_normalized(self):
        refs = mg.parse_source_refs(r"file:output\蓝海集团\方案_v1.html")
        assert refs[0]["value"] == "output/蓝海集团/方案_v1.html"

    def test_file_no_anchor(self):
        refs = mg.parse_source_refs("file:_knowledge/clients/蓝海集团/refs/x.xlsx")
        assert refs[0]["anchor"] == ""
        assert refs[0]["value"] == "_knowledge/clients/蓝海集团/refs/x.xlsx"

    def test_multiple_refs(self):
        refs = mg.parse_source_refs("file:a#p1;session:12;decision:3;user:微信确认")
        assert [r["kind"] for r in refs] == ["file", "session", "decision", "user"]

    def test_session_decision_values_are_strings(self):
        refs = mg.parse_source_refs("session:12;decision:3")
        assert refs[0]["value"] == "12"
        assert refs[1]["value"] == "3"

    def test_session_decision_leading_zeros_stripped(self):
        refs = mg.parse_source_refs("session:012;decision:003;session:000")
        assert refs[0]["value"] == "12"
        assert refs[1]["value"] == "3"
        assert refs[2]["value"] == "0"  # 全零保 "0"，交给校验层自然失败

    def test_unknown_kind_invalid(self):
        refs = mg.parse_source_refs("foo:bar")
        assert refs[0]["kind"] == "invalid"
        assert refs[0]["raw"] == "foo:bar"

    def test_no_colon_invalid(self):
        refs = mg.parse_source_refs("noseparator")
        assert refs[0]["kind"] == "invalid"

    def test_empty_value_invalid(self):
        assert mg.parse_source_refs("file:")[0]["kind"] == "invalid"
        assert mg.parse_source_refs("session:")[0]["kind"] == "invalid"
        assert mg.parse_source_refs("user:")[0]["kind"] == "invalid"

    def test_trailing_semicolon_ignored(self):
        refs = mg.parse_source_refs("user:abc;")
        assert len(refs) == 1
        assert refs[0]["kind"] == "user"


# ============================================================
# verify_source_ref
# ============================================================
class TestVerifySourceRef:
    def test_file_ok(self, tmp_path):
        (tmp_path / "方案.html").write_text("x", encoding="utf-8")
        ref = {"kind": "file", "value": "方案.html", "anchor": "", "raw": "file:方案.html"}
        ok, reason = mg.verify_source_ref(ref, "某客户", base_dir=str(tmp_path))
        assert ok is True

    def test_file_missing(self, tmp_path):
        ref = {"kind": "file", "value": "不存在.html", "anchor": "", "raw": "file:不存在.html"}
        ok, reason = mg.verify_source_ref(ref, "某客户", base_dir=str(tmp_path))
        assert ok is False
        assert reason == "文件不存在: 不存在.html"

    def test_session_ok(self, tmp_path):
        ctx = tmp_path / "context.md"
        ctx.write_text("### [2026-08-18] 第 3 次会话\n#### 关键决策\nx\n", encoding="utf-8")
        ref = {"kind": "session", "value": "2", "anchor": "", "raw": "session:2"}
        ok, reason = mg.verify_source_ref(ref, "某客户", context_path=str(ctx))
        assert ok is True

    def test_session_out_of_range(self, tmp_path):
        ctx = tmp_path / "context.md"
        ctx.write_text("### [2026-08-18] 第 2 次会话\n", encoding="utf-8")
        ref = {"kind": "session", "value": "5", "anchor": "", "raw": "session:5"}
        ok, reason = mg.verify_source_ref(ref, "某客户", context_path=str(ctx))
        assert ok is False
        assert reason == "会话 5 不存在（共 2 次）"

    def test_session_non_integer(self, tmp_path):
        ctx = tmp_path / "context.md"
        ctx.write_text("### [2026-08-18] 第 2 次会话\n", encoding="utf-8")
        ref = {"kind": "session", "value": "abc", "anchor": "", "raw": "session:abc"}
        ok, reason = mg.verify_source_ref(ref, "某客户", context_path=str(ctx))
        assert ok is False

    def test_session_context_missing(self, tmp_path):
        ref = {"kind": "session", "value": "1", "anchor": "", "raw": "session:1"}
        ok, reason = mg.verify_source_ref(ref, "某客户", context_path=str(tmp_path / "none.md"))
        assert ok is False
        assert reason == "context.md 不存在"

    def test_decision_ok(self, tmp_path):
        dec = tmp_path / "decisions.md"
        dec.write_text("## 决策 3：标题\n- **决策内容**：x\n", encoding="utf-8")
        ref = {"kind": "decision", "value": "3", "anchor": "", "raw": "decision:3"}
        ok, reason = mg.verify_source_ref(ref, "某客户", decisions_path=str(dec))
        assert ok is True

    def test_decision_missing(self, tmp_path):
        dec = tmp_path / "decisions.md"
        dec.write_text("## 决策 1：标题\n", encoding="utf-8")
        ref = {"kind": "decision", "value": "9", "anchor": "", "raw": "decision:9"}
        ok, reason = mg.verify_source_ref(ref, "某客户", decisions_path=str(dec))
        assert ok is False
        assert reason == "决策 9 不存在"

    def test_decision_file_missing(self, tmp_path):
        ref = {"kind": "decision", "value": "1", "anchor": "", "raw": "decision:1"}
        ok, reason = mg.verify_source_ref(ref, "某客户", decisions_path=str(tmp_path / "none.md"))
        assert ok is False
        assert reason == "decisions.md 不存在"

    def test_user_always_ok(self):
        ref = {"kind": "user", "value": "微信确认", "anchor": "", "raw": "user:微信确认"}
        ok, reason = mg.verify_source_ref(ref, "某客户")
        assert ok is True
        assert reason == "用户口述（免校验）"

    def test_invalid(self):
        ref = {"kind": "invalid", "value": "", "anchor": "", "raw": "foo:bar"}
        ok, reason = mg.verify_source_ref(ref, "某客户")
        assert ok is False
        assert reason == "格式非法: foo:bar"


# ============================================================
# gate_entry
# ============================================================
class TestGateEntry:
    def test_empty_decisions_and_evidence_ok(self):
        # 监工修复（2026-08-19）："决策与证据都为空"才无事可守
        r = mg.gate_entry("", "", "某客户")
        assert r["verdict"] == "ok"
        assert r["marker"] == ""
        assert r["counts"] == {"total_refs": 0, "passed": 0, "failed": 0}

    def test_empty_decisions_with_evidence_fail_warn(self, tmp_path):
        # 监工修复（2026-08-19）：传了证据串就必须校验——空决策不再短路，
        # 坏引用 + 非 strict -> warn（原行为：静默 ok，坏引用被放行）
        r = mg.gate_entry("", "file:missing.html", "某客户", base_dir=str(tmp_path))
        assert r["verdict"] == "warn"
        assert "证据待核" in r["marker"]
        assert r["counts"] == {"total_refs": 1, "passed": 0, "failed": 1}

    def test_empty_decisions_with_evidence_fail_blocked(self, tmp_path):
        # 监工修复（2026-08-19）：空决策 + 坏引用 + strict -> blocked（原行为放行）
        r = mg.gate_entry("", "file:missing.html", "某客户",
                          strict=True, base_dir=str(tmp_path))
        assert r["verdict"] == "blocked"
        assert len(r["reasons"]) == 1

    def test_empty_decisions_with_evidence_pass_ok(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry("", "file:a.html", "某客户", base_dir=str(tmp_path))
        assert r["verdict"] == "ok"
        assert r["counts"] == {"total_refs": 1, "passed": 1, "failed": 0}
        assert r["evidence_lines"] == ["[✓] file:a.html"]

    def test_unparseable_evidence_warn(self):
        # 有证据串但解析不出合法引用（且无决策）：显式可见警告，绝不静默
        # （parse_source_refs 返回 kind=invalid 的 ref -> verify 失败 -> 证据待核）
        r = mg.gate_entry("", "garbage without ref prefix", "某客户")
        assert r["verdict"] == "warn"
        assert "证据待核" in r["marker"]
        assert r["counts"]["failed"] == 1

    def test_none_decisions_ok(self):
        r = mg.gate_entry(None, "", "某客户")
        assert r["verdict"] == "ok"

    def test_no_evidence_warn(self):
        r = mg.gate_entry("某决策内容", "", "某客户")
        assert r["verdict"] == "warn"
        assert r["marker"] == "（待补证据）"

    def test_all_pass_ok(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry("某决策", "file:a.html", "某客户", base_dir=str(tmp_path))
        assert r["verdict"] == "ok"
        assert r["counts"] == {"total_refs": 1, "passed": 1, "failed": 0}
        assert r["evidence_lines"] == ["[✓] file:a.html"]

    def test_some_fail_warn(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry("某决策", "file:a.html;file:missing.html", "某客户", base_dir=str(tmp_path))
        assert r["verdict"] == "warn"
        assert "证据待核" in r["marker"]
        assert r["counts"]["passed"] == 1
        assert r["counts"]["failed"] == 1
        assert len(r["reasons"]) == 1

    def test_some_fail_blocked(self, tmp_path):
        (tmp_path / "a.html").write_text("x", encoding="utf-8")
        r = mg.gate_entry("某决策", "file:a.html;file:missing.html", "某客户",
                          strict=True, base_dir=str(tmp_path))
        assert r["verdict"] == "blocked"
        assert len(r["reasons"]) == 1
        assert r["reasons"][0] == "文件不存在: missing.html"


# ============================================================
# normalize_status
# ============================================================
class TestNormalizeStatus:
    def test_confirmed(self):
        assert mg.normalize_status("已确认") == "已确认"
        assert mg.normalize_status("客户已确认该口径") == "已确认"
        assert mg.normalize_status("确认过") == "已确认"

    def test_unconfirmed(self):
        assert mg.normalize_status("未确认") == "未确认"
        assert mg.normalize_status("待确认") == "未确认"
        assert mg.normalize_status("待核实") == "未确认"

    def test_unreadable_preserved(self):
        assert mg.normalize_status("不可读(PDF加密)") == "不可读(PDF加密)"

    def test_not_exists(self):
        assert mg.normalize_status("不存在") == "不存在"
        assert mg.normalize_status("客户没有该产品") == "不存在"

    def test_none_and_empty(self):
        assert mg.normalize_status(None) == "未确认"
        assert mg.normalize_status("") == "未确认"
        assert mg.normalize_status("   ") == "未确认"

    def test_unmatched_returns_original(self):
        assert mg.normalize_status("部分材料已提供") == "部分材料已提供"


# ============================================================
# detect_conflict
# ============================================================
class TestDetectConflict:
    def _write(self, tmp_path, text):
        p = tmp_path / "decisions.md"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_no_same_topic(self, tmp_path):
        p = self._write(tmp_path, "## [2026-08-17] 其他主题\n- **决策**: A\n")
        r = mg.detect_conflict("某主题", "B", p)
        assert r["conflict"] is False
        assert r["old_date"] is None

    def test_same_topic_same_content(self, tmp_path):
        p = self._write(tmp_path, "## [2026-08-17] 某主题\n- **决策**: A\n")
        r = mg.detect_conflict("某主题", "A", p)
        assert r["conflict"] is False

    def test_same_topic_diff_content(self, tmp_path):
        p = self._write(tmp_path, "## [2026-08-17] 某主题\n- **决策**: A\n- **理由**: x\n")
        r = mg.detect_conflict("某主题", "B", p)
        assert r["conflict"] is True
        assert r["old_date"] == "2026-08-17"
        assert "某主题" in r["old_heading"]

    def test_missing_file(self, tmp_path):
        r = mg.detect_conflict("某主题", "B", str(tmp_path / "none.md"))
        assert r["conflict"] is False

    def test_topic_whitespace_ignored(self, tmp_path):
        p = self._write(tmp_path, "## [2026-08-17] 某主题\n- **决策**: A\n")
        r = mg.detect_conflict("  某主题  ", "B", p)
        assert r["conflict"] is True


# ============================================================
# count_pending_conflicts
# ============================================================
class TestCountPendingConflicts:
    def test_count(self, tmp_path):
        p = tmp_path / "decisions.md"
        p.write_text("<!-- conflict: pending -->\n<!-- conflict: pending -->\n", encoding="utf-8")
        assert mg.count_pending_conflicts(str(p)) == 2

    def test_zero(self, tmp_path):
        p = tmp_path / "decisions.md"
        p.write_text("无标记\n", encoding="utf-8")
        assert mg.count_pending_conflicts(str(p)) == 0

    def test_missing(self, tmp_path):
        assert mg.count_pending_conflicts(str(tmp_path / "none.md")) == 0


# ============================================================
# scan_memory_health
# ============================================================
class TestScanMemoryHealth:
    def test_full(self, tmp_path):
        d = tmp_path / "某客户"
        d.mkdir()
        (d / "context.md").write_text(
            "### [2026-08-17] 第 1 次会话\n"
            "#### 关键决策\nx（待补证据）\n"
            "### [2026-08-18] 第 2 次会话\n"
            "#### 关键决策\ny（证据待核：文件不存在）\n"
            "#### 证据\n[✓] file:a\n",
            encoding="utf-8",
        )
        (d / "decisions.md").write_text(
            "## 决策 1：标题\n- **决策内容**：x\n"
            "## [2026-08-18] 某主题\n- **决策**: y\n"
            "<!-- conflict: pending -->\n",
            encoding="utf-8",
        )
        r = mg.scan_memory_health("某客户", client_dir=str(d))
        assert r["client"] == "某客户"
        assert r["context_exists"] is True
        assert r["decisions_exists"] is True
        assert r["sessions"] == 2
        assert r["evidence_sections"] == 1
        assert r["pending_evidence"] == 1
        assert r["unverified_evidence"] == 1
        assert r["decision_entries"] == 2  # 1 手写 + 1 程序化
        assert r["conflicts_pending"] == 1

    def test_missing_files(self, tmp_path):
        r = mg.scan_memory_health("某客户", client_dir=str(tmp_path / "none"))
        assert r["context_exists"] is False
        assert r["decisions_exists"] is False
        assert r["sessions"] == 0
        assert r["evidence_sections"] == 0
        assert r["decision_entries"] == 0
        assert r["conflicts_pending"] == 0
