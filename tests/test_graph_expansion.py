# -*- coding: utf-8 -*-
"""图扩展双层检索回归测试。

覆盖本轮修复点：
1. revised_from 只连「同文档系列不同版本」的 output，不跨系列、不连 decision；
2. _full_build 的 ID 重分配后不再二次映射边（历史 bug：边被错指到 decision）；
3. _expand_graph_2hop 返回带 summary 的 2 跳邻接；
4. _find_pivot_nodes output 加权，优先命中产出物。
"""
import json

from _graph import (_infer_edges, _expand_graph_2hop, _find_pivot_nodes,
                    _full_build, _normalize_output_title, _same_output_series)


def _output(i, title, version, date, file_type="html"):
    return {
        "id": f"n{i:03d}", "type": "output", "title": title,
        "summary": f"{version} (在用)",
        "details_path": f"output/测试客户/{title}",
        "metadata": {"version": version, "status": "在用",
                     "file_type": file_type, "date": date},
        "created": date, "updated": date,
    }


def _decision(i, title, date):
    return {
        "id": f"n{i:03d}", "type": "decision", "title": title,
        "summary": "决策内容", "details_path": "decisions.md",
        "metadata": {"date": date, "subtype": "general"},
        "created": date, "updated": date,
    }


# 6 产出物（白皮书 v1/v2/v3、产品说明 v1/v2、七层架构 v1）+ 2 决策
NODES = [
    _output(0, "兰亭_技术白皮书_v1.html", "v1", "2026-07-01"),
    _output(1, "兰亭_技术白皮书_v2.html", "v2", "2026-07-02"),
    _output(2, "兰亭_技术白皮书_v3.html", "v3", "2026-07-03"),
    _output(3, "兰亭_产品说明_v1.html", "v1", "2026-07-01"),
    _output(4, "兰亭_产品说明_v2.html", "v2", "2026-07-02"),
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


class TestExpand2hop:
    def test_returns_summary_and_hops(self, tmp_path):
        graph = {
            "nodes": [
                {"id": "n000", "type": "output", "title": "技术白皮书_v1.html",
                 "summary": "v1", "metadata": {}},
                {"id": "n001", "type": "output", "title": "技术白皮书_v2.html",
                 "summary": "v2", "metadata": {}},
                {"id": "n002", "type": "output", "title": "技术白皮书_v3.html",
                 "summary": "v3", "metadata": {}},
            ],
            "edges": [
                {"from": "n001", "to": "n000", "type": "revised_from"},
                {"from": "n002", "to": "n001", "type": "revised_from"},
            ],
        }
        gp = tmp_path / "g.json"
        gp.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        exps = _expand_graph_2hop(str(gp), "n002")
        by_id = {e["id"]: e for e in exps}
        assert by_id["n001"]["hops"] == 1
        assert by_id["n001"]["summary"] == "v2"
        assert by_id["n000"]["hops"] == 2


class TestPivot:
    def test_prefers_output_over_decision(self):
        graph = {"nodes": [n.copy() for n in NODES],
                 "edges": [{"from": "n001", "to": "n000", "type": "revised_from"}]}
        pivots = _find_pivot_nodes("技术白皮书", graph, top_k=2)
        assert pivots, "应命中技术白皮书产出物"
        assert pivots[0]["node"]["type"] == "output"
        assert "技术白皮书" in pivots[0]["node"]["title"]
