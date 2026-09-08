# -*- coding: utf-8 -*-
"""Step 6：confirm 事件化门禁测试（sidecar 哈希、幂等、渲染拦截）。"""

import json
import os
import sys

import yaml


def _run_main(argv, monkeypatch):
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
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


def _write_spec(tmp_path, title="方案", confirmed=False):
    spec = {
        "confirmed": confirmed,
        "document": {"title": title},
        "pages": [{"id": "p1", "title": "页", "elements": [
            {"type": "text", "content": "内容"}]}],
    }
    path = tmp_path / "spec.yml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_confirm_writes_sidecar_and_sets_confirmed(tmp_path, monkeypatch):
    code = _run_main(["_cli.py", "confirm", _write_spec(tmp_path),
                      "--client", "测试"], monkeypatch)
    assert code in (None, 0)
    sidecar = tmp_path / "spec.confirm.json"
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["client"] == "测试"
    assert payload["host"] in ("dsh", "kimi", "unknown")
    assert len(payload["spec_sha256"]) == 64
    spec = yaml.safe_load((tmp_path / "spec.yml").read_text(encoding="utf-8"))
    assert spec["confirmed"] is True


def test_confirm_idempotent(tmp_path, monkeypatch):
    spec_path = _write_spec(tmp_path)
    assert _run_main(["_cli.py", "confirm", spec_path], monkeypatch) in (None, 0)
    sidecar = tmp_path / "spec.confirm.json"
    first = json.loads(sidecar.read_text(encoding="utf-8"))
    assert _run_main(["_cli.py", "confirm", spec_path], monkeypatch) in (None, 0)
    second = json.loads(sidecar.read_text(encoding="utf-8"))
    assert first["spec_sha256"] == second["spec_sha256"]


def test_modified_spec_after_confirm_blocked_exit2(tmp_path, monkeypatch):
    spec_path = _write_spec(tmp_path)
    assert _run_main(["_cli.py", "confirm", spec_path], monkeypatch) in (None, 0)
    # 修改 spec 后渲染应被 sidecar 哈希校验拦下（exit 2）
    spec = yaml.safe_load((tmp_path / "spec.yml").read_text(encoding="utf-8"))
    spec["document"]["title"] = "被修改"
    (tmp_path / "spec.yml").write_text(
        yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    # 只需要走到 confirm 门，屏蔽后续依赖/渲染
    monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
    out_html = os.path.join(str(tmp_path), "out.html")
    code = _run_main(
        ["_cli.py", "html-build", spec_path, out_html, "--html-only",
         "--client", "测试"], monkeypatch)
    assert code == 2
    assert not os.path.exists(out_html)


def test_missing_sidecar_blocked_exit2(tmp_path, monkeypatch):
    """只有 confirmed:true 没有 sidecar 的存量/手改 spec 也应被守卫拦下。"""
    spec_path = _write_spec(tmp_path, confirmed=True)
    monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
    out_html = os.path.join(str(tmp_path), "out.html")
    code = _run_main(
        ["_cli.py", "html-build", spec_path, out_html, "--html-only",
         "--client", "测试"], monkeypatch)
    assert code == 2
    assert not os.path.exists(out_html)


def test_pptd_spec_gate_confirmed_without_sidecar_blocked(tmp_path):
    """0b 回归：pptd-build 的 confirm 门必须把 spec_path 传给 is_confirmed
    （曾误以位置参数绑定到 context，sidecar 校验被静默跳过）——
    confirmed:true 但无 sidecar 的 spec 必须抛 RenderBlockedError。"""
    import hashlib

    import pytest

    from _renderer import RenderBlockedError
    from _spec_drift_gate import _pptd_apply_spec_gates

    spec_path = _write_spec(tmp_path, confirmed=True)
    deck = tmp_path / "deck"
    deck.mkdir()
    digest = hashlib.sha256(
        (tmp_path / "spec.yml").read_bytes()).hexdigest()
    (deck / ".spec_sha256").write_text(
        f"{spec_path}|{digest}", encoding="utf-8")
    with pytest.raises(RenderBlockedError):
        _pptd_apply_spec_gates(str(deck))


def test_pptd_spec_gate_corrupt_spec_blocked_exit2(tmp_path):
    """S4 增强：spec 读盘/解析失败按 fail-closed 收口（此前裸 traceback
    崩进程），打印阻断并 exit 2。"""
    import hashlib

    import pytest

    from _spec_drift_gate import _pptd_apply_spec_gates

    spec_path = tmp_path / "spec.yml"
    spec_path.write_text("pages: [unclosed\n", encoding="utf-8")
    deck = tmp_path / "deck"
    deck.mkdir()
    digest = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    (deck / ".spec_sha256").write_text(
        f"{spec_path}|{digest}", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        _pptd_apply_spec_gates(str(deck))
    assert exc_info.value.code == 2


def test_pptd_spec_gate_non_dict_spec_blocked(tmp_path):
    """S4 增强：spec 解析出非 dict（如顶层 YAML 列表）按未确认处理，
    confirm 门阻断（RenderBlockedError）。"""
    import hashlib

    import pytest

    from _renderer import RenderBlockedError
    from _spec_drift_gate import _pptd_apply_spec_gates

    spec_path = _write_spec(tmp_path, confirmed=True)
    # 覆写为顶层列表 YAML（语法合法但非 dict）
    spec_path_obj = tmp_path / "spec.yml"
    spec_path_obj.write_text("- just\n- a\n- list\n", encoding="utf-8")
    deck = tmp_path / "deck"
    deck.mkdir()
    digest = hashlib.sha256(spec_path_obj.read_bytes()).hexdigest()
    (deck / ".spec_sha256").write_text(
        f"{spec_path}|{digest}", encoding="utf-8")
    with pytest.raises(RenderBlockedError):
        _pptd_apply_spec_gates(str(deck))


def test_pptd_spec_gate_missing_spec_path_skips_with_hint(tmp_path, capsys):
    """S4 增强：.spec_sha256 记录的 spec 挪走/删除——不阻断（向后兼容），
    但必须打印提示保证双门跳过可见（旧实现静默 return）。"""
    from _spec_drift_gate import _pptd_apply_spec_gates

    deck = tmp_path / "deck"
    deck.mkdir()
    gone = tmp_path / "gone" / "spec.yml"
    (deck / ".spec_sha256").write_text(f"{gone}|deadbeef", encoding="utf-8")
    _pptd_apply_spec_gates(str(deck))  # 不抛即通过
    assert "跳过" in capsys.readouterr().out


def test_deliver_resume_skips_html_pause(tmp_path, monkeypatch):
    """deliver --resume 不再走 html-build/暂停，直接进入 pptd 定位/构建。"""
    import _cli_generate
    calls = []
    def fake_call(cmd, *a, **kw):
        calls.append(cmd[2])
        return 0
    monkeypatch.setattr("subprocess.call", fake_call)
    # 伪造 pptd 目录
    pptd_dir = tmp_path / "deck"
    (pptd_dir / "pages").mkdir(parents=True, exist_ok=True)
    (pptd_dir / "main.pptd").write_text("", encoding="utf-8")
    out_html = os.path.join(str(tmp_path), "deck.html")
    args = type("Args", (), {
        "spec": str(tmp_path / "spec.yml"),
        "output": out_html,
        "client": None,
        "style": None,
        "pptd": str(pptd_dir),
        "inline_editor": False,
        "skip_review": False,
        "review": False,
        "shots": False,
        "resume": True,
    })()
    # 不抛即成功；且不应调用 html-build
    _cli_generate.cmd_deliver(args)
    assert "html-build" not in calls
    assert "pptd-build" in calls
