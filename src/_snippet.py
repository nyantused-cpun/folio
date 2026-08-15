# -*- coding: utf-8 -*-
"""方案片段库：存/搜/列/套用可复用的方案积木。

片段类型：card（卡片）/ chart（图表）/ section（整段）/ table（表格）/ text（文字块）
存储：_knowledge/snippets/<type>/<name>.md（含 YAML front matter 元数据 + 正文 HTML/MD）
索引：_knowledge/snippets/index.json（name→meta，供 BM25 检索）
"""
import os
import json
import re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SNIPPETS_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "snippets")
INDEX_PATH = os.path.join(SNIPPETS_DIR, "index.json")

VALID_TYPES = ["card", "chart", "section", "table", "text", "antipattern"]


def _ensure_dirs():
    for t in VALID_TYPES:
        os.makedirs(os.path.join(SNIPPETS_DIR, t), exist_ok=True)


def _load_index():
    if not os.path.exists(INDEX_PATH):
        return {"snippets": []}
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"snippets": []}


def _save_index(index):
    _ensure_dirs()
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def save_snippet(name, snippet_type, content, source="", tags=None, client=""):
    """保存片段。content 是 HTML 或 Markdown 正文。"""
    _ensure_dirs()
    if snippet_type not in VALID_TYPES:
        print(f"错误: 类型必须是 {VALID_TYPES}")
        return False

    safe_name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
    file_path = os.path.join(SNIPPETS_DIR, snippet_type, f"{safe_name}.md")

    tags = tags or []
    meta = {
        "name": name,
        "type": snippet_type,
        "tags": tags,
        "source": source,
        "client": client,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "file": f"{snippet_type}/{safe_name}.md"
    }

    front_matter = "---\n"
    for k, v in meta.items():
        if isinstance(v, list):
            # P3：列表元素含特殊字符时用双引号包裹（flow sequence 内 \[ 无效）
            safe_items = []
            for item in v:
                sv = str(item)
                if any(c in sv for c in [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "<", ">", "=", "%", "@", "`", '"']):
                    safe_items.append('"' + sv.replace('"', '\\"') + '"')
                else:
                    safe_items.append(sv)
            front_matter += f"{k}: [{', '.join(safe_items)}]\n"
        else:
            # P3：标量值含冒号或特殊字符时用引号包裹
            sv = str(v)
            if any(c in sv for c in [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "<", ">", "=", "%", "@", "`"]):
                safe_v = sv.replace('"', '\\"')
                front_matter += f'{k}: "{safe_v}"\n'
            else:
                front_matter += f"{k}: {sv}\n"
    front_matter += "---\n\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(front_matter + content)

    index = _load_index()
    index["snippets"] = [s for s in index["snippets"] if s.get("file") != meta["file"]]
    index["snippets"].append(meta)
    _save_index(index)

    print(f"已保存片段: {name} ({snippet_type})")
    print(f"  路径: {file_path}")
    return True


def search_snippets(query, top_k=5, snippet_type=None):
    """关键词搜索片段。用简单的词频匹配（片段数量少，无需 BM25）。"""
    index = _load_index()
    snippets = index.get("snippets", [])
    if snippet_type:
        snippets = [s for s in snippets if s.get("type") == snippet_type]

    if not snippets:
        print("没有片段")
        return []

    query_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', query.lower()))
    scored = []
    for s in snippets:
        text = (s.get("name", "") + " " + " ".join(s.get("tags", [])) + " " + s.get("source", "") + " " + s.get("client", "")).lower()
        content_text = ""
        fpath = os.path.join(SNIPPETS_DIR, s.get("file", ""))
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content_text = f.read().lower()
        combined = text + " " + content_text
        score = sum(1 for w in query_words if w in combined)
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = scored[:top_k]

    if not results:
        print(f"未找到匹配 '{query}' 的片段")
        return []

    print(f"=== 片段搜索结果（{len(results)} 项）===\n")
    for i, (score, s) in enumerate(results):
        print(f"[{i}] {s.get('name', '')} ({s.get('type', '')}) 命中 {score}")
        print(f"    标签: {', '.join(s.get('tags', [])) or '无'}")
        print(f"    来源: {s.get('source', '') or '无'}")
        print(f"    路径: _knowledge/snippets/{s.get('file', '')}")
        print()
    return results


def list_snippets(snippet_type=None):
    """列出所有片段。"""
    index = _load_index()
    snippets = index.get("snippets", [])
    if snippet_type:
        snippets = [s for s in snippets if s.get("type") == snippet_type]

    if not snippets:
        print("没有片段")
        return

    print(f"=== 片段库（{len(snippets)} 项）===\n")
    by_type = {}
    for s in snippets:
        by_type.setdefault(s.get("type", "?"), []).append(s)
    for t, items in sorted(by_type.items()):
        print(f"【{t}】({len(items)})")
        for s in items:
            tags = ", ".join(s.get("tags", []))
            print(f"  - {s.get('name', '')}  [{tags}]" if tags else f"  - {s.get('name', '')}")
        print()


