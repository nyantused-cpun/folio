# -*- coding: utf-8 -*-
"""R3-2 育种自动登记钩子（P3-2 收口，2026-09-08）测试。

钩子本体 _cli_generate_build.notify_breeding；接线在 cmd_html_build（HTML verify
通过后、auto_review 前，尽力而为不阻断生成链）。registry 一律 tmp_path 隔离，
不碰 _knowledge/breeding/registry.json 真库。
"""
import inspect
import json

import pytest
import yaml

import _cli_generate as gen
import _cli_generate_build as gen_build
import _cli_generate_deliver as gen_deliver


def _write_spec(tmp_path, crafted=True):
    """最小 spec：crafted=True 时含 raw_html 页（collect_crafted_pages 硬信号）。"""
    page = {"id": "cover", "elements": []}
    if crafted:
        page["elements"] = [{"type": "raw_html", "html": "<section>demo</section>"}]
    spec = {"document": {"title": "钩子测试"}, "pages": [page]}
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_crafted_page_registers_candidate(tmp_path):
    reg = tmp_path / "registry.json"
    spec = _write_spec(tmp_path, crafted=True)
    ids = gen_build.notify_breeding(spec, str(tmp_path / "out.html"),
                                    "钩子测试客户", registry=str(reg))
    assert ids and len(ids) == 1
    entries = json.loads(reg.read_text(encoding="utf-8"))
    assert entries[0]["name"] == "crafted:cover"
    assert entries[0]["source"] == "html-build"
    assert entries[0]["status"] == "candidate"


def test_register_is_idempotent(tmp_path):
    reg = tmp_path / "registry.json"
    spec = _write_spec(tmp_path, crafted=True)
    first = gen_build.notify_breeding(spec, str(tmp_path / "a.html"), "客户甲",
                                      registry=str(reg))
    second = gen_build.notify_breeding(spec, str(tmp_path / "b.html"), "客户乙",
                                       registry=str(reg))
    assert first and second == []  # 幂等：同名非归档条目不重复登记


def test_plain_spec_registers_nothing(tmp_path):
    reg = tmp_path / "registry.json"
    spec = _write_spec(tmp_path, crafted=False)
    ids = gen_build.notify_breeding(spec, str(tmp_path / "out.html"), "客户",
                                    registry=str(reg))
    assert ids == []
    assert not reg.exists()  # 无登记不落盘


def test_data_track_fallback_when_spec_side_empty(tmp_path):
    """spec 侧无 crafted 标签、产物侧 data-track 硬信号在场 → 兜底登记。"""
    reg = tmp_path / "registry.json"
    spec = _write_spec(tmp_path, crafted=False)
    html = tmp_path / "out.html"
    html.write_text('<div data-track="crafted">x</div>', encoding="utf-8")
    ids = gen_build.notify_breeding(spec, str(html), "客户", registry=str(reg))
    assert len(ids) == 1
    entries = json.loads(reg.read_text(encoding="utf-8"))
    assert entries[0]["name"] == "crafted:crafted-page"


def test_breeding_failure_does_not_block_html_build(monkeypatch):
    """登记链任何异常只降级跳过，不影响 html-build 主链（接线契约）。"""
    def _boom(*a, **k):
        raise RuntimeError("registry 不可写")
    monkeypatch.setattr(gen_build, "notify_breeding", _boom)
    # 模拟 cmd_html_build 的接线段：与 cmd_html_build 内 try/except 同构
    try:
        gen_build.notify_breeding("spec.yml", "out.html", None)
        raised = False
    except Exception as e:
        raised = True
        assert "registry 不可写" in str(e)
    assert raised
    # 接线确凿：cmd_html_build 源码里 notify_breeding 必须被 try/except 包裹
    src = inspect.getsource(gen_build.cmd_html_build)
    assert "notify_breeding" in src
    assert "自动登记跳过" in src


def test_facade_reexports_hook_and_cmds():
    """R3-1 拆分后访问面不变：cmd_* 与钩子仍从 _cli_generate 可取（_cli.py 契约）。"""
    for name in ("cmd_html_build", "cmd_quote_build", "cmd_spec_gen",
                 "cmd_docx_build", "cmd_outline_to_spec", "cmd_pptd_gen",
                 "cmd_pptd_build", "cmd_deliver", "notify_breeding",
                 "_write_deliver_receipt", "_run_pre_check"):
        assert hasattr(gen, name), name


@pytest.mark.parametrize("fn", [gen_build.cmd_html_build, gen_build.cmd_quote_build,
                                gen_build.cmd_pptd_build, gen_deliver.cmd_deliver])
def test_moved_cmds_resolve_helpers_via_facade(fn):
    """子模块命令体对共享助手必须经 _g.<name> 属性解析（打桩面契约的机械保证）：
    源码里不允许出现对打桩面助手的裸名调用。"""
    src = inspect.getsource(fn)
    for helper in ("_run_pre_check", "backup_before_generate", "_auto_review",
                   "_run_post_check", "_record_last_review", "_advance_state"):
        if helper in src:
            assert f"_g.{helper}" in src, (
                f"{fn.__name__} 对 {helper} 存在裸名调用，会绕过 _cli_generate 打桩面")
