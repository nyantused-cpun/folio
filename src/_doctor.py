# -*- coding: utf-8 -*-
"""
doctor：只读环境诊断命令（P0-2，dev_plan_cli_panel_2026-08-18）。

背景：2026-08-18 会话中「探测 venv 装了哪些库」被守卫拦截，AI 只能凭设计文档推断，
暴露「求知/验证通道」缺口。key-doctor 只查 API key，不查运行环境。

本命令纯只读：不落盘、不调 LLM、不执行外部子进程（包信息走 importlib.metadata，
核心模块可导入性走进程内 import）。输出：venv 路径/版本、依赖库、核心模块、
宿主识别、API key 状态（只报「已设置/未设置」，绝不回显值）。
"""
import os
import sys

from importlib import metadata as _metadata

# 本项目三类格式解析的关键依赖（与"实测清单"核对：pymupdf/pypdf/openpyxl/xlrd/python-docx/pptx）
CORE_PACKAGES = [
    "pymupdf", "pypdf", "openpyxl", "xlrd",
    "python-docx", "python-pptx", "mammoth", "pdf2image", "pypdfium2",
]

# 核心模块可导入性检查（对照 .folio/hooks/_blocked_modules.json，进程内只测 import）
CORE_MODULES = [
    "_pipeline", "_doc_extract", "_bid_parse", "_cli_guards", "_verify_hook",
    "_theme_guard", "_style_guard", "_cloud_llm", "_session", "_paths",
    "_snippet", "_indexer", "_renderer", "_pptd", "_skills_sync", "_inbox_scan",
]

# API key 名（只查是否存在，不回显值；与 key-doctor 的掩码纪律一致）
API_KEY_NAMES = [
    "MINIMAX_API_KEY", "DEEPSEEK_API_KEY", "TAVILY_API_KEY",
    "OPENAI_API_KEY", "ASK_ECHO_SEARCH_INFINITY_API_KEY", "SILICONFLOW_API_KEY",
    "GLM_API_KEY", "QWEN_API_KEY",
]


def _distributions():
    """一次获取全部分发名->版本（兼容 - 与 _ 两种规范化形式）。"""
    try:
        out = {}
        for d in _metadata.distributions():
            name = d.metadata.get("Name", "").lower()
            if not name:
                continue
            out[name] = d.version
            out[name.replace("-", "_")] = d.version
        return out
    except Exception:  # noqa: BLE001
        return {}


def _host_detect():
    """宿主识别：DSH / Trae / Kimi / 其他。"""
    hints = []
    if os.environ.get("TRAE_PROJECT_DIR"):
        hints.append("Trae")
    if os.environ.get("DSH_") is not None or any(k.startswith("DSH_") for k in os.environ):
        hints.append("DSH")
    env = {k for k in os.environ}
    if "KIMI_API_KEY" in env or "MOONSHOT_API_KEY" in env:
        hints.append("Kimi")
    return hints or ["unknown"]


def run_doctor(as_json=False):
    """返回 dict（as_json=True 走 JSON 输出）或打印文本。"""
    dists = _distributions()
    pkgs = {}
    for name in CORE_PACKAGES:
        pkgs[name] = dists.get(name.lower()) or "(未安装)"

    modules = {}
    for m in CORE_MODULES:
        try:
            __import__(m)
            modules[m] = "OK"
        except Exception as e:  # noqa: BLE001
            modules[m] = f"FAIL: {type(e).__name__}"

    keys = {}
    for k in API_KEY_NAMES:
        keys[k] = "已设置" if os.environ.get(k) else "未设置"

    result = {
        "python": sys.version.split()[0],
        "venv": sys.prefix,
        "project_dir": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "host": _host_detect(),
        "packages": pkgs,
        "modules": modules,
        "api_keys": keys,
    }

    if as_json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"venv:      {sys.prefix}")
    print(f"python:    {sys.version.split()[0]}")
    print(f"宿主:       {', '.join(result['host'])}")
    print("\n--- 依赖库 ---")
    for k, v in pkgs.items():
        print(f"  {k:<16} {v}")
    print("\n--- 核心模块（进程内 import 可达性）---")
    for k, v in modules.items():
        print(f"  {k:<22} {v}")
    print("\n--- API key（只报状态，不回显值）---")
    for k, v in keys.items():
        print(f"  {k:<24} {v}")
    return 0


def run(argv):
    as_json = "--json" in argv
    return run_doctor(as_json=as_json)