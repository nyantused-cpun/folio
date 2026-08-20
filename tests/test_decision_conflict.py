# -*- coding: utf-8 -*-
"""save_decision 溯源 + 冲突保留（P0 · T3）测试。

全部用 tmp_path 造假客户目录，绝不读写真实 _knowledge/ 客户目录。
monkeypatch 只改 _theme_guard.CLIENTS_DIR（模块级常量），不碰 _paths 真实常量。
"""

import pytest

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
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    _theme_guard.save_decision("测试客户", "报价口径", "100万")
    content = _read(client_dir)
    assert content.count("## [") == 2  # 正常追加，不覆盖
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
    # pending 的旧块（100万）被跳过，只加载新块（200万）
    assert len(themes) == 1
    assert "200万" in themes[0]["impact"]
    assert _theme_guard.count_skipped_conflicts() == 1


def test_load_no_pending_normal(client_dir):
    _theme_guard.save_decision("测试客户", "报价口径", "100万", persistence="permanent")
    themes = _theme_guard.load_active_themes("测试客户", only_permanent=True)
    assert len(themes) == 1
    assert _theme_guard.count_skipped_conflicts() == 0


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
