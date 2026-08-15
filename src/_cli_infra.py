# -*- coding: utf-8 -*-
"""CLI 基础设施：环境加载、环境检查、文件打开。"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    """无依赖加载 .env 到 os.environ（已存在的 key 不覆盖）。
    优先环境变量，避免 IDE 配置的 key 被 .env 覆盖。
    """
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_dotenv()


def _check_env():
    """检查关键环境变量，缺失时打印警告。"""
    required = {
        "TAVILY_API_KEY": "Tavily 联网搜索（第一检索引擎）→ 缺失：web-search 仅剩字节搜索可用",
        "ZHIPU_API_KEY": "智谱 LLM（embedding/chat/rerank）→ 缺失：语义召回降级为 BM25，LLM 类功能不可用",
    }
    missing = []
    for var, desc in required.items():
        if not os.environ.get(var):
            missing.append(f"  {var} ({desc})")
    if missing:
        print("[环境检查] 以下环境变量未设置，对应功能按降级矩阵处理：")
        for m in missing:
            print(m)
        print("  排查 key 来源与可用性：python _cli.py key-doctor")
    
    has_byte_search = os.environ.get("ASK_ECHO_SEARCH_INFINITY_API_KEY") or \
                      (os.environ.get("VOLCENGINE_ACCESS_KEY") and os.environ.get("VOLCENGINE_SECRET_KEY"))
    if not has_byte_search:
        print("[环境检查] 字节搜索未配置（第二检索引擎），搜索仅使用 Tavily。")
        print("  如需启用字节搜索，请设置 ASK_ECHO_SEARCH_INFINITY_API_KEY 或 VOLCENGINE_ACCESS_KEY/SECRET_KEY。")


_check_env()


def _open_file(path):
    """跨平台用系统默认程序打开文件。"""
    import subprocess
    import platform
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"[提示] 无法自动打开，请手动编辑: {path}（{e}）")
