# -*- coding: utf-8 -*-
import _inbox_registry as reg


def _patch(tmp_path, monkeypatch):
    p = tmp_path / "inbox_registry.json"
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(p))
    return p


def test_register_and_pending(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    reg.register_entry("示例评估.pptx", "client", client="示例客户", note="示例客户门户参考")
    reg.register_entry("泛微产品介绍.pdf", "general", note="通用样张")
    pend = reg.pending_entries()
    assert [e["file"] for e in pend] == ["示例评估.pptx", "泛微产品介绍.pdf"]
    # client 过滤：只含该客户的 client 条目，general 不混入
    assert [e["file"] for e in reg.pending_entries("示例客户")] == ["示例评估.pptx"]
    assert reg.pending_entries("别的客户") == []


def test_register_dedupes_same_file(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    reg.register_entry("a.pdf", "client", client="X")
    reg.register_entry("a.pdf", "general")  # 改主意 → 更新而非追加
    entries = reg.load_registry()["entries"]
    assert len(entries) == 1
    assert entries[0]["dest"] == "general"
    assert entries[0]["client"] == ""  # general 登记必须清空客户
    assert entries[0]["status"] == "pending"


def test_mark_done(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    reg.register_entry("a.pdf", "general")
    assert reg.mark_done("a.pdf") is True
    assert reg.pending_entries() == []
    assert reg.mark_done("不存在.pdf") is False


def test_mark_done_hits_only_one(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    # 直接构造同名多条目（历史脏数据场景）：mark_done 只置一条 done
    reg.save_registry({"entries": [
        {"file": "a.pdf", "dest": "client", "client": "X", "note": "", "ts": "t1", "status": "pending"},
        {"file": "a.pdf", "dest": "client", "client": "Y", "note": "", "ts": "t2", "status": "pending"},
    ]})
    assert reg.mark_done("a.pdf") is True
    statuses = [e["status"] for e in reg.load_registry()["entries"]]
    assert statuses.count("done") == 1
    assert statuses.count("pending") == 1


def test_corrupt_registry_degrades(tmp_path, monkeypatch):
    p = _patch(tmp_path, monkeypatch)
    p.write_text("{broken json", encoding="utf-8")
    assert reg.load_registry() == {"entries": []}
    assert reg.pending_entries() == []  # 降级：只报告不移动的前提
