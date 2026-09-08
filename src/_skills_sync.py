# -*- coding: utf-8 -*-
"""skills-sync：.folio/skills/ -> .agents/skills/ 单向镜像。

.folio/skills/ 是技能唯一事实源；.agents/skills/ 是派生副本（供其他 agent 环境使用），
此前手工维持、已出现漂移。按目录内容哈希复制新增/变更，--prune 删除多余项。
只同步含 SKILL.md 的目录。

P0-4：本模块同时负责从 Skill frontmatter 生成 AGENTS_REFERENCE.md 的自动路由表。
扩展字段独立命名空间：route_level / triggers / negative；官方必填 name/description 优先。
"""
import hashlib
import os
import re
import shutil

import yaml


def _dir_hash(path):
    """目录内容哈希：相对路径 + 文件内容，与文件元数据无关。"""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(path)):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, path).replace(os.sep, "/")
            h.update(rel.encode("utf-8"))
            with open(fpath, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def _symlink_dirs(base):
    """base 下一级子项中的 symlink 名集合（D-5：显式跳过对象）。"""
    if not os.path.isdir(base):
        return set()
    return {name for name in os.listdir(base)
            if os.path.islink(os.path.join(base, name))}


def _skill_dirs(base):
    """base 下含 SKILL.md 的一级子目录名集合（symlink 不算，由 sync_skills 单列）。"""
    if not os.path.isdir(base):
        return set()
    result = set()
    for name in os.listdir(base):
        sub = os.path.join(base, name)
        # D-5：symlink 显式跳过——.agents 侧存在物理文件在别处的 symlink
        # （反向指），单向同步不跟随、不复制、不剪枝，避免 copytree 撞
        # FileExistsError / rmtree 拒删符号链接
        if os.path.islink(sub):
            continue
        if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "SKILL.md")):
            result.add(name)
    return result


def sync_skills(src_dir, dst_dir, prune=False):
    """把 src_dir 的技能目录镜像到 dst_dir，返回同步报告 dict。"""
    src_skills = _skill_dirs(src_dir)
    dst_skills = _skill_dirs(dst_dir)
    # D-5：双侧 symlink 统一显式 no-op（跳过 + 计数留痕），不进 added/updated/
    # unchanged/pruned/orphans 任何变更口径
    skipped = _symlink_dirs(src_dir) | _symlink_dirs(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)

    report = {"added": [], "updated": [], "unchanged": [], "pruned": [],
              "orphans": [], "symlinks_skipped": sorted(skipped)}
    for name in sorted(src_skills - skipped):
        src_sub = os.path.join(src_dir, name)
        dst_sub = os.path.join(dst_dir, name)
        if name not in dst_skills:
            shutil.copytree(src_sub, dst_sub)
            report["added"].append(name)
        elif _dir_hash(src_sub) != _dir_hash(dst_sub):
            # 原子替换：先复制到临时目录，成功后才删旧目录，防 rmtree 后 copytree 失败丢数据
            tmp_sub = dst_sub + ".tmp"
            if os.path.exists(tmp_sub):
                shutil.rmtree(tmp_sub)
            shutil.copytree(src_sub, tmp_sub)
            shutil.rmtree(dst_sub)
            os.rename(tmp_sub, dst_sub)
            report["updated"].append(name)
        else:
            report["unchanged"].append(name)

    if prune:
        for name in sorted(dst_skills - src_skills):
            shutil.rmtree(os.path.join(dst_dir, name))
            report["pruned"].append(name)
    else:
        # 孤儿报告：目标端存在、事实源没有的技能（不剪枝，只可见——防影子技能静默累积）
        report["orphans"] = sorted(dst_skills - src_skills)

    return report


# ── P0-4：Skill 路由表自动生成 ──────────────────────────────────────────────

_ROUTE_MARKER_BEGIN = "<!-- AUTO-GENERATED:BEGIN skills-routing -->"
_ROUTE_MARKER_END = "<!-- AUTO-GENERATED:END skills-routing -->"
_VALID_ROUTE_LEVELS = {"mandatory", "optional", "excluded"}


def _read_frontmatter(path):
    """读取 SKILL.md 的 YAML frontmatter；解析失败返回空 dict（不阻断）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {}
    text = text.lstrip("\ufeff")
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value):
    """把 frontmatter/overrides 中的字符串或列表统一成字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def scan_skill_routing(skills_dir):
    """扫描所有 skill 的 frontmatter 路由字段，返回排序后的路由条目。"""
    entries = []
    if not os.path.isdir(skills_dir):
        return entries
    for name in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        fm = _read_frontmatter(skill_md)
        route_level = fm.get("route_level", "optional")
        if route_level not in _VALID_ROUTE_LEVELS:
            route_level = "optional"
        entries.append({
            "name": name,
            "official_name": str(fm.get("name") or name),
            "description": str(fm.get("description") or "").strip(),
            "route_level": route_level,
            "triggers": _as_list(fm.get("triggers")),
            "negative": str(fm.get("negative") or "").strip(),
        })
    return entries


