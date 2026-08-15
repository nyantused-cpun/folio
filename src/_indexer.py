# -*- coding: utf-8 -*-
"""index.json 摘要/标签生成与维护。
用 _compress.extract_attention 做提取式摘要，正则提标签。"""
import os
import json
import re

from _paths import SCRIPT_DIR

INDEX_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "index.json")

INDUSTRY_KEYWORDS = {
    "制造业": ["制造", "工厂", "产线", "生产", "MRO", "维修", "排产", "物料"],
    "教育": ["教育", "学校", "教学", "课程", "学生", "教师", "校园"],
    "政府": ["政府", "政务", "机关", "公共", "市民", "审批"],
    "科技": ["科技", "互联网", "SaaS", "云", "API", "平台", "数字化"],
    "金融": ["金融", "银行", "信贷", "风控", "支付", "结算"],
}


def _extract_tags(text):
    # P3：用 dict.fromkeys 保序去重，避免 set 无序导致 diff 噪声
    tags = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            tags[industry] = None
    # 系统名词：要求前缀是名词性词（排除"坚持/全市/维护/强化/提升"等动词或修饰语）
    # 用白名单前缀：常见业务域名词
    sys_words = re.findall(r'(?:业务|数据|应用|技术|信息|客户|销售|采购|库存|生产|财务|人力|办公|协同|知识|内容|渠道|服务|安全|架构|能力|资源|流程)[\u4e00-\u9fff]{0,4}(?:系统|平台|流程|模块|管理)', text)
    for w in sys_words[:5]:
        tags[w] = None
    headings = re.findall(r'^#+\s*(.+)$', text, re.MULTILINE)
    for h in headings[:3]:
        nouns = re.findall(r'[\u4e00-\u9fff]{2,8}', h)
        for n in nouns[:2]:
            tags[n] = None
    return list(tags.keys())[:10]


def _generate_summary(text, max_chars=150):
    try:
        from _compress import extract_attention
        attention = extract_attention(text)
    except ImportError:
        attention = text[:max_chars]
    if len(attention) > max_chars:
        attention = attention[:max_chars] + "..."
    return attention.replace("\n", " ").strip()


def _read_file_text(file_path):
    if not os.path.exists(file_path):
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".md", ".txt"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    try:
        from _pipeline import READERS
        reader = READERS.get(ext)
        if reader:
            return reader(file_path)
    except Exception:
        pass
    return ""


def _is_valid_proj_key(proj_key):
    """proj_key 必须是 _knowledge/clients/合法目录名 的相对路径，防止路径越界。"""
    if not proj_key or not isinstance(proj_key, str):
        return False
    if ".." in proj_key or os.path.isabs(proj_key):
        return False
    allowed_prefixes = ("_knowledge/clients/", "_knowledge/")
    if not any(proj_key.startswith(p) for p in allowed_prefixes):
        return False
    normalized = os.path.normpath(proj_key)
    if ".." in normalized.split(os.sep):
        return False
    return True


def _resolve_asset_path(proj_key, file_name):
    if not _is_valid_proj_key(proj_key):
        return None
    if not file_name or not isinstance(file_name, str):
        return None
    # 防止 file_name 越界
    if ".." in file_name or os.path.isabs(file_name):
        return None
    candidates = [
        os.path.join(SCRIPT_DIR, proj_key, file_name),
        os.path.join(SCRIPT_DIR, proj_key, "outputs", file_name),
        os.path.join(SCRIPT_DIR, proj_key, "refs", file_name),
        os.path.join(SCRIPT_DIR, proj_key, "inputs", file_name),
    ]
    for c in candidates:
        real_c = os.path.normpath(c)
        if not real_c.startswith(os.path.normpath(SCRIPT_DIR) + os.sep):
            continue
        if os.path.exists(real_c):
            return real_c
    return None


def update_index():
    if not os.path.exists(INDEX_PATH):
        print(f"index.json 不存在: {INDEX_PATH}")
        return

    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] index.json 解析失败: {e}，跳过更新")
        return

    updated_count = 0
    orphan_removed = 0

    # 通用孤儿检测：检查每个资产文件是否存在，不存在则删除
    projects = index.get("projects", {})
    for proj_key in list(projects.keys()):
        if not _is_valid_proj_key(proj_key):
            print(f"清理非法项目键: {proj_key}")
            del projects[proj_key]
            continue
        proj = projects[proj_key]
        if not isinstance(proj, dict):
            continue
        kept_assets = []
        for asset in proj.get("assets", []):
            file_name = asset.get("file", "")
            if not file_name:
                kept_assets.append(asset)
                continue
            file_path = _resolve_asset_path(proj_key, file_name)
            if file_path and os.path.exists(file_path):
                kept_assets.append(asset)
            else:
                orphan_removed += 1
                print(f"清理孤儿条目: {proj_key}/{file_name}")
        proj["assets"] = kept_assets
        # 如果项目下资产全空，删除整个项目
        if not kept_assets:
            del projects[proj_key]
            print(f"清理空项目: {proj_key}")

    for proj_key, proj in index.get("projects", {}).items():
        if not isinstance(proj, dict):
            continue
        for asset in proj.get("assets", []):
            if asset.get("summary"):
                continue
            file_name = asset.get("file", "")
            if not file_name:
                continue
            file_path = _resolve_asset_path(proj_key, file_name)
            if not file_path or not os.path.exists(file_path):
                continue
            text = _read_file_text(file_path)
            if not text:
                continue
            asset["summary"] = _generate_summary(text)
            asset["tags"] = _extract_tags(text)
            updated_count += 1
            print(f"已生成摘要: {proj_key}/{file_name}")

    # 原子写入：先写临时文件再替换，防止写入中断导致 index.json 损坏
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(INDEX_PATH), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, INDEX_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    print(f"\n完成: 更新 {updated_count} 个摘要, 清理 {orphan_removed} 个孤儿条目")


if __name__ == "__main__":
    update_index()
