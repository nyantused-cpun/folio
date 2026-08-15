# -*- coding: utf-8 -*-
"""项目路径常量单一数据源。

所有模块通过 `from _paths import SCRIPT_DIR, CLIENTS_DIR, ...` 引用，
避免 23 个模块各自 os.path.join 重复计算（候选 2 · paths 统一）。

迁移前各模块重复定义：
  SCRIPT_DIR      — 23 处
  CLIENTS_DIR     — 6 处（_session/_theme_guard/_indexer/_aliases/_feedback/...）
  TASK_HISTORY     — 2 处（_session/_verify_hook）
  STYLES_PATH     — 2 处（_renderer/_quote_html）
  LOGS_DIR        — _verify_hook
  INBOX_DIR       — _session
  KNOWLEDGE_DIR   — _session
  PPT_WORKSPACE   — _renderer
  PROFILE_PATH    — _renderer
  USAGE_LOG       — _cloud_llm
"""
import os
import hashlib
import pickle

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 客户与知识库
CLIENTS_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
KNOWLEDGE_DIR = os.path.join(SCRIPT_DIR, "_knowledge")
INBOX_DIR = os.path.join(SCRIPT_DIR, "inbox")

# 日志与历史
LOGS_DIR = os.path.join(SCRIPT_DIR, ".trae", "logs")
TASK_HISTORY = os.path.join(LOGS_DIR, "task_history.json")

# 渲染相关
PPT_WORKSPACE = os.path.join(SCRIPT_DIR, "ppt_workspace")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
STYLES_PATH = os.path.join(SCRIPT_DIR, "_renderer", "styles.json")
PROFILE_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")

# 产出扫描跳过目录（D-118：audit / stop_verify 单一数据源）
# hooks 侧镜像在 .trae/hooks/_output_skip_dirs.json（hook 不能 import 内部模块，
# json.load + 硬编码 fallback；tests/test_skip_dirs_consistency.py 快照兜底一致性）
OUTPUT_SKIP_DIRS = (
    "node_modules", ".versions", "dist", ".git",
    "debug", "figures", "_screenshots", "_4a_screenshots", "_align_check",
    "_archive", "_assets", "_baseline_work",
)
# 守卫放行的中间工程目录 = 扫描跳过目录 + pptd/HTML 工程目录（pages/media）
OUTPUT_INTERMEDIATE_DIRS = OUTPUT_SKIP_DIRS + ("pages", "media")

# LLM 用量
USAGE_LOG = os.path.join(LOGS_DIR, "llm_usage.jsonl")

# 视觉识别结果缓存（重复截图跳过上传，P-vision-5）
VISION_CACHE = os.path.join(LOGS_DIR, "vision_cache.json")

# 审查日志（独立于 task_history，见 spec 破坏点 3）
REVIEW_LOG = os.path.join(LOGS_DIR, "review_log.json")

# 去 AI 化禁用词（单一数据源，_review.py 和 _style_guard.py 共同引用）
BANNED_WORDS = ["赋能", "抓手", "闭环", "生态", "打通", "全方位", "一站式", "卓越"]
BANNED_PHRASES = ["综上所述", "总而言之", "不难看出", "可以说"]

# 世界书（spec 第三块）
INSIGHTS_DIR = os.path.join(LOGS_DIR, "insights")

# 技能（.trae/skills 唯一事实源 + 已读哨兵）
SKILLS_DIR = os.path.join(SCRIPT_DIR, ".trae", "skills")
SKILL_READ_DIR = os.path.join(LOGS_DIR, "skill_read")


def client_graph_path(client_name):
    """客户世界书 JSON 路径。"""
    _validate_client_name(client_name)
    return os.path.join(CLIENTS_DIR, client_name, "client_graph.json")


def client_index_path(client_name):
    """客户 AI 可读索引 MD 路径。"""
    _validate_client_name(client_name)
    return os.path.join(CLIENTS_DIR, client_name, "client_index.md")


def _validate_client_name(client_name):
    """校验客户名不含路径遍历字符。"""
    if not client_name or ".." in client_name or os.sep in client_name or "/" in client_name or "\\" in client_name:
        raise ValueError(f"非法客户名: {client_name!r}")


# HMAC 签名密钥（基于项目路径派生，不硬编码）
_HMAC_KEY = hashlib.sha256(SCRIPT_DIR.encode("utf-8")).digest()


def safe_pickle_load(path):
    """安全加载 pickle 文件：带 HMAC 签名校验。

    防止 pickle 文件被篡改后执行任意代码（RCE）。
    签名格式：文件前 32 字节为 HMAC-SHA256，其余为 pickle 数据。
    若文件无签名（旧格式），降级为直接 pickle.load 并打印警告。
    """
    with open(path, "rb") as f:
        data = f.read()

    if len(data) > 32:
        sig = data[:32]
        payload = data[32:]
        expected_sig = hmac_new(payload)
        if hmac_compare(sig, expected_sig):
            return pickle.loads(payload)  # nosec B301 - HMAC-SHA256 签名校验通过后才反序列化

    # 旧格式无签名：降级加载但打印警告
    import warnings
    warnings.warn(f"pickle 文件 {path} 无 HMAC 签名，建议重新生成以启用安全校验", stacklevel=2)
    return pickle.loads(data)  # nosec B301 - 仅加载本工具自产的本地缓存文件


def safe_pickle_dump(obj, path):
    """安全写入 pickle 文件：带 HMAC 签名。

    签名格式：HMAC-SHA256(32字节) + pickle 数据。
    """
    payload = pickle.dumps(obj)
    sig = hmac_new(payload)
    with open(path, "wb") as f:
        f.write(sig + payload)


def hmac_new(data):
    """计算数据的 HMAC-SHA256。"""
    import hmac as _hmac
    return _hmac.new(_HMAC_KEY, data, hashlib.sha256).digest()


def hmac_compare(a, b):
    """恒定时间比较，防止时序攻击。"""
    import hmac as _hmac
    return _hmac.compare_digest(a, b)
