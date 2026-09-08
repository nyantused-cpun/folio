# -*- coding: utf-8 -*-
"""integration 点对点简式渲染测试（#58）。

outline_to_spec M1 生成器产 source/target 系统名字符串的简式形态
（tests/test_outline_to_spec.py 钉死），schema 放行 str|dict 双合法；
渲染端 _intg_html/_intg_pptd 补简式分支（#58 前字符串 source 会在
.get("items") 处 AttributeError 走渲染异常降级）。

覆盖：简式 html/pptd 双端渲染、mapping dict 形态回归（结构钉死）、
简式缺 target 降级不崩、双端语义同构。
"""

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _renderer.diagram import render_diagram_html, render_diagram_pptd
from _renderer.diagram import architecture as arch


def _p2p(**extra):
    """点对点简式夹具（生成器形态：source/target 系统名字符串）。"""
    elem = {"type": "diagram", "diagram_type": "architecture", "subtype": "integration",
            "title": "点对点集成", "source": "OA", "target": "ERP"}
    elem.update(extra)
    return elem


def _mapping(**extra):
    """端点 mapping dict 夹具（渲染端既有形态，回归保障用）。"""
    elem = {"type": "diagram", "diagram_type": "architecture", "subtype": "integration",
            "title": "集成",
            "source": {"name": "OA", "items": ["凭证", "审批"]},
            "target": {"name": "SAP", "items": ["接收"]},
            "links": [{"label": "RFC", "mode": "bidirectional"}]}
    elem.update(extra)
    return elem


class TestP2pHtml:
    def test_p2p_str_source_renders_both_endpoints(self):
        """简式 html：不 AttributeError、不经异常降级、含 source/target 文本。"""
        html = render_diagram_html(_p2p())
        assert "渲染异常" not in html          # #58 前 str source 在此降级
        assert "border:2px dashed" not in html  # 非 fallback 占位卡
        assert "OA" in html and "ERP" in html
        # 复用 mapping 形态视觉语言：同款三列网格 + 顶色条端点卡
        assert "grid-template-columns:1fr 150px 1fr" in html
        assert "border-top:4px solid" in html
        # 连接表达：缺省单 link sync 箭头 + 模式名
        assert "→" in html and "同步" in html

    def test_p2p_links_and_interface_respected(self):
        """简式同样吃 links/interface 字段（与 mapping 形态同约定）。"""
        html = render_diagram_html(
            _p2p(interface="RFC", links=[{"label": "IDoc", "mode": "async"}]))
        assert "IDoc" in html and "⇢" in html and "异步" in html


class TestP2pPptd:
    def test_p2p_str_source_pptd_executable(self):
        """简式 pptd：可执行、双端点文本齐全、单 sync 走块箭头（D-2 同款）。"""
        elems, h = render_diagram_pptd(_p2p(), 192, 130, 1048)
        assert elems and h > 0
        texts = "".join(e["content"].get("text", "") for e in elems
                        if e["elementType"] == "text")
        assert "OA" in texts and "ERP" in texts
        arrows = [e for e in elems if e.get("shapeName") == "rightArrow"]
        assert arrows, "简式单 link sync 缺块箭头"

    def test_p2p_bidirectional_keeps_connector(self):
        """简式双向集成与 mapping 形态同构：connector 而非块箭头。"""
        elems, h = render_diagram_pptd(
            _p2p(links=[{"label": "RFC", "mode": "bidirectional"}]), 192, 130, 1048)
        assert h > 0
        assert not [e for e in elems if e.get("shapeName") == "rightArrow"]
        assert [e for e in elems if "Connector" in str(e.get("shapeName", ""))]


