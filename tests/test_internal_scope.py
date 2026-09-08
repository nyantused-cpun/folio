# -*- coding: utf-8 -*-
"""Wave2 作用域治理 #48/D2：非客户目录迁 _internal/ 后的三条验收线。

1. 枚举收口：list_client_dirs() 不含任何 _internal 子目录 / _ 前缀 / 隐藏目录；
2. 账本职能保留：save 通用 类内部账本路径仍可解析、context/decisions/outputs_index
   照写，且跳过 graph/worldbook 生成（全程 tmp_path 仿真，不碰真实客户目录）；
3. 语料消费方：embed 索引器扫描（scan_corpus_with_warnings，BM25 重建同源）
   对含内部目录的 clients 树不收入 _internal 语料。
"""

import json

import _aliases
import _context
import _embed_index
import _memory_guard
import _paths
import _session
import _theme_guard
import _worldbook


# ============================================================
# 1. 枚举收口 helper
# ============================================================
class TestListClientDirs:
    def test_excludes_internal_underscore_and_hidden(self, tmp_path):
        for name in ("真客户A", "_internal", "_template", ".hidden"):
            (tmp_path / name).mkdir()
        (tmp_path / "散文件.txt").write_text("x", encoding="utf-8")  # 非目录应排除

        assert _paths.list_client_dirs(clients_dir=str(tmp_path)) == ["真客户A"]

    def test_include_internal_returns_all_dirs(self, tmp_path):
        for name in ("真客户A", "_internal", "_template"):
            (tmp_path / name).mkdir()
        got = sorted(_paths.list_client_dirs(include_internal=True,
                                             clients_dir=str(tmp_path)))
        assert got == ["_internal", "_template", "真客户A"]

    def test_missing_root_returns_empty(self, tmp_path):
        assert _paths.list_client_dirs(clients_dir=str(tmp_path / "不存在")) == []

    def test_real_tree_has_no_internal_leak(self):
        """真实 clients 树：枚举结果不含 _internal 及其任何子目录（只读冒烟）。"""
        names = _paths.list_client_dirs()
        assert "_internal" not in names
        assert not any(n.startswith("_") for n in names)


# ============================================================
# 2. 写入端按名解析（顶层优先，_internal 回退）
# ============================================================
class TestClientDirResolution:
    def test_top_level_wins(self, tmp_path):
        (tmp_path / "真客户A").mkdir()
        (tmp_path / "_internal" / "通用").mkdir(parents=True)
        assert _paths.client_dir("真客户A", clients_dir=str(tmp_path)) == \
            str(tmp_path / "真客户A")

    def test_internal_fallback(self, tmp_path):
        (tmp_path / "_internal" / "通用").mkdir(parents=True)
        assert _paths.client_dir("通用", clients_dir=str(tmp_path)) == \
            str(tmp_path / "_internal" / "通用")

    def test_unknown_new_client_lands_top(self, tmp_path):
        assert _paths.client_dir("新客户", clients_dir=str(tmp_path)) == \
            str(tmp_path / "新客户")

    def test_is_internal_client_dir(self, tmp_path):
        internal = tmp_path / "_internal" / "通用"
        internal.mkdir(parents=True)
        top = tmp_path / "真客户A"
        top.mkdir()
        assert _paths.is_internal_client_dir(str(internal), clients_dir=str(tmp_path))
        assert not _paths.is_internal_client_dir(str(top), clients_dir=str(tmp_path))
        assert not _paths.is_internal_client_dir(str(tmp_path / "不存在"),
                                                 clients_dir=str(tmp_path))

    def test_context_and_ensure_resolve_internal(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        (clients / "_internal" / "通用").mkdir(parents=True)
        (clients / "_internal" / "通用" / "context.md").write_text(
            "# 项目上下文记录\n", encoding="utf-8")
        for mod in (_context, _aliases, _theme_guard, _memory_guard):
            monkeypatch.setattr(mod, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))

        assert _context.get_context_path("通用") == \
            str(clients / "_internal" / "通用" / "context.md")
        assert _context.ensure_client_dir("通用") == \
            str(clients / "_internal" / "通用")
        # 解析到内部位时不得在顶层复活同名目录
        assert not (clients / "通用").exists()


