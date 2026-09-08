# -*- coding: utf-8 -*-
"""
doc-extract：统一文档读取命令（P0-1，dev_plan_cli_panel_2026-08-18）。

补齐协作边界表欠账：PROJECT_DESIGN §1.3 承诺「二进制解析（pptx/pdf/docx）由 CLI 负责」，
但命令面板此前只有 `read`（摘要+缓存）与 `bid-parse`（招标专用语义）。

本模块基于 _pipeline 已有读取器封薄壳（不引入 Docling 等新依赖，对齐 §简单），提供：
  - 格式自动识别：pdf / docx / xlsx / pptx / txt / md（可 --format 强制）
  - --mode text：纯文本提取（等价 read 的原文部分，但不落缓存，纯只读）
  - --mode structured：结构化输出（xlsx 逐行带表头上下文+anchor；其余格式带分页/分块标记）
  - --json：结构化 JSON 输出，供程序化消费

读取只读、不落盘、不调用 LLM。
"""
import os
import sys

from _pipeline import (
    read_pdf, read_docx, read_pptx, read_xlsx, read_xlsx_structured, read_txt,
)

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR

# 格式 -> (识别名, 纯文本读取器)
FORMAT_READERS = {
    "pdf": ("pdf", read_pdf),
    "docx": ("docx", read_docx),
    "pptx": ("pptx", read_pptx),
    "xlsx": ("xlsx", read_xlsx),
    "txt": ("text", read_txt),
    "md": ("text", read_txt),
}


def _resolve(path):
    """相对路径按项目根解析（与 _pipeline.read_full 一致）。"""
    if not os.path.isabs(path):
        path = os.path.join(SCRIPT_DIR, path)
    return path


def detect_format(path, fmt_hint="auto"):
    """返回格式名或 None。fmt_hint 优先，否则按扩展名。

    P3-2026-09-06：非法 fmt_hint 返回 None（fail-soft）——原实现把 hint 原样
    透传，调用方（FORMAT_READERS[fmt]）对未知键直接 KeyError；CLI 传入经
    argparse 自由文本，程序化调用传错值同样命中。
    """
    if fmt_hint and fmt_hint != "auto":
        return fmt_hint if fmt_hint in FORMAT_READERS else None
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext in FORMAT_READERS else None


def extract_document(path, fmt_hint="auto", mode="text", as_json=False):
    """统一提取入口。返回纯文本（as_json=False）或 dict（as_json=True）。

    as_json=True 时返回：
      {ok, file, format, mode, text|chunks, chars, error}
    chunks: [{text, anchor}]（structured 模式）
    """
    path = _resolve(path)
    result = {
        "ok": False,
        "file": path,
        "format": None,
        "mode": mode,
        "error": None,
    }
    if not os.path.exists(path):
        result["error"] = f"文件不存在: {path}"
        return result if as_json else result["error"]

    # P2-5：超限文件拒绝解析（与 read_full 同源上限）
    from _pipeline import size_exceeded
    err = size_exceeded(path)
    if err:
        result["error"] = err
        return result if as_json else result["error"]

    fmt = detect_format(path, fmt_hint)
    if not fmt:
        supported = ", ".join(sorted(FORMAT_READERS))
        # P3-2026-09-06：非法 --format 时报具体值，避免误报成扩展名问题
        bad = (fmt_hint if fmt_hint not in ("auto", "", None)
               and fmt_hint not in FORMAT_READERS
               else os.path.splitext(path)[1])
        result["error"] = (
            f"不支持的格式: {bad}（支持: {supported}，"
            f"或 --format 强制指定）"
        )
        return result if as_json else result["error"]

    # 格式强制与真实扩展名不一致时给警告（避免误解析）
    real_ext = os.path.splitext(path)[1].lower().lstrip(".")
    if fmt_hint not in ("auto", None) and real_ext in FORMAT_READERS and real_ext != fmt_hint:
        result["warning"] = (
            f"文件扩展名为 .{real_ext}，但 --format 强制为 {fmt_hint}；"
            f"按强制格式解析（结果可能为空或乱码）"
        )
        if not as_json:
            print(f"[警告] {result['warning']}", file=sys.stderr)

    result["format"] = fmt
    try:
        if mode == "structured" and fmt == "xlsx":
            chunks = read_xlsx_structured(path)
            result["chunks"] = [{"text": t, "anchor": a} for t, a in chunks]
            result["ok"] = True
            if as_json:
                return result
            return "\n\n".join(f"[{a}] {t}" for t, a in chunks)
        reader = FORMAT_READERS[fmt][1]
        text = reader(path)
        result["text"] = text
        result["chars"] = len(text)
        result["ok"] = True
    except Exception as e:  # noqa: BLE001
        result["error"] = f"读取失败: {e}"
        return result if as_json else result["error"]

    if as_json:
        return result
    return text


def run(argv):
    """argv: 已去掉命令名的参数列表。"""
    if len(argv) < 1:
        print("用法: python _cli.py doc-extract <文件> [--format auto|pdf|docx|xlsx|pptx|txt|md] "
              "[--mode text|structured] [--json]")
        return 1

    path = argv[0]
    fmt_hint = "auto"
    mode = "text"
    as_json = False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--format" and i + 1 < len(argv):
            fmt_hint = argv[i + 1]
            i += 2
        elif a == "--mode" and i + 1 < len(argv):
            mode = argv[i + 1]
            i += 2
        elif a == "--json":
            as_json = True
            i += 1
        else:
            i += 1

    # 退出码统一取 dict 的 ok 字段（P3-2026-09-06）：原实现按正文子串
    # （"不存在/失败/不支持"）猜成败，文档内容含这些词（如「传统方案失败…」）
    # 即误判 exit 1，错误串措辞变化也会漏判。
    result = extract_document(path, fmt_hint=fmt_hint, mode=mode, as_json=True)
    if as_json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("warning"):
            print(f"[警告] {result['warning']}", file=sys.stderr)
        if result.get("chunks"):
            print("\n\n".join(f"[{a}] {t}" for t, a in result["chunks"]))
        else:
            print(result["text"] if result.get("text") is not None
                  else result.get("error") or "")
    return 0 if result.get("ok") else 1