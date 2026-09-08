# -*- coding: utf-8 -*-
"""统一云端 LLM 接口：Chat / Embedding / Rerank / 结构化提取。

增强特性：
  - Provider fallback 链（主 provider 失败自动切换）
  - 指数退避重试（429/5xx 最多 3 次）
  - Token 用量追踪（日志记录）
  - 统一 prompt 模板管理
  - 防幻觉机制（强制引用 + 未提及合法 + 温度=0）

环境变量：
  LLM_PROVIDER=deepseek|mimo|minimax（默认 deepseek）
  DEEPSEEK_API_KEY / MIMO_API_KEY / MINIMAX_API_KEY
  ZHIPU_API_KEY 或 GLM_API_KEY（智谱 Embedding）
  DEBUG_REMOTE_ECHO=1（调试回显：HTTP 错误响应体 / host-mode prompt 全文；默认截断防泄密）
"""
import os
import json
import re
import threading

from _paths import USAGE_LOG, CLIENTS_DIR, SCRIPT_DIR

try:
    from _cli_infra import _load_dotenv
    _load_dotenv()
except ImportError:
    pass

# --- #57/Q2 方案A（2026-09-06）：HTTP 传输层下沉 _cloud_transport（真源）。
# 此处转载保 _cloud_llm._post_json 等别名可用：存量测试 patch("_cloud_llm._post_json")
# 零强制迁移（chat/embed/rerank 等母文件内路径经本模块全局名解析，打点仍命中）。
from _cloud_transport import _DEBUG_ECHO_ENV, _debug_echo_enabled, _post_json

# ============================================================
# I-1 出域开关：cloud_policy = full | embedding_only | off
# ============================================================
_CLOUD_POLICY_VALUES = ("full", "embedding_only", "off")


def resolve_cloud_policy(client_name=None, clients_dir=None, config_path=None):
    """客户出域策略：full（默认）| embedding_only | off。

    优先级：客户目录 cloud_policy.yml > recall_config.yml 全局 > 默认 full。
    非法值回退（打印警告）；client_name 为空恒返回 full（向后兼容，不限制
    无客户上下文的调用方）。
    """
    if not client_name:
        return "full"
    clients_dir = clients_dir or CLIENTS_DIR
    _cfg = os.path.join(clients_dir, client_name, "cloud_policy.yml")
    if os.path.exists(_cfg):
        try:
            import yaml
            with open(_cfg, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            v = data.get("cloud_policy", "")
            if isinstance(v, bool):
                # YAML 1.1 布尔：off/no/false → False；on/yes/true → True
                v = "off" if v is False else "full"
            else:
                v = str(v).strip().lower()
            if v in _CLOUD_POLICY_VALUES:
                return v
            print(f"[cloud-policy] 客户 {client_name} 配置值非法({v})，回退全局/默认")
        except Exception as e:
            print(f"[cloud-policy] 读取 {client_name} cloud_policy 失败: {e}")
    try:
        import yaml
        with open(config_path or os.path.join(SCRIPT_DIR, "recall_config.yml"),
                  encoding="utf-8") as f:
            g = yaml.safe_load(f) or {}
        v = g.get("cloud_policy", "full")
        if isinstance(v, bool):
            v = "off" if v is False else "full"
        else:
            v = str(v).strip().lower()
        if v in _CLOUD_POLICY_VALUES:
            return v
    except Exception:
        pass
    return "full"


def _policy_allows(client_name, kind):
    """熔断判定：off 全熔断；embedding_only 熔断 chat/rerank。True=放行。"""
    policy = resolve_cloud_policy(client_name)
    if policy == "off":
        return False
    if policy == "embedding_only" and kind in ("chat", "rerank"):
        return False
    return True

# ============================================================
# Host 模式开关：LLM_MODE=host 时不调云端 API，改打印 prompt 由宿主 AI 执行
# ============================================================
LLM_MODE = os.environ.get("LLM_MODE", "cloud")  # cloud=云端 API（默认） | host=打印 prompt 由宿主 AI 执行

# ============================================================
# Provider 配置
# ============================================================
PROVIDERS = {
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "ZHIPU_API_KEY",
        "chat_model": "glm-5.2",
        "reasoning_model": "glm-5.2",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "chat_model": "deepseek-v4-flash",
        "reasoning_model": "deepseek-v4-pro",
    },
    "mimo": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "key_env": "MIMO_API_KEY",
        "chat_model": "mimo-v2.5",
        "reasoning_model": "mimo-v2.5-pro",
    },
    "minimax": {
        # Token Plan/国内站 key 用 https://api.minimaxi.com/v1（MINIMAX_BASE_URL 覆盖）
        "base_url": os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
        "key_env": "MINIMAX_API_KEY",
        "chat_model": "MiniMax-M3",
        "reasoning_model": "MiniMax-M3",
    },
}

# fallback 顺序：主 provider 挂了依次尝试下一个
FALLBACK_CHAIN = ["zhipu", "deepseek", "minimax"]

