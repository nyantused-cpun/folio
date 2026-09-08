# -*- coding: utf-8 -*-
"""save_decision 溯源 + 冲突保留（P0 · T3）测试。

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
monkeypatch 只改 _theme_guard.CLIENTS_DIR（模块级常量），不碰 _paths 真实常量。
"""

import pytest

import _memory_guard
import _theme_guard


@pytest.fixture
def client_dir(tmp_path, monkeypatch):
    """把 _theme_guard 用的 CLIENTS_DIR 指到 tmp，隔离真实客户目录。"""
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(tmp_path))
    return tmp_path


def _read(client_dir, name="测试客户"):
    return (client_dir / name / "decisions.md").read_text(encoding="utf-8")


# ============================================================
# 1. 冲突触发 / 2. 幂等
# ============================================================
def test_conflict_two_entries_coexist(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    content = _read(client_dir)
    # 两条并存（旧正文不删不改）
    assert content.count("## [") == 2
    assert "100万" in content
    assert "200万" in content
    # 旧块有 pending 标记
    assert "<!-- conflict: pending -->" in content
    # 新条目有 ⚠️ 冲突行
    assert "⚠️ 冲突" in content
    assert "待人工裁决" in content


def test_idempotent_same_content_no_conflict(client_dir):
    """W1-3 后：同日同题同内容不再追加第二块，而是归并为「复发」行（防灌水）。"""
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    content = _read(client_dir)
    assert content.count("## [") == 1  # 单块不膨胀（原为追加两块）
    assert "- **复发**: 第 2 次（" in content
    assert "<!-- conflict: pending -->" not in content
    assert "⚠️ 冲突" not in content


# ============================================================
# 3. resolve_conflict 两个方向 + 无未决冲突
# ============================================================
def test_resolve_keep_old(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "old")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "<!-- conflict: pending -->" not in content  # pending 已清
    assert "已废弃" in content  # 新条目（200万）标已废弃
    assert "100万" in content  # 旧条目正文保留


def test_resolve_keep_new(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "new")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "<!-- conflict: pending -->" not in content
    assert "冲突已裁决" in content  # 新条目标生效
    assert "已废弃" in content  # 旧条目标已废弃


def test_resolve_no_pending(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "new")
    assert r["resolved"] is False
    assert r["detail"] == "无未决冲突"


def test_resolve_neutralizes_stale_wording(client_dir):
    """裁决后「待人工裁决」措辞必须被中性化——标记语义跟随状态走（监工修正回归）。"""
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "old")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "待人工裁决" not in content  # 过期裁决措辞已清
    assert "已裁决" in content  # ⚠️ 行改写为已裁决



