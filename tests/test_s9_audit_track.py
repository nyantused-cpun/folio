# -*- coding: utf-8 -*-
"""S9 阶段 2b audit 轨一致性检查回归（_cli_audit_track，C-G2）。

三态探针（开发计划 §四 2b 验收：合规/越轨/游离），全部 tmp_path 封闭
（audit 测试封闭化先例：test_audit_debt_cost / test_audit_behavior_mode），
不依赖仓库真实 output/ 与真实 review_log。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _cli_audit_track import REVIEW_WINDOW, _audit_track, analyze_track, check_review_record


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


# ---- 页骨架工厂（模拟 renderer 双形态页容器 + crafted 边界标记） ----

def _page(pid, body, crafted=False, layout="v2-page"):
    mark = ('\n    <div class="raw-html-crafted" data-track="crafted">'
            '<p style="color:#0F172A"><svg><path d="M0 0L9 9"/></svg></p></div>'
            if crafted else "")
    return f'    <section class="{layout}" id="{pid}">{mark}\n{body}\n    </section>'


STD_CLEAN = _page("p01", '<h3>标准页</h3><p style="color:var(--t-primary)">正文</p>')
STD_HEX = _page("p02", '<p style="color:#FF0000;">越轨红</p>')
STD_SVG = _page("p03", '<svg width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>')
DIAGRAM_SVG = _page("p04",
                    '<section class="diagram" data-diagram-type="architecture"'
                    ' data-subtype="tree"><svg><rect/></svg></section>')


def _doc(*pages, head='<style>:root{--t-primary:#3182ce;}</style><!-- #FFFFFF 注释 -->'):
    return ("<!DOCTYPE html>\n<html><head>" + head + "</head><body>\n"
            + "\n".join(pages) + "\n</body></html>")


def _deck(tmp_path, name, text, client="甲客户"):
    d = tmp_path / "output" / client
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p


def _review_log(tmp_path, *entries):
    import json
    p = tmp_path / "review_log.json"
    p.write_text(json.dumps(list(entries), ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 合规态：双轨 deck 全干净 + crafted 产物已审
# ---------------------------------------------------------------------------

class TestCompliant:
    def test_dual_track_clean_deck(self):
        """双轨 deck：standard 页干净 + crafted 页 hex/手写 SVG 豁免 + diagram 容器 SVG 豁免。"""
        rep = analyze_track(_doc(STD_CLEAN, STD_CLEAN,
                                 DIAGRAM_SVG,
                                 _page("p09", "<p>定制表达</p>", crafted=True)))
        assert rep["has_crafted_mark"] is True
        assert rep["total_pages"] == 4 and rep["crafted_pages"] == 1
        assert rep["stray_hex"] == []
        assert rep["unmarked_svg"] == []

    def test_crafted_page_hex_and_svg_not_flagged(self):
        """crafted 轨表达豁免：crafted 页内裸 hex 与手写 SVG 都不判。"""
        rep = analyze_track(_doc(STD_CLEAN, _page("p09", "", crafted=True)))
        assert rep["stray_hex"] == [] and rep["unmarked_svg"] == []

    def test_handler_pass_with_review_record(self, tmp_path, capsys):
        """crafted 产物在 review_log 有记录（曾审口径，含 FAIL 也算）→ 检查通过。"""
        deck = _deck(tmp_path, "甲客户_方案_v1.html", _doc(STD_CLEAN, _page("p09", "", crafted=True)))
        _review_log(tmp_path, {"verdict": "FAIL", "file": str(deck), "client": "甲客户"})
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(tmp_path / "review_log.json")) is True
        out = capsys.readouterr().out
        assert "已审" in out and "verdict=FAIL" in out

    def test_empty_output_dir_degrades_pass(self, tmp_path, capsys):
        """output/ 不存在：空转通过（不报错不 FAIL）。"""
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(tmp_path / "review_log.json")) is True
        assert "空转通过" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 越轨态：游离 hex / 无标记手写 SVG / crafted 无 review 记录
# ---------------------------------------------------------------------------

class TestViolating:
    def test_stray_hex_in_standard_page(self):
        """standard 页内联 style 裸 hex → 判出（页 id + 值 + 位置）。"""
        rep = analyze_track(_doc(STD_CLEAN, STD_HEX, _page("p09", "", crafted=True)))
        assert rep["stray_hex"] == [("p02", "#FF0000", "<p style>")]

    def test_unmarked_svg_in_standard_page(self):
        """standard 页手写 SVG（不在 diagram 容器内）→ 判出。"""
        rep = analyze_track(_doc(STD_CLEAN, STD_SVG, _page("p09", "", crafted=True)))
        assert rep["unmarked_svg"] == ["p03"]

    def test_handler_fails_on_violations(self, tmp_path, capsys):
        """游离 hex + 无标记 SVG + crafted 无 review 记录 → 三项 FAIL，返回 False。"""
        _deck(tmp_path, "甲客户_方案_v1.html",
              _doc(STD_CLEAN, STD_HEX, STD_SVG, _page("p09", "", crafted=True)))
        _review_log(tmp_path)  # 空 review_log
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(tmp_path / "review_log.json")) is False
        out = capsys.readouterr().out
        assert "游离 hex #FF0000" in out
        assert "无标记手写 SVG" in out and "p03" in out
        assert "未经 review 即交付" in out

    def test_review_record_outside_window_not_counted(self, tmp_path):
        """曾审窗口 = 近 N 条：记录被挤出窗口视同未审。"""
        deck = _deck(tmp_path, "甲客户_方案_v1.html", _doc(STD_CLEAN, _page("p09", "", crafted=True)))
        newer = [{"verdict": "PASS", "file": f"output/其他_{i}.html"}
                 for i in range(REVIEW_WINDOW)]
        reviewed, _ = check_review_record(str(deck), newer + [{"verdict": "PASS", "file": str(deck)}])
        assert reviewed is True   # 记录在窗口内（末条）
        reviewed, _ = check_review_record(str(deck), [{"verdict": "PASS", "file": str(deck)}] + newer)
        assert reviewed is False  # 记录沉到窗口外（第 1 条，其后恰有 N 条新记录）


# ---------------------------------------------------------------------------
# 游离态（零误报门）：运行时注入面 / diagram 容器 / 存量纯 standard deck
# ---------------------------------------------------------------------------

class TestZeroFalsePositive:
    def test_style_script_comment_hex_exempt(self):
        """<style> 主题 token、<script>（editor.js 注入形态）、注释内 hex 一律不判。"""
        head = ('<style>:root{--t-primary:#3182ce;--t-hero-from:#0A1540;}</style>'
                '<script>var editorCfg = {color:"#fff"};</script>'
                '<!-- editor.css 内联预览 #FAFAFA -->')
        rep = analyze_track(_doc(STD_CLEAN, head=head))
        assert rep["stray_hex"] == []

    def test_svg_in_diagram_section_exempt(self):
        """diagram 元素渲染容器（theme.section_open）内 SVG 不判手写。"""
        rep = analyze_track(_doc(STD_CLEAN, DIAGRAM_SVG))
        assert rep["unmarked_svg"] == []

    def test_pure_standard_deck_not_deep_scanned(self, tmp_path, capsys):
        """存量纯 standard deck（无 crafted 标记，存量带内联 hex/裸 SVG）零打扰。"""
        _deck(tmp_path, "东方航空_4A架构图_v1.html",
              _doc(_page("p01", '<p style="color:#C53030">存量</p><svg><rect/></svg>')))
        _review_log(tmp_path)
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(tmp_path / "review_log.json")) is True
        out = capsys.readouterr().out
        assert "✗" not in out and "纯 standard 1" in out

    def test_hex_outside_page_sections_not_attributed(self):
        """文档级区域（页容器之外）的 hex 不归属 standard 页，不判（宁缺毋滥）。"""
        rep = analyze_track(_doc(STD_CLEAN) + '<footer style="color:#888">页脚</footer>')
        assert rep["stray_hex"] == []


# ---------------------------------------------------------------------------
# 占比告警（warn 级，不 FAIL）与 CLI 分发面
# ---------------------------------------------------------------------------

class TestRatioAndDispatch:
    def test_ratio_over_half_warns_not_fails(self, tmp_path, capsys):
        """crafted 页过半 → ⚠ 警告级；警告不影响返回 True。"""
        _deck(tmp_path, "甲客户_方案_v1.html",
              _doc(_page("p01", "", crafted=True), _page("p02", "", crafted=True),
                   _page("p03", "", crafted=True), STD_CLEAN))
        deck = tmp_path / "output" / "甲客户" / "甲客户_方案_v1.html"
        _review_log(tmp_path, {"verdict": "PASS", "file": str(deck)})
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(tmp_path / "review_log.json")) is True
        out = capsys.readouterr().out
        assert "⚠" in out and "3/4" in out and "警告级" in out

    def test_corrupted_review_log_fails(self, tmp_path):
        """review_log 解析失败是真问题 → FAIL（对齐 behavior 损坏语义）。"""
        _deck(tmp_path, "甲客户_方案_v1.html", _doc(STD_CLEAN, _page("p09", "", crafted=True)))
        bad = tmp_path / "review_log.json"
        bad.write_text("{broken", encoding="utf-8")
        assert _audit_track(output_dir=str(tmp_path / "output"),
                            review_log_path=str(bad)) is False

    def test_track_mode_dispatched_not_unknown(self, monkeypatch, capsys):
        """--mode track 走 handler，不落「未知审计模式」continue（behavior 先例）。"""
        import _cli_audit
        called = {}
        monkeypatch.setattr(_cli_audit, "_audit_track",
                            lambda: called.setdefault("hit", True))
        args = type("Args", (), {"mode": "track", "client": None})()
        with pytest.raises(SystemExit) as ei:
            _cli_audit.cmd_audit(args)
        assert ei.value.code == 0
        assert called.get("hit") is True
        assert "未知审计模式" not in capsys.readouterr().out

    def test_track_in_all_modes(self):
        """--mode all 聚合含 track（2b 要求挂进 all）。"""
        import inspect
        import _cli_audit
        src = inspect.getsource(_cli_audit.cmd_audit)
        assert '"track"' in src.split("modes = [")[1].split("]")[0]

    def test_handler_lives_in_dedicated_module(self):
        """体量棘轮拆分钉子：_cli_audit 引用面同对象（monkeypatch 路径不迁移）。"""
        import _cli_audit
        import _cli_audit_track
        assert _cli_audit._audit_track is _cli_audit_track._audit_track
