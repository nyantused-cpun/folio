# -*- coding: utf-8 -*-
"""spec.yml 结构化 diff（重构计划 §八 3.2）。

对比两份 spec.yml，输出人类可读的结构化差异：
  - 顶层字段变化（project/style/confirmed/theme/document 等，嵌套 dict 递归到叶子路径）
  - 页面级：新增 / 删除 / 重排（按 page id 匹配；无 id 或 id 重复时退化为带序号的键）
  - 元素级：每页内元素的增 / 删 / 改（按 index + type 匹配；
    改动给出字段级 before/after，长文本截断显示）

退出码对齐 diff(1) 语义，方便脚本判断：
  0 = 无差异；1 = 有差异；2 = 错误（文件不存在 / YAML 解析失败 / 顶层非字典）

配合 §八 3.1 的 spec 快照（.versions/）可回溯"v4 长什么样"：
  python _cli.py spec-diff .versions/方案_spec.yml.20260720120000 方案_spec.yml
"""
import os
import sys

import yaml

# before/after 单行展示上限（超出截断，保证长文本不刷屏）
MAX_TEXT_LEN = 60

_KIND_MARK = {"added": "+", "removed": "-", "changed": "~"}


def load_spec(path):
    """读取 spec.yml。文件缺失 / 解析失败 / 顶层非 dict 时抛错（cmd 层转退出码 2）。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, dict):
        raise ValueError(f"spec 顶层不是字典（不是有效的 spec.yml）: {path}")
    return spec


def _short(value, limit=MAX_TEXT_LEN):
    """值 → 单行截断显示文本。字符串去换行加引号，其余走 repr。"""
    if isinstance(value, str):
        shown = '"' + value.replace("\n", "⏎") + '"'
    else:
        shown = repr(value)
    if len(shown) > limit:
        shown = shown[:limit] + "…"
    return shown


def _diff_values(a, b, path, changes):
    """递归字段级 diff：dict 按 key 并集、list 按 index、叶子不等记 changed。

    changes 追加 (kind, path, before, after)，kind ∈ added/removed/changed。
    """
    if isinstance(a, dict) and isinstance(b, dict):
        keys = list(a.keys()) + [k for k in b.keys() if k not in a]
        for key in keys:
            sub = f"{path}.{key}" if path else str(key)
            if key not in b:
                changes.append(("removed", sub, a[key], None))
            elif key not in a:
                changes.append(("added", sub, None, b[key]))
            else:
                _diff_values(a[key], b[key], sub, changes)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            sub = f"{path}[{i}]"
            if i >= len(b):
                changes.append(("removed", sub, a[i], None))
            elif i >= len(a):
                changes.append(("added", sub, None, b[i]))
            else:
                _diff_values(a[i], b[i], sub, changes)
    elif a != b:
        changes.append(("changed", path, a, b))


def _index_pages(pages):
    """页面列表 → {匹配键: (位置, page)}。

    匹配键优先 page id；无 id 用位置键 "#i"；同 id 重复出现加 "#n" 后缀，
    保证两份 spec 的重复页仍能一一对应。
    """
    seen = {}
    indexed = {}
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            page = {"title": str(page)}
        pid = page.get("id")
        if not pid:
            key = f"#{i}"
        else:
            n = seen.get(pid, 0) + 1
            seen[pid] = n
            key = pid if n == 1 else f"{pid}#{n}"
        indexed[key] = (i, page)
    return indexed


def _lis_indices(seq):
    """返回 seq 一个最长递增子序列的下标（用于识别"未移动的页"，其余即重排页）。"""
    n = len(seq)
    if n == 0:
        return []
    dp = [1] * n
    prev = [-1] * n
    best = 0
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                prev[i] = j
        if dp[i] > dp[best]:
            best = i
    indices = []
    while best != -1:
        indices.append(best)
        best = prev[best]
    return indices


def _elem_label(elem):
    """元素单行标识：type + 首个有内容的识别字段（title/content/name）。"""
    if not isinstance(elem, dict):
        return _short(elem, 30)
    etype = elem.get("type", "?")
    for field in ("title", "content", "name"):
        v = elem.get(field)
        if isinstance(v, str) and v.strip():
            return f"{etype}:{_short(v, 24)}"
    return str(etype)


def diff_specs(spec_a, spec_b):
    """对比两份 spec dict，返回结构化差异报告（配合 format_diff 展示）。"""
    report = {
        "top": [],              # 顶层字段 [(kind, path, before, after)]
        "pages_added": [],      # [(id, title)]
        "pages_removed": [],    # [(id, title)]
        "pages_reordered": [],  # [(id, 旧位置, 新位置)]（位置为 1-based 页码）
        "pages_changed": [],    # [{id, title, field_changes, elements_added/removed/changed}]
    }

    # 1. 顶层字段（pages 单独做页面级对比）
    top_a = {k: v for k, v in spec_a.items() if k != "pages"}
    top_b = {k: v for k, v in spec_b.items() if k != "pages"}
    _diff_values(top_a, top_b, "", report["top"])

    # 2. 页面增删（按 id 匹配）
    pages_a = _index_pages(spec_a.get("pages") or [])
    pages_b = _index_pages(spec_b.get("pages") or [])
    for key, (_, page) in pages_a.items():
        if key not in pages_b:
            report["pages_removed"].append((key, page.get("title", "")))
    for key, (_, page) in pages_b.items():
        if key not in pages_a:
            report["pages_added"].append((key, page.get("title", "")))

    # 3. 重排：公共页在 B 中的相对顺序与 A 不一致的部分
    #    （LIS 内的页保持相对顺序视为未动，LIS 外才是被移动的页，避免误报连坐）
    common_a = [k for k in pages_a if k in pages_b]
    common_b = [k for k in pages_b if k in pages_a]
    rank_in_b = {k: i for i, k in enumerate(common_b)}
    keep = set(_lis_indices([rank_in_b[k] for k in common_a]))
    for i, key in enumerate(common_a):
        if i not in keep:
            report["pages_reordered"].append(
                (key, pages_a[key][0] + 1, pages_b[key][0] + 1))

    # 4. 公共页：页字段（elements 之外）+ 元素级 diff
    for key in common_a:
        page_a = pages_a[key][1]
        page_b = pages_b[key][1]
        entry = {
            "id": key,
            "title": page_b.get("title") or page_a.get("title") or "",
            "field_changes": [],
            "elements_added": [],    # [(index, label)]
            "elements_removed": [],  # [(index, label)]
            "elements_changed": [],  # [(index, type, [(kind, path, before, after)])]
        }
        meta_a = {k: v for k, v in page_a.items() if k != "elements"}
        meta_b = {k: v for k, v in page_b.items() if k != "elements"}
        _diff_values(meta_a, meta_b, "", entry["field_changes"])

        elems_a = page_a.get("elements") or []
        elems_b = page_b.get("elements") or []
        for i in range(max(len(elems_a), len(elems_b))):
            if i >= len(elems_b):
                entry["elements_removed"].append((i, _elem_label(elems_a[i])))
                continue
            if i >= len(elems_a):
                entry["elements_added"].append((i, _elem_label(elems_b[i])))
                continue
            ea, eb = elems_a[i], elems_b[i]
            ta = ea.get("type", "?") if isinstance(ea, dict) else "?"
            tb = eb.get("type", "?") if isinstance(eb, dict) else "?"
            if ta != tb:
                # 同 index 但 type 不同：不是"改"，是整元素替换
                entry["elements_removed"].append((i, _elem_label(ea)))
                entry["elements_added"].append((i, _elem_label(eb)))
                continue
            changes = []
            _diff_values(ea, eb, "", changes)
            if changes:
                entry["elements_changed"].append((i, ta, changes))

        if any([entry["field_changes"], entry["elements_added"],
                entry["elements_removed"], entry["elements_changed"]]):
            report["pages_changed"].append(entry)

    return report


def has_changes(report):
    """报告是否含任何差异（决定退出码 0/1）。"""
    return any([report["top"], report["pages_added"], report["pages_removed"],
                report["pages_reordered"], report["pages_changed"]])


def _format_changes(changes, indent):
    lines = []
    for kind, path, before, after in changes:
        mark = _KIND_MARK[kind]
        if kind == "added":
            lines.append(f"{indent}{mark} {path}: （新增）{_short(after)}")
        elif kind == "removed":
            lines.append(f"{indent}{mark} {path}: {_short(before)} （已删除）")
        else:
            lines.append(f"{indent}{mark} {path}: {_short(before)} -> {_short(after)}")
    return lines


def format_diff(report, name_a, name_b):
    """结构化报告 → 人类可读文本（带页 id 和元素定位）。"""
    lines = ["=== spec-diff ===", f"A: {name_a}", f"B: {name_b}", ""]
    if not has_changes(report):
        lines.append("无差异")
        return "\n".join(lines)

    if report["top"]:
        lines.append("[顶层字段]")
        lines.extend(_format_changes(report["top"], "  "))
        lines.append("")

    page_lines = []
    for pid, title in report["pages_added"]:
        page_lines.append(f"  + 新增页 {pid}  {_short(title, 30)}")
    for pid, title in report["pages_removed"]:
        page_lines.append(f"  - 删除页 {pid}  {_short(title, 30)}")
    for pid, old_pos, new_pos in report["pages_reordered"]:
        page_lines.append(f"  ↕ 移动页 {pid}: 位置 {old_pos} -> {new_pos}")
    if page_lines:
        lines.append("[页面增删/重排]")
        lines.extend(page_lines)
        lines.append("")

    for entry in report["pages_changed"]:
        lines.append(f"[页 {entry['id']}]  {_short(entry['title'], 40)}")
        lines.extend(_format_changes(entry["field_changes"], "  "))
        for i, label in entry["elements_added"]:
            lines.append(f"  + elements[{i}] ({label}) 新增元素")
        for i, label in entry["elements_removed"]:
            lines.append(f"  - elements[{i}] ({label}) 删除元素")
        for i, etype, changes in entry["elements_changed"]:
            lines.append(f"  ~ elements[{i}] ({etype}):")
            lines.extend(_format_changes(changes, "      "))
        lines.append("")

    lines.append(
        f"合计: 顶层字段 {len(report['top'])} 处 · "
        f"新增页 {len(report['pages_added'])} · 删除页 {len(report['pages_removed'])} · "
        f"移动页 {len(report['pages_reordered'])} · 内容变化页 {len(report['pages_changed'])}")
    return "\n".join(lines)


def cmd_spec_diff(args):
    """CLI 入口：spec-diff <旧spec> <新spec>。

    退出码 0 无差异 / 1 有差异 / 2 错误。
    错误必须在此捕获并 exit 2——若抛给 main 的异常兜底会按 exit 1 处理，
    与"有差异"语义冲突，脚本无法区分。
    """
    try:
        spec_a = load_spec(args.spec_a)
        spec_b = load_spec(args.spec_b)
    except (OSError, ValueError, yaml.YAMLError) as e:
        print(f"[spec-diff] 错误: {e}")
        sys.exit(2)

    report = diff_specs(spec_a, spec_b)
    print(format_diff(report, args.spec_a, args.spec_b))
    sys.exit(1 if has_changes(report) else 0)
