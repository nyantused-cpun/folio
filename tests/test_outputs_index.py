# -*- coding: utf-8 -*-
"""outputs_index.json 程序写入方：save 时自动从 output/{客户}/ 扫描合并。

此前 outputs_index.json 只能手工维护（迁移审计断链 #3），
update_outputs_index 补上写入路径：保留已有条目、补新文件、幂等。
W1-5 起：悬空条目改删除为 missing 标记（保留历史设计不变），
字符串旧条目规范化为 dict；三消费端（L3/graph/worldbook）跳过 missing。
"""

import json

import _paths
from _session import update_outputs_index


def _isolate(tmp_path, monkeypatch):
    """把产出目录/客户目录/项目根都指到 tmp，避免碰真实数据。"""
    out = tmp_path / "output"
    clients = tmp_path / "clients"
    monkeypatch.setattr(_paths, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_paths, "SCRIPT_DIR", str(tmp_path))
    return out, clients


def _read_index(clients, client="测试客户"):
    return json.loads(
        (clients / client / "outputs_index.json").read_text(encoding="utf-8"))


class TestUpdateOutputsIndex:
    def test_scans_new_outputs_and_parses_naming(self, tmp_path, monkeypatch):
        out, clients = _isolate(tmp_path, monkeypatch)
        cdir = out / "测试客户"
        cdir.mkdir(parents=True)
        (cdir / "测试客户_需求分析_v1.md").write_text("x", encoding="utf-8")
        (cdir / "测试客户_方案汇报_v2.pptx").write_bytes(b"x")
        (cdir / "中间截图.png").write_bytes(b"x")  # 非交付物扩展名，不入索引
        (cdir / "~$锁文件.docx").write_bytes(b"x")  # Office 锁文件，跳过

        assert update_outputs_index("测试客户") == 2
        idx = _read_index(clients)
        assert idx["client"] == "测试客户"
        assert idx["last_update"]
        files = {e["file"]: e for e in idx["outputs"]}
        assert set(files) == {
            "output/测试客户/测试客户_需求分析_v1.md",
            "output/测试客户/测试客户_方案汇报_v2.pptx",
        }
        e = files["output/测试客户/测试客户_需求分析_v1.md"]
        assert e["version"] == "v1"
        assert e["type"] == "需求分析"
        assert e["status"] == "在用"

    def test_preserves_existing_entries(self, tmp_path, monkeypatch):
        out, clients = _isolate(tmp_path, monkeypatch)
        cdir = out / "测试客户"
        cdir.mkdir(parents=True)
        (cdir / "测试客户_需求分析_v1.md").write_text("x", encoding="utf-8")
        (cdir / "测试客户_报价_v1.xlsx").write_bytes(b"x")
        kdir = clients / "测试客户"
        kdir.mkdir(parents=True)
        # 已有条目：一个人工标了"废弃"，一个旧式字符串格式
        (kdir / "outputs_index.json").write_text(json.dumps({
            "client": "测试客户",
            "last_update": "2026-06-24",
            "industry": "汽车零部件",
            "outputs": [
                {"version": "v1", "file": "output/测试客户/测试客户_需求分析_v1.md",
                 "type": "需求分析", "status": "废弃", "date": "2026-06-24"},
                "output/测试客户/旧手工条目.pptx",
            ],
        }, ensure_ascii=False), encoding="utf-8")

        assert update_outputs_index("测试客户") == 1  # 只有 xlsx 是新的
        idx = _read_index(clients)
        assert idx["industry"] == "汽车零部件"  # 人工字段不动
        assert idx["outputs"][0]["status"] == "废弃"  # 已有条目不覆盖（文件在盘）
        assert "missing" not in idx["outputs"][0]
        # W1-5：字符串旧条目规范化为 dict；文件不在盘 -> missing 标记
        legacy = idx["outputs"][1]
        assert isinstance(legacy, dict)
        assert legacy["file"] == "output/测试客户/旧手工条目.pptx"
        assert legacy["missing"] is True
        assert legacy["status"] == "已归档/缺失"

    def test_missing_flag_and_selfheal(self, tmp_path, monkeypatch):
        """W1-5：删文件 -> missing 标记；文件回迁 -> 标记自清除、status 回位。"""
        out, clients = _isolate(tmp_path, monkeypatch)
        cdir = out / "测试客户"
        cdir.mkdir(parents=True)
        f = cdir / "测试客户_方案_v1.html"
        f.write_text("x", encoding="utf-8")
        assert update_outputs_index("测试客户") == 1
        f.unlink()
        assert update_outputs_index("测试客户") == 0
        e = _read_index(clients)["outputs"][0]
        assert e["missing"] is True
        assert e["status"] == "已归档/缺失"
        # 条目仍在（保留历史，不删除）
        assert e["file"] == "output/测试客户/测试客户_方案_v1.html"
        # 归档物回迁自愈
        f.write_text("x", encoding="utf-8")
        assert update_outputs_index("测试客户") == 0
        e = _read_index(clients)["outputs"][0]
        assert "missing" not in e
        assert e["status"] == "在用"

    def test_legacy_string_existing_normalized(self, tmp_path, monkeypatch):
        """W1-5：在盘的字符串旧条目规范化为 dict（不误标 missing）。"""
        out, clients = _isolate(tmp_path, monkeypatch)
        cdir = out / "测试客户"
        cdir.mkdir(parents=True)
        (cdir / "旧手工条目.pptx").write_bytes(b"x")
        kdir = clients / "测试客户"
        kdir.mkdir(parents=True)
        (kdir / "outputs_index.json").write_text(json.dumps({
            "outputs": ["output/测试客户/旧手工条目.pptx"],
        }, ensure_ascii=False), encoding="utf-8")
        assert update_outputs_index("测试客户") == 0
        e = _read_index(clients)["outputs"][0]
        assert isinstance(e, dict)
        assert e["file"] == "output/测试客户/旧手工条目.pptx"
        assert "missing" not in e
        assert e["status"] == "在用"


