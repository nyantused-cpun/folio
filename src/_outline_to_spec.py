# -*- coding: utf-8 -*-
"""场景大纲 → spec.yml 草稿生成器。

流程：
  1. 读取场景大纲 outline.yml（思维导图结构）
  2. 读取客户材料（_pipeline 全文解析）
  3. 调云端 LLM extract_json（防幻觉）提取每章节内容
     （§八 3.3：按 prompt 全部输入缓存到 _knowledge/.cache/llm_extract_cache.json，
      命中跳过 LLM；prompt 结构变更时递增 PROMPT_VERSION 使旧缓存失效）
  4. 按 outline 的 role 映射到 spec.yml 的 layout
  5. 输出 spec.yml 草稿

防幻觉：每章节提取都走 _cloud_llm.extract_json，强制引用原文数字。
"""
import os
import json
import yaml
import hashlib
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
OUTLINES_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "outlines")

# role → layout 映射（spec.yml 的 layout 字段）
ROLE_LAYOUT = {
    "pain_points": "cards_3",
    "goals": "title_body",
    "blueprint": "tree",
    "implementation": "phases",
    "value": "title_body",
    "next_steps": "summary",
    "requirement": "title_body",
    "solution_overview": "title_body",
    "function_architecture": "tree",
    "core_functions": "table",
    "tech_architecture": "tree",
    "service": "title_body",
    "overview": "title_body",
    "progress": "table",
    "issues": "cards_3",
    "decisions": "cards_3",
    "scope": "title_body",
    "pricing": "table",
    "payment": "title_body",
    "terms": "bullets",
    "value_added": "cards_3",
}

# 架构类 role：LLM 提取时追加 layers 结构化要求，build_elements 产 diagram（§七 2.7）
ARCH_ROLES = {"blueprint", "function_architecture", "tech_architecture"}

# Gold spec 示范库（§8 v1.2 候选 4 三层示范库）：每种 diagram subtype 1 个
# 验收过的 spec 片段，由 _tools/extract_gold_specs.py 从已验收产出切片生成
GOLD_SPECS_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "gold_specs")
# 每种示范注入截断到 ~500 tokens（3-5 种 ≈ 2k/单，替代 ~23k 目检）
GOLD_DEMO_MAX_TOKENS = 500

# role → 本章节将产出的 diagram（build_elements 的实际产出），gold 示范按此召回
ROLE_DIAGRAM = {role: ("architecture", "layered") for role in ARCH_ROLES}


def _est_tokens(text):
    """粗估 token 数（偏保守上界）：CJK 1 字 ≈ 1 token，ASCII ~4 字符 ≈ 1 token。"""
    cjk = sum(1 for ch in text if ord(ch) >= 0x2E80)
    return cjk + (len(text) - cjk) // 4 + 1


def _truncate_to_tokens(text, max_tokens):
    """按行截断到 token 预算内（不切断行），超预算时追加截断标注。"""
    if _est_tokens(text) <= max_tokens:
        return text
    kept, budget = [], 0
    for line in text.splitlines():
        t = _est_tokens(line)
        if budget + t > max_tokens:
            break
        kept.append(line)
        budget += t
    return "\n".join(kept) + "\n# …（超出示范 token 预算，余下截断）"


def load_gold_demo(diagram_type, subtype, max_tokens=GOLD_DEMO_MAX_TOKENS):
    """读 gold spec 示范片段并截断到 token 预算；无对应 gold 返回 None（不注入）。

    先剥 `#` 注释行：gold 文件头注释含验收来源（内部路径/客户名），
    不能泄进其他客户的 prompt，且省 token。
    """
    path = os.path.join(GOLD_SPECS_DIR, f"{diagram_type}__{subtype}.yml")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _truncate_to_tokens(_strip_comment_lines(f.read()), max_tokens)


