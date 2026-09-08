# -*- coding: utf-8 -*-
"""B-3 证据台账编号检查（S0 棘轮处置拆分自 _verify_checks.py，2026-09-07）。

职责：check_evidence_ledger（evidence_ledger 元素 num 重复 → [观察]，
只报告不阻断）。_verify.py 再导出本模块公开符号，既有引用面不变。
"""


def check_evidence_ledger(spec):
    """B-3 证据台账编号唯一性（观察模式）：num 非空且重复 → [观察]。TTL(2026-12-31): 季度评审转正/销号（盘点表未登记，随下轮盘点补录）

    只报告不阻断（exit code 不变）。
    """
    from collections import Counter
    msgs = []
    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        for ei, elem in enumerate(page.get("elements", []) or []):
            if not isinstance(elem, dict) or elem.get("type") != "evidence_ledger":
                continue
            nums = [it.get("num", "") for it in elem.get("items", []) or []
                    if isinstance(it, dict) and it.get("num")]
            dup = [n for n, c in Counter(nums).items() if c > 1]
            if dup:
                msgs.append(f"[观察] pages[{pi}].elements[{ei}]: "
                            f"evidence_ledger 证据编号重复 {', '.join(dup)}")
    return msgs
