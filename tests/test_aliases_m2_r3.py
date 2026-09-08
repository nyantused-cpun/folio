# -*- coding: utf-8 -*-
"""M2-R3 别名表 + 查询归一化 + 别名 ablation 透传测试。

不读/写真实 `_knowledge/clients/*`。所有客户目录均用 tmp_path 隔离。
"""
import os
from types import SimpleNamespace


import _aliases
import _cli
import _recall


# ============================================================
# R3-1 suggest（#49④ aliases.md 退役：生成链已移除，仅存 suggest 与 YAML 链）
# ============================================================
class TestSuggestAliases:
    def test_returns_candidates_and_does_not_write(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        c = clients / "测试客户M2R3"
        c.mkdir(parents=True)
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))

        text = (
            "上海测试科技有限公司（简称上海测试）"
            "要上 CRM 系统，关键人王总说预算管理平台也要一起做。"
        )
        cands = _aliases.suggest_aliases(text, {})
        assert isinstance(cands, list)
        assert any(x["type"] == "公司全称" for x in cands)
        assert any(x["type"] == "系统名" for x in cands)
        assert any(x["type"] == "关键人" for x in cands)
        # 纯建议：不能写任何文件
        assert not (c / "aliases.md").exists()
        assert not (c / "aliases.yml").exists()

    def test_filters_existing_terms(self):
        cands = _aliases.suggest_aliases("CRM 系统 CRM", {"CRM": ["客户关系管理"]})
        assert all(x["term"] != "CRM" for x in cands)