# thinking 控制参数映射（per-provider 隔离，P0-1 参数化，2026-07-21）
# 拍板：质量 > token，thinking 默认全开——本表只控制"怎么开"，不控制"开不开"
#   zhipu:    thinking.type=enabled（reasoning_effort 默认即 max）
#   deepseek: thinking enabled + reasoning_effort=max（最大推理强度，与质量优先一致）
#   minimax:  adaptive 默认开启、API 不可控，无需参数（故无条目）
# 预留：Trae 环境接入 OpenAI / Anthropic 系时在此补映射位
THINKING_PAYLOAD = {
    "zhipu": {"thinking": {"type": "enabled"}},
    "deepseek": {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
}

# W1-1（#37，2026-09-06 B6 Wave1）：task 级 thinking 参数覆盖，chat() 内后写
# 覆盖 THINKING_PAYLOAD 的 provider 全局默认。post_generate_review 是审查型
# 任务：deepseek reasoning_effort=max 时思维链烧光 completion 配额（review
# 初调撞墙加倍到 12000 仍 length 截断），降 medium 保审查通道可用；
# 未列出的 task/provider 维持全局默认（质量优先不整体松动）。
TASK_THINKING_OVERRIDE = {
    "post_generate_review": {"deepseek": {"reasoning_effort": "medium"}},
}

# P0-1 max_tokens 自适应（2026-07-21）：glm-5.2 / deepseek 等推理模型的 reasoning
# 计入 completion 配额，非 thinking 时代的 max_tokens 遗产会顶格截断 JSON
THINKING_TOKEN_MULTIPLIER = 3   # thinking 开启时 max_tokens 余量倍率
THINKING_TOKEN_FLOOR = 4000     # thinking 开启时 max_tokens 下限
MAX_TOKENS_RETRY_CEILING = 16000  # finish_reason=length 撞墙加倍重试的上限：
# 须覆盖 thinking 余量后的 effective（4000×3=12000 撞墙可翻至 16000）——
# 8000 时代架构章节（最需要撞墙重试的场景）永远进不了重试分支（死代码）；
# zhipu 端若拒绝超大 max_tokens，由 _post_json 现有 400 处理兜底（None 走 fallback）

EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
ZHIPU_EMBED_MODEL = "embedding-3-pro"

# ============================================================
# 能力边界动态策略（L3/L4/L5 三模式 + creative 创意模式）
# ============================================================
# L3 directed: 人给框架 AI 填充，严格按指导执行（temperature 低）
# L4 collaborative: AI 主导人确认，边界内探索（temperature 中）
# L5 autonomous: AI 全自动可重跑，可跨越边界尝试（temperature 高）
# creative: 灵感/发散/头脑风暴模式，不追求确定性（temperature 极高）
MODE_PROFILES = {
    "directed": {
        "temperature": 0.15,
        "prompt_prefix": "严格按以下指导执行，不自由扩展：",
    },
    "collaborative": {
        "temperature": 0.3,
        "prompt_prefix": "在以下边界内探索，关键节点确认：",
    },
    "autonomous": {
        "temperature": 0.4,
        "prompt_prefix": "充分应用你的能力，可跨越边界尝试：",
    },
    "creative": {
        "temperature": 0.8,
        "prompt_prefix": "你现在处于创意发散模式。大胆联想、给出多个不同方向的方案、允许不完美和不完整。不要自我审查，不要追求确定性，不要只给一个安全的答案。优先考虑多样性和新颖性：",
    },
}


def _apply_mode(system, temperature, mode):
    """按 mode 调整 system prompt 和 temperature。mode=None 时原样返回。"""
    if mode is None or mode not in MODE_PROFILES:
        return system, temperature
    profile = MODE_PROFILES[mode]
    prefix = profile["prompt_prefix"]
    new_system = f"{prefix}\n{system}" if system else prefix
    return new_system, profile["temperature"]

# ============================================================
# Prompt 模板（防幻觉核心）
# ============================================================
EXTRACT_SYSTEM = """你是数据提取助手。严格遵守以下规则：
1. 只从【给定文本】中提取信息，禁止推断、猜测、补充
2. 如果文本中没有相关信息，填写"未提及"，不要编造
3. 数字必须原文引用，禁止四舍五入或换算
4. 每条提取必须标注来源段落编号（如"第2段"）
5. 输出严格 JSON 格式，不要任何解释"""

RERANK_SYSTEM = """你是文档相关性排序助手。只根据候选片段与查询的相关程度打分。
- 严格基于片段内容判断，不要假设片段包含未提及的信息
- 如果片段与查询完全无关，打 0 分
- 只返回结果，不要解释"""

QUALITY_CHECK_SYSTEM = """你是方案质量检查助手。检查方案是否满足以下要求，逐项打分(0-10)：
1. 信息密度：是否有实质内容（非空话套话）
2. 数据支撑：关键论点是否有数字/案例支撑
3. 痛点-方案对应：每个痛点是否有对应方案
4. 可执行性：方案是否具体到可落地
严格返回 JSON，不要解释。"""

# 视觉识别防幻觉约束（P-vision-2：vision_chat 始终注入，堵图片识别编造黑洞）
VISION_SYSTEM = """你是图片识别助手。严格遵守以下规则：
1. 只描述图片中真实可见的内容，禁止推断、猜测或补充图中不存在的信息
2. 图中的文字必须原文摘录，禁止改写、翻译或扩写；看不清的文字标注"[文字模糊]"而非臆测
3. 数字、日期、金额、百分比等必须原文引用，禁止四舍五入或换算
4. 无法确定的内容明确标注"不确定"，宁可少说也不编造
5. 用中文回答
6. 每条结论按可见性分类（参考 ds-vision 证据契约）：直接可见、可逐字核验的事实归 visible_fact；基于视觉的推断性判断（风格、意图、语义、属性猜测）归 image_candidate；无法辨认或图中不存在、无法回答的项归 unknown。禁止把推断写成事实"""

# 结构化输出模板（vision-describe --format json 用；uncertain 字段承接规则 4 的不确定项；
# evidence 三态承接规则 6 的可见性分类：visible_fact / image_candidate / unknown）
VISION_JSON_TEMPLATE = ('\n只输出 JSON，不要输出任何 JSON 之外的文字或解释：'
                        '{"summary": "一段总述", "extracted_text": "图中全部文字原文摘录", '
                        '"objects": ["主要对象"], "layout": "版式结构", '
                        '"uncertain": ["不确定或无法辨认的内容"], '
                        '"evidence": {"visible_fact": ["图中直接可见、可逐字核验的事实"], '
                        '"image_candidate": ["基于视觉的推断性判断（需人工或二次核验）"], '
                        '"unknown": ["无法辨认或图中不存在、无法回答的项"]}}')

# 识图输出配额：minimax adaptive thinking 计入 completion，给足余量防 JSON 截断
VISION_MAX_TOKENS = 4000
# 图片大小上限（base64 前字节数）；超限 API 直接拒，提前拦掉给明确报错
VISION_MAX_IMAGE_BYTES = 15 * 1024 * 1024


# ============================================================
# 内部工具
# ============================================================
def _get_provider():
    name = os.environ.get("LLM_PROVIDER", "zhipu").lower()
    if name not in PROVIDERS:
        name = "deepseek"
    return name, PROVIDERS[name]


def _get_api_key(cfg, provider_name=""):
    key = os.environ.get(cfg["key_env"], "")
    # P0-8：fallback 仅对 zhipu provider 生效，避免 deepseek/mimo/minimax 误用 zhipu 的 key
    if not key and provider_name == "zhipu":
        key = os.environ.get("GLM_API_KEY", "") or os.environ.get("ZHIPU_API_KEY", "")
    if key and not key.isascii():
        return ""
    return key.strip()


def _log_usage(provider, model, prompt_tokens, completion_tokens, task="", cached_tokens=0,
               reasoning_tokens=0, image_tokens=0, cache_hit_tokens=0, cache_miss_tokens=0):
    """记录 token 用量到日志。

    cached_tokens: P1 优化（2026-07-20）- zhipu glm-5.2 隐式缓存命中的 token 数
    缓存命中部分按更低价格计费（通常 10%），用于验证 prompt cache 效果。
    reasoning_tokens: P1-2（2026-07-21）- thinking 模式思维链消耗的 token 数
    （glm-5.2 / deepseek 等 reasoning 计入 completion 配额），思维链预算的数据基础。
    image_tokens: P1-1（2026-07-21）- vision 调用中图片消耗的 token 数，
    各家 usage 结构不一，防御式提取，缺失记 0 不报错。
    cache_hit_tokens / cache_miss_tokens: DeepSeek 官方字段（2026-08-13），
    精确拆分前缀缓存命中/未命中 token，用于监控命中率（0.1 元/M vs 1 元/M，10 倍价差）。
    """
    from datetime import datetime
    os.makedirs(os.path.dirname(USAGE_LOG), exist_ok=True)
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "task": task,
    }
    if cached_tokens > 0:
        entry["cached_tokens"] = cached_tokens
    if reasoning_tokens > 0:
        entry["reasoning_tokens"] = reasoning_tokens
    if image_tokens > 0:
        entry["image_tokens"] = image_tokens
    if cache_hit_tokens > 0:
        entry["cache_hit_tokens"] = cache_hit_tokens
    if cache_miss_tokens > 0:
        entry["cache_miss_tokens"] = cache_miss_tokens
    try:
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_available_providers():
    """返回当前有 key 的 provider 列表（按 fallback 顺序）。"""
    available = []
    for name in FALLBACK_CHAIN:
        cfg = PROVIDERS[name]
        if _get_api_key(cfg, name):
            available.append(name)
    return available


