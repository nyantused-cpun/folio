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
import re
import sys
import json
import yaml
import hashlib

from _paths import SCRIPT_DIR, validate_read_path_lenient
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed

OUTLINES_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "outlines")

# S1 拆分（2026-09-04）：role 表 / gold 注入 / 宽容校验器群迁 _diagram_extract，
# chapters 补页迁 _narrative_apply。此处 re-import 保持既有引用面可达
# （tests/test_gold_specs.py、tests/test_outline_to_spec.py、_cli_cmds_qa.py 等
#  经 _outline_to_spec 引用这些符号），主文件内消费者的 monkeypatch 面不变。
# 到期复审：tests monkeypatch 面迁移至真源后退役（复审点：下一大批次开工前）。——2026-09-07 复审：tests 仍经此面打桩（test_b3_cli_face/test_m1_f0/test_recall_eval/test_verify_render_report 等），保留；退役点顺延至 monkeypatch 面迁移完成。
from _diagram_extract import (
    ARCH_ROLES, GOLD_DEMO_MAX_TOKENS, GOLD_SPECS_DIR, ROLE_DIAGRAM,
    ROLE_DIAGRAM_PROMPTS, ROLE_DIAGRAM_SPEC, ROLE_ELEMENT_KIND, ROLE_LAYOUT,
    _diagram_data_from_result, _est_tokens, _gold_demo_block,
    _strip_comment_lines, _truncate_to_tokens, diagram_result_cacheable,
    load_gold_demo,
)
from _narrative_apply import _apply_chapters_container

# ---- LLM 提取缓存（重构计划 §八 3.3）----
# prompt 模板版本号：改动 extract_section_content 的 prompt 结构
# （含架构章节附加要求）时递增——版本号进缓存 key，旧缓存自动失效，无需手清文件
PROMPT_VERSION = "v2"
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


