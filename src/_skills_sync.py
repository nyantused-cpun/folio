# -*- coding: utf-8 -*-
"""skills-sync：技能目录 -> .agents/skills/ 单向镜像。

发布版技能事实源是仓库根 `skills/`（或运行时 `.folio/skills/`）；
`.agents/skills/` 是 DSH 宿主派生副本，此前手工维持、已出现漂移。
按目录内容哈希复制新增/变更，--prune 删除多余项。
只同步含 SKILL.md 的目录。
"""
import hashlib
import os
import shutil


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


def _skill_dirs(base):
    """base 下含 SKILL.md 的一级子目录名集合。"""
    if not os.path.isdir(base):
        return set()
    result = set()
    for name in os.listdir(base):
        sub = os.path.join(base, name)
        if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "SKILL.md")):
            result.add(name)
    return result


def sync_skills(src_dir, dst_dir, prune=False):
    """把 src_dir 的技能目录镜像到 dst_dir，返回同步报告 dict。"""
    src_skills = _skill_dirs(src_dir)
    dst_skills = _skill_dirs(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)

    report = {"added": [], "updated": [], "unchanged": [], "pruned": []}
    for name in sorted(src_skills):
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

    return report
