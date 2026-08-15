# -*- coding: utf-8 -*-
"""行为路径测试：_renderer/__init__.py、_cli.py、_cli_generate.py。

优先覆盖：
- confirmed gate 通过后的生成流
- 命令路由分发
- 渲染主路径（HTML 元素渲染、报告收集、封面渲染）
"""

import os
import sys
import shutil

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


# ============================================================
# 公共 fixture
# ============================================================

@pytest.fixture(autouse=True)
def _cli_env():
    """Renderer 要求 _PRESALES_CLI_INVOKED=1；保存/还原避免污染。"""
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _write_spec(tmp_path, pages=None, confirmed=True, **extra):
    """写一份 spec 到 tmp_path，返回路径字符串。"""
    spec = {
        "confirmed": confirmed,
        "document": {"title": "行为测试文档", "subtitle": "副标题"},
        "author": "测试作者",
        "pages": pages or [],
    }
    spec.update(extra)
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(spec_path)


def _run_main(argv, monkeypatch):
    """调用 _cli.main()，返回退出码（成功无 SystemExit 返回 None）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _mock_generate_pipeline(monkeypatch):
    """mock 生成链路外围（pre_check / 编辑器注入 / verify / review / post_check），
    保留真实 Renderer 渲染与 backup。"""
    import _cli_generate
    monkeypatch.setattr(_cli_generate, "_run_pre_check",
                        lambda client_name=None: {"ok": True})
    monkeypatch.setattr(_cli_generate, "_run_post_check", lambda *a, **k: None)
    monkeypatch.setattr(_cli_generate, "_auto_review", lambda *a, **k: None)
    monkeypatch.setattr("_renderer.html_editor_injector.inject", lambda *a, **k: None)
    monkeypatch.setattr("_verify_hook.run_single", lambda *a, **k: True)


OUT_DIR = os.path.join("output", "通用", "_test_behavior_paths")


@pytest.fixture
def out_dir():
    """白名单内输出目录。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    yield OUT_DIR
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)


# ============================================================
# _renderer/__init__.py 行为测试（渲染主路径）
# ============================================================

