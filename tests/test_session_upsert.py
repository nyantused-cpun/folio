# -*- coding: utf-8 -*-
"""save_session 会话级 upsert（P1 健壮性 · T8a）+ 文件锁集成（T7）。

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
重型副作用（embedding/graph/bm25/case_cards/outputs_index）全部 monkeypatch 计数。
"""

import glob
import json

import _session
import _context
import _aliases
import _embed_index
import _save_lock


# ============================================================
# 测试基座：tmp 客户目录 + 重定向写入目标 + 计数桩
# ============================================================
def _setup(tmp_path, monkeypatch):
    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))

    counters = {"embedding": [], "bm25": [], "graph": [], "cases": [], "outputs": []}

    def _mk(name):
        def _fake(*a, **kw):
            counters[name].append(1)
            return {}
        return _fake

    monkeypatch.setattr(_embed_index, "build_embedding_index", _mk("embedding"))
    monkeypatch.setattr(_session, "_sync_bm25_if_stale", _mk("bm25"))
    monkeypatch.setattr(_session, "build_client_graph", _mk("graph"))
    monkeypatch.setattr(_session, "_extract_case_cards", _mk("cases"))
    monkeypatch.setattr(_session, "update_outputs_index", _mk("outputs"))
    return clients, counters


def _context_text(clients, name):
    return (clients / name / "context.md").read_text(encoding="utf-8")


def _task_entries(tmp_path):
    p = tmp_path / "task_history.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _count_marker_blocks(text, sid):
    return text.count(f"<!-- dsh:session:{sid} -->")


CLIENT = "测试客户U1"
SID = "sess-dsh-001"


