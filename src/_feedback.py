# -*- coding: utf-8 -*-
"""客户反馈自动入库：截图/文本 → 提取要点 → 存到 context.md 的"客户反馈"段。

截图：依赖 AI 多模态视觉（_pipeline.py 不解析图片，AI 直接看）
文本：_pipeline.py 读取
入库：追加到 _knowledge/clients/{客户}/context.md 的 ## 客户反馈 段
"""
import os
from datetime import datetime

from _paths import CLIENTS_DIR


def ingest_feedback(client, file_path, note=""):
    """把反馈文件入库到客户 context.md。

    流程：
    1. 读取文件（文本用 _pipeline，图片标记为"需 AI 视觉理解"）
    2. 生成反馈条目（时间 + 来源文件 + note + 内容摘要占位）
    3. 追加到 context.md 的 ## 客户反馈 段
    4. 输出提示让 AI 补充内容摘要
    """
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        print(f"错误: 文件不存在: {abs_path}")
        return

    client_dir = os.path.join(CLIENTS_DIR, client)
    context_path = os.path.join(client_dir, "context.md")
    if not os.path.exists(context_path):
        print(f"错误: 客户 {client} 不存在，先 python _cli.py save {client}")
        return

    ext = os.path.splitext(abs_path)[1].lower()
    is_image = ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
    is_text = ext in [".txt", ".md"]
    is_doc = ext in [".docx", ".pdf", ".pptx"]

    content_text = ""
    if is_text:
        with open(abs_path, "r", encoding="utf-8") as f:
            content_text = f.read()
    elif is_doc:
        try:
            import _pipeline
            content_text, _cache = _pipeline.read_full(abs_path)
        except Exception as e:
            print(f"警告: 文档读取失败: {e}，将只记录文件路径")
    elif is_image:
        content_text = "[图片反馈，需 AI 视觉理解]"
    else:
        content_text = f"[未知格式: {ext}]"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    feedback_entry = f"\n### [{timestamp}] {os.path.basename(abs_path)}\n"
    feedback_entry += f"- 来源文件: {abs_path}\n"
    if note:
        feedback_entry += f"- 附加说明: {note}\n"
    if is_image:
        feedback_entry += "- 类型: 图片（AI 请用视觉能力理解内容并补充摘要）\n"
        feedback_entry += "- 内容摘要: [待 AI 补充]\n"
    else:
        preview = content_text.strip().replace("\n", " ")[:200]
        feedback_entry += f"- 类型: {ext}\n"
        feedback_entry += f"- 内容预览: {preview}\n"
        feedback_entry += "- 内容摘要: [待 AI 补充]\n"
    feedback_entry += "- 处理状态: 待处理\n"

    with open(context_path, "r", encoding="utf-8") as f:
        ctx = f.read()

    if "## 客户反馈" in ctx:
        ctx = ctx.replace("## 客户反馈", "## 客户反馈" + feedback_entry, 1)
    else:
        ctx = ctx.rstrip() + "\n\n## 客户反馈\n" + feedback_entry

    with open(context_path, "w", encoding="utf-8") as f:
        f.write(ctx)

    print(f"已入库反馈到 {client}/context.md")
    print(f"  时间: {timestamp}")
    print(f"  文件: {os.path.basename(abs_path)}")
    if is_image:
        print(f"  ⚠ 图片反馈，AI 请用视觉能力读取 {abs_path} 并补充内容摘要")
    else:
        print(f"  内容预览: {content_text.strip()[:100]}")
    print(f"\nAI 下一步: 读取 {context_path} 的 ## 客户反馈 段，补充内容摘要和处理建议")


# ============================================================
# M5: feedback diff 闭环（AI 原版 vs 人工修改）
# ============================================================
def record_diff(client, ai_version_path, human_version_path, note=""):
    """记录 AI 原版 vs 人工修改的差异，供反模式回流（M6）使用。

    流程：
    1. 逐行 diff 两个版本
    2. 提取人工修改的段落（+ 行）
    3. 保存 diff 记录到客户目录
    4. 返回差异段落列表，供 _snippet.save_antipattern 使用

    返回 (diff_text, changes) 或 (None, [])。
    """
    import difflib

    if not os.path.exists(ai_version_path):
        print(f"错误: AI 原版不存在: {ai_version_path}")
        return None, []
    if not os.path.exists(human_version_path):
        print(f"错误: 人工修改版不存在: {human_version_path}")
        return None, []

    with open(ai_version_path, "r", encoding="utf-8") as f:
        ai_text = f.read()
    with open(human_version_path, "r", encoding="utf-8") as f:
        human_text = f.read()

    # 逐行 diff
    diff = difflib.unified_diff(
        ai_text.splitlines(keepends=True),
        human_text.splitlines(keepends=True),
        fromfile="AI原版",
        tofile="人工修改",
        n=3,
    )
    diff_text = "".join(diff)

    if not diff_text:
        print("两个版本完全一致，无差异")
        return "", []

    # 提取人工修改的段落（+ 行，排除 +++ 文件名行）
    changes = []
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            changes.append(line[1:])

    # 保存 diff 记录到客户目录
    client_dir = os.path.join(CLIENTS_DIR, client)
    if os.path.exists(client_dir):
        diffs_dir = os.path.join(client_dir, "refs", "diffs")
        os.makedirs(diffs_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        diff_file = os.path.join(diffs_dir, f"diff_{timestamp}.txt")
        header = f"# AI vs 人工修改 diff\n# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n# AI原版: {ai_version_path}\n# 人工修改: {human_version_path}\n"
        if note:
            header += f"# 备注: {note}\n"
        with open(diff_file, "w", encoding="utf-8") as f:
            f.write(header + "\n" + diff_text)
        print(f"diff 已保存: {diff_file}")

        # spec 5.1.3：diff 存完后增量更新索引，让 recall 能搜到
        try:
            from _embed_index import build_embedding_index
            build_embedding_index()
        except Exception as e:
            print(f"[warn] diff 索引更新失败（不阻断）: {e}")

    print(f"发现 {len(changes)} 处人工修改段落")
    return diff_text, changes
