# -*- coding: utf-8 -*-
"""CLI 质量面命令（T1 拆分自 _cli.py，2026-09-01）。
承载：质量面（verify/spec-edit/doctor/ocr/style-check/vision-describe/web-search/session-start）。不改命令行为。"""
import os
import re
import json
import sys

from _cli_infra import SCRIPT_DIR
from _cli_guards import (REQUIRED_GEN_SKILLS, OPTIONAL_GEN_SKILLS,
                         _sentinel_enabled)
from _session import auto_for_input
from _archive_auto import record_session_start
from _cloud_llm import vision_chat
from _state import get_state, set_state, advance as advance_state

def _print_gold_spec_hint(spec_path):
    """手写/编辑 spec 后提示该 diagram subtype 有金标准（P2，至少 CLI 提示）。"""
    if not str(spec_path).lower().endswith((".yml", ".yaml")):
        return
    try:
        import yaml
        from _outline_to_spec import GOLD_SPECS_DIR
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        subtypes = set()
        for page in spec.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            for elem in page.get("elements", []) or []:
                if isinstance(elem, dict) and elem.get("type") == "diagram":
                    dt = elem.get("diagram_type", "")
                    st = elem.get("subtype", "")
                    if dt and st:
                        subtypes.add((dt, st))
        if not subtypes:
            return
        for dt, st in sorted(subtypes):
            gold = os.path.join(GOLD_SPECS_DIR, f"{dt}__{st}.yml")
            if os.path.exists(gold):
                print(f"[金标准] {dt}/{st} 有验收过的 gold spec，"
                      f"是否对照：{gold}")
    except Exception:
        pass


def cmd_verify(args):
    only = getattr(args, "only", None)
    mode = getattr(args, "mode", None)
    if mode == "quote":
        from _quote_gate import check_verify
        issues, warnings = check_verify(args.file)
        print("=== 报价门禁（verify --mode quote）===")
        for i in issues:
            print(f"  [FAIL] {i}")
        for w in warnings:
            print(f"  [warn] {w}")
        if issues:
            print("  结论: FAIL（需修复）")
            sys.exit(2)
        print("  结论: PASS（判断性 WARN 不阻断）")
        sys.exit(0)
    if only == "style":
        from _verify import verify_style_scan
        ok, msg = verify_style_scan(args.file)
        print(msg)
        sys.exit(0 if ok else 1)
    # late import（单源化）：调用时绑定，测试对 _verify_hook.run_single 的
    # monkeypatch 才能对本命令生效（模块级 from-import 绑定不随 patch 更新）
    from _verify_hook import run_single
    ok = run_single(args.file)
    _print_gold_spec_hint(args.file)
    sys.exit(0 if ok else 1)


