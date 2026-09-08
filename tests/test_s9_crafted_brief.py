# -*- coding: utf-8 -*-
import pytest
"""S9 阶段 2c 创作子代理简报契约五件套完整性机检回归（_crafted_brief）。

三态：齐全（零 error）/ 缺件（逐件 error）/ 空事实包与形状坏（error）。
另钉：派发-重派 ≤3 轮常量与 crafted-track.md 契约模板落账互证。
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _crafted_brief import MAX_DISPATCH_ROUNDS, check_brief_completeness


def _valid_brief():
    """五件套齐全的最小合规简报（与 crafted-track.md 契约模板同构）。"""
    return {
        "brief": {
            "audience": "客户高层决策者（3 秒定印象）",
            "primary_expression": "全链路数据流架构总图",
            "static_equivalent": "静态分层框图",
            "density": "低",
            "temperament": "克制的深蓝科技感",
        },
        "facts": [
            {"text": "8 大模块、37 个接口", "source": "蓝图 v2 §3"},
        ],
        "refs": [
            {"source": "gold/架构总图_A", "kind": "near", "note": "借分层骨架，弃配色"},
            {"source": "baseline/政务蓝图", "kind": "near", "note": "借版式节奏"},
            {"source": "gold/愿景图_B", "kind": "near", "note": "借主视觉重心"},
            {"source": "年报信息图（跨行业）", "kind": "far", "note": "借数据强调手法"},
            {"source": "地图可视化（跨媒介）", "kind": "far", "note": "借空间隐喻，弃复杂度"},
        ],
        "boundaries": {
            "p4_iron_rules": "客户铁律：深蓝主色；去AI化硬 5 词",
            "external_compliance": "只借鉴思想与原理，零复制标识符，产出注明来源",
        },
        "output": {
            "element": "raw_html",
            "self_check_report": "密度档/对比度/溢出/字号底线逐项自检",
        },
    }


class TestComplete:
    def test_full_brief_no_errors(self):
        errors, warnings = check_brief_completeness(_valid_brief())
        assert errors == [] and warnings == []

    def test_non_dict_rejected(self):
        errors, _ = check_brief_completeness([])
        assert errors and "dict" in errors[0]

    def test_dispatch_rounds_pinned_and_doc_synced(self):
        """派发-重派 ≤3 轮：常量钉死，且契约模板文档同步落账。"""
        assert MAX_DISPATCH_ROUNDS == 3
        doc = os.path.join(SCRIPT_DIR, ".folio", "skills", "visual-craft-guide",
                           "references", "crafted-track.md")
        with open(doc, "r", encoding="utf-8") as f:
            text = f.read()
        assert "创作子代理契约（stage 2）" in text
        assert "派发-重派" in text and "≤3 轮" in text


class TestMissing:
    def test_each_top_key_missing_flagged(self):
        for key in ("brief", "facts", "refs", "boundaries", "output"):
            brief = _valid_brief()
            del brief[key]
            errors, _ = check_brief_completeness(brief)
            assert any(key in e for e in errors), f"缺 {key} 未报"

    def test_brief_subfield_missing_flagged(self):
        brief = _valid_brief()
        del brief["brief"]["temperament"]
        errors, _ = check_brief_completeness(brief)
        assert any("temperament" in e for e in errors)

    def test_refs_ratio_below_3_near_2_far(self):
        """条目数够但配比坏（5 近 0 远）→ 配比 error。"""
        brief = _valid_brief()
        brief["refs"] = [{**r, "kind": "near"} for r in brief["refs"]]
        errors, _ = check_brief_completeness(brief)
        assert any("近/远配比" in e for e in errors)

    def test_refs_missing_decision_note(self):
        brief = _valid_brief()
        del brief["refs"][0]["note"]
        errors, _ = check_brief_completeness(brief)
        assert any("决策注解" in e for e in errors)

    def test_refs_over_5_warns_not_errors(self):
        """参考包超 3+2 基数 = 弱形状（warn 不 error）。"""
        brief = _valid_brief()
        brief["refs"].append({"source": " extra", "kind": "near", "note": "补充参考"})
        errors, warnings = check_brief_completeness(brief)
        assert errors == []
        assert any("3+2" in w for w in warnings)


class TestBadShape:
    def test_empty_fact_pack_flagged(self):
        """空事实包 = error（只能用包内事实，包空则无从创作）。"""
        for empty in ([], {}, None):
            brief = _valid_brief()
            brief["facts"] = empty
            errors, _ = check_brief_completeness(brief)
            assert any("空事实包" in e for e in errors), f"facts={empty!r} 未报"

    def test_output_element_must_be_raw_html(self):
        brief = _valid_brief()
        brief["output"]["element"] = "free_div"
        errors, _ = check_brief_completeness(brief)
        assert any("raw_html" in e for e in errors)

    def test_output_missing_self_check_report(self):
        brief = _valid_brief()
        del brief["output"]["self_check_report"]
        errors, _ = check_brief_completeness(brief)
        assert any("self_check_report" in e for e in errors)

    def test_boundary_missing_external_compliance(self):
        """外部参考合规（零复制铁律）声明缺失 = error。"""
        brief = _valid_brief()
        del brief["boundaries"]["external_compliance"]
        errors, _ = check_brief_completeness(brief)
        assert any("external_compliance" in e for e in errors)

    def test_placeholder_leftover_warns(self):
        """占位符残留（待补/TBD）= 弱形状 warn。"""
        brief = _valid_brief()
        brief["brief"]["temperament"] = "待补"
        errors, warnings = check_brief_completeness(brief)
        assert errors == []
        assert any("待补" in w for w in warnings)


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