def _strip_comment_lines(text):
    """剥掉 `#` 注释行（行首/缩进后以 # 开头的 yaml 注释），保留内容行。"""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _gold_demo_block(section):
    """本章节将产 diagram 时返回写法示范注入块，否则返回 ""。

    §3 前缀稳定性：注入块拼在静态 system 段之后、【本章节任务】之前
    （与 evidence 同区），静态前缀逐字节不变。
    """
    target = ROLE_DIAGRAM.get(section.get("role", ""))
    if not target:
        return ""
    demo = load_gold_demo(*target)
    if not demo:
        return ""
    return ("\n【写法示范】以下为验收过的 gold spec 片段，模仿其字段结构和信息密度，"
            "不要抄内容：\n" + demo + "\n")

# ---- LLM 提取缓存（重构计划 §八 3.3）----
# prompt 模板版本号：改动 extract_section_content 的 prompt 结构
# （含架构章节附加要求）时递增——版本号进缓存 key，旧缓存自动失效，无需手清文件
PROMPT_VERSION = "v1"
LLM_EXTRACT_CACHE_PATH = os.path.join(
    SCRIPT_DIR, "_knowledge", ".cache", "llm_extract_cache.json")
# outline-to-spec 并行提取（ThreadPoolExecutor），写缓存需加锁 + 写前重读合并
_CACHE_LOCK = threading.Lock()


def _extract_provider_model():
    """extract_section_content 固定走 zhipu 的 chat 模型，读配置取模型名进缓存 key。"""
    try:
        from _cloud_llm import PROVIDERS
        cfg = PROVIDERS.get("zhipu", {})
        return "zhipu", cfg.get("chat_model", "?")
    except Exception:
        return "zhipu", "?"


