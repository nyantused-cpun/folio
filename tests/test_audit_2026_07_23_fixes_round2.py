# -*- coding: utf-8 -*-
"""audit_2026-07-23 报告 第二轮（剩余 bug + 机制项）修复的回归测试。

覆盖：#3 #4 #9 #10 #11 #13 #14 #21 #22 M1 M3
（#15/#28 位于 outline-to-spec 闭包内，靠全量回归 + 代码评审覆盖；
#20 为死代码删除，无需测试）
"""
import importlib.util
import json
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

HOOKS_DIR = os.path.join(SCRIPT_DIR, ".folio", "hooks")


_HOOK_MODS = {}


def _load_hook(name):
    """按路径加载 hook 脚本（hooks 不在 sys.path，且文件名与包无关）。

    模块级缓存：同一路径只 exec 一次，保证 fixture 的 monkeypatch 与
    test 内引用的是同一模块实例（否则每个 test 重新 exec 产生新实例，
    monkeypatch 不生效，ask 记忆会污染真实缓存）。
    """
    if name not in _HOOK_MODS:
        spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS_DIR, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HOOK_MODS[name] = mod
    return _HOOK_MODS[name]


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


# ---------------------------------------------------------------------------
# #3 sync_skills rmtree 后 copytree 失败丢数据（改原子替换）
# ---------------------------------------------------------------------------
class TestSkillsSyncAtomic:
    def _mk_skill(self, base, name, marker):
        sub = os.path.join(base, name)
        os.makedirs(sub)
        with open(os.path.join(sub, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(marker)

    def test_copy_failure_preserves_dst(self, tmp_path, monkeypatch):
        import shutil
        import _skills_sync
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._mk_skill(str(src), "skill-a", "new")
        self._mk_skill(str(dst), "skill-a", "old")

        real_copytree = shutil.copytree

        def _boom(s, d, *a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(_skills_sync.shutil, "copytree", _boom)
        with pytest.raises(OSError):
            _skills_sync.sync_skills(str(src), str(dst))
        # 旧目录必须原样保留（修复前：rmtree 已执行，目录丢失）
        with open(os.path.join(str(dst), "skill-a", "SKILL.md"), encoding="utf-8") as f:
            assert f.read() == "old"
        monkeypatch.setattr(_skills_sync.shutil, "copytree", real_copytree)

    def test_normal_update_still_works(self, tmp_path):
        import _skills_sync
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        self._mk_skill(str(src), "skill-a", "new")
        self._mk_skill(str(dst), "skill-a", "old")
        report = _skills_sync.sync_skills(str(src), str(dst))
        assert report["updated"] == ["skill-a"]
        with open(os.path.join(str(dst), "skill-a", "SKILL.md"), encoding="utf-8") as f:
            assert f.read() == "new"
        assert not os.path.exists(os.path.join(str(dst), "skill-a.tmp"))


# ---------------------------------------------------------------------------
# #4 pretool_cmd_guard 安全目录外也 allow（改 ask）
# ---------------------------------------------------------------------------
class TestCmdGuard:
    @pytest.fixture(autouse=True)
    def _isolate_ask_cache(self, tmp_path, monkeypatch):
        """隔离 ask 记忆缓存：测试的 ask 不写真实 .folio/logs/。"""
        guard = _load_hook("pretool_cmd_guard")
        monkeypatch.setattr(guard, "_approved_cache_path",
                            lambda: str(tmp_path / "approved.json"))
        yield

    def test_unsafe_script_asks(self):
        guard = _load_hook("pretool_cmd_guard")
        decision, _ = guard._check_command("python evil_script.py")
        assert decision == "ask"

    def test_safe_dir_allows(self):
        guard = _load_hook("pretool_cmd_guard")
        decision, _ = guard._check_command("python tests/test_x.py")
        assert decision == "allow"

    def test_cli_allows(self):
        guard = _load_hook("pretool_cmd_guard")
        decision, _ = guard._check_command("python _cli.py status")
        assert decision == "allow"

    def test_import_internal_denied(self):
        guard = _load_hook("pretool_cmd_guard")
        decision, _ = guard._check_command('python -c "import _graph"')
        assert decision == "deny"


# ---------------------------------------------------------------------------
# #9 路径前缀匹配未检查分隔符边界
# ---------------------------------------------------------------------------
class TestPathGuardNormalize:
    def test_sibling_dir_not_treated_as_inside(self, tmp_path, monkeypatch):
        guard = _load_hook("pretool_path_guard")
        proj = str(tmp_path / "knowledge base")
        os.makedirs(proj)
        evil = os.path.join(proj + "_evil", "output", "f.html")
        monkeypatch.setenv("TRAE_PROJECT_DIR", proj)
        rel = guard._normalize(evil)
        # 兄弟目录不得被截成项目内相对路径
        assert not rel.startswith("_evil")
        assert "output" not in rel.split("/")[0:1]

    def test_inside_path_still_relative(self, tmp_path, monkeypatch):
        guard = _load_hook("pretool_path_guard")
        proj = str(tmp_path / "knowledge base")
        os.makedirs(os.path.join(proj, "output"))
        monkeypatch.setenv("TRAE_PROJECT_DIR", proj)
        rel = guard._normalize(os.path.join(proj, "output", "通用", "f.html"))
        assert rel == "output/通用/f.html"


# ---------------------------------------------------------------------------
# M1 黑名单补齐 _layout_lint / _spec_diff
# ---------------------------------------------------------------------------
class TestBlockedModules:
    def test_json_contains_new_modules(self):
        with open(os.path.join(HOOKS_DIR, "_blocked_modules.json"), encoding="utf-8") as f:
            modules = json.load(f)["core_modules"]
        assert "_layout_lint" in modules
        assert "_spec_diff" in modules

    @pytest.mark.parametrize("hook", ["pretool_cmd_guard", "pretool_path_guard"])
    def test_guard_fallback_contains_new_modules(self, hook):
        mod = _load_hook(hook)
        modules = mod._load_core_modules()
        assert "_layout_lint" in modules
        assert "_spec_diff" in modules

    def test_new_module_import_denied(self):
        guard = _load_hook("pretool_cmd_guard")
        decision, _ = guard._check_command('python -c "import _layout_lint"')
        assert decision == "deny"


# ---------------------------------------------------------------------------
# #10 check_bid_risks json.load 无 JSONDecodeError 保护
# ---------------------------------------------------------------------------
class TestBidRisksCorruptJson:
    def test_corrupt_criteria_no_crash(self, tmp_path, monkeypatch):
        import _verify
        out = tmp_path / "output" / "蓝海集团"
        out.mkdir(parents=True)
        (out / "bid_criteria.json").write_text("{broken json", encoding="utf-8")
        monkeypatch.setattr(_verify, "SCRIPT_DIR", str(tmp_path))
        ok, issues = _verify.check_bid_risks("any.docx", "蓝海集团")
        assert ok is False
        assert any("解析失败" in i for i in issues)


# ---------------------------------------------------------------------------
# #11 _print_review uncovered 为 None 时 TypeError
# ---------------------------------------------------------------------------
class TestPrintReviewNone:
    def test_null_uncovered_no_crash(self):
        from _review import _print_review
        _print_review({"theme_coverage": {"覆盖数": 1, "未覆盖": None}}, "out.html")


# ---------------------------------------------------------------------------
# #13 _classify.load_index 无 JSONDecodeError 保护
# ---------------------------------------------------------------------------
class TestClassifyLoadIndex:
    def test_corrupt_index_returns_default(self, tmp_path, monkeypatch):
        import _classify
        bad = tmp_path / "index.json"
        bad.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(_classify, "INDEX_PATH", str(bad))
        assert _classify.load_index() == {"projects": {}, "recents": []}


# ---------------------------------------------------------------------------
# #14 classify 中 shutil.move 无单文件异常隔离
# ---------------------------------------------------------------------------
class TestClassifyMoveIsolation:
    def test_move_failure_skips_file(self, tmp_path, monkeypatch):
        import _classify
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / "a.docx").write_text("x", encoding="utf-8")
        (inbox / "b.docx").write_text("y", encoding="utf-8")
        target = tmp_path / "target"
        monkeypatch.setattr(_classify, "load_config", lambda: {
            "inbox": str(inbox), "knowledge": str(tmp_path / "kn"),
            "routes": [{"name": "r", "target": str(target), "rules": [{"ext": ["*"]}]}],
        })
        monkeypatch.setattr(_classify, "LOG_DIR", str(tmp_path / "logs"))

        def _boom(*a, **k):
            raise OSError("file locked")

        monkeypatch.setattr(_classify.shutil, "move", _boom)
        result = _classify.classify()
        # 不崩溃、无文件被分类、文件留在 inbox
        assert result == []
        assert (inbox / "a.docx").exists()
        assert (inbox / "b.docx").exists()


# ---------------------------------------------------------------------------
# #21 query_graph 直接 n["metadata"] 访问
# ---------------------------------------------------------------------------
class TestQueryGraphMetadata:
    def test_node_without_metadata_no_keyerror(self, tmp_path, monkeypatch):
        import _paths
        import _graph
        gpath = tmp_path / "client_graph.json"
        gpath.write_text(json.dumps({
            "client": "t",
            "nodes": [{"id": "n001", "type": "doc", "title": "无 metadata 的旧节点"}],
            "edges": [],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "client_graph_path", lambda c: str(gpath))
        result = _graph.query_graph("t")
        assert len(result["nodes"]) == 1


# ---------------------------------------------------------------------------
# #22 _file_hash 文本模式读文件
# ---------------------------------------------------------------------------
class TestFileHash:
    def test_non_utf8_file_hashed(self, tmp_path):
        from _graph import _file_hash
        p = tmp_path / "bin.dat"
        p.write_bytes(b"\xff\xfe\x00binary\x81\x82")
        h = _file_hash(str(p))
        assert h != ""  # 文本模式会 UnicodeDecodeError 落 except 返回 ""
        assert h == _file_hash(str(p))  # 稳定

    def test_text_file_hash_matches_binary(self, tmp_path):
        import hashlib
        from _graph import _file_hash
        p = tmp_path / "a.txt"
        p.write_bytes("中文内容\r\n换行".encode("utf-8"))
        assert _file_hash(str(p)) == hashlib.md5(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# M3 quote-build/pptd-gen 门禁统一 require_confirmed（行为不变：exit 1）
# ---------------------------------------------------------------------------
class TestConfirmedGateSinglePoint:
    def test_quote_build_unconfirmed_exits_1(self, tmp_path, monkeypatch, capsys):
        import yaml
        import _cli
        monkeypatch.setattr("_cli_generate._run_pre_check", lambda **kw: {"ok": True})
        spec = tmp_path / "q.yml"
        spec.write_text(yaml.dump({"client": "测试", "confirmed": False}), encoding="utf-8")
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        monkeypatch.setattr(sys, "argv", ["_cli.py", "quote-build", str(spec), "output/通用/q"])
        try:
            with pytest.raises(SystemExit) as exc:
                _cli.main()
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# #19 补：L5 废标检查正向逻辑（修复前是死代码，从未执行过）
# ---------------------------------------------------------------------------
class TestBidRisksLogic:
    def _mk_docx(self, tmp_path, text):
        from docx import Document
        doc = Document()
        for _ in range(20):
            doc.add_paragraph(text)
        p = tmp_path / "bid.docx"
        doc.save(str(p))
        return str(p)

    def _mk_criteria(self, tmp_path, criteria):
        out = tmp_path / "output" / "蓝海集团"
        out.mkdir(parents=True)
        (out / "bid_criteria.json").write_text(
            json.dumps(criteria, ensure_ascii=False), encoding="utf-8")

    def test_all_covered_passes(self, tmp_path, monkeypatch):
        import _verify
        self._mk_criteria(tmp_path, {
            "scoring": [{"item": "技术方案"}, {"item": "售后服务"}],
            "qualifications": {"must_mention": ["ISO9001"]},
        })
        monkeypatch.setattr(_verify, "SCRIPT_DIR", str(tmp_path))
        path = self._mk_docx(tmp_path, "技术方案 售后服务 ISO9001 内容")
        ok, issues = _verify.check_bid_risks(path, "蓝海集团")
        assert ok, issues

    def test_uncovered_scoring_flagged(self, tmp_path, monkeypatch):
        import _verify
        self._mk_criteria(tmp_path, {
            "scoring": [{"item": "技术方案"}, {"item": "保密资质"}],
            "qualifications": {"must_mention": ["ISO9001"]},
        })
        monkeypatch.setattr(_verify, "SCRIPT_DIR", str(tmp_path))
        path = self._mk_docx(tmp_path, "技术方案 内容")
        ok, issues = _verify.check_bid_risks(path, "蓝海集团")
        assert not ok
        assert any("保密资质" in i for i in issues)
        assert any("ISO9001" in i for i in issues)

    def test_no_client_skips(self, tmp_path):
        import _verify
        path = self._mk_docx(tmp_path, "任意内容")
        ok, issues = _verify.check_bid_risks(path)
        assert ok and issues == []