def load_route_overrides(path):
    """读取 route_overrides.yml；文件不存在/非法时返回空 dict。"""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def apply_route_overrides(entries, overrides):
    """应用人工例外：force_include / force_exclude / trigger_alias。"""
    if not overrides:
        return entries
    by_name = {e["name"]: dict(e) for e in entries}
    for name in _as_list(overrides.get("force_include")):
        if name in by_name and by_name[name]["route_level"] == "excluded":
            by_name[name]["route_level"] = "optional"
    for name in _as_list(overrides.get("force_exclude")):
        if name in by_name:
            by_name[name]["route_level"] = "excluded"
    for alias in overrides.get("trigger_alias") or []:
        if not isinstance(alias, dict):
            continue
        target = alias.get("skill")
        if target not in by_name:
            continue
        for trigger in _as_list(alias.get("triggers")):
            if trigger not in by_name[target]["triggers"]:
                by_name[target]["triggers"].append(trigger)
    return [by_name[name] for name in sorted(by_name)]


def apply_disable_model_invocation(skills_dir, overrides):
    """T3：让 route_level=excluded 真正控制加载（名实相符）。

    excluded 且不在 keep_active 名单的 skill，sync 时自动写入
    disable-model-invocation: true（幂等，重复跑无 diff）；keep_active 名单内的
    excluded 技能保持可调用（不写标记）。手工已有标记的文件不重复写。
    """
    keep_active = set(_as_list((overrides or {}).get("keep_active")))
    changed = []
    if not os.path.isdir(skills_dir):
        return changed
    for name in sorted(os.listdir(skills_dir)):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        fm = _read_frontmatter(skill_md)
        if fm.get("route_level") != "excluded":
            continue
        if name in keep_active:
            continue
        with open(skill_md, "r", encoding="utf-8") as f:
            text = f.read()
        if "disable-model-invocation: true" in text:
            continue
        # 在 name: 行后插入标记：先放回 name 行尾换行（\2），再写标记，再放同一换行
        new_text = re.sub(
            r"^(name:[^\r\n]*)(\r?\n)",
            r"\1\2disable-model-invocation: true\2",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if new_text == text:
            continue
        with open(skill_md, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        changed.append(name)
    return changed


def _cell_text(value):
    """路由表单元格转义。"""
    if isinstance(value, list):
        value = "、".join(value)
    value = str(value or "")
    value = value.replace("|", "\\|").replace("\n", " ").strip()
    return value or "-"


def render_routing_section(entries):
    """生成带 AUTO-GENERATED 标记的路由表 Markdown 块。"""
    lines = [_ROUTE_MARKER_BEGIN, ""]
    lines.append("| Skill | route_level | triggers | negative |")
    lines.append("|---|---|---|---|")
    order = {"mandatory": 0, "optional": 1, "excluded": 2}
    for e in sorted(entries, key=lambda x: (order.get(x["route_level"], 3), x["name"])):
        lines.append(
            f"| `{e['name']}` | {e['route_level']} "
            f"| {_cell_text(e['triggers'])} | {_cell_text(e['negative'])} |"
        )
    lines.append("")
    lines.append(_ROUTE_MARKER_END)
    return "\n".join(lines)


def update_routing_table(reference_path, entries):
    """把生成的路由表写入 AGENTS_REFERENCE.md 的 AUTO-GENERATED 区。

    只替换标记之间的内容；文件中没有标记时在原“Skill 路由”小节后插入。
    """
    section = render_routing_section(entries)
    if not os.path.exists(reference_path):
        with open(reference_path, "w", encoding="utf-8") as f:
            f.write(section + "\n")
        return "created"
    with open(reference_path, "r", encoding="utf-8") as f:
        text = f.read()
    begin = text.find(_ROUTE_MARKER_BEGIN)
    end = text.find(_ROUTE_MARKER_END)
    if begin != -1 and end != -1:
        end += len(_ROUTE_MARKER_END)
        text = text[:begin] + section + text[end:]
        with open(reference_path, "w", encoding="utf-8") as f:
            f.write(text)
        return "updated"
    # fallback：没有标记时在“## Skill 路由”小节后插入
    heading = "## Skill 路由"
    idx = text.find(heading)
    if idx == -1:
        text = text.rstrip() + "\n\n" + section + "\n"
    else:
        # 找到该小节结束位置：下一个 ## 或文件尾
        next_heading = text.find("\n## ", idx + len(heading))
        if next_heading == -1:
            insert_at = len(text.rstrip())
        else:
            insert_at = next_heading + 1
        text = text[:insert_at].rstrip() + "\n\n" + section + "\n" + text[insert_at:]
    with open(reference_path, "w", encoding="utf-8") as f:
        f.write(text)
    return "inserted"
