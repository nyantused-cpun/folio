# -*- coding: utf-8 -*-
"""P3「审计/质量」组 9 项修复回归（全库审查报告 2026-09-06 §五）。

覆盖清单：
  1  _review._parse_review_json 顶层数组 fail-closed（曾 AttributeError 逃逸、不写 review_log）
  2  _verify_hook.update_task_history 锁失败 stderr 告警留痕（曾静默放弃写 task_history）
  3  _verify_hook._main 按验证结果透传 exit code（曾恒 exit 0）
  4  _spec_edit.add_element 负索引拒绝（与 update/delete_element 越界口径统一）
  5  _verify_checks.check_question_binding Q 编号边界（Q1 不被 Q12 顶替）
  6  _domain_guard DB-02 fit 词边界（benefit/profit 不再误报）
  7  _cli_audit._audit_output_provenance verify 非 dict 类型守卫 + WARN（曾崩掉 audit）
  8  _cli_audit._audit_anti_regeneration diagram 计数逐文件核销（陈旧数字不再被集合归属掩盖）
  9  _style_guard 词库 re.escape + _verify.verify_html style 扫描异常告警留痕（不再静默停用）
"""
import json
import os

import pytest

import _paths
import _review
import _save_lock
import _style_guard
import _verify
import _verify_checks
import _verify_hook


# ===========================================================================
# 1. review JSON 数组 fail-closed
# ===========================================================================

def test_parse_review_json_rejects_top_level_array():
    """顶层数组/标量视为解析失败（raise JSONDecodeError），dict 正常解析不回归。"""
    with pytest.raises(json.JSONDecodeError):
        _review._parse_review_json('["verdict", "PASS", "issues", []]')
    with pytest.raises(json.JSONDecodeError):
        _review._parse_review_json('"PASS"')
    assert _review._parse_review_json('{"verdict": "PASS"}') == {"verdict": "PASS"}


def test_review_llm_array_fail_closed_and_log_written(tmp_path, monkeypatch):
    """review() 收到 JSON 数组 → FAIL 路径 + review_log 落盘（fail-closed 防线不削弱）。"""
    import _cloud_llm

    out = tmp_path / "产出.html"
    out.write_text("<!DOCTYPE html><html><body>" + "正文内容。" * 200
                   + "</body></html>", encoding="utf-8")
    monkeypatch.setattr(_cloud_llm, "chat",
                        lambda **kw: '["整体不错", "问题不多", "可以交付"]')
    log_path = tmp_path / "review_log.json"
    monkeypatch.setattr(_paths, "REVIEW_LOG", str(log_path))

    result = _review.review(str(out), client_name=None, spec_path=None, quiet=True)

    assert result["verdict"] == "FAIL"
    assert any("解析失败" in i for i in result["issues"])
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert entries[-1]["verdict"] == "FAIL"


def test_review_dimension_array_returns_error_not_escape(monkeypatch):
    """并行维度路收到 JSON 数组 → 记 error，不抛 AttributeError 逃逸线程池。"""
    import _cloud_llm

    monkeypatch.setattr(_cloud_llm, "chat", lambda **kw: '["铁律未覆盖，逐条缺失"]')
    ctx = {"themes_text": "无", "spec_summary": "无", "output_text": "正文"}
    r = _review._review_dimension(_review._PARALLEL_DIMENSIONS[0], ctx)
    assert "error" in r and "非 JSON" in r["error"]


# ===========================================================================
# 2. verify_hook 锁失败 stderr 留痕
# ===========================================================================

def test_update_task_history_client_lock_failure_warns_stderr(
        tmp_path, monkeypatch, capsys):
    """客户保存锁获取失败：仍降级跳过，但 stderr 留中文告警。"""
    monkeypatch.setattr(_verify_hook, "CLIENTS_DIR", str(tmp_path / "clients"))
    monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(_verify_hook, "TASK_HISTORY",
                        str(tmp_path / "logs" / "task_history.json"))
    monkeypatch.setattr(_save_lock, "acquire_save_lock", lambda *a, **kw: None)

    _verify_hook.update_task_history(str(tmp_path / "产出.html"), True, "html",
                                     client_name="测试客户")

    err = capsys.readouterr().err
    assert "[warn]" in err and "保存锁获取失败" in err and "task_history" in err
    assert not os.path.exists(tmp_path / "logs" / "task_history.json")


def test_update_task_history_global_lock_failure_warns_stderr(
        tmp_path, monkeypatch, capsys):
    """全局 task_history 锁获取失败：同样 stderr 留痕。"""
    monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(_verify_hook, "TASK_HISTORY",
                        str(tmp_path / "logs" / "task_history.json"))
    monkeypatch.setattr(_save_lock, "acquire_save_lock", lambda *a, **kw: None)

    _verify_hook.update_task_history(str(tmp_path / "产出.html"), True, "html")

    err = capsys.readouterr().err
    assert "[warn]" in err and "全局锁" in err


# ===========================================================================
# 3. verify_hook exit code 透传
# ===========================================================================

