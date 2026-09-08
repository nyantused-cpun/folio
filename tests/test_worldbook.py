# -*- coding: utf-8 -*-
"""M2-R1 世界书直生测试：直读真源 / 噪音过滤 / 结构段序 / 版本表 / 待补 / L3 注入 / audit 新鲜度。"""
import json


def _make_client(tmp_path, client="测试客户", decisions="", outputs=None, context="", preferences=""):
    clients = tmp_path / "clients"
    d = clients / client
    d.mkdir(parents=True, exist_ok=True)
    if decisions:
        (d / "decisions.md").write_text(decisions, encoding="utf-8")
    if outputs is not None:
        (d / "outputs_index.json").write_text(
            json.dumps(outputs, ensure_ascii=False), encoding="utf-8")
    if context:
        (d / "context.md").write_text(context, encoding="utf-8")
    if preferences:
        (d / "preferences.md").write_text(preferences, encoding="utf-8")
    return clients


def _simple_outputs(versions=("v1", "v2", "v3"), series="方案"):
    return {
        "client": "测试客户",
        "outputs": [
            {
                "version": v,
                "file": f"output/测试客户/{series}_{v}.html",
                "type": series,
                "status": "在用" if v == versions[-1] else "已备份",
                "date": f"2026-07-0{i+1}",
                "method": "auto-scan",
            }
            for i, v in enumerate(versions)
        ],
    }


class TestBuildWorldbookDirect:
    def test_generates_without_graph(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions=(
                "## 决策 1：预算口径\n"
                "- **日期**: 2026-06-24\n"
                "- **决策内容**: 预算以 X 为准\n"
                "- **persistence: permanent**\n"
                "- **scope: client**\n"
            ),
            outputs=_simple_outputs(),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))

        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")

        index_path = clients / "测试客户" / "client_index.md"
        assert index_path.exists()
        assert "# 测试客户 世界书" in md
        assert "_source_hashes:" in md
        assert "## 决策时间线" in md
        assert "## 产出物版本表" in md
        # 不依赖 client_graph.json
        assert not (clients / "测试客户" / "client_graph.json").exists()

    def test_source_hashes_match_build(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs=_simple_outputs(),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook, compute_source_hashes, read_source_hashes
        build_worldbook("测试客户")
        index_path = clients / "测试客户" / "client_index.md"
        assert read_source_hashes(str(index_path)) == compute_source_hashes(str(clients / "测试客户"))

    def test_client_dir_writes_into_supplied_dir_not_real_clients(self, tmp_path, monkeypatch):
        """评审修正：提供 client_dir 时写临时目录，不写 _paths.CLIENTS_DIR 真实客户。"""
        import _paths
        real_clients = tmp_path / "real_clients"
        sampled = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs=_simple_outputs(),
        )
        # 真实 CLIENTS_DIR 指向另一个临时目录；client_dir 采样路径独立
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(real_clients))
        from _worldbook import build_worldbook
        client_dir = sampled / "测试客户"
        md = build_worldbook("测试客户", client_dir=str(client_dir))

        assert (client_dir / "client_index.md").exists()
        assert "# 测试客户 世界书" in md
        assert not (real_clients / "测试客户" / "client_index.md").exists()


