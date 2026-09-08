# -*- coding: utf-8 -*-
"""I-7 S15 域禁令机械检查测试（_domain_guard.check_domain_bans + verify 接线）。"""

from _domain_guard import DOMAIN_BANS, check_domain_bans


class TestRuleTable:
    def test_ten_rules_formalized(self):
        assert len(DOMAIN_BANS) == 10
        ids = [r["id"] for r in DOMAIN_BANS]
        assert len(set(ids)) == 10
        for r in DOMAIN_BANS:
            assert r["source"] and r["ban"]
            assert callable(r["detect"])

    def test_manual_rules_do_not_false_positive(self):
        # 语义规则默认不自动命中（避免误伤）
        hits = check_domain_bans("行业模板直接套用了他行业的内容，客户事实张冠李戴，归档画成文件柜")
        assert all(not h["manual"] for h in hits)

    def test_include_manual_lists_semantic_rules(self):
        hits = check_domain_bans("", include_manual=True)
        manual = [h for h in hits if h["manual"]]
        assert len(manual) >= 3  # DB-05/09/10 等语义规则


class TestMechanicalDetection:
    def test_db01_blueprint_without_design_principles(self):
        text = "本方案包括现状分析、蓝图与实施路径三部分。"  # 蓝图无设计原则
        hits = {h["id"] for h in check_domain_bans(text)}
        assert "DB-01" in hits

    def test_db02_all_fit_no_gap(self):
        text = "系统全部适配，100% 匹配现有流程。"
        hits = {h["id"] for h in check_domain_bans(text)}
        assert "DB-02" in hits

    def test_db04_blueprint_without_gap_route(self):
        text = "以下是整体蓝图，包含目标架构。"
        hits = {h["id"] for h in check_domain_bans(text)}
        assert "DB-04" in hits

    def test_db08_rpa_ocr_without_capability_catalog(self):
        text = "本方案内置 RPA 与 OCR 能力，覆盖票据识别。"
        hits = {h["id"] for h in check_domain_bans(text)}
        assert "DB-08" in hits

    def test_clean_text_no_hits(self):
        text = ("本方案先明确设计原则，再给出现状数据（12 个系统）与差距分析，"
                "Gap 逐条带处理方式，最后是分期实施路线。预算按软件/实施双列"
                "并说明估法口径。RPA 能力以 E9 能力目录校验后进入组件映射。")
        hits = check_domain_bans(text)
        assert hits == []


class TestVerifyHook:
    def test_verify_html_annotates_domain_bans(self, tmp_path, monkeypatch):
        """verify_html 观察模式把域禁令命中附到 msg（不阻断）。"""
        from _verify import verify_html
        html = tmp_path / "方案.html"
        # 含蓝图但无设计原则/差距/路线 -> DB-01/DB-04 应命中；正文补足 > MIN_HTML_SIZE(500)
        body = "<h1>整体蓝图</h1><p>本方案展示目标架构与总体设计思路。</p>" + \
            "<p>" + ("系统能力建设需要围绕客户业务目标展开。" * 8) + "</p>"
        html.write_text(
            "<!DOCTYPE html><html><head><style>body{font-family:sans-serif}</style></head>"
            f"<body>{body}</body></html>",
            encoding="utf-8")
        ok, msg = verify_html(str(html))
        assert ok is True  # 不阻断
        assert "域禁令" in msg
        assert "DB-01" in msg or "DB-04" in msg
