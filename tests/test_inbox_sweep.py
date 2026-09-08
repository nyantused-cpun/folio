# -*- coding: utf-8 -*-
import json

import _inbox_scan as scan


def _mk(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "_pending").mkdir()
    (tmp_path / "_knowledge" / "clients").mkdir(parents=True)
    (tmp_path / ".folio" / "logs").mkdir(parents=True)
    return tmp_path


def test_sweep_moves_unregistered_by_month(tmp_path, monkeypatch):
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    (root / "inbox" / "材料.pptx").write_bytes(b"x")
    r = scan.sweep_pending(str(root))
    assert len(r["swept"]) == 1
    dest = r["swept"][0]["dest"]
    assert "_pending" in dest and "20" in dest  # YYYY-MM 目录
    assert not (root / "inbox" / "材料.pptx").exists()
    assert (root / dest).exists()


def test_sweep_skips_registry_pending_and_subdirs(tmp_path, monkeypatch):
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    (root / "inbox" / "已登记.pdf").write_bytes(b"x")
    (root / "inbox" / "_scan_reports").mkdir()
    (root / "inbox" / "_scan_reports" / "a.json").write_text("{}")
    import _inbox_registry as reg
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(root / ".folio" / "logs" / "inbox_registry.json"))
    reg.register_entry("已登记.pdf", "general")
    r = scan.sweep_pending(str(root))
    assert r["swept"] == []
    assert (root / "inbox" / "已登记.pdf").exists()


def test_strong_hint(tmp_path, monkeypatch):
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    monkeypatch.chdir(root)  # load_config 相对路径兜底
    # 自带分类配置：本测试原先隐式依赖仓库根 _classify_config.json 的真实客户
    # 关键词（经 _inbox_scan._config_cache 进程内缓存渗入）——改为夹具自带
    # 配置 + 清缓存，与真实配置解耦（主仓/folio 两侧行为一致）。
    import _classify
    (root / "_classify_config.json").write_text(json.dumps({
        "routes": [{"name": "客户-示例集团",
                    "target": "_knowledge/clients/示例集团/refs",
                    "output_target": "output/示例集团",
                    "rules": [{"ext": [".docx"], "keyword": ["示例集团"],
                               "strong": True}]}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr(_classify, "CONFIG_PATH", str(root / "_classify_config.json"))
    monkeypatch.setattr(scan, "_config_cache", None)
    try:
        hint = scan.strong_hint(str(root), "示例集团OA需求.docx")
        assert "示例集团" in hint
        assert scan.strong_hint(str(root), "无关文件名.docx") == ""
    finally:
        scan._config_cache = None  # 还原缓存，防真实配置测试被污染


def test_sweep_flags_duplicate_same_name_same_size(tmp_path, monkeypatch):
    """与客户 refs 同名同大小 → 仍进中转区，reason 标"疑似重复"（不再进 _trash）。"""
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    (root / "_knowledge" / "clients" / "蓝海" / "refs").mkdir(parents=True)
    (root / "_knowledge" / "clients" / "蓝海" / "refs" / "旧文件.txt").write_bytes(b"hello world" * 10)
    (root / "inbox" / "旧文件.txt").write_bytes(b"hello world" * 10)
    r = scan.sweep_pending(str(root))
    assert len(r["swept"]) == 1
    assert "疑似重复" in r["swept"][0]["reason"]
    assert "_trash" not in r["swept"][0]["dest"]


def test_sweep_dry_run_moves_nothing(tmp_path, monkeypatch):
    """dry_run=True：列出将被收走的文件但不移动。"""
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    (root / "inbox" / "材料.pptx").write_bytes(b"x")
    r = scan.sweep_pending(str(root), dry_run=True)
    assert len(r["swept"]) == 1
    assert (root / "inbox" / "材料.pptx").exists()  # 未动


def test_migrate_uncategorized(tmp_path, monkeypatch):
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    unc = root / "inbox" / "_uncategorized"
    unc.mkdir()
    (unc / "旧材料.docx").write_bytes(b"x")
    r = scan.migrate_uncategorized(str(root))
    assert r["moved"] == 1
    assert (root / "inbox" / "_pending" / "legacy-uncategorized" / "旧材料.docx").exists()
    assert not unc.exists()
    assert scan.migrate_uncategorized(str(root))["moved"] == 0  # 幂等


def test_refresh_todo_marks_over_30d(tmp_path, monkeypatch):
    root = _mk(tmp_path)
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(root))
    mdir = root / "inbox" / "_pending" / "2026-08"
    mdir.mkdir(parents=True)
    (mdir / "老的.pdf").write_bytes(b"x")
    import os
    old = (root / "inbox" / "_pending" / "_todo.md")
    old.write_text("seed")  # 占位
    os.utime(mdir / "老的.pdf", (0, 0))  # mtime 归零 → 超 30 天
    todo = scan.refresh_todo(str(root))
    text = (root / todo).read_text(encoding="utf-8") if not os.path.isabs(todo) else open(todo, encoding="utf-8").read()
    assert "超 30 天" in text and "老的.pdf" in text
