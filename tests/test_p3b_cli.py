# -*- coding: utf-8 -*-
"""P3「CLI/报价」组回归测试（2026-09-06 清扫批次 B）。

覆盖五项：
1. _quote_gate Q1 数量数值化判空（数字字符串 "0" 不再绕过）
2. _quote_data/_quote_html description None 容错（空串降级）
3. _cli_cmds_mem compact：project null 条目守卫 + 全局 task_history 写入时序保持
4. _cli_guards post_check 扩展名 lower() 归一（.HTML 不再跳过主题覆盖检查）
5. _cli_cmds_gen word-com polish 失败步骤如实上报（exit 1，不静默完成）
"""
import json
import types

import pytest

import _cli_cmds_gen
import _cli_cmds_mem
import _cli_guards


# ---------------------------------------------------------------------------
# P3：_quote_gate Q1 数量数值化判空
# ---------------------------------------------------------------------------

def _write_quote_spec(path, quantities):
    """构造最小报价 spec：一个 section，多行 items（quantity 逐行给定）。"""
    items = [{"name": f"行{i}", "quantity": q, "unit": "套"}
             for i, q in enumerate(quantities)]
    lines = ["quote:", "  client: 测试客户", "  tax_rate: 0.06", "  sheets:",
             "    - sections:",
             "        - id: modules", "          items:"]
    for it in items:
        q = it["quantity"]
        q_repr = repr(q) if not isinstance(q, str) else json.dumps(q, ensure_ascii=False)
        lines.append(f"            - {{name: {json.dumps(it['name'], ensure_ascii=False)}, "
                     f"quantity: {q_repr}, unit: 套}}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestQuoteGateQ1NumericString(object):
    def test_numeric_string_zero_flagged(self, tmp_path):
        from _quote_gate import check_build
        spec = _write_quote_spec(tmp_path / "quote.yml", ["0", 0])
        issues = check_build(str(spec))
        # "0"（数字字符串）与数字 0 同样拦截——旧代码 isinstance 判定漏掉字符串
        assert len(issues) == 2 and all("Q1" in i for i in issues)

    def test_numeric_string_negative_flagged(self, tmp_path):
        from _quote_gate import check_build
        spec = _write_quote_spec(tmp_path / "quote.yml", ["-2"])
        issues = check_build(str(spec))
        assert len(issues) == 1 and "Q1" in issues[0]

    def test_numeric_string_positive_passes(self, tmp_path):
        from _quote_gate import check_build
        spec = _write_quote_spec(tmp_path / "quote.yml", ["2", " 3 "])
        issues = check_build(str(spec))
        assert issues == []

    def test_non_numeric_and_missing_flagged(self, tmp_path):
        from _quote_gate import check_build
        spec = _write_quote_spec(tmp_path / "quote.yml", ["若干", None])
        issues = check_build(str(spec))
        # 非数字/缺失数量同样记 Q1（数值化失败按缺失处理）
        assert len(issues) == 2 and all("Q1" in i for i in issues)


# ---------------------------------------------------------------------------
# P3：description None 容错（数据层空串降级 + 渲染层不崩）
# ---------------------------------------------------------------------------

class _StubLibrary(object):
    """库存根：条目 description 显式为 null（YAML `description:` 空值场景）。"""

    def get(self, item_id):
        return {"id": "m1", "name": "模块A", "description": None}

    def find_by_name(self, name):
        return None


class TestQuoteDescriptionNone(object):
    def test_resolve_item_null_description_becomes_empty(self):
        from _quote_data import QuoteBuilder
        builder = QuoteBuilder(library=_StubLibrary())
        item = builder._resolve_item({"id": "m1"}, 1, 1.0, "modules")
        # 旧代码 lib.get("description", "") 对显式 None 不兜底 → Item.description=None
        assert item.description == ""

    def test_render_html_with_none_description(self):
        from _quote_data import Item, QuoteData, Section
        from _quote_html import render_html
        qd = QuoteData()
        qd.metadata = {"client": "测试客户"}
        sec = Section(title="模块", headers=["编号", "名称", "描述", "单价", "折扣", "数量", "金额"])
        sec.items = [Item(index=1, name="模块A", description=None,
                          unit_price=100, quantity=2, amount=200)]
        sec.total_label = "小计"
        sec.total_amount = 200
        qd.sections = [sec]
        qd.summary = [(sec.title, 200)]
        qd.summary_total = 200
        # 旧代码 it.description[:60] 对 None 切片 TypeError
        html = render_html(qd)
        assert "模块A" in html
        assert "200" in html  # 合计/金额仍在

    def test_render_html_long_description_truncated(self):
        from _quote_data import Item, QuoteData, Section
        from _quote_html import render_html
        qd = QuoteData()
        qd.metadata = {}
        sec = Section(title="模块", headers=["编号", "名称", "描述", "单价", "折扣", "数量", "金额"])
        sec.items = [Item(index=1, name="模块B", description="长" * 80, amount=1)]
        sec.total_label = "小计"
        sec.total_amount = 1
        qd.sections = [sec]
        html = render_html(qd)
        assert "…" in html  # 超长截断省略号仍生效


# ---------------------------------------------------------------------------
# P3：compact null 守卫 + 全局写入时序保持
# ---------------------------------------------------------------------------

class TestCompactTaskHistory(object):
    def _write_history(self, logs_dir):
        history = [
            {"project": None, "action": "null条目"},
            {"project": "client:甲", "action": "甲1"},
            {"project": "client:乙", "action": "乙1"},
            {"project": "client:甲", "action": "甲2"},
            {"project": "client:乙", "action": "乙2"},
            {"project": "client:甲", "action": "甲3"},
        ]
        path = logs_dir / "task_history.json"
        path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        return path

    def test_compact_tolerates_null_project_and_keeps_order(self, monkeypatch, tmp_path):
        import _context
        import _paths

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (tmp_path / "clients" / "甲").mkdir(parents=True)
        monkeypatch.setattr(_paths, "LOGS_DIR", str(logs_dir))
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(tmp_path / "clients"))
        history_path = self._write_history(logs_dir)
        monkeypatch.setattr(_context, "compact", lambda client, keep_last=1: None)

        args = types.SimpleNamespace(client="甲", keep=2, keep_sessions=0)
        # 旧代码：project 为 null 的条目触发 AttributeError（None.replace）
        _cli_cmds_mem.cmd_compact(args)

        after = json.loads(history_path.read_text(encoding="utf-8"))
        actions = [r.get("action") for r in after]
        # 甲1 被删（keep=2），甲2/甲3 保留
        assert "甲1" not in actions
        assert actions.count("甲2") == 1 and actions.count("甲3") == 1
        # null 条目原位保留（未因守卫被误删）
        assert actions[0] == "null条目"
        # 写入时序保持：甲2 仍在 乙2 之前（旧代码 other+kept 会把保留条目搬到列表尾）
        assert actions.index("甲2") < actions.index("乙2")

    def test_compact_no_need_keeps_file_untouched(self, monkeypatch, tmp_path):
        import _context
        import _paths

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (tmp_path / "clients" / "甲").mkdir(parents=True)
        monkeypatch.setattr(_paths, "LOGS_DIR", str(logs_dir))
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(tmp_path / "clients"))
        history_path = self._write_history(logs_dir)
        monkeypatch.setattr(_context, "compact", lambda client, keep_last=1: None)

        args = types.SimpleNamespace(client="甲", keep=10, keep_sessions=0)
        _cli_cmds_mem.cmd_compact(args)
        after = json.loads(history_path.read_text(encoding="utf-8"))
        assert len(after) == 6  # 无需压缩时不落盘重排