class TestRendererHtmlMainPath:
    """Renderer.render_html 主路径行为。"""

    def test_render_html_produces_valid_structure(self, tmp_path, out_dir):
        """confirmed spec 渲染出完整 HTML 骨架：DOCTYPE + title + 页标题 + 元素。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "概述", "elements": [
                {"type": "text", "content": "这是正文段落。"}]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "main_path.html")
        r.render_html(out)

        html = open(out, encoding="utf-8").read()
        assert "<!DOCTYPE html>" in html
        assert "<title>行为测试文档</title>" in html
        assert "<h2>概述</h2>" in html
        assert "这是正文段落。" in html

    def test_render_html_multiple_element_types(self, tmp_path, out_dir):
        """多种元素类型正确渲染：heading / bullets / table / cards。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "多元素", "elements": [
                {"type": "heading", "text": "二级标题", "level": 1},
                {"type": "bullets", "items": ["要点A", "要点B"]},
                {"type": "table", "headers": ["列1", "列2"],
                 "rows": [["a", "b"], ["c", "d"]]},
                {"type": "cards", "cards": [
                    {"title": "卡片1", "body": "内容1"}]},
            ]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "multi_elem.html")
        r.render_html(out)

        html = open(out, encoding="utf-8").read()
        # heading level 1 -> h3 (level + 2)
        assert "<h3>二级标题</h3>" in html
        # bullets 用 div.bullet
        assert 'class="bullet"' in html
        assert "要点A" in html
        # table
        assert "<th>列1</th>" in html
        assert "<td>a</td>" in html
        # cards
        assert "卡片1" in html

    def test_render_html_empty_payload_skipped_and_reported(self, tmp_path, out_dir):
        """已知类型但内容为空的元素被跳过并记入 report.skipped。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "空元素", "elements": [
                {"type": "bullets", "items": []},
                {"type": "text", "content": "有内容"},
            ]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "empty_elem.html")
        r.render_html(out)

        html = open(out, encoding="utf-8").read()
        assert "有内容" in html
        # 空 bullets 被跳过，report 有记录
        assert len(r.report.skipped) >= 1

    def test_render_html_unknown_type_reported(self, tmp_path, out_dir):
        """未知元素类型不静默跳过，进 report.skipped。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "未知", "elements": [
                {"type": "totally_unknown_widget", "data": "xxx"},
            ]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "unknown.html")
        r.render_html(out)

        assert len(r.report.skipped) >= 1
        assert any("totally_unknown_widget" in str(s) for s in r.report.skipped)

    def test_render_html_cover_dark_photo(self, tmp_path, out_dir):
        """dark-photo 封面模板渲染：背景图 + 罩层 + 标题。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[], document={
            "title": "封面标题",
            "subtitle": "封面副标题",
            "cover": {
                "template": "dark-photo",
                "background_image": "bg.jpg",
                "veil": "#0A1540",
                "veil_opacity": 0.8,
                "confidential": "机密",
                "show_date": True,
                "date": "2026-07-31",
            },
        })
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "cover.html")
        r.render_html(out)

        html = open(out, encoding="utf-8").read()
        assert 'class="cover"' in html
        assert "bg.jpg" in html
        assert "封面标题" in html
        assert "机密" in html
        assert "2026-07-31" in html

    def test_render_html_v2_page_layout_section(self, tmp_path, out_dir):
        """v2 P 系版式页输出 <section class='v2-page' id='...'>，不输出 h2。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "目录", "layout": "P01", "elements": [
                {"type": "text", "content": "v2 内容"},
            ]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "v2page.html")
        r.render_html(out)

        html = open(out, encoding="utf-8").read()
        assert 'class="v2-page"' in html
        assert 'id="p01"' in html
        # v2 页不输出 h2 页标题
        assert "<h2>目录</h2>" not in html

    def test_render_html_extract_fail_marker_warns(self, tmp_path, out_dir):
        """outline-to-spec 提取失败占位页触发 report.warnings。"""
        from _renderer import Renderer
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "失败页", "elements": [
                {"type": "text", "content": "（本章节内容提取失败，请手动补充）"},
            ]},
        ])
        r = Renderer(spec_path)
        out = os.path.join(out_dir, "fail_marker.html")
        r.render_html(out)

        assert any("提取失败占位页" in w for w in r.report.warnings)

    def test_client_name_empty_blocks(self, tmp_path):
        """spec.client_name 存在但为空时阻断。"""
        from _renderer import Renderer, RenderBlockedError
        spec_path = _write_spec(tmp_path, pages=[], client_name="")
        with pytest.raises(RenderBlockedError, match="client_name"):
            Renderer(spec_path)


# ============================================================
# _cli.py 行为测试（命令路由分发）
# ============================================================

