# -*- coding: utf-8 -*-
"""spec.yml 类型化增量变更（P1-6，借鉴 DataFlow-Harness typed incremental mutations）。

与全量重写（yaml.dump 整份 spec）不同，本模块提供按操作的增量变更 API：
  - add_page: 新增整页
  - update_page: 更新页属性（title/layout/evidence 等）
  - delete_page: 删除整页
  - add_element: 向指定页新增元素
  - update_element: 更新指定页的指定元素
  - delete_element: 删除指定页的指定元素

每次操作：
  1. 操作前自动 .versions/ 快照（复用 _backup.backup_before_generate）
  2. 操作后调 validate_element / validate_spec 类型化校验
  3. 写回 spec.yml（yaml.safe_dump，保留 confirmed 等顶层字段）

借鉴 DataFlow-Harness 论文（arxiv 2607.16617）的 typed incremental mutations--
比全量重写更省 token、更少回归风险。
"""
import os
import yaml

from _renderer.schema import validate_element
from _backup import backup_before_generate


def _load_spec(path):
    """读取 spec.yml，返回 dict。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"spec 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(f"spec 顶层不是字典: {path}")
    if "pages" not in spec:
        spec["pages"] = []
    return spec


def _save_spec(path, spec):
    """写回 spec.yml（保留顶层字段顺序）。"""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _find_page(spec, page_id):
    """按 id 查找页面，返回 (index, page) 或 (None, None)。"""
    for i, p in enumerate(spec.get("pages", [])):
        if p.get("id") == page_id:
            return i, p
    return None, None


def add_page(spec_path, page_id, title, layout="bullets", elements=None, evidence=None):
    """新增整页。

    Args:
        spec_path: spec.yml 路径
        page_id: 页面 ID（唯一标识）
        title: 页面标题
        layout: 页面布局（默认 bullets）
        elements: 元素列表（可选，默认空列表）
        evidence: 证据列表（可选）

    Returns:
        dict: {"ok": bool, "errors": [...], "page_index": int}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    # 检查 page_id 唯一性
    idx, existing = _find_page(spec, page_id)
    if existing is not None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 已存在（index={idx}）"], "page_index": None}

    new_page = {"id": page_id, "title": title, "layout": layout, "elements": elements or []}
    if evidence:
        new_page["evidence"] = evidence

    # 校验元素
    errors = []
    for ei, elem in enumerate(new_page["elements"]):
        errors.extend(validate_element(elem, index=ei))

    if errors:
        return {"ok": False, "errors": errors, "page_index": None}

    spec["pages"].append(new_page)
    _save_spec(spec_path, spec)
    return {"ok": True, "errors": [], "page_index": len(spec["pages"]) - 1}


def update_page(spec_path, page_id, updates):
    """更新页属性（title/layout/evidence/target_score 等）。

    Args:
        spec_path: spec.yml 路径
        page_id: 要更新的页面 ID
        updates: dict，要更新的字段（不包含 id）

    Returns:
        dict: {"ok": bool, "errors": [...]}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    idx, page = _find_page(spec, page_id)
    if page is None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 不存在"]}

    # 不允许通过 update_page 改 id（避免引用断裂）
    if "id" in updates:
        return {"ok": False, "errors": ["update_page 不允许修改 id（如需改 id 请 delete + add）"]}

    page.update(updates)
    _save_spec(spec_path, spec)
    return {"ok": True, "errors": []}


def delete_page(spec_path, page_id):
    """删除整页。

    Returns:
        dict: {"ok": bool, "errors": [...], "deleted_index": int}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    idx, page = _find_page(spec, page_id)
    if page is None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 不存在"], "deleted_index": None}

    spec["pages"].pop(idx)
    _save_spec(spec_path, spec)
    return {"ok": True, "errors": [], "deleted_index": idx}


def add_element(spec_path, page_id, element, index=None):
    """向指定页新增元素。

    Args:
        spec_path: spec.yml 路径
        page_id: 目标页面 ID
        element: 元素 dict（必须含 type）
        index: 插入位置（None=追加到末尾）

    Returns:
        dict: {"ok": bool, "errors": [...], "element_index": int}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    idx, page = _find_page(spec, page_id)
    if page is None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 不存在"], "element_index": None}

    # 类型化校验
    errors = validate_element(element, index=0)
    if errors:
        return {"ok": False, "errors": errors, "element_index": None}

    elements = page.get("elements", [])
    if index is None or index >= len(elements):
        elements.append(element)
        index = len(elements) - 1
    else:
        elements.insert(index, element)
    page["elements"] = elements

    _save_spec(spec_path, spec)
    return {"ok": True, "errors": [], "element_index": index}


def update_element(spec_path, page_id, element_index, updates):
    """更新指定页的指定元素。

    Args:
        spec_path: spec.yml 路径
        page_id: 目标页面 ID
        element_index: 元素在 page.elements 中的序号
        updates: dict，要更新的字段

    Returns:
        dict: {"ok": bool, "errors": [...]}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    idx, page = _find_page(spec, page_id)
    if page is None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 不存在"]}

    elements = page.get("elements", [])
    if element_index < 0 or element_index >= len(elements):
        return {"ok": False, "errors": [f"element_index {element_index} 越界（共 {len(elements)} 个元素）"]}

    elements[element_index].update(updates)

    # 更新后重新校验
    errors = validate_element(elements[element_index], index=element_index)
    if errors:
        return {"ok": False, "errors": errors}

    _save_spec(spec_path, spec)
    return {"ok": True, "errors": []}


def delete_element(spec_path, page_id, element_index):
    """删除指定页的指定元素。

    Returns:
        dict: {"ok": bool, "errors": [...]}
    """
    backup_before_generate(spec_path)
    spec = _load_spec(spec_path)

    idx, page = _find_page(spec, page_id)
    if page is None:
        return {"ok": False, "errors": [f"page_id '{page_id}' 不存在"]}

    elements = page.get("elements", [])
    if element_index < 0 or element_index >= len(elements):
        return {"ok": False, "errors": [f"element_index {element_index} 越界（共 {len(elements)} 个元素）"]}

    elements.pop(element_index)
    _save_spec(spec_path, spec)
    return {"ok": True, "errors": []}


# 操作注册表（供 CLI 分发）
OPERATIONS = {
    "add_page": add_page,
    "update_page": update_page,
    "delete_page": delete_page,
    "add_element": add_element,
    "update_element": update_element,
    "delete_element": delete_element,
}
