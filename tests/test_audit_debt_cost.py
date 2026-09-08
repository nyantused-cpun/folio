# -*- coding: utf-8 -*-
"""audit debt/drift/cost 三只读模式（Q3，_scratch forensic 脚本收编）回归测试。

封闭化先例（test_audit_knowledge / test_cli_audit_ratchet）：全部用 tmp_path
构造假客户目录与假 logs 目录，不依赖仓库真实卡片与真实 .folio/logs。
三项检查均为观察级（恒返回 True），断言落在输出文本上。
"""
import json
import os
import sys
from datetime import datetime

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


def _mk_client(tmp_path, name="甲客户", files=None):
    """在 tmp clients/ 下造假客户目录；files 为 {文件名: 内容（str 或 dict）}。"""
    base = tmp_path / "clients" / name
    base.mkdir(parents=True, exist_ok=True)
    for fname, content in (files or {}).items():
        p = base / fname
        if isinstance(content, dict):
            p.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        else:
            p.write_text(content, encoding="utf-8")
    return base


def _oi(entries, **meta):
    """outputs_index.json 内容（dict 形态，outputs=entries）。"""
    d = {"client": "甲客户"}
    d.update(meta)
    d["outputs"] = entries
    return d


# ---------------------------------------------------------------------------
# debt：outputs_index 悬空 / missing 标记 / 重复决策 / 冲突组 / 残留
# ---------------------------------------------------------------------------
class TestDebtMode:
    def test_dangling_unmarked_found(self, tmp_path, capsys):
        """悬空且无 missing 标记 = 债，必须点名。"""
        _mk_client(tmp_path, files={"outputs_index.json": _oi(
            ["output/审计测试客户/不存在_方案_v9.html"])})
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "悬空未标" in out and "不存在_方案_v9.html" in out

    def test_marked_missing_not_dangling(self, tmp_path, capsys):
        """带 missing 标记的悬空条目按设计保留：不报悬空，只作已标记信息。"""
        _mk_client(tmp_path, files={"outputs_index.json": _oi([
            {"path": "output/审计测试客户/丢失_v1.html", "missing": True}])})
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "悬空未标" not in out
        assert "已标记缺失" in out

    def test_marked_but_on_disk_hint(self, tmp_path, capsys):
        """在盘却带 missing 标记 = 自愈未跑，要提示。"""
        _mk_client(tmp_path, files={"outputs_index.json": _oi([
            {"path": "AGENTS.md", "missing": True}])})  # AGENTS.md 在仓库根必在盘
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "自愈未跑" in out

    def test_same_day_same_topic_dup_found(self, tmp_path, capsys):
        """同日同题重复块必须发现。"""
        decisions = ("# 决策\n\n## [2026-09-07] 交付边界口径\n\npersistence: task\n内容一\n\n"
                     "## [2026-09-07] 交付边界口径\n\npersistence: task\n内容二\n")
        _mk_client(tmp_path, files={"decisions.md": decisions})
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "同日同题重复" in out and "交付边界口径" in out

    def test_conflict_pending_group_listed_not_dup(self, tmp_path, capsys):
        """conflict: pending 同题组不报重复，只单列为冲突队列待裁决。"""
        decisions = ("# 决策\n\n## [2026-09-07] 交付边界口径\n\npersistence: task\n内容一\n\n"
                     "## [2026-09-07] 交付边界口径\n\npersistence: task\n内容二\n"
                     "<!-- conflict: pending -->\n")
        _mk_client(tmp_path, files={"decisions.md": decisions})
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "同日同题重复" not in out
        assert "冲突队列" in out and "交付边界口径" in out

    def test_session_notes_leftover_found(self, tmp_path, capsys):
        """session_notes 残留必须发现。"""
        _mk_client(tmp_path, files={"session_notes_2026-09-01.md": "残留笔记\n"})
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "残留" in out and "session_notes_2026-09-01.md" in out

    def test_snapshot_over_keep_found(self, tmp_path, capsys):
        """snapshot 超当前设计保留数（3，_context._snapshot_context 同步）即残留。"""
        files = {"context.md": "# 卡片\n"}
        for i in range(4):
            files[f"context.md.snapshot.2026090700000{i}"] = "# 旧卡片\n"
        _mk_client(tmp_path, files=files)
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "snapshot×4" in out and "超3" in out

    def test_internal_dirs_excluded(self, tmp_path, capsys):
        """#48 收口：_ 前缀内部目录（_internal/_template）不得当客户扫。"""
        from _paths import list_client_dirs
        root = tmp_path / "clients"
        for name in ("甲客户", "_internal", "_template", ".hidden"):
            (root / name).mkdir(parents=True)
        _mk_client(tmp_path, name="_template", files={
            "outputs_index.json": _oi(["output/模板客户/不存在_v9.html"])})
        assert list_client_dirs(clients_dir=str(root)) == ["甲客户"]
        from _cli_audit import _audit_debt
        assert _audit_debt(clients_dir=str(root)) is True
        out = capsys.readouterr().out
        assert "_template" not in out and "悬空未标" not in out