class TestMappingFormRegression:
    def test_mapping_dict_html_unchanged(self):
        """dict mapping 形态 html 关键结构与修复前一致（items 清单 + 双向箭头）。"""
        html = render_diagram_html(_mapping())
        assert "渲染异常" not in html
        assert "OA" in html and "SAP" in html
        assert "凭证" in html and "审批" in html and "接收" in html
        assert "⟷" in html and "双向" in html
        # 端点卡壳（#58 抽共用原语，输出零 diff）：顶色条 + 居中标题 + 分隔线
        assert ('<div style="background:#FFFFFF;border:1px solid #E2E8F0;'
                'border-top:4px solid #00338D;border-radius:10px;padding:18px 20px;">') in html
        # items 清单行：BG 底 + 层色左边条
        assert 'border-left:3px solid #00338D' in html
        assert 'border-left:3px solid #198038' in html  # 图形盘绿（R-4 提饱和）

    def test_mapping_dict_pptd_unchanged(self):
        """dict mapping 形态 pptd 元素序列与修复前逐项一致（id/类型/preset）。"""
        elems, h = render_diagram_pptd(_mapping(), 192, 130, 1048)
        got = [(e["elementId"], e["elementType"], e.get("shapeName", "")) for e in elems]
        assert got == [
            ("dg130-intg-src", "shape", "roundRect"),
            ("dg130-intg-src-top", "shape", "rect"),
            ("dg130-intg-src-h", "text", ""),
            ("dg130-intg-src-i0", "shape", "roundRect"),
            ("dg130-intg-src-i0-bar", "shape", "rect"),
            ("dg130-intg-src-i0-t", "text", ""),
            ("dg130-intg-src-i1", "shape", "roundRect"),
            ("dg130-intg-src-i1-bar", "shape", "rect"),
            ("dg130-intg-src-i1-t", "text", ""),
            ("dg130-intg-tgt", "shape", "roundRect"),
            ("dg130-intg-tgt-top", "shape", "rect"),
            ("dg130-intg-tgt-h", "text", ""),
            ("dg130-intg-tgt-i0", "shape", "roundRect"),
            ("dg130-intg-tgt-i0-bar", "shape", "rect"),
            ("dg130-intg-tgt-i0-t", "text", ""),
            ("dg130-intg-arr0", "shape", "straightConnector1"),
            ("dg130-intg-arr0-l", "text", ""),
        ]
        assert abs(h - 174.66666666666666) < 1e-9


class TestP2pDegraded:
    def test_p2p_str_missing_target_degrades_html(self):
        """简式缺 target：html 降级单卡不抛异常。

        经 dispatcher 层时 schema 会先拦（p2p 需 source+target）走占位卡，
        此处直测渲染器自身（render_html 层）按模块 warn 惯例优雅降级。
        """
        html = arch._intg_html({"subtype": "integration", "source": "OA"})
        assert "OA" in html
        assert "ERP" not in html
        assert "display:flex;justify-content:center" in html  # 单卡居中

    def test_p2p_str_missing_target_degrades_pptd(self):
        """简式缺 target：pptd 降级单卡，返回非空元素与正高度，不抛异常。"""
        elems, h = arch._intg_pptd({"subtype": "integration", "source": "OA"},
                                   192, 130, 1048)
        assert elems and h > 0
        texts = "".join(e["content"].get("text", "") for e in elems
                        if e["elementType"] == "text")
        assert "OA" in texts
        assert not [e for e in elems if e.get("shapeName") in ("rightArrow",
                                                               "straightConnector1")]

    def test_p2p_non_str_target_treated_as_missing(self):
        """target 非 str（脏数据）视同缺失走降级，不崩。"""
        html = arch._intg_html({"subtype": "integration", "source": "OA",
                                "target": 123})
        assert "OA" in html and "display:flex;justify-content:center" in html

    def test_dispatcher_never_raises_on_malformed_p2p(self):
        """dispatcher 层对畸形简式（缺 target）也不抛异常（schema 先拦走占位卡）。"""
        bad = {"type": "diagram", "diagram_type": "architecture",
               "subtype": "integration", "title": "坏例", "source": "OA"}
        html = render_diagram_html(bad)
        assert "坏例" in html and "border:2px dashed" in html  # 占位卡兜底
        elems, h = render_diagram_pptd(bad, 192, 130, 1048)
        assert elems and h > 0


class TestHubUnaffected:
    def test_hub_form_untouched(self):
        """hub 总线形态不受简式分支影响（优先级：hub > p2p 简式 > mapping）。"""
        elem = {"type": "diagram", "diagram_type": "architecture",
                "subtype": "integration", "title": "总线",
                "hub": {"name": "ESB"}, "systems": [{"name": "CRM"}, {"name": "SAP"}],
                "source": "OA", "target": "ERP"}  # 脏数据双形态并存，hub 优先
        html = render_diagram_html(elem)
        assert "<svg" in html and "ESB" in html
        elems, h = render_diagram_pptd(elem, 192, 130, 1048)
        assert h > 0 and any(e["elementId"].endswith("hub") for e in elems)