class TestNoiseFilter:
    def test_excludes_review_fail_and_engineering_task(self, tmp_path, monkeypatch):
        import _paths
        decisions = (
            "# 测试客户 决策记录\n"
            "\n"
            "## 决策 1：正常客户铁律\n"
            "- **日期**: 2026-07-01\n"
            "- **决策内容**: 正常内容\n"
            "- **persistence: permanent**\n"
            "- **scope: client**\n"
            "\n"
            "### D-002 · review FAIL: 测试客户_方案.html\n"
            "- **日期**: 2026-07-02\n"
            "- **决策**: 产出审查未通过\n"
            "- **persistence: task**\n"
            "- **scope: client**\n"
            "\n"
            "## 决策 3：工程侧剥离指针\n"
            "- **日期**: 2026-07-03\n"
            "- **决策内容**: 已迁「代码修改」（工程侧剥离）\n"
            "\n"
            "### D-004 · 工程 task 临时记录\n"
            "- **日期**: 2026-07-04\n"
            "- **决策**: 跑回归测试\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
            "- **task_id: 20260704_120000**\n"
            "\n"
            "## [2026-07-05] 客户会话决策 2026-07-05 #第1次\n"
            "- **决策**: 客户确认采用 A 方案\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
            "- **task_id: 2026-07-05#第1次**\n"
            "- **来源**: user:会话决策\n"
        )
        clients = _make_client(tmp_path, decisions=decisions, outputs=_simple_outputs())
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "review FAIL" not in md
        assert "审查未通过" not in md
        assert "已迁「代码修改」" not in md
        assert "工程侧剥离" not in md
        assert "跑回归测试" not in md
        # 客户会话 task 应保留（task 最近 10 条）
        assert "客户确认采用 A 方案" in md
        assert "正常客户铁律" in md

    def test_client_task_without_session_marker_is_kept(self, tmp_path, monkeypatch):
        """评审修正：客户项目 task 不因缺少 user:会话决策/日期#第N次被排除。"""
        import _paths
        decisions = (
            "# 测试客户 决策记录\n"
            "\n"
            "## [2026-07-21] v6 方案内容结构：五段式\n"
            "- **决策**: 客户项目按五段组织内容\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
            "- **task_id: v6_proposal**\n"
        )
        clients = _make_client(tmp_path, decisions=decisions, outputs=_simple_outputs())
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "五段式" in md
        assert "客户项目按五段组织内容" in md

    def test_internal_engineering_patterns_filtered(self, tmp_path, monkeypatch):
        """评审修正：客户 decisions.md 中明确的内部工程/工具沉淀条目要过滤。"""
        import _paths
        decisions = (
            "# 测试客户 决策记录\n"
            "\n"
            "## 决策 1：UI 规范 + CLI 下沉计划 + Profile 补全\n"
            "- **决策内容**: 落地 2 套 UI 规范，CLI 下沉只写计划\n"
            "- **persistence: permanent**\n"
            "- **scope: client**\n"
            "\n"
            "## 决策 2：架构图 skill 沉淀 + 首张实例\n"
            "- **决策内容**: 封装 architecture-diagram-builder skill\n"
            "- **persistence: permanent**\n"
            "- **scope: client**\n"
            "\n"
            "## 决策 3：md 需求清单转 xlsx 走 openpyxl 临时方案\n"
            "- **决策内容**: 用一次性 openpyxl 脚本转 xlsx\n"
            "- **persistence: permanent**\n"
            "- **scope: client**\n"
            "\n"
            "## 决策 4：单元测试记录\n"
            "- **决策**: 补 unit test 记录\n"
            "- **persistence: task**\n"
            "- **scope: task**\n"
        )
        clients = _make_client(tmp_path, decisions=decisions, outputs=_simple_outputs())
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "UI 规范 + CLI 下沉计划" not in md
        assert "架构图 skill 沉淀" not in md
        assert "openpyxl 临时方案" not in md
        assert "单元测试记录" not in md


