# -*- coding: utf-8 -*-
"""P3 记忆/会话组回归测试（全库审查报告 2026-09-06 §五）。

覆盖 8 项修复（第 9 项 _classify_config.json forbidden 3≠5 对齐【明确不做】，
设计依赖，不在本批）：
  1. append_session_decision upsert 以新 reason 覆盖旧「待补证据」标记
  2. keynote_change 写入/引用标题同源（keynote_change_topic 唯一拼装点）
  3. load_active_themes 文件头判定补无括号日期形态（首条铁律不再被丢）
  4. 客户目录存在而 context.md 缺失 -> 按模板补齐 + save fail-soft
  5. _upsert_session_block 不吞块尾非白名单 H2 段（## 自动提取: …）
  6. _pending 根目录散落文件进催办清单
  7. sweep/main_entry dry_run 全路径只读（不建月目录、不重写 todo、不迁移）
  8. 产出路径合规检查补分隔符边界（测试客户P3B 不误配 测试客户P3Bv2）

全部用 tmp_path 造假客户目录，绝不写真实 _knowledge/clients/；
重型副作用（embedding/bm25/graph/case_cards/outputs_index/worldbook）全部打桩。
"""

import os
from datetime import datetime

import _aliases
import _context
import _embed_index
import _inbox_scan as scan
import _memory_guard
import _session
import _theme_guard
import _worldbook

CLIENT = "测试客户P3B"
SID = "sess-p3b"


# ============================================================
# 测试基座（与 test_session_upsert 同口径）
# ============================================================
def _setup(tmp_path, monkeypatch):
    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
    monkeypatch.setattr(_session, "SCRIPT_DIR", str(tmp_path))

    def _fake(*a, **kw):
        return {}

    monkeypatch.setattr(_embed_index, "build_embedding_index", _fake)
    monkeypatch.setattr(_session, "_sync_bm25_if_stale", _fake)
    monkeypatch.setattr(_session, "build_client_graph", _fake)
    monkeypatch.setattr(_session, "_extract_case_cards", _fake)
    monkeypatch.setattr(_session, "update_outputs_index", _fake)
    monkeypatch.setattr(_worldbook, "build_worldbook", _fake)
    return clients


def _seed_session_decision(clients, decision, reason):
    """预置一条带 task_id 的 task 决策块（upsert 命中的前提）。"""
    d = clients / CLIENT
    d.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    text = (
        f"# {CLIENT} 决策记录\n\n"
        f"## [{today}] 会话决策 {today} #sess-1\n"
        f"- **决策**: {decision}\n"
        f"- **理由**: {reason}\n"
        f"- **层级**: L4\n"
        f"- **persistence: task**\n"
        f"- **scope: task**\n"
        f"- **task_id: {today}#sess-1**\n"
        f"- **来源**: user:会话决策\n"
        f"- **confidence**: 0.5\n"
    )
    (d / "decisions.md").write_text(text, encoding="utf-8")
    return d / "decisions.md"


