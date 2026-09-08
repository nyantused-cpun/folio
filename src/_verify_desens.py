# -*- coding: utf-8 -*-
"""C-E5 截图/图片类元素脱敏提醒（S8-B 棘轮拆小：自 _verify.py 外迁）。

动因：_verify 806 行 > 基线 cap 800（只许拆小不许加码；S4-S3 _verify_checks
先例）。本模块只承载 warn 级脱敏扫描，不阻断；verify 链经 _verify 的
re-export 消费，`from _verify import _warn_screenshot_desensitization`
既有引用面不变。
"""
import re

# C-E5：截图/图片类元素触发脱敏提醒（warn 级，不阻断）
# S8-B 增补：profile_card（人员照片）/logo_wall（客户 logo）同属含图构件，
# 但只在真引用图片（items 内 photo/src 非空）时才提醒——纯文字牌无脱敏面
_SCREENSHOT_ELEMENT_TYPES = {"screenshot", "image", "img"}
_IMAGE_BEARING_ITEM_FIELDS = {"profile_card": "photo", "logo_wall": "src"}
_IMG_TAG_RE = re.compile(r"<img[\s>]", re.IGNORECASE)


def _warn_screenshot_desensitization(html_text=None, spec=None):
    """扫描 HTML 文本或 spec 字典，出现 screenshot/image/img 类元素时给出脱敏提醒。

    只报告不阻断；返回警告字符串列表（命中即一条）。
    """
    warnings = []
    if isinstance(html_text, str) and _IMG_TAG_RE.search(html_text):
        warnings.append("确认截图已脱敏（客户数据/域名/内部路径）")
        return warnings
    if isinstance(spec, dict):
        for page in spec.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            for elem in page.get("elements", []) or []:
                if not isinstance(elem, dict):
                    continue
                if elem.get("type") in _SCREENSHOT_ELEMENT_TYPES:
                    warnings.append("确认截图已脱敏（客户数据/域名/内部路径）")
                    return warnings
                img_key = _IMAGE_BEARING_ITEM_FIELDS.get(elem.get("type"))
                items = elem.get("logos") or elem.get("profiles")
                if img_key and isinstance(items, list) and any(
                        isinstance(it, dict) and it.get(img_key)
                        for it in items):
                    warnings.append("确认截图已脱敏（客户数据/域名/内部路径）")
                    return warnings
    return warnings


