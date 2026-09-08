# -*- coding: utf-8 -*-
import pytest
"""I-3 批4 D1 golden 场景：「keynote 未经人确认不变更」（I-3 原文验收件）。

场景：材料/输入暗示权重变化（新材料暗示"研发支撑线应提前"）→ 系统行为必须是：
1. keynote.md 不被自动改写（无 keynote_change 事件产生）；
2. TAIL 自检/提示层出现冲突并列提示（keynote 声明 vs 产出伴随，两者并列可见）。

不烧 API：LLM 层用固定字符串模拟（测机制不测模型表现）。

取证方式（双轨，均可机械执行）：
- 静态：扫描生产代码（仓库根 *.py），keynote.md 相关行不得含任何写原语；
  引用 keynote.md 的文件必须在白名单内（新增文件触碰 keynote.md 直接 fail）；
  白名单文件内所有涉及 keynote 路径的 open() 必须是读模式。
- 行为：在写哨兵（write sentinel，任何写模式打开 */keynote.md 即 AssertionError）
  下跑完整链——session-start 读侧（auto_for_input）/ 生成前 pre_check /
  verify 观察（A5）/ save 链（含 AI 擅自结论的 decisions）/ 人批事件路径
  （append_keynote_change），全程 keynote.md 字节不动。

全部用 tmp_path + monkeypatch 造假客户目录，绝不读写真实 _knowledge/。
"""

import builtins
import hashlib
import os
import re

import _cli_guards
import _domain_guard
import _memory_guard
import _session
import _theme_guard
from _cli_audit import _audit_keynote_hash

CLIENT = "基调测试客户D1"

