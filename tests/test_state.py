# -*- coding: utf-8 -*-
"""M3-F2 阶段状态机测试：_state + state 命令 + session-start/status stage + 失败不推进。

所有测试隔离到 tmp_path，绝不读/写真实 .folio/logs/session_state.json。
"""
import json
from types import SimpleNamespace

import pytest

import _state
import _cli
import _context
import _cli_generate


@pytest.fixture
def state_path(tmp_path, monkeypatch):
    path = tmp_path / "session_state.json"
    monkeypatch.setattr(_state, "SESSION_STATE_PATH", str(path))
    return path


def _client_args(client, **kw):
    defaults = dict(
        client=client,
        client_name=None,
        stage=None,
        confirm_html=False,
        reset=False,
        json=False,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestStateModule:
    def test_default_intake(self, state_path):
        assert _state.get_state(None)["stage"] == "intake"
        assert _state.get_state("测试客户A")["stage"] == "intake"
        assert _state.get_state("测试客户A")["client"] == "测试客户A"

    def test_advance_and_set_state(self, state_path):
        _state.advance("测试客户A", "spec_draft")
        assert _state.get_state("测试客户A")["stage"] == "spec_draft"

        _state.set_state("测试客户A", stage="html_confirmed", taskId="T-1")
        st = _state.get_state("测试客户A")
        assert st["stage"] == "html_confirmed"
        assert st["taskId"] == "T-1"

    def test_invalid_stage_rejected(self, state_path):
        with pytest.raises(ValueError):
            _state.set_state("测试客户A", stage="not-a-stage")
        with pytest.raises(ValueError):
            _state.advance("测试客户A", "not-a-stage")

    def test_reset_state(self, state_path):
        _state.advance("测试客户A", "delivered")
        st = _state.reset_state("测试客户A")
        assert st["stage"] == "intake"
        assert _state.get_state("测试客户A")["stage"] == "intake"

    def test_multi_client_isolation(self, state_path):
        _state.advance("客户甲", "spec_draft")
        _state.advance("客户乙", "html_done")
        assert _state.get_state("客户甲")["stage"] == "spec_draft"
        assert _state.get_state("客户乙")["stage"] == "html_done"

    def test_get_state_returns_deep_copy_of_lastReview(self, state_path):
        st = _state.get_state("测试客户A")
        st["lastReview"]["verdict"] = "PASS"
        st["lastReview"]["issues"].append("x")
        fresh = _state.get_state("测试客户A")
        assert fresh["lastReview"]["verdict"] == ""
        assert fresh["lastReview"]["issues"] == []
        # 默认值本身也不能被默认状态污染
        default = _state.get_state(None)
        default["lastReview"]["verdict"] = "DIRTY"
        assert _state.get_state(None)["lastReview"]["verdict"] == ""

    def test_set_state_returns_deep_copy_of_lastReview(self, state_path):
        st = _state.set_state(
            "测试客户A",
            stage="spec_confirmed",
            lastReview={"verdict": "PASS", "issues": ["a"], "at": "2026-08-30T00:00:00"},
        )
        st["lastReview"]["verdict"] = "MUTATED"
        st["lastReview"]["issues"].append("b")
        persisted = _state.get_state("测试客户A")
        assert persisted["lastReview"]["verdict"] == "PASS"
        assert persisted["lastReview"]["issues"] == ["a"]


class TestCmdState:
    def test_set_via_command_json(self, state_path, capsys):
        args = _client_args("测试客户A", stage="html_confirmed", json=True)
        _cli.cmd_state(args)
        out = json.loads(capsys.readouterr().out)
        assert out["client"] == "测试客户A"
        assert out["stage"] == "html_confirmed"

    def test_show_all_command(self, state_path, capsys):
        _state.advance("测试客户A", "spec_confirmed")
        _cli.cmd_state(_client_args(None))
        out = capsys.readouterr().out
        assert "测试客户A" in out
        assert "spec_confirmed" in out


class TestSessionStartStage:
    def _setup_session_start(self, monkeypatch):
        fake = {
            "level": "L4",
            "mode": "collaborative",
            "context_summary": "x",
            "client_index": "",
            "recall": [],
            "warnings": [],
            "recent_task_decisions": [],
            "head_context": "",
            "tail_checklist": "",
        }
        monkeypatch.setattr("_cli_cmds_qa.auto_for_input", lambda *a, **kw: fake)
        monkeypatch.setattr("_cli_cmds_qa.record_session_start", lambda *a, **kw: None)

    def test_json_contains_stage(self, state_path, monkeypatch, capsys):
        self._setup_session_start(monkeypatch)
        _state.advance("测试客户A", "spec_draft")
        args = SimpleNamespace(client="测试客户A", json=True, input="帮我做方案")
        _cli.cmd_session_start(args)
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "spec_draft"

    def test_text_prints_stage(self, state_path, monkeypatch, capsys):
        self._setup_session_start(monkeypatch)
        _state.advance("测试客户A", "html_done")
        args = SimpleNamespace(client="测试客户A", json=False, input="帮我做方案")
        _cli.cmd_session_start(args)
        assert "阶段: html_done" in capsys.readouterr().out


class TestStatusStage:
    def test_text_status_includes_stage(self, state_path, monkeypatch, capsys):
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(state_path.parent / "clients"))
        (state_path.parent / "clients" / "测试客户A").mkdir(parents=True, exist_ok=True)
        _state.advance("测试客户A", "pptx_done")
        _cli.cmd_status(SimpleNamespace(json=False))
        out = capsys.readouterr().out
        assert "阶段状态:" in out
        assert "测试客户A" in out
        assert "pptx_done" in out

    def test_json_status_includes_stage(self, state_path, monkeypatch, capsys):
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(state_path.parent / "clients"))
        (state_path.parent / "clients" / "测试客户A").mkdir(parents=True, exist_ok=True)
        _state.advance("测试客户A", "html_confirmed")
        _cli.cmd_status(SimpleNamespace(json=True))
        payload = json.loads(capsys.readouterr().out)
        assert any(e["client"] == "测试客户A" and e["stage"] == "html_confirmed" for e in payload)


