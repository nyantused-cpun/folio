# -*- coding: utf-8 -*-
import pytest
import _archive_auto as aa
import _inbox_registry as reg
import _inbox_scan as scan


def _env(tmp_path, monkeypatch):
    """把所有模块级路径指进 tmp，防止碰到真仓库。"""
    monkeypatch.setattr(reg, "REGISTRY_PATH", str(tmp_path / ".folio" / "logs" / "inbox_registry.json"))
    monkeypatch.setattr(aa, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(aa, "INDEX_PATH", str(tmp_path / "_knowledge" / "index.json"))
    monkeypatch.setattr(scan, "SCRIPT_DIR", str(tmp_path))
    (tmp_path / "_knowledge" / "clients" / "示例客户" / "refs").mkdir(parents=True)
    (tmp_path / "_knowledge" / "refs").mkdir(parents=True)
    (tmp_path / ".folio" / "logs").mkdir(parents=True)
    return tmp_path


def test_save_moves_registered_only(tmp_path, monkeypatch):
    root = _env(tmp_path, monkeypatch)
    (root / "inbox").mkdir()
    (root / "inbox" / "示例客户材料.pptx").write_bytes(b"x")
    (root / "inbox" / "通用样张.pdf").write_bytes(b"y")
    (root / "inbox" / "陌生文件.docx").write_bytes(b"z")
    aa.archive_note(["示例客户材料.pptx"], dest="client", client_name="示例客户")
    aa.archive_note(["通用样张.pdf"], dest="general", note="通用样张")
    r = aa.auto_archive("示例客户")
    assert r["archived"] == ["示例客户材料.pptx", "通用样张.pdf"]
    assert (root / "_knowledge" / "clients" / "示例客户" / "refs" / "示例客户材料.pptx").exists()
    assert (root / "_knowledge" / "refs" / "通用样张.pdf").exists()
    # 未登记的被 sweep 收走，inbox 根目录必空
    assert r["swept"] and r["swept"][0]["file"] == "陌生文件.docx"
    assert not (root / "inbox" / "陌生文件.docx").exists()
    # 登记表条目已置 done
    assert reg.pending_entries() == []


def test_no_cross_client_takeaway(tmp_path, monkeypatch):
    root = _env(tmp_path, monkeypatch)
    (root / "inbox").mkdir()
    (root / "inbox" / "示例客户的参考.docx").write_bytes(b"x")
    aa.archive_note(["示例客户的参考.docx"], dest="client", client_name="示例客户")
    r = aa.auto_archive("蓝海")  # 另一个客户 save
    assert r["archived"] == []   # 登记给示例客户的不被蓝海收走
    assert (root / "inbox" / "示例客户的参考.docx").exists()
    assert r["unregistered_hint"] == ["示例客户的参考.docx"]  # 只提示不移动


def test_auto_archive_finds_file_swept_into_pending(tmp_path, monkeypatch):
    """登记消费必须覆盖 _pending/YYYY-MM/ 落点：sweep 先于 archive-note 时文件的常规形态。"""
    root = _env(tmp_path, monkeypatch)
    month = root / "inbox" / "_pending" / "2026-09"
    month.mkdir(parents=True)
    (month / "示例客户清单.xlsx").write_bytes(b"x")
    aa.archive_note(["示例客户清单.xlsx"], dest="client", client_name="示例客户")
    r = aa.auto_archive("示例客户")
    assert r["archived"] == ["示例客户清单.xlsx"]
    assert r["pending_review"] == []
    assert (root / "_knowledge" / "clients" / "示例客户" / "refs" / "示例客户清单.xlsx").exists()
    assert not (month / "示例客户清单.xlsx").exists()
    assert reg.pending_entries() == []


# ---------- C-A6：dst 撞名改名后，销账按原名、落盘/索引/返回值记实名 ----------
# 旧行为：moved/索引/archived 全记原名——mark_done 把账销了但盘上是时间戳
# 实名，index 指向不存在的文件，同名材料再次归档即重复/断链。


def test_auto_archive_collision_rename_registers_actual_name(tmp_path, monkeypatch):
    root = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(aa, "LOG_DIR", str(root / ".folio" / "logs"))
    refs = root / "_knowledge" / "clients" / "示例客户" / "refs"
    (refs / "示例客户材料.pptx").write_bytes(b"old")   # refs 预置同名 -> 必撞名
    (root / "inbox").mkdir()
    (root / "inbox" / "示例客户材料.pptx").write_bytes(b"new")
    aa.archive_note(["示例客户材料.pptx"], dest="client", client_name="示例客户")
    r = aa.auto_archive("示例客户")
    # archived 返回实名（时间戳后缀），不再谎报原名
    assert len(r["archived"]) == 1
    actual = r["archived"][0]
    assert actual != "示例客户材料.pptx"
    assert actual.startswith("示例客户材料_") and actual.endswith(".pptx")
    # 盘上实名落盘，refs 原同名文件未被覆盖
    assert (refs / actual).read_bytes() == b"new"
    assert (refs / "示例客户材料.pptx").read_bytes() == b"old"
    # index.json 记实名
    idx = json.loads((root / "_knowledge" / "index.json").read_text(encoding="utf-8"))
    assets = idx["projects"]["_knowledge/clients/示例客户/refs"]["assets"]
    assert [a["file"] for a in assets] == [actual]
    # 登记表按原名销账清空，无 pending 残留
    assert reg.pending_entries() == []
    assert r["pending_review"] == []


def test_general_archive_collision_registers_actual_name(tmp_path, monkeypatch):
    """general 库同规则：撞名改名后 index/返回值记实名、登记表按原名销账。"""
    root = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(aa, "LOG_DIR", str(root / ".folio" / "logs"))
    (root / "_knowledge" / "refs" / "通用样张.pdf").write_bytes(b"old")
    (root / "inbox").mkdir()
    (root / "inbox" / "通用样张.pdf").write_bytes(b"new")
    aa.archive_note(["通用样张.pdf"], dest="general", note="样张")
    r = aa.auto_archive("示例客户")
    actual = r["archived"][0]
    assert actual != "通用样张.pdf" and actual.startswith("通用样张_")
    assert (root / "_knowledge" / "refs" / actual).read_bytes() == b"new"
    idx = json.loads((root / "_knowledge" / "index.json").read_text(encoding="utf-8"))
    assert [a["file"] for a in idx["projects"]["_knowledge/refs"]["assets"]] == [actual]
    assert reg.pending_entries() == []


def test_refuse_creating_new_client(tmp_path, monkeypatch):
    root = _env(tmp_path, monkeypatch)
    (root / "inbox").mkdir()
    (root / "inbox" / "示例评估.pptx").write_bytes(b"x")
    aa.archive_note(["示例评估.pptx"], dest="client", client_name="示例咖啡")
    r = aa.auto_archive("示例咖啡")
    assert r["archived"] == []
    assert any("拒绝自动创建" in s for s in r["pending_review"])
    assert not (root / "_knowledge" / "clients" / "示例咖啡").exists()  # 未建目录
    # 已登记文件不被 sweep 顺走，留在原地等人处理
    assert (root / "inbox" / "示例评估.pptx").exists()


def test_corrupt_registry_report_only(tmp_path, monkeypatch):
    root = _env(tmp_path, monkeypatch)
    reg_path = root / ".folio" / "logs" / "inbox_registry.json"
    reg_path.write_text("{broken", encoding="utf-8")
    (root / "inbox").mkdir()
    (root / "inbox" / "a.pdf").write_bytes(b"x")
    r = aa.auto_archive("示例客户")
    assert r["archived"] == []                    # 降级：只报告不移动
    assert r["swept"] == []                       # 连 sweep 也不动
    assert "登记表损坏" in r["reason"]
    assert (root / "inbox" / "a.pdf").exists()    # 原地保留


def test_archive_note_validation(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    r = aa.archive_note(["a.pdf"], dest="client", client_name="")
    assert r["errors"] and not r["added"]         # client 必须带客户名
    r = aa.archive_note(["a.pdf"], dest="bogus")
    assert r["errors"] and not r["added"]         # 非法 dest
    r = aa.archive_note(["b.pdf"], dest="general", client_name="X")
    assert r["added"] == ["b.pdf"]                # general 允许但忽略客户名
    assert reg.pending_entries()[0]["client"] == ""


# ---------- #55 forbidden 3≠5 对齐（B5 挂账 → B6 Wave1，2026-09-06） ----------
# 黑名单四处落点：_archive_auto.FORBIDDEN_IN_INBOX_EXTS（真源）、_inbox_scan.FORBIDDEN_EXTS、
# classify 配置（_classify_config.json + _default_config 兜底）、_session.py 检查1 内联元组。
# B5 根因 = 三处独立定义单边演化漂移；本组测试防再漂移 + 关闭 classify --client 污染面。
import json
import os
import re

import _classify as cls

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FORBIDDEN_5 = {".py", ".log", ".pyc", ".tmp", ".bak"}


def _session_inline_forbidden():
    """从 _session.py 源码提取『检查 1』内联黑名单（第三处独立定义）。"""
    session_path = os.path.join(_REPO_ROOT, "_session.py")
    with open(session_path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"inbox/ 残留[^\n]*\n\s*for ext in \(([^)]*)\)", src)
    assert m, "_session.py 检查1 内联 forbidden 元组定位失败（注释/结构被改？）"
    return set(re.findall(r'"(\.[A-Za-z0-9]+)"', m.group(1)))


def _json_config_forbidden():
    """读真实 _classify_config.json 的黑名单（只读，不落盘）。"""
    with open(os.path.join(_REPO_ROOT, "_classify_config.json"), encoding="utf-8") as f:
        return set(json.load(f)["rules_meta"]["forbidden_ininbox_ext"])


def test_forbidden_three_way_same_source():
    """三方同源断言：_archive_auto == config(实配+默认) == _session，B5 漂移根因防回归。"""
    aa_exts = set(aa.FORBIDDEN_IN_INBOX_EXTS)
    default_exts = set(cls._default_config()["rules_meta"]["forbidden_ininbox_ext"])
    json_exts = _json_config_forbidden()
    session_exts = _session_inline_forbidden()
    assert aa_exts == default_exts == json_exts == session_exts


def test_forbidden_value_contract_5():
    """值契约：恰为 5 项；.tmp/.bak 是本次补齐项，防单边回退到 3 项旧口径。"""
    assert set(aa.FORBIDDEN_IN_INBOX_EXTS) == _FORBIDDEN_5
    assert set(cls._default_config()["rules_meta"]["forbidden_ininbox_ext"]) == _FORBIDDEN_5
    assert _json_config_forbidden() == _FORBIDDEN_5
    assert _session_inline_forbidden() == _FORBIDDEN_5


def _cls_env(tmp_path, monkeypatch):
    """classify --client 隔离环境：aa / classify 全部落盘点指进 tmp。"""
    monkeypatch.setattr(aa, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(aa, "INDEX_PATH", str(tmp_path / "_knowledge" / "index.json"))
    monkeypatch.setattr(aa, "LOG_DIR", str(tmp_path / ".folio" / "logs"))
    monkeypatch.setattr(cls, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(cls, "LOG_DIR", str(tmp_path / ".folio" / "logs"))
    (tmp_path / "_knowledge" / "clients" / "示例客户" / "refs").mkdir(parents=True)
    (tmp_path / ".folio" / "logs").mkdir(parents=True)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "备份数据.bak").write_bytes(b"b")
    (inbox / "临时草稿.tmp").write_bytes(b"t")
    (inbox / "正式材料.pdf").write_bytes(b"p")   # 对照组：正常材料应照常归档
    return tmp_path, inbox


def test_classify_client_rejects_bak_tmp_default_config(tmp_path, monkeypatch):
    """行为断言（_default_config 兜底路径）：.bak/.tmp 不被 classify --client 搬进客户 refs。"""
    root, inbox = _cls_env(tmp_path, monkeypatch)
    moved = cls._classify_with_client("示例客户", str(inbox), cls._default_config())
    refs = root / "_knowledge" / "clients" / "示例客户" / "refs"
    assert (inbox / "备份数据.bak").exists()       # 原地保留（不丢文件）
    assert (inbox / "临时草稿.tmp").exists()
    assert not (refs / "备份数据.bak").exists()    # 污染面关闭
    assert not (refs / "临时草稿.tmp").exists()
    assert {os.path.basename(p[0]) for p in moved} == {"正式材料.pdf"}


def test_classify_client_rejects_bak_tmp_real_config(tmp_path, monkeypatch):
    """行为断言（真实 _classify_config.json 路径）：B5 实弹场景 D 关闭。"""
    root, inbox = _cls_env(tmp_path, monkeypatch)
    cls._classify_with_client("示例客户", str(inbox), cls.load_config())
    refs = root / "_knowledge" / "clients" / "示例客户" / "refs"
    assert (inbox / "备份数据.bak").exists()
    assert (inbox / "临时草稿.tmp").exists()
    assert not (refs / "备份数据.bak").exists()
    assert not (refs / "临时草稿.tmp").exists()
    assert (refs / "正式材料.pdf").exists()


def test_default_config_matches_json_config():
    """默认兜底与实配同源：config 缺失/损坏降级时不回到 3 项旧口径。"""
    assert set(cls._default_config()["rules_meta"]["forbidden_ininbox_ext"]) \
        == _json_config_forbidden()


def test_inbox_scan_sweep_same_blacklist():
    """第四处引用（_inbox_scan sweep，注释承诺与 _archive_auto 一致）不同步即红灯。"""
    import _inbox_scan as scan
    assert set(scan.FORBIDDEN_EXTS) == set(aa.FORBIDDEN_IN_INBOX_EXTS)


# ============================================================
# C-A7（0907 计划）：index.json 损坏备份重建 + 写锁 + 原子写
# ============================================================

def test_corrupt_index_backed_up_before_rebuild(tmp_path, monkeypatch):
    """损坏 index.json 不再静默清空：先备份留档，再从空结构重建登记。"""
    import glob
    import json as _json

    root = _env(tmp_path, monkeypatch)
    aa.INDEX_PATH = str(root / "_knowledge" / "index.json")
    (root / "inbox").mkdir()
    (root / "inbox" / "证据.pdf").write_bytes(b"x")
    # 写入损坏 index（模拟半截 JSON）
    with open(aa.INDEX_PATH, "w", encoding="utf-8") as f:
        f.write('{"projects": {"_knowledge/clients/示例客户/refs": {"name"')
    aa.archive_note(["证据.pdf"], dest="client", client_name="示例客户")
    r = aa.auto_archive("示例客户")
    assert r["archived"] == ["证据.pdf"]
    # 损坏件已备份留档（溯源可查），不是无痕丢失
    baks = glob.glob(aa.INDEX_PATH + ".corrupt-*.bak")
    assert len(baks) == 1
    assert '半截' in open(baks[0], encoding="utf-8").read() or '"name"' in open(baks[0], encoding="utf-8").read()
    # 索引重建成功且新登记写入
    idx = _json.load(open(aa.INDEX_PATH, encoding="utf-8"))
    files = [a["file"] for a in idx["projects"]["_knowledge/clients/示例客户/refs"]["assets"]]
    assert files == ["证据.pdf"]


def test_save_index_atomic_no_tmp_leftover(tmp_path, monkeypatch):
    """_save_index 走 tmp→os.replace：完成后无 .tmp 残片，产物可解析。"""
    import json as _json

    root = _env(tmp_path, monkeypatch)
    aa.INDEX_PATH = str(root / "_knowledge" / "index.json")
    aa._save_index({"projects": {"k": {"name": "n", "assets": []}}, "recents": []})
    assert not (root / "_knowledge" / "index.json.tmp").exists()
    idx = _json.load(open(aa.INDEX_PATH, encoding="utf-8"))
    assert "k" in idx["projects"]
    # 锁随写随释放，不留锁文件
    assert not (root / "_knowledge" / ".index_save_lock").exists()


def test_save_index_lock_timeout_fails_loud(tmp_path, monkeypatch):
    """锁等待超时：大声失败（TimeoutError），绝不绕锁写入；_update_index 记日志降级。"""
    root = _env(tmp_path, monkeypatch)
    aa.INDEX_PATH = str(root / "_knowledge" / "index.json")

    import _save_lock
    real = _save_lock.acquire_save_lock

    def fake_acquire(client_dir, **kw):
        fd = real(client_dir, **kw)
        if fd is not None:  # 模拟他人持锁：立即释放自己的锁并拒绝
            _save_lock.release_save_lock(client_dir, fd, lock_name=kw.get("lock_name", _save_lock.LOCK_FILENAME))
        return None

    monkeypatch.setattr("_save_lock.acquire_save_lock", fake_acquire)
    try:
        aa._save_index({"projects": {}, "recents": []})
        raised = False
    except TimeoutError:
        raised = True
    assert raised, "锁超时应大声失败"
    assert not (root / "_knowledge" / "index.json").exists(), "不得绕锁写入"

    # _update_index 消费侧降级：不抛、跳过登记（记日志）
    aa._update_index("_knowledge/clients/示例客户/refs", "示例客户", "x.pdf")
    assert not (root / "_knowledge" / "index.json").exists()


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/真实数据，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
