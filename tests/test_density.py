# -*- coding: utf-8 -*-
"""A-5 渲染后密度/可读性检查测试（观察模式）。"""

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
        return check_density_html(str(out))

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