def apply_snippet(name, output_format="html"):
    """读取片段内容，输出给 AI 套用。"""
    index = _load_index()
    for s in index.get("snippets", []):
        if s.get("name") == name:
            fpath = os.path.join(SNIPPETS_DIR, s.get("file", ""))
            if not os.path.exists(fpath):
                print(f"错误: 片段文件不存在: {fpath}")
                return None
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
            # 去掉 front matter
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    content = raw[end + 3:].strip()
                else:
                    content = raw
            else:
                content = raw
            print(f"=== 片段: {name} ({s.get('type', '')}) ===")
            print(f"标签: {', '.join(s.get('tags', []))}")
            print(f"来源: {s.get('source', '')}")
            print("\n--- 内容 ---\n")
            print(content)
            return content
    print(f"未找到片段: {name}")
    return None


def delete_snippet(name):
    """删除片段。"""
    index = _load_index()
    for i, s in enumerate(index.get("snippets", [])):
        if s.get("name") == name:
            fpath = os.path.join(SNIPPETS_DIR, s.get("file", ""))
            if os.path.exists(fpath):
                os.remove(fpath)
            index["snippets"].pop(i)
            _save_index(index)
            print(f"已删除片段: {name}")
            return True
    print(f"未找到片段: {name}")
    return False


def recommend_for_spec(spec_path, top_k=5):
    """根据 spec.yml 的行业/客户/主题，主动推荐相关片段。

    优先用 BM25 索引，fallback 到关键词匹配。
    """
    if not os.path.exists(spec_path):
        print(f"错误: spec 文件不存在: {spec_path}")
        return []

    with open(spec_path, "r", encoding="utf-8") as f:
        spec_text = f.read()

    # 提取 spec 中的关键词：标题、客户、行业、主题
    keywords = set()
    for line in spec_text.split("\n"):
        line = line.strip()
        if any(line.startswith(k) for k in ["title:", "client:", "industry:", "theme:", "name:"]):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if val:
                keywords.update(re.findall(r'[\u4e00-\u9fff]+|\w+', val.lower()))
    keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', spec_text))

    if not keywords:
        print("未从 spec 提取到关键词")
        return []

    index = _load_index()
    snippets = index.get("snippets", [])
    if not snippets:
        print("片段库为空")
        return []

    # 尝试用 BM25 索引
    bm25_scores = {}
    try:
        from _bm25 import query_bm25
        query_str = " ".join(list(keywords)[:30])
        bm25_results = query_bm25(query_str, top_k=top_k * 2)
        for path, score in bm25_results:
            # path 格式如 "<工作目录>\_knowledge\snippets\card\xxx.md#h0"
            base_path = path.split("#")[0]
            # P1-12：归一化为绝对路径，与下方 fpath 对齐
            if not os.path.isabs(base_path):
                base_path = os.path.normpath(os.path.join(SCRIPT_DIR, base_path))
            bm25_scores[base_path] = score
    except Exception:
        pass

    scored = []
    for s in snippets:
        fpath_rel = s.get("file", "")
        fpath = os.path.join(SNIPPETS_DIR, fpath_rel)
        meta_text = (s.get("name", "") + " " + " ".join(s.get("tags", [])) + " " + s.get("source", "") + " " + s.get("client", "")).lower()
        content_text = ""
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content_text = f.read().lower()

        # P1-12：BM25 key 用绝对路径 fpath，与 bm25_scores 的 key 对齐
        bm25_key = os.path.normpath(fpath)
        bm25_s = bm25_scores.get(bm25_key, 0)

        # 关键词匹配分
        kw_score = sum(1 for w in keywords if w in meta_text + " " + content_text)

        # 综合分：BM25 优先，关键词做 fallback
        combined = bm25_s * 10 if bm25_s > 0 else kw_score
        if combined > 0:
            scored.append((combined, s, bm25_s > 0))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [(s, used_bm25) for _, s, used_bm25 in scored[:top_k]]

    if not results:
        print("没有匹配的片段可推荐")
        return []

    method = "BM25+关键词" if any(r[1] for r in results) else "关键词"
    print(f"=== 主动推荐片段（基于 {spec_path}，{method}）===\n")
    print(f"提取关键词: {', '.join(list(keywords)[:15])}\n")
    for i, (s, used_bm25) in enumerate(results):
        mark = "★" if used_bm25 else "○"
        print(f"[{i}] {mark} {s.get('name', '')} ({s.get('type', '')})")
        print(f"    标签: {', '.join(s.get('tags', []))}")
        print(f"    来源: {s.get('source', '')}")
        print(f"    套用: python _cli.py snippet apply \"{s.get('name', '')}\"")
        print()
    return [s for s, _ in results]



