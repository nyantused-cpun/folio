# -*- coding: utf-8 -*-
"""CLI 基础设施：环境加载、环境检查、文件打开。"""
import os

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根（.env 等用户数据）


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
    """发布版口径（2026-08-16）：零 key 是正常状态，不再每次启动刷缺失警告。

    能力降级矩阵保留（不配 key 自动降级 BM25/宿主能力）；「建议配什么 key」
    只在 key-doctor 与 .env.example / docs/能力配置引导 中呈现。
    """
    pass


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