def _extract_cache_key(section, materials_text, client_name, evidence_chunks):
    """缓存 key = sha256（提取的全部 prompt 输入）。

    evidence 参与 key 的决策：evidence 内容直接拼接进 prompt（见
    extract_section_content 的 evidence_block 构造），若不入 key，同一材料+章节
    但召回结果不同时会返回与当前证据不匹配的旧提取。安全优先——prompt 的任一
    输入变化都触发重新提取，代价仅是召回波动时缓存命中率略降。

    gold 示范入 key 的决策同理（§8 v1.2-4）：gold_block 直接拼接进 prompt，
    gold 库重提取/增删片段时内容变化必须触发重取；同时该字段的加入本身使
    注入功能上线前的旧 key 全部失配，等效于一次缓存失效，无需动 PROMPT_VERSION。
    """
    provider, model = _extract_provider_model()
    payload = {
        "materials_sha256": hashlib.sha256(
            materials_text.encode("utf-8")).hexdigest(),
        "section": section.get("section", ""),
        "role": section.get("role", ""),
        "children": section.get("children", []),
        "prompt_hint": section.get("prompt", "").strip(),
        "client": client_name or "",
        "evidence": [
            {"source": ev.get("source", ""), "snippet": ev.get("snippet", ""),
             "parent_context": ev.get("parent_context", "")}
            for ev in (evidence_chunks or [])
        ],
        "gold_demo_sha256": hashlib.sha256(
            _gold_demo_block(section).encode("utf-8")).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "model": model,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_extract_cache():
    """读提取缓存；文件不存在返回空，损坏时降级为无缓存（告警但不报错）。"""
    try:
        with open(LLM_EXTRACT_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries") if isinstance(data, dict) else None
        return entries if isinstance(entries, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:  # JSONDecodeError 是 ValueError 子类
        print(f"    [cache] 提取缓存读取失败，按无缓存继续: {e}")
        return {}


def _save_extract_cache(entries):
    """写提取缓存；失败只告警不中断（缓存是性能优化，不是正确性依赖）。"""
    try:
        os.makedirs(os.path.dirname(LLM_EXTRACT_CACHE_PATH), exist_ok=True)
        with open(LLM_EXTRACT_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "entries": entries},
                      f, ensure_ascii=False, indent=1)
    except OSError as e:
        print(f"    [cache] 提取缓存写入失败（忽略）: {e}")


def _cache_put(key, section_name, result):
    """线程安全写入一条缓存（并行提取场景，写前重读合并防丢条目）。"""
    with _CACHE_LOCK:
        entries = _load_extract_cache()
        entries[key] = {
            "section": section_name,
            "created_at": __import__("datetime").datetime.now()
                            .isoformat(timespec="seconds"),
            "result": result,
        }
        _save_extract_cache(entries)


def load_outline(scene_name):
    """加载场景大纲。"""
    outline_path = os.path.join(OUTLINES_DIR, scene_name, "outline.yml")
    if not os.path.exists(outline_path):
        raise FileNotFoundError(f"场景大纲不存在: {scene_name}")
    with open(outline_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_materials(materials_paths, client_name=""):
    """读取客户材料，返回纯文本。client_name 且未传 paths 时自动扫描 refs/。"""
    from _pipeline import read_full
    paths = list(materials_paths)

    if client_name and not paths:
        refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "refs")
        if os.path.isdir(refs_dir):
            paths = [os.path.join(refs_dir, f) for f in os.listdir(refs_dir)
                     if not f.startswith(".")]
            print(f"  自动扫描客户 refs/: {len(paths)} 个文件")

    all_text = []
    for path in paths:
        if not os.path.isabs(path):
            path = os.path.join(SCRIPT_DIR, path)
        if not os.path.exists(path):
            print(f"  跳过（不存在）: {path}")
            continue
        print(f"  读取: {path}")
        summary, cache = read_full(path)
        if os.path.exists(cache):
            with open(cache, "r", encoding="utf-8") as f:
                all_text.append(f.read())
        else:
            all_text.append(summary)
    return "\n\n---\n\n".join(all_text)


def _infer_style_from_client(client_name):
    """从客户 context.md 推断行业，映射到 style 名。"""
    if not client_name:
        return "enterprise"
    ctx_path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "context.md")
    if not os.path.exists(ctx_path):
        return "enterprise"
    with open(ctx_path, "r", encoding="utf-8") as f:
        text = f.read()
    if "教育" in text or "学校" in text:
        return "education"
    if "科技" in text or "互联网" in text:
        return "tech"
    if "政府" in text or "政务" in text:
        return "gov"
    return "enterprise"


def extract_section_content(section, materials_text, client_name="", evidence_chunks=None):
    """用 LLM 从材料中提取单章节内容（防幻觉）。

    直接调 chat + json_mode，不走 extract_json（后者会把 prompt 当待提取文本）。
    evidence_chunks: 召回的证据片段列表 [{"source", "snippet"}, ...]，注入 prompt 增强准确性。
    """
    from _cloud_llm import chat, _parse_json, _validate_against_source, LLM_MODE

    section_name = section["section"]
    role = section.get("role", "")
    prompt_hint = section.get("prompt", "").strip()
    children = section.get("children", [])

    # §八 3.3：命中缓存直接返回，跳过 LLM 调用（key 覆盖全部 prompt 输入）
    cache_key = _extract_cache_key(section, materials_text, client_name,
                                   evidence_chunks)
    cached = _load_extract_cache().get(cache_key)
    if cached is not None and isinstance(cached.get("result"), dict):
        print(f"    [cache] 章节「{section_name}」命中 LLM 提取缓存"
              f"（prompt {PROMPT_VERSION}），跳过 LLM 调用")
        return cached["result"]

    # 构造证据块（替代全量 materials_text，实测节省 ~48% token）
    evidence_block = ""
    evidence_text_for_validate = ""
    if evidence_chunks:
        lines = []
        for i, ev in enumerate(evidence_chunks, 1):
            line = f"[证据{i}] 来源：{ev.get('source', '?')}\n内容：{ev.get('snippet', '')}"
            if ev.get("parent_context"):
                line += f"\n  [父级上下文] {ev['parent_context']}"
            lines.append(line)
        evidence_block = "\n【语义召回证据（主要参考）】\n" + "\n\n".join(lines) + "\n"
        evidence_text_for_validate = "\n".join(ev.get("snippet", "") for ev in evidence_chunks)

    # Fallback：evidence 不足时用全量材料前 4000 字符（避免完全无依据）
    materials_fallback = ""
    if len(evidence_text_for_validate) < 1500:
        materials_fallback = f"\n【客户材料（evidence 不足，前 4000 字符）】\n{materials_text[:4000]}\n"
        evidence_text_for_validate = materials_text[:4000]

    # gold spec 写法示范（§8 v1.2-4）：本章节产 diagram 时注入，与 evidence 同区
    gold_block = _gold_demo_block(section)

    system = """你是咨询方案撰写助手。任务：从客户材料中提取指定章节的内容，输出 JSON。

【强制规则】
1. content 和 key_points 必须基于上方【客户材料】的原文内容，禁止编造
2. 如果材料中没有本章节相关内容，content 填"未提及"，key_points 和 data 返回空数组 []
3. data 字段只放材料中真实出现的数字/指标，原文引用
4. source_quote 必须是材料原文片段，用于防幻觉校验
5. 严格输出 JSON，不要加 markdown 代码块标记"""

    prompt = f"""【客户】{client_name or "（未指定）"}
{evidence_block}{materials_fallback}{gold_block}
---

【本章节任务】
章节：{section_name}
章节角色：{role}
参考子要点：{children}

写作要求：
{prompt_hint}

请输出如下 JSON 格式（严格 JSON，不要加 ```json 标记）：
{{
  "title": "本章节标题（基于材料内容拟定）",
  "content": "本章节正文，2-4 句话，基于材料内容",
  "key_points": ["从材料提取的 2-5 个具体要点，每个一句话"],
  "data": ["材料中出现的具体数字/指标，原文引用"],
  "source_quote": "材料中支撑本章节的原文片段"
}}"""

    # 架构类章节：追加 layers 结构化提取要求（§七 2.7），供 build_elements 产 diagram
    if role in ARCH_ROLES:
        prompt += """

【架构章节附加要求】
本章节是架构类章节。除上述字段外，JSON 需额外包含 "layers" 字段，用于绘制分层架构图：
"layers": [
  {"name": "层名", "desc": "该层一句话说明", "components": ["组件1", "组件2", "组件3"]}
]
要求：
1. 3-6 层，每层 3-6 个组件，层名和组件必须全部来自材料原文，禁止编造
2. 按材料中描述的架构分层组织；材料不足以支撑分层时，layers 返回空数组 []"""

    # 架构类章节输出更长（多 layers 字段），且 zhipu 思考模式会消耗 token 预算，
    # 实测 2000 max_tokens 会被 reasoning 耗尽导致空 content → 架构章节提到 4000
    max_tokens = 4000 if role in ARCH_ROLES else 2000
    resp = chat(prompt, system=system,
                temperature=0.0, json_mode=True, task="extract_section",
                max_tokens=max_tokens)
    if not resp:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return None

    result = _parse_json(resp)
    if not result:
        print(f"    [warn] JSON 解析失败，原始响应: {resp[:200]}")
        return None

    # 防幻觉校验：对实际注入 prompt 的材料校验
    _validate_against_source(result, evidence_text_for_validate)
    # 只缓存成功结果：提取失败（上面的 return None）不入缓存，重跑可重试
    _cache_put(cache_key, section_name, result)
    return result


def _recall_evidence(query, client_name, top_k=5):
    """按主题召回证据片段，用于注入 spec 提取的 prompt。

    返回 [{"source": "文件名#锚点", "snippet": "片段文本"}, ...]
    """
    if not query or not client_name:
        return []
    try:
        import io
        import contextlib
        from _session import recall

        # 静默 recall（抑制打印），启用客户过滤
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            results = recall(query, client_name=client_name,
                             use_embedding=True, return_results=True,
                             client_filter=True)
        if not results:
            return []
        return [{"source": r.get("path", "?"), "snippet": r.get("snippet", ""),
                 "parent_context": r.get("parent_context", "")}
                for r in results[:top_k]]
    except Exception as e:
        print(f"    [recall] 证据召回失败: {e}")
        return []


def _load_bid_criteria(client_name):
    """加载 bid_criteria.json（如果存在），返回 dict 或 None。"""
    if not client_name:
        return None
    path = os.path.join(SCRIPT_DIR, "output", client_name, "bid_criteria.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_scoring_to_section(section_name, scoring_list):
    """将评分项匹配到大纲章节，返回 (target_score, scoring_guide) 或 (None, None)。"""
    if not scoring_list:
        return None, None
    for item in scoring_list:
        item_name = item.get("item", "")
        # 精确匹配
        if section_name == item_name:
            return item.get("score"), item.get("detail", "")
        # 模糊匹配：章节名包含评分项名
        if item_name and item_name in section_name:
            return item.get("score"), item.get("detail", "")
        # 检查子项
        for sub in item.get("sub_items", []):
            sub_name = sub.get("name", "")
            if sub_name and (sub_name in section_name or section_name in sub_name):
                return sub.get("score"), sub.get("detail", "")
    return None, None


def build_spec_from_outline(scene_name, materials_paths, client_name="", output_path="spec_draft.yml"):
    """从场景大纲 + 客户材料生成 spec.yml 草稿。"""
    # §八 3.5：spec 草稿写入过 output/ 白名单，入口前置校验，
    # 避免材料读取 + LLM 逐章节提取完才在写入点抛异常
    from _renderer import _validate_output_path
    _validate_output_path(output_path)

    print("=== 场景大纲 → spec 草稿 ===")
    print(f"场景: {scene_name}")
    print(f"客户: {client_name or '(未指定)'}")
    print(f"材料: {materials_paths}\n")

    outline = load_outline(scene_name)
    print(f"大纲: {outline.get('scene', scene_name)}")
    print(f"页数范围: {outline.get('page_range', '?')}\n")

    print("[1/3] 读取客户材料...")
    materials_text = read_materials(materials_paths, client_name)
    if not materials_text.strip():
        print("错误：材料为空，无法生成 spec")
        return None
    print(f"  材料总长: {len(materials_text)} 字符\n")

    if client_name:
        ctx_path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "context.md")
        if os.path.exists(ctx_path):
            with open(ctx_path, "r", encoding="utf-8") as f:
                ctx_text = f.read()
            if ctx_text.strip():
                materials_text = f"【客户历史上下文】\n{ctx_text}\n\n【客户材料】\n{materials_text}"
                print(f"  已注入 context.md ({len(ctx_text)} 字符)")

    print("[2/3] 逐章节提取内容（LLM 防幻觉 + 语义召回证据 + 并行）...")

    # 加载招标评分标准（如果 bid-parse 已跑过）
    bid_criteria = _load_bid_criteria(client_name)
    scoring_list = bid_criteria.get("scoring", []) if bid_criteria else []
    fmt_req = bid_criteria.get("format_requirements", {}) if bid_criteria else {}
    if bid_criteria:
        print(f"  已加载 bid_criteria.json（{len(scoring_list)} 评分项）")

    sections = outline.get("structure", [])

    def _process_section(idx_sec):
        """处理单个章节（可并行调用）。"""
        i, sec = idx_sec
        sec_name = sec.get("section", f"未命名章节_{i+1}")
        print(f"\n  章节 {i+1}/{len(sections)}: {sec_name}")

        # 语义召回
        query = sec_name
        if sec.get("children"):
            query += " " + " ".join(sec["children"][:3])
        evidence = _recall_evidence(query, client_name)
        if evidence:
            print(f"    -> 召回 {len(evidence)} 条证据")

        result = extract_section_content(sec, materials_text, client_name, evidence_chunks=evidence)
        if not result:
            # §6.3：LLM 提取失败不再静默丢章节——保留页并放 text 占位，
            # 页数结构完整、用户可见，重新运行 outline-to-spec 可修复
            print(f"    [警告] 章节「{sec_name}」内容提取失败，已保留占位页"
                  f"（请重新运行 outline-to-spec 或手动补充）")
            role = sec.get("role", "title_body")
            return {
                "id": role or f"page_{i+1}",
                "title": sec_name,
                "layout": ROLE_LAYOUT.get(role, "title_body"),
                "elements": [{
                    "type": "text",
                    "role": "body",
                    "content": "（本章节内容提取失败，请重新运行 outline-to-spec 或手动补充）",
                }],
                "evidence": evidence,
            }

        role = sec.get("role", "title_body")
        layout = ROLE_LAYOUT.get(role, "title_body")

        # 匹配评分标准
        target_score, scoring_guide = _match_scoring_to_section(sec_name, scoring_list)

        page = {
            "id": role or f"page_{i+1}",
            "title": result.get("title", sec_name),
            "layout": layout,
            "elements": build_elements(layout, result, sec),
            "evidence": evidence,
        }
        if target_score is not None:
            page["target_score"] = target_score
        if scoring_guide:
            page["scoring_guide"] = scoring_guide

        print(f"    -> OK (layout: {layout}" +
              (f", 评分: {target_score}" if target_score else "") + ")")
        return page

    # 并行生成（max_workers=4 避免 API 限流）
    pages = [None] * len(sections)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_process_section, (i, sec)): i
            for i, sec in enumerate(sections)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
            except Exception as e:
                # 单章节异常不中断整批：保留占位页（与提取失败的占位策略一致）
                sec = sections[idx]
                sec_name = sec.get("section", f"未命名章节_{idx+1}")
                print(f"    [警告] 章节「{sec_name}」生成异常（{type(e).__name__}: {e}），已保留占位页")
                role = sec.get("role", "title_body")
                result = {
                    "id": role or f"page_{idx+1}",
                    "title": sec_name,
                    "layout": ROLE_LAYOUT.get(role, "title_body"),
                    "elements": [{
                        "type": "text",
                        "role": "body",
                        "content": "（本章节生成异常，请重新运行 outline-to-spec 或手动补充）",
                    }],
                    "evidence": [],
                }
            if result:
                pages[idx] = result

    pages = [p for p in pages if p is not None]

    print("\n[3/3] 生成 spec.yml...")
    spec = {
        "project": f"{client_name} - {outline.get('scene', scene_name)}" if client_name else outline.get('scene', scene_name),
        "author": "咨询团队",
        "date": __import__("datetime").date.today().isoformat(),
        "style": _infer_style_from_client(client_name),
        "document": {
            "title": f"{client_name}{outline.get('scene', scene_name)}" if client_name else outline.get('scene', scene_name),
            "subtitle": outline.get('scene_desc', ''),
        },
        "pages": pages,
    }

    # 如果有招标格式要求，注入 format 字段
    if fmt_req:
        spec["format"] = fmt_req

    # 草稿默认未确认，人工检查后改 confirmed: true 才允许渲染
    spec.setdefault("confirmed", False)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n spec 草稿已生成: {output_path}")
    print(f"  共 {len(pages)} 页")
    print("\n下一步:")
    print("  1. AI 微调 spec.yml（补充细节、调整结构）")
    print("  2. 人工确认后设 confirmed: true")
    print(f"  3. python _cli.py html-build {output_path} <输出.html>  生成 HTML + pptd 工程")
    return output_path


