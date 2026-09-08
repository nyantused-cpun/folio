# -*- coding: utf-8 -*-
"""方案片段库（2B 收敛版，2026-08-31）：纯语料库定位。

片段类型：card（卡片）/ chart（图表）/ section（整段）/ table（表格）/ text（文字块）/ antipattern（反模式词库）
存储：_knowledge/snippets/<type>/<name>.md（含 YAML front matter 元数据 + 正文 HTML/MD）
索引：_knowledge/snippets/index.json

2026-08-31 决策（decisions.md「清理与下线工程六项拍板」2B）：本模块收敛为**纯写入语料库**——
仅保留 save_snippet（由 _verify_hook 验证通过后自动采集调用）；
search/list/apply/delete/recommend 五个无调用方函数已删除，片段复用统一走 recall 检索管线。
⚠️ 2026-08-31 下线工程实测复核：_embed_index.scan_corpus_with_warnings 语料源
（client refs/diffs/client_index、docs 方法论白名单、方法 skill、industries、cases）
**不含** _knowledge/snippets/，BM25 与 Embedding 同源——本目录当前不在召回语料内；
如需片段进召回，须扩 scan_corpus（P2 候选，防自动采集片段稀释客户证据召回，慎开）。
"""
import os
import json
import re
from datetime import datetime

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR
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
    # P3-6：原子写——先写 tmp 再 os.replace，中断只留 .tmp 残片，
    # 不会留下半截 index.json（照 _embed_index._save_npy 范式）
    tmp_path = INDEX_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, INDEX_PATH)


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
