# -*- coding: utf-8 -*-
"""版本链索引（原图扩展）回归测试。

M2-R2 把 client_graph.json 从自动召回图扩展降级为版本链索引/调试资产。
覆盖版本链语义：
1. revised_from 只连「同文档系列不同版本」的 output，不跨系列、不连 decision；
2. 显式「修订决策 N」supersedes 保留，auto-consolidate 伪边不再产生；
3. used_method / decided_by / triggers 伪边不再产生；
4. query_graph 默认过滤 status=removed。
"""
import json

import _paths

from _graph import (_infer_edges, _full_build, _normalize_output_title,
                    _same_output_series, query_graph)


def _output(i, title, version, date, file_type="html", **metadata_extra):
    metadata = {"version": version, "status": "在用",
                "file_type": file_type, "date": date}
    metadata.update(metadata_extra)
    return {
        "id": f"n{i:03d}", "type": "output", "title": title,
        "summary": f"{version} (在用)",
        "details_path": f"output/测试客户/{title}",
        "metadata": metadata,
        "created": date, "updated": date,
    }


def _decision(i, title, date, subtype="general"):
    return {
        "id": f"n{i:03d}", "type": "decision", "title": title,
        "summary": "决策内容", "details_path": "decisions.md",
        "metadata": {"date": date, "subtype": subtype},
        "created": date, "updated": date,
    }


# 6 产出物（白皮书 v1/v2/v3、产品说明 v1/v2、七层架构 v1）+ 2 决策
NODES = [
    _output(0, "售前助手_技术白皮书_v1.html", "v1", "2026-07-01"),
    _output(1, "售前助手_技术白皮书_v2.html", "v2", "2026-07-02"),
    _output(2, "售前助手_技术白皮书_v3.html", "v3", "2026-07-03"),
    _output(3, "售前助手_产品说明_v1.html", "v1", "2026-07-01"),
    _output(4, "售前助手_产品说明_v2.html", "v2", "2026-07-02"),
    _output(5, "AI时代企业信息化七层架构_v1.html", "v1", "2026-07-01"),
    _decision(6, "架构方向决策", "2026-07-01"),
    _decision(7, "报价决策", "2026-07-02"),
]


class TestNormalizeTitle:
    def test_strip_ext_and_version(self):
        assert _normalize_output_title("技术白皮书_v2.html") == "技术白皮书"
        assert _normalize_output_title("架构图_v2.9.6.html") == "架构图"
        assert _normalize_output_title("产品说明_v3_汇报版.html") == "产品说明_汇报版"

    def test_same_series(self):
        a = _output(0, "技术白皮书_v1.html", "v1", "2026-07-01")
        b = _output(1, "技术白皮书_v2.html", "v2", "2026-07-02")
        c = _output(2, "产品说明_v1.html", "v1", "2026-07-01")
        assert _same_output_series(a, b) is True
        assert _same_output_series(a, c) is False


class TestRevisedFromEdges:
    def test_only_same_series_outputs_linked(self):
        edges = _infer_edges([n.copy() for n in NODES])
        revised = [e for e in edges if e["type"] == "revised_from"]
        types = {n["id"]: n["type"] for n in NODES}
        # 只允许 output 参与 revised_from
        for e in revised:
            assert types[e["from"]] == "output"
            assert types[e["to"]] == "output"
        # 白皮书 3 版本 -> 3 条；产品说明 2 版本 -> 1 条；七层架构独立 0 条
        assert len(revised) == 4

    def test_cross_series_not_linked(self):
        edges = _infer_edges([n.copy() for n in NODES])
        revised = {(e["from"], e["to"]) for e in edges if e["type"] == "revised_from"}
        # 七层架构 n005 不与任何节点连 revised_from
        assert not any("n005" in pair for pair in revised)

    def test_transitive_revised_from_materialized(self):
        edges = _infer_edges([n.copy() for n in NODES])
        indirect = [e for e in edges if e["type"] == "indirectly_revised_from"]
        # 白皮书链：n002 -> n001 -> n000，因此 n002 indirectly_revised_from n000
        assert any(e["from"] == "n002" and e["to"] == "n000" for e in indirect)