def _extract_cache_key(section, materials_text, client_name, evidence_chunks,
                       graphic_intent=None, direction_sha256=None):
    """缓存 key = sha256（提取的全部 prompt 输入）。

    evidence 参与 key 的决策：evidence 内容直接拼接进 prompt（见
    extract_section_content 的 evidence_block 构造），若不入 key，同一材料+章节
    但召回结果不同时会返回与当前证据不匹配的旧提取。安全优先——prompt 的任一
    输入变化都触发重新提取，代价仅是召回波动时缓存命中率略降。

    gold 示范入 key 的决策同理（§8 v1.2-4）：gold_block 直接拼接进 prompt，
    gold 库重提取/增删片段时内容变化必须触发重取；同时该字段的加入本身使
    注入功能上线前的旧 key 全部失配，等效于一次缓存失效，无需动 PROMPT_VERSION。

    graphic_intent（叙事设计单 graphic，"族/subtype"）同样直接进 prompt
    并改变 gold 注入，必须入 key；仅在有设计单时加入 payload，
    无设计单的存量 key 保持不变（兼容债红线）。
    direction_sha256（I-3 批3 C2 方向文件）同理：direction_block 直接拼接进
    prompt，存在性+内容 hash 必须入 key；仅在有方向文件（人批）时加入 payload，
    无方向文件的存量 key 保持不变（兼容红线）。
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
            _gold_demo_block(section, gold_override=graphic_intent)
            .encode("utf-8")).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "model": model,
    }
    if graphic_intent:
        payload["graphic_intent"] = graphic_intent
    if direction_sha256:
        payload["direction_sha256"] = direction_sha256
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


def read_materials(materials_paths, client_name="", allow_outside=False):
    """读取客户材料，返回纯文本。client_name 且未传 paths 时自动扫描 refs/。
    P2-4/D3 读边界：refs 扫描与显式材料路径一律限工作区内（allow_outside 显式放行）。"""
    from _pipeline import read_full_text
    paths = list(materials_paths)

    if client_name and not paths:
        refs_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "refs")
        if os.path.isdir(refs_dir):
            paths = [os.path.join(refs_dir, f) for f in os.listdir(refs_dir)
                     if not f.startswith(".")]
            print(f"  自动扫描客户 refs/: {len(paths)} 个文件")

    all_text = []
    for path in paths:
        # P2-4/D3 读边界：isabs 归一 + 工作区校验单点在 _paths（lenient 逐文件跳过）
        path = validate_read_path_lenient(path, allow_outside=allow_outside)
        if path is None or not os.path.exists(path):
            continue
        print(f"  读取: {path}")
        text = read_full_text(path)  # 容错壳：坏文件告警跳过，不裸崩整条链
        if text is not None:
            all_text.append(text)
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


def _spec_theme_for_client(client_name):
    """spec 的 theme 字段值：旧 style 语义归一为 v2 主题名。

    schema Step 2 起 spec 的 style 字段已废弃（fail-loud 迁移错误），
    outline-to-spec 生成草稿时必须直接产出 theme（DSH 实测 2026-09-01）。
    """
    from _renderer.theme import normalize_theme_name
    return normalize_theme_name(_infer_style_from_client(client_name))


# ---- I-3 批3 C2：方向文件机械消费（_knowledge/clients/{客户}/方向文件.md）----
def _load_direction_block(client_name):
    """读客户方向文件，返回 (prompt 块, 内容 sha256)；无文件 / 未人批 → ("", "")。

    只消费头部「确认状态：人批」的文件（草稿 = 未经人批，不进 prompt，
    与「未确认不入召回」同纪律）；无方向文件时行为与现状完全一致（兼容红线）。
    """
    if not client_name:
        return "", ""
    path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client_name, "方向文件.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return "", ""
    if not re.search(r"确认状态[：:]\s*人批", content.split("## ", 1)[0]):
        print("  [方向文件] 存在但确认状态非「人批」，按无方向文件处理（草稿不进 prompt）")
        return "", ""
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    block = ("\n【客户已定方向（人批）——提取内容须与之对齐，不得冲突】\n"
             + content.strip()[:3000] + "\n")
    return block, sha


def _enforce_evidence_anchors(spec):
    """方向文件（人批）生效时，spec 每页 evidence 条目强制挂有效锚点
    （_memory_guard 语法）：裸路径（召回结果 path#anchor）补 file: 前缀；
    补前缀后仍无法解析的条目剔除并打印（不静默）。返回剔除条数。"""
    from _memory_guard import parse_source_refs
    dropped = 0
    for page in spec.get("pages", []) or []:
        evs = page.get("evidence") if isinstance(page, dict) else None
        if not isinstance(evs, list) or not evs:
            continue
        kept = []
        for ev in evs:
            if isinstance(ev, dict):
                src = str(ev.get("source") or "")
                refs = parse_source_refs(src)
                if not refs or any(r["kind"] == "invalid" for r in refs):
                    ev["source"] = f"file:{src}"  # 裸路径补锚点前缀
                    refs = parse_source_refs(ev["source"])
                if refs and all(r["kind"] != "invalid" for r in refs):
                    kept.append(ev)
                    continue
            dropped += 1
        page["evidence"] = kept
    if dropped:
        print(f"  [方向文件] evidence 锚点强制：剔除无法挂有效锚点的条目 {dropped} 条")
    return dropped


def extract_section_content(section, materials_text, client_name="", evidence_chunks=None,
                            graphic_intent=None):
    """用 LLM 从材料中提取单章节内容（防幻觉）。

    直接调 chat + json_mode，不走 extract_json（后者会把 prompt 当待提取文本）。
    evidence_chunks: 召回的证据片段列表 [{"source", "snippet"}, ...]，注入 prompt 增强准确性。
    graphic_intent: 叙事设计单 page_map 项的 graphic（"族/subtype"），
    非空时在 prompt 追加图形意图行并按该 族/subtype 注入 gold 示范（条目 2-2）。
    """
    from _cloud_llm import chat, _parse_json, _validate_against_source, LLM_MODE

    section_name = section["section"]
    role = section.get("role", "")
    prompt_hint = section.get("prompt", "").strip()
    children = section.get("children", [])

    # §八 3.3：命中缓存直接返回，跳过 LLM 调用（key 覆盖全部 prompt 输入）
    # I-3 批3 C2：方向文件（人批）作为「客户已定方向」约束注入 prompt，hash 进缓存键
    direction_block, direction_sha = _load_direction_block(client_name)
    cache_key = _extract_cache_key(section, materials_text, client_name,
                                   evidence_chunks, graphic_intent=graphic_intent,
                                   direction_sha256=direction_sha)
    cached = _load_extract_cache().get(cache_key)
    # P3-2026-09-06：缓存值归一化——LLM 偶发返回 JSON 数组（如整段包成 []），
    # 非 dict 也原样入缓存，读取门却只认 dict，同键永不命中、每次重跑白烧
    # token。放行 list（命中后返回与首次完全相同的值，不改变缓存语义）。
    if cached is not None and isinstance(cached.get("result"), (dict, list)):
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

    # gold spec 写法示范（§8 v1.2-4）：本章节产 diagram 时注入，与 evidence 同区；
    # 叙事设计单指定 graphic 意图时按其 族/subtype 覆盖 role 默认映射（条目 2-2）。
    # 无意图时保持旧调用签名（兼容既有 monkeypatch 测试）
    gold_block = (_gold_demo_block(section, gold_override=graphic_intent)
                  if graphic_intent else _gold_demo_block(section))

    system = """你是咨询方案撰写助手。任务：从客户材料中提取指定章节的内容，输出 JSON。