# ============================================================
# 同 ID upsert：context.md / task_history 唯一
# ============================================================
class TestSameIdUpsert:
    def test_same_id_two_saves_single_context_block(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        assert _session.save_session(
            CLIENT, input_desc="输入A", decisions="决策A", pending="待办A",
            dsh_session=SID) is True
        assert _session.save_session(
            CLIENT, input_desc="输入B", decisions="决策B", pending="待办B",
            dsh_session=SID) is True

        text = _context_text(clients, CLIENT)
        # 同 dsh_session 连续 save×2 -> context.md 该会话仅一块
        assert _count_marker_blocks(text, SID) == 1
        # 整块替换：会话号不变（仍是第 1 次），内容为最新一次
        assert "第 1 次会话" in text
        assert "第 2 次会话" not in text
        assert "输入B" in text and "输入A" not in text
        # 标记位于标题行下一行
        assert "<!-- dsh:session:" + SID + " -->" in text

    def test_same_id_two_saves_single_task_entry(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              dsh_session=SID)
        _session.save_session(CLIENT, input_desc="输入B", decisions="决策B",
                              dsh_session=SID)

        entries = _task_entries(tmp_path)
        # task_history.json 仅一条
        assert len(entries) == 1
        e = entries[0]
        assert e["dsh_session"] == SID
        assert e["project"] == f"client:{CLIENT}"
        # 原地更新：内容为最新，date/session 序号保持
        assert e["decisions"] == "决策B"
        assert e["session"] == 1
        assert "date" in e  # 原条目 date 键保留（原地更新不新增条目）

    def test_light_then_full_same_id_single_block_and_index_filled(self, tmp_path, monkeypatch):
        clients, counters = _setup(tmp_path, monkeypatch)
        # light 先打检查点（不碰索引）
        assert _session.save_session(CLIENT, input_desc="输入A", dsh_session=SID,
                                     light=True) is True
        assert counters["embedding"] == []
        # 终局全量 save：同 ID -> 块仍唯一，且索引补齐（计数=1）
        assert _session.save_session(CLIENT, input_desc="输入B", decisions="决策B",
                                     dsh_session=SID) is True

        text = _context_text(clients, CLIENT)
        assert _count_marker_blocks(text, SID) == 1
        assert "输入B" in text and "输入A" not in text
        assert counters["embedding"] == [1]
        # 终局 save 生成 session_notes
        assert glob.glob(str(clients / CLIENT / "session_notes_*.md"))


# ============================================================
# 不传新参 = 现状 append（逐字节不变）
# ============================================================
class TestLegacyAppendUnchanged:
    def test_no_dsh_session_appends_two_blocks_and_entries(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        assert _session.save_session(CLIENT, input_desc="输入A", decisions="决策A") is True
        assert _session.save_session(CLIENT, input_desc="输入B", decisions="决策B") is True

        text = _context_text(clients, CLIENT)
        # dsh_session=None 时 append 两块（现状不变）
        assert text.count("### [") == 2
        assert "第 1 次会话" in text and "第 2 次会话" in text
        assert "<!-- dsh:session:" not in text  # 无标记

        entries = _task_entries(tmp_path)
        assert len(entries) == 2
        assert all("dsh_session" not in e for e in entries)
        assert [e["session"] for e in entries] == [1, 2]

    def test_marker_only_written_when_dsh_session_given(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", dsh_session=SID)
        _session.save_session(CLIENT, input_desc="输入B")  # 无 ID -> append 无标记块
        text = _context_text(clients, CLIENT)
        assert _count_marker_blocks(text, SID) == 1  # 只有第一块带标记
        assert text.count("### [") == 2


# ============================================================
# light=True：证据守门 + context/task_history 照常，重型副作用跳过
# ============================================================
class TestLightMode:
    def test_light_skips_session_notes(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              dsh_session=SID, light=True)
        # light=True 不生成 session_notes
        assert not glob.glob(str(clients / CLIENT / "session_notes_*.md"))

    def test_light_skips_embedding_and_other_indexes(self, tmp_path, monkeypatch):
        _, counters = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              dsh_session=SID, light=True)
        # light 不调用 build_embedding_index（monkeypatch 计数=0）
        assert counters["embedding"] == []
        # 按规格：graph / bm25 / case_cards 同样跳过
        assert counters["graph"] == []
        assert counters["bm25"] == []
        assert counters["cases"] == []
        # outputs_index 不在跳过清单内（任务规格），light 下照常更新
        assert counters["outputs"] == [1]

    def test_light_still_upserts_context_and_task_history(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              dsh_session=SID, light=True)
        _session.save_session(CLIENT, input_desc="输入B", decisions="决策B",
                              dsh_session=SID, light=True)
        text = _context_text(clients, CLIENT)
        assert _count_marker_blocks(text, SID) == 1
        assert "输入B" in text
        entries = _task_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["decisions"] == "决策B"


# ============================================================
# T7 集成：锁失败 return False 零写入 / 正常跑完无锁残留
# ============================================================
class TestLockIntegration:
    def test_held_lock_save_returns_false_no_write(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        client_dir = clients / CLIENT
        client_dir.mkdir()  # 锁文件必须挂在已存在目录内

        # save_session 内部 acquire 用短超时，避免测试等 30s
        real_acquire = _save_lock.acquire_save_lock
        monkeypatch.setattr(
            _save_lock, "acquire_save_lock",
            lambda d, timeout=30.0, stale_after=300.0: real_acquire(d, timeout=1.0, stale_after=stale_after))

        fd = _save_lock.acquire_save_lock(str(client_dir), timeout=1.0)
        assert fd is not None
        try:
            result = _session.save_session(CLIENT, input_desc="输入A", decisions="决策A")
            assert result is False  # 持锁调用 -> 返回 False
        finally:
            _save_lock.release_save_lock(str(client_dir), fd)

        # 零写入：context.md / task_history 均未创建
        assert not (client_dir / "context.md").exists()
        assert _task_entries(tmp_path) == []

    def test_normal_save_no_lock_residue(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        assert _session.save_session(CLIENT, input_desc="输入A", dsh_session=SID) is True
        # save_session 正常跑完无锁残留
        assert not (clients / CLIENT / ".save_lock").exists()


# ============================================================
# parse_args 新键（T8b 事件层以 CLI 传 --dsh-session= / --light）
# ============================================================
class TestParseArgsDshKeys:
    def test_dsh_session_and_light_parsed(self):
        r = _session.parse_args(["--dsh-session=sess-x", "--light"])
        assert r["dsh_session"] == "sess-x"
        assert r["light"] is True

    def test_defaults_none_false(self):
        r = _session.parse_args([])
        assert r["dsh_session"] is None
        assert r["light"] is False
        # 旧四键行为不变
        assert r["input_desc"] == "" and r["decisions"] == ""

    def test_light_value_variants(self):
        assert _session.parse_args(["--light=1"])["light"] is True
        assert _session.parse_args(["--light=true"])["light"] is True
        assert _session.parse_args(["--light=0"])["light"] is False

    def test_empty_dsh_session_means_none(self):
        r = _session.parse_args(["--dsh-session="])
        assert r["dsh_session"] is None


# ============================================================
# 纯函数单测：_build_session_entry / _upsert_session_block
# ============================================================
class TestBuildSessionEntry:
    def test_legacy_format_byte_identical(self):
        entry = _session._build_session_entry(
            "2026-08-18", 3, "输入", "决策", "产出", "待办", [], None)
        expected = ("\n### [2026-08-18] 第 3 次会话\n"
                    "#### 本次输入\n输入\n"
                    "#### 关键决策\n决策\n"
                    "#### 产出文件\n产出\n"
                    "#### 待办 / 下次要做的\n待办\n")
        assert entry == expected

    def test_marker_inserted_after_title_line(self):
        entry = _session._build_session_entry(
            "2026-08-18", 3, "输入", "决策", "产出", "待办", [], SID)
        assert entry.startswith(
            f"\n### [2026-08-18] 第 3 次会话\n<!-- dsh:session:{SID} -->\n#### 本次输入\n")

    def test_evidence_lines_appended_after_body(self):
        entry = _session._build_session_entry(
            "2026-08-18", 1, "输入", "决策", "", "", ["file:a.html"], None)
        assert entry.endswith("#### 证据\nfile:a.html\n")


class TestUpsertSessionBlock:
    def test_replace_last_block_with_same_id(self):
        content = ("### [2026-08-18] 第 1 次会话\n"
                   "<!-- dsh:session:sess-1 -->\n"
                   "#### 本次输入\n旧\n")
        entry = ("\n### [2026-08-18] 第 2 次会话\n"
                 "<!-- dsh:session:sess-1 -->\n"
                 "#### 本次输入\n新\n")
        new_content, replaced, old_head = _session._upsert_session_block(content, entry, "sess-1")
        assert replaced is True
        assert old_head == ("2026-08-18", 1)  # 保留旧标题的日期与会话号
        assert "第 1 次会话" in new_content
        assert "新" in new_content and "旧" not in new_content

    def test_no_marker_last_block_returns_unchanged(self):
        content = "### [2026-08-18] 第 1 次会话\n#### 本次输入\n旧\n"
        entry = ("\n### [2026-08-18] 第 2 次会话\n"
                 "<!-- dsh:session:sess-2 -->\n#### 本次输入\n新\n")
        new_content, replaced, old_head = _session._upsert_session_block(content, entry, "sess-2")
        assert replaced is False
        assert old_head is None
        assert new_content == content  # 调用方走现有 append

    def test_different_id_last_block_returns_unchanged(self):
        content = ("### [2026-08-18] 第 1 次会话\n"
                   "<!-- dsh:session:sess-1 -->\n#### 本次输入\n旧\n")
        entry = ("\n### [2026-08-18] 第 2 次会话\n"
                 "<!-- dsh:session:sess-2 -->\n#### 本次输入\n新\n")
        new_content, replaced, _ = _session._upsert_session_block(content, entry, "sess-2")
        assert replaced is False
        assert new_content == content


# ============================================================
# 监工修复（2026-08-19 真客户实测）：upsert 合并语义
# ============================================================
class TestUpsertMergeSemantics:
    """同会话二次 save 参数为空时，必须保留旧块内容（否则 light/dispose
    的空参数 save 会覆盖先前更丰富的决策与证据）。"""

    def test_second_minimal_save_keeps_old_decisions_and_evidence(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        # 第一次：富内容（决策 + 证据）
        assert _session.save_session(
            CLIENT, input_desc="输入A", decisions="决策A：重要口径", pending="待办A",
            evidence="file:不存在.md;user:测试", dsh_session=SID) is True
        text1 = _context_text(clients, CLIENT)
        assert "决策A：重要口径" in text1
        # 第二次：仅输入（模拟 light/dispose 空参数 upsert）
        assert _session.save_session(
            CLIENT, input_desc="输入B", dsh_session=SID) is True
        text2 = _context_text(clients, CLIENT)
        # 合并语义：输入被更新，决策与待办保留
        assert _count_marker_blocks(text2, SID) == 1
        assert "输入B" in text2
        assert "决策A：重要口径" in text2
        assert "待办A" in text2

    def test_second_minimal_save_keeps_old_evidence_section(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              evidence="file:不存在.md;user:测试", dsh_session=SID)
        # 第二次无证据 -> 旧证据段保留（[✗] 待核行仍在，供可见核对）
        _session.save_session(CLIENT, input_desc="输入B", dsh_session=SID)
        text = _context_text(clients, CLIENT)
        assert "#### 证据" in text
        assert "file:不存在.md" in text

    def test_second_minimal_save_keeps_task_history_fields(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              evidence="user:测试", dsh_session=SID)
        _session.save_session(CLIENT, input_desc="输入B", dsh_session=SID)
        entries = _task_entries(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        # 合并语义：新值空 -> 保留旧值（task_history 无 input_desc 键）
        assert e["decisions"] == "决策A"
        assert e["evidence"] == "user:测试"

    def test_second_full_save_still_overwrites_nonempty(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A", dsh_session=SID)
        _session.save_session(CLIENT, input_desc="输入B", decisions="决策B", dsh_session=SID)
        text = _context_text(clients, CLIENT)
        # 非空新值照常覆盖
        assert "决策B" in text and "决策A" not in text

    def test_merge_pure_function_unit(self):
        old_sections = {
            "本次输入": "旧输入",
            "关键决策": "旧决策（待补证据）",
            "产出文件": "(未记录)",
            "待办 / 下次要做的": "旧待办",
            "证据": "[✗] file:旧.md（文件不存在: 旧.md）",
        }
        entry = ("\n### [2026-08-18] 第 2 次会话\n"
                 "<!-- dsh:session:sess-1 -->\n"
                 "#### 本次输入\n新输入\n"
                 "#### 关键决策\n(未记录)\n"
                 "#### 产出文件\n(未记录)\n"
                 "#### 待办 / 下次要做的\n(未记录)\n")
        out = _session._merge_session_entry(entry, old_sections)
        assert "新输入" in out          # 非空新值保留
        assert "旧决策（待补证据）" in out  # 空新值回填旧值
        assert "旧待办" in out
        assert "#### 证据" in out       # 旧证据段回填
        assert "[✗] file:旧.md" in out

    def test_merge_no_change_returns_identical(self):
        old_sections = {"本次输入": "旧输入", "关键决策": "旧决策"}
        entry = ("\n### [2026-08-18] 第 2 次会话\n"
                 "#### 本次输入\n新输入\n"
                 "#### 关键决策\n新决策\n")
        out = _session._merge_session_entry(entry, old_sections)
        assert out == entry  # 无字段可合并 -> 逐字节不变


class TestUpsertMergeTaskHistory:
    def test_second_minimal_save_keeps_task_history_fields(self, tmp_path, monkeypatch):
        clients, _ = _setup(tmp_path, monkeypatch)
        _session.save_session(CLIENT, input_desc="输入A", decisions="决策A",
                              evidence="user:测试", dsh_session=SID)
        _session.save_session(CLIENT, input_desc="输入B", dsh_session=SID)
        entries = _task_entries(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        # 合并语义：新值空 -> 保留旧值（task_history 无 input_desc 键，只查决策/证据）
        assert e["decisions"] == "决策A"
        assert e["evidence"] == "user:测试"
