# -*- coding: utf-8 -*-
"""P1-4 报价门禁：quote-build 阻断 + verify --mode quote 判断检查。

Q1/Q2 在 quote-build 内部阻断；Q3-Q6 由 verify --mode quote 输出。
"""
import os
import yaml

from _paths import SCRIPT_DIR

PRICING_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "me", "pricing.yml")

DEFAULT_PRICING = {
    "min_margin": 0.20,
    "max_discount": 0.10,
    "default_tax_rate": 0.06,
    "cost_factor": 1.0,
}


def load_pricing():
    """加载 pricing.yml；不存在/损坏时返回默认底线（不阻断）。"""
    if not os.path.exists(PRICING_PATH):
        return dict(DEFAULT_PRICING)
    try:
        with open(PRICING_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return dict(DEFAULT_PRICING)
    merged = dict(DEFAULT_PRICING)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def _quote_object(spec):
    """兼容顶层 quote: 或裸 quote 字段。"""
    if isinstance(spec, dict) and isinstance(spec.get("quote"), dict):
        return spec["quote"]
    return spec if isinstance(spec, dict) else {}


def _load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_build(spec_path):
    """quote-build 内部确定性阻断（Q1 数量/单位，Q2 税率）。"""
    spec = _load_spec(spec_path)
    quote = _quote_object(spec)
    pricing = load_pricing()
    issues = []

    for sheet in quote.get("sheets", []) or []:
        for sec in sheet.get("sections", []) or []:
            for item in sec.get("items", []) or []:
                qty = item.get("quantity")
                # P3：数值化后再判——数字字符串（如 "0"、"-2"）与空白串同样拦截，
                # 非数字视为缺失；仅判 isinstance 会漏掉 str 型绕过
                try:
                    qty_val = float(qty) if qty is not None and str(qty).strip() != "" else None
                except (TypeError, ValueError):
                    qty_val = None
                if qty_val is None or qty_val <= 0:
                    issues.append(f"Q1 数量缺失/为 0: {item.get('name', '?')}")
                unit = item.get("unit")
                if unit is None or str(unit).strip() == "":
                    issues.append(f"Q1 单位缺失: {item.get('name', '?')}")

    tax = quote.get("tax_rate")
    if tax is None or str(tax).strip() == "":
        issues.append("Q2 税率缺失（quote.tax_rate 必须填写）")
    else:
        try:
            tax_val = float(tax)
            default_tax = float(pricing.get("default_tax_rate") or 0)
            if abs(tax_val - default_tax) > 1e-6:
                issues.append(f"Q2 税率与 pricing.yml 不一致: 当前 {tax_val}，默认 {default_tax}")
        except (TypeError, ValueError):
            issues.append(f"Q2 税率非数字: {tax!r}")

    return issues


def check_verify(spec_path):
    """verify --mode quote：Q3 毛利、Q4 漏项、Q5 cost_basis、Q6 折扣/有效期。"""
    spec = _load_spec(spec_path)
    quote = _quote_object(spec)
    pricing = load_pricing()
    issues = []
    warnings = []

    # Q3 毛利低于下限（确定性）
    margin = quote.get("margin")
    if margin is not None and margin != "":
        try:
            margin_val = float(margin)
            min_margin = float(pricing.get("min_margin") or 0)
            if margin_val < min_margin:
                issues.append(f"Q3 毛利低于下限: {margin_val} < {min_margin}")
        except (TypeError, ValueError):
            warnings.append(f"Q3 margin 非数字: {margin!r}")
    else:
        warnings.append("Q3 未声明 margin（无法机械判定毛利）")

    # Q4 报价漏项：暂以“存在 cost_basis 关联声明”的最简对账提示
    if not quote.get("coverage_ref") and not quote.get("expected_items"):
        warnings.append("Q4 未提供 coverage_ref/expected_items，无法对账功能项漏项")

    # Q5 cost_basis 缺失（判断性 WARN）
    if not quote.get("cost_basis"):
        warnings.append("Q5 cost_basis 缺失（成本依据未声明）")

    # Q6 折扣/有效期
    discount = quote.get("discount", quote.get("global_discount", 1.0))
    try:
        discount_val = float(discount) if discount not in (None, "") else 1.0
        max_discount = float(pricing.get("max_discount") or 1)
        if discount_val < 1 - max_discount:
            warnings.append(f"Q6 折扣超上限: 折扣 {discount_val}，最高 {1 - max_discount}")
    except (TypeError, ValueError):
        warnings.append(f"Q6 discount 非数字: {discount!r}")
    if not quote.get("valid_until"):
        warnings.append("Q6 quote_valid_until 缺失")

    return issues, warnings