def cmd_spec_edit(args):
    """spec.yml 类型化增量变更（P1-6）。

    用法示例：
      python _cli.py spec-edit spec.yml --op add_page --page-id p04 --title "实施计划" --layout phases
      python _cli.py spec-edit spec.yml --op delete_page --page-id p04
      python _cli.py spec-edit spec.yml --op add_element --page-id p03 --element '{"type":"text","content":"新增内容"}'
      python _cli.py spec-edit spec.yml --op update_element --page-id p03 --index 0 --updates '{"content":"改后内容"}'
      python _cli.py spec-edit spec.yml --op delete_element --page-id p03 --index 0
    """
    from _spec_edit import OPERATIONS
    import json as _json

    op = args.op
    if op not in OPERATIONS:
        print(f"未知操作 '{op}'，合法值：{'/'.join(sorted(OPERATIONS))}")
        sys.exit(1)

    spec_path = args.spec
    if not os.path.exists(spec_path):
        print(f"spec 文件不存在: {spec_path}")
        sys.exit(1)

    # 解析 element / updates JSON
    element = None
    updates = None
    if args.element:
        try:
            element = _json.loads(args.element)
        except _json.JSONDecodeError as e:
            print(f"--element JSON 解析失败: {e}")
            sys.exit(1)
    if args.updates:
        try:
            updates = _json.loads(args.updates)
        except _json.JSONDecodeError as e:
            print(f"--updates JSON 解析失败: {e}")
            sys.exit(1)

    # 分发到对应操作
    if op == "add_page":
        if not args.page_id or not args.title:
            print("add_page 需要 --page-id 和 --title")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id, args.title,
                                layout=args.layout or "bullets", elements=element.get("elements") if element else None)
    elif op == "update_page":
        if not args.page_id or not updates:
            print("update_page 需要 --page-id 和 --updates")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id, updates)
    elif op == "delete_page":
        if not args.page_id:
            print("delete_page 需要 --page-id")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id)
    elif op == "add_element":
        if not args.page_id or not element:
            print("add_element 需要 --page-id 和 --element")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id, element, index=args.index)
    elif op == "update_element":
        if not args.page_id or args.index is None or not updates:
            print("update_element 需要 --page-id --index 和 --updates")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id, args.index, updates)
    elif op == "delete_element":
        if not args.page_id or args.index is None:
            print("delete_element 需要 --page-id 和 --index")
            sys.exit(1)
        result = OPERATIONS[op](spec_path, args.page_id, args.index)

    # 输出结果
    if result["ok"]:
        print(f"[spec-edit] {op} 成功")
        if "page_index" in result and result["page_index"] is not None:
            print(f"  页面位置: index={result['page_index']}")
        if "element_index" in result and result["element_index"] is not None:
            print(f"  元素位置: index={result['element_index']}")
        if "deleted_index" in result and result["deleted_index"] is not None:
            print(f"  已删除位置: index={result['deleted_index']}")
        # 操作后全量校验
        from _spec_edit import _load_spec
        from _renderer.schema import validate_spec
        spec = _load_spec(spec_path)
        errors = validate_spec(spec)
        if errors:
            print(f"  [warn] 操作后校验发现 {len(errors)} 个问题:")
            for e in errors[:5]:
                print(f"    - {e}")
        else:
            print("  校验通过")

        # P2：手写/编辑路径提示有金标准
        _print_gold_spec_hint(spec_path)

        # M3-F2：--confirm 确认 spec -> spec_confirmed（仅操作成功后推进）
        if getattr(args, "confirm", False):
            client = getattr(args, "client", None)
            if not client:
                m = re.search(r"output[\\/]([^\\/]+)[\\/]", spec_path.replace("\\", "/"))
                if m:
                    client = m.group(1)
            if client:
                try:
                    advance_state(client, "spec_confirmed")
                    print(f"[state] 已确认 spec，{client} -> spec_confirmed")
                except Exception as e:
                    print(f"[state] 阶段推进失败（不阻断）: {e}")
            else:
                print("[state] --confirm 未指定 --client 且 spec 不在 output/<客户>/ 下，跳过阶段推进")
    else:
        print(f"[spec-edit] {op} 失败:")
        for e in result["errors"]:
            print(f"  - {e}")
        # CLI 契约 v1 §2：1=执行失败（页/元素不存在、索引越界等操作被拒）；
        # 2 仅守卫阻断（spec 未确认、confirm 哈希不匹配等）——那些出口在
        # generate/confirm/review 流程（_cli.py 顶层 RenderBlockedError 映射 /
        # theme_guard critical），spec-edit 命令体内没有守卫阻断路径。C-A3
        sys.exit(1)




def cmd_doctor(args):
    """doctor：只读环境诊断（P0-2，dev_plan_cli_panel_2026-08-18）。"""
    from _doctor import run_doctor

    run_doctor(as_json=bool(getattr(args, "json", False)))


def cmd_ocr(args):
    """ocr：图片逐字提取（P0-3，精确层；无本地 tesseract 时走视觉链 fallback）。"""
    image_path = args.image
    if not os.path.exists(image_path):
        print(f"[ocr] 文件不存在: {image_path}")
        sys.exit(1)
    from _cloud_llm import LLM_MODE, host_prompt, vision_chat

    provider = args.provider or "minimax"
    prompt = (
        "你是 OCR 引擎。逐字提取图中所有文字，按阅读顺序每行一条输出。"
        "不要描述图片、不要翻译、不要补全缺字、不要输出任何额外说明。"
        "图中无文字时只输出【无文字】。"
    )
    print(f"[ocr] {image_path} (provider={provider})")
    if LLM_MODE == "host":
        host_prompt("ocr", prompt, image_path=image_path)
        print("[host-mode] 机械部分已完成；请按上方 prompt 完成逐字提取并继续流程")
        return
    text = vision_chat(prompt, image_path, provider=provider)
    if not text:
        print("[ocr] 未拿到结果（key 未配置 / 网络失败）")
        return
    print("--- ocr BEGIN ---")
    print(text.strip())
    print("--- ocr END ---")