def _valid_layers(result):
    """宽容校验 LLM 返回的 layers 字段。

    合法（list、每项有 name 和 components list、组件非空）→ 返回规范化列表；
    缺失或结构不对 → 返回 None（调用方回退 text+cards，不报错）。
    """
    layers = result.get("layers")
    if not isinstance(layers, list) or not layers:
        return None
    cleaned = []
    for item in layers:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        components = item.get("components")
        if not name or not isinstance(components, list) or not components:
            return None
        cleaned.append({
            "name": str(name),
            "desc": str(item.get("desc") or ""),
            "components": [str(c) for c in components],
        })
    return cleaned


def build_elements(layout, result, section):
    """根据 layout 构造 spec 的 elements。"""
    section.get("children", [])
    key_points = result.get("key_points", [])
    content = result.get("content", "")
    data = result.get("data", [])

    if layout == "cards_3":
        # 痛点/问题/决策 → 卡片
        cards = []
        for i, point in enumerate(key_points[:3], 1):
            cards.append({
                "title": point if isinstance(point, str) else str(point),
                "tag": f"{i:02d}",
                "body": content[:100] if content else "",
                "highlight": data[i-1] if i <= len(data) else ""
            })
        return [{"type": "cards", "cards": cards}]

    elif layout == "tree":
        # 架构 → diagram（§七 2.7）：LLM 返回合法 layers 时产 architecture/layered
        layers = _valid_layers(result)
        if layers is not None:
            elements = []
            if content:
                elements.append({"type": "text", "role": "body", "content": content[:200]})
            elements.append({
                "type": "diagram",
                "diagram_type": "architecture",
                "subtype": "layered",
                "title": section.get("section", ""),
                "layers": layers,
            })
            return elements
        # 回退：无合法 layers 时仍产 text + 卡片组（P0 修复路径，内容不丢。
        # 原产出 type:"tree" 不在 KNOWN_ELEMENT_TYPES，三端静默丢弃）
        elements = []
        if content:
            elements.append({"type": "text", "role": "body", "content": content})
        labels = key_points[:4] if key_points else []
        if labels:
            cards = [{
                "title": label if isinstance(label, str) else str(label),
                "tag": f"{i:02d}",
                "body": "",
            } for i, label in enumerate(labels, 1)]
            elements.append({"type": "cards", "cards": cards})
        return elements if elements else [{"type": "text", "role": "body", "content": "(待填充)"}]

    elif layout == "phases":
        # 实施路径 → 阶段
        # P0 修复：原产出 phase/title/duration/items 三端均不识别。
        # 正典字段 name/desc/actions，并双写 label/goal 保证 DOCX 端可见
        # （Phase 1 normalize 层落地后可只写正典）
        phases = []
        for point in key_points[:3]:
            name = point if isinstance(point, str) else str(point)
            phases.append({
                "name": name,
                "label": name,
                "desc": "",
                "goal": "",
                "actions": [],
            })
        return [{"type": "phases", "phases": phases}]

    elif layout == "table":
        # 表格
        return [{
            "type": "table",
            "headers": ["项目", "说明", "数据"],
            "rows": [[point, content[:50], data[i] if i < len(data) else ""]
                     for i, point in enumerate(key_points[:5])]
        }]

    elif layout == "bullets":
        return [{"type": "bullets", "items": key_points if key_points else [content]}]

    else:
        # title_body
        elements = []
        if content:
            elements.append({"type": "text", "role": "body", "content": content})
        if key_points:
            elements.append({"type": "bullets", "items": key_points})
        return elements if elements else [{"type": "text", "role": "body", "content": "(待填充)"}]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python _outline_to_spec.py <场景名> [材料1 材料2 ...] --client <客户> --output <spec.yml>")
        sys.exit(0)

    scene = sys.argv[1]
    materials = []
    client = ""
    output = "spec_draft.yml"
    for arg in sys.argv[2:]:
        if arg.startswith("--client="):
            client = arg[9:]
        elif arg.startswith("--output="):
            output = arg[9:]
        else:
            materials.append(arg)

    if not materials and not client:
        print("错误：未指定材料文件，且未传 --client 无法自动扫描 refs/")
        sys.exit(1)

    build_spec_from_outline(scene, materials, client, output)