# ============================================================
# R3-2 normalize_query_with_aliases / recall(use_aliases=False)
# ============================================================
class TestNormalizeQueryWithAliases:
    def test_expands_with_provided_aliases(self):
        aliases = {"CRM": ["客户关系管理"]}
        out = _aliases.normalize_query_with_aliases("CRM", aliases=aliases)
        assert "客户关系管理" in out

    def test_use_aliases_false_returns_original(self):
        assert _aliases.normalize_query_with_aliases(
            "CRM", aliases={"CRM": ["客户关系管理"]}, use_aliases=False
        ) == "CRM"

    def test_loads_client_when_client_name_given(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        c = clients / "蓝海"
        c.mkdir(parents=True)
        (c / "aliases.yml").write_text(
            "extends: global\nCRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
        out = _aliases.normalize_query_with_aliases("CRM", client_name="蓝海")
        assert "客户关系管理" in out

    def test_no_client_returns_original(self):
        assert _aliases.normalize_query_with_aliases("CRM") == "CRM"


class TestRecallUseAliasesSwitches:
    def _setup_recall_mocks(self, monkeypatch, clients=None, config=None):
        import _bm25
        if config is None:
            config = {
                "rrf": {"k": 10, "fallback_threshold": 0.05},
                "embedding": {"threshold": 0.1, "top_k": 20},
                "bm25": {"top_k": 20},
                "rerank": {"top_k": 5},
                "dedup": {"enabled": False, "max_per_doc": 1},
            }
        monkeypatch.setattr(_recall, "_RECALL_CONFIG", config)
        monkeypatch.setattr(_recall, "list_clients", lambda: ["蓝海"])
        monkeypatch.setattr(
            _recall, "get_context_path",
            lambda c: str(clients / c / "context.md") if clients else c,
        )
        monkeypatch.setattr(_recall, "_embedding_recall", lambda *a, **k: None)

        captured = {}
        # 用 monkeypatch 捕获 query_bm25 传入的 query_text

        def fake_bm25(query_text, top_k=20, client_filter=None):
            captured["query_text"] = query_text
            return []

        monkeypatch.setattr(_bm25, "query_bm25", fake_bm25)
        return captured

    def test_client_alias_expansion_off(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        c = clients / "蓝海"
        c.mkdir(parents=True)
        (c / "aliases.yml").write_text(
            "extends: global\nCRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
        captured = self._setup_recall_mocks(monkeypatch, clients)

        _recall.recall(
            "CRM", client_name="蓝海", rerank=False, return_results=False,
            use_embedding=False, use_aliases=False,
        )
        assert captured["query_text"] == "CRM"

    def test_client_alias_expansion_on(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        c = clients / "蓝海"
        c.mkdir(parents=True)
        (c / "aliases.yml").write_text(
            "extends: global\nCRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
        captured = self._setup_recall_mocks(monkeypatch, clients)

        _recall.recall(
            "CRM", client_name="蓝海", rerank=False, return_results=False,
            use_embedding=False, use_aliases=True,
        )
        assert "客户关系管理" in captured["query_text"]


# ============================================================
# R3-2 CLI chunk-read 路径语义 + graph-query 精确 ID / --query 搜索
# ============================================================
class TestChunkReadPathSemantics:
    def test_chunk_read_keeps_path_and_reads_file_with_alias_like_path(
        self, monkeypatch, tmp_path, capsys
    ):
        clients = tmp_path / "clients"
        c = clients / "蓝海"
        c.mkdir(parents=True)
        (c / "aliases.yml").write_text(
            "CRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))

        file = tmp_path / "CRM.md"
        file.write_text("hello", encoding="utf-8")
        calls = []
        monkeypatch.setattr(
            _cli, "normalize_query_with_aliases",
            lambda query, **kw: calls.append(query) or query + " 客户关系管理",
        )
        args = SimpleNamespace(path=str(file), client="蓝海", no_alias=False,
                               allow_outside=True)
        _cli.cmd_chunk_read(args)
        out = capsys.readouterr().out
        assert out == "hello\n"
        # 路径没有被别名展开污染，且文件仍可读取
        assert args.path == str(file)
        assert calls == []


class TestGraphQueryExactIdAndSearch:
    @staticmethod
    def _write_graph(tmp_path, client="蓝海", nodes=None, edges=None):
        import json as _json
        clients = tmp_path / "clients"
        c = clients / client
        c.mkdir(parents=True)
        graph = {
            "client": client,
            "nodes": nodes or [],
            "edges": edges or [],
        }
        (c / "client_graph.json").write_text(
            _json.dumps(graph, ensure_ascii=False), encoding="utf-8"
        )
        return str(clients)

    def test_node_exact_id_unchanged_even_if_alias_contains_id(
        self, monkeypatch, tmp_path, capsys
    ):
        nodes = [
            {"id": "n001", "type": "decision", "title": "CRM 系统",
             "summary": "蓝海客户关系管理项目", "metadata": {}},
            {"id": "n002", "type": "output", "title": "无关产出",
             "summary": "另一个节点", "metadata": {}},
        ]
        clients = self._write_graph(tmp_path, nodes=nodes)
        c = tmp_path / "clients" / "蓝海"
        (c / "aliases.yml").write_text(
            "客户关系管理: [n001]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", clients)
        import _paths
        monkeypatch.setattr(_paths, "CLIENTS_DIR", clients)

        calls = []
        monkeypatch.setattr(
            _cli, "normalize_query_with_aliases",
            lambda query, **kw: calls.append(query) or query + "_corrupt",
        )
        args = SimpleNamespace(
            client="蓝海", node="n001", type=None, edges=None,
            query=None, no_alias=False, json=False,
        )
        _cli.cmd_graph_query(args)
        out = capsys.readouterr().out
        assert calls == []
        assert "n001" in out

    def test_graph_query_query_expands_alias_and_finds_expected_node(
        self, monkeypatch, tmp_path, capsys
    ):
        nodes = [
            {"id": "n001", "type": "decision", "title": "CRM 系统",
             "summary": "客户关系管理项目", "metadata": {}},
            {"id": "n002", "type": "output", "title": "无关产出",
             "summary": "另一个节点", "metadata": {}},
        ]
        clients = self._write_graph(tmp_path, nodes=nodes)
        c = tmp_path / "clients" / "蓝海"
        (c / "aliases.yml").write_text(
            "CRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", clients)
        import _paths
        monkeypatch.setattr(_paths, "CLIENTS_DIR", clients)

        calls = []
        original_normalize = _cli.normalize_query_with_aliases

        def fake_normalize(query, **kw):
            calls.append(query)
            return original_normalize(query, **kw)

        monkeypatch.setattr("_cli_cmds_mem.normalize_query_with_aliases", fake_normalize)
        args = SimpleNamespace(
            client="蓝海", node=None, type=None, edges=None,
            query="CRM", no_alias=False, json=False,
        )
        _cli.cmd_graph_query(args)
        out = capsys.readouterr().out
        assert calls == ["CRM"]
        assert "n001" in out
        assert "n002" not in out

    def test_graph_query_query_no_alias_does_not_expand(
        self, monkeypatch, tmp_path, capsys
    ):
        nodes = [
            {"id": "n001", "type": "decision", "title": "其他项目",
             "summary": "客户关系管理项目", "metadata": {}},
            {"id": "n002", "type": "output", "title": "无关产出",
             "summary": "另一个节点", "metadata": {}},
        ]
        clients = self._write_graph(tmp_path, nodes=nodes)
        c = tmp_path / "clients" / "蓝海"
        (c / "aliases.yml").write_text(
            "CRM: [客户关系管理]\n", encoding="utf-8"
        )
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", clients)
        import _paths
        monkeypatch.setattr(_paths, "CLIENTS_DIR", clients)

        args = SimpleNamespace(
            client="蓝海", node=None, type=None, edges=None,
            query="CRM", no_alias=True, json=False,
        )
        _cli.cmd_graph_query(args)
        out = capsys.readouterr().out
        # 未展开时只有 token "crm"，不会命中只含“客户关系管理”的标题/摘要
        assert "n001" not in out


# ============================================================
# R3-2 CLI recall --no-alias 直接透传
# ============================================================
class TestRecallCliNoAlias:
    def test_cmd_recall_passes_no_alias(self, monkeypatch):
        captured = {}

        def fake_recall(query, **kwargs):
            captured["query"] = query
            captured.update(kwargs)
            return []

        monkeypatch.setattr("_cli_cmds_mem.recall", fake_recall)
        args = SimpleNamespace(
            keywords=["CRM"],
            keyword=False,
            client="蓝海",
            rerank=False,
            no_embedding=True,
            json=False,
            no_client_filter=False,
            client_filter=None,
            permanent_only=False,
            no_alias=True,
        )
        _cli.cmd_recall(args)
        assert captured["query"] == "CRM"
        assert captured["client_name"] == "蓝海"
        assert captured["use_aliases"] is False


# ============================================================
# R3-3 run_eval / CLI recall-eval --no-alias 透传
# ============================================================
class TestAliasAblationPassThrough:
    def test_run_eval_passes_use_aliases_to_recall(self, monkeypatch):
        from _recall_eval import run_eval
        captured = {}

        def fake_recall(query, **kwargs):
            captured.update(kwargs)
            return [{"client": "x", "score": 0.9, "path": "a.docx", "snippet": "..."}]

        monkeypatch.setattr("_session.recall", fake_recall)
        eval_set = [{"id": "gq1", "query": "q", "client": "蓝海",
                     "expect": ["a.docx"], "note": ""}]
        run_eval(eval_set, use_aliases=False)
        assert captured["use_aliases"] is False

    def test_recall_eval_no_alias_passes_to_run_eval(self, monkeypatch, tmp_path):
        import _recall_eval
        yml = tmp_path / "q.yml"
        yml.write_text(
            "- id: gq1\n  query: q1\n  expect:\n    - a.docx\n",
            encoding="utf-8",
        )
        captured = {}

        def fake_run_eval(eval_set, *, rerank=False, use_embedding=True,
                          limit=None, use_aliases=True,
                          use_query_rewrite=True):
            captured["use_aliases"] = use_aliases
            captured["use_query_rewrite"] = use_query_rewrite
            return {
                "chain": "rrf",
                "config": {},
                "per_query": [],
                "metrics": {
                    "total": 0, "hit_at_1": 0.0, "hit_at_3": 0.0, "mrr": 0.0,
                    "neg_total": 0, "neg_pass_no_hit": 0,
                    "neg_pass_fallback": 0, "neg_fail": 0, "misses": [],
                },
            }

        monkeypatch.setattr(_recall_eval, "run_eval", fake_run_eval)
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(yml), "--no-alias"],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            _cli.main()
            code = None
        except SystemExit as e:
            code = e.code
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert code in (None, 0)
        assert captured["use_aliases"] is False

    def test_cli_ablation_uses_alias_on_off_and_ignores_no_alias(
        self, monkeypatch, tmp_path, capsys
    ):
        import _recall_eval
        yml = tmp_path / "q.yml"
        yml.write_text(
            "- id: gq1\n  query: q1\n  expect:\n    - a.docx\n",
            encoding="utf-8",
        )
        calls = []

        def fake_run_eval(eval_set, *, rerank=False, use_embedding=True,
                          limit=None, use_aliases=True,
                          use_query_rewrite=True):
            calls.append((rerank, use_embedding, use_aliases,
                          use_query_rewrite))
            return {
                "chain": "bm25_only",
                "config": {},
                "per_query": [],
                "metrics": {
                    "total": 0, "hit_at_1": 0.0, "hit_at_3": 0.0, "mrr": 0.0,
                    "neg_total": 0, "neg_pass_no_hit": 0,
                    "neg_pass_fallback": 0, "neg_fail": 0, "misses": [],
                },
            }

        monkeypatch.setattr(_recall_eval, "run_eval", fake_run_eval)
        monkeypatch.setattr(
            "sys.argv",
            ["_cli.py", "recall-eval", "--file", str(yml), "--ablation", "--no-alias"],
        )
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            _cli.main()
            code = None
        except SystemExit as e:
            code = e.code
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved
        assert code in (None, 0)
        assert len(calls) == 2
        # (rerank, use_embedding, use_aliases, use_query_rewrite)
        assert calls[0] == (False, False, True, False)   # alias_on：BM25-only 离线，关闭改写（I-2）
        assert calls[1] == (False, False, False, False)  # alias_off 同
        assert "忽略 --no-alias" in capsys.readouterr().out

    def test_cli_aliases_suggest_does_not_write(self, monkeypatch, tmp_path, capsys):
        clients = tmp_path / "clients"
        c = clients / "测试客户CLI"
        c.mkdir(parents=True)
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))

        args = SimpleNamespace(
            client="测试客户CLI", text="上海测试科技有限公司 CRM 系统", file=None,
        )
        _cli.cmd_aliases_suggest(args)
        out = capsys.readouterr().out
        assert "可能新增别名建议" in out
        # #49④ aliases.md 退役：suggest 只提示维护 aliases.yml
        assert "aliases.md 已退役" in out
        assert not (c / "aliases.md").exists()
        assert not (c / "aliases.yml").exists()

    def test_parser_registers_new_commands(self):
        parser = _cli.build_parser()
        sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
        for name in ("aliases-suggest", "recall-eval"):
            assert name in sub.choices
        dispatch = _cli._build_dispatch()
        # #49④ aliases.md 退役：aliases-init 生成链已移除
        assert "aliases-init" not in dispatch
        assert "aliases-suggest" in dispatch