# ---------------------------------------------------------------------------
# drift：覆盖矩阵（aliases.md 退役）/ meta_version / 结构代际
# ---------------------------------------------------------------------------
class TestDriftMode:
    def test_retired_aliases_md_never_in_output(self, tmp_path, capsys):
        """硬要求：aliases.md 机制已退役，输出绝不出现该字样（即使盘上还有文件）。"""
        _mk_client(tmp_path, files={
            "context.md": "<!-- meta_version: 3 -->\n# 客户卡片\n\n## 基本信息\n待澄清：无\n",
            "aliases.yml": "extends: _base\n",
            "aliases.md": "# 别名\n别名/全称：说明\n",
            "preferences.md": "暂无偏好记录",
        })
        from _cli_audit import _audit_drift
        assert _audit_drift(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "aliases.md" not in out
        assert "别名.yml" in out and "偏好" in out  # 在役文件仍在矩阵

    def test_meta_version_missing_warned(self, tmp_path, capsys):
        _mk_client(tmp_path, files={"context.md": "# 客户卡片\n\n## 基本信息\n"})
        from _cli_audit import _audit_drift
        assert _audit_drift(clients_dir=str(tmp_path / "clients")) is True
        assert "缺meta_version" in capsys.readouterr().out

    def test_meta_version_present_clean(self, tmp_path, capsys):
        _mk_client(tmp_path, files={
            "context.md": "<!-- meta_version: 3 -->\n# 客户卡片\n\nopen_questions: 无\n"})
        from _cli_audit import _audit_drift
        assert _audit_drift(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "缺meta_version" not in out

    def test_legacy_decisions_without_persistence_warned(self, tmp_path, capsys):
        """drift_audit.py 结构代际项：H2 有而 persistence 无 = 老格式。"""
        _mk_client(tmp_path, files={
            "decisions.md": "## 决策 1：老条目\n内容\n\n## 决策 2：老条目二\n内容\n"})
        from _cli_audit import _audit_drift
        assert _audit_drift(clients_dir=str(tmp_path / "clients")) is True
        assert "decisions老格式" in capsys.readouterr().out

    def test_missing_files_dash_in_matrix(self, tmp_path, capsys):
        """缺文件在矩阵中显示 -，不抛异常。"""
        _mk_client(tmp_path, files={})  # 空客户目录
        from _cli_audit import _audit_drift
        assert _audit_drift(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "甲客户" in out and "-" in out


# ---------------------------------------------------------------------------
# cost：telemetry 体量/轮转、本月 LLM 用量、probe 缓存（缺失一律降级）
# ---------------------------------------------------------------------------
class TestCostMode:
    def test_missing_sources_no_raise(self, tmp_path, capsys):
        """logs 目录为空/数据源全缺：不抛异常，标注「数据源不存在」，恒 True。"""
        logs = tmp_path / "logs"
        logs.mkdir()
        from _cli_audit import _audit_cost
        assert _audit_cost(logs_dir=str(logs)) is True
        out = capsys.readouterr().out
        assert "数据源不存在" in out
        assert "✗" not in out  # 缺失是降级标注，不是失败

    def test_telemetry_oversize_warns(self, tmp_path, monkeypatch, capsys):
        """>10MB 未轮转 = 告警（阈值经 monkeypatch 归零，万字节即超）。"""
        import _cli_audit
        monkeypatch.setattr(_cli_audit, "_TELEMETRY_WARN_MB", 0)
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "telemetry_dsh.jsonl").write_text('{"at":"x"}\n' * 1000, encoding="utf-8")
        assert _cli_audit._audit_cost(logs_dir=str(logs)) is True
        out = capsys.readouterr().out
        assert "⚠" in out and "telemetry_dsh.jsonl" in out

    def test_llm_usage_month_aggregated(self, tmp_path, capsys):
        """只聚合本月记录，历史月份不计入。"""
        month = datetime.now().strftime("%Y-%m")
        rows = [
            {"time": f"{month}-01 10:00:00", "provider": "zhipu", "total_tokens": 120},
            {"time": f"{month}-02 11:00:00", "provider": "zhipu", "total_tokens": 30},
            {"time": "2020-01-01 00:00:00", "provider": "zhipu", "total_tokens": 999},
        ]
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "llm_usage.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        from _cli_audit import _audit_cost
        assert _audit_cost(logs_dir=str(logs)) is True
        out = capsys.readouterr().out
        assert "2 次 / 150 tokens" in out
        assert "999" not in out  # 历史月份不并入

    def test_probe_cache_present_counts_entries(self, tmp_path, capsys):
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "model_capabilities.json").write_text(
            json.dumps({"model-a": {}, "model-b": {}}), encoding="utf-8")
        from _cli_audit import _audit_cost
        assert _audit_cost(logs_dir=str(logs)) is True
        assert "probe 缓存 model_capabilities.json 存在（2 条）" in capsys.readouterr().out


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