# ============================================================
# W1-5：消费端过滤（L3 / graph / worldbook 跳过 missing 条目）
# ============================================================
class TestConsumersSkipMissing:
    IDX = {
        "client": "测试客户",
        "outputs": [
            {"file": "output/测试客户/在用_v1.html", "version": "v1",
             "type": "方案", "status": "在用", "date": "2026-09-01"},
            {"file": "output/测试客户/已归档_v1.html", "version": "v1",
             "type": "方案", "status": "已归档/缺失", "date": "2026-09-01",
             "missing": True},
        ],
    }

    def test_graph_extract_skips_missing(self):
        from _graph import _extract_output_nodes
        nodes, _ = _extract_output_nodes(self.IDX, "测试客户")
        paths = [n["details_path"] for n in nodes]
        assert paths == ["output/测试客户/在用_v1.html"]

    def test_worldbook_table_skips_missing(self):
        from _worldbook import _build_output_version_table
        table = "\n".join(_build_output_version_table(self.IDX))
        # 系列名经 _normalize_output_title 剥版本号 -> 用状态判别 missing 是否入表
        assert "已归档" not in table  # missing 条目整行排除
        assert "| 在用 | html | v1 | 1 |" in table  # 在用条目正常成行

    def test_l3_load_skips_missing(self, tmp_path, monkeypatch):
        import _context
        import _paths
        clients = tmp_path / "clients"
        kdir = clients / "测试客户"
        kdir.mkdir(parents=True)
        (kdir / "outputs_index.json").write_text(
            json.dumps(self.IDX, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_context, "SCRIPT_DIR", str(tmp_path))
        # client_index.md 不存在走降级分支（打印 warn，不影响本测试）
        monkeypatch.setattr(_paths, "client_index_path",
                            lambda name: str(tmp_path / "nope.md"))
        loaded = _context.load_context_by_level("测试客户", "L3")
        files = [o["file"] for o in loaded["outputs_index"]["outputs"]]
        assert files == ["output/测试客户/在用_v1.html"]

    def test_idempotent(self, tmp_path, monkeypatch):
        out, clients = _isolate(tmp_path, monkeypatch)
        cdir = out / "测试客户"
        cdir.mkdir(parents=True)
        (cdir / "测试客户_方案_v1.html").write_text("x", encoding="utf-8")
        assert update_outputs_index("测试客户") == 1
        assert update_outputs_index("测试客户") == 0
        assert len(_read_index(clients)["outputs"]) == 1

    def test_missing_output_dir_is_noop(self, tmp_path, monkeypatch):
        out, clients = _isolate(tmp_path, monkeypatch)
        assert update_outputs_index("无产出客户") == 0
        assert not (clients / "无产出客户" / "outputs_index.json").exists()

    def test_output_dir_missing_still_marks_dangling_entries(self, tmp_path, monkeypatch):
        """目录缺失早退修复：output/{客户}/ 不存在时，存量索引悬空条目仍标 missing。"""
        out, clients = _isolate(tmp_path, monkeypatch)
        kdir = clients / "测试客户"
        kdir.mkdir(parents=True)
        (kdir / "outputs_index.json").write_text(json.dumps({
            "client": "测试客户",
            "last_update": "2026-09-01",
            "outputs": [
                {"version": "v1", "file": "output/测试客户/测试客户_方案_v1.html",
                 "type": "方案", "status": "在用", "date": "2026-09-01"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        # output/测试客户/ 不存在（从未建/已清空）——此前直接 return 0，悬空条目漏标
        assert not (out / "测试客户").exists()

        assert update_outputs_index("测试客户") == 0
        e = _read_index(clients)["outputs"][0]
        assert e["missing"] is True
        assert e["status"] == "已归档/缺失"
        assert e["file"] == "output/测试客户/测试客户_方案_v1.html"  # 条目保留不删