【强制规则】
1. content 和 key_points 必须基于上方【客户材料】的原文内容，禁止编造
2. 如果材料中没有本章节相关内容，content 填"未提及"，key_points 和 data 返回空数组 []
3. data 字段只放材料中真实出现的数字/指标，原文引用
4. source_quote 必须是材料原文片段，用于防幻觉校验
5. 严格输出 JSON，不要加 markdown 代码块标记"""

    prompt = f"""【客户】{client_name or "（未指定）"}
{direction_block}{evidence_block}{materials_fallback}{gold_block}
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

    # 叙事设计单 graphic 意图（条目 2-2）：prompt 追加图形意图行
    if graphic_intent:
        prompt += (f"\n\n【图形意图】本页图形意图：{graphic_intent}（族/subtype），"
                   "请按该图形的字段结构提取内容")

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
    elif role in ROLE_DIAGRAM_PROMPTS:
        # 其他图形化角色：追加结构化字段，让 LLM 一次给出可渲染的 diagram 数据
        prompt += ROLE_DIAGRAM_PROMPTS[role] + """

要求：
1. 所有字段必须来自材料原文，禁止编造；材料不足时对应数组返回 []
2. 字段结构必须与上面示例一致，不要发明新键"""

    # 图形类章节输出更长（多结构化字段），且 zhipu 思考模式会消耗 token 预算，
    # 实测 2000 max_tokens 会被 reasoning 耗尽导致空 content → 所有产图 role 提到 4000
    max_tokens = 4000 if role in ROLE_DIAGRAM_SPEC else 2000
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
    # I-2 T5：事实一致性校验（数字/实体），违规入隔离区日志，不阻断生成
    try:
        from _fact_guard import guard_check, enqueue_guard_item
        _fg_text = " ".join(filter(None, [
            result.get("content", ""),
            *(result.get("key_points") or []),
            *(result.get("data") or []),
        ]))
        _fg = guard_check(_fg_text, client=client_name)
        for _v in (_fg.get("violations") or [])[:20]:
            print(f"    [fact-guard] {section_name} 违规: {_v}")
        if _fg.get("violations"):
            enqueue_guard_item({
                "stage": "outline_to_spec.extract_section_content",
                "section": section_name,
                "client": client_name,
                "violations": _fg["violations"][:20],
            })
    except Exception as _e:
        print(f"    [warn] fact-guard 校验失败: {_e}")
    # 只缓存成功结果：提取失败（上面的 return None）不入缓存，重跑可重试；
    # 图形 section 再过校验门（P1-13 fail-closed：畸形结果不入缓存，重跑可自愈）
    if diagram_result_cacheable(section, result):
        _cache_put(cache_key, section_name, result)
    return result


