# -*- coding: utf-8 -*-
"""I-3 认知链装配 批1（A2-A6）keynote 全链测试。

覆盖：
- A2：keynote_change 条目类型写入/读取（append_keynote_change + gate_entry 认新类型）
- A3：HEAD 注入顺序（keynote 段先于普通铁律）+ 无 keynote 向后兼容
- A4：pre_check WARN 触发与不触发 + TAIL 自检项
- A5：线集合核对（子集通过 / 新线提示 / 先后权重冲突 / 无 keynote 兼容）
- A6：audit hash 对账（tmp 封闭，不依赖仓库真实状态）

全部用 tmp_path + monkeypatch 造假客户目录，绝不读写真实 _knowledge/。
"""

import hashlib

import _cli_guards
import _domain_guard
import _memory_guard
import _paths
import _session
import _theme_guard
from _cli_audit import _audit_keynote_hash, _latest_keynote_change_hash

CLIENT = "基调测试客户K1"

KEYNOTE_V1 = """# 基调测试客户K1 · 基调卡（keynote）

> 版本：v1 ｜ 生效日期：2026-09-01 ｜ 批准人：用户 ｜ 批准日期：2026-09-04
> 性质：本卡是该客户所有提取与输出的**权重基准**。

## 线清单

| 线 | 内容 | 权重档 | 先后 | 依据 |
|---|---|---|---|---|
| 1 工厂线 | MES + WMS + QMS（生产/质量/仓储） | 主线 | 一期 | 用户拍板 |
| 2 经营线 | CRM + 研发项目管理 + 基础 OA | 主线 | 二期 | 用户拍板 |
| 3 研发支撑线 | 研发算力、出海合规、AI 应用 | 主线 | 三期 | 用户拍板 |

> 权重档取值：主线 / 次线 / 底座 / 排除。先后取值：一期 / 二期 / 三期 / 待定。

## 呈现结构

现状与痛点 → 建设目标 → 蓝图架构 → 差距分析 → 实施路径 → 价值与收益 → 下一步行动

## 修改纪律

- 后续轮次只做**增量修改**（证实/证伪/新增），对回线清单。

## 变更记录指针

| 版本 | 日期 | decisions 事件 | 锚点日志编号 |
|---|---|---|---|

## 备注
"""