# ============================================================
# 4. load_active_themes 跳过 pending 块
# ============================================================
def test_load_skips_pending_block(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万", persistence="permanent")
    _theme_guard.save_decision("测试客户", "报价口径", "200万", persistence="permanent")
    themes = _theme_guard.load_active_themes("测试客户", only_permanent=True)
    # #61 双形态判定：冲突组两块在裁决前全部隔离（旧块 HTML 标记 + 新块 ⚠️ 行）。
    # 改前只认 HTML 标记时新块（⚠️ 行）会静默当铁律加载 = 默认站队新侧；
    # 现在裁决前两块都不进 HEAD，裁决后胜者块（标记已清）恢复加载
    assert themes == []


def test_load_no_pending_normal(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万", persistence="permanent")
    themes = _theme_guard.load_active_themes("测试客户", only_permanent=True)
    assert len(themes) == 1


# ============================================================
# 5. strict 坏来源抛 ValueError 且文件未被追加
# ============================================================
def test_strict_bad_source_raises(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    before = _read(client_dir)
    with pytest.raises(ValueError):
        _theme_guard.save_decision(
            "测试客户", "报价口径", "200万",
            source="file:__no_such_file_abc123__.html", strict=True,
        )
    after = _read(client_dir)
    assert before == after  # 什么都不落盘


# ============================================================
# 6. source=user 免校验正常写入
# ============================================================
def test_user_source_no_verification(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万", source="user:微信确认报价口径")
    content = _read(client_dir)
    assert "user:微信确认报价口径" in content
    assert "证据待核" not in content  # 免校验，无待核标记


# ============================================================
# 7. confidence / 来源行渲染正确
# ============================================================
def test_source_and_confidence_render(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万", source="user:测试", confidence=0.9)
    content = _read(client_dir)
    assert "- **来源**: user:测试" in content
    assert "- **confidence**: 0.9" in content


def test_empty_source_render_placeholder(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    content = _read(client_dir)
    assert "- **来源**: (待补)" in content
    assert "- **confidence**: 0.5" in content


# ============================================================
# 8. resolve-conflict 泛化：双形态 pending / 子串匹配 / N 块 / --list 数据面
#    （构造用直接写 decisions.md——save_decision 写不出的旧版存量形态）
# ============================================================
def _write_decisions(client_dir, text, name="测试客户"):
    """直接写入 decisions.md，构造旧版写入产物（只有 ⚠️ 行、无 HTML 标记）等形态。"""
    d = client_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "decisions.md").write_text(text, encoding="utf-8")


def _legacy_conflict_md(topic="报价口径", old_decision="100万", new_decision="200万"):
    """两块同主题、只有 ⚠️ 冲突行、无 HTML 标记的旧版存量形态（示例集团实弹同款）。"""
    return (
        "# 测试客户 决策记录\n"
        f"## [2026-09-01] {topic}\n"
        f"- **决策**: {old_decision}\n"
        "- **理由**: (未记录)\n"
        "- **persistence: permanent**\n"
        f"- **⚠️ 冲突**: 与 [2026-08-01] 同主题条目矛盾，待人工裁决（resolve-conflict）\n"
        f"## [2026-09-05] {topic}\n"
        f"- **决策**: {new_decision}\n"
        "- **理由**: (未记录)\n"
        "- **persistence: permanent**\n"
        f"- **⚠️ 冲突**: 与 [2026-09-01] 同主题条目矛盾，待人工裁决（resolve-conflict）\n"
    )


def test_list_conflicts_detects_warning_only_blocks(client_dir):
    """①前半：无 HTML 标记只有 ⚠️ 行的两块 -> 判为未决（旧版存量不再漏检）。"""
    _write_decisions(client_dir, _legacy_conflict_md())
    content = _read(client_dir)
    assert "<!-- conflict: pending -->" not in content  # 存量形态本就无 HTML 标记
    groups = _theme_guard.list_conflicts("测试客户")
    assert len(groups) == 1
    assert groups[0]["topic"] == "报价口径"
    assert groups[0]["dates"] == ["2026-09-01", "2026-09-05"]
    assert groups[0]["pending_blocks"] == 2


def test_resolve_legacy_warning_only_keep_old(client_dir):
    """①后半：存量两块 keep=old 裁决 -> 最早块胜，全文无「待人工裁决」残留。"""
    _write_decisions(client_dir, _legacy_conflict_md())
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "old")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "待人工裁决" not in content  # 裁决后任何块不得残留
    assert "**⚠️ 冲突**" not in content  # ⚠️ 标记同步清理（防再判未决）
    assert "<!-- conflict: pending -->" not in content
    assert "100万" in content  # 旧条目正文保留
    assert content.count("- **状态**: 已废弃") == 1
    assert "- **状态**: 冲突已裁决（本条保留，其余 1 条已废弃）" in content


def test_resolve_legacy_warning_only_keep_new(client_dir):
    """①后半：存量两块 keep=new 裁决 -> 最晚块胜，双形态标记清零。"""
    _write_decisions(client_dir, _legacy_conflict_md())
    r = _theme_guard.resolve_conflict("测试客户", "报价口径", "new")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "待人工裁决" not in content
    assert "**⚠️ 冲突**" not in content
    assert "200万" in content  # 新条目生效
    assert content.count("- **状态**: 已废弃") == 1
    assert "- **状态**: 冲突已裁决（本条生效，其余 1 条已废弃）" in content


def test_resolve_three_blocks_keep_both_directions(client_dir):
    """②三块同主题：old/new 两路胜者正确、其余全废弃、pending 清零。"""
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    _theme_guard.save_decision("测试客户", "报价口径", "300万")
    assert _read(client_dir).count("## [") == 3

    r_old = _theme_guard.resolve_conflict("测试客户", "报价口径", "old")
    assert r_old["resolved"] is True
    content = _read(client_dir)
    assert "100万" in content  # 最早块胜
    assert "待人工裁决" not in content
    assert "<!-- conflict: pending -->" not in content
    assert "**⚠️ 冲突**" not in content  # pending 清零（含中间块）
    assert content.count("- **状态**: 已废弃") == 2  # 中间块+最晚块全废弃
    assert "- **状态**: 冲突已裁决（本条保留，其余 2 条已废弃）" in content

    # 重建后测 keep=new（互不污染：重新生成三块）
    _write_decisions(client_dir, "# 测试客户 决策记录\n")
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "200万")
    _theme_guard.save_decision("测试客户", "报价口径", "300万")
    r_new = _theme_guard.resolve_conflict("测试客户", "报价口径", "new")
    assert r_new["resolved"] is True
    content = _read(client_dir)
    assert "300万" in content  # 最晚块胜
    assert "待人工裁决" not in content
    assert "<!-- conflict: pending -->" not in content
    assert "**⚠️ 冲突**" not in content
    assert content.count("- **状态**: 已废弃") == 2  # 最早块+中间块全废弃
    assert "- **状态**: 冲突已裁决（本条生效，其余 2 条已废弃）" in content


def test_resolve_substring_unique_match(client_dir):
    """③子串唯一命中：长主题传短串即可裁决（全串 CLI 传参几乎不可用）。"""
    long_topic = ("二期19套系统名录与中文名（2026-09-06 最新拍板，覆盖决策18/21口径）："
                  "企业资源计划系统二期、文档系统二期、档案系统二期等")
    _theme_guard.save_decision("测试客户", long_topic, "口径A")
    _theme_guard.save_decision("测试客户", long_topic, "口径B")
    r = _theme_guard.resolve_conflict("测试客户", "二期19套系统名录", "new")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "口径B" in content
    assert "待人工裁决" not in content
    assert "**⚠️ 冲突**" not in content


def test_resolve_substring_ambiguous_lists_candidates(client_dir):
    """④子串多义：resolved False + 候选主题列表（截断 40 字）。"""
    _theme_guard.save_decision("测试客户", "缓存策略：本地缓存优先", "A")
    _theme_guard.save_decision("测试客户", "缓存策略：分布式缓存优先", "B")
    r = _theme_guard.resolve_conflict("测试客户", "缓存策略", "old")
    assert r["resolved"] is False
    assert "缓存策略：本地缓存优先" in r["detail"]
    assert "缓存策略：分布式缓存优先" in r["detail"]


def test_resolve_topic_not_found(client_dir):
    """子串 0 命中：报无此主题（区别于「无未决冲突」）。"""
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    r = _theme_guard.resolve_conflict("测试客户", "交付范围", "old")
    assert r["resolved"] is False
    assert "无此主题" in r["detail"]


def test_resolve_missing_topic(client_dir):
    """--topic 缺失（argparse 放开 required 后的运行时防线）：明确报错。"""
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    r = _theme_guard.resolve_conflict("测试客户", None, "old")
    assert r["resolved"] is False
    assert "缺少主题" in r["detail"]


def test_resolve_orphan_single_pending_block(client_dir):
    """孤儿单块：对侧条目已被清理、仅剩 1 块带 ⚠️ 行（示例集团存量实态）——可裁决清标记。"""
    _write_decisions(
        client_dir,
        "# 测试客户 决策记录\n"
        "## [2026-09-06] 会话决策 2026-09-06 #第8次\n"
        "- **决策**: 四要素纪要\n"
        "- **persistence: task**\n"
        "- **⚠️ 冲突**: 与 [2026-09-06] 同主题条目矛盾，待人工裁决（resolve-conflict）\n",
    )
    groups = _theme_guard.list_conflicts("测试客户")
    assert len(groups) == 1
    assert groups[0]["pending_blocks"] == 1
    r = _theme_guard.resolve_conflict("测试客户", "#第8次", "new")
    assert r["resolved"] is True
    content = _read(client_dir)
    assert "待人工裁决" not in content
    assert "**⚠️ 冲突**" not in content
    assert "- **状态**: 冲突已裁决（本条生效）" in content
    assert "已废弃" not in content  # 无对侧块，无败方


def test_list_conflicts_mixed_shapes(client_dir):
    """⑤混合形态分组：有/无 HTML 标记、task/permanent 混排，clean 组不列。"""
    # a) 旧版存量双块（仅 ⚠️ 行，permanent）
    _write_decisions(client_dir, _legacy_conflict_md(topic="报价口径"))
    # b) 现版 save_decision 双块（HTML 标记 + ⚠️ 行，task）
    _theme_guard.save_decision("测试客户", "交付范围", "仅二期", persistence="task")
    _theme_guard.save_decision("测试客户", "交付范围", "二期+一期", persistence="task")
    # c) 单块 clean（permanent）——不列
    _theme_guard.save_decision("测试客户", "架构风格", "KPMG v3", persistence="permanent")
    # d) 双块 clean 同主题（手工构造，无任何标记）——不列
    #    （save_decision 的 entry 不带尾换行，追加块前必须补 \n 防标题行粘连）
    with open(client_dir / "测试客户" / "decisions.md", "a", encoding="utf-8") as f:
        f.write(
            "\n## [2026-09-02] 图表规范\n- **决策**: 不带图例\n- **persistence: task**\n"
            "## [2026-09-03] 图表规范\n- **决策**: 带图例\n- **persistence: task**\n")

    groups = _theme_guard.list_conflicts("测试客户")
    assert len(groups) == 2
    by_topic = {g["topic"]: g for g in groups}
    assert by_topic["报价口径"]["pending_blocks"] == 2  # 仅 ⚠️ 行形态
    assert by_topic["报价口径"]["dates"] == ["2026-09-01", "2026-09-05"]
    assert by_topic["交付范围"]["pending_blocks"] == 2  # HTML + ⚠️ 形态
    assert "架构风格" not in by_topic  # 单块 clean 不列
    assert "图表规范" not in by_topic  # 多块但无未决不列
    assert _theme_guard.list_conflicts("不存在的客户") == []  # 只读，缺文件返回空


# ============================================================
# 9. 双形态判定单一事实源对齐（#61）：count_pending_conflicts / load_active_themes
#    判定真源 = _memory_guard._block_has_pending_conflict，_theme_guard 薄委托；
#    改造前两处消费点只认 HTML 标记，「⚠️ 行孤儿块」计 0 / 被当铁律加载。
# ============================================================
def test_count_pending_counts_warning_only_blocks(client_dir):
    """①只有 ⚠️ 行、无 HTML 标记的存量块被 count_pending_conflicts 计数。

    示例集团实弹：改前按标记出现次数计 0（健康线「冲突未决 N 条」失真），
    改后按决策块双形态判定计 2。
    """
    _write_decisions(client_dir, _legacy_conflict_md())
    p = str(client_dir / "测试客户" / "decisions.md")
    assert "<!-- conflict: pending -->" not in _read(client_dir)  # 存量形态本就无 HTML 标记
    assert _memory_guard.count_pending_conflicts(p) == 2


def test_warning_only_block_not_loaded_as_theme(client_dir):
    """②只有 ⚠️ 行的块不被 load_active_themes 当铁律加载（改前会双载 HEAD）。"""
    _write_decisions(client_dir, _legacy_conflict_md())
    themes = _theme_guard.load_active_themes("测试客户", only_permanent=True)
    assert themes == []  # 两块均未决，全部跳过


def test_html_marker_form_behavior_unchanged(client_dir):
    """③HTML 标记形态行为不变：照常计数、照常跳过（对齐改造前语义）。"""
    _write_decisions(
        client_dir,
        "# 测试客户 决策记录\n"
        "## [2026-09-01] 报价口径\n- **决策**: 100万\n<!-- conflict: pending -->\n"
        "## [2026-09-02] 交付范围\n- **决策**: 仅二期\n<!-- conflict: pending -->\n"
        "## [2026-09-03] 架构风格\n- **决策**: KPMG v3\n",
    )
    p = str(client_dir / "测试客户" / "decisions.md")
    assert _memory_guard.count_pending_conflicts(p) == 2  # 每块 1 标记 = 2 块未决
    themes = _theme_guard.load_active_themes("测试客户", only_permanent=True)
    assert len(themes) == 1  # 只加载干净块
    assert "KPMG v3" in themes[0]["impact"]


def test_dual_form_single_source_consistency():
    """④共享 helper 两形态一致性：_theme_guard._block_is_pending 与
    _memory_guard._block_has_pending_conflict 对各形态同判（防两处漂移）。"""
    cases = [
        # HTML 标记形态
        ("<!-- conflict: pending -->", True),
        # ⚠️ 行形态（旧版存量，示例集团实弹同款）
        ("- **⚠️ 冲突**: 与 [2026-09-06] 同主题条目矛盾，待人工裁决（resolve-conflict）", True),
        # 双形态同块
        ("x\n<!-- conflict: pending -->\n- **⚠️ 冲突**: 矛盾", True),
        # 干净块
        ("## [2026-09-01] 甲\n- **决策**: A\n", False),
        # 裁决后中性化产物（「冲突裁决」行）不回判未决
        ("- **冲突裁决**: 与 [2026-09-06] 同主题条目矛盾，已裁决\n", False),
        ("", False),
    ]
    for text, expected in cases:
        assert _theme_guard._block_is_pending(text) == expected, repr(text[:30])
        assert _memory_guard._block_has_pending_conflict(text) == expected, repr(text[:30])
