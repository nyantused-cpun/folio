# -*- coding: utf-8 -*-
"""#49③/D4 preferences 机器链：save 从偏好类决策自动摘要维护 preferences.md。

tmp 隔离（同 test_session_upsert 基座口径），重副作用全桩。
历史回填批不在本链（需用户确认，另行拍板）。
"""
import _session
import _context


def _setup(tmp_path, monkeypatch):
    import _aliases
    import _theme_guard

    clients = tmp_path / "clients"
    clients.mkdir()
    monkeypatch.setattr(_context, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_aliases, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_theme_guard, "CLIENTS_DIR", str(clients))
    monkeypatch.setattr(_session, "TASK_HISTORY", str(tmp_path / "task_history.json"))
    monkeypatch.setattr(_session, "update_outputs_index", lambda *a, **kw: 0)
    return clients


def _read_pref(clients, name="测试客户P"):
    return (clients / name / "preferences.md").read_text(encoding="utf-8")


def test_save_preference_decision_creates_preferences(tmp_path, monkeypatch):
    clients = _setup(tmp_path, monkeypatch)
    assert _session.save_session(
        "测试客户P", input_desc="定风格",
        decisions="方案页面用深色主题；客户喜欢简洁图表",
        light=True) is True
    text = _read_pref(clients)
    assert "# 客户偏好" in text and "## 偏好记录" in text  # 最小骨架
    assert "方案页面用深色主题" in text
    assert "客户喜欢简洁图表" in text
    assert text.count("## 偏好记录") == 1


def test_second_save_same_entry_not_duplicated(tmp_path, monkeypatch):
    clients = _setup(tmp_path, monkeypatch)
    decision = "用户偏好深色主题"
    assert _session.save_session("测试客户P", decisions=decision, light=True) is True
    assert _session.save_session("测试客户P", decisions=decision, light=True) is True
    text = _read_pref(clients)
    assert text.count("- 用户偏好深色主题") == 1


def test_non_preference_decision_no_file(tmp_path, monkeypatch):
    clients = _setup(tmp_path, monkeypatch)
    assert _session.save_session(
        "测试客户P", decisions="报价口径含税；交付周期 6 周", light=True) is True
    assert not (clients / "测试客户P" / "preferences.md").exists()


def test_keyword_match_semantics(tmp_path, monkeypatch):
    """保守匹配口径：命中关键词的条目收，纯业务条目不收。"""
    hits = _session._extract_preference_entries(
        "禁用红色标注；字体用思源黑体；对客户称谓用「您」；交期 6 周")
    assert hits == ["禁用红色标注", "字体用思源黑体", "对客户称谓用「您」"]
    assert _session._extract_preference_entries("") == []


def test_meta_record_lines_filtered(tmp_path, monkeypatch):
    """S5 遗留根治（P3-9①）：四要素纪要元记录整行跳过，不误当客户偏好。

    实锤案例：调试纪要行因「[红色]」命中「色」被收进 preferences.md——
    行内含 ①-⑤ 要素标号即判元记录（存量合法偏好条目无一使用这些标记）。
    """
    debug_note = ("本机Excel16 COM对WPS源拒收,GUI路径可加载,判定多因子WPS写包污染,"
                  "③最终修法(用户拍板'保留数据Excel重建')=openpyxl提取全量模型,"
                  "④坑=[Red]中文版Excel须写[红色](locale 2052)")
    assert _session._extract_preference_entries(debug_note) == []
    # 四要素标签词整行跳过
    assert _session._extract_preference_entries("②对话过程要点：探讨过深色与浅色两种方向") == []
    # 合法偏好不受影响（含「色」但无元记录标记）
    assert _session._extract_preference_entries(
        "主题色用企业蓝 #1E5BB8（决策 13）") == ["主题色用企业蓝 #1E5BB8（决策 13）"]
