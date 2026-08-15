# -*- coding: utf-8 -*-
"""能力目录 schema 定义与校验（语义库·事实层）。

叶子模块（仿 _graph.py，无内部依赖）。edge 声明仿 pygraft relation_info：
domain/range/inverse/transitive/functional。
"""
import os
import json


__all__ = [
    "REQUIRED_LINK_FIELDS", "CARDINALITIES",
    "VALID_LEVELS", "OBJECT_TYPES",
    "DEFAULT_CATALOG_PATH",
    "_validate_link_type", "_validate_module",
    "load_catalog", "check_catalog",
]


REQUIRED_LINK_FIELDS = ["name", "domain", "range", "cardinality", "inverse", "transitive", "functional"]
CARDINALITIES = {"ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"}
VALID_LEVELS = {"APP", "ABB", "function"}
OBJECT_TYPES = {"CapabilityModule", "CapabilityFunction"}
DEFAULT_CATALOG_PATH = os.path.join("_knowledge", "capability_catalog", "能力目录_E9标准_v1.json")


def _validate_link_type(link):
    """校验一条 link_type 声明，返回错误字符串列表。"""
    errors = []
    for field in REQUIRED_LINK_FIELDS:
        if field not in link:
            errors.append(f"link {link.get('name', '?')} 缺字段: {field}")
    if "cardinality" in link and link["cardinality"] not in CARDINALITIES:
        errors.append(f"link {link.get('name', '?')} cardinality 非法: {link['cardinality']}")
    if "domain" in link and link["domain"] not in OBJECT_TYPES:
        errors.append(f"link {link.get('name', '?')} domain 非法: {link['domain']}")
    if "range" in link and link["range"] not in OBJECT_TYPES:
        errors.append(f"link {link.get('name', '?')} range 非法: {link['range']}")
    return errors


def _validate_module(mod):
    """校验一个能力模块条目，返回错误字符串列表。"""
    errors = []
    for field in ("module_id", "name", "app_domain", "level"):
        if field not in mod:
            errors.append(f"module {mod.get('module_id', '?')} 缺字段: {field}")
    if "level" in mod and mod["level"] not in VALID_LEVELS:
        errors.append(f"module {mod.get('module_id', '?')} level 非法: {mod['level']}")
    funcs = mod.get("functions", [])
    for fn in funcs:
        for field in ("function_id", "name"):
            if field not in fn:
                errors.append(f"module {mod.get('module_id', '?')} 功能缺字段: {field}")
    return errors


def load_catalog(path=None):
    """加载能力目录 JSON。返回 dict（含 error 键失败）。"""
    p = path or DEFAULT_CATALOG_PATH
    if not os.path.exists(p):
        return {"error": f"能力目录不存在: {p}"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"能力目录解析失败: {e}"}


def check_catalog(path=None):
    """校验能力目录 JSON，返回 {"valid": bool, "errors": [...]}。"""
    catalog = load_catalog(path)
    if "error" in catalog:
        return {"valid": False, "errors": [catalog["error"]]}
    errors = []
    if catalog.get("schema_version") != "1":
        errors.append(f"schema_version 必须为 '1'，实际 {catalog.get('schema_version')}")
    for link in catalog.get("link_types", []):
        errors.extend(_validate_link_type(link))
    for mod in catalog.get("modules", []):
        errors.extend(_validate_module(mod))
    return {"valid": not errors, "errors": errors}