def cmd_style_check(args):
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}")
        sys.exit(1)
    from _verify import verify_style_scan
    ok, msg = verify_style_scan(args.file)
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_vision_describe(args):
    """vision-describe：把图片转成文字描述，返回给纯文本 agent 用。

    当 AI agent 本身没有视觉能力时，先用 vision 模型把图片读一遍，
    把描述当作 prompt 上文注入。当前 agent 是多模态模型时（AGENT_MODEL_SUPPORTS_VISION=true）会跳过。

    --rounds 2：A/B 隔离双观察 + 分歧仲裁（仅 json 格式；参考 ds-vision-v3 证据契约）。
    """
    image_path = args.image
    from _cli_infra import _guard_read_path
    image_path = _guard_read_path(args, image_path, label="vision-describe")
    if not os.path.exists(image_path):
        print(f"[vision-describe] 文件不存在: {image_path}")
        sys.exit(1)
    from _cloud_llm import VISION_JSON_TEMPLATE, vision_describe_ab, LLM_MODE, host_prompt
    fmt = getattr(args, "format", "json")
    rounds = int(getattr(args, "rounds", 1) or 1)
    show_rounds = bool(getattr(args, "show_rounds", False))
    if fmt == "text" and rounds > 1:
        print("[vision-describe] text 格式无结构化 diff，--rounds 2 降级为单次观察"
              "（A/B 仲裁仅支持 json 格式）")
        rounds = 1
    if fmt == "json":
        prompt = (args.prompt or "请描述这张图片的内容。") + VISION_JSON_TEMPLATE
    else:
        prompt = args.prompt or "请详细描述这张图片的内容。"
    provider = args.provider or "minimax"
    print(f"[vision-describe] {image_path} (provider={provider}, format={fmt}, rounds={rounds})")
    if LLM_MODE == "host":
        host_prompt("vision", prompt, image_path=image_path)
        print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return
    meta = None
    if rounds >= 2 and fmt == "json":
        desc, meta = vision_describe_ab(prompt, image_path, provider=provider)
        if not desc:
            print(f"[vision-describe] A/B 双观察失败（{meta.get('failed_round')} 轮无结果），"
                  f"降级为单次观察")
            rounds, meta = 1, None
            desc = vision_chat(prompt, image_path, provider=provider)
    else:
        desc = vision_chat(prompt, image_path, provider=provider)
    if not desc:
        print("[vision-describe] 未拿到描述（key 未配置 / agent 自带多模态 / 网络失败）")
        return
    print("--- vision-describe BEGIN ---")
    if fmt == "json":
        from _cloud_llm import _parse_json
        data = _parse_json(desc) or {"summary": desc.strip()}
        data["source_image"] = os.path.abspath(image_path)
        if meta:
            data["verification_mode"] = meta.get("verification_mode")
            if meta.get("conflicts"):
                data["conflicts"] = meta["conflicts"]
            if show_rounds:
                data["_rounds"] = meta  # 含 A/B 两轮解析后原文，审计用
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(desc.strip())
    print("--- vision-describe END ---")


def cmd_web_search(args):
    """web-search：联网搜索（双引擎融合：Tavily + 字节搜索）。"""
    from _cloud_llm import web_search

    query = args.query
    max_results = args.max_results
    engines = args.engines.split(",") if args.engines else None

    print(f"[web-search] query=\"{query}\" engines={engines or 'auto'} max_results={max_results}")
    results = web_search(query, max_results=max_results, engines=engines)

    if not results:
        print("[web-search] 无结果")
        sys.exit(1)

    print(f"\n=== web-search 结果（{len(results)} 条） ===\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r.get('source', '?')}] {r.get('title', '')}")
        print(f"   {r.get('url', '')}")
        content = r.get("content", "")
        # P3 加固（2026-09-06 安全审查）：content 为服务器可控内容，默认不回显，
        # 防止注入文本随会话日志持久化；调试需要时显式开 DEBUG_REMOTE_ECHO=1
        if os.environ.get("DEBUG_REMOTE_ECHO", "").lower() in ("1", "true", "yes"):
            if len(content) > 200:
                content = content[:200] + "..."
            print(f"   {content}")
        print()




