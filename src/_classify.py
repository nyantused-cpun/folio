# -*- coding: utf-8 -*-
import os
import json
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "_classify_config.json")
LOG_DIR = os.path.join(SCRIPT_DIR, ".trae", "logs")
INDEX_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "index.json")


def _default_config():
    """分类配置缺失或损坏时的安全默认值。"""
    return {
        "inbox": "inbox",
        "knowledge": "_knowledge",
        "output": "output",
        "archive": "_archive",
        "rules_meta": {
            "input_only_ext": [".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".html", ".md", ".txt"],
            "forbidden_ininbox_ext": [".py", ".log", ".pyc"],
            "archive_root": "_archive",
        },
        "routes": [
            {
                "name": "静态资源",
                "target": "_knowledge/assets",
                "rules": [{"ext": [".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".bmp", ".webp"]}],
                "knowledge": {"ref": False, "asset": True},
            },
            {
                "name": "未分类",
                "target": "inbox/_uncategorized",
                "rules": [{"ext": ["*"]}],
                "knowledge": {"ref": False, "asset": False},
            },
        ],
    }


def load_config():
    """加载分类配置，缺失或损坏时返回默认空规则，避免导出包缺文件直接崩溃。"""
    if not os.path.exists(CONFIG_PATH):
        print(f"[警告] 分类配置不存在: {CONFIG_PATH}，使用默认空规则")
        return _default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] 分类配置解析失败: {e}，使用默认空规则")
        return _default_config()


def load_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[警告] 分类索引损坏（{e}），已从空索引重建")
            return {"projects": {}, "recents": []}
    return {"projects": {}, "recents": []}


def save_index(index):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def match_file(filename, rules):
    """strong 规则优先：strong 命中即定；否则回落普通规则。"""
    strong = [r for r in rules if r.get("strong")]
    if strong and _match_rules(filename, strong):
        return True
    return _match_rules(filename, [r for r in rules if not r.get("strong")])


def _match_rules(filename, rules):
    name_lower = filename.lower()
    for rule in rules:
        ext_match = False
        ext_list = rule.get("ext", [])
        if "*" in ext_list:
            ext_match = True
        else:
            for ext in ext_list:
                if name_lower.endswith(ext.lower()):
                    ext_match = True
                    break

        if not ext_match:
            continue

        keywords = rule.get("keyword", [])
        if not keywords:
            return True

        for kw in keywords:
            if kw.lower() in name_lower:
                return True

    return False


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def log_message(msg, log_file):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    log_file.write(line + "\n")


def classify(client=None):
    """分类 inbox/ 下的文件。返回已分类文件列表 [(dst_path, client_name), ...]。

    client 指定时：跳过规则猜客户，inbox/ 根目录文件直接归档到该客户 refs
    （用于跨会话手动归档——归属由调用方显式指定，不再靠文件名猜）。
    """
    config = load_config()
    inbox_path = os.path.join(SCRIPT_DIR, config["inbox"])
    knowledge_path = os.path.join(SCRIPT_DIR, config["knowledge"])
    routes = config["routes"]

    if not os.path.exists(inbox_path):
        ensure_dir(inbox_path)
        print(f"inbox/ 目录已创建于 {inbox_path}")
        return []

    if client:
        return _classify_with_client(client, inbox_path, config)

    files = [
        f for f in os.listdir(inbox_path)
        if os.path.isfile(os.path.join(inbox_path, f))
    ]

    if not files:
        print("inbox/ 中没有待分类文件")
        return []

    log_path = os.path.join(LOG_DIR, f"classify_{datetime.now().strftime('%Y-%m-%d')}.log")
    ensure_dir(LOG_DIR)

    classified = []

    with open(log_path, "a", encoding="utf-8") as log:
        log_message(f"分类开始 | inbox/ 共 {len(files)} 个文件", log)

        index = load_index()
        success = 0
        unclassified = 0

        for filename in files:
            src = os.path.join(inbox_path, filename)
            matched = False

            for route in routes:
                if match_file(filename, route["rules"]):
                    target_dir = os.path.join(SCRIPT_DIR, route["target"])
                    ensure_dir(target_dir)
                    dst = os.path.join(target_dir, filename)

                    if os.path.exists(dst):
                        base, ext = os.path.splitext(filename)
                        dst = os.path.join(target_dir, f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")

                    try:
                        shutil.move(src, dst)
                    except OSError as e:
                        # 单文件失败（占用/权限/磁盘满）不中断整批
                        log_message(f"FAIL {filename}: 移动失败（{e}），跳过", log)
                        unclassified += 1
                        break
                    log_message(f"OK {filename} -> {route['target']}/  (规则: {route['name']})", log)

                    if route.get("knowledge", {}).get("ref"):
                        target_basename = os.path.basename(route["target"].rstrip("/\\"))
                        ref_dir = os.path.join(knowledge_path, "refs", target_basename)
                        ensure_dir(ref_dir)
                        try:
                            shutil.copy2(dst, os.path.join(ref_dir, filename))
                        except PermissionError:
                            pass

                    project_name = route["target"]
                    if project_name not in index["projects"]:
                        index["projects"][project_name] = {"name": route["name"], "assets": []}
                    index["projects"][project_name]["assets"].append({
                        "file": filename,
                        "type": "input",
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })

                    index["recents"].insert(0, {
                        "file": filename,
                        "target": route["target"],
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    index["recents"] = index["recents"][:50]

                    # 从 route target 提取客户名（格式如 "xxx/client/refs" → "client"）
                    parts = route["target"].rstrip("/").split("/")
                    client_name = parts[-2] if len(parts) >= 2 else ""
                    classified.append((dst, client_name))

                    success += 1
                    matched = True
                    break

            if not matched:
                uncat_dir = os.path.join(inbox_path, "_uncategorized")
                ensure_dir(uncat_dir)
                try:
                    shutil.move(src, os.path.join(uncat_dir, filename))
                except OSError as e:
                    # 单文件失败不中断整批
                    log_message(f"FAIL {filename}: 移动失败（{e}），跳过", log)
                    unclassified += 1
                    continue
                log_message(f"?? {filename} -> inbox/_uncategorized/  (未匹配任何规则)", log)
                unclassified += 1

        save_index(index)
        log_message(f"分类完成 | 成功 {success}, 未分类 {unclassified}", log)

    return classified


def _classify_with_client(client, inbox_path, config):
    """指定客户归档：跳过规则猜客户，直接移入该客户 refs。复用 _archive_auto 的移动/索引逻辑。"""
    from _archive_auto import archive_to_client

    forbidden = tuple(config["rules_meta"].get("forbidden_ininbox_ext", []))
    files = [
        f for f in os.listdir(inbox_path)
        if os.path.isfile(os.path.join(inbox_path, f))
        and not f.lower().endswith(forbidden)
    ]
    if not files:
        print("inbox/ 中没有待分类文件")
        return []

    outcome = archive_to_client(client, files, inbox_path)

    log_path = os.path.join(LOG_DIR, f"classify_{datetime.now().strftime('%Y-%m-%d')}.log")
    ensure_dir(LOG_DIR)
    with open(log_path, "a", encoding="utf-8") as log:
        log_message(f"分类开始 | 指定客户 {client} | 共 {len(files)} 个文件", log)
        for fn in outcome["moved"]:
            log_message(f"OK {fn} -> _knowledge/clients/{client}/refs/  (指定客户)", log)
        for fn, reason in outcome["skipped"]:
            log_message(f"FAIL {fn}: {reason}", log)
        log_message(f"分类完成 | 成功 {len(outcome['moved'])}, 未分类 {len(outcome['skipped'])}", log)

    refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client, "refs")
    return [(os.path.join(refs_dir, fn), client) for fn in outcome["moved"]]


def classify_and_extract(client=None):
    """IDE 模式：分类 + 自动提取内容摘要到 context.md。等价 CLI classify --extract。

    返回 schema:
    {
        "classified_count": int,
        "extracted_count": int,
        "warnings": list
    }
    """
    warnings = []
    classified = classify(client=client)
    if not classified:
        return {"classified_count": 0, "extracted_count": 0, "warnings": []}

    extracted_count = 0
    try:
        from _pipeline import read_full
        from _session import get_context_path
        for dst_path, client_name in classified:
            if not client_name:
                continue
            try:
                summary, cache = read_full(dst_path)
                ctx_path = get_context_path(client_name)
                if os.path.exists(ctx_path):
                    with open(ctx_path, "r", encoding="utf-8") as f:
                        existing = f.read()
                    fname = os.path.basename(dst_path)
                    marker = f"## 自动提取: {fname}"
                    if marker not in existing:
                        with open(ctx_path, "a", encoding="utf-8") as f:
                            f.write(f"\n{marker}\n")
                            f.write(f"来源: {dst_path}\n")
                            f.write(f"缓存: {cache}\n")
                            f.write(f"摘要:\n{summary[:2000]}\n\n")
                        extracted_count += 1
            except Exception as e:
                warnings.append(f"提取 {os.path.basename(dst_path)} 失败: {e}")
    except Exception as e:
        warnings.append(f"模块加载失败: {e}")

    return {
        "classified_count": len(classified),
        "extracted_count": extracted_count,
        "warnings": warnings,
    }


if __name__ == "__main__":
    classify()

