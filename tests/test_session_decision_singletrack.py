# -*- coding: utf-8 -*-
"""P0 决策单轨化集成测试（记忆机制收敛）。

覆盖：
- save --decisions -> decisions.md 新增 task 条目（persistence=task, scope=task, task_id=<date>#<session>）
- context.md 决策段只留一行引用；task_history 只留 ≤200 字摘要
- 同一 dsh_session 连续 save 不重复写 decisions.md（幂等）
- L4 加载能读到最近 task 决策（load_context_by_level）
- 统一决策解析器三格式回归：
    ### D-NNN（蓝海） / ## 决策 N / ## [YYYY-MM-DD] / ## YYYY-MM-DD：标题（无方括号）

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
"""

import json
from datetime import datetime

import _context
import _aliases
import _graph
import _session
import _theme_guard
import _embed_index


CLIENT = "单轨测试客户S1"
SID = "sess-single-001"
TODAY = datetime.now().strftime("%Y-%m-%d")  # P1-4：动态日期，避免测试时间炸弹


def _setup(tmp_path, monkeypatch):
    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))

    counters = {"embedding": [], "graph": []}

    def _mk(name):
        def _fake(*a, **kw):
            counters[name].append(1)
            return {}
        return _fake

    monkeypatch.setattr(_embed_index, "build_embedding_index", _mk("embedding"))
    monkeypatch.setattr(_session, "build_client_graph", _mk("graph"))
    monkeypatch.setattr(_session, "_sync_bm25_if_stale", _mk("bm25"))
    monkeypatch.setattr(_session, "_extract_case_cards", _mk("cases"))
    monkeypatch.setattr(_session, "update_outputs_index", _mk("outputs"))
    return clients, counters


def _decisions_text(clients):
    p = clients / CLIENT / "decisions.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _context_text(clients):
    return (clients / CLIENT / "context.md").read_text(encoding="utf-8")


def _task_entries(tmp_path):
    p = tmp_path / "task_history.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