# 材料暗示前的既定基调：研发支撑线 = 主线·三期（人批 v1）
KEYNOTE_V1 = """# 基调测试客户D1 · 基调卡（keynote）

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

# 新材料（模拟材料解析输出）：暗示研发支撑线应提前——与 keynote v1 冲突
NEW_MATERIAL_HINT = "最新调研显示客户研发算力需求急迫，研发支撑线应提前到一期启动"

# 模拟 LLM 顺从材料暗示产出的方案文本（权重被材料带偏的版本）
LLM_BIASED_OUTPUT = "研发支撑线作为一期主线先行，研发算力平台优先建设"


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _make_client(tmp_path, monkeypatch, register_event=True):
    """造假客户目录（keynote v1 + 已登记 keynote_change 事件），重定向写入目标。"""
    clients = tmp_path / "clients"
    cdir = clients / CLIENT
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "keynote.md").write_bytes(KEYNOTE_V1.encode("utf-8"))
    # 预建 context.md（ensure_client_dir 只在目录不存在时从模板创建）
    (cdir / "context.md").write_bytes("# 项目上下文记录\n\n".encode("utf-8"))
    if register_event:
        dec = ("# 决策记录\n\n## [2026-09-04] keynote_change 基调变更 v1\n"
               "- **决策**: 初始化｜指针: keynote.md@v1 sha256:"
               + _sha256_bytes(KEYNOTE_V1.encode("utf-8")) + "｜批准人: 用户\n"
               "- **persistence: task**\n- **scope: task**\n"
               "- **type: keynote_change**\n")
        (cdir / "decisions.md").write_bytes(dec.encode("utf-8"))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(_memory_guard, "SCRIPT_DIR", str(tmp_path))
    return clients, cdir


class _WriteSentinel:
    """写哨兵：任何写模式 open / Path.write_* / os.replace 落到 */keynote.md 即炸。"""

    def __init__(self, monkeypatch):
        real_open = builtins.open

        def guarded_open(file, mode="r", *a, **kw):
            if any(m in mode for m in "wax+") and str(file).replace("\\", "/").endswith("keynote.md"):
                raise AssertionError(f"keynote.md 被写入: {file} (mode={mode})")
            return real_open(file, mode, *a, **kw)

        import pathlib
        real_wt = pathlib.Path.write_text
        real_wb = pathlib.Path.write_bytes

        def guarded_wt(self, *a, **kw):
            if str(self).replace("\\", "/").endswith("keynote.md"):
                raise AssertionError(f"keynote.md 被 write_text: {self}")
            return real_wt(self, *a, **kw)

        def guarded_wb(self, *a, **kw):
            if str(self).replace("\\", "/").endswith("keynote.md"):
                raise AssertionError(f"keynote.md 被 write_bytes: {self}")
            return real_wb(self, *a, **kw)

        monkeypatch.setattr(builtins, "open", guarded_open)
        monkeypatch.setattr(pathlib.Path, "write_text", guarded_wt)
        monkeypatch.setattr(pathlib.Path, "write_bytes", guarded_wb)


# ============================================================
# 取证一（静态）：生产代码不存在任何写 keynote.md 的路径
# ============================================================
class TestStaticNoKeynoteWriter:
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 引用 "keynote.md" 字面量的生产文件白名单（新增触碰者直接 fail，强制评审）
    KEYNOTE_TOUCHERS = {
        "_theme_guard.py",   # load_keynote（读）/ append_keynote_change（只写 decisions.md）
        "_cli_audit.py",     # A6 hash 对账（读）
        "_embed_index.py",   # A7 语料扫描（读）
        "_cli_guards.py",    # A4 pre_check WARN 文案
        "_session.py",       # keynote_change 未登记提示文案
        "_cli_cmds_qa.py",   # session-start JSON keynote 字段（只增不改）
        "_domain_guard.py",  # A5 线集合核对文案
        "_memory_guard.py",  # 条目类型常量
    }
    _WRITE_RE = re.compile(r"write_text|write_bytes|\.write\(|open\([^)]*['\"][wa]")

    def _prod_py_files(self):
        return [f for f in os.listdir(self.REPO_ROOT)
                if f.endswith(".py") and os.path.isfile(os.path.join(self.REPO_ROOT, f))]

    def test_keynote_mentions_confined_to_whitelist(self):
        """生产代码里凡出现 'keynote.md' 字面量的文件必须在白名单内。"""
        touchers = set()
        for fname in self._prod_py_files():
            with open(os.path.join(self.REPO_ROOT, fname), "r", encoding="utf-8") as f:
                if "keynote.md" in f.read():
                    touchers.add(fname)
        assert touchers <= self.KEYNOTE_TOUCHERS, \
            f"新文件触碰 keynote.md，须评审是否引入写入路径: {touchers - self.KEYNOTE_TOUCHERS}"

    def test_no_write_primitive_on_keynote_lines(self):
        """所有含 keynote 路径表达式的行不得带写原语（write_text/write_bytes/.write(/open w|a）。"""
        offenders = []
        for fname in self._prod_py_files():
            with open(os.path.join(self.REPO_ROOT, fname), "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f.readlines(), 1):
                    if re.search(r'keynote|kn_path|kn\[', line) and self._WRITE_RE.search(line):
                        offenders.append(f"{fname}:{lineno}: {line.strip()}")
        assert offenders == [], "发现疑似 keynote.md 写入路径：\n" + "\n".join(offenders)

    def test_keynote_opens_are_read_mode(self):
        """白名单文件内 open(kn_path/path 指向 keynote) 必须读模式。"""
        opens = []
        for fname in ("_theme_guard.py", "_cli_audit.py", "_embed_index.py"):
            with open(os.path.join(self.REPO_ROOT, fname), "r", encoding="utf-8") as f:
                src = f.read()
            # 定位 keynote 路径变量名 -> 检查以其为实参的 open() 调用模式
            for m in re.finditer(r'open\((kn_path|path|kn\["path"\])\s*(?:,\s*["\'](\w+)["\'])?', src):
                mode = m.group(2) or "r"
                opens.append((fname, m.group(0), mode))
                assert all(c in "rb+" and c not in "wax+" for c in mode), \
                    f"{fname}: open({m.group(1)}, '{mode}') 不是读模式"
        assert len(opens) >= 3, "三个读取点（load_keynote/audit/embed）均应被捕获"


# ============================================================
# 取证二（行为·golden 场景）：材料暗示权重变化 → 全链零改写
# ============================================================
class TestKeynoteImmutableGoldenScenario:
    def test_material_hint_triggers_conflict_but_never_rewrites(self, tmp_path, monkeypatch):
        clients, cdir = _make_client(tmp_path, monkeypatch)
        kn_before = (cdir / "keynote.md").read_bytes()
        sha_before = _sha256_bytes(kn_before)

        kn = _theme_guard.load_keynote(CLIENT)
        assert kn["lines"][2]["name"] == "研发支撑线" and kn["lines"][2]["order"] == "三期"

        # ---- 提示层：材料暗示与 LLM 顺从产出均触发冲突并列提示 ----
        for text in (NEW_MATERIAL_HINT, LLM_BIASED_OUTPUT):
            warns = _domain_guard.check_keynote_lines(text, kn)
            conflict = [w for w in warns if "研发支撑线" in w and "先后冲突" in w]
            assert conflict, f"材料暗示未触发冲突提示: {text!r}"
            # 冲突并列：keynote 声明（三期）与产出伴随（一期）同现于提示文本
            assert "三期" in conflict[0] and "一期" in conflict[0]
            suffix = _domain_guard.keynote_observe_for_text(text, client_name=CLIENT)
            assert suffix.startswith(" | keynote: ") and "研发支撑线" in suffix

        # TAIL 自检层：权重基准自检项在位
        tail = _theme_guard.build_tail_checklist([], keynote=kn)
        assert "线间权重符合基调卡" in tail

        # ---- 写哨兵下跑完整链：读侧/生成前/verify/save/人批事件路径 ----
        _WriteSentinel(monkeypatch)
        monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
        monkeypatch.setattr(_session, "recall", lambda *a, **kw: [])
        import _context, _aliases, _embed_index
        monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
        monkeypatch.setattr(_embed_index, "build_embedding_index", lambda *a, **kw: {})
        monkeypatch.setattr(_session, "_sync_bm25_if_stale", lambda *a, **kw: {})
        monkeypatch.setattr(_session, "build_client_graph", lambda *a, **kw: {})
        monkeypatch.setattr(_session, "_extract_case_cards", lambda *a, **kw: {})
        monkeypatch.setattr(_session, "update_outputs_index", lambda *a, **kw: {})

        # ① session-start 读侧（材料暗示作为输入）：HEAD keynote 段最前，keynote 只读
        r = _session.auto_for_input(NEW_MATERIAL_HINT, client_name=CLIENT)
        assert r["head_context"].startswith("=== 基调基准 keynote.md@v1")
        assert "研发支撑线(主线·三期)" in r["head_context"]  # 权重基准仍是人批版本
        assert r["keynote"]["version"] == "v1"

        # ② 生成前 pre_check（keynote 存在 -> 无「未定基调」WARN，且不写 keynote）
        assert _cli_guards.keynote_pre_check_warn(CLIENT) is None

        # ③ save 链：即使 decisions 里带 AI 擅自结论，也只落 decisions.md task 条目
        assert _session.save_session(
            CLIENT, input_desc=NEW_MATERIAL_HINT,
            decisions="AI 擅自结论：研发支撑线提前到一期（未经人确认）",
            dsh_session="sess-d1") is True
        dec_text = (cdir / "decisions.md").read_text(encoding="utf-8")
        assert "AI 擅自结论" in dec_text                    # 会话决策正常入档
        assert dec_text.count("**type: keynote_change**") == 1  # 只有初始登记那条
        assert "研发支撑线提前到一期" not in dec_text.split("**type: keynote_change**")[0]

        # ④ 人批事件路径（append_keynote_change）：也只写 decisions.md，不碰 keynote.md
        assert _theme_guard.append_keynote_change(
            CLIENT, "v1 复核：维持原权重", approver="用户",
            conflict_note="新材料暗示研发支撑线提前，与 v1 冲突，并列挂待确认",
            session_ref="sess-d1b") is not None
        dec_text = (cdir / "decisions.md").read_text(encoding="utf-8")
        assert "冲突并列: 新材料暗示研发支撑线提前" in dec_text

        # ---- 终局断言：keynote.md 字节不动 ----
        kn_after = (cdir / "keynote.md").read_bytes()
        assert kn_after == kn_before, "keynote.md 未经人确认被改写"
        assert _sha256_bytes(kn_after) == sha_before

    def test_audit_hash_consistent_after_scenario(self, tmp_path, monkeypatch, capsys):
        """A6 对账兜底：场景跑完后 hash 对账无「基调被改」警告。"""
        clients, cdir = _make_client(tmp_path, monkeypatch)
        assert _audit_keynote_hash(clients_dir=str(clients)) is True
        out = capsys.readouterr().out
        assert "对账一致" in out and "基调被改" not in out

    def test_material_hint_alone_cannot_register_change(self, tmp_path, monkeypatch):
        """仅靠材料暗示（无 append_keynote_change 调用）不会产生 keynote_change 事件。"""
        clients, cdir = _make_client(tmp_path, monkeypatch)
        kn = _theme_guard.load_keynote(CLIENT)
        # 模拟「AI 读到暗示但什么都没做」：只有检测层在跑
        _domain_guard.check_keynote_lines(NEW_MATERIAL_HINT, kn)
        _theme_guard.pre_check(CLIENT)
        dec_text = (cdir / "decisions.md").read_text(encoding="utf-8")
        assert dec_text.count("**type: keynote_change**") == 1  # 仅初始登记，无新增事件


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