def cmd_session_start(args):
    """会话开始：auto_for_input 一次完成判层级+加载上下文+语义召回。"""
    client = args.client if args.client else None
    json_output = getattr(args, 'json', False)

    # 客户名纠错（别名/近似匹配），避免把别名当新客户创建空目录
    if client:
        try:
            from _aliases import resolve_client_name
            resolved, candidates, matched_by = resolve_client_name(client)
            if matched_by == 'alias':
                if not json_output:
                    print(f"[session] 客户名 '{client}' 已解析为 '{resolved}'（别名匹配）")
                client = resolved
            elif matched_by == 'substring':
                if not json_output:
                    print(f"[session] ⚠️ 未找到客户 '{client}'，近似候选: {', '.join(candidates)}")
                    print(f"[session] 继续使用 '{client}'，若需切换请在后续消息中明确指定")
            elif matched_by is None:
                if not json_output:
                    print(f"[session] ℹ️ 客户 '{client}' 不存在，将作为新客户处理")
        except Exception as e:
            if not json_output:
                print(f"  [warn] 客户名解析失败: {e}")

    # 会话开始时间戳（save 自动归档靠它界定会话窗口）
    if client:
        try:
            record_session_start(client)
        except Exception:
            pass

    r = auto_for_input(args.input, client_name=client)

    # P1-3 C3：session-start 已加载决策/上下文，记为读取事件
    if client:
        try:
            from datetime import datetime
            set_state(client, decisions_read_at=datetime.now().isoformat(timespec="seconds"))
        except Exception:
            pass

    recall_results = r.get("recall", [])
    recall_degraded = any(bool(item.get("degraded")) for item in recall_results)
    warnings = list(r.get("warnings", []) or [])
    if recall_degraded:
        warnings.append("召回链路存在降级（embedding/索引/关键词 fallback），结果质量可能打折")

    # F0-12：session-start 附带用量摘要（文本 / JSON 两分支）
    try:
        from _cloud_llm import get_usage_summary
        usage_summary = get_usage_summary()
    except Exception:
        usage_summary = {}

    # M3-F2：读取当前阶段；读取失败不阻断原行为（默认 intake）
    try:
        stage = get_state(client).get("stage", "intake")
    except Exception:
        stage = "intake"

    # P1-5：生成软锚定数据（由 creator preset 的 soft-anchor 插件读取，禁止手写第二份铁律）
    if client:
        try:
            from datetime import datetime as _dt
            soft_dir = os.path.join(SCRIPT_DIR, ".folio", "logs")
            os.makedirs(soft_dir, exist_ok=True)
            brief = r.get("client_brief") or {}
            soft = {
                "client": client,
                "generated_at": _dt.now().isoformat(timespec="seconds"),
                "level": r.get("level", "?"),
                "stage": stage,
                "head_context": (r.get("head_context") or "")[:600],
                "recent_decisions": (r.get("recent_task_decisions") or [])[:3],
                "refs": (brief.get("refs") or [])[:20],
                "missing": (brief.get("missing") or [])[:20],
            }
            with open(os.path.join(soft_dir, "soft_anchor.json"), "w", encoding="utf-8") as f:
                json.dump(soft, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    if json_output:
        # P1-4: 结构化 JSON 输出，供程序化消费（省去 stdout 解析）
        # P1：透传 client_index / head_context / tail_checklist（DSH folio_session_start 消费）
        # P1-3/F0-12：附 recall_degraded 与 usage_summary
        import json as _json
        output = {
            "level": r.get("level", "?"),
            "mode": r.get("mode", "?"),
            "client": client,
            "stage": stage,
            "context_summary": r.get("context_summary", ""),
            "client_index": r.get("client_index", ""),
            "head_context": r.get("head_context", ""),
            "tail_checklist": r.get("tail_checklist", ""),
            "keynote": r.get("keynote"),  # I-3 A3：只增不改（无 keynote 客户为 null）
            "recent_task_decisions": r.get("recent_task_decisions", []),
            "client_brief": r.get("client_brief", {}),
            "recall": recall_results,
            "recall_degraded": recall_degraded,
            # F0-9 修正：只给新增的 degraded 降级提示加 [warn] 前缀，
            # 保留既有 warnings 原文，避免改变 JSON 消费方对普通 warning 的解析。
            "warnings": [f"[warn] {w}" if w.startswith("召回链路存在降级") else w for w in warnings],
            "usage_summary": usage_summary,
            "vision_supported": os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"),
        }
        print(_json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("=== 会话上下文 ===")
    print(f"  层级: {r.get('level', '?')} | 模式: {r.get('mode', '?')}")
    print(f"  阶段: {stage}")
    print(f"  摘要: {r.get('context_summary', '无')[:300]}")

    # P1-2：客户简报（阶段/任务/refs/缺失信息）
    client_brief = r.get("client_brief") or {}
    if client_brief:
        print("\n=== 客户简报 ===")
        print(f"  客户: {client_brief.get('client', '')} | 阶段: {client_brief.get('stage', 'intake')} | 当前任务: {client_brief.get('task_id', '') or '无'}")
        brief_refs = client_brief.get("refs") or []
        if brief_refs:
            print(f"  refs 清单（{len(brief_refs)} 个，按任务读取）：")
            for i, ref in enumerate(brief_refs[:10], 1):
                print(f"    [{i}] {ref}")
        elif client_brief.get("exists"):
            print("  refs 清单：无")
        brief_missing = client_brief.get("missing") or []
        if brief_missing:
            print("  缺失信息清单：")
            for m in brief_missing[:10]:
                print(f"    - {m}")
    if recall_degraded:
        print("  [warn] 召回链路存在降级（embedding/索引/关键词 fallback），结果质量可能打折")
    if recall_results:
        print(f"\n  召回 {len(recall_results)} 条:")
        for i, item in enumerate(recall_results[:5]):
            print(f"    [{i}] {item.get('client', '?')} ({item.get('score', 0):.3f}) {item.get('path', '?')[-60:]}")
            snippet = item.get("snippet", "")
            if snippet:
                print(f"        片段: {snippet[:120]}")
    if usage_summary:
        print(f"  [usage] 本月累计调用 {usage_summary.get('total_calls', 0)} 次 / "
              f"{usage_summary.get('total_tokens', 0)} tokens")
    for w in warnings:
        print(f"  [warn] {w}")
    # P1-3：非 JSON 分支打印最近 task 决策（Kimi 等价出口）
    recent = r.get("recent_task_decisions", [])
    if recent:
        print(f"\n  最近会话决策 {len(recent)} 条:")
        for i, rd in enumerate(recent[:3], 1):
            title = rd.get("title", "") or ""
            dec = rd.get("decision", "") or ""
            print(f"    [{i}] {title}" + (f"：{dec[:60]}" if dec else ""))
    # P1：非 JSON 分支打印 HEAD/TAIL 等价出口（Kimi 无 DSH 结构化消费，靠文本）
    head_ctx = r.get("head_context", "")
    tail_cl = r.get("tail_checklist", "")
    if head_ctx:
        # P2-6：head_ctx 首行已含「=== 核心约束刷新 ===」，不再重复打印标题
        print(f"\n{head_ctx.rstrip()}")
    if tail_cl:
        print(f"\n{tail_cl.rstrip()}")
    # vision 路由握手：告知 AI 本会话图片处理方式（自我评估优先，env flag 兜底）
    if os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"):
        print("  [vision] AGENT_MODEL_SUPPORTS_VISION=true：图片请直接读取（agent 多模态），vision-describe 将跳过")
    else:
        print("  [vision] 图片路由：能直接读图（多模态）就直接读；不能则用 python _cli.py vision-describe <图片> 预转文本")

    # skill 注入（档位1，按层级条件注入）：L3/L4 生成/规划类任务提醒先读必读 skill
    # 解决"AI 生成 HTML/PPT 前没读 skill"——把 skill 清单喂到嘴边；
    # 机械兜底由 REQUIRE_SKILL_SENTINEL 哨兵门禁承担（档位2，默认开）
    level = r.get("level", "?")
    if level in ("L3", "L4"):
        print("\n=== 生成前置 skill 提示（强制清单来自 _cli_guards.REQUIRED_GEN_SKILLS）===")
        print("本任务为 L3/L4。必读 skill 如下，读完后自行判断走多完整：")
        required_hints = {
            "delivery-pipeline": "交付顺序：HTML 先行->确认->PPT",
            "spec-writing-guide": "spec 字段/容量/confirmed 门禁",
            "visual-craft-guide": "视觉与图形规范（反模式/选型/容量预算/画法细节）；生成 HTML/PPT 方案、写 diagram 必读",
        }
        for skill_name in REQUIRED_GEN_SKILLS:
            hint = required_hints.get(skill_name, "")
            suffix = f"   # {hint}" if hint else ""
            print(f"  python _cli.py load-skill {skill_name}{suffix}")
        print("  [按需] " + " / ".join(OPTIONAL_GEN_SKILLS))
        print("  简便工作（编辑已有产出/纯检索/单页微调/工程代码/内部分析）可跳过。")
        if _sentinel_enabled():
            print("  [哨兵] REQUIRE_SKILL_SENTINEL 默认开：未 load-skill 时 *-build 将被机械拦截（必须执行；显式 false 可关）")
        else:
            print("  [哨兵] REQUIRE_SKILL_SENTINEL 已显式关闭：不机械强制。")

