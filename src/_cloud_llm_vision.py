# -*- coding: utf-8 -*-
"""_cloud_llm 视觉识别子模块（T9 拆分自 _cloud_llm.py，2026-09-01）。
承载：vision_chat / vision_describe_ab / 视觉缓存与预处理。"""
import os
import json
import time
import hashlib

import _cloud_transport
# 环断（#57/Q2 方案A，2026-09-06）：本模块不再模块级导入 _cloud_llm——
# 母文件尾部 re-export 本模块，模块级互导构成 mother→vision→mother 环，
# 单独 import _cloud_llm_vision 会撞 partially initialized ImportError。
# 母文件属性（LLM_MODE/PROVIDERS/VISION_* 等）一律在函数内延迟导入；
# HTTP 一律走 _cloud_transport 真源（测试打点 patch _cloud_transport._post_json）。

def _vision_cache_load():
    """加载视觉识别缓存 dict；文件缺失/损坏返回空 dict（不阻断识图）。"""
    import _cloud_llm
    try:
        with open(_cloud_llm.VISION_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _vision_cache_save(cache):
    """原子写回缓存（先临时文件再替换），失败不阻断识图。

    C-A9（2026-09-07）：os.replace 带 backoff 重试——目标文件正被并发读句柄
    （_vision_cache_get 历史契约锁外读）占有时，Windows 抛共享冲突
    PermissionError（WinError 5/32），单次即弃会把本批条目静默打丢（except OSError
    只 print）。实测 6 读线程压 500 次 replace 全数 PermissionError(13)；
    pytest 复跑 80 次 0 复现（偶发）+ B5b 在案 WinError 5 先例
    （docs/B6收尾_四件套与顺手项_实施报告_2026-09-07.md），根因同源。
    """
    import _cloud_llm
    tmp = _cloud_llm.VISION_CACHE + ".tmp"
    try:
        os.makedirs(os.path.dirname(_cloud_llm.VISION_CACHE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        for attempt in range(5):
            try:
                os.replace(tmp, _cloud_llm.VISION_CACHE)
                return
            except OSError:
                if attempt == 4:
                    raise  # 重试耗尽：按原契约放弃（print，不阻断识图）
                time.sleep(0.02 * (attempt + 1))
    except OSError as e:
        print(f"[vision] 缓存写入失败（不影响识图）: {e}")


def _vision_cache_get(key):
    """命中返回 desc 字符串，未命中返回 None。

    C-A9（2026-09-07）：读也走 _VISION_CACHE_LOCK——Windows 上锁外读与
    os.replace 相撞即共享冲突（PermissionError WinError 5/32），read_batch
    多线程下 save 会被整批静默打丢（= test_concurrent_cache_writes_no_loss
    偶发失败根因）。锁内读写互斥后进程内该竞态确定性消除；跨进程残余由
    _vision_cache_save 的 replace 重试兜底。
    """
    import _cloud_llm
    with _cloud_llm._VISION_CACHE_LOCK:
        entry = _vision_cache_load().get(key)
    return entry.get("desc") if isinstance(entry, dict) else None


def _vision_cache_put(key, desc):
    """写入缓存并按 ts 做 LRU 淘汰，保留最新 _cloud_llm.VISION_CACHE_MAX_ENTRIES 条。

    加锁串行 load-modify-save：read_batch 并行读图时多线程同时写入，
    无锁会互相覆盖丢条目。
    """
    import _cloud_llm
    with _cloud_llm._VISION_CACHE_LOCK:
        cache = _vision_cache_load()
        cache[key] = {"desc": desc, "ts": time.time()}
        if len(cache) > _cloud_llm.VISION_CACHE_MAX_ENTRIES:
            overflow = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))[:len(cache) - _cloud_llm.VISION_CACHE_MAX_ENTRIES]
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


def _host_prompt_brief(task, prompt, image_path=None):
    """host 模式提示（P3 加固）：只记长度 + 前 80 字符预览，不回显完整 prompt。

    与 _cloud_llm.host_prompt 的区别：后者全量打印 prompt，含图内提取文本等
    材料内容，会随宿主会话日志持久化；此处降为摘要，宿主按 task 与会话上下文
    自行完成推理。返回 None，语义与 host_prompt 一致（调用方应中止后续解析）。
    """
    print("\n[host-mode] 以下推理交由宿主 AI 执行（LLM_MODE=host）：")
    print(f"[host-mode] task={task}" + (f" image={image_path}" if image_path else ""))
    print(f"[host-mode prompt] 长度={len(prompt)} 字符（安全截断，仅前 80 字符预览）: {prompt[:80]}...")
    print()
    return None


def vision_chat(prompt, image_path, provider="minimax", task="vision", cache_bust=False):
    """视觉理解：把图片 + prompt 发给多模态模型，返回文本描述。

    当 AGENT_MODEL_SUPPORTS_VISION=true 时跳过本调用：
    表示当前运行的 AI agent 本身具备多模态能力，
    应直接传图片而非先转文本。

    cache_bust=True 时完全跳过结果缓存（读写都不走）：
    A/B 双观察轮次需要同图多次独立采样，不能命中彼此的缓存。
    """
    import _cloud_llm
    if _cloud_llm.LLM_MODE == "host":
        # P3 加固（2026-09-06 安全审查）：host_prompt 全文会带材料进会话日志，
        # 改用本地摘要版（长度 + 前 80 字符）
        _host_prompt_brief(task, prompt, image_path=image_path)
        return None
    import base64
    # P-vision-1：声明式跳过。当前的 AI agent 本身多模态时不必预转文本
    if os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"):
        print("[vision] 已跳过：AGENT_MODEL_SUPPORTS_VISION=true（agent 自身多模态）")
        return ""
    cfg = _cloud_llm.PROVIDERS.get(provider, _cloud_llm.PROVIDERS["minimax"])
    key = _cloud_llm._get_api_key(cfg, provider)
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
    if len(raw) > _cloud_llm.VISION_MAX_IMAGE_BYTES:
        print(f"[vision] 图片过大: {len(raw) / 1024 / 1024:.1f}MB > "
              f"{_cloud_llm.VISION_MAX_IMAGE_BYTES / 1024 / 1024:.0f}MB，请压缩后再试")
        return ""
    b64 = base64.b64encode(raw).decode()

    url = f"{cfg['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # P-vision-2：注入防幻觉 system 约束 + 独立 max_tokens 防截断
    payload = {
        "model": cfg.get("chat_model", "MiniMax-M3"),
        "messages": [
            {"role": "system", "content": _cloud_llm.VISION_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}}
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": _cloud_llm.VISION_MAX_TOKENS,
    }
    # P-vision-4：超时随体积自适应，慢网 + 大图给更长窗口，避免 30s 误判失败
    timeout = max(60, min(300, len(b64) // 20_000))
    data, status = _cloud_transport._post_json(url, headers, payload, timeout=timeout)
    if not data:
        print(f"[vision] 请求失败: HTTP {status or '无响应'}")
        return ""
    # P1-1（2026-07-21）：vision 计量接入 _cloud_llm._log_usage，堵 CLI vision 黑洞。
    # 各家 usage 结构不一，防御式提取，缺失记 0 不报错
    usage = data.get("usage", {}) or {}
    prompt_details = usage.get("prompt_tokens_details", {}) or {}
    completion_details = usage.get("completion_tokens_details", {}) or {}
    _cloud_llm._log_usage(
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
    result = _cloud_llm._strip_think(content)
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
    import _cloud_llm
    text_a = vision_chat(prompt, image_path, provider=provider, task=task, cache_bust=True)
    if not text_a:
        return None, {"verification_mode": "ab_failed", "failed_round": "A", "conflicts": []}
    text_b = vision_chat(prompt, image_path, provider=provider, task=task, cache_bust=True)
    if not text_b:
        return None, {"verification_mode": "ab_failed", "failed_round": "B", "conflicts": []}
    da, db = _cloud_llm._parse_json(text_a), _cloud_llm._parse_json(text_b)
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
