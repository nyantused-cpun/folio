# -*- coding: utf-8 -*-
"""I-7 域卡死法 → 构图禁令机械检查（S15 转正内核）。

数据源：presentation-content-design/references/scenario-presale.md §4.2
首批 10 条死法→禁令映射（元卡 7 + 档案域 3）。

设计：
- DOMAIN_BANS：10 条规则表（id / 来源死法 / 禁令 / 机械判定或人工标记）。
- check_domain_bans(text)：机械可判定的结构/关键词规则自动命中；语义规则
  不自动误报，仅以 "manual_check" 标注供 review 人工维度消费。
- 与 _verify.verify_html 观察模式接线：命中只进 msg 不阻断（对齐升级条件: 全量 verify 误报归零跑满 3 个发版批次 → 升 error 级（盘点#3）
  style/密度/占位符同款先例）。

诚实边界：机械检查只覆盖可确定判定的子集，其余规则保留为人工复核项，
避免误伤（对齐 review「反均分人工复核」先例）。
"""
import re

DOMAIN_BANS = [
    {
        "id": "DB-01",
        "source": "元卡#1",
        "ban": "蓝图前必须有设计原则页；每张架构图四要素齐全（结论/图例/来源/行动）",
        "mechanical": True,
        "detect": lambda text: (
            "蓝图" in text and "设计原则" not in text and "设计理念" not in text
            and "设计思路" not in text),
    },
    {
        "id": "DB-02",
        "source": "元卡#3",
        "ban": "差距页 Gap 必须显式且逐条带处理方式，禁全绿 Fit 矩阵",
        "mechanical": True,
        # P3：fit 用词边界匹配——裸子串会被 benefit/profit 等词误命中
        "detect": lambda text: (
            (re.search(r"\bfit\b", text, re.IGNORECASE) is not None
             and "gap" not in text.lower())
            or ("全绿" in text and "差距" not in text)
            or ("100% 匹配" in text and "差距" not in text)),
    },
    {
        "id": "DB-03",
        "source": "元卡#5",
        "ban": "capability_map/产品能力卡只作佐证，禁当规划主线（菜单 ≠ 方法论）",
        "mechanical": True,
        "detect": lambda text: (
            ("功能清单" in text or "产品菜单" in text or "功能菜单" in text)
            and "方法论" not in text),
    },
    {
        "id": "DB-04",
        "source": "元卡#7",
        "ban": "只交付蓝图没有差距/演进/治理 -> 蓝图之后必有差距页 + 路线页",
        "mechanical": True,
        "detect": lambda text: (
            "蓝图" in text
            and "差距" not in text
            and "路线" not in text and "演进" not in text and "分期" not in text),
    },
    {
        "id": "DB-05",
        "source": "元卡#8",
        "ban": "行业模板直接套：他行业应用清单/数字禁入，行业内容以客户行业卡为准",
        "mechanical": False,
        "detect": lambda text: False,  # 语义判定，review 人工维度
    },
    {
        "id": "DB-06",
        "source": "元卡#9",
        "ban": "现状不给数字、结论没来源：现状页必须 data_narrative；外部数据挂来源行",
        "mechanical": True,
        "detect": lambda text: (
            "现状" in text and not any(c.isdigit() for c in text)),
    },
    {
        "id": "DB-07",
        "source": "元卡#10",
        "ban": "预算只报总价、不给口径：预算页软件/实施双列 + 估法说明",
        "mechanical": True,
        "detect": lambda text: (
            ("预算" in text and "万元" in text) and "口径" not in text
            and "估法" not in text),
    },
    {
        "id": "DB-08",
        "source": "档案域#4",
        "ban": "硬编 RPA/OCR 当标配：组件映射页逐格挂 E9 能力目录校验；SOW 没有的能力禁入功能页/架构图",
        "mechanical": True,
        "detect": lambda text: (
            ("RPA" in text or "OCR" in text) and "能力目录" not in text
            and "SOW" not in text and "E9" not in text),
    },
    {
        "id": "DB-09",
        "source": "档案域#5",
        "ban": "别家客户特定事实张冠李戴：客户名/系统缩写/指标数字必须换成本客户的",
        "mechanical": False,
        "detect": lambda text: False,  # 语义判定，review 人工维度
    },
    {
        "id": "DB-10",
        "source": "档案域#1",
        "ban": "档案系统当'文件柜'：功能页禁把归档画成孤立存储组件，必须画出关联/利用链",
        "mechanical": False,
        "detect": lambda text: False,  # 语义判定，review 人工维度
    },
]


