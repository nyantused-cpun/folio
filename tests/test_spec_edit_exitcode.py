# -*- coding: utf-8 -*-
"""C-A3 回归：spec-edit 退出码契约（docs/cli_contract_v1.md §2）。

契约三条：0=成功（含 warn）/ 1=执行失败 / 2=守卫阻断。
spec-edit 命令体内没有守卫阻断路径（spec 未确认、confirm 哈希不匹配、
theme critical 等守卫出口都在 generate/confirm/review 流程），因此本命令
不应出现 exit 2——失败分支历史上误用 2（与守卫语义混淆），
2026-09-07 修为 1（0907 修复计划 C-A3）。
"""
import os
import sys

import pytest

pytest.importorskip("yaml")

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


def _run_main(argv, monkeypatch):
    """进程内跑 _cli.main()，返回退出码（无 SystemExit 视为 0）。

    模式与 tests/test_m1_f0_cli_verification_chain.py 一致。
    """
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return 0
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _write_spec(tmp_path):
    """最小合法 spec：有 pages 列表即可被 add_page/delete_page 操作。"""
    import yaml
    spec = {
        "confirmed": True,
        "document": {"title": "退出码契约测试"},
        "pages": [{"id": "p01", "title": "首页", "layout": "bullets",
                   "elements": []}],
    }
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_success_exits_0(tmp_path, monkeypatch):
    spec = _write_spec(tmp_path)
    code = _run_main(
        ["_cli.py", "spec-edit", spec, "--op", "add_page",
         "--page-id", "p02", "--title", "新增页"], monkeypatch)
    assert code == 0
    with open(spec, encoding="utf-8") as f:
        import yaml
        assert any(pg["id"] == "p02" for pg in yaml.safe_load(f)["pages"])


def test_operation_failure_exits_1(tmp_path, monkeypatch):
    """操作被拒（页不存在）→ 1，不再是 2（C-A3 主断言）。"""
    spec = _write_spec(tmp_path)
    code = _run_main(
        ["_cli.py", "spec-edit", spec, "--op", "delete_page",
         "--page-id", "p99"], monkeypatch)
    assert code == 1


def test_duplicate_page_id_failure_exits_1(tmp_path, monkeypatch):
    """add_page 撞已有 page_id 同属执行失败 → 1。"""
    spec = _write_spec(tmp_path)
    code = _run_main(
        ["_cli.py", "spec-edit", spec, "--op", "add_page",
         "--page-id", "p01", "--title", "重复页"], monkeypatch)
    assert code == 1


def test_missing_spec_exits_1(tmp_path, monkeypatch):
    """文件不存在 → 1（契约 §2 原有口径，防回退成 2）。"""
    code = _run_main(
        ["_cli.py", "spec-edit", str(tmp_path / "nope.yml"),
         "--op", "add_page", "--page-id", "p02", "--title", "T"], monkeypatch)
    assert code == 1


def test_unknown_op_exits_1(tmp_path, monkeypatch, capsys):
    """命令体内未知 op 分支（纵深防御）→ 1。

    经 CLI 入口时 argparse choices 先拦（usage error exit 2，全 CLI 惯例、
    不属契约表语义），故此分支只能函数级触达（夹具同 tests/test_state.py）。
    """
    from types import SimpleNamespace

    import _cli
    spec = _write_spec(tmp_path)
    with pytest.raises(SystemExit) as ei:
        _cli.cmd_spec_edit(SimpleNamespace(
            spec=spec, op="bogus_op", page_id=None, title=None,
            layout=None, element=None, updates=None, index=None,
            confirm=False, client=None))
    assert ei.value.code == 1


def test_no_exit2_in_command_body():
    """契约钉：守卫阻断码 2 不得出现在 spec-edit 命令体内。

    spec-edit 无守卫路径，exit 2 只属于 generate/confirm/review 流程；
    源级断言防未来把守卫/失败语义再次混入本命令（先例：源码 grep 断言
    见 tests/test_archive_auto_v2.py::_session_inline_forbidden）。
    """
    import inspect

    from _cli_cmds_qa import cmd_spec_edit
    assert "sys.exit(2)" not in inspect.getsource(cmd_spec_edit)