def _recall_evidence(query, client_name, top_k=5):
    """按主题召回证据片段，用于注入 spec 提取的 prompt。

    返回 [{"source": "文件名#锚点", "snippet": "片段文本"}, ...]
    """
    if not query or not client_name:
        return []

    def _plain(value):
        """召回结果里混入 numpy 标量（np.str_/np.float64 等）会污染 yaml/json 序列化
        （spec 的 evidence 段写进 python/object 标签，verify 无法解析）——统一转原生 str。
        注意 np.str_ 是 str 的子类，必须先用 .item() 还原再 isinstance 判定。"""
        if value is None:
            return ""
        if hasattr(value, "item"):  # numpy 标量 → 原生 Python 标量（先于 isinstance）
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, str):
            return value
        return str(value)

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
        return [{"source": _plain(r.get("path")) or "?",
                 "snippet": _plain(r.get("snippet")),
                 "parent_context": _plain(r.get("parent_context"))}
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


def build_spec_from_outline(scene_name, materials_paths, client_name="", output_path="spec_draft.yml",
                            narrative_path=None, allow_outside=False):
    """从场景大纲 + 客户材料生成 spec.yml 草稿。

    narrative_path（条目 2-2，可选）：叙事设计单 yml。给出时——
    页面顺序/页面 id/layout 以 page_map 为准（与 outline.structure 按位置 zip），
    graphic 意图注入对应页的提取 prompt 与 gold 示范，spec 顶层写
    narrative_ref/container。不给时行为零变化（兼容债红线）。
    """
    # §八 3.5：spec 草稿写入过 output/ 白名单，入口前置校验，
    # 避免材料读取 + LLM 逐章节提取完才在写入点抛异常
    from _renderer import _validate_output_path
    _validate_output_path(output_path)

    print("=== 场景大纲 → spec 草稿 ===")
    print(f"场景: {scene_name}")
    print(f"客户: {client_name or '(未指定)'}")
    print(f"材料: {materials_paths}\n")

    # 叙事设计单（条目 2-2）：开工先校验，错误逐条打印并 exit 2（门禁阻断）
    narrative = None
    page_map = None
    if narrative_path:
        from _renderer.narrative_schema import load_and_validate
        narrative, errors = load_and_validate(narrative_path)
        if errors:
            print(f"[阻断] 叙事设计单校验未通过: {narrative_path}")
            for err in errors:
                print(f"  - {err}")
            sys.exit(2)
        page_map = narrative.get("page_map", [])
        # D-b=A 确认门：生成前打印摘要；确认并入 L4 大纲确认环节，不新增独立门禁
        print(f"叙事设计单: {os.path.basename(narrative_path)}")
        print(f"  受众: {narrative.get('audience')} | 叙事弧线: {narrative.get('arc')}")
        print(f"  阅读行为: {narrative.get('reading')} | 页数预算: {narrative.get('page_budget')}"
              f" | page_map: {len(page_map)} 页")
        print("  提示：叙事设计单随 L4 大纲确认环节一并确认\n")

    outline = load_outline(scene_name)
    print(f"大纲: {outline.get('scene', scene_name)}")
    print(f"页数范围: {outline.get('page_range', '?')}\n")

    print("[1/3] 读取客户材料...")
    materials_text = read_materials(materials_paths, client_name,
                                    allow_outside=allow_outside)
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

    # I-3 批3 C2：方向文件（人批）存在时，spec evidence 段条目强制挂有效锚点
    direction_active = bool(_load_direction_block(client_name)[1])
    if direction_active:
        print("  已加载方向文件（人批）：注入「客户已定方向」约束 + evidence 锚点强制")

    # 加载招标评分标准（如果 bid-parse 已跑过）
    bid_criteria = _load_bid_criteria(client_name)
    scoring_list = bid_criteria.get("scoring", []) if bid_criteria else []
    fmt_req = bid_criteria.get("format_requirements", {}) if bid_criteria else {}
    if bid_criteria:
        print(f"  已加载 bid_criteria.json（{len(scoring_list)} 评分项）")

    sections = outline.get("structure", [])

    # 条目 2-2：page_map 与 outline.structure 按位置一一对应，数量不一致即阻断
    if page_map is not None and len(page_map) != len(sections):
        print(f"[阻断] 叙事设计单 page_map 共 {len(page_map)} 页，"
              f"大纲「{scene_name}」共 {len(sections)} 节，数量不一致，"
              "无法按位置一一对应")
        sys.exit(2)

    def _page_shell(i, sec, role):
        """有设计单时页面 id/layout 取 page_map[i]；否则沿用 role 默认映射。"""
        pm = page_map[i] if page_map else None
        return {
            "id": pm["page"] if pm else (role or f"page_{i+1}"),
            # 批6（C17）：无映射 role 的兜底从旧值 title_body 改受控版式 P03
            # （结论摘要=最通用内容页）；存量旧值 spec 经 LEGACY_LAYOUTS 白名单
            # 仍自由流渲染（F9），必需构件缺失仅 warning（D-e 拍板不变）
            "layout": pm["layout"] if pm else ROLE_LAYOUT.get(role, "P03"),
        }

    def _process_section(idx_sec):
        """处理单个章节（可并行调用）。"""
        i, sec = idx_sec
        sec_name = sec.get("section", f"未命名章节_{i+1}")
        pm = page_map[i] if page_map else None
        graphic = pm.get("graphic") if pm else None
        print(f"\n  章节 {i+1}/{len(sections)}: {sec_name}")
        if graphic:
            print(f"    -> 图形意图: {graphic}")

        # 语义召回
        query = sec_name
        if sec.get("children"):
            query += " " + " ".join(sec["children"][:3])
        evidence = _recall_evidence(query, client_name)
        if evidence:
            print(f"    -> 召回 {len(evidence)} 条证据")

        result = extract_section_content(sec, materials_text, client_name,
                                         evidence_chunks=evidence,
                                         graphic_intent=graphic)
        if not result:
            # §6.3：LLM 提取失败不再静默丢章节——保留页并放 text 占位，
            # 页数结构完整、用户可见，重新运行 outline-to-spec 可修复
            print(f"    [警告] 章节「{sec_name}」内容提取失败，已保留占位页"
                  f"（请重新运行 outline-to-spec 或手动补充）")
            role = sec.get("role", "title_body")
            page = {
                **_page_shell(i, sec, role),
                "title": sec_name,
                "elements": [{
                    "type": "text",
                    "role": "body",
                    "content": "（本章节内容提取失败，请重新运行 outline-to-spec 或手动补充）",
                }],
                "evidence": evidence,
            }
            if graphic:
                page["graphic_intent"] = graphic
            return page

        role = sec.get("role", "title_body")

        # 匹配评分标准
        target_score, scoring_guide = _match_scoring_to_section(sec_name, scoring_list)

        page = {
            **_page_shell(i, sec, role),
            "title": result.get("title", sec_name),
            "elements": build_elements(result, sec),
            "evidence": evidence,
        }
        if graphic:
            # 供 verify 事后核对的意图留痕；渲染层不消费此键
            page["graphic_intent"] = graphic
        if target_score is not None:
            page["target_score"] = target_score
        if scoring_guide:
            page["scoring_guide"] = scoring_guide

        print(f"    -> OK (layout: {page['layout']}" +
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
                    **_page_shell(idx, sec, role),
                    "title": sec_name,
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
        "theme": _spec_theme_for_client(client_name),
        "document": {
            "title": f"{client_name}{outline.get('scene', scene_name)}" if client_name else outline.get('scene', scene_name),
            "subtitle": outline.get('scene_desc', ''),
        },
        "pages": pages,
    }

    # 叙事设计单溯源（条目 2-2）：narrative_ref 只写文件名；container 取 reading
    if narrative:
        spec["narrative_ref"] = os.path.basename(narrative_path)
        spec["container"] = narrative.get("reading")

    # 如果有招标格式要求，注入 format 字段
    if fmt_req:
        spec["format"] = fmt_req

    # I-3 批3 C2：方向文件生效 → spec evidence 段条目强制挂有效锚点（_memory_guard 语法）
    if direction_active:
        _enforce_evidence_anchors(spec)

    # container=chapters 最小落地（条目 2-7，D-a=A）：自动补目录/章节页
    if spec.get("container") == "chapters":
        spec["pages"] = _apply_chapters_container(spec["pages"], page_map)

    # 草稿默认未确认，人工检查后改 confirmed: true 才允许渲染
    spec.setdefault("confirmed", False)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n spec 草稿已生成: {output_path}")
    print(f"  共 {len(spec['pages'])} 页")
    print("\n下一步:")
    print("  1. AI 微调 spec.yml（补充细节、调整结构）")
    print("  2. 人工确认后设 confirmed: true")
    print(f"  3. python _cli.py html-build {output_path} <输出.html>  生成 HTML + pptd 工程")
    return output_path






def build_elements(result, section):
    """按 role 构造 spec 的 elements（§3-6：与页面版式 layout 解耦——
    layout 只作为页面版式字段落到 page dict，元素构造按 ROLE_ELEMENT_KIND
    的 role 形态分支，与迁移前旧 layout 字符串分支一一对应）。"""
    key_points = result.get("key_points", [])
    content = result.get("content", "")
    data = result.get("data", [])
    role = section.get("role", "")
    kind = ROLE_ELEMENT_KIND.get(role, "title_body")

    # 图形化角色优先：LLM 返回了合法结构化字段时，直接产 diagram；
    # 没返回/结构非法则继续走下方原有 text/cards/table 回退，内容不丢。
    diagram_spec = ROLE_DIAGRAM_SPEC.get(role)
    if diagram_spec:
        diagram_data = _diagram_data_from_result(diagram_spec, result)
        if diagram_data is not None:
            elements = []
            if content:
                elements.append({"type": "text", "role": "body", "content": content[:200]})
            elements.append({
                "type": "diagram",
                "diagram_type": diagram_spec["diagram_type"],
                "subtype": diagram_spec["subtype"],
                "title": section.get("section", ""),
                **diagram_data,
            })
            return elements

    if kind == "cards":
        # 痛点/问题/决策 → 卡片
        cards = []
        for i, point in enumerate(key_points[:3], 1):
            cards.append({
                "title": point if isinstance(point, str) else str(point),
                "tag": f"{i:02d}",
                "body": content[:100] if content else "",
                "highlight": data[i-1] if i <= len(data) else ""
            })
        if not cards:
            # LLM 返回空 key_points 时不产空 cards（schema error），回退 text
            return [{"type": "text", "role": "body", "content": content or "(待填充)"}]
        return [{"type": "cards", "cards": cards}]

    elif kind == "layered":
        # 架构回退：layers 未通过上方 diagram 校验（architecture/layered 由
        # ROLE_DIAGRAM_SPEC 优先路径产出）时仍产 text + 卡片组
        # （P0 修复路径，内容不丢。原产出 type:"tree" 不在 KNOWN_ELEMENT_TYPES，
        # 三端静默丢弃）
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

    elif kind == "phases":
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
        if not phases:
            # LLM 返回空 key_points 时不产空 phases（schema error），回退 text
            return [{"type": "text", "role": "body", "content": content or "(待填充)"}]
        return [{"type": "phases", "phases": phases}]

    elif kind == "table":
        # 表格。P3-2026-09-06：key_points 与 cards/layered/phases 分支同口径
        # str 化——LLM 混入数字时裸值曾直落 rows，下游 verify/渲染端类型漂移
        return [{
            "type": "table",
            "headers": ["项目", "说明", "数据"],
            "rows": [[point if isinstance(point, str) else str(point),
                      content[:50], data[i] if i < len(data) else ""]
                     for i, point in enumerate(key_points[:5])]
        }]

    elif kind == "bullets":
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