# #43（B6 Wave3）：provider 卫生熔断——key 存在但失效（HTTP 错误/持续空 content）
# 时跨调用记忆失败连击，连败达阈值在进程内跳过该 provider，防每轮调用都先撞
# 一次死链（附册 §1.2：无 key 本就零成本，防的是「key 存在但失效」）。成功清零；
# 仅进程内生效，新进程重试给失效 key 恢复机会。
_PROVIDER_FAIL_STREAK: dict = {}
_PROVIDER_FAIL_MAX = 3


def _fail_streak_bump(pname):
    n = _PROVIDER_FAIL_STREAK.get(pname, 0) + 1
    _PROVIDER_FAIL_STREAK[pname] = n
    if n == _PROVIDER_FAIL_MAX:
        print(f"[cloud_llm] {pname} 连续失败 {n} 次，本进程内卫生跳过"
              f"（key 存在但疑似失效；新进程自动重试）")


def host_prompt(task, prompt, system="", image_path=None):
    """LLM_MODE=host 时打印推理请求，由宿主 AI 执行；返回 None 表示调用方应中止后续解析。

    安全（安全审查 P3）：prompt 常携带客户材料，默认只记长度+前 80 字符
    （格式对齐 _cloud_llm_vision._host_prompt_brief），防材料全文落会话日志；
    设 DEBUG_REMOTE_ECHO=1 时输出全文（调试用）。
    """
    if LLM_MODE != "host":
        return None
    print("\n[host-mode] 以下推理交由宿主 AI 执行（LLM_MODE=host）：")
    print(f"[host-mode] task={task}" + (f" image={image_path}" if image_path else ""))
    if system:
        print(f"[host-mode system] {system}")
    if _debug_echo_enabled():
        print(f"[host-mode prompt] {prompt}\n")
    else:
        head = (prompt or "")[:80]
        print(f"[host-mode prompt] 长度={len(prompt or '')} 字符"
              f"（安全截断，仅前 80 字符预览）: {head}..."
              f"（全文回显需显式开 {_DEBUG_ECHO_ENV}=1）\n")
    return None