# ---------------------------------------------------------------------------
# P3：post_check 扩展名大小写归一
# ---------------------------------------------------------------------------

class TestPostCheckExtensionCase(object):
    def test_uppercase_html_extension_still_checked(self, monkeypatch, tmp_path, capsys):
        import _theme_guard

        monkeypatch.setattr(_theme_guard, "pre_check",
                            lambda client: {"themes": ["铁律A"]})
        monkeypatch.setattr(_theme_guard, "check_coverage",
                            lambda text, themes: {"missing": [], "covered": ["铁律A"]})
        out = tmp_path / "报告.HTML"
        out.write_text("<html></html>", encoding="utf-8")
        # 旧代码：.HTML 大写扩展名直接 return，主题覆盖检查被静默跳过
        # 新代码：进入检查并打印覆盖结果，且不因覆盖通过而退出
        _cli_guards._run_post_check(str(out), client_name="测试客户")
        assert "已覆盖" in capsys.readouterr().out

    def test_non_html_still_skipped(self, monkeypatch, tmp_path, capsys):
        import _theme_guard

        checked = []
        monkeypatch.setattr(_theme_guard, "pre_check",
                            lambda client: checked.append(client) or {"themes": ["铁律A"]})
        out = tmp_path / "方案.PPTX"
        out.write_bytes(b"PK")
        _cli_guards._run_post_check(str(out), client_name="测试客户")
        assert checked == []  # 非 HTML（含大写）仍跳过
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# P3：word-com polish 失败步骤如实上报
# ---------------------------------------------------------------------------

