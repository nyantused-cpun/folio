# -*- coding: utf-8 -*-
"""A-5 渲染后密度/可读性检查测试（观察模式）。"""

import os

import pytest


class TestDensityHtml:
    def _check(self, tmp_path, html):
        out = tmp_path / "t.html"
        out.write_text(html, encoding="utf-8")
        # 预检：无 playwright 时跳过（CI 友好）
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("playwright 未安装")
        from _density import check_density_html
        findings = check_density_html(str(out))
        # P3-1 flake 根因（R3-8，2026-09-08）：全量序资源压力下 Chrome 偶发启动
        # 失败，check_density_html 按降级契约返回单条「密度检查执行失败」（只报
        # 不判）——这是测量不可得，不是「无溢出」的实测结论，按 skip 处置而非
        # 让断言偶发 FAIL（71 轮复现 1 次，孤立复跑恒绿）。
        if any(str(f).startswith(("密度检查执行失败", "playwright 未安装"))
               for f in findings):
            pytest.skip(f"密度测量不可得（环境降级）: {findings}")
        return findings

    def test_overflow_detected(self, tmp_path):
        """窄容器 + 长文本 nowrap → 溢出 finding。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="width:100px;overflow:visible;white-space:nowrap">'
            '这是一段非常非常长绝对不会换行也不会被裁剪的文本内容测试'
            '</div></body></html>'
        )
        findings = self._check(tmp_path, html)
        assert any("溢出" in f for f in findings)

    def test_large_blank_detected(self, tmp_path):
        """body 固定高度 + 短内容 → 底部大空白 finding。"""
        html = (
            '<!DOCTYPE html><html><body style="height:2000px">'
            '<div>短内容</div>'
            '</body></html>'
        )
        findings = self._check(tmp_path, html)
        assert any("大空白" in f for f in findings)

    def test_low_contrast_detected(self, tmp_path):
        """浅黄文字白底 → 低对比度 finding。"""
        html = (
            '<!DOCTYPE html><html><body style="background:#ffffff">'
            '<div style="color:#ffff00">浅色文字</div>'
            '</body></html>'
        )
        findings = self._check(tmp_path, html)
        assert any("低对比度" in f for f in findings)

    def test_default_background_no_false_positive(self, tmp_path):
        """无显式背景（transparent）→ 回退白底，黑字不误报低对比度。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div>黑色文字</div>'
            '</body></html>'
        )
        findings = self._check(tmp_path, html)
        assert not any("低对比度" in f for f in findings)

    def test_missing_file(self, tmp_path):
        from _density import check_density_html
        findings = check_density_html(str(tmp_path / "不存在.html"))
        assert len(findings) == 1 and "文件不存在" in findings[0]

    def test_no_playwright_degrades(self, tmp_path, monkeypatch):
        """playwright 不可用 → 单条降级提示，不抛异常。"""
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *a, **k):
            if name.startswith("playwright"):
                raise ImportError("no playwright")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        out = tmp_path / "t.html"
        out.write_text("<!DOCTYPE html><html></html>", encoding="utf-8")
        from _density import check_density_html
        findings = check_density_html(str(out))
        assert len(findings) == 1 and "playwright 未安装" in findings[0]

    def test_overlap_detected(self, tmp_path):
        """两个卡片级元素边界框相交 → 重叠 finding（ZSW R6，D-120）。"""
        html = (
            '<!DOCTYPE html><html><body style="position:relative">'
            '<div style="position:absolute;left:0;top:0;width:200px;height:100px">卡片A</div>'
            '<div style="position:absolute;left:100px;top:50px;width:200px;height:100px">卡片B</div>'
            '</body></html>'
        )
        findings = self._check(tmp_path, html)
        assert any("重叠" in f for f in findings)

    def test_overlap_parent_child_exempt(self, tmp_path):
        """父子包含关系（文字在卡片内）不误报重叠。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="width:300px;height:120px">'
            '<span style="width:200px;height:60px;display:block">内部文字</span>'
            '</div></body></html>'
        )
        findings = self._check(tmp_path, html)
        assert not any("重叠" in f for f in findings)

    def test_single_font_size_reported(self, tmp_path):
        """全页仅 1 档字号 → 字号层级 finding（ZSW R9/R13，D-120）。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="font-size:16px">标题文字</div>'
            '<p style="font-size:16px">正文内容</p>'
            '</body></html>'
        )
        findings = self._check(tmp_path, html)
        assert any("字号层级" in f for f in findings)

    def test_result_is_iterable_list(self, tmp_path):
        """DensityResult 保持 list 行为，现有调用方可遍历/切片/len。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="width:100px;overflow:visible;white-space:nowrap">'
            '很长很长很长很长很长很长很长很长很长很长很长很长的文本'
            '</div></body></html>'
        )
        findings = self._check(tmp_path, html)
        assert isinstance(findings, list)
        assert len(findings) >= 1
        assert any("溢出" in f for f in findings)


class TestDensityStructuredResult:
    """新结构化返回字段（level / blocked / metrics / screenshots）。"""

    def _run(self, tmp_path, html, gate="verify"):
        out = tmp_path / "t.html"
        out.write_text(html, encoding="utf-8")
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("playwright 未安装")
        from _density import check_density_html
        return check_density_html(str(out), gate=gate)

    def test_standard_page_warn_level(self, tmp_path):
        """标准页 finding 仅 warn，不 blocked。"""
        html = (
            '<!DOCTYPE html><html><body style="height:2000px">'
            '<div>短内容</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert res.level == "warn"
        assert res.blocked is False
        assert not res.blocked_findings
        assert "whitespace_ratio" in res.metrics

    def test_crafted_page_detected(self, tmp_path):
        """带 data-track="crafted" 的容器被识别为 crafted 页。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div data-track="crafted" style="font-size:24px">定制页标题</div>'
            '<p style="font-size:14px">定制页正文</p>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert res.level == "ok"
        assert res.blocked is False

    def test_crafted_font_size_floor_blocks(self, tmp_path):
        """crafted 页字号 < 12px 触发阻断级 finding。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div data-track="crafted" style="font-size:10px">小字</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert any("字号底线" in f for f in res)
        assert res.level == "fail"
        assert res.blocked is True
        assert any("字号底线" in f for f in res.blocked_findings)

    def test_crafted_overflow_blocks(self, tmp_path):
        """crafted 页文字溢出触发阻断。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div data-track="crafted" style="width:50px;overflow:visible;white-space:nowrap">'
            '这是一段非常非常长绝对不会换行也不会被裁剪的文本内容测试'
            '</div></body></html>'
        )
        res = self._run(tmp_path, html)
        assert any("溢出" in f for f in res)
        assert res.blocked is True

    def test_crafted_overlap_blocks(self, tmp_path):
        """crafted 页元素重叠触发阻断。"""
        html = (
            '<!DOCTYPE html><html><body style="position:relative">'
            '<div data-track="crafted" style="position:absolute;left:0;top:0;width:200px;height:100px">'
            '卡片A</div>'
            '<div style="position:absolute;left:100px;top:50px;width:200px;height:100px">卡片B</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert any("重叠" in f for f in res)
        assert res.blocked is True

    def test_crafted_low_contrast_blocks(self, tmp_path):
        """crafted 页低对比度阈值收紧到 4.5:1。"""
        # #808080 on white = 3.95:1，低于 4.5，高于 3.0
        html = (
            '<!DOCTYPE html><html><body style="background:#ffffff">'
            '<div data-track="crafted" style="color:#808080">中灰文字</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert any("低对比度" in f for f in res)
        assert res.blocked is True

    def test_standard_low_contrast_still_warn(self, tmp_path):
        """标准页低对比度仍用 3.0 阈值，仅 warn。"""
        html = (
            '<!DOCTYPE html><html><body style="background:#ffffff">'
            '<div style="color:#aaaaaa">浅灰文字</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert any("低对比度" in f for f in res)
        assert res.level == "warn"
        assert res.blocked is False

    def test_visual_intent_metrics_present(self, tmp_path):
        """C-G3 指标集：留白率/层级梯度/对齐偏差/HSL 和谐均返回。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="font-size:24px;margin:20px">标题</div>'
            '<p style="font-size:14px;margin:20px">正文内容</p>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert "whitespace_ratio" in res.metrics
        assert "hierarchy_gradient" in res.metrics
        assert "alignment_deviation" in res.metrics
        assert "hsl_harmony" in res.metrics
        hg = res.metrics["hierarchy_gradient"]
        assert "distinct_sizes" in hg
        assert "cv" in hg

    def test_deliver_gate_saves_screenshots(self, tmp_path):
        """gate="deliver" 使用多视口并截图存档。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="font-size:16px">交付门测试</div>'
            '</body></html>'
        )
        res = self._run(tmp_path, html, gate="deliver")
        # 两个视口应有两张截图
        assert len(res.screenshots) == 2
        for p in res.screenshots:
            assert os.path.exists(p)
            assert p.endswith(".png")

    def test_verify_gate_single_viewport_no_screenshots(self, tmp_path):
        """gate="verify"（默认）单视口且不截图。"""
        html = (
            '<!DOCTYPE html><html><body>'
            '<div style="font-size:24px">验证门标题</div>'
            '<p style="font-size:14px">验证门正文</p>'
            '</body></html>'
        )
        res = self._run(tmp_path, html)
        assert res.level == "ok"
        assert len(res.screenshots) == 0

    def test_no_playwright_degrades_returns_density_result(self, tmp_path, monkeypatch):
        """playwright 不可用时仍返回 DensityResult，不抛异常。"""
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *a, **k):
            if name.startswith("playwright"):
                raise ImportError("no playwright")
            return real_import(name, *a, **k)

        monkeypatch.setattr("builtins.__import__", _fake_import)
        out = tmp_path / "t.html"
        out.write_text("<!DOCTYPE html><html></html>", encoding="utf-8")
        from _density import check_density_html
        res = check_density_html(str(out))
        assert len(res) == 1 and "playwright 未安装" in res[0]
        assert res.level == "ok"
