# -*- coding: utf-8 -*-
"""Renderer tests."""

import os
import tempfile
import pytest


class TestRendererImports:
    """测试 _renderer 模块的导入行为。"""

    def test_direct_import_raises_error(self, monkeypatch):
        """直接 import _renderer 应该抛出 NotInvokedViaCLIError。"""
        # 用 monkeypatch 保证本用例的环境前提，不再依赖其他测试“恰好”pop 过
        # 环境变量（原依赖 test_diagram.py 的污染行为，§七 2.8 根因修复）
        monkeypatch.delenv('_PRESALES_CLI_INVOKED', raising=False)
        assert '_PRESALES_CLI_INVOKED' not in os.environ
        
        try:
            from _renderer import NotInvokedViaCLIError
            from _renderer import Renderer
            
            spec_path = os.path.join(tempfile.gettempdir(), 'test_spec.yml')
            with open(spec_path, 'w', encoding='utf-8') as f:
                f.write('confirmed: true\n')
            
            with pytest.raises(NotInvokedViaCLIError):
                Renderer(spec_path)
                
        except ImportError as e:
            pytest.skip(f"_renderer 导入失败: {e}")

    def test_env_var_allows_import(self):
        """设置环境变量后可以正常导入。"""
        os.environ['_PRESALES_CLI_INVOKED'] = '1'
        
        try:
            from _renderer import Renderer
            
            spec_path = os.path.join(tempfile.gettempdir(), 'test_spec.yml')
            with open(spec_path, 'w', encoding='utf-8') as f:
                f.write('confirmed: true\n')
            
            r = Renderer(spec_path)
            assert r is not None
            assert r.spec == {'confirmed': True}
            
        finally:
            if '_PRESALES_CLI_INVOKED' in os.environ:
                del os.environ['_PRESALES_CLI_INVOKED']

    def test_unconfirmed_spec_raises_error(self):
        """未确认的 spec 应该抛出 RenderBlockedError。"""
        os.environ['_PRESALES_CLI_INVOKED'] = '1'
        
        try:
            from _renderer import RenderBlockedError
            from _renderer import Renderer
            
            spec_path = os.path.join(tempfile.gettempdir(), 'test_spec.yml')
            with open(spec_path, 'w', encoding='utf-8') as f:
                f.write('confirmed: false\n')
            
            with pytest.raises(RenderBlockedError):
                Renderer(spec_path)
                
        finally:
            if '_PRESALES_CLI_INVOKED' in os.environ:
                del os.environ['_PRESALES_CLI_INVOKED']


class TestStyleResolution:
    """测试风格解析功能。"""

    def test_resolve_existing_style(self):
        """解析存在的风格。"""
        from _renderer import _resolve_style
        style = _resolve_style('enterprise')
        assert style is not None
        assert style.get('name') == '企业通用'

    def test_resolve_nonexistent_style(self):
        """解析不存在的风格返回 enterprise。"""
        from _renderer import _resolve_style
        style = _resolve_style('nonexistent')
        assert style is not None
        assert style.get('name') == '企业通用'


class TestOutputPathValidation:
    """测试输出路径验证。"""

    def test_allowed_path(self):
        """允许的路径不抛出异常。"""
        from _renderer import _validate_output_path
        
        output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'test.html')
        try:
            _validate_output_path(output_path)
        except Exception as e:
            pytest.fail(f"Allowed path raised error: {e}")

    def test_disallowed_path(self):
        """不允许的路径抛出异常。"""
        from _renderer import _validate_output_path, OutputPathNotAllowedError
        
        with pytest.raises(OutputPathNotAllowedError):
            _validate_output_path('C:\\Users\\test\\malicious.exe')

class TestEscapeHtml:
    """§七 2.6：HTML 端用户文本统一过 _esc（防注入/防非法 HTML）。"""

    def _render(self, tmp_path, elements):
        import shutil
        os.environ['_PRESALES_CLI_INVOKED'] = '1'
        try:
            from _renderer import Renderer
            spec_path = tmp_path / "spec.yml"
            import yaml
            spec_path.write_text(yaml.safe_dump({
                "confirmed": True,
                "document": {"title": "转义<测试>"},
                "pages": [{"id": "p01", "title": "页&标题", "elements": elements}],
            }, allow_unicode=True), encoding="utf-8")
            out_dir = os.path.join("output", "通用", "escape_html_test")
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)
            try:
                r = Renderer(str(spec_path))
                out = os.path.join(out_dir, "out.html")
                r.render_html(out)
                with open(out, encoding="utf-8") as f:
                    return f.read()
            finally:
                if os.path.exists(out_dir):
                    shutil.rmtree(out_dir)
        finally:
            del os.environ['_PRESALES_CLI_INVOKED']

    def test_text_script_escaped(self, tmp_path):
        """text 含 <script> 必须转义，不出现在输出里。"""
        html = self._render(tmp_path, [
            {"type": "text", "content": "<script>alert(1)</script>"}])
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<script>alert(1)</script>" not in html

    def test_cards_title_amp_escaped(self, tmp_path):
        """cards title 含 & 转义为 &amp;。"""
        html = self._render(tmp_path, [
            {"type": "cards", "cards": [{"title": "A&B", "body": "x"}]}])
        assert "A&amp;B</div>" in html

    def test_page_title_and_doc_title_escaped(self, tmp_path):
        """页标题/文档标题同样转义。"""
        html = self._render(tmp_path, [])
        assert "页&amp;标题" in html
        assert "转义&lt;测试&gt;" in html
