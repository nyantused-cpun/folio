# -*- coding: utf-8 -*-
"""v2 spec 的 hex 字面量防线（§5.1，F5 主题预设制机械防线）。

从 _renderer/schema.py 拆出（S8 棘轮拆小：schema 1252>cap 1250，到顶即拆
先例）。spec 只写主题名；任何位置出现 hex 字面量 → error。theme.colors
子树豁免（旧覆盖机制）；evidence 子树豁免（召回证据原文引用，非设计决策）；
raw_html content 子树豁免（crafted 页美学主导，不受主题色约束，C-G1）。
"""

import re

_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _is_v2_spec(spec):
    """是否 v2 版式体系 spec（声明 v2 主题名或任一页用 P 系版式）。

    hex 防线只约束 v2 spec：老 spec 的合法 hex 存量（theme.colors 覆盖、
    深色画布自定义、正文提及色值）不在 v2 管辖范围（回归零误伤）。
    """
    from _renderer.schema import PAGE_LAYOUTS  # 局部 import 防循环
    if isinstance(spec.get("theme"), str):
        return True
    for page in spec.get("pages", []) or []:
        if isinstance(page, dict) and page.get("layout") in PAGE_LAYOUTS:
            return True
    return False


def _validate_spec_hex(spec):
    """v2 spec hex 防线主入口：返回 error 字符串列表，不抛异常。"""
    if not _is_v2_spec(spec):
        return []
    errors = []

    def _walk(node, path):
        if isinstance(node, dict):
            # raw_html content 子树豁免：crafted 页美学主导，不受主题色约束
            if node.get("type") == "raw_html" and "content" in node:
                return
            for k, v in node.items():
                if path == "" and k == "theme" and isinstance(v, dict):
                    continue  # 旧 theme.colors 覆盖机制豁免
                if k == "evidence":
                    continue  # 证据原文引用豁免（非设计决策）
                _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and _HEX_RE.search(node):
            errors.append(f"{path}: spec 出现 hex 字面量 "
                          f"'{_HEX_RE.search(node).group(0)}'"
                          "（F5：v2 spec 只写主题名，配色进主题包 tokens）")

    for key, value in spec.items():
        if key == "theme" and isinstance(value, dict):
            continue
        _walk(value, key)
    return errors
