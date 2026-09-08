# -*- coding: utf-8 -*-
"""S10-3a 育种登记闭环回归 + 3e 观察项 TTL 机检。

覆盖（验收单）：注册幂等 / 确认门槛（同客户 2 次 ≠ 2 客户）/ evaluate 双条件 /
promote 状态迁移（含 breeding 中间态与 archived 拒绝）/ 尸体清理 dry-run 与
实归档 / 季度审计 0 转化 flag / 锁写顺序双写不丢数据 / scan_observation_ttl
tmp 注入 / CLI 面（breed 经 _cli.main）exit code 0/1。

tmp 注入口径：registry 路径参数化（真目录零残留）；CLI 面测试 monkeypatch
_breeding.SCRIPT_DIR 到 tmp_path（registry_path 运行时读模块全局）。
"""

import datetime
import json
import os
import sys

import pytest

import _breeding


def _days_ago(n):
    return datetime.date.today() - datetime.timedelta(days=n)


@pytest.fixture()
def reg(tmp_path):
    """注入 tmp registry 路径（_knowledge/breeding 真目录零写入）。"""
    return str(tmp_path / "registry.json")


def _write(registry, entries):
    os.makedirs(os.path.dirname(registry), exist_ok=True)
    with open(registry, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _read(registry):
    with open(registry, "r", encoding="utf-8") as f:
        return json.load(f)


def _seed_mature(registry, name="三维架构图", **kw):
    """登记满 14 天 + 2 客户确认的达标候选。"""
    entry, created = _breeding.register_candidate(
        name, "output/示例客户/方案_v1.html", registry=registry, today=_days_ago(20), **kw)
    assert created
    for c in ("客户甲", "客户乙"):
        _breeding.add_confirmation(entry["id"], c, registry=registry, today=_days_ago(5))
    return entry


class TestRegister:
    def test_register_and_idempotent(self, reg):
        entry, created = _breeding.register_candidate("三维架构图", "output/甲/方案_v1.html", registry=reg)
        assert created and entry["status"] == "candidate"
        assert entry["registered_at"] == datetime.date.today().isoformat()
        again, created2 = _breeding.register_candidate("三维架构图", "output/乙/x.html", registry=reg)
        assert not created2
        assert again["id"] == entry["id"]  # 幂等返回已存在，且不覆盖登记信息
        assert again["source"] == "output/甲/方案_v1.html"
        assert len(_read(reg)) == 1

    def test_register_slug_and_id_dedup(self, reg):
        e1, _ = _breeding.register_candidate("价值链图", "s1", registry=reg)
        assert e1["id"] == "价值链图"
        e2, created = _breeding.register_candidate("价值链图！", "s2", registry=reg)
        # 不同名允许共存；slug 撞车自动加后缀（幂等按 name 判，不误吞新候选）
        assert created and e2["id"] == "价值链图-2"
        assert len(_read(reg)) == 2

    def test_register_empty_name_rejected(self, reg):
        entry, created = _breeding.register_candidate("  ", "s", registry=reg)
        assert entry is None and not created
        assert not os.path.exists(reg)


class TestConfirmationGate:
    def test_same_client_twice_is_not_two_clients(self, reg):
        entry, _ = _breeding.register_candidate("对比页", "s", registry=reg, today=_days_ago(20))
        _breeding.add_confirmation(entry["id"], "客户甲", registry=reg)
        _breeding.add_confirmation(entry["id"], "客户甲", registry=reg)  # 同客户重复
        assert len(_read(reg)[0]["confirmations"]) == 1  # 不叠加
        rep = _breeding.evaluate(entry["id"], registry=reg)
        assert rep["distinct_clients"] == 1
        assert rep["suggest"] == "wait"

    def test_two_distinct_clients_count(self, reg):
        entry, _ = _breeding.register_candidate("对比页", "s", registry=reg, today=_days_ago(20))
        for c in ("客户甲", "客户乙", "客户甲"):
            _breeding.add_confirmation(entry["id"], c, registry=reg)
        assert _breeding.evaluate(entry["id"], registry=reg)["distinct_clients"] == 2

    def test_confirm_unknown_id(self, reg):
        assert _breeding.add_confirmation("不存在", "甲", registry=reg) == (None, False)


class TestEvaluate:
    def test_fresh_registration_fails_stable_window(self, reg):
        entry, _ = _breeding.register_candidate("热力图", "s", registry=reg)  # 今天登记
        for c in ("甲", "乙"):
            _breeding.add_confirmation(entry["id"], c, registry=reg)
        rep = _breeding.evaluate(entry["id"], registry=reg)
        assert rep["suggest"] == "wait"
        assert rep["days_stable"] == 0
        assert any("稳定期" in m for m in rep["missing"])

    def test_mature_two_clients_promote_suggested(self, reg):
        entry = _seed_mature(reg)
        rep = _breeding.evaluate(entry["id"], registry=reg)
        assert rep["suggest"] == "promote"
        assert rep["distinct_clients"] == 2 and rep["days_stable"] >= 14
        assert rep["missing"] == []

    def test_evaluate_unknown_id_none(self, reg):
        assert _breeding.evaluate("不存在", registry=reg) is None


class TestPromote:
    def test_two_phase_transition(self, reg):
        entry = _seed_mature(reg)
        e, ok, reason = _breeding.promote(entry["id"], refs=[], registry=reg)
        assert ok and e["status"] == "breeding"  # 无 refs → 进入提炼评审
        e, ok, _ = _breeding.promote(entry["id"], refs=["schema:diagram 三维件", " gold:relationship__3d "], registry=reg)
        assert ok and e["status"] == "promoted"
        assert e["promoted_refs"] == ["schema:diagram 三维件", "gold:relationship__3d"]
        assert e["promoted_at"] == datetime.date.today().isoformat()

    def test_promoted_is_terminal(self, reg):
        entry = _seed_mature(reg)
        _breeding.promote(entry["id"], ["gold:x"], registry=reg)
        _, ok, reason = _breeding.promote(entry["id"], ["gold:y"], registry=reg)
        assert not ok and "promoted" in reason

    def test_archived_refuses_promote(self, reg):
        _write(reg, [{"id": "dead", "name": "死条目", "source": "s", "registered_at": "2026-01-01",
                      "confirmations": [], "status": "archived", "promoted_refs": [], "notes": ""}])
        _, ok, reason = _breeding.promote("dead", ["gold:x"], registry=reg)
        assert not ok and "归档" in reason


class TestArchiveStale:
    def test_dry_run_does_not_mutate(self, reg):
        _seed_mature(reg, name="旧候选")  # 登记 20 天，不足 3 月
        _write(reg, _read(reg) + [{
            "id": "old-one", "name": "陈旧候选", "source": "s", "registered_at": "2026-01-01",
            "confirmations": [], "status": "candidate", "promoted_refs": [], "notes": ""}])
        stale = _breeding.archive_stale(months=3, registry=reg)
        assert [s["id"] for s in stale] == ["old-one"]
        assert _read(reg)[0]["status"] == "candidate"  # dry-run 不落盘
        assert all(e["status"] != "archived" for e in _read(reg))

    def test_apply_archives_and_spares_promoted(self, reg):
        _write(reg, [
            {"id": "old-c", "name": "旧c", "source": "s", "registered_at": "2026-01-01",
             "confirmations": [], "status": "candidate", "promoted_refs": [], "notes": ""},
            {"id": "old-p", "name": "旧p", "source": "s", "registered_at": "2026-01-01",
             "promoted_at": "2026-01-05", "confirmations": [], "status": "promoted",
             "promoted_refs": ["gold:x"], "notes": ""},
        ])
        stale = _breeding.archive_stale(months=3, registry=reg, apply=True)
        assert [s["id"] for s in stale] == ["old-c"]  # promoted 不是尸体
        by_id = {e["id"]: e for e in _read(reg)}
        assert by_id["old-c"]["status"] == "archived"
        assert "archived_at" in by_id["old-c"]
        assert by_id["old-p"]["status"] == "promoted"

    def test_confirmation_refreshes_activity(self, reg):
        _breeding.register_candidate("近期活跃", "s", registry=reg, today=_days_ago(100))
        entry = _read(reg)[0]
        entry["confirmations"] = [{"client": "甲", "date": _days_ago(10).isoformat()}]
        _write(reg, [entry])
        assert _breeding.archive_stale(months=3, registry=reg) == []  # 确认刷新末次活动


class TestQuarterlyAudit:
    def test_zero_conversion_flags_review(self, reg):
        _seed_mature(reg, name="候选A")
        _seed_mature(reg, name="候选B")
        rep = _breeding.quarterly_audit(registry=reg)
        assert rep["registered"] == 2 and rep["promoted"] == 0
        assert rep["zero_convert"] and rep["review_suggested"]

    def test_conversion_clears_flag(self, reg):
        _seed_mature(reg, name="候选A")
        _breeding.promote("候选A", ["gold:x"], registry=reg)  # promoted_at=今天
        rep = _breeding.quarterly_audit(registry=reg)
        assert rep["promoted"] == 1 and not rep["review_suggested"]

    def test_empty_registry_no_flag(self, reg):
        rep = _breeding.quarterly_audit(registry=reg)
        assert rep["registered"] == 0 and not rep["review_suggested"]


class TestLockSequentialWrites:
    def test_sequential_double_write_keeps_both(self, reg):
        """锁写并发（简化口径）：顺序双写经同一锁通道，先写不丢、后写可见。"""
        _breeding.register_candidate("模式一", "s1", registry=reg)
        _breeding.register_candidate("模式二", "s2", registry=reg)
        ids = [e["id"] for e in _read(reg)]
        assert len(ids) == 2
        _breeding.add_confirmation(ids[0], "甲", registry=reg)
        _breeding.add_confirmation(ids[1], "乙", registry=reg)
        data = _read(reg)
        assert {len(e["confirmations"]) for e in data} == {1}  # 双写确认互不覆盖
        assert not os.path.exists(os.path.join(os.path.dirname(reg), _breeding.LOCK_NAME))


class TestScanObservationTtl:
    def test_missing_vs_annotated(self, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text(
            "# 观察级告警：超限提示（无标注）\n"
            "# 观察级告警：超限提示 TTL(2026-12-31): 复审转正\n"
            "# 观察模式降级留痕 升级条件: 误报归零跑满三批\n", encoding="utf-8")
        f2 = tmp_path / "b.md"
        f2.write_text("普通行，不含观察词\n- **机检状态**：⚠️ 观察中（review 判语义）\n", encoding="utf-8")
        missing = _breeding.scan_observation_ttl(targets=[str(f1), str(f2)])
        rel1 = os.path.relpath(str(f1), _breeding.SCRIPT_DIR)
        rel2 = os.path.relpath(str(f2), _breeding.SCRIPT_DIR)
        hits = {(rel, ln) for rel, ln, _ in missing}
        assert (rel1, 1) in hits
        assert (rel1, 2) not in hits and (rel1, 3) not in hits  # 带标注的行不列
        assert (rel2, 2) in hits

    def test_unreadable_file_skipped(self, tmp_path):
        missing = _breeding.scan_observation_ttl(targets=[str(tmp_path / "不存在.py")])
        assert missing == []


class TestCliFace:
    """CLI 面：经 _cli.main 全链（parser/dispatch/exit code），SCRIPT_DIR 注入 tmp。"""

    @pytest.fixture()
    def cli_tmp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_breeding, "SCRIPT_DIR", str(tmp_path))
        return tmp_path

    def _main(self, argv, monkeypatch):
        """仿 test_cli_exitcodes：SystemExit 取退出码；正常返回（成功路径）按 0。"""
        import _cli
        monkeypatch.setattr(sys, "argv", argv)
        saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
        try:
            try:
                _cli.main()
                return 0
            except SystemExit as e:
                return e.code
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved

    def test_register_without_source_exits_1(self, cli_tmp, monkeypatch, capsys):
        assert self._main(["_cli.py", "breed", "register", "架构图"], monkeypatch) == 1

    def test_confirm_unknown_id_exits_1(self, cli_tmp, monkeypatch):
        assert self._main(["_cli.py", "breed", "confirm", "不存在", "--client", "甲"], monkeypatch) == 1

    def test_full_chain_exit_0(self, cli_tmp, monkeypatch, capsys):
        base = ["_cli.py", "breed"]
        assert self._main(base + ["register", "金字塔图", "--source", "output/甲/方案_v1.html"], monkeypatch) == 0
        assert self._main(base + ["register", "金字塔图", "--source", "output/乙/x.html"], monkeypatch) == 0  # 幂等
        assert self._main(base + ["confirm", "金字塔图", "--client", "客户甲"], monkeypatch) == 0
        assert self._main(base + ["confirm", "金字塔图", "--client", "客户甲"], monkeypatch) == 0  # 重复确认不报错
        out = capsys.readouterr().out
        # 结构稳定期未满 → evaluate 建议等待（不阻断，仍 exit 0）
        assert self._main(base + ["evaluate", "金字塔图"], monkeypatch) == 0
        assert self._main(base + ["promote", "金字塔图", "--refs", "gold:pyramid"], monkeypatch) == 0
        assert self._main(base + ["list"], monkeypatch) == 0
        assert self._main(base + ["audit"], monkeypatch) == 0
        assert self._main(base + ["ttl"], monkeypatch) == 0
        out = capsys.readouterr().out
        assert "promoted" in out and "refs: gold:pyramid" in out
        reg_path = os.path.join(str(cli_tmp), "_knowledge", "breeding", "registry.json")
        data = json.load(open(reg_path, encoding="utf-8"))
        assert data[0]["status"] == "promoted"