class TestAdvancePoints:
    def test_advance_helper_maps_stage(self, state_path, capsys):
        _cli_generate._advance_state("测试客户A", "spec_draft")
        assert _state.get_state("测试客户A")["stage"] == "spec_draft"

    def test_html_done_advance_helper_only_when_want_html(self, state_path, capsys):
        # --pptd-only/want_html=False 不推进 html_done，保持调用前 stage
        _cli_generate._advance_html_done("测试客户A", False)
        assert _state.get_state("测试客户A")["stage"] == "intake"
        # 正常 HTML 路径才推进
        _cli_generate._advance_html_done("测试客户B", True)
        assert _state.get_state("测试客户B")["stage"] == "html_done"

    def test_html_build_pptd_only_does_not_advance(self, state_path, monkeypatch):
        """真实 cmd_html_build --pptd-only 不推进 html_done。"""
        import _layout_lint
        import _pptd
        import _pptd_gen
        import _renderer

        spec = state_path.parent / "spec.yml"
        spec.write_text("confirmed: true\n", encoding="utf-8")
        # Step 6：补 sidecar 才能通过确认门
        import hashlib
        import json
        digest = hashlib.sha256(spec.read_bytes()).hexdigest()
        (state_path.parent / "spec.confirm.json").write_text(
            json.dumps({"spec_sha256": digest}), encoding="utf-8")
        out = state_path.parent / "out.html"
        args = SimpleNamespace(
            spec=str(spec), output=str(out), html_only=False, pptd_only=True,
            client="测试客户A", industry="", style="enterprise", pptd=None,
            inline_editor=False, skip_review=False,
        )

        monkeypatch.setattr(_cli_generate, "_run_pre_check", lambda client_name=None: {"ok": True})
        monkeypatch.setattr(_cli_generate, "_snapshot_spec_if_confirmed", lambda *a, **k: None)
        monkeypatch.setattr(_cli_generate, "backup_before_generate", lambda *a, **k: None)

        class FakeRenderer:
            def __init__(self, *a, **k):
                self.spec = {"confirmed": True}
                self.style_name = "enterprise"
                self.style = {"name": "enterprise"}

        monkeypatch.setattr(_renderer, "Renderer", FakeRenderer)
        monkeypatch.setattr(_renderer, "_resolve_style", lambda style: {"name": style})
        monkeypatch.setattr(_renderer, "_validate_output_path", lambda *a, **k: None)

        monkeypatch.setattr(_pptd_gen, "_slugify_name", lambda name: name)
        monkeypatch.setattr(_pptd_gen, "build_deck",
                            lambda *a, **k: (["deck.page"], []))
        monkeypatch.setattr(_pptd_gen, "emit_deck", lambda *a, **k: None)
        monkeypatch.setattr(_renderer.elements, "RenderReport",
                            lambda *a, **k: type("RR", (), {
                                "summary": lambda self: "",
                                "has_issues": lambda self: False,
                            })())
        monkeypatch.setattr(_layout_lint, "lint_pptd_files", lambda *a, **k: [])
        monkeypatch.setattr(_pptd, "get_backend", lambda: None)

        _cli_generate.cmd_html_build(args)
        assert _state.get_state("测试客户A")["stage"] == "intake"

    def test_spec_edit_failure_does_not_advance(self, state_path, capsys):
        with pytest.raises(SystemExit):
            _cli.cmd_spec_edit(SimpleNamespace(
                spec=str(state_path.parent / "nope.yml"),
                op="add_page",
                page_id="p1",
                title="T",
                layout=None,
                element=None,
                updates=None,
                index=None,
                confirm=True,
                client="测试客户A",
            ))
        assert not state_path.exists()
        assert _state.get_state("测试客户A")["stage"] == "intake"
