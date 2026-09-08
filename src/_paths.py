# -*- coding: utf-8 -*-
"""项目路径常量单一数据源。

所有模块通过 `from _paths import SCRIPT_DIR, CLIENTS_DIR, ...` 引用，
避免 23 个模块各自 os.path.join 重复计算（候选 2 · paths 统一）。

迁移前各模块重复定义：
  SCRIPT_DIR      — 23 处
  CLIENTS_DIR     — 6 处（_session/_theme_guard/_indexer/_aliases/_feedback/...）
  TASK_HISTORY     — 2 处（_session/_verify_hook）
  LOGS_DIR        — _verify_hook
  INBOX_DIR       — _session
  KNOWLEDGE_DIR   — _session
  PROFILE_PATH    — _renderer
  USAGE_LOG       — _cloud_llm
"""
import os
import hashlib
import pickle  # nosec B403 - safe_pickle_load 带 HMAC 校验，仅供本地缓存

# 发布版目录契约：代码在 src/，用户工作区在仓库根（output/_knowledge/.folio 所在）
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(CODE_DIR)

# 客户与知识库
CLIENTS_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
KNOWLEDGE_DIR = os.path.join(SCRIPT_DIR, "_knowledge")
INBOX_DIR = os.path.join(SCRIPT_DIR, "inbox")

# 日志与历史
LOGS_DIR = os.path.join(SCRIPT_DIR, ".folio", "logs")
TASK_HISTORY = os.path.join(LOGS_DIR, "task_history.json")
# M3-F2：阶段状态机事实源（多客户 state 文件）
SESSION_STATE_PATH = os.path.join(LOGS_DIR, "session_state.json")

# 渲染相关
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
PROFILE_PATH = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")

# 产出扫描跳过目录（D-118：audit / stop_verify 单一数据源）
# hooks 侧镜像在 .folio/hooks/_output_skip_dirs.json（hook 不能 import 内部模块，
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

# 去 AI 化禁用词（单一数据源，_review.py / _verify.py / _style_guard.py 共同引用）
# C-C1（2026-09-07 拍板，8→5）：删 抓手/生态/全方位——「生态合作」等 EA 术语不再误杀
BANNED_WORDS = ["赋能", "闭环", "打通", "一站式", "卓越"]
BANNED_PHRASES = ["综上所述", "总而言之", "不难看出", "可以说"]
# 语境层（C-C1）：3 词的形容词性用法只 warn 不阻断（severity=warn，供 pre_check/review 区分）
CONTEXT_WORDS = ["卓越的", "一站式的", "全方位的"]

# 世界书（spec 第三块）
INSIGHTS_DIR = os.path.join(LOGS_DIR, "insights")

# 技能（.folio/skills 唯一事实源 + 已读哨兵）
SKILLS_DIR = os.path.join(SCRIPT_DIR, ".folio", "skills")
SKILL_READ_DIR = os.path.join(LOGS_DIR, "skill_read")


def client_graph_path(client_name):
    """客户世界书 JSON 路径。"""
    _validate_client_name(client_name)
    return os.path.join(CLIENTS_DIR, client_name, "client_graph.json")


def client_index_path(client_name):
    """客户 AI 可读索引 MD 路径。"""
    _validate_client_name(client_name)
    return os.path.join(CLIENTS_DIR, client_name, "client_index.md")


# 内部账本区（Wave2 #48/D2 作用域治理）：clients/ 顶层 `_` 前缀目录 = 内部
# （含 _internal/ 整体），非客户目录（test/通用/工程/专家等）平铺收口于此。
INTERNAL_CLIENTS_DIRNAME = "_internal"


def list_client_dirs(include_internal=False, clients_dir=None):
    """返回 clients/ 下客户目录名（读端枚举唯一收口，#48/D2）。

    默认跳过 `_` 前缀内部目录（含 _internal/ 整体）与 `.` 隐藏目录；
    include_internal=True 时内部目录一并返回。clients_dir 供单测注入
    tmp 目录，默认读全局 CLIENTS_DIR。
    """
    root = clients_dir or CLIENTS_DIR
    if not os.path.isdir(root):
        return []
    return [n for n in os.listdir(root)
            if not n.startswith(".")
            and os.path.isdir(os.path.join(root, n))
            and (include_internal or not n.startswith("_"))]


def client_dir(client_name, clients_dir=None):
    """按名解析客户目录绝对路径（写入端按名解析统一入口，#48/D2）。

    解析顺序：顶层存在 -> 顶层；_internal/{名} 存在 -> 内部账本位；
    两处都不存在 -> 顶层（新建客户默认落顶层，_internal/ 不自动扩散）。
    clients_dir 供单测注入 tmp 目录，默认读全局 CLIENTS_DIR。
    """
    _validate_client_name(client_name)
    root = clients_dir or CLIENTS_DIR
    top = os.path.join(root, client_name)
    if os.path.isdir(top):
        return top
    internal = os.path.join(root, INTERNAL_CLIENTS_DIRNAME, client_name)
    if os.path.isdir(internal):
        return internal
    return top


def is_internal_client_dir(client_path, clients_dir=None):
    """目录路径是否位于 _internal/ 内部账本区（save 跳过 graph/worldbook 等判断用）。

    clients_dir 供单测注入；relpath 跨盘符（Windows ValueError）一律视为非内部。
    """
    root = clients_dir or CLIENTS_DIR
    try:
        rel = os.path.relpath(os.path.abspath(client_path), root)
    except ValueError:
        return False
    return (rel == INTERNAL_CLIENTS_DIRNAME
            or rel.startswith(INTERNAL_CLIENTS_DIRNAME + os.sep))


