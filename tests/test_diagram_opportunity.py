# -*- coding: utf-8 -*-
"""「可用而未用」观察测试（条目 3-5，观察级永不阻断）。

覆盖：命中提对应 subtype / 有 diagram 不提 / 无信号不提 /
同页多信号只报最匹配一条 / 有结构化组件（raci_matrix）不提 /
挂载 verify_spec_layout_data 汇聚且不影响 ok。
"""
from _verify import check_diagram_opportunity, verify_spec_layout_data


def _page(pid, title="", elements=None):
    return {"id": pid, "title": title, "elements": elements or []}


def _action_title(text):
    return {"type": "action_title", "segments": [{"t": text}]}


# ---------- 命中：标题/正文信号 → 提示对应 subtype ----------

def test_raci_signal_in_action_title():
    spec = {"pages": [_page("p1", "治理保障", [
        _action_title("明确双方责任分工，关键事项到人"),
        {"type": "table", "headers": ["事项", "角色"],
         "rows": [["需求确认", "客户"]]},
    ])]}
    msgs = check_diagram_opportunity(spec)
    assert msgs == ["[观察] 页 p1 命中「分工」信号但只有文字/卡片，"
                    "可考虑 matrix/raci"]


def test_value_chain_signal_in_body_text():
    """信号词在 cards 正文里（不在标题）同样命中。"""
    spec = {"pages": [_page("p2", "业务梳理", [
        {"type": "cards", "cards": [
            {"title": "端到端", "body": "按价值链拆解流程与服务"}]},
    ])]}
    msgs = check_diagram_opportunity(spec)
    assert len(msgs) == 1 and "relationship/value_chain" in msgs[0]
    assert "「价值链」" in msgs[0]


def test_org_signal_maps_to_org_tree():
    spec = {"pages": [_page("p3", "组织架构与汇报线", [
        _action_title("三级组织架构，汇报线清晰")])]}
    msgs = check_diagram_opportunity(spec)
    assert len(msgs) == 1 and "relationship/org_tree" in msgs[0]


def test_quadrant_and_cbm_signals():
    spec = {"pages": [
        _page("p4", "系统优先级排序", [_action_title("按两轴划分四象限")]),
        _page("p5", "能力地图", [_action_title("核心能力地图一图总览")]),
    ]}
    msgs = check_diagram_opportunity(spec)
    assert len(msgs) == 2
    assert any("matrix/quadrant" in m and "页 p4" in m for m in msgs)
    assert any("matrix/cbm" in m and "页 p5" in m for m in msgs)


def test_multi_signal_only_first_rule_reported():
    """同页命中多个信号（职责→raci、组织→org_tree、权限→crud），
    按规则表顺序只报最匹配一条（raci）。"""
    spec = {"pages": [_page("p6", "组织职责与权限边界", [
        _action_title("理清组织职责与系统权限边界")])]}
    msgs = check_diagram_opportunity(spec)
    assert len(msgs) == 1
    assert "matrix/raci" in msgs[0] and "「职责」" in msgs[0]


def test_page_without_id_falls_back_to_index():
    spec = {"pages": [{"title": "实施排期",
                       "elements": [{"type": "text", "content": "排期待定"}]}]}
    msgs = check_diagram_opportunity(spec)
    assert len(msgs) == 1 and "页 pages[0]" in msgs[0]


# ---------- 豁免 ----------

def test_page_with_diagram_no_hint():
    spec = {"pages": [_page("p1", "责任分工", [
        _action_title("明确责任分工"),
        {"type": "diagram", "diagram_type": "matrix", "subtype": "raci"},
    ])]}
    assert check_diagram_opportunity(spec) == []


def test_no_signal_no_hint():
    spec = {"pages": [_page("p1", "项目背景", [
        _action_title("客户信息化基础良好，本期聚焦深化应用"),
        {"type": "bullets", "items": ["一期已上线", "二期做深化"]},
    ])]}
    assert check_diagram_opportunity(spec) == []


def test_structured_component_exempts():
    """页面已有 raci_matrix / evidence_ledger 等结构化组件（类型不在
    _NON_DIAGRAM_TYPES 内），不算「只有文字/卡片」，不提示。"""
    spec = {"pages": [_page("p1", "责任分工", [
        _action_title("明确责任分工"),
        {"type": "raci_matrix", "items": [
            {"task": "需求确认", "role": "客户", "raci": "A"}]},
    ])]}
    assert check_diagram_opportunity(spec) == []


def test_non_dict_pages_and_elements_ignored():
    spec = {"pages": [None, "bad", _page("p1", "背景", [None, 42])]}
    assert check_diagram_opportunity(spec) == []


def test_empty_pages_no_hint():
    assert check_diagram_opportunity({}) == []
    assert check_diagram_opportunity({"pages": []}) == []


# ---------- 挂载点：verify_spec_layout_data 汇聚 + 永不阻断 ----------

def test_mounted_in_verify_spec_layout_data():
    spec = {"confirmed": True,
            "pages": [_page("p1", "治理保障", [
                _action_title("明确双方责任分工，关键事项到人"),
                {"type": "table", "headers": ["事项"], "rows": [["确认"]]},
            ])]}
    ok, errors, warnings = verify_spec_layout_data(spec)
    assert ok and errors == []
    assert any("可考虑 matrix/raci" in w for w in warnings)