class TestStructure:
    def test_fixed_section_order(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs=_simple_outputs(),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        sections = [
            "# 测试客户 世界书",
            "## 客户背景",
            "## 决策时间线",
            "## 产出物版本表",
            "## 待办 / 悬而未决",
        ]
        positions = [md.index(s) for s in sections]
        assert positions == sorted(positions)
        assert "## 洞察" not in md


class TestOutputVersionTable:
    def test_only_latest_and_count(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n",
            outputs=_simple_outputs(("v1", "v2", "v3")),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        # 版本表行：| 方案 | html | v3 | 3 | 在用 | 2026-07-03 |
        assert "| 方案 | html | v3 | 3 | 在用 | 2026-07-03 |" in md
        assert "| v1 |" not in md
        assert "| v2 |" not in md

    def test_string_output_entries_not_dropped(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n",
            outputs={
                "client": "测试客户",
                "outputs": [
                    "output/测试客户/方案_v1.html",
                    "output/测试客户/方案_v2.html",
                ],
            },
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "| 方案 | html | （无版本号） | 2 | 待补 | 待补 |" in md


class TestPendingMarkers:
    def test_missing_profile_fields_marked_pending(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs={"client": "测试客户", "outputs": []},
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "- 客户全称：待补" in md
        assert "- 行业：待补" in md
        assert "- 核心需求：待补" in md
        assert "- 行业：" not in md.replace("- 行业：待补", "")

    def test_empty_scope_dict_displays_pending(self, tmp_path, monkeypatch):
        import _paths
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs={"client": "测试客户", "outputs": [], "scope": {}},
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        md = build_worldbook("测试客户")
        assert "- 规模/范围：待补" in md
        assert "sheets=" not in md
        assert "subsystems=" not in md


class TestL3Injection:
    def test_l3_loads_worldbook(self, tmp_path, monkeypatch):
        import _paths
        import _context
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs=_simple_outputs(),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        build_worldbook("测试客户")

        loaded = _context.load_context_by_level("测试客户", "L3")
        assert "client_index" in loaded
        assert "# 测试客户 世界书" in loaded["client_index"]

        l5 = _context.load_context_by_level("测试客户", "L5")
        assert "client_index" not in l5
        creative = _context.load_context_by_level("测试客户", "creative")
        assert "client_index" not in creative


class TestAuditFreshness:
    def test_stale_decisions_warns(self, tmp_path, monkeypatch, capsys):
        import _paths
        from _cli_audit import _audit_worldbook_freshness
        clients = _make_client(
            tmp_path,
            decisions="# 测试客户 决策记录\n\n## 决策 1：A\n- **决策内容**: B\n",
            outputs=_simple_outputs(),
        )
        monkeypatch.setattr(_paths, "CLIENTS_DIR", str(clients))
        from _worldbook import build_worldbook
        build_worldbook("测试客户")

        # 初始新鲜不 WARN
        _audit_worldbook_freshness("测试客户", clients_dir=str(clients))
        out = capsys.readouterr().out
        assert "落后于真源" not in out

        # 人为改 decisions.md -> WARN
        d = clients / "测试客户" / "decisions.md"
        d.write_text(d.read_text(encoding="utf-8") + "\n## 决策 2：新增\n- **决策内容**: C\n",
                     encoding="utf-8")
        ok = _audit_worldbook_freshness("测试客户", clients_dir=str(clients))
        out = capsys.readouterr().out
        assert ok is True  # 警告级不影响 pass/fail
        assert "落后于真源" in out


class TestI8TimelineBudget:
    """I-8 世界书丢尾预算：permanent > 最近 task，超预算从低优先级丢。"""

    def _mk(self, persistence, scope, date, i):
        return (
            {"title": f"决策 {i}", "summary": f"概要 {i}",
             "metadata": {"persistence": persistence, "scope": scope,
                          "date": date, "decision_num": i}},
            "",
        )

    def test_permanent_over_budget_truncates_to_budget(self):
        from _worldbook import _select_timeline, TIMELINE_MAX_ITEMS
        pairs = [self._mk("permanent", "client", f"2026-01-{i:02d}", i)
                 for i in range(1, TIMELINE_MAX_ITEMS + 11)]
        perm, task = _select_timeline(pairs)
        assert len(perm) == TIMELINE_MAX_ITEMS  # 超预算截到 50
        assert task == []

    def test_permanent_under_budget_task_fills_room(self):
        from _worldbook import _select_timeline, TIMELINE_MAX_ITEMS, RECENT_TASK_LIMIT
        perm_pairs = [self._mk("permanent", "client", f"2026-01-{i:02d}", i)
                      for i in range(1, 11)]  # 10 permanent
        task_pairs = [self._mk("task", "task", f"2026-02-{i:02d}", i)
                      for i in range(1, 31)]  # 30 task
        perm, task = _select_timeline(perm_pairs + task_pairs)
        assert len(perm) == 10
        room = TIMELINE_MAX_ITEMS - 10  # 40
        assert len(task) == min(RECENT_TASK_LIMIT, room) == RECENT_TASK_LIMIT

    def test_task_only_within_budget(self):
        from _worldbook import _select_timeline
        task_pairs = [self._mk("task", "task", f"2026-02-{i:02d}", i)
                      for i in range(1, 5)]
        perm, task = _select_timeline(task_pairs)
        assert perm == []
        assert len(task) == 4


class TestI8ChunkReadAlias:
    """I-8 chunk-read 别名归一化：路径客户目录段 alias 命中 -> 规范目录名。"""

    def test_chunk_read_resolves_alias_path(self, monkeypatch, capsys):
        import types
        import _cli_cmds_idx as idx
        import _paths
        monkeypatch.setattr(_paths, "SCRIPT_DIR", "C:/kb")  # 读边界守卫对齐假工作区
        monkeypatch.setattr(idx, "CLIENTS_DIR", "C:/kb/_knowledge/clients")
        monkeypatch.setattr(
            idx, "resolve_client_name",
            lambda name: ("蓝海集团", [], "alias") if name == "蓝海"
            else (name, [], "exact"))
        seen = {}
        def fake_read_chunk(spec):
            seen["spec"] = spec
            return "chunk 内容"
        monkeypatch.setattr(idx, "read_chunk", fake_read_chunk)
        monkeypatch.setattr(idx.os.path, "exists", lambda p: True)
        args = types.SimpleNamespace(path="C:/kb/_knowledge/clients/蓝海/context.md#p1")
        idx.cmd_chunk_read(args)
        assert seen["spec"].replace("\\", "/") == "C:/kb/_knowledge/clients/蓝海集团/context.md#p1"
        out = capsys.readouterr().out
        assert "蓝海 -> 蓝海集团" in out
        assert "chunk 内容" in out

    def test_chunk_read_non_alias_keeps_path(self, monkeypatch, capsys):
        import types
        import _cli_cmds_idx as idx
        import _paths
        monkeypatch.setattr(_paths, "SCRIPT_DIR", "C:/kb")  # 读边界守卫对齐假工作区
        monkeypatch.setattr(idx, "CLIENTS_DIR", "C:/kb/_knowledge/clients")
        monkeypatch.setattr(
            idx, "resolve_client_name",
            lambda name: (name, [], "exact"))
        seen = {}
        def fake_read_chunk(spec):
            seen["spec"] = spec
            return "内容"
        monkeypatch.setattr(idx, "read_chunk", fake_read_chunk)
        monkeypatch.setattr(idx.os.path, "exists", lambda p: True)
        args = types.SimpleNamespace(path="C:/kb/_knowledge/clients/蓝海集团/方案.html#p2")
        idx.cmd_chunk_read(args)
        assert seen["spec"].replace("\\", "/") == "C:/kb/_knowledge/clients/蓝海集团/方案.html#p2"
        assert "别名解析" not in capsys.readouterr().out