class TestCliCommandRouting:
    """_cli.py 命令路由分发行为。"""

    def test_deprecated_command_intercepted_before_argparse(self, monkeypatch, capsys):
        """废弃命令在 argparse 之前被拦截，exit 1 + 提示替代。"""
        code = _run_main(["_cli.py", "compress", "通用"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "已废弃" in out
        assert "compact" in out

    def test_deprecated_handoff_shows_replacement(self, monkeypatch, capsys):
        """handoff 废弃提示包含替代命令 session-start。"""
        code = _run_main(["_cli.py", "handoff", "客户"], monkeypatch)
        assert code == 1
        assert "session-start" in capsys.readouterr().out

    def test_no_command_prints_help_exits_0(self, monkeypatch):
        """无子命令时打印帮助并 exit 0。"""
        code = _run_main(["_cli.py"], monkeypatch)
        assert code == 0

    def test_dispatch_table_covers_all_parser_commands(self):
        """dispatch 表与 parser 注册命令完全一致。"""
        import _cli
        parser = _cli.build_parser()
        sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
        assert set(sub.choices.keys()) == set(_cli._build_dispatch().keys())

    def test_main_sets_cli_invoked_env(self, monkeypatch):
        """main() 执行时设置 _PRESALES_CLI_INVOKED=1。"""
        import _cli
        monkeypatch.setattr(sys, "argv", ["_cli.py", "status"])
        os.environ.pop("_PRESALES_CLI_INVOKED", None)
        # status 可能正常退出或无 SystemExit
        try:
            _cli.main()
        except SystemExit:
            pass
        assert os.environ.get("_PRESALES_CLI_INVOKED") == "1"
        os.environ.pop("_PRESALES_CLI_INVOKED", None)

    def test_file_not_found_exception_handled(self, monkeypatch, capsys):
        """命令内部抛 FileNotFoundError 被兜底为友好提示 + exit 1。"""
        import _cli
        monkeypatch.setattr(sys, "argv", ["_cli.py", "status"])

        def _boom(args):
            raise FileNotFoundError("spec.yml")

        monkeypatch.setitem(_cli._build_dispatch(), "status", _boom)
        # 需要 patch _build_dispatch 返回的 dict
        original_build = _cli._build_dispatch
        dispatch = original_build()
        dispatch["status"] = _boom
        monkeypatch.setattr(_cli, "_build_dispatch", lambda: dispatch)

        code = _run_main(["_cli.py", "status"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "找不到文件" in out

    def test_module_not_found_exception_handled(self, monkeypatch, capsys):
        """命令内部抛 ModuleNotFoundError 被兜底为依赖提示 + exit 1。"""
        import _cli

        def _boom(args):
            raise ModuleNotFoundError("No module named 'foo'")

        dispatch = _cli._build_dispatch()
        dispatch["status"] = _boom
        monkeypatch.setattr(_cli, "_build_dispatch", lambda: dispatch)

        code = _run_main(["_cli.py", "status"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "缺少依赖模块" in out

    def test_generic_exception_handled_gracefully(self, monkeypatch, capsys):
        """未知异常被兜底为通用错误提示 + exit 1（不暴露 traceback）。"""
        import _cli

        def _boom(args):
            raise RuntimeError("something unexpected")

        dispatch = _cli._build_dispatch()
        dispatch["status"] = _boom
        monkeypatch.setattr(_cli, "_build_dispatch", lambda: dispatch)

        code = _run_main(["_cli.py", "status"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "执行失败" in out
        assert "Traceback" not in out


# ============================================================
# _cli_generate.py 行为测试（confirmed gate 通过后生成流）
# ============================================================

class TestCliGenerateConfirmedFlow:
    """confirmed gate 通过后的生成流行为。"""

    def test_html_build_confirmed_generates_html(self, monkeypatch, tmp_path, out_dir):
        """confirmed=true 的 spec 经 html-build 生成 HTML 文件。"""
        _mock_generate_pipeline(monkeypatch)
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "测试页", "elements": [
                {"type": "text", "content": "生成内容。"}]},
        ])
        out_html = os.path.join(out_dir, "confirmed.html")
        code = _run_main(
            ["_cli.py", "html-build", spec_path, out_html, "--html-only"],
            monkeypatch)
        assert code in (None, 0)
        assert os.path.exists(out_html)
        html = open(out_html, encoding="utf-8").read()
        assert "生成内容。" in html

    def test_html_build_unconfirmed_blocked(self, monkeypatch, tmp_path, out_dir):
        """confirmed=false 的 spec 被 confirmed 门阻断，无产出。"""
        _mock_generate_pipeline(monkeypatch)
        spec_path = _write_spec(tmp_path, pages=[], confirmed=False)
        out_html = os.path.join(out_dir, "blocked.html")
        code = _run_main(
            ["_cli.py", "html-build", spec_path, out_html, "--html-only"],
            monkeypatch)
        assert code == 1
        assert not os.path.exists(out_html)

    def test_html_build_html_only_skips_pptd(self, monkeypatch, tmp_path, out_dir):
        """--html-only 不生成 pptd 工程目录。"""
        _mock_generate_pipeline(monkeypatch)
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "页", "elements": [
                {"type": "text", "content": "x"}]},
        ])
        out_html = os.path.join(out_dir, "html_only.html")
        code = _run_main(
            ["_cli.py", "html-build", spec_path, out_html, "--html-only"],
            monkeypatch)
        assert code in (None, 0)
        # 同名 pptd 目录不应存在
        pptd_dir = os.path.splitext(out_html)[0]
        assert not os.path.isdir(pptd_dir)

    def test_html_build_pre_check_failure_blocks(self, monkeypatch, tmp_path, out_dir, capsys):
        """pre_check 返回 None（依赖缺失）时阻断生成。"""
        import _cli_generate
        monkeypatch.setattr(_cli_generate, "_run_pre_check",
                            lambda client_name=None: None)
        spec_path = _write_spec(tmp_path, pages=[])
        out_html = os.path.join(out_dir, "precheck_fail.html")
        code = _run_main(
            ["_cli.py", "html-build", spec_path, out_html, "--html-only"],
            monkeypatch)
        assert code == 1
        assert "生成前检查失败" in capsys.readouterr().out

    def test_docx_build_confirmed_generates_file(self, monkeypatch, tmp_path, out_dir):
        """confirmed spec 经 docx-build 生成 .docx 文件。"""
        _mock_generate_pipeline(monkeypatch)
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "Word页", "elements": [
                {"type": "text", "content": "Word 正文。"}]},
        ])
        out_docx = os.path.join(out_dir, "test.docx")
        code = _run_main(
            ["_cli.py", "docx-build", spec_path, out_docx], monkeypatch)
        assert code in (None, 0)
        assert os.path.exists(out_docx)
        assert os.path.getsize(out_docx) > 0

    def test_snapshot_created_before_render(self, monkeypatch, tmp_path, out_dir):
        """confirmed spec 在渲染前产生 .versions/ 快照。"""
        _mock_generate_pipeline(monkeypatch)
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "快照", "elements": [
                {"type": "text", "content": "内容"}]},
        ])
        out_html = os.path.join(out_dir, "snapshot.html")
        code = _run_main(
            ["_cli.py", "html-build", spec_path, out_html, "--html-only"],
            monkeypatch)
        assert code in (None, 0)
        versions_dir = tmp_path / ".versions"
        assert versions_dir.is_dir()

    def test_deprecated_ppt_build_exits_with_hint(self, monkeypatch, capsys):
        """退役命令 ppt-build 调用即打印替代方案并 exit 1。"""
        code = _run_main(
            ["_cli.py", "ppt-build", "spec.yml", "out.pptx"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "废弃" in out
        assert "html-build" in out

    def test_deprecated_html_to_ppt_exits_with_hint(self, monkeypatch, capsys):
        """退役命令 html-to-ppt 调用即提示 D-088 同源双输出。"""
        code = _run_main(
            ["_cli.py", "html-to-ppt", "in.html", "out.pptx"], monkeypatch)
        assert code == 1
        out = capsys.readouterr().out
        assert "废弃" in out


class TestCliGenerateHelpers:
    """_cli_generate.py 辅助函数行为。"""

    def test_snapshot_same_content_skips_duplicate(self, tmp_path):
        """内容与最新快照一致时跳过（不产生重复快照）。"""
        import _cli_generate
        spec_path = _write_spec(tmp_path, pages=[
            {"id": "p01", "title": "判重", "elements": []},
        ])
        # 第一次快照
        _cli_generate._snapshot_spec_if_confirmed(spec_path)
        versions_dir = tmp_path / ".versions"
        count_1 = len(os.listdir(versions_dir))
        # 第二次相同内容：应跳过
        _cli_generate._snapshot_spec_if_confirmed(spec_path)
        count_2 = len(os.listdir(versions_dir))
        assert count_2 == count_1

    def test_run_layout_lint_error_blocks(self, monkeypatch):
        """_run_layout_lint 有 error 级 issue 时返回 False。"""
        import _cli_generate
        from _layout_lint import Issue
        issues = [Issue(page="p01", element_id="e0", kind="overlap",
                        message="元素重叠", severity="error")]
        result = _cli_generate._run_layout_lint(issues)
        assert result is False

    def test_run_layout_lint_warning_passes(self, monkeypatch):
        """_run_layout_lint 只有 warning 时返回 True（不阻断）。"""
        import _cli_generate
        from _layout_lint import Issue
        issues = [Issue(page="p01", element_id="e0", kind="out_of_bounds",
                        message="边距偏小", severity="warning")]
        result = _cli_generate._run_layout_lint(issues)
        assert result is True
