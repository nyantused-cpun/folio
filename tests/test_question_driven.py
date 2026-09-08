# -*- coding: utf-8 -*-
"""Step 3：question_driven 页面级 questions 字段 + verify 最简绑定检查。"""

from _renderer.schema import validate_spec
from _verify import check_question_binding, verify_spec_layout_data


def _spec(questions_page, later_pages):
    return {"pages": [questions_page] + later_pages}


def _qpage(questions):
    return {"id": "p1", "title": "问题清单", "questions": questions,
            "elements": []}


def test_schema_accepts_questions():
    spec = _spec(_qpage([{"id": "Q1", "text": "现状如何？"}]), [])
    assert validate_spec(spec) == []


def test_schema_rejects_malformed_questions():
    spec = _spec(_qpage("坏"), [])
    assert any("questions" in e for e in validate_spec(spec))
    spec = _spec(_qpage([{"text": "缺 id"}]), [])
    assert any("id" in e for e in validate_spec(spec))
    spec = _spec(_qpage([{"id": "Q1"}]), [])
    assert any("text" in e for e in validate_spec(spec))


def test_binding_missing_warns():
    spec = _spec(_qpage([{"id": "Q1", "text": "现状如何？"}]), [
        {"id": "p2", "title": "后续", "elements": []},
    ])
    msgs = check_question_binding(spec)
    assert any("Q1" in m and "未在后续页面" in m for m in msgs)


def test_binding_satisfied_by_title():
    spec = _spec(_qpage([{"id": "Q1", "text": "现状如何？"}]), [
        {"id": "p2", "title": "Q1 现状分析", "elements": []},
    ])
    assert check_question_binding(spec) == []


def test_binding_satisfied_by_section_tag():
    spec = _spec(_qpage([{"id": "Q2", "text": "缺口？"}]), [
        {"id": "p2", "title": "后续",
         "elements": [{"type": "section_tag", "label": "Q2 缺口"}]},
    ])
    assert check_question_binding(spec) == []


def test_verify_spec_layout_includes_binding_warning():
    spec = _spec(_qpage([{"id": "Q9", "text": "问题？"}]), [
        {"id": "p2", "title": "没有引用", "elements": []},
    ])
    ok, errors, warnings = verify_spec_layout_data(spec)
    assert ok and not errors
    assert any("Q9" in w for w in warnings)
