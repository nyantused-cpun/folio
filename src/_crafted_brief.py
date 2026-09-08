# -*- coding: utf-8 -*-
"""创作子代理简报契约五件套完整性机检（S9 阶段 2c）。

规格源：docs/视觉生产线_创意模式_开发计划_2026-09-07.md §四 2c +
root decisions.md 第 10 条（2026-09-07 拍板）。crafted 页创作统一走
「人类显式指示 → 主脑派发创作子代理」，主脑不亲自写 raw_html；派发前用
check_brief_completeness 自检简报五件套：

  ①brief      创作简报（受众/主表达/静态等价物/密度档/气质坐标）
  ②facts      事实包（本页允许出现的全部事实/数字/名称/口径——只能用包内事实）
  ③refs       参考包（3 近 2 远，每条带决策注解）
  ④boundaries 边界自律（P4 铁律 + 外部参考合规零复制）
  ⑤output     输出契约（raw_html 元素 + 自检报告）

errors=缺件/形状坏（派发前必须修）；warnings=弱形状（建议修）。
契约模板单一事实源 = crafted-track.md「创作子代理契约（stage 2）」节；
本模块供派发前自检与将来工具化，纯函数不落盘。
"""
import re

MAX_DISPATCH_ROUNDS = 3  # 派发-重派循环上限（对齐修正上限，超限上报人类）
_BRIEF_KEYS = ("audience", "primary_expression", "static_equivalent",
               "density", "temperament")
_PLACEHOLDER_RE = re.compile(r"待补|TBD|xxx|XXX")
_NEAR_MIN, _FAR_MIN = 3, 2  # 参考包 3 近 2 远


def _bad_strings(node):
    """占位符残留扫描（待补/TBD/xxx），命中即弱形状。"""
    hits = []
    if isinstance(node, str):
        if _PLACEHOLDER_RE.search(node):
            hits.append(node[:40])
    elif isinstance(node, dict):
        for v in node.values():
            hits.extend(_bad_strings(v))
    elif isinstance(node, list):
        for v in node:
            hits.extend(_bad_strings(v))
    return hits


def check_brief_completeness(brief):
    """五件套完整性检查。返回 (errors, warnings)，均为 str 列表；纯函数。"""
    errors, warnings = [], []
    if not isinstance(brief, dict):
        return ["简报必须是 dict（五件套顶层键）"], []
    for key in ("brief", "facts", "refs", "boundaries", "output"):
        if key not in brief:
            errors.append(f"缺件：{key}（五件套之一）")
    if errors:
        return errors, warnings  # 顶层缺件时不再深检，避免噪音

    b = brief["brief"]
    if not isinstance(b, dict):
        errors.append("①brief 必须是 dict")
    else:
        for k in _BRIEF_KEYS:
            if not str(b.get(k) or "").strip():
                errors.append(f"①brief 缺 {k}（受众/主表达/静态等价物/密度档/气质坐标）")

    facts = brief["facts"]
    if not isinstance(facts, (list, dict)) or not facts:
        errors.append("②facts 空事实包（创作子代理无可用事实，只能用包内事实）")

    refs = brief["refs"]
    if not isinstance(refs, list) or len(refs) < _NEAR_MIN + _FAR_MIN:
        errors.append(f"③refs 参考包不足 {_NEAR_MIN} 近 {_FAR_MIN} 远（现 "
                      f"{len(refs) if isinstance(refs, list) else '非列表'} 条）")
    else:
        near = far = 0
        for i, r in enumerate(refs):
            if not isinstance(r, dict) or not str(r.get("source") or "").strip():
                errors.append(f"③refs[{i}] 缺 source")
                continue
            note = str(r.get("note") or "").strip()
            if not note:
                errors.append(f"③refs[{i}] 缺决策注解 note（借什么/弃什么/为什么）")
            kind = str(r.get("kind") or "").lower()
            near += kind == "near"
            far += kind == "far"
        if near < _NEAR_MIN or far < _FAR_MIN:
            errors.append(f"③refs 近/远配比不足（near={near}<{_NEAR_MIN} 或 far={far}<{_FAR_MIN}）")
        if len(refs) > _NEAR_MIN + _FAR_MIN:
            warnings.append(f"③refs 超 3+2 基数（{len(refs)} 条），确认非噪音堆料")

    bound = brief["boundaries"]
    if not isinstance(bound, dict) or not str(bound.get("p4_iron_rules") or "").strip():
        errors.append("④boundaries 缺 p4_iron_rules（本页生效铁律清单）")
    if isinstance(bound, dict) and not str(bound.get("external_compliance") or "").strip():
        errors.append("④boundaries 缺 external_compliance（外部参考合规零复制声明）")

    out = brief["output"]
    if not isinstance(out, dict):
        errors.append("⑤output 必须是 dict")
    else:
        if str(out.get("element") or "") != "raw_html":
            errors.append("⑤output.element 必须是 raw_html（crafted 页唯一容器）")
        if not (out.get("self_check_report") or out.get("self_report")):
            errors.append("⑤output 缺 self_check_report（子代理自检报告要求）")

    for hit in _bad_strings(brief):
        warnings.append(f"占位符残留「{hit}」——派发前应填实")
    return errors, warnings
