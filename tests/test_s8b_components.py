# -*- coding: utf-8 -*-
import pytest
"""S8 Wave B · C-E2 三件套 + C-E3 duo_compare 语义强化 + C-E4 qa 官方绿。

覆盖：
- sla_block / profile_card / logo_wall：normalize/schema/HTML 渲染/DOCX 降级/
  PPTD 原生形状 + 图片资产缺失文字牌兜底
- duo_compare：tone before/after + metrics 量化对比行，存量 spec 无新字段不破
- qa_block 官方绿：主题 qa 语义槽（默认 #2D796A/#D6F0D7，gov_red 金系覆写）
  HTML CSS 变量与 PPTD 取色同源
- verify 脱敏提醒覆盖含图构件（profile_card/logo_wall）
"""
import os
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.elements import (
    CAPABILITIES,
    DEGRADE,
    is_empty_payload,
    normalize_element,
)
from _renderer.schema import validate_element

GOLD_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "gold_specs")


def _load(name):
    with open(os.path.join(GOLD_DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_spec(tmp_path, elements, client_name="示例"):
    spec = {
        "confirmed": True,
        "client_name": client_name,
        "document": {"title": "S8B 回归"},
        "pages": [{"id": "p1", "title": "S8B 页", "elements": elements}],
    }
    spec_path = os.path.join(str(tmp_path), "spec.yml")
    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True)
    return spec_path


def _render_html(spec_path):
    from _renderer import Renderer
    r = Renderer(spec_path)
    work_dir = os.path.join(SCRIPT_DIR, "output", "通用", "_s8b_test_work")
    os.makedirs(work_dir, exist_ok=True)
    html_path = os.path.join(work_dir, "out.html")
    r.render_html(html_path)
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    os.remove(html_path)
    try:
        os.rmdir(work_dir)
    except OSError:
        pass
    return r, html


# ---- C-E2：三件套协议层 ----


class TestTrioProtocol:
    """sla_block / profile_card / logo_wall：能力声明 + normalize + schema。"""

    def test_capabilities_declared(self):
        for t in ("sla_block", "profile_card", "logo_wall"):
            assert CAPABILITIES[t]["html"] == "render"
            assert CAPABILITIES[t]["docx"] == DEGRADE
            assert CAPABILITIES[t]["pptd"] == "render"

    def test_normalize_defaults(self):
        _, n = normalize_element({"type": "sla_block"})
        assert n == {"title": "", "items": []}
        _, n = normalize_element({"type": "profile_card"})
        assert n == {"title": "", "profiles": []}
        _, n = normalize_element({"type": "logo_wall"})
        assert n == {"title": "", "logos": []}

    def test_schema_required_fields(self):
        errs = validate_element({"type": "sla_block",
                                 "items": [{"name": "响应时限"}]})
        assert any("缺 value" in e for e in errs)
        errs = validate_element({"type": "profile_card",
                                 "profiles": [{"role": "PM"}]})
        assert any("缺 name" in e for e in errs)
        errs = validate_element({"type": "logo_wall",
                                 "logos": [{"src": "refs/a.png"}]})
        assert any("缺 name" in e for e in errs)

    def test_empty_payload(self):
        assert is_empty_payload("sla_block", {"items": []})
        assert is_empty_payload("profile_card", {"profiles": []})
        assert is_empty_payload("logo_wall", {"logos": []})
        assert not is_empty_payload("sla_block", {"items": [{"name": "a"}]})

    def test_degrade_text(self):
        from _renderer.elements import degrade_text
        assert "[服务承诺（SLA）×2]" in degrade_text(
            "sla_block", {"items": [{}, {}]}, "docx")
        assert "[项目团队：张三]" in degrade_text(
            "profile_card", {"profiles": [{"name": "张三"}]}, "docx")
        assert "[客户 logo 墙 ×3]" in degrade_text(
            "logo_wall", {"logos": [{}, {}, {}]}, "docx")


# ---- C-E2：三件套 HTML / DOCX / PPTD ----


class TestTrioRender:
    """三件套三端渲染路径。"""

    def test_gold_trio_html_renders(self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        elems = [_load("element__sla_block.yml"),
                 _load("element__profile_card.yml"),
                 _load("element__logo_wall.yml")]
        r, html = _render_html(_write_spec(tmp_path, elems))
        for cls in ("sla-card", "sla-value", "pcard-name", "pcard-avatar",
                    "lwall-cell", "lwall-name"):
            assert cls in html, cls
        assert "30 分钟" in html
        assert "张明" in html
        # 张明 photo（refs/团队-张明.png）在测试环境不存在 → 文字兜底 warn 预期内；
        # 不允许的是 skipped/degraded（静默丢失）
        assert not r.report.skipped and not r.report.degraded

    def test_logo_missing_asset_falls_back_to_name_plate(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        # gold 里只有 C/D/E/F 无 src，A/B 的 refs 图不存在 → 全部走文字牌
        elem = _load("element__logo_wall.yml")
        r, html = _render_html(_write_spec(tmp_path, [elem]))
        assert html.count("lwall-name") >= 6
        assert any("图片不存在" in w for w in r.report.warnings)
        assert not r.report.has_issues() or r.report.warnings

    def test_trio_docx_degrades(self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        elems = [_load("element__sla_block.yml"),
                 _load("element__profile_card.yml"),
                 _load("element__logo_wall.yml")]
        r = Renderer(_write_spec(tmp_path, elems))
        out = os.path.join(SCRIPT_DIR, "output", "通用", "_s8b_test_work",
                           "out.docx")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        r.render_docx(out)
        if os.path.exists(out):
            os.remove(out)
        try:
            os.rmdir(os.path.dirname(out))
        except OSError:
            pass
        degraded = {d["type"] for d in r.report.degraded}
        assert {"sla_block", "profile_card", "logo_wall"} <= degraded

    def test_trio_pptd_renders_shapes(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _pptd_gen import build_deck
        from _renderer.theme import resolve_theme
        elems = [_load("element__sla_block.yml"),
                 _load("element__profile_card.yml"),
                 _load("element__logo_wall.yml")]
        spec = {
            "confirmed": True,
            "client_name": "示例",
            "document": {"title": "S8B"},
            "pages": [{"id": "p1", "title": "S8B 页", "elements": elems[:1]}],
            # 三个大件一页会溢出拆页，单件单页足够验证分发与造型
        }
        spec["pages"].append(
            {"id": "p2", "title": "S8B 页", "elements": elems[1:2]})
        spec["pages"].append(
            {"id": "p3", "title": "S8B 页", "elements": elems[2:]})
        spec_path = os.path.join(SCRIPT_DIR, "output", "通用",
                                 "_s8b_test_work", "spec.yml")
        os.makedirs(os.path.dirname(spec_path), exist_ok=True)
        with open(spec_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec, f, allow_unicode=True)
        try:
            files, _ = build_deck(spec, spec_path,
                                  resolve_theme("consulting_kpmg"), "gold",
                                  os.path.join(SCRIPT_DIR, "output", "通用",
                                               "_s8b_test_work", "deck"),
                                  client_name="示例")
            all_pages = "\n".join(v for k, v in files.items()
                                  if k.startswith("pages/"))
            for tag in ("sla-0-v", "pfc-0-n", "lgw-0-n"):
                assert tag in all_pages, tag
        finally:
            for root, dirs, fs in os.walk(os.path.dirname(spec_path),
                                          topdown=False):
                for name in fs:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))


# ---- C-E3：duo_compare 语义强化 ----

_DUO = {
    "type": "duo_compare",
    "left": {"title": "现状", "tone": "before",
             "points": ["手工报账", "周期 5 天"]},
    "right": {"title": "目标", "tone": "after",
              "points": ["自动报账", "周期 1 天"]},
    "metrics": [{"label": "报账周期", "left": "5 天", "right": "1 天"}],
}


class TestDuoCompareSemantics:

    def test_legacy_spec_backward_compatible(self):
        """存量 spec 无 tone/metrics：normalize 补空、schema 零错、
        HTML 端不出现语义类。"""
        legacy = {"type": "duo_compare",
                  "left": {"title": "A", "points": ["a"]},
                  "right": {"title": "B", "points": ["b"]}}
        assert validate_element(legacy) == []
        _, n = normalize_element(legacy)
        assert n["left"]["tone"] == "" and n["metrics"] == []

    def test_tone_and_metrics_schema(self):
        assert validate_element(_DUO) == []
        bad = {"type": "duo_compare",
               "left": {"title": "A", "tone": "worse", "points": ["a"]},
               "right": {"title": "B", "points": ["b"]},
               "metrics": [{"left": "1", "right": "2"}]}
        errs = validate_element(bad)
        assert any("tone 非法值" in e for e in errs)
        assert any("metrics[0] 缺 label" in e for e in errs)

    def test_html_tone_classes_and_metrics_table(self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        r, html = _render_html(_write_spec(tmp_path, [_DUO]))
        assert "duo-before" in html and "duo-after" in html
        assert "duo-metrics" in html
        assert "报账周期" in html
        assert not r.report.has_issues()

    def test_pptd_metrics_rows_and_tone_bar(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _pptd_gen import build_deck
        from _renderer.theme import resolve_theme
        spec = {
            "confirmed": True,
            "client_name": "示例",
            "document": {"title": "S8B"},
            "pages": [{"id": "p1", "title": "S8B 页", "elements": [_DUO]}],
        }
        spec_path = os.path.join(SCRIPT_DIR, "output", "通用",
                                 "_s8b_test_work", "spec.yml")
        os.makedirs(os.path.dirname(spec_path), exist_ok=True)
        with open(spec_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec, f, allow_unicode=True)
        try:
            files, _ = build_deck(spec, spec_path,
                                  resolve_theme("consulting_kpmg"), "gold",
                                  os.path.join(SCRIPT_DIR, "output", "通用",
                                               "_s8b_test_work", "deck"),
                                  client_name="示例")
            page = files["pages/02_p1.page"]
            # before/after 语义 + 量化行 + after 侧主色竖条
            for tag in ("duo-bar1", "duo-m-hr", "duo-m-l0", "duo-m-vr0"):
                assert tag in page, tag
        finally:
            for root, dirs, fs in os.walk(os.path.dirname(spec_path),
                                          topdown=False):
                for name in fs:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))


# ---- C-E4：qa_block 官方绿 ----


class TestQaOfficialGreen:

    def test_theme_qa_slots_default(self):
        from _renderer.theme import DEFAULT_QA_SLOTS, THEMES, theme_tokens_css
        assert DEFAULT_QA_SLOTS == {"text": "#2D796A", "bg": "#D6F0D7"}
        for name in THEMES:
            css = theme_tokens_css(name)
            assert "--t-qa-text:" in css and "--t-qa-bg:" in css, name

    def test_gov_red_qa_override_no_red_green_clash(self):
        """gov_red 禁红配绿裁决：qa 槽覆写为赭金对，不用官方绿。"""
        from _renderer.theme import THEMES, theme_tokens_css
        assert THEMES["gov_red"]["qa"] == {"text": "#7A5A14",
                                           "bg": "#FBF5E7"}
        css = theme_tokens_css("gov_red")
        assert "--t-qa-text:#7A5A14" in css
        assert "#2D796A" not in css

    def test_pptd_theme_qa_colors_match_css(self):
        from _renderer.theme import pptd_theme, theme_tokens_css
        for name in ("consulting_kpmg", "gov_red"):
            colors = pptd_theme(name)["colors"]
            css = theme_tokens_css(name)
            assert f"--t-qa-text:{colors['qa_text']}" in css
            assert f"--t-qa-bg:{colors['qa_bg']}" in css

    def test_qa_block_uses_green_in_html(self, tmp_path, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        qa = {"type": "qa_block",
              "items": [{"q": "实施周期多长？", "a": "标准版 12 周上线。"}]}
        _, html = _render_html(_write_spec(tmp_path, [qa]))
        # CSS 变量落 tokens（--t-qa-* 发射）+ qa-item 消费变量
        assert "--t-qa-text:#2D796A" in html
        assert "var(--t-qa-text" in html

    def test_qa_block_uses_green_in_pptd(self, monkeypatch):
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _pptd_gen import build_deck
        from _renderer.theme import resolve_theme
        qa = {"type": "qa_block",
              "items": [{"q": "实施周期多长？", "a": "标准版 12 周上线。"}]}
        spec = {
            "confirmed": True,
            "client_name": "示例",
            "document": {"title": "S8B"},
            "pages": [{"id": "p1", "title": "S8B 页", "elements": [qa]}],
        }
        spec_path = os.path.join(SCRIPT_DIR, "output", "通用",
                                 "_s8b_test_work", "spec.yml")
        os.makedirs(os.path.dirname(spec_path), exist_ok=True)
        with open(spec_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec, f, allow_unicode=True)
        try:
            files, _ = build_deck(spec, spec_path,
                                  resolve_theme("consulting_kpmg"), "gold",
                                  os.path.join(SCRIPT_DIR, "output", "通用",
                                               "_s8b_test_work", "deck"),
                                  client_name="示例")
            page = files["pages/02_p1.page"]
            assert "#2D796A" in page and "#D6F0D7" in page
        finally:
            for root, dirs, fs in os.walk(os.path.dirname(spec_path),
                                          topdown=False):
                for name in fs:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))


# ---- C-E5 联动：脱敏提醒覆盖含图构件 ----


class TestDesensitizationCoversImageBearing:

    def test_spec_path_warns_for_logo_wall_and_profile_card(self):
        from _verify import _warn_screenshot_desensitization
        spec = {"pages": [{"elements": [
            {"type": "logo_wall",
             "logos": [{"name": "A", "src": "refs/logo.png"}]}]}]}
        assert _warn_screenshot_desensitization(spec=spec)
        spec = {"pages": [{"elements": [
            {"type": "profile_card",
             "profiles": [{"name": "张三", "photo": "refs/p.png"}]}]}]}
        assert _warn_screenshot_desensitization(spec=spec)
        # 无图构件不触发
        spec = {"pages": [{"elements": [{"type": "logo_wall",
                                         "logos": [{"name": "A"}]}]}]}
        assert not _warn_screenshot_desensitization(spec=spec)


# ---- S8-B 棘轮拆分钉死（b722f01 test_spec_hex_split_module_pinned 先例）----


def test_pptd_emit_chrome_split_module_pinned():
    """拆分钉死：chrome 构件发射器族住 pptd_emit_chrome/ext（cap 收紧 1606→720），
    pptd_emit 经 __getattr__ 懒加载转发保持 import 面。若有人把发射器搬回
    pptd_emit 或改掉转发面，此测试当场红。"""
    from _renderer.diagram import pptd_emit, pptd_emit_chrome, pptd_emit_ext
    # 实现住新模块
    assert pptd_emit_chrome.emit_chrome_pptd.__module__ == \
        "_renderer.diagram.pptd_emit_chrome"
    assert pptd_emit_chrome.emit_sla_block_pptd.__module__ == \
        "_renderer.diagram.pptd_emit_chrome"
    assert pptd_emit_ext.emit_ui_mock_pptd.__module__ == \
        "_renderer.diagram.pptd_emit_ext"
    # 旧入口懒加载转发（函数本体 + 模块属性双通道）
    assert pptd_emit.emit_chrome_pptd.__module__ == "_renderer.diagram.pptd_emit"
    assert pptd_emit.emit_stat_cards_pptd is pptd_emit_chrome.emit_stat_cards_pptd
    assert pptd_emit.emit_ui_mock_pptd is pptd_emit_ext.emit_ui_mock_pptd
    assert pptd_emit._CHROME_PPTD_EMITTERS is pptd_emit_chrome._CHROME_PPTD_EMITTERS
    # dispatch 行为不变：三件套全在 map 中
    for t in ("sla_block", "profile_card", "logo_wall"):
        assert t in pptd_emit._CHROME_PPTD_EMITTERS


def test_verify_desens_split_module_pinned():
    """拆分钉死：C-E5 脱敏扫描住 _verify_desens，_verify re-export 引用面不变。"""
    import _verify
    import _verify_desens
    assert _verify._warn_screenshot_desensitization is \
        _verify_desens._warn_screenshot_desensitization


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