# ============================================================
# 1. upsert 以新 reason 覆盖旧「待补证据」
# ============================================================
class TestUpsertReasonOverwrite:
    def test_upsert_clears_stale_pending_evidence(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        p = _seed_session_decision(clients, "旧决策", "（待补证据）")
        _theme_guard.append_session_decision(
            CLIENT, "会话决策", "新决策内容", evidence_marker="", session_ref="sess-1")
        text = p.read_text(encoding="utf-8")
        assert "- **决策**: 新决策内容" in text
        # 旧「待补证据」标记被清掉（健康计数不再虚高）
        assert "（待补证据）" not in text
        assert "- **理由**: (未记录)" in text
        h = _memory_guard.scan_memory_health(CLIENT, client_dir=str(clients / CLIENT))
        assert h["pending_evidence"] == 0

    def test_upsert_overwrites_reason_with_new_marker(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        p = _seed_session_decision(clients, "旧决策", "（待补证据）")
        _theme_guard.append_session_decision(
            CLIENT, "会话决策", "新决策内容",
            evidence_marker="（证据待核：文件缺失）", session_ref="sess-1")
        text = p.read_text(encoding="utf-8")
        assert "- **理由**: （证据待核：文件缺失）" in text
        assert "（待补证据）" not in text


# ============================================================
# 2. keynote_change 写入/引用标题同源
# ============================================================
KEYNOTE_TEXT = (
    f"# {CLIENT} 基调卡\n\n版本: v1\n生效日期: 2026-09-01\n批准人: 用户\n"
)


class TestKeynoteChangeTitleUnified:
    def test_reference_title_matches_written_title(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        (clients / CLIENT).mkdir(parents=True)
        (clients / CLIENT / "keynote.md").write_text(KEYNOTE_TEXT, encoding="utf-8")
        assert _session.save_session(
            CLIENT, input_desc="i", decisions="初始化基调 v1",
            entry_type="keynote_change", dsh_session=SID) is True
        dec = (clients / CLIENT / "decisions.md").read_text(encoding="utf-8")
        ctx = (clients / CLIENT / "context.md").read_text(encoding="utf-8")
        # decisions.md 实际写入标题
        assert "keynote_change 基调变更 v1" in dec
        # context.md 引用行指向同一标题（此前硬编码 session_ref，引用悬空）
        assert "（见 decisions.md：keynote_change 基调变更 v1）" in ctx

    def test_keynote_change_topic_fallback_without_version(self):
        # 无版本 -> v? 兜底，写入与引用两侧同一拼装点
        assert _theme_guard.keynote_change_topic("") == "keynote_change 基调变更 v?"
        assert _theme_guard.keynote_change_topic("v2") == "keynote_change 基调变更 v2"


# ============================================================
# 3. 文件头判定补无括号日期形态
# ============================================================
class TestDecisionHeaderDetection:
    def test_first_unbracketed_date_block_not_dropped(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        d = clients / CLIENT
        d.mkdir(parents=True)
        # 首块为无括号日期决策（行首带一个空格 -> 统一切分器不在该行产生切分点，
        # 整块成为 blocks[0]）。旧字面量元组（"## 决策"/"### D-"/"## ["）不认
        # 无括号形态，会把这条真决策整体当文件头丢弃。
        (d / "decisions.md").write_text(
            " ## 2026-07-01：首条铁律\n"
            "- **决策**: 不分阶段\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n\n"
            "## 2026-07-02：第二条铁律\n"
            "- **决策**: 另一条\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n",
            encoding="utf-8")
        themes = _theme_guard.load_active_themes(CLIENT)
        names = [t["theme"] for t in themes]
        assert any("首条铁律" in n for n in names)
        assert len(names) == 2

    def test_headerless_file_with_unbracketed_heading(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        d = clients / CLIENT
        d.mkdir(parents=True)
        # 无文件头、首行即无括号日期决策：H1 文件头判定不得误伤
        (d / "decisions.md").write_text(
            "## 2026-07-01：铁律A\n"
            "- **决策**: 内容A\n"
            "- **persistence**: permanent\n"
            "- **scope**: client\n",
            encoding="utf-8")
        themes = _theme_guard.load_active_themes(CLIENT)
        assert len(themes) == 1
        assert "铁律A" in themes[0]["theme"]


# ============================================================
# 4. 客户目录存在而 context.md 缺失 -> 补齐 + fail-soft
# ============================================================
class TestMissingContextMd:
    def test_save_backfills_missing_context_md(self, tmp_path, monkeypatch):
        clients = _setup(tmp_path, monkeypatch)
        d = clients / CLIENT
        (d / "refs").mkdir(parents=True)  # 目录已存在，context.md 缺失
        assert _session.save_session(CLIENT, input_desc="i", dsh_session=SID) is True
        ctx = d / "context.md"
        assert ctx.exists()
        assert "第 1 次会话" in ctx.read_text(encoding="utf-8")

    def test_save_survives_context_read_failure(self, tmp_path, monkeypatch, capsys):
        clients = _setup(tmp_path, monkeypatch)
        d = clients / CLIENT
        (d / "refs").mkdir(parents=True)
        # 模板补齐也失败（如目录只读）——save 仍 fail-soft 走完，不抛 FileNotFoundError
        monkeypatch.setattr(_context, "_init_context_file", lambda p: False)
        assert _session.save_session(CLIENT, input_desc="i", dsh_session=SID) is True
        assert "context.md 读取失败" in capsys.readouterr().out
        # 降级后照常落盘（append 模式自行建文件）
        assert (d / "context.md").exists()


# ============================================================
# 5. upsert 不吞块尾非白名单 H2 段
# ============================================================
CONTENT_WITH_EXTRACT = (
    "# 测试客户P3B\n\n## 基础信息\n- x\n\n"
    "### [2026-09-06] 第 1 次会话\n"
    "<!-- dsh:session:sess-5 -->\n"
    "#### 本次输入\n旧输入\n"
    "#### 关键决策\n旧决策\n"
    "#### 产出文件\n(未记录)\n"
    "#### 待办 / 下次要做的\n(未记录)\n\n"
    "## 自动提取: 材料.docx\n来源: refs/材料.docx\n缓存: cache/1.md\n"
)


class TestUpsertBlockBoundary:
    def test_upsert_preserves_trailing_nonwhitelist_h2(self):
        entry = _session._build_session_entry(
            "2026-09-06", 1, "新输入", "新决策", "", "", [], "sess-5")
        new_content, replaced, old_head = _session._upsert_session_block(
            CONTENT_WITH_EXTRACT, entry, "sess-5")
        assert replaced is True
        assert old_head == ("2026-09-06", 1)
        assert "新输入" in new_content and "旧输入" not in new_content
        # 块尾 classify --extract 追加的非白名单 H2 段不被整块吞掉
        assert "## 自动提取: 材料.docx" in new_content
        assert "来源: refs/材料.docx" in new_content

    def test_upsert_marker_mismatch_keeps_content_intact(self):
        entry = _session._build_session_entry(
            "2026-09-06", 2, "新输入", "新决策", "", "", [], "other")
        new_content, replaced, _ = _session._upsert_session_block(
            CONTENT_WITH_EXTRACT, entry, "other")
        assert replaced is False
        assert new_content == CONTENT_WITH_EXTRACT


# ============================================================
# 6. _pending 根目录散落文件进催办清单
# ============================================================
class TestTodoIncludesRootFiles:
    def test_refresh_todo_includes_pending_root_files(self, tmp_path):
        root = tmp_path
        mdir = root / "inbox" / "_pending" / "2026-08"
        mdir.mkdir(parents=True)
        (mdir / "老的.pdf").write_bytes(b"x")
        (root / "inbox" / "_pending" / "散落.docx").write_bytes(b"x")
        (root / "inbox" / "_pending" / "更旧的.txt").write_bytes(b"x")
        os.utime(mdir / "老的.pdf", (0, 0))
        os.utime(root / "inbox" / "_pending" / "更旧的.txt", (0, 0))
        todo = scan.refresh_todo(str(root))
        text = open(todo, encoding="utf-8").read()
        # 根目录散落文件进清单（此前永不出现）
        assert "散落.docx" in text
        assert "更旧的.txt" in text
        assert "2026-08/老的.pdf" in text
        # 超 30 天的（含根目录散文件）置顶；新散文件归本期待定
        top = text.split("## 本期待定")[0]
        assert "更旧的.txt" in top and "老的.pdf" in top
        assert "散落.docx" in text.split("## 本期待定")[1]
        # `_` 前缀系统文件（含 _todo.md 自身）不入清单
        assert "`_todo.md`" not in text


# ============================================================
# 7. dry_run 全路径只读
# ============================================================
class TestDryRunReadonly:
    def test_sweep_dry_run_creates_nothing_and_rewrites_nothing(self, tmp_path):
        root = tmp_path
        (root / "inbox").mkdir()
        (root / "inbox" / "材料.pptx").write_bytes(b"x")
        pending = root / "inbox" / "_pending"
        pending.mkdir()
        todo = pending / "_todo.md"
        todo.write_text("seed-marker", encoding="utf-8")
        r = scan.sweep_pending(str(root), dry_run=True)
        assert len(r["swept"]) == 1
        # 文件不动
        assert (root / "inbox" / "材料.pptx").exists()
        # _todo.md 不被重写
        assert todo.read_text(encoding="utf-8") == "seed-marker"
        # 不新建月份目录
        assert [p.name for p in pending.iterdir() if p.is_dir()] == []
        # todo_path 只报告将写入的路径
        assert r["todo_path"].endswith("_todo.md")

    def test_main_entry_dry_run_skips_uncategorized_migration(self, tmp_path):
        root = tmp_path
        unc = root / "inbox" / "_uncategorized"
        unc.mkdir(parents=True)
        (unc / "旧材料.docx").write_bytes(b"x")
        (root / ".folio" / "logs").mkdir(parents=True)
        r = scan.main_entry(str(root), dry_run=True)
        # dry_run 不做真实迁移
        assert (unc / "旧材料.docx").exists()
        assert r["migrated_uncategorized"] == 0

    def test_main_entry_real_run_still_migrates(self, tmp_path):
        root = tmp_path
        unc = root / "inbox" / "_uncategorized"
        unc.mkdir(parents=True)
        (unc / "旧材料.docx").write_bytes(b"x")
        (root / ".folio" / "logs").mkdir(parents=True)
        r = scan.main_entry(str(root), dry_run=False)
        assert r["migrated_uncategorized"] == 1
        assert not unc.exists()


# ============================================================
# 8. 产出路径合规检查补分隔符边界
# ============================================================
class TestOutputPathSeparatorBoundary:
    def test_sibling_client_dir_flagged(self, tmp_path, monkeypatch, capsys):
        _setup(tmp_path, monkeypatch)
        # 测试客户P3Bv2 目录前缀包含 测试客户P3B —— 旧裸 startswith 误放行
        assert _session.save_session(
            CLIENT, input_desc="i",
            outputs="output/测试客户P3Bv2/方案_v1.html", dsh_session=SID) is True
        assert "产出路径不合规" in capsys.readouterr().out

    def test_own_client_dir_not_flagged(self, tmp_path, monkeypatch, capsys):
        _setup(tmp_path, monkeypatch)
        assert _session.save_session(
            CLIENT, input_desc="i",
            outputs="output/测试客户P3B/方案_v1.html", dsh_session=SID) is True
        assert "产出路径不合规" not in capsys.readouterr().out