def check_domain_bans(text, include_manual=False):
    """对文本跑域禁令机械检查。

    text: 规范/产出文本（HTML 去标签后的正文或 spec 文本）。
    include_manual: True 时把语义规则也列出（标 manual），供 review 人工维度消费。
    返回 [{"id", "source", "ban", "manual": bool}, ...] 命中列表。
    """
    text = text or ""
    hits = []
    for rule in DOMAIN_BANS:
        try:
            if rule["detect"](text):
                hits.append({
                    "id": rule["id"],
                    "source": rule["source"],
                    "ban": rule["ban"],
                    "manual": not rule["mechanical"],
                })
        except Exception:
            continue
    if include_manual:
        for rule in DOMAIN_BANS:
            if not rule["mechanical"] and not any(
                    h["id"] == rule["id"] for h in hits):
                hits.append({
                    "id": rule["id"],
                    "source": rule["source"],
                    "ban": rule["ban"],
                    "manual": True,
                })
    return hits


# ============================================================
# I-3 A5：keynote 线集合核对（同款「只进 msg 不阻断」模式）
# ============================================================
_PHASES = ("一期", "二期", "三期")
_WEIGHTS = ("主线", "次线", "底座")
# 「X线」候选中的泛用词（非业务线），防误报
_GENERIC_LINE_WORDS = {
    "主线", "次线", "产线", "路线", "在线", "上线", "下线", "一线", "全线",
    "专线", "前线", "热线", "阵线", "战线", "射线", "管线", "曲线", "直线",
}


def check_keynote_lines(text, keynote):
    """产出文本的线集合 vs keynote 声明线集合（观察级，返回 warnings 列表）。升级条件: 与域禁令同批评审——误报归零跑满 3 个发版批次 → 转正（盘点#4）

    - keynote 缺失/无线 -> []（向后兼容，读侧行为与现状一致）；
    - 文本出现 keynote 未声明的「X线」-> 新线提示（触发人审，D7 纪律 2）；
    - 声明线在 ±12 字窗口内伴随与声明不一致的先后/权重档 -> 冲突提示（warning，不阻断）。
    """
    if not text or not keynote:
        return []
    declared = {row["name"]: row for row in (keynote.get("lines") or []) if row.get("name")}
    if not declared:
        return []
    warnings = []
    for m in re.finditer(r"[一-鿿A-Za-z0-9]{1,6}线", text):
        token = m.group(0)
        if any(g in token for g in _GENERIC_LINE_WORDS):
            continue  # 泛用词组合（如「以上为主线」「系统上线」）非业务线，防误报
        if any(token in name or name in token for name in declared):
            continue  # 已声明线（含子串归属，如「工厂线」归属声明名）
        warnings.append(f"keynote 未声明的新线「{token}」出现在产出中，提示触发人审（D7 纪律 2）")
    for name, line in declared.items():
        for m in re.finditer(re.escape(name), text):
            window = text[max(0, m.start() - 12):m.end() + 12]
            for ph in _PHASES:
                if ph in window and line.get("order") in _PHASES and ph != line["order"]:
                    warnings.append(f"线「{name}」先后冲突：keynote 声明 {line['order']}，产出伴随 {ph}")
                    break
            for w in _WEIGHTS:
                if w in window and line.get("weight") in _WEIGHTS and w != line["weight"]:
                    warnings.append(f"线「{name}」权重档冲突：keynote 声明 {line['weight']}，产出伴随 {w}")
                    break
    return list(dict.fromkeys(warnings))


def keynote_observe_for_text(text, client_name=None, keynote=None):
    """A5 接线 helper：返回 verify msg 追加串（" | keynote ..."），无命中/无 keynote -> ""。"""
    if keynote is None and client_name:
        from _theme_guard import load_keynote
        keynote = load_keynote(client_name)
    warns = check_keynote_lines(text, keynote)
    return (" | keynote: " + "; ".join(warns[:3])) if warns else ""
