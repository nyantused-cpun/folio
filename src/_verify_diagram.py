# -*- coding: utf-8 -*-
"""图级校验聚合（C-F1，S4 棘轮处置再拆独立模块，2026-09-07）。

check_diagram_level：逐 diagram 元素聚合 _renderer.schema 的 error 校验 +
容量预算 warning，供 deliver receipt 取 verify 摘要。规则单点在 schema，
本模块只做全稿聚合与定位，不改规则、不造新阈值。
_verify_checks 经 import 暴露同名，既有引用面（tests、_cli_generate 等）不变。
"""


def check_diagram_level(spec):
    """图级校验聚合（C-F1，2026-09-07）：返回 {"diagrams", "errors", "warnings"}。

    逐 diagram 元素跑 _renderer.schema 的 error 校验（图形类型合法 / 必填字段 /
    subtype 专项结构）+ 容量预算 warning（graphics.md §2 口径，阈值单一事实源
    是 schema 的 *_WARN 常量）。本函数不改规则、不造新阈值，只做全稿聚合与定位
    （pages[pi].elements[ei] 前缀，与 validate_spec 的报错风格一致）。

    verify 链（verify_spec_layout_data -> schema.validate_spec /
    validate_element_warnings）消费的是同一规则集；本聚合供 cmd_deliver 写
    receipt 时取「verify 验证摘要」的图级切片，不需要为 receipt 重复发明摘要口径。
    """
    from _renderer import schema as _schema
    errors, warnings = [], []
    n = 0
    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        for ei, elem in enumerate(page.get("elements") or []):
            if not isinstance(elem, dict) or elem.get("type") != "diagram":
                continue
            n += 1
            errors.extend(f"pages[{pi}].{err}"
                          for err in _schema.validate_element(elem, index=ei))
            warnings.extend(_schema.validate_element_warnings(elem, index=ei))
    return {"diagrams": n, "errors": errors, "warnings": warnings}