def test_main_exit_code_follows_run_single(monkeypatch):
    monkeypatch.setattr(_verify_hook, "write_log", lambda msg: None)
    monkeypatch.setattr(_verify_hook, "run_single", lambda path, **kw: False)
    assert _verify_hook._main(["prog", "x.html"]) == 1
    monkeypatch.setattr(_verify_hook, "run_single", lambda path, **kw: True)
    assert _verify_hook._main(["prog", "x.html"]) == 0


def test_main_all_mode_exit_code_follows_run_all(monkeypatch):
    monkeypatch.setattr(_verify_hook, "write_log", lambda msg: None)
    seen = {}

    def fake_run_all(paths):
        seen.update(paths)
        return False

    monkeypatch.setattr(_verify_hook, "run_all", fake_run_all)
    assert _verify_hook._main(["prog", "--all", "a.pptx", "b.html"]) == 1
    assert seen == {"pptx": "a.pptx", "html": "b.html"}


def test_main_no_args_usage_returns_zero(capsys):
    assert _verify_hook._main(["prog"]) == 0
    assert "用法" in capsys.readouterr().out


# ===========================================================================
# 4. spec_edit add_element 负索引
# ===========================================================================

def _write_spec(tmp_path, elements):
    import yaml
    p = tmp_path / "spec.yml"
    p.write_text(
        yaml.safe_dump({"pages": [{"id": "p1", "title": "页", "elements": elements}]},
                       allow_unicode=True),
        encoding="utf-8")
    return str(p)


def test_add_element_rejects_negative_index(tmp_path):
    """负索引拒绝，与 update_element/delete_element 的越界口径一致。"""
    from _spec_edit import add_element
    spec_path = _write_spec(tmp_path, [
        {"type": "text", "content": "甲"},
        {"type": "text", "content": "乙"},
        {"type": "text", "content": "丙"},
    ])
    r = add_element(spec_path, "p1",
                    {"type": "text", "content": "丁"}, index=-1)
    assert r["ok"] is False
    assert any("负索引" in e for e in r["errors"])
    import yaml
    spec = yaml.safe_load(open(spec_path, encoding="utf-8"))
    assert len(spec["pages"][0]["elements"]) == 3  # 未被误插


def test_add_element_append_and_insert_semantics_unchanged(tmp_path):
    """回归：None 追加、正数索引插入行为不变。"""
    from _spec_edit import add_element
    import yaml
    spec_path = _write_spec(tmp_path, [{"type": "text", "content": "甲"}])
    assert add_element(spec_path, "p1",
                       {"type": "text", "content": "乙"})["ok"] is True
    assert add_element(spec_path, "p1",
                       {"type": "text", "content": "头"}, index=0)["ok"] is True
    spec = yaml.safe_load(open(spec_path, encoding="utf-8"))
    assert [e["content"] for e in spec["pages"][0]["elements"]] == ["头", "甲", "乙"]


# ===========================================================================
# 5. question 绑定 Q 编号边界
# ===========================================================================

def test_question_binding_q1_not_displaced_by_q12():
    spec = {"pages": [
        {"id": "p1", "title": "问题",
         "questions": [{"id": "Q1", "text": "现状如何"}], "elements": []},
        {"id": "p2", "title": "Q12 展望", "elements": []},
    ]}
    msgs = _verify_checks.check_question_binding(spec)
    assert any("Q1" in m and "未在后续页面" in m for m in msgs)


def test_question_binding_exact_match_still_binds():
    spec = {"pages": [
        {"id": "p1", "title": "问题",
         "questions": [{"id": "Q1", "text": "现状如何"},
                       {"id": "Q12", "text": "规划"}],
         "elements": []},
        {"id": "p2", "title": "Q1 现状 + Q12 展望",
         "elements": [{"type": "section_tag", "label": "Q1 小结"}]},
    ]}
    assert _verify_checks.check_question_binding(spec) == []


# ===========================================================================
# 6. domain guard DB-02 fit 词边界
# ===========================================================================

def test_db02_fit_word_boundary_no_false_positive():
    """benefit/profit 内含 fit 子串，不得命中 DB-02。"""
    from _domain_guard import check_domain_bans
    for text in ("客户 benefit 显著提升", "利润 profit 空间可期", "notafile 之类"):
        hits = check_domain_bans(text)
        assert not any(h["id"] == "DB-02" for h in hits), text


def test_db02_still_hits_bare_fit_and_allgreen():
    from _domain_guard import check_domain_bans
    hits = check_domain_bans("能力与现状完全 Fit，矩阵全绿")
    assert any(h["id"] == "DB-02" for h in hits)
    # 有 gap 讨论时不命中第一分支
    hits = check_domain_bans("Fit 与 gap 逐条对照")
    assert not any(h["id"] == "DB-02" for h in hits)


# ===========================================================================
# 7. output provenance verify 非 dict 类型守卫
# ===========================================================================