# ============================================================
# Chat：统一对话接口（带 fallback）
# ============================================================
def _strip_think(text):
    """剥掉推理模型的 <think>...</think> 段（MiniMax-M3 等），只留正文。"""
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _is_length_truncated(data):
    """finish_reason=length 检测（provider 无关，各家均返回 finish_reason；防御式）。"""
    try:
        return (data.get("choices") or [{}])[0].get("finish_reason") == "length"
    except Exception:
        return False


def chat(prompt, system="", provider=None, model_type="chat", model=None,
         temperature=0.1, max_tokens=2000, json_mode=False, task="", mode=None,
         client_name=None):
    """统一 Chat 接口。返回文本或 None。

    provider: 强制指定 provider 名，None 时用环境变量 + fallback
    model_type: "chat"（快+便宜）或 "reasoning"（强推理）
    model: 可选模型覆盖（F5-2 用于 review 独立模型；None 用 provider 默认）
    json_mode: True 时要求输出 JSON
    task: 用途标签（用于 token 追踪日志）
    mode: 能力边界模式（directed/collaborative/autonomous），None 时用传入的 temperature
    client_name: 指定客户时按其 cloud_policy 熔断（off/embedding_only 返回 None）。
    """
    if not _policy_allows(client_name, "chat"):
        return None
    if LLM_MODE == "host":
        host_prompt(task, prompt, system)
        return None

    # mode 覆盖 temperature 和 system（L3/L4/L5 能力边界动态策略）
    system, temperature = _apply_mode(system, temperature, mode)

    # 确定 provider 列表
    if provider:
        providers_to_try = [provider]
    else:
        primary, _ = _get_provider()
        available = _get_available_providers()
        # #43 卫生熔断：连败达阈值的 provider 本进程内让位（显式指定 provider
        # 时不拦，保留人工诊断通道）
        available = [p for p in available
                     if _PROVIDER_FAIL_STREAK.get(p, 0) < _PROVIDER_FAIL_MAX]
        # primary 已熔断则直接从 fallback 起（不拦显式指定，见上）
        if primary in available:
            providers_to_try = [primary] + [p for p in available if p != primary]
        else:
            providers_to_try = available

    if not providers_to_try:
        print("[cloud_llm] 没有可用的 provider（未设置任何 API KEY）")
        return None

    last_error = None
    explicit_model = model  # P1-16：显式模型覆盖仅首轮生效；fallback 各轮
    for idx, pname in enumerate(providers_to_try):  # 必须用当轮 provider 自家模型名
        cfg = PROVIDERS.get(pname)
        if not cfg:
            continue
        key = _get_api_key(cfg, pname)
        if not key:
            continue

        model = explicit_model if (explicit_model and idx == 0) else cfg.get(
            f"{model_type}_model", cfg["chat_model"])

        # 思考模式 provider 列表：这些 provider 会开启 thinking，并要求中文思考
        thinking_providers = {"deepseek", "zhipu", "minimax"}
        use_thinking = pname in thinking_providers

        # 要求思考过程用中文（仅对开启思考模式的 provider 生效）。
        # 用 req_system 局部变量拼接——直接改 system 会在 fallback
        # 循环内重复追加同一 hint（每轮 thinking provider 各加一次）
        req_system = system
        if use_thinking:
            chinese_thinking_hint = "[请务必使用中文进行思考过程（reasoning_content），最终回答也用中文。]"
            req_system = "\n\n".join(p for p in (system, chinese_thinking_hint) if p)

        messages = []
        if req_system:
            messages.append({"role": "system", "content": req_system})
        messages.append({"role": "user", "content": prompt})

        # P0-1（2026-07-21 拍板：质量 > token，thinking 全开）：reasoning 计入
        # completion 配额，thinking 开启时 max_tokens 自动加 reasoning 余量
        #（基础值 ×3，下限 4000），防 glm-5.2 等推理模型顶格截断 JSON
        effective_max_tokens = max_tokens
        if use_thinking:
            effective_max_tokens = max(max_tokens * THINKING_TOKEN_MULTIPLIER,
                                       THINKING_TOKEN_FLOOR)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": effective_max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # thinking 控制参数（per-provider 映射集中管理，P0-1 参数化；
        # minimax adaptive 不可控无条目，行为与原来一致）
        if use_thinking:
            payload.update(THINKING_PAYLOAD.get(pname, {}))
            # W1-1（#37）：task 级覆盖后写生效，只收窄不放宽全局默认
            payload.update(TASK_THINKING_OVERRIDE.get(task, {}).get(pname, {}))

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        data, status = _post_json(
            f"{cfg['base_url']}/chat/completions", headers, payload,
            timeout=max(30, effective_max_tokens // 10)
        )

        # P0-1 撞墙兜底：finish_reason=length -> max_tokens 加倍重试一次
        #（上限 MAX_TOKENS_RETRY_CEILING=16000，覆盖 thinking 余量后的
        # effective；重试条件同一常量，同步生效）。provider 无关（各家均
        # 返回 finish_reason），不依赖人工逐 task 调参
        if data and _is_length_truncated(data) and \
                payload["max_tokens"] < MAX_TOKENS_RETRY_CEILING:
            retry_tokens = min(payload["max_tokens"] * 2, MAX_TOKENS_RETRY_CEILING)
            print(f"[cloud_llm] {pname} finish_reason=length，max_tokens "
                  f"{payload['max_tokens']} -> {retry_tokens} 重试一次")
            payload["max_tokens"] = retry_tokens
            data, status = _post_json(
                f"{cfg['base_url']}/chat/completions", headers, payload,
                timeout=max(30, retry_tokens // 10)
            )

        if data:
            try:
                choice = data["choices"][0]
                content = _strip_think(choice.get("message", {}).get("content", ""))
                # P0-1 补充（2026-09-06）：thinking provider 可能把 completion 配额
                # 全烧在 reasoning_content 上，最终 content 为空/纯空白。空内容不是
                # 可用回答，继续 fallback 到下一个 provider；否则 review 会误判为
                # 「无可用 provider」并返回 ERROR（实为 deepseek 空 content 通道病）。
                if not content or not content.strip():
                    finish_reason = choice.get("finish_reason", "?")
                    last_error = f"{pname} 返回空内容（finish_reason={finish_reason}）"
                    _fail_streak_bump(pname)
                    continue
                # token 用量追踪
                usage = data.get("usage", {})
                # P1 优化：提取缓存命中 token（zhipu glm-5.2 隐式缓存）
                prompt_details = usage.get("prompt_tokens_details", {}) or {}
                cached_tokens = prompt_details.get("cached_tokens", 0) or 0
                # P1-2（2026-07-21）：思维链计量。照抄 cached_tokens 防御模式——
                # zhipu / deepseek / OpenAI 系字段结构不同、glm-4-flash 等无此字段，缺失记 0
                completion_details = usage.get("completion_tokens_details", {}) or {}
                reasoning_tokens = completion_details.get("reasoning_tokens", 0) or 0
                # DeepSeek 官方缓存字段（2026-08-13）：精确拆分前缀缓存命中/未命中，
                # 用于监控命中率；zhipu 无此字段，防御式提取记 0
                cache_hit_tokens = usage.get("prompt_cache_hit_tokens", 0) or 0
                cache_miss_tokens = usage.get("prompt_cache_miss_tokens", 0) or 0
                _log_usage(
                    pname, model,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    task=task,
                    cached_tokens=cached_tokens,
                    reasoning_tokens=reasoning_tokens,
                    cache_hit_tokens=cache_hit_tokens,
                    cache_miss_tokens=cache_miss_tokens,
                )
                _PROVIDER_FAIL_STREAK[pname] = 0  # #43：成功清零连击
                return content
            except (KeyError, IndexError):
                last_error = f"响应解析失败: {json.dumps(data, ensure_ascii=False)[:200]}"
                _fail_streak_bump(pname)
        else:
            last_error = f"{pname} HTTP {status}"
            _fail_streak_bump(pname)

    if last_error:
        print(f"[cloud_llm] 所有 provider 均失败: {last_error}")
    return None


# ============================================================
# Embedding：智谱 embedding-3-pro 优先，SiliconFlow BGE-m3 兜底
# ============================================================
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
SILICONFLOW_EMBED_MODEL = "BAAI/bge-m3"


def current_embed_provider():
    """返回当前可用的 embedding provider (name, model)；无可用 key 返回 None。

    顺序：智谱 embedding-3-pro（4096 维，索引实测口径）→ SiliconFlow BGE-m3（1024 维）。
    两个模型向量空间不兼容，切换 provider/模型后需 embed-rebuild --force 重建索引。
    """
    if os.environ.get("ZHIPU_API_KEY", "") or os.environ.get("GLM_API_KEY", ""):
        return ("zhipu", ZHIPU_EMBED_MODEL)
    if os.environ.get("SILICONFLOW_API_KEY", ""):
        return ("siliconflow", SILICONFLOW_EMBED_MODEL)
    return None


def embed(text, dimensions=None, client_name=None):
    """单条 embedding，返回向量 list[float] 或 None。

    client_name: 指定客户时按其 cloud_policy 熔断（off 返回 None）。
    """
    vecs = embed_batch([text], dimensions=dimensions, client_name=client_name)
    return vecs[0] if vecs else None


def embed_batch(texts, dimensions=None, client_name=None):
    """批量 embedding。返回 list[list[float]] 或 None。

    client_name: 指定客户时按其 cloud_policy 熔断（off 返回 None）。
    """
    if not _policy_allows(client_name, "embed"):
        return None
    provider = current_embed_provider()
    if not provider:
        return None
    name, model = provider
    if name == "zhipu":
        key = os.environ.get("ZHIPU_API_KEY", "") or os.environ.get("GLM_API_KEY", "")
        url = EMBEDDING_URL
    else:
        key = os.environ.get("SILICONFLOW_API_KEY", "")
        url = SILICONFLOW_EMBED_URL

    payload = {"model": model, "input": texts}
    if dimensions:
        payload["dimensions"] = dimensions

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    data, _ = _post_json(url, headers, payload, timeout=30)
    if not data:
        return None

    try:
        items = sorted(data["data"], key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]
    except (KeyError, IndexError):
        return None


# ============================================================
# Rerank：LLM 精排（防幻觉版）
# ============================================================
def rerank(query, candidates, top_k=5, provider=None, mode="directed", client_name=None):
    """LLM rerank。

    candidates: [(client, score, path, snippet), ...] 或 [(path, snippet), ...]
    返回 rerank 后的 top_k 列表（保持输入格式）。
    mode: 能力边界模式，默认 directed（rerank 需严格）
    client_name: 指定客户时按其 cloud_policy 熔断（off/embedding_only 返回 None）。
    """
    if not _policy_allows(client_name, "rerank"):
        return None
    if not candidates:
        return candidates

    lines = [f"查询：{query}\n", "候选片段（按编号）："]
    for i, item in enumerate(candidates[:20], 1):
        if len(item) == 4:
            client, score, path, snippet = item
            text = (snippet or "")[:200].replace("\n", " ")
            lines.append(f"{i}. [{client}] {text}")
        else:
            _path, snippet = item[0], item[1] if len(item) > 1 else ""
            text = (snippet or "")[:200].replace("\n", " ")
            lines.append(f"{i}. {text}")

    lines.append(f"\n请按与查询的相关性打分(0-10)，返回最相关的 {top_k} 个编号。")
    lines.append("格式：编号:分数,编号:分数,...（只返回结果，不要解释）")

    prompt = "\n".join(lines)
    resp = chat(prompt, system=RERANK_SYSTEM, provider=provider,
                temperature=0.0, task="rerank", mode=mode)
    if not resp:
        return candidates[:top_k]

    try:
        ranked = []
        for item in resp.strip().split(","):
            item = item.strip()
            if ":" in item:
                idx_str, score_str = item.split(":", 1)
                idx = int(idx_str.strip()) - 1
                new_score = float(score_str.strip())
                if 0 <= idx < len(candidates):
                    orig = candidates[idx]
                    if len(orig) == 4:
                        ranked.append((orig[0], new_score, orig[2], orig[3]))
                    elif len(orig) == 3:
                        ranked.append((orig[0], new_score, orig[2]))
                    else:
                        ranked.append((orig[0], new_score))
        if ranked:
            return ranked[:top_k]
    except Exception as e:
        print(f"[cloud_llm] rerank 解析失败: {e}")

    return candidates[:top_k]


# ============================================================
# Rerank：Silicon Flow 专用（BGE-reranker-v2-m3）
# ============================================================
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"


def _siliconflow_key():
    """从环境变量读 Silicon Flow API Key。空值返回 None。"""
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not key or not key.isascii():
        return None
    return key


def siliconflow_rerank(query, candidates, top_k=5, alpha=0.7, client_name=None):
    """调用 Silicon Flow 的 BGE-reranker-v2-m3 精排。

    输入 candidates 与 rerank() 格式一致：
      - 4 元素: (client, rrf_score, path, snippet)
      - 2 元素: (path, snippet)
    返回 top_k 列表，按融合分数降序。

    分数融合：final = alpha * rerank_score + (1-alpha) * rrf_score
      - alpha=0.7：Reranker 主导，RRF 兜底防误判
      - RRF 分数归一化到 [0,1]，避免量纲不一致

    Key 缺失或调用失败时返回 None，调用方应回退到 LLM rerank。
    client_name: 指定客户时按其 cloud_policy 熔断（off/embedding_only 返回 None）。
    """
    if not _policy_allows(client_name, "rerank"):
        return None
    if not candidates:
        return candidates

    key = _siliconflow_key()
    if not key:
        return None

    # 提取 rrf 原始分数用于融合（4 元素时第 2 位是 rrf_score）
    rrf_scores = []
    for item in candidates[:20]:
        if len(item) >= 4:
            rrf_scores.append(float(item[1]) if item[1] else 0.0)
        else:
            rrf_scores.append(0.0)
    # RRF 分数归一化到 [0,1]
    max_rrf = max(rrf_scores) if rrf_scores else 1.0
    if max_rrf <= 0:
        max_rrf = 1.0
    rrf_norm = [s / max_rrf for s in rrf_scores]

    # Silicon Flow rerank 接口要求 documents 为字符串列表
    docs = []
    for item in candidates[:20]:
        if len(item) >= 4:
            text = (item[3] or "")[:500]
        else:
            text = (item[1] if len(item) > 1 else "") or ""
        docs.append(text.replace("\n", " "))

    payload = {
        "model": os.environ.get("SILICONFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
        "query": query,
        "documents": docs,
        "top_n": min(top_k, len(docs)),
        "return_documents": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    data, status = _post_json(
        f"{SILICONFLOW_BASE_URL}/rerank",
        headers, payload, timeout=30, max_retries=3
    )
    if data is None:
        return None

    # 响应格式: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
    try:
        results = data.get("results", [])
        if not results:
            return None
        ranked = []
        for r in results:
            idx = int(r.get("index", -1))
            rerank_score = float(r.get("relevance_score", 0.0))
            if 0 <= idx < len(candidates):
                orig = candidates[idx]
                # 分数融合：alpha * rerank + (1-alpha) * rrf_norm
                fused = alpha * rerank_score + (1 - alpha) * rrf_norm[idx]
                if len(orig) == 4:
                    ranked.append((orig[0], fused, orig[2], orig[3]))
                else:
                    ranked.append((orig[0], fused))
        # 按融合分数降序
        ranked.sort(key=lambda x: x[1], reverse=True)
        _log_usage("siliconflow", payload["model"], len(query) + sum(len(d) for d in docs),
                   0, task="rerank")
        return ranked[:top_k]
    except Exception as e:
        print(f"[cloud_llm] siliconflow_rerank 解析失败: {e}")
        return None


def _parse_json(text):
    """从 LLM 输出中解析 JSON，尝试多种方式。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ``` 块
    m = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    print(f"[cloud_llm] JSON 解析失败: {text[:200]}")
    return None


def _validate_against_source(result, source_text):
    """防幻觉校验：检查提取的数字是否在原文中出现。"""
    if not isinstance(result, dict):
        return

    # 递归检查所有字符串值中的数字
    def check_value(obj, path=""):
        if isinstance(obj, str):
            # P1-5：用正则边界匹配，避免 "100" in "1000" 漏报
            # 提取数字串（含百分号/单位），检查是否作为独立 token 出现在原文中
            numbers = re.findall(r'\d+(?:\.\d+)?[%万千百十亿万]*', obj)
            for num in numbers:
                if len(num) <= 1:
                    continue
                # 用正则边界匹配：数字前后不能是数字或小数点
                boundary_pattern = r'(?<![\d.])' + re.escape(num) + r'(?![\d])'
                if not re.search(boundary_pattern, source_text):
                    print(f"[cloud_llm] [warn] 幻觉警告: '{num}' 未在原文中找到 (路径: {path})")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                check_value(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_value(v, f"{path}[{i}]")

    check_value(result)


# ============================================================
# 方案质量自评
# ============================================================
def quality_check(proposal_text, provider=None, mode="collaborative"):
    """对方案做质量自评。返回 dict 或 None。

    返回格式：{
      "info_density": {"score": 8, "comment": "..."},
      "data_support": {"score": 6, "comment": "..."},
      "mapping": {"score": 7, "comment": "..."},
      "actionability": {"score": 5, "comment": "..."},
      "overall": 6.5,
      "issues": ["...", "..."]
    }
    mode: 能力边界模式，默认 collaborative（质量评估允许边界内探索）
    """

    prompt = f"""请检查以下方案的质量，按 4 个维度打分（0-10）并给出具体问题。

【强制规则】
1. 必须输出 JSON，key 必须用英文（info_density/data_support/mapping/actionability/overall/issues）
2. 每个 score 是 0-10 的数字（不是字符串）
3. issues 是字符串数组

【方案内容】
{proposal_text[:6000]}"""

    resp = chat(prompt, system=QUALITY_CHECK_SYSTEM, provider=provider,
                temperature=0.0, json_mode=True, task="quality_check", mode=mode)
    if not resp:
        return None

    result = _parse_json(resp)
    # 兼容中文 key（LLM 可能不听话）
    if result:
        key_map = {
            "信息密度": "info_density", "数据支撑": "data_support",
            "痛点-方案对应": "mapping", "可执行性": "actionability",
            "总分": "overall", "问题": "issues",
        }
        for cn, en in key_map.items():
            if cn in result and en not in result:
                result[en] = result[cn]
    return result


# ============================================================
# Token 用量查询
# ============================================================
def get_usage_summary(month=None):
    """读取用量日志，返回汇总统计。

    month: 可选 "YYYY-MM"，只统计该月内 record；None 表示全量（兼容旧调用）。
    """
    if not os.path.exists(USAGE_LOG):
        return {"total_calls": 0, "total_tokens": 0, "by_provider": {}}

    by_provider = {}
    total_calls = 0
    total_tokens = 0
    corrupted = 0  # 损坏行计数：单条跳过不中止全量（尾部统一告警）
    month_prefix = f"{month}-" if month else None

    try:
        with open(USAGE_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 单条损坏行跳过并计数，不中止全量统计（旧实现 try 包住整个
                # 循环，一条坏行会静默吞掉其后全部记录，用量汇总整体失真）
                try:
                    entry = json.loads(line)
                except ValueError:
                    corrupted += 1
                    continue
                if not isinstance(entry, dict):
                    corrupted += 1
                    continue
                ts = entry.get("time", "")
                if month_prefix and not ts.startswith(month_prefix):
                    continue
                total_calls += 1
                total_tokens += entry.get("total_tokens", 0)
                p = entry.get("provider", "unknown")
                if p not in by_provider:
                    by_provider[p] = {"calls": 0, "tokens": 0}
                by_provider[p]["calls"] += 1
                by_provider[p]["tokens"] += entry.get("total_tokens", 0)
    except Exception:
        pass

    if corrupted:
        print(f"[cloud_llm] 用量日志有 {corrupted} 条损坏行，已跳过（不参与统计）")

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "by_provider": by_provider,
    }


# ============================================================
# 可用性检测
# ============================================================
def check_providers():
    """检测各 provider 的可用性。返回 {name: (bool, model)}。"""
    results = {}
    for name in FALLBACK_CHAIN:
        cfg = PROVIDERS[name]
        key = _get_api_key(cfg, name)
        if not key:
            results[name] = (False, "未设置 API KEY")
            continue
        resp = chat("回复OK", provider=name, max_tokens=10, task="health_check")
        results[name] = (resp is not None, cfg["chat_model"])

    zhipu_key = os.environ.get("ZHIPU_API_KEY", "") or os.environ.get("GLM_API_KEY", "")
    if zhipu_key:
        v = embed("测试")
        results["zhipu_embedding"] = (v is not None, ZHIPU_EMBED_MODEL)
    else:
        results["zhipu_embedding"] = (False, "未设置 ZHIPU_API_KEY")

    return results


if __name__ == "__main__":
    print("=== 云端 LLM 可用性检测 ===\n")
    status = check_providers()
    for name, (ok, model) in status.items():
        mark = "OK" if ok else "不可用"
        print(f"  {name}: {mark} ({model})")

    any_ok = any(ok for ok, _ in status.values())

    if any_ok:
        print("\n=== 测试 Chat ===")
        resp = chat("用一句话介绍咨询顾问的工作", task="test")
        print(f"  回复: {resp}")

    if status.get("zhipu_embedding", (False,))[0]:
        print("\n=== 测试 Embedding ===")
        v = embed("数字化转型方案")
        if v:
            print(f"  维度: {len(v)}")
            print(f"  前5维: {v[:5]}")

    print("\n=== Token 用量汇总 ===")
    summary = get_usage_summary()
    print(f"  总调用: {summary['total_calls']} 次")
    print(f"  总 token: {summary['total_tokens']}")
    for p, s in summary["by_provider"].items():
        print(f"  {p}: {s['calls']} 次, {s['tokens']} tokens")


# ============================================================
# 视觉理解：MiniMax M3 多模态
# ============================================================
# 结果缓存上限：超限按最旧（ts 升序）淘汰，防日志目录无限膨胀
VISION_CACHE_MAX_ENTRIES = 200
# 缓存写锁：read_batch 用 ThreadPoolExecutor 并行读图，load-modify-save 需串行防丢条目
_VISION_CACHE_LOCK = threading.Lock()





# === T9 拆分：子模块 re-export（调用方 import 路径不变）===
# 【到期复审】下游（_cli/_cli_cmds_qa/_pipeline 等）仍经此处转载导入 vision/search
# 符号，暂不可删；下游全部直连 _cloud_llm_vision/_cloud_llm_search 后应整体退役
# （对齐 B4 theme 退役先例）。HTTP 真源已下沉 _cloud_transport，
# 两子模块不再经母文件取 _post_json（mother→vision→mother 导入环已断）。
from _cloud_llm_vision import (  # noqa: F401
    vision_chat, vision_describe_ab,
    _vision_cache_get, _vision_cache_load, _vision_cache_put,
)
from _cloud_llm_search import tavily_search, byte_search, web_search  # noqa: F401
# 测试/外部仍经 _cloud_llm.VISION_CACHE 访问
from _paths import VISION_CACHE  # noqa: F401