# ============================================================
# 3. save 账本语义：照写三件套 + 跳过 graph/worldbook
# ============================================================
def _setup_save_sandbox(tmp_path, monkeypatch):
    """save_session 沙箱：全部写入目标重定向 tmp；索引/案例卡打桩；图谱/世界书挂记录器。"""
    clients = tmp_path / "clients"
    clients.mkdir()
    for mod in (_context, _aliases, _theme_guard, _memory_guard):
        monkeypatch.setattr(mod, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_paths, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))

    monkeypatch.setattr(_embed_index, "build_embedding_index", lambda *a, **kw: {})
    monkeypatch.setattr(_session, "_sync_bm25_if_stale", lambda *a, **kw: None)
    monkeypatch.setattr(_session, "_extract_case_cards", lambda *a, **kw: 0)

    calls = {"graph": 0, "worldbook": 0}
    monkeypatch.setattr(_session, "build_client_graph",
                        lambda name: calls.__setitem__("graph", calls["graph"] + 1))
    monkeypatch.setattr(_worldbook, "build_worldbook",
                        lambda name: calls.__setitem__("worldbook", calls["worldbook"] + 1))
    return clients, calls


class TestSaveInternalLedger:
    def test_internal_ledger_saves_without_graph_worldbook(self, tmp_path, monkeypatch):
        clients, calls = _setup_save_sandbox(tmp_path, monkeypatch)
        ledger = clients / "_internal" / "通用"
        ledger.mkdir(parents=True)
        (ledger / "context.md").write_text("# 项目上下文记录\n", encoding="utf-8")
        out_dir = tmp_path / "output" / "通用"
        out_dir.mkdir(parents=True)
        (out_dir / "通用_方案_v1.html").write_text("<html></html>", encoding="utf-8")

        ok = _session.save_session("通用", input_desc="账本输入",
                                   decisions="账本决策结论", outputs="output/通用/通用_方案_v1.html")
        assert ok is True

        # 三件套照写，且全部落在 _internal/ 内部位
        assert "账本输入" in (ledger / "context.md").read_text(encoding="utf-8")
        assert "账本决策结论" in (ledger / "decisions.md").read_text(encoding="utf-8")
        oij = json.loads((ledger / "outputs_index.json").read_text(encoding="utf-8"))
        assert any("通用_方案_v1.html" in json.dumps(o, ensure_ascii=False)
                   for o in oij.get("outputs", []))
        # task_history 照写
        hist = json.loads((tmp_path / "task_history.json").read_text(encoding="utf-8"))
        assert any(e.get("project") == "client:通用" for e in hist)

        # 账本不产世界书/图谱：记录器零调用 + clients 树无产物
        assert calls == {"graph": 0, "worldbook": 0}
        assert not list(clients.rglob("client_graph.json"))
        assert not list(clients.rglob("client_index.md"))
        # 顶层不得复活同名目录
        assert not (clients / "通用").exists()

    def test_real_client_still_builds_graph_worldbook(self, tmp_path, monkeypatch):
        clients, calls = _setup_save_sandbox(tmp_path, monkeypatch)
        (clients / "真客户B").mkdir()

        assert _session.save_session("真客户B", input_desc="真客户输入") is True
        assert calls["graph"] == 1
        assert calls["worldbook"] == 1


# ============================================================
# 4. 语料消费方：embed 扫描（BM25 重建同源）不含 _internal
# ============================================================
class TestEmbedScanExcludesInternal:
    def test_scan_corpus_skips_internal(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        clients = proj / "_knowledge" / "clients"
        (clients / "真客户C").mkdir(parents=True)
        (clients / "真客户C" / "context.md").write_text(
            "## [2026-09-06] 第 1 次会话\n\n真客户C的上下文内容，长度足以入语料索引。" * 2,
            encoding="utf-8")
        internal = clients / "_internal" / "通用"
        internal.mkdir(parents=True)
        (internal / "context.md").write_text(
            "## [2026-09-06] 第 1 次会话\n\n内部账本的上下文内容，不应入索引语料。" * 2,
            encoding="utf-8")

        monkeypatch.setattr(_embed_index, "SCRIPT_DIR", str(proj))
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))

        corpus, _warnings = _embed_index.scan_corpus_with_warnings()
        paths = [p for p, _t in corpus]
        assert any("真客户C" in p for p in paths)
        assert not any("_internal" in p for p in paths)
