# -*- coding: utf-8 -*-
"""outputs_index.json 程序写入方：save 时自动从 output/{客户}/ 扫描合并。

此前 outputs_index.json 只能手工维护（迁移审计断链 #3），
update_outputs_index 补上写入路径：保留已有条目、补新文件、幂等。
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
        assert idx["outputs"][0]["status"] == "废弃"  # 已有条目不覆盖
        assert "output/测试客户/旧手工条目.pptx" in idx["outputs"]  # 字符串条目保留

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