class TestWordComPolishReporting(object):
    def _stub_steps(self, monkeypatch, results):
        import _renderer.docx_com_postprocess as post

        monkeypatch.setattr(post, "normalize_headings", lambda p: results["normalize"])
        monkeypatch.setattr(post, "renumber_headings",
                            lambda p, style="chinese_multi": results["renumber"])
        monkeypatch.setattr(post, "apply_style_set",
                            lambda p, style_set="bid": results["style_set"])
        monkeypatch.setattr(post, "apply_headers_footers",
                            lambda p, project_name="", dark_bid=False: results["headers"])
        monkeypatch.setattr(post, "refresh_toc", lambda p: results["toc"])
        monkeypatch.setattr(post, "save_as_pdf", lambda p, pdf_path=None: results.get("pdf", True))

    def _args(self, tmp_path, pdf=False):
        doc = tmp_path / "标书.docx"
        doc.write_bytes(b"PK\x03\x04")
        return types.SimpleNamespace(word_com_cmd="polish", file=str(doc),
                                     style_set="bid", project_name="", pdf=pdf)

    def test_polish_failed_step_exits_1(self, monkeypatch, tmp_path, capsys):
        results = {"normalize": True, "renumber": False, "style_set": True,
                   "headers": True, "toc": True}
        self._stub_steps(monkeypatch, results)
        with pytest.raises(SystemExit) as ei:
            _cli_cmds_gen.cmd_word_com(self._args(tmp_path))
        # 旧代码：失败不记账仍打印"polish 完成"并 exit 0
        assert ei.value.code == 1
        out = capsys.readouterr().out
        assert "失败 1 个步骤" in out and "renumber" in out

    def test_polish_multiple_failed_steps_listed(self, monkeypatch, tmp_path, capsys):
        results = {"normalize": False, "renumber": True, "style_set": True,
                   "headers": False, "toc": True, "pdf": False}
        self._stub_steps(monkeypatch, results)
        with pytest.raises(SystemExit) as ei:
            _cli_cmds_gen.cmd_word_com(self._args(tmp_path, pdf=True))
        assert ei.value.code == 1
        out = capsys.readouterr().out
        assert "失败 3 个步骤" in out
        assert "normalize" in out and "headers_footers" in out and "pdf" in out

    def test_polish_all_ok_reports_done_without_exit(self, monkeypatch, tmp_path, capsys):
        results = {"normalize": True, "renumber": True, "style_set": True,
                   "headers": True, "toc": True}
        self._stub_steps(monkeypatch, results)
        _cli_cmds_gen.cmd_word_com(self._args(tmp_path))  # 不抛 SystemExit
        out = capsys.readouterr().out
        assert "polish 完成" in out and "失败" not in out