# ============================================================
# P0 单轨：save --decisions 写 decisions.md
# ============================================================
class TestSaveDecisionSingleTrack:
    def test_save_writes_task_entry_and_reference(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        assert _session.save_session(
            CLIENT, input_desc="输入A", decisions="报价口径定为 100 万",
            dsh_session=SID) is True

        dec = _decisions_text(clients)
        assert "## [" + TODAY + "] 会话决策 " + TODAY + " #" + SID in dec
        assert "报价口径定为 100 万" in dec
        assert "**persistence: task**" in dec
        assert "**scope: task**" in dec
        assert "**task_id: " + TODAY + "#" + SID in dec
        assert "**来源**: user:会话决策" in dec

        ctx = _context_text(clients)
        # context.md 决策段只留一行引用（全文真源在 decisions.md）
        assert "（见 decisions.md：会话决策" in ctx
        assert "报价口径定为 100 万" not in ctx

    def test_task_history_keeps_summary(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        long_decision = "决策内容" * 60  # 远超 200 字
        _session.save_session(CLIENT, decisions=long_decision, dsh_session=SID)
        entries = _task_entries(tmp_path)
        assert len(entries) == 1
        assert len(entries[0]["decisions"]) <= 200

    def test_same_dsh_session_twice_no_duplicate(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, decisions="决策A", dsh_session=SID)
        _session.save_session(CLIENT, decisions="决策A", dsh_session=SID)
        dec = _decisions_text(clients)
        # 同 task_id 不重复 append
        assert dec.count("## [" + TODAY + "] 会话决策 " + TODAY + " #" + SID) == 1

    def test_non_dsh_session_same_day_upserts_single_entry(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, decisions="决策A")
        _session.save_session(CLIENT, decisions="决策B")
        dec = _decisions_text(clients)
        # S8：同一天重复 save 视为同一会话，decisions.md 只落一块（后写赢）
        assert dec.count("## [" + TODAY + "] 会话决策") == 1
        assert "决策B" in dec and "决策A" not in dec

    def test_no_decisions_no_reference_no_entry(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="仅输入")
        assert _decisions_text(clients) == ""  # decisions.md 未创建
        ctx = _context_text(clients)
        assert "（见 decisions.md" not in ctx


# ============================================================
# L4 加载最近 task 决策
# ============================================================
class TestL4RecentTaskDecisions:
    def test_load_context_l4_reads_recent_task_decisions(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, decisions="铁律A 报价口径", dsh_session=SID)
        loaded = _context.load_context_by_level(CLIENT, "L4")
        recent = loaded.get("recent_task_decisions", [])
        assert recent, "L4 应能读到最近 task 决策"
        assert any("报价口径" in r["decision"] for r in recent)
        assert any(r["task_id"] == f"{TODAY}#{SID}" for r in recent)

    def test_load_context_l4_limits_to_3(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        for i in range(5):
            _session.save_session(CLIENT, decisions=f"决策{i}", dsh_session=f"sess-{i}")
        loaded = _context.load_context_by_level(CLIENT, "L4")
        recent = loaded.get("recent_task_decisions", [])
        assert len(recent) <= 3


# ============================================================
# 统一决策解析器：三格式回归（load_active_themes / _extract_decision_nodes）
# ============================================================
class TestThreeFormatParser:
    def _write_decisions(self, clients, content):
        d = clients / CLIENT
        d.mkdir(parents=True, exist_ok=True)
        (d / "decisions.md").write_text(content, encoding="utf-8")

    def test_d_nnn_format_parsed(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        self._write_decisions(clients, (
            "# 测试客户 决策记录\n"
            "### D-001 · 以正式招标文件为铁律\n"
            "- **日期**：2026-07-08\n"
            "- **决策**: 以招标文件为准\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
        ))
        themes = _theme_guard.load_active_themes(CLIENT, only_permanent=True)
        assert len(themes) == 1
        assert themes[0]["theme"] == "以正式招标文件为铁律"
        assert themes[0]["persistence"] == "permanent"

        nodes = _graph._extract_decision_nodes((clients / CLIENT / "decisions.md").read_text(encoding="utf-8"))
        assert len(nodes) == 1
        assert nodes[0]["title"] == "以正式招标文件为铁律"

    def test_decision_number_format_parsed(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        self._write_decisions(clients, (
            "# 测试客户 决策记录\n"
            "## 决策 1：系统一体化切换\n"
            "- **日期**: 2026-06-24\n"
            "- **决策**: 不分阶段切换\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
        ))
        themes = _theme_guard.load_active_themes(CLIENT, only_permanent=True)
        assert len(themes) == 1
        assert themes[0]["theme"] == "系统一体化切换"

        nodes = _graph._extract_decision_nodes((clients / CLIENT / "decisions.md").read_text(encoding="utf-8"))
        assert len(nodes) == 1
        assert nodes[0]["metadata"]["decision_num"] == 1

    def test_bracket_date_format_parsed(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        self._write_decisions(clients, (
            "# 测试客户 决策记录\n"
            "## [2026-07-17] 入库决策\n"
            "- **决策**: 客户正式名以蓝海为准\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
        ))
        themes = _theme_guard.load_active_themes(CLIENT, only_permanent=True)
        assert len(themes) == 1
        assert themes[0]["theme"] == "入库决策"
        assert themes[0]["source_date"] == "2026-07-17"

    def test_no_bracket_date_format_parsed(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        self._write_decisions(clients, (
            "# 测试客户 决策记录\n"
            "## 2026-07-17：入库决策\n"
            "- **决策**: 客户正式名以蓝海为准\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
        ))
        themes = _theme_guard.load_active_themes(CLIENT, only_permanent=True)
        assert len(themes) == 1
        assert themes[0]["theme"] == "入库决策"
        assert themes[0]["source_date"] == "2026-07-17"

    def test_deprecated_block_skipped(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        self._write_decisions(clients, (
            "# 测试客户 决策记录\n"
            "### D-001 · 旧铁律\n"
            "- **决策**: 旧口径\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n"
            "<!-- conflict: pending -->\n"
        ))
        themes = _theme_guard.load_active_themes(CLIENT, only_permanent=True)
        assert themes == []



# ============================================================
# P1-14：决策文本含反斜杠转义序列时 upsert 往返无损
# ============================================================
class TestSessionDecisionBackslashRoundtrip:
    """决策文本含 \1 / \n / \t 时，同 task_id upsert 不得被 re.sub
    当反向引用/转义解释（曾用字符串替换形式，炸 re.error 或静默改写内容）。"""

    def test_backslash_decision_upsert_lossless(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _theme_guard.append_session_decision(
            CLIENT, "主题A", "初版决策", session_ref="s9")
        tricky = "含转义 \1 与 \n 以及 \t 和 \g<0> 的决策"
        _theme_guard.append_session_decision(
            CLIENT, "主题A", tricky, session_ref="s9")
        text = _decisions_text(clients)
        assert tricky in text                       # 往返无损
        assert text.count("- **决策**: 含转义") == 1  # 同 task_id 单块不膨胀
        assert "初版决策" not in text               # 后写赢：旧内容被更新
