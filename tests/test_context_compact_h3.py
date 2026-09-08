# -*- coding: utf-8 -*-
"""P0-1 回归：compact 切分正则行首锚定（H3 会话块错切修复）。

旧实现 `(?=## \\[日期])` 无行首锚定，H3 会话标题 `### [日期]` 中的 `## [` 子串
会把前一块在标题处误切、且块头丢一个 `#`（H3 降级 H2）；header_end 用
find("## [") 会命中模板尾注里的示例字样。修复后与 _session._upsert_session_block
同源（`(?m)^#{2,3} \\[日期]`）。
"""
import _context
import _session

HEADER = """# 项目上下文记录

## 项目基础信息
- 客户名称: 测试客户

## 会话历史

（每次会话结束后自动追加一条）

---
> 会话结束标记格式：## [2026-01-01] 第 0 次会话

"""


def _session_block(date, num, dsh_id=None):
    marker = f"\n<!-- dsh:session:{dsh_id} -->\n" if dsh_id else "\n"
    return (
        f"### [{date}] 第 {num} 次会话\n"
        f"{marker}"
        f"#### 本次输入\n输入{num}\n"
        f"#### 关键决策\n决策{num}\n"
        f"#### 待办 / 下次要做的\n待办{num}\n\n"
    )


def _make_client(monkeypatch, tmp_path, content, name="测试客户"):
    clients = tmp_path / "clients"
    (clients / name).mkdir(parents=True)
    ctx = clients / name / "context.md"
    ctx.write_text(content, encoding="utf-8")
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    return ctx


def test_compact_h3_roundtrip_keeps_blocks(monkeypatch, tmp_path):
    """H3 多块 compact 往返：编号保持、标记保持、无 H1 突变、尾注保留。"""
    content = HEADER + "".join(
        _session_block(f"2026-08-0{i}", i, f"s-{i}") for i in range(1, 5))
    ctx = _make_client(monkeypatch, tmp_path, content)

    _context.compact("测试客户", keep_last=1)

    new = ctx.read_text(encoding="utf-8")
    # 保留块原样：H3 级别不降级、会话编号保持、upsert 标记保持
    assert "### [2026-08-04] 第 4 次会话" in new
    assert "<!-- dsh:session:s-4 -->" in new
    assert "输入4" in new and "待办4" in new
    # 无 H1 突变（首行项目标题除外）
    for line in new.splitlines():
        if line == "# 项目上下文记录":
            continue
        assert not line.startswith("# "), f"H1 突变: {line!r}"
    # 摘要覆盖第 1 ~ 3 次
    assert "第 1 ~ 3 次会话" in new
    # 模板尾注不被当 header_end：头区尾注保留在文件里
    assert "会话结束标记格式" in new
    # 被压缩块不再以完整块形式存在
    assert "### [2026-08-02] 第 2 次会话" not in new
    assert (str(ctx) + ".bak").endswith(".bak")


def test_compact_mixed_h2_h3_levels_preserved(monkeypatch, tmp_path):
    """旧 compact 格式（## [日期]）与新格式（### [日期]）混排时各自级别保持。"""
    content = (
        HEADER
        + "## [2026-08-01] 第 1 次会话\n#### 本次输入\n输入1\n\n"
        + _session_block("2026-08-02", 2)
        + _session_block("2026-08-03", 3)
    )
    ctx = _make_client(monkeypatch, tmp_path, content)

    _context.compact("测试客户", keep_last=2)

    new = ctx.read_text(encoding="utf-8")
    assert "第 1 ~ 1 次会话" in new          # 第 1 次进摘要
    assert "## [2026-08-01] 第 1 次会话" not in new
    assert "### [2026-08-02] 第 2 次会话" in new   # H3 不被切成 H2
    assert "### [2026-08-03] 第 3 次会话" in new


def test_compact_roundtrip_upsert_still_hits_marker(monkeypatch, tmp_path):
    """compact 后同 ID 会话 upsert 仍命中标记（与 save 链路闭环）。"""
    content = HEADER + _session_block("2026-08-01", 1) + \
        _session_block("2026-08-02", 2, "sess-9")
    _make_client(monkeypatch, tmp_path, content)

    _context.compact("测试客户", keep_last=1)

    new = (tmp_path / "clients" / "测试客户" / "context.md").read_text(encoding="utf-8")
    entry = _session._build_session_entry(
        "2026-08-02", 2, "新输入", "新决策", "x.md", "(未记录)", [], "sess-9")
    new_content, replaced, old_head = _session._upsert_session_block(new, entry, "sess-9")
    assert replaced is True
    assert old_head == ("2026-08-02", 2)
    assert "新输入" in new_content