def test_audit_output_provenance_tolerates_dirty_verify(
        tmp_path, monkeypatch, capsys):
    """verify 值为脏数据（非 dict）时 WARN 跳过，audit 不崩，正常条目仍生效。"""
    import _cli_audit
    monkeypatch.setattr(_cli_audit, "SCRIPT_DIR", str(tmp_path))
    out_dir = tmp_path / "output" / "测试客户"
    out_dir.mkdir(parents=True)
    html = out_dir / "方案.html"
    html.write_text("<!DOCTYPE html><html></html>", encoding="utf-8")
    logs = tmp_path / ".folio" / "logs"
    logs.mkdir(parents=True)
    (logs / "task_history.json").write_text(json.dumps([
        {"date": "2026-09-06", "project": "测试客户",
         "verify": {str(html): {"ok": True}}},
        {"date": "2026-09-06", "project": "脏数据", "verify": "不是字典"},
    ], ensure_ascii=False), encoding="utf-8")

    ok = _cli_audit._audit_output_provenance()

    assert ok is True
    captured = capsys.readouterr()
    assert "非 dict 的 verify" in captured.out
    assert "溯源通过" in captured.out


# ===========================================================================
# 8. diagram 计数逐文件核销
# ===========================================================================

def _make_skill_files(tmp_path, skill_nums, graphics_nums, spec_nums):
    vc = tmp_path / ".folio" / "skills" / "visual-craft-guide"
    (vc / "references").mkdir(parents=True, exist_ok=True)
    (vc / "SKILL.md").write_text(
        f"速查：{skill_nums} 种子类型见 references。\n", encoding="utf-8")
    (vc / "references" / "graphics.md").write_text(
        f"### {graphics_nums} 种子类型全表\n", encoding="utf-8")
    sg = tmp_path / ".folio" / "skills" / "spec-writing-guide"
    sg.mkdir(parents=True, exist_ok=True)
    (sg / "SKILL.md").write_text(f"{spec_nums} 种子类型对齐。\n", encoding="utf-8")


def _fake_all_subtypes(n):
    # all_subtypes() 返回集合（audit 侧取 len），桩函数对齐返回形态
    return [f"subtype_{i}" for i in range(n)]


def test_diagram_count_stale_file_flagged(tmp_path, monkeypatch, capsys):
    """graphics.md 声明陈旧数字（31）时逐文件核销 FAIL，不再被 37 掩盖。"""
    import _cli_audit
    import _renderer.schema as schema
    monkeypatch.setattr(_cli_audit, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(schema, "all_subtypes", lambda: _fake_all_subtypes(37))
    _make_skill_files(tmp_path, 37, 31, 37)

    ok = _cli_audit._audit_anti_regeneration()

    assert ok is False
    out = capsys.readouterr().out
    assert "31" in out and "graphics.md" in out


def test_diagram_count_all_files_aligned_passes(tmp_path, monkeypatch, capsys):
    """全部文件声明一致 → 通过（消息含逐文件核销口径）。"""
    import _cli_audit
    import _renderer.schema as schema
    monkeypatch.setattr(_cli_audit, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(schema, "all_subtypes", lambda: _fake_all_subtypes(37))
    _make_skill_files(tmp_path, 37, 37, 37)

    ok = _cli_audit._audit_anti_regeneration()

    assert ok is True
    assert "逐文件核销" in capsys.readouterr().out


# ===========================================================================
# 9. style_guard 词库 re.escape + verify_html 异常留痕
# ===========================================================================

def test_antipattern_words_with_regex_metachars_escaped(tmp_path, monkeypatch):
    """反模式词含正则元字符时按字面匹配（曾直拼 pattern 炸掉整个扫描）。"""
    adir = tmp_path / "antipattern"
    adir.mkdir()
    (adir / "实战词.md").write_text("- 降本增效(新\n- 赋能+抓手\n", encoding="utf-8")
    monkeypatch.setattr(_style_guard, "ANTIPATTERN_DIR", str(adir))
    monkeypatch.setattr(_style_guard, "_ANTIPATTERN_CACHE", None)

    issues = _style_guard.check("我们要降本增效(新，同时拒绝赋能+抓手")

    names = {i["name"] for i in issues}
    assert "实战词" in names


def test_verify_html_style_scan_failure_warns_not_silent(
        tmp_path, monkeypatch, capsys):
    """style 扫描抛异常时 verify 结果不受影响，但 stderr 必须留告警。"""
    import _density

    html = tmp_path / "产出.html"
    html.write_text(
        "<!DOCTYPE html><html><head><style>body{color:#333}</style></head><body>"
        + "<p>正文段落，用于占足体积。</p>" * 30 + "</body></html>",
        encoding="utf-8")

    def boom(content):
        raise RuntimeError("词库炸了")

    monkeypatch.setattr(_style_guard, "check", boom)
    monkeypatch.setattr(_density, "check_density_html", lambda path: [])

    ok, msg = _verify.verify_html(str(html))

    assert ok is True
    err = capsys.readouterr().err
    assert "[warn]" in err and "style" in err