def _make_client(tmp_path, monkeypatch, keynote_text=KEYNOTE_V1, decisions_text=None):
    """造假客户目录（keynote.md / decisions.md 按需），重定向 CLIENTS_DIR/SCRIPT_DIR。"""
    clients = tmp_path / "clients"
    cdir = clients / CLIENT
    cdir.mkdir(parents=True, exist_ok=True)
    if keynote_text is not None:
        (cdir / "keynote.md").write_bytes(keynote_text.encode("utf-8"))
    if decisions_text is not None:
        (cdir / "decisions.md").write_bytes(decisions_text.encode("utf-8"))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    # 指针相对路径由 _paths.rel_to_script 计算（跨盘回退绝对），故重定向 _paths.SCRIPT_DIR
    monkeypatch.setattr(_paths, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(_memory_guard, "SCRIPT_DIR", str(tmp_path))
    return clients, cdir


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================
# load_keynote parser（A1 模板契约的消费端）
# ============================================================
class TestLoadKeynote:
    def test_parse_lines_and_meta(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        assert kn["version"] == "v1"
        assert kn["effective_date"] == "2026-09-01"
        assert kn["approver"] == "用户"
        assert [row["name"] for row in kn["lines"]] == ["工厂线", "经营线", "研发支撑线"]
        assert kn["lines"][0]["weight"] == "主线" and kn["lines"][0]["order"] == "一期"
        assert kn["lines"][2]["order"] == "三期"
        assert kn["sha256"] == _sha256(KEYNOTE_V1)
        assert "现状与痛点" in kn["structure"]

    def test_missing_returns_none(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, keynote_text=None)
        assert _theme_guard.load_keynote(CLIENT) is None


# ============================================================
# A2：keynote_change 条目类型
# ============================================================
class TestKeynoteChangeEntry:
    def test_append_writes_event_with_pointer(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        path = _theme_guard.append_keynote_change(
            CLIENT, "初始化 keynote v1", approver="用户", session_ref="sess-k1")
        assert path is not None
        text = (tmp_path / "clients" / CLIENT / "decisions.md").read_text(encoding="utf-8")
        assert "**type: keynote_change**" in text
        assert "初始化 keynote v1" in text
        assert f"keynote.md@v1 sha256:{_sha256(KEYNOTE_V1)}" in text
        assert "批准人: 用户" in text
        # 只记事件：不复述线清单内容
        assert "MES + WMS + QMS" not in text

    def test_append_with_conflict_note(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        _theme_guard.append_keynote_change(
            CLIENT, "权重调整", conflict_note="新材料暗示经营线提前，两版并列挂待确认")
        text = (tmp_path / "clients" / CLIENT / "decisions.md").read_text(encoding="utf-8")
        assert "冲突并列: 新材料暗示经营线提前" in text

    def test_missing_keynote_refused(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, keynote_text=None)
        assert _theme_guard.append_keynote_change(CLIENT, "x") is None
        assert not (tmp_path / "clients" / CLIENT / "decisions.md").exists()

    def test_gate_entry_accepts_known_type(self):
        r = _memory_guard.gate_entry("基调变更", "", CLIENT, entry_type="keynote_change")
        assert r["entry_type"] == "keynote_change"
        assert "未知条目类型" not in str(r["reasons"])

    def test_gate_entry_unknown_type_visible_warn(self):
        r = _memory_guard.gate_entry("", "", CLIENT, entry_type="bogus_type")
        assert r["verdict"] == "warn"
        assert "条目类型未知" in r["marker"]
        assert any("未知条目类型" in x for x in r["reasons"])

    def test_gate_entry_strict_semantics_unchanged(self):
        # 三道闸语义不变：strict + 坏引用仍 blocked，与条目类型无关
        r = _memory_guard.gate_entry(
            "d", "file:no/such/file_xyz.md", CLIENT,
            strict=True, entry_type="keynote_change", base_dir="/nonexistent")
        assert r["verdict"] == "blocked"

    def test_parse_args_entry_type(self):
        r = _session.parse_args(["--decisions=x", "--entry-type=keynote_change"])
        assert r["entry_type"] == "keynote_change"
        assert _session.parse_args(["--decisions=x"])["entry_type"] is None


# ============================================================
# A3：HEAD 注入（最前段，先于普通铁律）
# ============================================================
class TestHeadInjection:
    DECISIONS = ("# 决策记录\n\n## [2026-08-01] 核心铁律必须遵守\n"
                 "- **决策**: 铁律内容\n- **persistence**: permanent\n- **scope**: client\n")

    def test_keynote_segment_first(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, decisions_text=self.DECISIONS)
        pc = _theme_guard.pre_check(CLIENT)
        head = pc["head_context"]
        assert head.startswith("=== 基调基准 keynote.md@v1")
        assert "[KEYNOTE] 工厂线(主线·一期)｜经营线(主线·二期)｜研发支撑线(主线·三期)" in head
        # keynote 段先于普通铁律段
        assert head.index("[KEYNOTE]") < head.index("[PERMANENT-CLIENT]")
        assert pc["keynote"]["version"] == "v1"

    def test_no_keynote_behaviour_unchanged(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, keynote_text=None,
                     decisions_text=self.DECISIONS)
        pc = _theme_guard.pre_check(CLIENT)
        assert pc["keynote"] is None
        assert pc["head_context"].startswith("=== 核心约束刷新 ===")
        assert "KEYNOTE" not in pc["head_context"]

    def test_auto_for_input_has_keynote_key(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
        monkeypatch.setattr(_session, "recall", lambda *a, **kw: [])
        import _context, _aliases
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(tmp_path / "clients"))
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(tmp_path / "clients"))
        r = _session.auto_for_input("做方案", client_name=CLIENT)
        assert "keynote" in r and r["keynote"]["version"] == "v1"
        assert r["head_context"].startswith("=== 基调基准")


# ============================================================
# A4：pre_check WARN + TAIL 自检项
# ============================================================
class TestPreCheckWarnAndTail:
    def test_warn_when_keynote_missing(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch, keynote_text=None)
        w = _cli_guards.keynote_pre_check_warn(CLIENT)
        assert w and "未定基调" in w and "不得从材料猜权重" in w

    def test_no_warn_when_keynote_exists(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        assert _cli_guards.keynote_pre_check_warn(CLIENT) is None

    def test_no_client_no_warn(self):
        assert _cli_guards.keynote_pre_check_warn(None) is None
        assert _cli_guards.keynote_pre_check_warn("") is None

    def test_tail_adds_keynote_item(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        tail = _theme_guard.build_tail_checklist([], keynote=kn)
        assert "线间权重符合基调卡" in tail

    def test_tail_unchanged_without_keynote(self):
        assert _theme_guard.build_tail_checklist([], keynote=None) == ""


# ============================================================
# A5：verify 线集合核对（观察级）
# ============================================================
class TestKeynoteLineCheck:
    def test_subset_passes(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        text = "工厂线覆盖 MES，经营线覆盖 CRM，实施路径按一期二期三期推进"
        assert _domain_guard.check_keynote_lines(text, kn) == []

    def test_undeclared_new_line_flagged(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        warns = _domain_guard.check_keynote_lines("工厂线之外新增物流线", kn)
        assert any("物流线" in w and "人审" in w for w in warns)

    def test_order_conflict_flagged(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        warns = _domain_guard.check_keynote_lines("研发支撑线作为一期主线先行", kn)
        assert any("研发支撑线" in w and "先后冲突" in w for w in warns)

    def test_generic_words_not_flagged(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        text = "以上为主线安排，系统上线后按路线推进"
        assert _domain_guard.check_keynote_lines(text, kn) == []

    def test_no_keynote_compatible(self):
        assert _domain_guard.check_keynote_lines("任意文本 物流线", None) == []
        assert _domain_guard.check_keynote_lines("", {"lines": []}) == []
        assert _domain_guard.keynote_observe_for_text("任意文本") == ""

    def test_observe_helper_msg_suffix(self, tmp_path, monkeypatch):
        _make_client(tmp_path, monkeypatch)
        suffix = _domain_guard.keynote_observe_for_text("新增物流线", client_name=CLIENT)
        assert suffix.startswith(" | keynote: ") and "物流线" in suffix
        assert _domain_guard.keynote_observe_for_text("工厂线 MES", client_name=CLIENT) == ""


# ============================================================
# A6：audit hash 对账（tmp 封闭）
# ============================================================
class TestAuditKeynoteHash:
    def _register(self, cdir, keynote_text):
        dec = ("# 决策记录\n\n## [2026-09-04] keynote_change 基调变更 v1\n"
               "- **决策**: 初始化｜指针: keynote.md@v1 sha256:"
               + _sha256(keynote_text) + "｜批准人: 用户\n"
               "- **persistence: task**\n- **scope: task**\n"
               "- **type: keynote_change**\n")
        (cdir / "decisions.md").write_bytes(dec.encode("utf-8"))

    def test_consistent_no_warn(self, tmp_path, capsys):
        cdir = tmp_path / "clients" / CLIENT
        cdir.mkdir(parents=True)
        (cdir / "keynote.md").write_bytes(KEYNOTE_V1.encode("utf-8"))
        self._register(cdir, KEYNOTE_V1)
        assert _audit_keynote_hash(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "对账一致" in out and "⚠ [" not in out

    def test_modified_keynote_warns(self, tmp_path, capsys):
        cdir = tmp_path / "clients" / CLIENT
        cdir.mkdir(parents=True)
        self._register(cdir, KEYNOTE_V1)
        (cdir / "keynote.md").write_bytes((KEYNOTE_V1 + "\n手改一行\n").encode("utf-8"))
        assert _audit_keynote_hash(clients_dir=str(tmp_path / "clients")) is True
        out = capsys.readouterr().out
        assert "基调被改但无决策记录" in out

    def test_unregistered_keynote_warns(self, tmp_path, capsys):
        cdir = tmp_path / "clients" / CLIENT
        cdir.mkdir(parents=True)
        (cdir / "keynote.md").write_bytes(KEYNOTE_V1.encode("utf-8"))
        assert _audit_keynote_hash(clients_dir=str(tmp_path / "clients")) is True
        assert "无 keynote_change 登记" in capsys.readouterr().out

    def test_no_keynote_clients_skipped(self, tmp_path, capsys):
        (tmp_path / "clients" / CLIENT).mkdir(parents=True)
        assert _audit_keynote_hash(clients_dir=str(tmp_path / "clients")) is True
        assert "无可对账客户" in capsys.readouterr().out

    def test_latest_hash_picked(self, tmp_path):
        dec = tmp_path / "decisions.md"
        dec.write_text(
            "# 决策记录\n\n## [2026-09-01] keynote_change A\n"
            "- **决策**: x sha256:" + "a" * 64 + "\n- **type: keynote_change**\n"
            "\n## [2026-09-04] keynote_change B\n"
            "- **决策**: y sha256:" + "b" * 64 + "\n- **type: keynote_change**\n",
            encoding="utf-8")
        assert _latest_keynote_change_hash(str(dec)) == "b" * 64
        assert _latest_keynote_change_hash(str(tmp_path / "none.md")) is None