class TestExplicitSupersedes:
    def test_explicit_revises_decision_kept(self):
        nodes = [
            _decision(0, "决策 1：架构方向", "2026-07-01", subtype="architecture"),
            _decision(1, "修订决策 1", "2026-07-02", subtype="architecture"),
        ]
        edges = _infer_edges([n.copy() for n in nodes])
        supersedes = [e for e in edges if e["type"] == "supersedes"]
        assert any(e["from"] == "n001" and e["to"] == "n000" for e in supersedes)


class TestNoPseudoEdges:
    def test_used_method_decided_by_triggers_not_inferred(self):
        # method 元数据仍存在也不会产生 used_method；关键词/日期重叠也不再产生
        # decided_by / triggers / auto-consolidate supersedes。
        nodes = [
            _output(0, "技术白皮书_v1.html", "v1", "2026-07-01",
                    method="auto-scan"),
            _output(1, "技术白皮书_v2.html", "v2", "2026-07-02"),
            _decision(2, "架构方向决策", "2026-07-01", subtype="architecture"),
            _decision(3, "架构方向决策 v2", "2026-07-03", subtype="architecture"),
        ]
        edges = _infer_edges([n.copy() for n in nodes])
        types = {e["type"] for e in edges}
        assert "used_method" not in types
        assert "decided_by" not in types
        assert "triggers" not in types
        # 自动 consolidate：同 subtype + 关键词重叠，不得自动产生 supersedes
        assert "supersedes" not in types


class TestFullBuild:
    def test_edges_not_cross_type(self, tmp_path):
        decisions = tmp_path / "decisions.md"
        decisions.write_text(
            "### D-001 · 架构方向\n"
            "- **日期**: 2026-07-01\n"
            "- **决策**: 采用七层架构\n",
            encoding="utf-8",
        )
        oij = tmp_path / "outputs_index.json"
        oij.write_text(json.dumps({
            "outputs": [
                {"version": "v1", "file": "output/测试客户/技术白皮书_v1.html",
                 "type": "技术白皮书", "status": "在用", "date": "2026-07-01",
                 "method": "auto-scan"},
                {"version": "v2", "file": "output/测试客户/技术白皮书_v2.html",
                 "type": "技术白皮书", "status": "在用", "date": "2026-07-02",
                 "method": "auto-scan"},
                {"version": "v3", "file": "output/测试客户/技术白皮书_v3.html",
                 "type": "技术白皮书", "status": "在用", "date": "2026-07-03",
                 "method": "auto-scan"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        insights = tmp_path / "insights"
        insights.mkdir()

        graph = _full_build(
            "测试客户",
            str(decisions), str(oij), str(insights),
            lambda name: str(tmp_path / "client_graph.json"),
            lambda name: str(tmp_path / "client_index.md"),
            {"decisions.md": "h1", "outputs_index.json": "h2", "insights": "h3"},
        )

        nm = {n["id"]: n for n in graph["nodes"]}
        revised = [e for e in graph["edges"] if e["type"] == "revised_from"]
        assert revised, "应有 revised_from 边"
        for e in revised:
            assert nm[e["from"]]["type"] == "output"
            assert nm[e["to"]]["type"] == "output"
        assert len(revised) == 3
        # method 字段已被移除，不产生 used_method
        assert all(e["type"] != "used_method" for e in graph["edges"])


class TestQueryGraphRemovedFilter:
    def test_default_filters_removed_nodes(self, tmp_path, monkeypatch):
        clients = tmp_path / "clients"
        d = clients / "测试客户"
        d.mkdir(parents=True, exist_ok=True)
        graph = {
            "client": "测试客户",
            "nodes": [
                {"id": "n000", "type": "output", "title": "在用产出",
                 "summary": "", "metadata": {"status": "在用"},
                 "created": "2026-07-01", "updated": "2026-07-01"},
                {"id": "n001", "type": "output", "title": "已移除产出",
                 "summary": "", "metadata": {"status": "removed"},
                 "created": "2026-07-01", "updated": "2026-07-01"},
            ],
            "edges": [],
        }
        (d / "client_graph.json").write_text(
            json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))

        result = query_graph("测试客户", include_removed=False)
        assert [n["id"] for n in result["nodes"]] == ["n000"]
        result_all = query_graph("测试客户", include_removed=True)
        assert len(result_all["nodes"]) == 2


class TestExpansionFunctionsRemoved:
    def test_graph_expansion_functions_no_longer_exported(self):
        import _graph
        assert not hasattr(_graph, "_expand_graph_2hop")
        assert not hasattr(_graph, "_find_pivot_nodes")
