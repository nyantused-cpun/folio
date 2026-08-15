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
"""
import os
import json
import time
import re
import hashlib
import threading

from _paths import USAGE_LOG, VISION_CACHE

try:
    from _cli_infra import _load_dotenv
    _load_dotenv()
except ImportError:
    pass

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

# P0-1 max_tokens 自适应（2026-07-21）：glm-5.2 / deepseek 等推理模型的 reasoning
# 计入 completion 配额，非 thinking 时代的 max_tokens 遗产会顶格截断 JSON
THINKING_TOKEN_MULTIPLIER = 3   # thinking 开启时 max_tokens 余量倍率
THINKING_TOKEN_FLOOR = 4000     # thinking 开启时 max_tokens 下限
MAX_TOKENS_RETRY_CEILING = 16000  # finish_reason=length 撞墙加倍重试的上限：
# 须覆盖 thinking 余量后的 effective（4000×3=12000 撞墙可翻至 16000）——
# 8000 时代架构章节（最需要撞墙重试的场景）永远进不了重试分支（死代码）；
# zhipu 端若拒绝超大 max_tokens，由 _post_json 现有 400 处理兜底（None 走 fallback）

EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

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


def _post_json(url, headers, payload, timeout=30, max_retries=3):
    """发 POST 请求，带指数退避重试。返回 (json_dict, http_status) 或 (None, status)。"""
    try:
        import requests
    except ImportError:
        print("[cloud_llm] 需要 requests 库：pip install requests")
        return None, 0

    last_status = 0
    for attempt in range(max_retries):
        try:
            # 用 data + encode 确保 UTF-8 编码，避免 latin-1 问题
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            resp = requests.post(url, headers=headers, data=body, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), 200
            if resp.status_code == 429 or resp.status_code >= 500:
                last_status = resp.status_code
                wait = 2 ** attempt
                print(f"[cloud_llm] HTTP {resp.status_code}，{wait}s 后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"[cloud_llm] HTTP {resp.status_code}: {resp.text[:200]}")
            return None, resp.status_code
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[cloud_llm] 请求异常: {e}，{wait}s 后重试")
                time.sleep(wait)
            else:
                print(f"[cloud_llm] 请求失败（已重试 {max_retries} 次）: {e}")
                return None, 0
    return None, last_status


def _get_available_providers():
    """返回当前有 key 的 provider 列表（按 fallback 顺序）。"""
    available = []
    for name in FALLBACK_CHAIN:
        cfg = PROVIDERS[name]
        if _get_api_key(cfg, name):
            available.append(name)
    return available


def host_prompt(task, prompt, system="", image_path=None):
    """LLM_MODE=host 时打印推理请求，由宿主 AI 执行；返回 None 表示调用方应中止后续解析。"""
    if LLM_MODE != "host":
        return None
    print("\n[host-mode] 以下推理交由宿主 AI 执行（LLM_MODE=host）：")
    print(f"[host-mode] task={task}" + (f" image={image_path}" if image_path else ""))
    if system:
        print(f"[host-mode system] {system}")
    print(f"[host-mode prompt] {prompt}\n")
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


def chat(prompt, system="", provider=None, model_type="chat",
         temperature=0.1, max_tokens=2000, json_mode=False, task="", mode=None):
    """统一 Chat 接口。返回文本或 None。

    provider: 强制指定 provider 名，None 时用环境变量 + fallback
    model_type: "chat"（快+便宜）或 "reasoning"（强推理）
    json_mode: True 时要求输出 JSON
    task: 用途标签（用于 token 追踪日志）
    mode: 能力边界模式（directed/collaborative/autonomous），None 时用传入的 temperature
    """
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
        # 主 provider 排在最前，其余按 fallback 顺序
        providers_to_try = [primary] + [p for p in available if p != primary]

    if not providers_to_try:
        print("[cloud_llm] 没有可用的 provider（未设置任何 API KEY）")
        return None

    last_error = None
    for pname in providers_to_try:
        cfg = PROVIDERS.get(pname)
        if not cfg:
            continue
        key = _get_api_key(cfg, pname)
        if not key:
            continue

        model = cfg.get(f"{model_type}_model", cfg["chat_model"])

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
                content = _strip_think(data["choices"][0]["message"]["content"])
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
                return content
            except (KeyError, IndexError):
                last_error = f"响应解析失败: {json.dumps(data, ensure_ascii=False)[:200]}"
        else:
            last_error = f"{pname} HTTP {status}"

    if last_error:
        print(f"[cloud_llm] 所有 provider 均失败: {last_error}")
    return None


# ============================================================
# Embedding：智谱 embedding-3 优先，SiliconFlow BGE-m3 兜底
# ============================================================
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
SILICONFLOW_EMBED_MODEL = "BAAI/bge-m3"


def current_embed_provider():
    """返回当前可用的 embedding provider (name, model)；无可用 key 返回 None。

    顺序：智谱 embedding-3（2048 维）→ SiliconFlow BGE-m3（1024 维）。
    两个模型向量空间不兼容，切换 provider 后需 embed-rebuild --force 重建索引。
    """
    if os.environ.get("ZHIPU_API_KEY", "") or os.environ.get("GLM_API_KEY", ""):
        return ("zhipu", "embedding-3")
    if os.environ.get("SILICONFLOW_API_KEY", ""):
        return ("siliconflow", SILICONFLOW_EMBED_MODEL)
    return None


def embed(text, dimensions=None):
    """单条 embedding，返回向量 list[float] 或 None。"""
    vecs = embed_batch([text], dimensions=dimensions)
    return vecs[0] if vecs else None


def embed_batch(texts, dimensions=None):
    """批量 embedding。返回 list[list[float]] 或 None。"""
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
def rerank(query, candidates, top_k=5, provider=None, mode="directed"):
    """LLM rerank。

    candidates: [(client, score, path, snippet), ...] 或 [(path, snippet), ...]
    返回 rerank 后的 top_k 列表（保持输入格式）。
    mode: 能力边界模式，默认 directed（rerank 需严格）
    """
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


def siliconflow_rerank(query, candidates, top_k=5, alpha=0.7):
    """调用 Silicon Flow 的 BGE-reranker-v2-m3 精排。

    输入 candidates 与 rerank() 格式一致：
      - 4 元素: (client, rrf_score, path, snippet)
      - 2 元素: (path, snippet)
    返回 top_k 列表，按融合分数降序。

    分数融合：final = alpha * rerank_score + (1-alpha) * rrf_score
      - alpha=0.7：Reranker 主导，RRF 兜底防误判
      - RRF 分数归一化到 [0,1]，避免量纲不一致

    Key 缺失或调用失败时返回 None，调用方应回退到 LLM rerank。
    """
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
def get_usage_summary():
    """读取用量日志，返回汇总统计。"""
    if not os.path.exists(USAGE_LOG):
        return {"total_calls": 0, "total_tokens": 0, "by_provider": {}}

    by_provider = {}
    total_calls = 0
    total_tokens = 0

    try:
        with open(USAGE_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                total_calls += 1
                total_tokens += entry.get("total_tokens", 0)
                p = entry.get("provider", "unknown")
                if p not in by_provider:
                    by_provider[p] = {"calls": 0, "tokens": 0}
                by_provider[p]["calls"] += 1
                by_provider[p]["tokens"] += entry.get("total_tokens", 0)
    except Exception:
        pass

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
        results["zhipu_embedding"] = (v is not None, "embedding-3")
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


def _vision_cache_load():
    """加载视觉识别缓存 dict；文件缺失/损坏返回空 dict（不阻断识图）。"""
    try:
        with open(VISION_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _vision_cache_save(cache):
    """原子写回缓存（先临时文件再替换），失败不阻断识图。"""
    try:
        os.makedirs(os.path.dirname(VISION_CACHE), exist_ok=True)
        tmp = VISION_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, VISION_CACHE)
    except OSError as e:
        print(f"[vision] 缓存写入失败（不影响识图）: {e}")


def _vision_cache_get(key):
    """命中返回 desc 字符串，未命中返回 None。"""
    entry = _vision_cache_load().get(key)
    return entry.get("desc") if isinstance(entry, dict) else None


def _vision_cache_put(key, desc):
    """写入缓存并按 ts 做 LRU 淘汰，保留最新 VISION_CACHE_MAX_ENTRIES 条。

    加锁串行 load-modify-save：read_batch 并行读图时多线程同时写入，
    无锁会互相覆盖丢条目。
    """
    with _VISION_CACHE_LOCK:
        cache = _vision_cache_load()
        cache[key] = {"desc": desc, "ts": time.time()}
        if len(cache) > VISION_CACHE_MAX_ENTRIES:
            overflow = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))[:len(cache) - VISION_CACHE_MAX_ENTRIES]
            for old_key, _ in overflow:
                cache.pop(old_key, None)
        _vision_cache_save(cache)


def _preprocess_image(raw, ext, mime):
    """发送前压缩图片，降低上传体积（对抗网速，P-vision-4）。

    - 长边缩到 1600px：截图/示意图识别足够，超高清对 OCR/理解无增益
    - 位图转 JPEG 质量 85；透明 PNG 合成白底，防转 JPEG 变黑底
    - Pillow 缺失或解码失败时原图直发（降级，不阻断识图）
    返回 (bytes, mime)。
    """
    # svg（矢量）、heic（PIL 常缺解码器）、gif（动图）不压缩，原样直发
    if ext in ("svg", "heic", "gif"):
        return raw, mime
    try:
        from PIL import Image
        import io as _io
    except ImportError:
        return raw, mime
    try:
        img = Image.open(_io.BytesIO(raw))
        img.load()
    except Exception:
        return raw, mime

    max_side = 1600
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        new_size = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
        img = img.resize(new_size, Image.LANCZOS)
    # 透明通道合成白底，再统一转 RGB（JPEG 不支持 alpha）
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGB"), mask=img.getchannel("A"))
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = _io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "jpeg"


def vision_chat(prompt, image_path, provider="minimax", task="vision", cache_bust=False):
    """视觉理解：把图片 + prompt 发给多模态模型，返回文本描述。

    当 AGENT_MODEL_SUPPORTS_VISION=true 时跳过本调用：
    表示当前运行的 AI agent 本身具备多模态能力，
    应直接传图片而非先转文本。

    cache_bust=True 时完全跳过结果缓存（读写都不走）：
    A/B 双观察轮次需要同图多次独立采样，不能命中彼此的缓存。
    """
    if LLM_MODE == "host":
        host_prompt(task, prompt, image_path=image_path)
        return None
    import base64
    # P-vision-1：声明式跳过。当前的 AI agent 本身多模态时不必预转文本
    if os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"):
        print("[vision] 已跳过：AGENT_MODEL_SUPPORTS_VISION=true（agent 自身多模态）")
        return ""
    cfg = PROVIDERS.get(provider, PROVIDERS["minimax"])
    key = _get_api_key(cfg, provider)
    if not key:
        print(f"[vision] {provider} API key 未配置")
        return ""

    # P-vision-3：格式白名单 + 大小上限（base64 后约 1.33 倍，超限 API 直接拒）
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif",
            "bmp": "bmp", "webp": "webp", "svg": "svg+xml",
            "tiff": "tiff", "tif": "tiff", "heic": "heic"}.get(ext)
    if not mime:
        print(f"[vision] 不支持的图片格式: .{ext}（支持 jpg/png/gif/bmp/webp/svg/tiff/heic）")
        return ""

    try:
        with open(image_path, "rb") as f:
            raw = f.read()
    except OSError as e:
        print(f"[vision] 读取图片失败: {e}")
        return ""
    # P-vision-5：结果缓存——同图（内容 hash 相同）跳过上传，直接返回上次描述
    cache_key = hashlib.sha256(raw).hexdigest()
    cached = None if cache_bust else _vision_cache_get(cache_key)
    if cached is not None:
        print(f"[vision] 命中缓存，跳过上传: {os.path.basename(image_path)}")
        return cached
    # P-vision-4：发送前压缩（大图缩到 1600px + 转 JPEG），体积降 80%+ 直接缓解网速影响
    raw, mime = _preprocess_image(raw, ext, mime)
    if len(raw) > VISION_MAX_IMAGE_BYTES:
        print(f"[vision] 图片过大: {len(raw) / 1024 / 1024:.1f}MB > "
              f"{VISION_MAX_IMAGE_BYTES / 1024 / 1024:.0f}MB，请压缩后再试")
        return ""
    b64 = base64.b64encode(raw).decode()

    url = f"{cfg['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # P-vision-2：注入防幻觉 system 约束 + 独立 max_tokens 防截断
    payload = {
        "model": cfg.get("chat_model", "MiniMax-M3"),
        "messages": [
            {"role": "system", "content": VISION_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}}
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": VISION_MAX_TOKENS,
    }
    # P-vision-4：超时随体积自适应，慢网 + 大图给更长窗口，避免 30s 误判失败
    timeout = max(60, min(300, len(b64) // 20_000))
    data, status = _post_json(url, headers, payload, timeout=timeout)
    if not data:
        print(f"[vision] 请求失败: HTTP {status or '无响应'}")
        return ""
    # P1-1（2026-07-21）：vision 计量接入 _log_usage，堵 CLI vision 黑洞。
    # 各家 usage 结构不一，防御式提取，缺失记 0 不报错
    usage = data.get("usage", {}) or {}
    prompt_details = usage.get("prompt_tokens_details", {}) or {}
    completion_details = usage.get("completion_tokens_details", {}) or {}
    _log_usage(
        provider, cfg.get("chat_model", "MiniMax-M3"),
        usage.get("prompt_tokens", 0) or 0,
        usage.get("completion_tokens", 0) or 0,
        task=task,
        reasoning_tokens=completion_details.get("reasoning_tokens", 0) or 0,
        image_tokens=prompt_details.get("image_tokens", 0) or 0,
    )
    # P-vision-2：minimax 的推理在 message.reasoning_content 独立字段，正文在 content；
    # 兼容某些 provider 把 reasoning 用 <think> 塞进 content 的情况
    message = (data.get("choices", [{}]) or [{}])[0].get("message", {}) or {}
    content = message.get("content", "")
    if not content:
        reasoning = message.get("reasoning_content", "")
        print(f"[vision] 模型未返回正文（reasoning_content {len(reasoning)} 字符）")
        return ""
    result = _strip_think(content)
    if result and not cache_bust:
        _vision_cache_put(cache_key, result)
    return result


# ============================================================
# A/B 双观察 + 分歧仲裁（vision-describe --rounds 2；参考 ds-vision-v3 证据契约）
# ============================================================

def _vision_conflicts(da, db):
    """字段级差异清单：A/B 两份 JSON 的逐字段比较。

    列表类字段按元素排序后比较（顺序无关），dict 类字段按键排序序列化比较，
    缺失字段视为 None。返回有差异的字段名列表；两份输出完全一致时为空。
    """
    if not isinstance(da, dict) or not isinstance(db, dict):
        return ["raw_output"]
    diffs = []
    for key in sorted(set(da) | set(db)):
        va, vb = da.get(key), db.get(key)
        if isinstance(va, list) or isinstance(vb, list):
            sa = json.dumps(sorted(json.dumps(x, ensure_ascii=False)
                                   for x in (va or [])), ensure_ascii=False)
            sb = json.dumps(sorted(json.dumps(x, ensure_ascii=False)
                                   for x in (vb or [])), ensure_ascii=False)
        else:
            sa = json.dumps(va, ensure_ascii=False, sort_keys=True)
            sb = json.dumps(vb, ensure_ascii=False, sort_keys=True)
        if sa != sb:
            diffs.append(key)
    return diffs


# 仲裁 prompt：把 A/B 分歧点摆给第 3 次观察裁决，输出与主模板同构 + arbitration 字段
VISION_ARBITRATION_SUFFIX = (
    "\n以下是两次独立观察的输出，两份在字段 {diff_fields} 存在分歧。"
    "请对照原图逐一裁决分歧，给出唯一的最终结论。\n"
    "【观察 A】\n{a}\n\n【观察 B】\n{b}\n\n"
    '只输出 JSON，不要输出任何 JSON 之外的文字或解释：'
    '{"summary": "一段总述", "extracted_text": "图中全部文字原文摘录", '
    '"objects": ["主要对象"], "layout": "版式结构", '
    '"uncertain": ["不确定或无法辨认的内容"], '
    '"evidence": {"visible_fact": ["图中直接可见、可逐字核验的事实"], '
    '"image_candidate": ["基于视觉的推断性判断（需人工或二次核验）"], '
    '"unknown": ["无法辨认或图中不存在、无法回答的项"]}, '
    '"arbitration": {"conflicts": ["被裁决的分歧字段"], "ruling": "每个分歧的裁决一句话"}}'
)


def vision_describe_ab(prompt, image_path, provider="minimax", task="vision"):
    """A/B 隔离双观察 + 分歧仲裁。

    两次独立观察互不泄漏（cache_bust 绕过同图缓存）；若两份输出逐字段一致，
    直接返回 A 并标 independent_ab_consistent；有分歧则第 3 次带分歧清单仲裁，
    标 independent_ab_arbitration。

    返回 (final_text, meta)：
      - final_text：最终结论文本（一致= A 原文；分歧= 仲裁 JSON 文本）；失败时 None
      - meta：{"verification_mode", "conflicts", "a": 解析后的A, "b": 解析后的B}
        任一轮调用失败时 meta["failed_round"] 记录失败轮次，调用方降级处理。
    """
    text_a = vision_chat(prompt, image_path, provider=provider, task=task, cache_bust=True)
    if not text_a:
        return None, {"verification_mode": "ab_failed", "failed_round": "A", "conflicts": []}
    text_b = vision_chat(prompt, image_path, provider=provider, task=task, cache_bust=True)
    if not text_b:
        return None, {"verification_mode": "ab_failed", "failed_round": "B", "conflicts": []}
    da, db = _parse_json(text_a), _parse_json(text_b)
    diffs = _vision_conflicts(da, db)
    if not diffs:
        # 一致：两份输出等价，A 原文作为最终结论（已含完整 JSON 结构）
        return text_a, {"verification_mode": "independent_ab_consistent", "conflicts": [],
                        "a": da, "b": db}
    arb_prompt = prompt + VISION_ARBITRATION_SUFFIX.format(
        diff_fields="、".join(diffs), a=text_a, b=text_b)
    text_arb = vision_chat(arb_prompt, image_path, provider=provider, task=task, cache_bust=True)
    if not text_arb:
        return None, {"verification_mode": "ab_failed", "failed_round": "arbitration",
                      "conflicts": diffs, "a": da, "b": db}
    return text_arb, {"verification_mode": "independent_ab_arbitration", "conflicts": diffs,
                      "a": da, "b": db}


# ============================================================
# 联网搜索：双引擎（Tavily 为主，字节搜索为辅）
# ============================================================

def _get_tavily_key():
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key or not key.isascii():
        return None
    return key


def _get_volcengine_keys():
    ak = os.environ.get("VOLCENGINE_ACCESS_KEY", "").strip()
    sk = os.environ.get("VOLCENGINE_SECRET_KEY", "").strip()
    api_key = os.environ.get("ASK_ECHO_SEARCH_INFINITY_API_KEY", "").strip()
    return ak, sk, api_key


def tavily_search(query, max_results=5):
    """调用 Tavily 搜索 API（第一检索引擎）。
    
    返回: (results_list, http_status_code) 或 (None, status_code)
    """
    key = _get_tavily_key()
    if not key:
        print("[search] Tavily API key 未配置")
        return None, 0

    url = "https://api.tavily.com/search"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
    }

    data, status = _post_json(url, headers, payload, timeout=30)
    if not data:
        print(f"[search] Tavily 请求失败: HTTP {status}")
        return None, status

    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "") or r.get("raw_content", ""),
            "score": r.get("score", 0),
            "source": "tavily",
        })
    return results, status


def byte_search(query, max_results=5):
    """调用豆包搜索（火山引擎 Search Infinity，第二检索引擎）。

    API 文档：https://www.volcengine.com/docs/87772/2272953
    """
    ak, sk, api_key = _get_volcengine_keys()

    if not api_key and (not ak or not sk):
        print("[search] 字节搜索 API key 未配置（需要 ASK_ECHO_SEARCH_INFINITY_API_KEY 或 VOLCENGINE_ACCESS_KEY/SECRET_KEY）")
        return None

    # API Key 接入（推荐）
    if api_key:
        url = "https://open.feedcoopapi.com/search_api/web_search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "Query": query,
            "SearchType": "web",
            "Count": max_results,
        }
    # AK/SK 接入（TOP 网关）
    else:
        url = "https://mercury.volcengineapi.com?Action=WebSearch&Version=2025-01-01"
        headers = {
            "Content-Type": "application/json",
            "X-Volcengine-Access-Key": ak,
            "X-Volcengine-Secret-Key": sk,
        }
        payload = {
            "Query": query,
            "SearchType": "web",
            "Count": max_results,
        }

    data, status = _post_json(url, headers, payload, timeout=30)
    if not data:
        print(f"[search] 字节搜索请求失败: HTTP {status}")
        return None

    # 检查 API 层错误
    err = data.get("ResponseMetadata", {}).get("Error")
    if err:
        print(f"[search] 字节搜索 API 错误: {err.get('Code', '')} {err.get('Message', '')}")
        return None

    results = []
    for r in data.get("Result", {}).get("WebResults", []):
        results.append({
            "title": r.get("Title", ""),
            "url": r.get("Url", ""),
            "content": r.get("Summary", "") or r.get("Snippet", ""),
            "score": r.get("RankScore", 0),
            "source": "byte_search",
        })
    return results


def web_search(query, max_results=5, engines=None):
    """联网搜索：支持多引擎融合。
    
    engines: 指定引擎列表，如 ["tavily", "byte_search"]，None 时自动检测可用引擎。
    返回合并后的结果列表，按 score 降序。
    
    降级策略：优先使用 Tavily，如果配额用完（429错误）则自动降级到字节搜索。
    """
    if engines is None:
        engines = []
        if _get_tavily_key():
            engines.append("tavily")
        if any(_get_volcengine_keys()):
            engines.append("byte_search")
        if not engines:
            print("[search] 未配置任何搜索引擎 key（TAVILY_API_KEY / ASK_ECHO_SEARCH_INFINITY_API_KEY / VOLCENGINE_ACCESS_KEY），联网搜索不可用")
            print("  提示：在 .env 中配置，或运行 python _cli.py key-doctor 检查")
            return None

    all_results = []
    tavily_quota_exceeded = False
    
    for engine in engines:
        try:
            if engine == "tavily":
                # 如果 Tavily 配额已用完，跳过
                if tavily_quota_exceeded:
                    print("[search] Tavily 配额已用完，跳过")
                    continue
                results, status = tavily_search(query, max_results)
                # 检测 Tavily 429 错误（配额用完）
                if status == 429:
                    tavily_quota_exceeded = True
                    print("[search] Tavily 配额已用完（HTTP 429），降级到字节搜索")
                    continue
                if results:
                    all_results.extend(results)
            elif engine == "byte_search":
                results = byte_search(query, max_results)
                if results:
                    all_results.extend(results)
                    # 如果字节搜索成功且之前 Tavily 配额用完，记录日志
                    if tavily_quota_exceeded:
                        print("[search] 字节搜索成功，已降级使用")
            else:
                continue
        except Exception as e:
            print(f"[search] 引擎 {engine} 调用异常: {e}")
            # 如果 Tavily 异常且是配额相关错误，标记配额用完
            if engine == "tavily" and "429" in str(e):
                tavily_quota_exceeded = True
                print("[search] Tavily 配额异常（429），标记配额已用完")
            continue

    if not all_results:
        print("[search] 所有引擎均返回空结果")
        return None

    # URL 去重（同一 URL 只保留 score 最高的）
    seen_urls = {}
    for r in all_results:
        url = r.get("url", "")
        if not url:
            continue
        if url not in seen_urls or r.get("score", 0) > seen_urls[url].get("score", 0):
            seen_urls[url] = r
    all_results = list(seen_urls.values())

    # 英文域名加权：非 .cn 域名加 0.1 bonus
    for r in all_results:
        url = r.get("url", "")
        if url and ".cn" not in url:
            r["score"] = r.get("score", 0) + 0.1

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results[:max_results]