def rel_to_script(path):
    """相对项目根的展示路径；跨盘符（Windows ValueError）回退为绝对路径。

    CI（GitHub Windows runner）工作区在 D:、TEMP 在 C:，对 tmp_path 产物做
    `os.path.relpath(fpath, SCRIPT_DIR)` 会抛 ValueError 把整条链打断（2026-09-08
    CI 实证：save/audit/breeding/theme 四处）。本函数只用于展示与登记，不参与
    路径拼接，回退绝对路径即可保证调用方继续。
    """
    abs_path = os.path.abspath(path)
    try:
        return os.path.relpath(abs_path, SCRIPT_DIR)
    except ValueError:
        return abs_path


# Windows 保留设备名（P2-2）：作为目录名会指向设备而非文件系统
_WINDOWS_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _validate_client_name(client_name):
    """校验客户名不含路径遍历字符、盘符与 Windows 设备名（P2-2）。

    `C:foo` 这类盘符相对路径经 os.path.join 会整段丢弃前缀
    （Python 3.12 实测），仅拦分隔符拦不住；设备名（CON/NUL/COM1 等）
    作为目录名会指向设备而非文件系统。均一律拒绝。
    """
    if not client_name or ".." in client_name or os.sep in client_name or "/" in client_name or "\\" in client_name:
        raise ValueError(f"非法客户名: {client_name!r}")
    drive, _ = os.path.splitdrive(client_name)
    if drive:
        raise ValueError(f"非法客户名（含盘符）: {client_name!r}")
    stem = client_name.split(".")[0].strip().upper()
    if stem in _WINDOWS_DEVICE_NAMES:
        raise ValueError(f"非法客户名（Windows 设备名）: {client_name!r}")


# ============================================================
# 读边界白名单（D3 拍板 2026-09-06）：工作区 + `--allow-outside` 显式旗标。
# inbox/output/_knowledge 均在工作区树内；对照样板 _indexer._is_valid_proj_key。
# ============================================================

class ReadPathNotAllowedError(Exception):
    """读路径不在工作区白名单内。"""


def _validate_read_path(path, allow_outside=False):
    """读边界守卫（P2-4）：仅允许工作区（SCRIPT_DIR 树）内路径。

    - 默认拒绝仓外读取（提示注入面 + 逃逸面，实弹见安全审查报告 1a 族）；
    - allow_outside=True 为用户显式放行（--allow-outside 旗标），仅归一化返回；
    - realpath 解析 junction/symlink——已存在祖先指仓外同样拒绝（P2-8）。

    返回归一化绝对路径；拒绝抛 ReadPathNotAllowedError。
    """
    if not path or not isinstance(path, str):
        raise ReadPathNotAllowedError(f"非法读路径: {path!r}")
    abs_path = os.path.abspath(path)
    if allow_outside:
        return abs_path
    # normcase 只用于比较（大小写/斜杠归一），返回值保留原形态供下游显示
    real = os.path.normcase(os.path.realpath(abs_path))
    workspace = os.path.normcase(os.path.realpath(SCRIPT_DIR))
    try:
        if os.path.commonpath([real, workspace]) == workspace:
            return abs_path
    except ValueError:
        pass  # 不同盘符，commonpath 无法比较
    raise ReadPathNotAllowedError(
        f"读路径不在工作区白名单内: {path}（仓外文件请加 --allow-outside 显式放行）")


def validate_read_path_lenient(path, allow_outside=False):
    """_validate_read_path 的 no-raise 变体：拒绝时打印原因返回 None。

    材料扫描类调用方（read_materials）逐文件跳过而非中断；print 放
    本层保证「拒绝原因」文案单点。返回归一化绝对路径或 None。
    """
    try:
        return _validate_read_path(path, allow_outside=allow_outside)
    except ReadPathNotAllowedError as e:
        print(f"  跳过（{e}）")
        return None


# HMAC 签名密钥（基于项目路径派生，不硬编码）
_HMAC_KEY = hashlib.sha256(SCRIPT_DIR.encode("utf-8")).digest()


def safe_pickle_load(path):
    """安全加载 pickle 文件：带 HMAC 签名校验（fail-closed）。

    完整性校验：防误写、损坏与意外篡改。密钥由公开项目路径派生（非机密），
    能写文件的攻击者可重算签名，故不构成对抗恶意攻击者的 RCE 防线；
    真正的防线是「无签名一律拒绝」+ 全库 np.load 不开 allow_pickle。
    签名格式：文件前 32 字节为 HMAC-SHA256，其余为 pickle 数据。
    无签名（含长度 ≤32）或签名不匹配一律拒绝，返回 None——
    调用方（_bm25 / _embed_index）已有 None 降级路径，绝不降级裸 pickle.load。
    """
    with open(path, "rb") as f:
        data = f.read()

    if len(data) <= 32:
        return None

    sig = data[:32]
    payload = data[32:]
    expected_sig = hmac_new(payload)
    if not hmac_compare(sig, expected_sig):
        return None
    return pickle.loads(payload)  # nosec B301 - HMAC-SHA256 签名校验通过后才反序列化


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
