# -*- coding: utf-8 -*-
"""原型生成器统一命令面板。
纯 argparse 包装现有模块，零新依赖。"""
import os
import sys
import re
import json
import argparse

import yaml

from _cli_infra import SCRIPT_DIR, _open_file
from _cli_guards import _run_pre_check
from _cli_audit import cmd_audit, cmd_cite_audit, cmd_key_doctor, cmd_theme_verify
from _cli_generate import (
    cmd_html_build, cmd_ppt_build, cmd_ppt_page, cmd_docx_build,
    cmd_quote_build, cmd_spec_gen, cmd_outline_to_spec,
    cmd_review, cmd_html_to_ppt, cmd_pptd_build,
    cmd_pptd_gen, cmd_deliver,
)
from _session import (
    show_all_clients, list_clients, get_context_path, load_context,
    save_session, parse_args as parse_session_args, read_chunk,
    onboard_client, rebuild_bm25_index_all, consolidate, auto_for_input,
    recall, build_client_graph, query_graph, add_graph_node, add_graph_edge,
)
from _classify import classify, classify_and_extract
from _archive_auto import (
    record_session_start, auto_archive, archive_note, list_pending,
)
from _verify_hook import run_single
from _pipeline import read_full
from _indexer import update_index
from _aliases import (
    load_global, load_client, diff_clients, export_to_excel, import_from_excel,
)
from _style_guard import print_report
from _cloud_llm import vision_chat
from _quote_spec_gen import gen_quote_spec
from _quote_engine import ExcelRenderer
from _quote_data import Library
from _theme_guard import save_decision, pre_check
from _insight import run_insight
from _feedback import record_diff
from _embed_index import build_embedding_index, get_stats, inspect_chunks
from _bid_parse import parse_tender, save_bid_criteria
from _spec_diff import cmd_spec_diff


def cmd_status(args):
    json_output = getattr(args, 'json', False)
    show_all_clients(json_output=json_output)


def cmd_pending(args):
    """扫描所有客户 context.md，列出未完成待办。"""
    clients = list_clients()
    if not clients:
        print("暂无客户项目")
        return

    print("未完成待办：")
    found = 0
    for c in clients:
        ctx_path = get_context_path(c)
        if not os.path.exists(ctx_path):
            continue
        with open(ctx_path, "r", encoding="utf-8") as f:
            content = f.read()

        sessions = re.findall(r'## \[(\d{4}-\d{2}-\d{2})\][^\n]*\n(.*?)(?=## \[|\Z)', content, re.DOTALL)
        if not sessions:
            continue
        last_date, last_body = sessions[-1]

        pending_match = re.search(r'### 待办[^\n]*\n(.*?)(?=\n###|\Z)', last_body, re.DOTALL)
        if pending_match:
            pending_text = pending_match.group(1).strip()
            if pending_text and pending_text != "(未记录)":
                for line in pending_text.split('\n'):
                    line = line.strip().lstrip('-').strip()
                    if line:
                        print(f"  [{c}] {last_date}  {line}")
                        found += 1

    if not found:
        print("  （无未完成待办）")


def cmd_load(args):
    load_context(args.client)


def cmd_save(args):
    kwargs = parse_session_args(args.extra)
    if not any(kwargs.values()):
        save_session(args.client)
    else:
        save_session(args.client, **kwargs)
    # 归档目标客户：与 save_session 内部保持一致（别名/近似解析到正式客户名）
    try:
        from _aliases import resolve_client_name
        resolved, _, matched_by = resolve_client_name(args.client)
        if matched_by == 'alias':
            args.client = resolved
    except Exception:
        pass
    # 会话后自动归档（归属在会话内产生，save 时消费；失败不影响保存主流程）
    try:
        result = auto_archive(args.client)
        if result["archived"]:
            print(f"[归档] 自动归档 {len(result['archived'])} 个文件 -> {args.client}/refs/：")
            for fn in result["archived"]:
                print(f"        {fn}")
        if result["pending_review"]:
            print(f"[归档] 以下 {len(result['pending_review'])} 个未归档（会话窗口外或失败），待确认：")
            for fn in result["pending_review"]:
                print(f"        {fn}")
        if result["ignored"]:
            print(f"[归档] 跳过残留类型 {len(result['ignored'])} 个：{', '.join(result['ignored'])}")
        if result["reason"] and not result["archived"]:
            print(f"[归档] {result['reason']}")
    except Exception as e:
        print(f"[归档] 自动归档跳过: {e}")


def cmd_classify(args):
    client = getattr(args, 'client', None)
    if getattr(args, 'extract', False):
        result = classify_and_extract(client=client)
        print(f"分类 {result['classified_count']} 个，提取 {result['extracted_count']} 个")
        for w in result.get("warnings", []):
            print(f"[warn] {w}")
    else:
        classify(client=client)


def cmd_archive_note(args):
    """会话内显式登记文件归属（save 自动归档时消费）。"""
    if getattr(args, 'list', False):
        pending = list_pending()
        if not pending:
            print("（无待归档登记）")
            return
        for client_name, files in pending.items():
            print(f"[{client_name}]")
            for fn, ts in files.items():
                print(f"  {fn}  ({ts})")
        return
    client = args.client
    files = args.files
    if not client:
        print("用法: python _cli.py archive-note <客户> <文件...> 或 --list")
        return
    if not files:
        print("用法: python _cli.py archive-note <客户> <文件...> 或 --list")
        return
    result = archive_note(client, files)
    print(f"已登记 {len(result['added'])} 个文件归属 {client}：")
    for fn in result["added"]:
        print(f"  {fn}")
    if result["ignored"]:
        print(f"忽略无效条目: {result['ignored']}")


def cmd_inbox_scan(args):
    """定期 inbox 扫描（Hook + 手动均可调用）。"""
    from _inbox_scan import main_entry
    project_dir = getattr(args, "project_dir", None)
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)
    quiet = getattr(args, "quiet", False)
    emit_json = getattr(args, "emit_json", False)

    report = main_entry(project_dir=project_dir, dry_run=dry_run, force=force)

    if emit_json:
        # Hook 调用：输出 JSON 便于解析
        import json as _json
        print(_json.dumps(report.to_dict(), ensure_ascii=False))
        return

    if quiet:
        # Hook 调用：只输出关键摘要，不啰嗦
        n_archived = len(report.archived)
        n_review = len(report.pending_review)
        if n_archived or n_review:
            print(f"[inbox-scan] 自动归档 {n_archived} 个，待 review {n_review} 个")
        return

    # 手动调用：完整输出
    print(f"[inbox-scan] @ {report.timestamp}")
    print(f"  自动归档: {len(report.archived)}")
    for fc in report.archived:
        print(f"    - {fc.filename} ({fc.category}) → {fc.reason}")
    print(f"  待 review: {len(report.pending_review)}")
    for fc in report.pending_review:
        print(f"    - {fc.filename} ({fc.category}) - {fc.reason}")
    if report.errors:
        print(f"  错误: {len(report.errors)}")
        for e in report.errors:
            print(f"    - {e}")


def cmd_verify(args):
    ok = run_single(args.file)
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
    else:
        print(f"[spec-edit] {op} 失败:")
        for e in result["errors"]:
            print(f"  - {e}")
        sys.exit(2)


def cmd_me(args):
    profile_path = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")
    if not os.path.exists(profile_path):
        print(f"profile.md 不存在: {profile_path}")
        sys.exit(1)
    if args.edit:
        _open_file(profile_path)
    else:
        with open(profile_path, "r", encoding="utf-8") as f:
            print(f.read())


def cmd_read(args):
    summary, cache = read_full(args.file)
    print("=== 注意力摘要 ===")
    print(summary)
    print(f"\n=== 缓存路径 ===\n{cache}")
    print(f"\n=== 提示 ===\nAI 可 Read 此缓存读全文：{cache}")


def cmd_chunk_read(args):
    """按 path#anchor 读完整 chunk 全文。"""
    fpath = str(args.path).split("#")[0]
    if not os.path.exists(fpath):
        print(f"错误: 文件不存在: {fpath}")
        sys.exit(1)
    text = read_chunk(args.path)
    print(text)


def cmd_new(args):
    """一键接单：建目录->分类->全文解析->打印素材->提示 AI 起草。"""
    result = onboard_client(
        args.client,
        scene=getattr(args, 'scene', None) or "整体信息化规划",
        html=getattr(args, 'html', False),
        quote=getattr(args, 'quote', False),
    )
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"[warn] {w}")


def cmd_index(args):
    update_index()


def cmd_index_rebuild(args):
    """重建 BM25 索引（扫描所有客户文件，含别名展开）"""
    result = rebuild_bm25_index_all()
    print(f"已索引 {result['indexed_count']} 个文档块")
    for w in result.get("warnings", []):
        print(f"[warn] {w}")


def cmd_skills_sync(args):
    """技能目录（发布版 skills/ 或 .trae/skills）-> .agents/skills/ 单向镜像。"""
    from _paths import SKILLS_DIR
    from _skills_sync import sync_skills
    src = SKILLS_DIR
    dst = os.path.join(SCRIPT_DIR, ".agents", "skills")
    if not os.path.isdir(src):
        print(f"错误: 技能源目录不存在: {src}")
        sys.exit(1)
    report = sync_skills(src, dst, prune=args.prune)
    print(f"技能同步完成（{src} -> {dst}）：")
    print(f"  新增 {len(report['added'])} · 更新 {len(report['updated'])} · 未变 {len(report['unchanged'])} · 剪枝 {len(report['pruned'])}")
    for label in ("added", "updated", "pruned"):
        for name in report[label]:
            print(f"  [{label}] {name}")


def cmd_load_skill(args):
    """load-skill：打印 SKILL.md 全文 + 写已读哨兵。

    配合 REQUIRE_SKILL_SENTINEL=true 使用（哨兵门禁）：*-build 前必须
    先 load-skill 读必读 skill，否则生成被机械拦截。默认关，不影响正常流程。
    """
    from _cli_guards import mark_skill_read
    skill = args.skill
    if skill == "list":
        # 列出可读技能（含必读标记）
        from _paths import SKILLS_DIR
        names = sorted(n for n in os.listdir(SKILLS_DIR)
                       if os.path.isdir(os.path.join(SKILLS_DIR, n))
                       and os.path.exists(os.path.join(SKILLS_DIR, n, "SKILL.md")))
        print("可用技能：")
        for n in names:
            print(f"  python _cli.py load-skill {n}")
        return

    # 防路径遍历：只允许技能目录名
    if not skill or skill in (".", "..") or os.sep in skill or "/" in skill or "\\" in skill:
        print(f"错误: 非法技能名: {skill!r}")
        print("  用法: python _cli.py load-skill <技能名> | list")
        sys.exit(1)

    from _paths import SKILLS_DIR
    skill_path = os.path.join(SKILLS_DIR, skill, "SKILL.md")
    if not os.path.isfile(skill_path):
        print(f"错误: 未找到技能 {skill}（{SKILLS_DIR}/{skill}/SKILL.md 不存在）")
        print("  用法: python _cli.py load-skill <技能名> | list")
        sys.exit(1)

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"===== SKILL: {skill} =====")
    print(content)
    print(f"===== END SKILL: {skill} =====")

    sentinel = mark_skill_read(skill)
    print(f"\n[load-skill] 已记录 {skill} 已读 → {sentinel}")


def cmd_outline_list(args):
    """列出所有场景大纲（按场景，不按行业）。"""
    outlines_dir = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "outlines")
    if not os.path.isdir(outlines_dir):
        print("暂无场景大纲（_knowledge/templates/outlines/ 不存在）")
        return
    scenes = [d for d in os.listdir(outlines_dir)
              if os.path.isdir(os.path.join(outlines_dir, d)) and not d.startswith(".")]
    if not scenes:
        print("暂无场景大纲")
        return
    print(f"{'场景':<20} {'页数范围':<20} {'说明'}")
    print("-" * 80)
    for s in scenes:
        outline_path = os.path.join(outlines_dir, s, "outline.yml")
        if not os.path.exists(outline_path):
            continue
        with open(outline_path, "r", encoding="utf-8") as f:
            outline = yaml.safe_load(f)
        print(f"{s:<20} {outline.get('page_range', '?'):<20} {outline.get('scene_desc', '')}")
    print("\n用法: python _cli.py outline-apply <场景名>  查看大纲骨架")
    print("      python _cli.py outline-to-spec <场景名> --client <客户> --materials <材料>  生成 spec 草稿")


def cmd_outline_apply(args):
    """查看场景大纲骨架（思维导图式展示）。"""
    outlines_dir = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "outlines")
    outline_path = os.path.join(outlines_dir, args.name, "outline.yml")
    ref_path = os.path.join(outlines_dir, args.name, "reference.md")
    if not os.path.exists(outline_path):
        print(f"错误: 场景大纲不存在: {args.name}")
        print(f"可用场景: {[d for d in os.listdir(outlines_dir) if os.path.isdir(os.path.join(outlines_dir, d))]}")
        sys.exit(1)
    with open(outline_path, "r", encoding="utf-8") as f:
        outline = yaml.safe_load(f)
    print(f"=== 场景大纲: {outline.get('scene', args.name)} ===")
    print(f"说明: {outline.get('scene_desc', '?')}")
    print(f"页数: {outline.get('page_range', '?')}")
    sources = outline.get('source_projects', [])
    if sources:
        print(f"来源项目: {', '.join(sources)}")
    print()

    print("思维导图结构:")
    for i, sec in enumerate(outline.get("structure", []), 1):
        weight = sec.get('weight', 1)
        weight_bar = "█" * weight
        print(f"\n{i}. {sec['section']}  [{weight_bar}]  (role: {sec.get('role', '?')})")
        children = sec.get('children', [])
        if children:
            for child in children:
                print(f"   ├─ {child}")
        prompt = sec.get('prompt', '').strip()
        if prompt:
            # prompt 缩进显示，每行加前缀
            for line in prompt.split('\n'):
                if line.strip():
                    print(f"   └─ 💡 {line.strip()}")
                    break  # 只显示第一行，避免太长

    if os.path.exists(ref_path):
        print(f"\n{'='*60}")
        print("行业实例参考（reference.md）:")
        print('='*60)
        with open(ref_path, "r", encoding="utf-8") as f:
            print(f.read())

    print(f"\n{'='*60}")
    print("下一步:")
    print(f"  1. python _cli.py outline-to-spec {args.name} --client <客户> --materials <材料文件>")
    print("     -> 生成 spec.yml 草稿")
    print("  2. 人工确认 spec（写 confirmed: true）")
    print("  3. python _cli.py html-build <spec.yml> output/<客户>/方案_v1.html --client <客户>")
    print("     -> HTML + pptd 双输出，再 pptd-build 出 PPT")


def cmd_aliases(args):
    if args.global_only:
        aliases = load_global()
        print("=== 全局别名 ===")
        for k, v in aliases.items():
            print(f"  {k}: {v}")
        return
    if args.diff:
        if len(args.diff) < 2:
            print("用法: aliases <客户A> <客户B>（对比两客户别名，不需要 diff 字样）")
            sys.exit(1)
        d = diff_clients(args.diff[0], args.diff[1])
        print(f"=== {args.diff[0]} vs {args.diff[1]} ===")
        if d["only_a"]:
            print(f"\n仅 {args.diff[0]} 有:")
            for k, v in d["only_a"].items():
                print(f"  {k}: {v}")
        if d["only_b"]:
            print(f"\n仅 {args.diff[1]} 有:")
            for k, v in d["only_b"].items():
                print(f"  {k}: {v}")
        if d["diff_value"]:
            print("\n同 key 不同值:")
            for k, v in d["diff_value"].items():
                print(f"  {k}:")
                print(f"    {args.diff[0]}: {v['a']}")
                print(f"    {args.diff[1]}: {v['b']}")
        return
    if args.edit:
        if args.global_only:
            path = os.path.join(SCRIPT_DIR, "_knowledge", "me", "aliases-global.yml")
        else:
            if not args.client:
                print("用法: aliases edit --client <客户名>")
                sys.exit(1)
            path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", args.client, "aliases.yml")
        _open_file(path)
        return
    if not args.client:
        print("用法: aliases --client <客户名> | --global | <客户A> <客户B>（对比） | edit --client <客户名>")
        sys.exit(1)
    aliases = load_client(args.client)
    print(f"=== {args.client} 别名（全局+专属合并）===")
    for k, v in aliases.items():
        print(f"  {k}: {v}")


def cmd_aliases_export(args):
    """导出全部别名到 Excel（含表头和现有数据）。"""
    export_to_excel(args.output)


def cmd_aliases_import(args):
    """从 Excel 导入别名（合并模式）。"""
    import_from_excel(args.file)


def cmd_style_check(args):
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}")
        sys.exit(1)
    print_report(args.file)


def cmd_vision_describe(args):
    """vision-describe：把图片转成文字描述，返回给纯文本 agent 用。

    当 AI agent 本身没有视觉能力时，先用 vision 模型把图片读一遍，
    把描述当作 prompt 上文注入。当前 agent 是多模态模型时（AGENT_MODEL_SUPPORTS_VISION=true）会跳过。

    --rounds 2：A/B 隔离双观察 + 分歧仲裁（仅 json 格式；参考 ds-vision-v3 证据契约）。
    """
    image_path = args.image
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
        if len(content) > 200:
            content = content[:200] + "..."
        print(f"   {content}")
        print()


def cmd_quote_spec_gen(args):
    """从客户材料提取报价 spec.yml。"""
    # 生成前强制验证
    client = getattr(args, 'client', None) or None
    _run_pre_check(client_name=client)

    # §八 3.5：输出白名单前置校验，避免材料读取 + LLM 提取完才在写入点抛异常
    # （gen_quote_spec 入口同样有校验兜底）
    from _renderer import _validate_output_path, OutputPathNotAllowedError
    try:
        _validate_output_path(args.output)
    except OutputPathNotAllowedError as e:
        print(f"[阻断] {e}")
        print("  提示：报价 spec 属产出物，输出路径请放在 output/ 下"
              "（如 output/通用/quote_spec.yml）")
        sys.exit(1)

    output_path = gen_quote_spec(args.materials_dir, client_name=args.client, output_path=args.output)

    # 生成后自动验证
    if output_path and os.path.exists(output_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            run_single(output_path)
        except Exception as e:
            print(f"[验证] 跳过: {e}")


def cmd_quote_validate(args):
    """校验报价 Excel 公式"""
    renderer = ExcelRenderer()
    issues = renderer.validate(args.xlsx)
    if issues:
        print("校验问题:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("校验通过")


def cmd_quote_library(args):
    """管理报价内容库：list / search"""
    lib_dir = os.path.join(SCRIPT_DIR, "_knowledge", "quote_library")
    type_file = {
        "modules": "modules.yaml",
        "licenses": "licenses.yaml",
        "services": "services.yaml",
        "thirdparty": "thirdparty.yaml",
    }
    fname = type_file.get(args.type)
    if not fname:
        print(f"未知类型: {args.type}")
        sys.exit(1)
    path = os.path.join(lib_dir, fname)
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    root_key = args.type if args.type != "services" else "roles"
    items = data.get(root_key, []) or []
    if args.action == "search" and args.keyword:
        kw = args.keyword.lower()
        items = [it for it in items if kw in str(it.get("name", "")).lower() or kw in str(it.get("description", "")).lower()]
    print(f"=== {args.type} ({len(items)} 条) ===")
    for it in items:
        print(f"  [{it.get('id')}] {it.get('name', '')}  ¥{it.get('unit_price', it.get('price_register', '-'))}")
        if args.action == "search" and it.get("description"):
            desc = str(it["description"])[:60]
            print(f"      {desc}")


def cmd_quote_search(args):
    """语义搜索全报价内容库"""
    lib = Library()
    results = lib.search(args.keyword, args.top)
    if not results:
        print(f"未找到匹配 '{args.keyword}' 的内容")
        return
    print(f"=== 搜索 '{args.keyword}' ({len(results)} 条) ===")
    for r in results:
        print(f"  [{r['id']}] {r['name']}  ¥{r.get('unit_price', '-')}  [{r.get('group', '')}]")
        if r.get("description"):
            print(f"      {r['description']}")


def cmd_consolidate(args):
    """自动固化：检测客户反复出现的模式，升级到 .trae/rules/。"""
    consolidate(args.client, threshold=args.threshold)


# ============================================================
# theme-guard：合并 theme-list + theme-set（PROJECT_DESIGN.md §13）
# ============================================================
def cmd_theme_guard(args):
    """主题守卫：列出/刷新/记录核心约束。

    无 --set：列出当前生效的 permanent 主题（HEAD 注入用）
    有 --set：记录一条 permanent 主题到 decisions.md
    有 --turn：按间隔检查是否需 re-grounding（步数化保真，借鉴 AAMAS 2026）
    """
    if args.set_theme:
        # 记录新主题（原 theme-set 功能）
        scope = args.scope
        task_id = args.task_id
        if scope == "task" and not task_id:
            print("错误: scope=task 时必须提供 --task-id")
            sys.exit(1)

        reason_parts = [f"scope={scope}", f"priority={args.priority}"]
        if task_id:
            reason_parts.append(f"task_id={task_id}")

        save_decision(
            args.client,
            args.set_theme,
            args.set_theme,
            reason=", ".join(reason_parts),
            alternatives_rejected="",
            level="L4",
            persistence="permanent",
            scope=scope,
            task_id=task_id,
        )
        print(f"已记录主题: {args.client} / {args.set_theme} (persistence=permanent, scope={scope})")
        if scope == "client":
            print("  铁律：跨任务跨会话始终生效")
        else:
            print(f"  本次任务全程不变（task_id={task_id}）")
        return

    # 列出当前生效主题（原 theme-list 功能）
    result = pre_check(args.client, args.task_id)
    themes = result.get("themes", [])

    # Re-grounding 步数化检查（P0-2，借鉴 AAMAS 2026 O(√T) 漂移研究）
    # 每 REGROUND_INTERVAL 轮触发一次保真刷新提示
    REGROUND_INTERVAL = 10
    need_reground = False
    if args.turn > 0 and args.turn % REGROUND_INTERVAL == 0:
        need_reground = True
        print(f"=== Re-grounding 保真刷新（第 {args.turn} 轮）===")
        print("语义漂移随轮次增长（AAMAS 2026: O(√T)），周期性 re-grounding 保真\n")

    print("=== 核心约束刷新 ===")
    print(f"客户: {args.client} | task_id={args.task_id or '未指定'}")
    print(f"共 {len(themes)} 条主题，其中 {result.get('critical_count', 0)} 条硬约束\n")
    for t in themes:
        persistence = t.get("persistence", "task")
        scope = t.get("scope", "client")
        tag = f"[{persistence.upper()}-{scope.upper()}]"
        if t.get("task_id"):
            tag += f" task={t['task_id']}"
        pri_tag = "🔴" if t.get("priority") == "critical" else "🟡"
        print(f"{pri_tag} {tag} {t['theme']}")
        if t.get("description"):
            print(f"   {t['description'][:120]}")
        print(f"   来源: decisions.md {t.get('source_date', '?')}")
        print()
    # HEAD context 输出
    head = result.get("head_context", "")
    if head:
        print("--- HEAD 注入 ---")
        print(head)
    # TAIL 清单输出（re-grounding 时强调）
    tail = result.get("tail_checklist", "")
    if tail:
        if need_reground:
            print("\n--- TAIL 自检（re-grounding 时逐项确认）---")
        print(tail)
    for w in result.get("warnings", []):
        print(f"[warn] {w}")


def cmd_compact(args):
    """压缩客户历史：合并 context.md + 清理旧 task_history 条目。

    --keep N: 保留最近 N 条 task_history 记录（默认 10）
    --keep-sessions N: context.md 保留最近 N 次完整会话（默认 1，传 0 跳过 context.md 压缩）
    """
    client = args.client
    keep = args.keep
    keep_sessions = getattr(args, 'keep_sessions', 1)

    from _paths import CLIENTS_DIR, LOGS_DIR
    clients_dir = CLIENTS_DIR
    client_path = os.path.join(clients_dir, client)
    if not os.path.exists(client_path):
        print(f"客户 '{client}' 不存在")
        sys.exit(1)

    # 1. 压缩 task_history.json（保留最近 N 条）
    history_path = os.path.join(LOGS_DIR, "task_history.json")
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        # 兼容旧版 dict 格式 {"tasks": [...]}（与 _verify_hook.update_task_history 同一兼容层）
        if isinstance(history, dict):
            history = history.get("tasks", [])
        # task_history.json 是列表结构，每条记录的 project 字段格式为 "client:客户名" 或直接客户名
        client_records = [r for r in history if r.get("project", "").replace("client:", "") == client or r.get("client") == client]
        other_records = [r for r in history if r.get("project", "").replace("client:", "") != client and r.get("client") != client]
        if len(client_records) > keep:
            kept = client_records[-keep:]
            removed = len(client_records) - keep
            history[:] = other_records + kept
            import shutil
            shutil.copy2(history_path, history_path + ".bak")  # 截断前留底
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f"已压缩 {client} 的 task_history: 删除 {removed} 条旧记录，保留 {len(kept)} 条")
        else:
            print(f"{client} 的 task_history 仅 {len(client_records)} 条，无需压缩")

    # 2. 压缩 context.md（调用 _context.compact，修复既有 bug：原代码只打印警告不调用）
    if keep_sessions > 0:
        from _context import compact as _compact_context
        print(f"\n[context] 压缩 {client} 的 context.md（保留最近 {keep_sessions} 次会话）...")
        _compact_context(client, keep_last=keep_sessions)
    else:
        print("\n[context] --keep-sessions=0，跳过 context.md 压缩")

    print(f"\n压缩完成: {client}")


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

    # 检测 handoff_packet.md（上下文重置）
    if client and not json_output:
        try:
            from _session import check_handoff_packet
            handoff_content, found = check_handoff_packet(client)
            if found and handoff_content:
                print("=== 会话交接包已检测（上下文重置模式）===")
                print(handoff_content)
                print("=== 交接包已注入，文件已删除（一次性使用）===\n")
        except Exception as e:
            print(f"  [warn] handoff_packet 检测失败: {e}")

    r = auto_for_input(args.input, client_name=client)

    if json_output:
        # P1-4: 结构化 JSON 输出，供程序化消费（省去 stdout 解析）
        import json as _json
        output = {
            "level": r.get("level", "?"),
            "mode": r.get("mode", "?"),
            "client": client,
            "context_summary": r.get("context_summary", ""),
            "recall": r.get("recall", []),
            "warnings": r.get("warnings", []),
            "vision_supported": os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"),
        }
        print(_json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("=== 会话上下文 ===")
    print(f"  层级: {r.get('level', '?')} | 模式: {r.get('mode', '?')}")
    print(f"  摘要: {r.get('context_summary', '无')[:300]}")
    recall_results = r.get("recall", [])
    if recall_results:
        print(f"\n  召回 {len(recall_results)} 条:")
        for i, item in enumerate(recall_results[:5]):
            print(f"    [{i}] {item.get('client', '?')} ({item.get('score', 0):.3f}) {item.get('path', '?')[-60:]}")
            snippet = item.get("snippet", "")
            if snippet:
                print(f"        片段: {snippet[:120]}")
            for exp_line in item.get("graph_expansions", []):
                print(f"        {exp_line}")
    for w in r.get("warnings", []):
        print(f"  [warn] {w}")
    # vision 路由握手：告知 AI 本会话图片处理方式（自我评估优先，env flag 兜底）
    if os.environ.get("AGENT_MODEL_SUPPORTS_VISION", "").lower() in ("1", "true", "yes"):
        print("  [vision] AGENT_MODEL_SUPPORTS_VISION=true：图片请直接读取（agent 多模态），vision-describe 将跳过")
    else:
        print("  [vision] 图片路由：能直接读图（多模态）就直接读；不能则用 python _cli.py vision-describe <图片> 预转文本")

    # skill 注入（档位1，按层级条件注入）：L3/L4 生成/规划类任务提醒先读必读 skill
    # 解决"AI 生成 HTML/PPT 前没读 skill"——把 skill 清单喂到嘴边；
    # 机械兜底由 REQUIRE_SKILL_SENTINEL=true 哨兵门禁承担（档位2）
    level = r.get("level", "?")
    if level in ("L3", "L4"):
        print("\n=== 生成前置 skill 提示（都读，AI 自判层级）===")
        print("本任务为 L3/L4。必读 skill 如下，读完后自行判断走多完整：")
        print("  python _cli.py load-skill delivery-pipeline   # 交付顺序：HTML 先行->确认->PPT")
        print("  python _cli.py load-skill presentation-content-design   # 内容设计（每页怎么讲）")
        print("  python _cli.py load-skill spec-writing-guide           # spec 字段/容量/confirmed 门禁")
        print("  python _cli.py load-skill de-ai-style                  # 客户可见文案去 AI 化")
        print("  简便工作（编辑已有产出/纯检索/单页微调/工程代码/内部分析）可跳过。")
        sentinel_on = os.environ.get("REQUIRE_SKILL_SENTINEL", "").strip().lower() in ("1", "true", "yes")
        if sentinel_on:
            print("  [哨兵] REQUIRE_SKILL_SENTINEL=true：未 load-skill 时 *-build 将被机械拦截（必须执行）")
        else:
            print("  [哨兵] REQUIRE_SKILL_SENTINEL 未开：不机械强制。")


def cmd_insight(args):
    """生成洞察报告。"""
    context = args.context or ""
    if args.context_file:
        try:
            with open(args.context_file, "r", encoding="utf-8") as f:
                context = f.read()
        except Exception as e:
            print(f"读取上下文文件失败: {e}")
            sys.exit(1)
    insight_text, filepath, reason = run_insight(
        args.client, context, turn_count=args.turn,
        user_input=args.input or "", force=args.force
    )
    if insight_text:
        print(f"[洞察] 触发原因: {reason}")
        print(f"[洞察] 存档: {filepath}")
        print(f"\n{insight_text[:2000]}")
    else:
        print(f"[洞察] 未触发: {reason}")


def cmd_diff_record(args):
    """记录 AI 原版 vs 人工修改的差异（反模式回流）。"""
    diff_text, changes = record_diff(
        args.client, args.ai_version, args.human_version, note=args.note or ""
    )
    if diff_text:
        print(f"[diff] 记录 {len(changes)} 处修改")
        print(diff_text[:2000])
    else:
        print("[diff] 无差异或文件不存在")


def cmd_graph_build(args):
    """构建/更新 client_graph.json + client_index.md。"""
    graph = build_client_graph(args.client)
    print(f"[graph-build] {args.client}: {len(graph['nodes'])} 节点, {len(graph['edges'])} 边")
    if graph.get("index_summary"):
        print(f"  摘要: {graph['index_summary']}")


def cmd_graph_query(args):
    """查询客户图节点和边。"""
    result = query_graph(args.client, node_id=args.node,
                         node_type=args.type, edges_of=args.edges)
    if getattr(args, 'json', False):
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result.get("error"):
        print(f"[graph-query] 错误: {result['error']}")
        sys.exit(1)
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    print(f"[graph-query] {args.client}: {len(nodes)} 节点, {len(edges)} 边")
    for n in nodes[:20]:
        print(f"  {n['id']} [{n['type']}] {n['title'][:50]}")
    if len(nodes) > 20:
        print(f"  ...还有 {len(nodes)-20} 个")
    for e in edges[:10]:
        print(f"  {e['from']} --{e['type']}--> {e['to']}")


def cmd_graph_add(args):
    """手动添加图节点。"""
    result = add_graph_node(args.client, node_type=args.type,
                            title=args.title, summary=args.summary,
                            method=args.method)
    node = result["node"]
    print(f"[graph-add] 添加节点: {node['id']} [{node['type']}] {node['title']}")


def cmd_graph_link(args):
    """手动添加图边。"""
    result = add_graph_edge(args.client, from_id=args.from_id,
                           to_id=args.to_id, edge_type=args.type,
                           note=args.note)
    if result.get("error"):
        print(f"[graph-link] 错误: {result['error']}")
        sys.exit(1)
    edge = result["edge"]
    print(f"[graph-link] 添加边: {edge['from']} --{edge['type']}--> {edge['to']}")


def cmd_semantic_catalog(args):
    """校验能力目录 JSON。"""
    from _semantic_catalog import check_catalog, DEFAULT_CATALOG_PATH
    path = getattr(args, "path", None) or DEFAULT_CATALOG_PATH
    result = check_catalog(path)
    print(f"[semantic-catalog] {path}")
    if result["valid"]:
        print("  valid: True, 0 错误")
    else:
        print(f"  valid: False, {len(result['errors'])} 错误")
        for e in result["errors"]:
            print(f"  - {e}")
        sys.exit(1)


def cmd_embed_rebuild(args):
    """构建 Embedding 索引（扫描所有客户文件 -> 批量 embedding -> 存 pkl）。"""
    from _cloud_llm import current_embed_provider
    provider = current_embed_provider()
    if not provider:
        print("[embed] 未配置 embedding key（ZHIPU_API_KEY 或 SILICONFLOW_API_KEY），embedding 不可用")
        print("  提示：在 .env 中填入任一个 key；排查来源用 python _cli.py key-doctor")
        sys.exit(1)
    print(f"[embed] provider: {provider[0]} ({provider[1]})")
    build_embedding_index(batch_size=args.batch_size, force=args.force)


def cmd_embed_stats(args):
    """查看 Embedding 索引统计。"""
    stats = get_stats()
    if stats.get("error"):
        print(f"[embed-stats] 索引读取失败: {stats['error']}")
        print("  提示：可运行 python _cli.py embed-rebuild --force 重建索引")
        sys.exit(1)
    if not stats.get("exists"):
        print("Embedding 索引不存在。运行 `python _cli.py embed-rebuild` 构建。")
        return
    print("=== Embedding 索引统计 ===")
    print(f"  向量数: {stats['count']}")
    print(f"  维度: {stats['dim']}")
    print(f"  模型: {stats.get('model', '?')}")
    print("  路径: _knowledge/.cache/embeddings_matrix.npy")
    from _cloud_llm import current_embed_provider
    cur = current_embed_provider()
    if cur:
        match = "匹配" if cur[1] == stats.get("model") else "不匹配（需 embed-rebuild --force 重建）"
        print(f"  当前 provider: {cur[0]} ({cur[1]}) — 与索引{match}")
    else:
        print("  当前 provider: 无可用 embedding key")


def cmd_chunk_inspect(args):
    """检查某文件的分块结果。"""
    chunks = inspect_chunks(args.path)
    if not chunks:
        print(f"未找到匹配 '{args.path}' 的分块")
        sys.exit(1)
    print(f"=== 分块结果（{len(chunks)} 个 chunk）===")
    for i, c in enumerate(chunks):
        anchor = c["path"].split("#", 1)[1] if "#" in c["path"] else "(无锚点)"
        print(f"\n[{i}] {anchor}  ({c['chars']} 字)")
        print(f"  {c['preview']}")


def cmd_recall(args):
    # --no-client-filter 显式禁用；--client-filter 显式启用；默认 None（由 recall 自动决策）
    if getattr(args, 'no_client_filter', False):
        client_filter = False
    elif getattr(args, 'client_filter', None):
        client_filter = True
    else:
        client_filter = None
    json_output = getattr(args, 'json', False)
    results = recall(" ".join(args.keywords),
                     force_keyword=args.keyword,
                     client_name=args.client,
                     rerank=args.rerank,
                     use_embedding=not args.no_embedding,
                     client_filter=client_filter,
                     return_results=json_output)
    if json_output and results is not None:
        import json as _json
        print(_json.dumps(results, ensure_ascii=False, indent=2))


def cmd_recall_eval(args):
    """召回质量评估：跑 golden query 评估集，输出三链路 Hit@1/Hit@3/MRR 指标。

    L5 级确定性评估器，只读 recall() 结果做判定，不改算法。
    实施依据：docs/dev_plan_recall_eval_2026-07-19.md
    """
    from _recall_eval import (
        load_eval_set, run_eval, save_baseline, compare_baseline,
        estimate_api_calls, DEFAULT_EVAL_SET_PATH, DEFAULT_BASELINE_PATH,
    )

    eval_path = args.file or DEFAULT_EVAL_SET_PATH
    try:
        eval_set = load_eval_set(eval_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"[recall-eval] 评估集加载失败: {e}")
        sys.exit(1)
    if not eval_set:
        print(f"[recall-eval] 评估集为空: {eval_path}")
        sys.exit(1)

    # 三链路：默认 rrf 必跑；--rerank / --no-embedding 各加一条
    chains_to_run = [("rrf", False, True)]  # (chain_name, rerank, use_embedding)
    if args.rerank:
        chains_to_run.append(("rerank", True, True))
    if args.no_embedding:
        chains_to_run.append(("bm25_only", False, False))

    # 成本守门：预估云端调用数 >50 且无 --yes -> exit 1
    total_calls = sum(
        estimate_api_calls(len(eval_set), rerank=r, use_embedding=ue)
        for _, r, ue in chains_to_run
    )
    if total_calls > 50 and not args.yes:
        print(
            f"[recall-eval] 预估 {total_calls} 次云端调用（embedding+rerank），"
            f">50 次需 --yes 确认"
        )
        sys.exit(1)

    if args.limit:
        eval_set = eval_set[: args.limit]

    reports = {}
    for chain_name, rerank, use_embedding in chains_to_run:
        print(f"\n=== 链路: {chain_name} ===")
        rep = run_eval(
            eval_set, rerank=rerank, use_embedding=use_embedding
        )
        reports[chain_name] = rep
        _print_chain_report(rep)

    # --save-baseline 落盘
    if args.save_baseline:
        config_snapshot = (
            reports["rrf"]["config"]
            if "rrf" in reports
            else next(iter(reports.values()))["config"]
        )
        chains_summary = {name: rep["metrics"] for name, rep in reports.items()}
        save_baseline(
            {"config": config_snapshot, "chains": chains_summary},
            path=DEFAULT_BASELINE_PATH,
        )
        print(f"\n[recall-eval] baseline 已落盘: {DEFAULT_BASELINE_PATH}")

    # --gate 回归门禁
    if args.gate:
        try:
            with open(args.gate, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[recall-eval] baseline 读取失败: {e}")
            sys.exit(1)
        # config 一致性告警（不阻断）
        current_config = next(iter(reports.values()))["config"]
        if baseline.get("config") and baseline["config"] != current_config:
            print(
                "[recall-eval] ⚠️ 警告: 当前 recall_config.yml 与 baseline 不一致，"
                "指标差异可能来自调参而非回归"
            )
        current_chains = {name: rep["metrics"] for name, rep in reports.items()}
        passed, diffs = compare_baseline(current_chains, baseline)
        print("\n=== Gate 对比 ===")
        for d in diffs:
            mark = "PASS" if d["passed"] else "FAIL"
            print(
                f"  [{mark}] {d['chain']}.{d['metric']}: "
                f"baseline={d['baseline']} current={d['current']} "
                f"delta={d['delta']:+} tol={d['tolerance']}"
            )
        if not passed:
            print("\n[recall-eval] 回归门禁 FAIL")
            sys.exit(1)
        print("\n[recall-eval] 回归门禁 PASS")

    # --json 结构化报告落盘
    if args.json:
        report_json = {"chains": reports}
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report_json, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n[recall-eval] 结构化报告: {args.json}")


def _print_chain_report(report):
    """打印单链路评估报告。"""
    m = report["metrics"]
    print(f"  正样本: {m['total']} 条 / 负样本: {m['neg_total']} 条")
    print(f"  Hit@1: {m['hit_at_1']:.4f}")
    print(f"  Hit@3: {m['hit_at_3']:.4f}  (核心指标)")
    print(f"  MRR:   {m['mrr']:.4f}")
    print(
        f"  负样本: no_hit 通过 {m['neg_pass_no_hit']} 条, "
        f"fallback 通过 {m['neg_pass_fallback']} 条, "
        f"不通过 {m['neg_fail']} 条"
    )
    if m["misses"]:
        print(f"  Miss ({len(m['misses'])} 条):")
        for miss in m["misses"]:
            err = f" [error: {miss.get('error')}]" if miss.get("error") else ""
            top3 = miss.get("top3_paths", [])
            print(f"    {miss['id']}: {miss['query'][:40]} -> top3: {top3}{err}")


def cmd_bid_parse(args):
    """解析招标文件，提取评分标准/格式要求/资质条款。"""
    client = getattr(args, 'client', None) or ""
    do_split = not getattr(args, 'no_split', False)
    criteria = parse_tender(args.file, client_name=client, do_split=do_split)
    save_bid_criteria(criteria, client_name=client)


class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """默认值自动显示 + epilog 保留原始换行。"""


def build_parser():
    parser = argparse.ArgumentParser(
        description="原型生成器统一命令面板",
        formatter_class=_HelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_status = sub.add_parser("status", help="所有客户状态一览")
    p_status.add_argument("--json", action="store_true", help="输出结构化 JSON")
    sub.add_parser("pending", help="扫描所有客户未完成待办")
    p_recall = sub.add_parser("recall", help="召回相关历史项目")
    p_recall.add_argument("keywords", nargs="+", help="关键词")
    p_recall.add_argument("--keyword", action="store_true", help="强制关键词模式")
    p_recall.add_argument("--client", help="客户名（用于别名展开）")
    p_recall.add_argument("--rerank", action="store_true", help="云端 LLM rerank 精排")
    p_recall.add_argument("--no-embedding", action="store_true", help="禁用 Embedding 语义召回")
    p_recall.add_argument("--client-filter", action="store_true", default=None,
                          help="强制按客户过滤（默认指定 --client 时自动开启）")
    p_recall.add_argument("--no-client-filter", action="store_true",
                          help="禁用按客户过滤（跨客户搜索时使用）")
    p_recall.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费）")
    p_eval = sub.add_parser("recall-eval",
                            help="召回质量评估（golden query 评估集 + 三链路 Hit@1/Hit@3/MRR）")
    p_eval.add_argument("--file", help="评估集 yml 路径（默认 _knowledge/eval/golden_queries.yml）")
    p_eval.add_argument("--rerank", action="store_true",
                        help="加跑 BGE-Reranker 精排链路")
    p_eval.add_argument("--no-embedding", action="store_true",
                        help="加跑 BM25 单路链路（用于定位哪一路拖后腿）")
    p_eval.add_argument("--limit", type=int, default=None,
                        help="只跑前 N 条（调试用）")
    p_eval.add_argument("--save-baseline", action="store_true",
                        help="本次指标写为 _knowledge/eval/baseline.json")
    p_eval.add_argument("--gate", metavar="BASELINE.json",
                        help="对比指定 baseline.json，回归超容差 exit 1")
    p_eval.add_argument("--json", help="结构化报告落盘路径")
    p_eval.add_argument("--yes", action="store_true",
                        help="确认成本守门（>50 次云端调用时需此）")
    p_load = sub.add_parser("load", help="加载客户上下文")
    p_load.add_argument("client", help="客户名")
    p_save = sub.add_parser("save", help="保存会话",
                            epilog='示例: python _cli.py save 蓝海集团 --input="完成架构图" --decisions="两步走" --outputs="output/蓝海集团/x.html" --pending="等客户确认"')
    p_save.add_argument("client", help="客户名")
    p_save.add_argument("extra", nargs="*", help="会话内容键（原样传入）: --input= --decisions= --outputs= --pending=")
    p_classify = sub.add_parser("classify", help="分类 inbox/")
    p_classify.add_argument("--extract", action="store_true", help="分类后自动提取内容摘要到 context.md")
    p_classify.add_argument("--client", help="显式指定客户（跳过规则猜客户，直接归档到该客户 refs）")
    p_archive_note = sub.add_parser("archive-note", help="会话内登记文件归属（save 自动归档时消费）")
    p_archive_note.add_argument("client", nargs="?", help="客户名")
    p_archive_note.add_argument("files", nargs="*", help="文件（可带路径，只取文件名）")
    p_archive_note.add_argument("--list", action="store_true", help="查看全部待归档登记")
    p_inbox_scan = sub.add_parser("inbox-scan", help="定期 inbox 扫描（Hook + 手动均可）")
    p_inbox_scan.add_argument("--dry-run", action="store_true", help="只报告，不移动")
    p_inbox_scan.add_argument("--force", action="store_true", help="忽略时间窗/冷却期（排障用）")
    p_inbox_scan.add_argument("--quiet", action="store_true", help="Hook 调用：只输出关键摘要")
    p_inbox_scan.add_argument("--emit-json", action="store_true", help="Hook 调用：输出 JSON 便于解析")
    p_inbox_scan.add_argument("--project-dir", help="项目根目录（默认 cwd）")
    p_verify = sub.add_parser("verify", help="验证生成产出")
    p_verify.add_argument("file", help="文件路径")
    p_me = sub.add_parser("me", help="打印/编辑个人画像")
    p_me.add_argument("--edit", action="store_true", help="用编辑器打开")

    p_read = sub.add_parser("read", help="全文读取（摘要+缓存）")
    p_read.add_argument("file", help="文件路径")
    p_new = sub.add_parser("new", help="一键接单（建目录->分类->解析->outline-to-spec 生成 spec 草稿）")
    p_new.add_argument("client", help="客户名")
    p_new.add_argument("--scene", default="整体信息化规划", help="方案场景（默认整体信息化规划）")
    p_new.add_argument("--html", action="store_true", help="同时生成方案 HTML")
    p_new.add_argument("--quote", action="store_true", help="同时生成 Excel 报价")

    # P1: 索引与方案模板
    sub.add_parser("index", help="为 index.json 补全摘要+标签")
    p_rebuild = sub.add_parser("index-rebuild", help="重建 BM25 索引")
    p_rebuild.add_argument("--force", action="store_true", help="强制重建全部")
    sub.add_parser("outline-list", help="列出所有场景大纲")
    p_outline = sub.add_parser("outline-apply", help="查看场景大纲骨架")
    p_outline.add_argument("name", help="场景名")

    # 场景大纲 -> spec 草稿
    p_ots = sub.add_parser("outline-to-spec", help="场景大纲 + 客户材料 -> spec.yml 草稿")
    p_ots.add_argument("scene", help="场景名（如：整体信息化规划）")
    p_ots.add_argument("materials", nargs="*", help="客户材料文件路径（可多个，不传则自动扫描 --client 的 refs/）")
    p_ots.add_argument("--client", help="客户名")
    p_ots.add_argument("--output", help="输出 spec.yml 路径（须在 output/ 下，如 output/通用/spec_draft.yml）")

    # Embedding 索引
    p_er = sub.add_parser("embed-rebuild", help="构建 Embedding 索引（增量更新）")
    p_er.add_argument("--batch-size", type=int, default=50, help="每批几个文档（默认50）")
    p_er.add_argument("--force", action="store_true", help="强制全量重建")
    sub.add_parser("embed-stats", help="查看 Embedding 索引统计")

    # 技能目录同步（.trae/skills -> .agents/skills 单向镜像）
    p_ssync = sub.add_parser("skills-sync", help="把 .trae/skills/ 单向同步到 .agents/skills/（事实源在前者，后者勿手改）")
    p_ssync.add_argument("--prune", action="store_true", help="删除 .agents/skills/ 中源端不存在的技能")

    # load-skill：读 skill + 写已读哨兵（REQUIRE_SKILL_SENTINEL=true 时的门禁入口）
    p_ls = sub.add_parser("load-skill", help="打印 SKILL.md 全文并记录已读哨兵（生成前必读；配合 REQUIRE_SKILL_SENTINEL=true 机械门禁）")
    p_ls.add_argument("skill", help="技能名（.trae/skills/<名称>/SKILL.md）或 list")

    # 切片审计
    p_ci = sub.add_parser("chunk-inspect", help="检查某文件的分块结果")
    p_ci.add_argument("path", help="文件路径（支持部分匹配）")

    # chunk-read：按 path#anchor 读完整 chunk
    p_cr = sub.add_parser("chunk-read", help="按 path#anchor 读完整 chunk 全文")
    p_cr.add_argument("path", help="文件路径（可带 #anchor 锚点）")

    # P1: 别名
    p_aliases = sub.add_parser("aliases", help="别名管理")
    p_aliases.add_argument("--client", help="客户名")
    p_aliases.add_argument("--global", dest="global_only", action="store_true", help="全局别名")
    p_aliases.add_argument("--edit", action="store_true", help="编辑")
    p_aliases.add_argument("diff", nargs="*", help="diff A B 对比两客户")

    # 别名 Excel 导入/导出
    p_aliases_export = sub.add_parser("aliases-export", help="导出全部别名到 Excel")
    p_aliases_export.add_argument("output", help="输出 Excel 路径（.xlsx）")
    p_aliases_import = sub.add_parser("aliases-import", help="从 Excel 导入别名（合并模式）")
    p_aliases_import.add_argument("file", help="输入 Excel 路径（.xlsx）")

    # P1: 去 AI 化
    p_style = sub.add_parser("style-check", help="检测 AI 套路")
    p_style.add_argument("file", help="待检测文件")

    # P-vision: 图片转描述（给纯文本 agent 用）
    p_vd = sub.add_parser("vision-describe", help="把图片转成文字描述，供纯文本 agent 当上下文使用")
    p_vd.add_argument("image", help="图片路径（png/jpg/gif/bmp/webp/svg/tiff/heic）")
    p_vd.add_argument("--prompt", "-p", default=None, help="问图模型的问题（默认：请描述这张图片的内容，json 模式追加结构化模板）")
    p_vd.add_argument("--provider", default=None, help="vision provider（默认 minimax；可指定其他 OpenAI 兼容视觉端点）")
    p_vd.add_argument("--format", choices=["text", "json"], default="json",
                      help="输出格式：json（默认，含 source_image 字段，适合进 spec 引用）或 text")
    p_vd.add_argument("--rounds", type=int, choices=[1, 2], default=1,
                      help="观察轮数：1=单次（默认）；2=A/B 双观察+分歧仲裁（仅 json 格式，text 自动降级）")
    p_vd.add_argument("--show-rounds", action="store_true",
                      help="rounds=2 时在输出中附 A/B 两轮原文（_rounds 字段，审计用）")

    # 联网搜索（双引擎：Tavily + 字节搜索）
    p_ws = sub.add_parser("web-search", help="联网搜索（双引擎融合：Tavily + 字节搜索）")
    p_ws.add_argument("query", help="搜索关键词")
    p_ws.add_argument("--max-results", "-n", type=int, default=5, help="最多返回条数（默认 5）")
    p_ws.add_argument("--engines", "-e", default=None, help="指定引擎（逗号分隔，如 tavily,byte_search），默认自动检测可用引擎")

    # Spec 自动生成（走 outline-to-spec）
    p_sg = sub.add_parser("spec-gen", help="从客户材料生成 spec 草稿（走场景大纲 + LLM 防幻觉提取）")
    p_sg.add_argument("file", help="客户材料（docx/pdf/md）")
    p_sg.add_argument("--output", help="输出 spec.yml 路径（须在 output/ 下，如 output/通用/spec_gen.yml）")
    p_sg.add_argument("--client", help="客户名")
    p_sg.add_argument("--scene", help="场景名（默认：整体信息化规划）")

    # 招标文件解析
    p_bp = sub.add_parser("bid-parse", help="解析招标文件，提取评分标准/格式要求/资质条款")
    p_bp.add_argument("file", help="招标文件路径（pdf/docx/txt/md）")
    p_bp.add_argument("--client", help="客户名（输出到 output/{客户}/）")
    p_bp.add_argument("--no-split", action="store_true", help="不拆分技术标/商务标")

    # PPT 单页热更新
    p_pp = sub.add_parser("ppt-page", help="[已废弃 D-090] PPT 单页重生成 -> 用 HTML 可编辑模式改单页")
    p_pp.add_argument("spec", help="spec.yml 路径")
    p_pp.add_argument("page_index", type=int, help="页码（从0开始）")
    p_pp.add_argument("output", help="输出 pptx 路径")
    p_pp.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_pp.add_argument("--base", help="基础 pptx（如有，替换其中对应页）")

    # PPT 分段构建（10+ 页自动分段）
    p_pb = sub.add_parser("ppt-build", help="[已废弃 D-090] 分段构建 PPT -> 用 html-build --pptd-only + pptd-build")
    p_pb.add_argument("spec", help="spec.yml 路径")
    p_pb.add_argument("output", help="输出 pptx 路径")
    p_pb.add_argument("--chunk-size", type=int, default=3, help="每段几页（默认3）")
    p_pb.add_argument("--no-quality", action="store_true", help="跳过质量自评")
    p_pb.add_argument("--client", default=None, help="客户名（触发生成前验证）")

    # HTML 方案生成（HTML 先行工作流入口）
    p_hb = sub.add_parser("html-build", help="从 spec.yml 生成方案 HTML + pptd 工程（双输出）",
                          epilog="前置: spec.yml 必须含 confirmed: true（人工确认后才允许渲染，否则 RenderBlockedError）\n"
                                 "示例: python _cli.py html-build spec.yml output/客户/方案_v1.html --client 客户名\n"
                                 "      python _cli.py html-build spec.yml output/客户/方案_v1.html --pptd-only --client 客户名")
    p_hb.add_argument("spec", help="spec.yml 路径")
    p_hb.add_argument("output", help="输出 .html 路径")
    p_hb.add_argument("--style", default="", help="强制样式: education/enterprise/tech/gov")
    p_hb.add_argument("--industry", default="", help="客户行业，从 profile.md 取主题色覆盖")
    p_hb.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_hb.add_argument("--pptd", default=None,
                      help="pptd 工程输出目录（默认与 .html 同名同目录）")
    p_hb.add_argument("--html-only", action="store_true", help="只出 HTML，不出 pptd")
    p_hb.add_argument("--pptd-only", action="store_true", help="只出 pptd 工程，不出 HTML")
    p_hb.add_argument("--inline-editor", action="store_true",
                      help="编辑器 JS/CSS 内联进 HTML（默认外部引用 _assets/）")

    # deliver（一键编排，P1-5 协调逻辑外置）
    p_del = sub.add_parser("deliver", help="一键编排：spec -> html-build -> pptd-build（协调逻辑外置，AI 只做判断）",
                           epilog="示例: python _cli.py deliver spec.yml output/客户/方案_v1.html --client 客户名\n"
                                  "      python _cli.py deliver spec.yml output/客户/方案_v1.html --client 客户名 --shots")
    p_del.add_argument("spec", help="spec.yml 路径")
    p_del.add_argument("output", help="输出 .html 路径")
    p_del.add_argument("--style", default="", help="强制样式: education/enterprise/tech/gov")
    p_del.add_argument("--client", default=None, help="客户名")
    p_del.add_argument("--pptd", default=None, help="pptd 工程目录（默认与 .html 同名同目录）")
    p_del.add_argument("--inline-editor", action="store_true", help="HTML 内联编辑器")
    p_del.add_argument("--shots", action="store_true", help="pptd-build 后逐页截图目检")

    # HTML -> PPT 转换（HTML 高保真转可编辑 PPT）
    p_hp = sub.add_parser("html-to-ppt", help="[已废弃 D-090] HTML 转 PPT -> 用 html-build 双输出（同源同步）")
    p_hp.add_argument("input", help="输入 HTML 文件路径")
    p_hp.add_argument("output", help="输出 .pptx 路径")
    p_hp.add_argument("--multi-page", action="store_true", help="长 HTML 按视口分页（默认单页）")
    p_hp.add_argument("--mode", choices=["auto", "svg", "text"], default="auto",
                      help="转换模式: auto=自动检测, svg=SVG图形型, text=文本排版型")

    # pptd 工程生成器（spec -> pptd 骨架，L3 确定性生成，D-086 上游）
    p_pg = sub.add_parser("pptd-gen", help="从 spec.yml 生成 pptd 工程骨架（主pptd + pages + media）",
                          epilog="示例: python _cli.py pptd-gen output/客户/方案_spec.yml --client 客户 --name 方案\n"
                                 "生成后跑: python _cli.py pptd-build output/客户/方案/方案.pptd --shots --client 客户")
    p_pg.add_argument("spec", help="spec.yml 路径（必须 confirmed: true）")
    p_pg.add_argument("--client", default=None, help="客户名（触发生成前验证 + 默认输出目录）")
    p_pg.add_argument("--output", default=None, help="工程输出目录（默认 output/{client}/{name}/）")
    p_pg.add_argument("--name", default=None, help="项目名（默认取 spec.document.title 清洗）")
    p_pg.add_argument("--style", default="enterprise", help="样式名（同 html-build，默认 enterprise）")
    p_pg.add_argument("--logo", default=None, help="logo 文件路径（不填则从 spec.document.cover.logo_image 探测）")
    p_pg.add_argument("--final-page", action="store_true", help="末尾加致谢页（默认不加）")

    # pptd 富媒体 PPT 构建（python-pptx 后端，D-086 富媒体路线 + C 批次自研引擎）
    p_pd = sub.add_parser("pptd-build", help="pptd 富媒体 PPT 构建（check->convert->verify->可选截图）",
                          epilog="前置: python-pptx（venv 依赖；PPTD_BACKEND 可选后端选择，默认 python_pptx）\n"
                                 "示例: python _cli.py pptd-build output/客户/工程/方案.pptd --shots --client 客户名\n"
                                 "QA 循环: python _cli.py pptd-build output/客户/工程/方案.pptx --shots（仅重出截图）")
    p_pd.add_argument("pptd", help="主 .pptd 文件路径（或 .pptx + --shots 仅截图）")
    p_pd.add_argument("-o", "--output", default=None, help="输出 .pptx 路径（默认与 pptd 同名）")
    p_pd.add_argument("--check-only", action="store_true", help="只校验不转换")
    p_pd.add_argument("--shots", action="store_true", help="转换后逐页导出 PNG 截图目检（需本机 PowerPoint）")
    p_pd.add_argument("--shots-dir", default=None, help="截图输出目录（默认 <pptx目录>/_shots_<名称>/）")
    p_pd.add_argument("--client", default=None, help="客户名（触发生成前验证）")

    # 自动固化
    p_con = sub.add_parser("consolidate", help="检测客户反复出现的模式，升级到 .trae/rules/")
    p_con.add_argument("client", help="客户名")
    p_con.add_argument("--threshold", type=int, default=3, help="出现次数阈值（默认3）")

    # 报价 Excel 生成
    p_qb = sub.add_parser("quote-build", help="生成报价（HTML/Excel）")
    p_qb.add_argument("spec", help="spec.yml 路径")
    p_qb.add_argument("--template", default="一页报价模板", help="模板版式名")
    p_qb.add_argument("--format", choices=["html", "xlsx", "all"], default="html", help="输出格式（默认 html）")
    p_qb.add_argument("--style", default="enterprise", help="样式名，与方案 HTML 统一")
    p_qb.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_qb.add_argument("output", help="输出文件路径（须在 output/ 下，扩展名自动处理）")

    p_qsg = sub.add_parser("quote-spec-gen", help="从客户材料提取报价 spec.yml")
    p_qsg.add_argument("materials_dir", help="材料目录")
    p_qsg.add_argument("output", help="输出 spec.yml 路径（须在 output/ 下）")
    p_qsg.add_argument("--client", default="", help="客户名")

    p_qv = sub.add_parser("quote-validate", help="校验报价 Excel 公式")
    p_qv.add_argument("xlsx", help="xlsx 路径")

    p_ql = sub.add_parser("quote-library", help="管理报价内容库")
    p_ql.add_argument("action", choices=["list", "search"], help="操作")
    p_ql.add_argument("type", choices=["modules", "licenses", "services", "thirdparty"], help="类型")
    p_ql.add_argument("--keyword", help="搜索关键词（search 用）")

    p_qs = sub.add_parser("quote-search", help="语义搜索全报价内容库")
    p_qs.add_argument("keyword", help="搜索关键词（名称+描述）")
    p_qs.add_argument("--top", type=int, default=10, help="返回数量")

    # Word 文档生成
    p_db = sub.add_parser("docx-build", help="从 spec.yml 生成 Word 文档")
    p_db.add_argument("spec", help="spec.yml 路径")
    p_db.add_argument("output", help="输出 docx 路径")
    p_db.add_argument("--client", default=None, help="客户名（触发生成前验证）")

    # theme-guard（合并 theme-list + theme-set，PROJECT_DESIGN.md §13）
    p_tg = sub.add_parser("theme-guard", help="列出/刷新/记录核心约束")
    p_tg.add_argument("client", help="客户名")
    p_tg.add_argument("--task-id", help="任务ID")
    p_tg.add_argument("--set", dest="set_theme", help="记录新主题（省略则列出当前主题）")
    p_tg.add_argument("--scope", choices=["client", "task"], default="client", help="作用域（默认 client）")
    p_tg.add_argument("--priority", choices=["critical", "high"], default="high")
    p_tg.add_argument("--turn", type=int, default=0, help="当前对话轮次（>0 时按间隔检查是否需 re-grounding）")

    # theme-verify（原 theme-check 独立命令）
    p_tv = sub.add_parser("theme-verify", help="检查产出文件是否覆盖 permanent 主题")
    p_tv.add_argument("file", help="产出文件路径")
    p_tv.add_argument("client", help="客户名")

    # audit（验证与审计）
    p_kd = sub.add_parser("key-doctor", help="检查各 API key 来源与可用性（默认活体探测）")
    p_kd.add_argument("--no-probe", action="store_true", help="只列来源，不联网探测")
    p_audit = sub.add_parser("audit", help="审计：配置/运行时/主题/行为")
    p_audit.add_argument("--mode", choices=["config", "runtime", "behavior", "theme", "all"], default="config")
    p_audit.add_argument("--client", help="客户名（--mode theme 时使用）")

    p_cite = sub.add_parser("cite-audit", help="引用及审查报告：从 spec 提取引用 + 反向校验来源 + 主题覆盖")
    p_cite.add_argument("spec", help="spec.yml 路径")
    p_cite.add_argument("--client", help="客户名（用于主题守卫检查）")
    p_cite.add_argument("--output", help="输出报告路径（须在 output/ 下；默认 spec 同名_审查报告.md，spec 不在 output/ 下时必须显式指定）")

    # spec-diff（两份 spec 结构化对比，配合 3.1 快照回溯历史版本）
    p_sdiff = sub.add_parser("spec-diff", help="两份 spec.yml 结构化 diff（退出码 0=无差异 1=有差异 2=错误）",
                             epilog="示例: python _cli.py spec-diff spec_v4.yml spec_v5.yml\n"
                                    "      python _cli.py spec-diff .versions/方案_spec.yml.20260720120000 方案_spec.yml  # 对比 §3.1 快照")
    p_sdiff.add_argument("spec_a", help="旧版 spec.yml 路径（对比基准）")
    p_sdiff.add_argument("spec_b", help="新版 spec.yml 路径")

    # spec-edit（类型化增量变更，P1-6）
    p_sedit = sub.add_parser("spec-edit", help="spec.yml 类型化增量变更（add_page/update_page/delete_page/add_element/update_element/delete_element）",
                             epilog="示例: python _cli.py spec-edit spec.yml --op add_page --page-id p04 --title 实施计划 --layout phases\n"
                                    "      python _cli.py spec-edit spec.yml --op add_element --page-id p03 --element '{\"type\":\"text\",\"content\":\"新增\"}'")
    p_sedit.add_argument("spec", help="spec.yml 路径")
    p_sedit.add_argument("--op", required=True, choices=["add_page", "update_page", "delete_page", "add_element", "update_element", "delete_element"], help="操作类型")
    p_sedit.add_argument("--page-id", default=None, help="目标页面 ID")
    p_sedit.add_argument("--title", default=None, help="页面标题（add_page 用）")
    p_sedit.add_argument("--layout", default=None, help="页面布局（add_page 用，默认 bullets）")
    p_sedit.add_argument("--index", type=int, default=None, help="元素序号（add_element/update_element/delete_element 用）")
    p_sedit.add_argument("--element", default=None, help='元素 JSON（add_element 用，如 \'{"type":"text","content":"内容"}\'）')
    p_sedit.add_argument("--updates", default=None, help='更新 JSON（update_page/update_element 用，如 \'{"title":"新标题"}\'）')

    # review（独立 LLM 审查）
    p_review = sub.add_parser("review", help="独立审查：用独立 LLM 会话审查产出质量")
    p_review.add_argument("output_file", help="产出文件路径（HTML/PPT/DOCX）")
    p_review.add_argument("--client", help="客户名（用于加载铁律）")
    p_review.add_argument("--spec", help="spec.yml 路径（用于内容一致性检查）")
    p_review.add_argument("--adversarial", action="store_true", help="对抗性审查模式（挑刺者角色，只找问题不打分；与 --parallel 组合 = 多角色并行挑刺）")
    p_review.add_argument("--parallel", action="store_true", help="并行审查模式（5 路独立会话各查一个维度，汇总去重；与 --adversarial 组合 = 多角色并行挑刺）")

    # compact（替代 compress / compress-doc）
    p_compact = sub.add_parser("compact", help="压缩客户历史（task_history + context.md）")
    p_compact.add_argument("client", help="客户名")
    p_compact.add_argument("--keep", type=int, default=10, help="保留最近 N 条 task_history 记录（默认 10）")
    p_compact.add_argument("--keep-sessions", type=int, default=1, help="context.md 保留最近 N 次完整会话（默认 1，传 0 跳过）")

    # 会话开始（auto_for_input CLI 入口）
    p_ss = sub.add_parser("session-start", help="会话开始：判层级+加载上下文+语义召回",
                          epilog="AGENTS.md 规定的 MANDATORY 入口：每段会话收到第一条用户消息后先执行，再开始工作")
    p_ss.add_argument("input", help="用户输入文本")
    p_ss.add_argument("--client", default=None, help="客户名")
    p_ss.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费，省去 stdout 解析）")

    # 洞察
    p_insight = sub.add_parser("insight", help="生成洞察报告")
    p_insight.add_argument("client", help="客户名")
    p_insight.add_argument("--context", default="", help="上下文摘要")
    p_insight.add_argument("--context-file", default=None, help="从文件读取上下文")
    p_insight.add_argument("--turn", type=int, default=0, help="当前对话轮次")
    p_insight.add_argument("--input", default="", help="用户最新输入（检测关键词触发）")
    p_insight.add_argument("--force", action="store_true", help="强制触发（上下文压缩前用）")

    # 反模式 diff 记录
    p_dr = sub.add_parser("diff-record", help="记录 AI 原版 vs 人工修改的差异")
    p_dr.add_argument("client", help="客户名")
    p_dr.add_argument("ai_version", help="AI 原版文件路径")
    p_dr.add_argument("human_version", help="人工修改版文件路径")
    p_dr.add_argument("--note", default="", help="备注")

    # 世界书 graph 命令
    sub.add_parser("graph-build", help="构建/更新 client_graph.json + client_index.md").add_argument("client", help="客户名")
    p_gq = sub.add_parser("graph-query", help="查询客户图节点和边")
    p_gq.add_argument("client", help="客户名")
    p_gq.add_argument("--node", default=None, help="节点 ID")
    p_gq.add_argument("--type", default=None, help="节点类型 (decision/output/insight/method/client_profile)")
    p_gq.add_argument("--edges", default=None, help="查询与该节点关联的边")
    p_gq.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费）")
    p_ga = sub.add_parser("graph-add", help="手动添加图节点")
    p_ga.add_argument("client", help="客户名")
    p_ga.add_argument("--type", required=True, help="节点类型")
    p_ga.add_argument("--title", required=True, help="节点标题")
    p_ga.add_argument("--summary", default="", help="节点摘要")
    p_ga.add_argument("--method", default="", help="关联方法论名")
    p_gl = sub.add_parser("graph-link", help="手动添加图边")
    p_gl.add_argument("client", help="客户名")
    p_gl.add_argument("--from", dest="from_id", required=True, help="起点节点 ID")
    p_gl.add_argument("--to", dest="to_id", required=True, help="终点节点 ID")
    p_gl.add_argument("--type", required=True, help="边类型 (produced_by/revised_from/used_method/applied_to)")
    p_gl.add_argument("--note", default="", help="备注")
    # 语义库（子计划1）
    p_sc = sub.add_parser("semantic-catalog", help="校验能力目录 JSON")
    p_sc.add_argument("--check", action="store_true", default=True, help="校验（默认行为）")
    p_sc.add_argument("--path", default=None, help="能力目录路径（默认 _knowledge/capability_catalog/能力目录_E9标准_v1.json）")

    return parser


def _build_dispatch():
    """构建命令调度表（模块级函数，供 audit 检查）。

    55 个活跃命令 + 3 个废弃存根（D-090：ppt-build / html-to-ppt / ppt-page）
    = 8 防幻觉查询 + 6 状态写入 + 8 生成执行（含 3 存根）+ 10 校验与审计
      + 6 索引管理 + 10 大纲与辅助 + 4 世界书 + 6 quote 辅助。
    其余废弃命令见 _DEPRECATED（22 个）。
    """
    return {
        # === 防幻觉查询（8）===
        "status": cmd_status,
        "pending": cmd_pending,
        "recall": cmd_recall,
        "recall-eval": cmd_recall_eval,
        "me": cmd_me,
        "load": cmd_load,
        "theme-guard": cmd_theme_guard,
        "theme-verify": cmd_theme_verify,
        # === 状态写入（6）===
        "new": cmd_new,
        "save": cmd_save,
        "classify": cmd_classify,
        "archive-note": cmd_archive_note,
        "inbox-scan": cmd_inbox_scan,
        "consolidate": cmd_consolidate,
        "compact": cmd_compact,
        # === 生成执行（8）===
        "html-build": cmd_html_build,
        "deliver": cmd_deliver,
        "ppt-build": cmd_ppt_build,
        "pptd-gen": cmd_pptd_gen,
        "pptd-build": cmd_pptd_build,
        "html-to-ppt": cmd_html_to_ppt,
        "docx-build": cmd_docx_build,
        "ppt-page": cmd_ppt_page,
        "quote-build": cmd_quote_build,
        # === 校验与审计（10）===
        "verify": cmd_verify,
        "style-check": cmd_style_check,
        "vision-describe": cmd_vision_describe,
        "session-start": cmd_session_start,
        "audit": cmd_audit,
        "key-doctor": cmd_key_doctor,
        "cite-audit": cmd_cite_audit,
        "review": cmd_review,
        "web-search": cmd_web_search,
        "spec-diff": cmd_spec_diff,
        "spec-edit": cmd_spec_edit,
        # === 索引管理（6）===
        "index": cmd_index,
        "index-rebuild": cmd_index_rebuild,
        "skills-sync": cmd_skills_sync,
        "load-skill": cmd_load_skill,
        "embed-rebuild": cmd_embed_rebuild,
        "chunk-inspect": cmd_chunk_inspect,
        "chunk-read": cmd_chunk_read,
        # === 大纲与辅助（10）===
        "read": cmd_read,
        "aliases": cmd_aliases,
        "aliases-export": cmd_aliases_export,
        "aliases-import": cmd_aliases_import,
        "outline-list": cmd_outline_list,
        "outline-apply": cmd_outline_apply,
        "outline-to-spec": cmd_outline_to_spec,
        "insight": cmd_insight,
        "diff-record": cmd_diff_record,
        "embed-stats": cmd_embed_stats,
        # === 世界书 graph（4）===
        "graph-build": cmd_graph_build,
        "graph-query": cmd_graph_query,
        "graph-add": cmd_graph_add,
        "graph-link": cmd_graph_link,
        # === 语义库（子计划1：仅本命令；子计划2-4 各自追加）===
        "semantic-catalog": cmd_semantic_catalog,
        # === quote 辅助（6）===
        "spec-gen": cmd_spec_gen,
        "bid-parse": cmd_bid_parse,
        "quote-spec-gen": cmd_quote_spec_gen,
        "quote-validate": cmd_quote_validate,
        "quote-library": cmd_quote_library,
        "quote-search": cmd_quote_search,
    }


# 已废弃命令 → 替代命令（argparse 之前拦截；_cli_audit 统计废弃命令数）
_DEPRECATED = {
    "ppt-pages": "ppt-build --preview",
    "ppt-outline": "ppt-build",
    "ppt-preview": "ppt-build --preview",
    "tpl-list": "outline-list",
    "tpl-parse": "outline-apply",
    "tpl-tune": "outline-apply",
    "tpl-save": "outline-apply",
    "tpl-apply": "outline-apply",
    "extract-batch": "new",
    "compress": "compact",
    "compress-doc": "compact",
    "handoff": "session-start",
    "feedback": "diff-record",
    "diff": "diff-record",
    "quality-check": "verify",
    "theme-list": "theme-guard",
    "theme-set": "theme-guard",
    "theme-check": "theme-verify",
    "skill-list": "(已降级为内部函数)",
    "skill-save": "(已降级为内部函数)",
    "llm-usage": "(已删除)",
    "llm-providers": "(已删除)",
}


def main():
    # Windows 控制台默认 GBK，输出 emoji/符号会 UnicodeEncodeError；统一按 UTF-8 输出
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, 'reconfigure', None)
        if _reconfigure:
            _reconfigure(encoding='utf-8', errors='replace')

    # 客户 xlsx 里的旧式打印区域定义名会触发 openpyxl UserWarning 刷屏，与本工具无关
    import warnings
    warnings.filterwarnings("ignore", message=r"Print area cannot be set.*")

    # 在 argparse 之前拦截已废弃命令（argparse 会拒绝未注册的子命令）
    if len(sys.argv) > 1 and sys.argv[1] in _DEPRECATED:
        cmd = sys.argv[1]
        replacement = _DEPRECATED[cmd]
        print(f"[已废弃] 命令 `{cmd}` 已合并到 `{replacement}`")
        if not replacement.startswith("("):
            print(f"  请改用：python _cli.py {replacement} ...")
        sys.exit(1)

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 防线 2：CLI 是唯一执行路径（PROJECT_DESIGN.md §5.4）
    # _cli.py 调用 _renderer 前设置环境变量，防止 AI 直接 import _renderer 绕过
    os.environ['_PRESALES_CLI_INVOKED'] = '1'

    dispatch = _build_dispatch()

    fn = dispatch.get(args.command)
    if not fn:
        print(f"未知命令: {args.command}")
        parser.print_help()
        sys.exit(1)

    # P2：异常兜底，避免用户看到 Python traceback
    try:
        fn(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
        sys.exit(130)
    except FileNotFoundError as e:
        print(f"[错误] 找不到文件：{e}")
        print("  提示：检查文件路径是否正确，文件是否存在")
        sys.exit(1)
    except PermissionError as e:
        print(f"[错误] 没有权限访问：{e}")
        print("  提示：尝试以管理员身份运行，或检查文件是否被其他程序占用")
        sys.exit(1)
    except ModuleNotFoundError as e:
        print(f"[错误] 缺少依赖模块：{e}")
        print("  提示：运行 pip install -r requirements.txt 安装缺失的依赖")
        sys.exit(1)
    except ImportError as e:
        print(f"[错误] 导入失败：{e}")
        print("  提示：检查 Python 环境是否完整，或重新 pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        msg = str(e)
        if "API key" in msg.lower() or "api_key" in msg.lower():
            print("[错误] API Key 未配置或无效")
            print("  提示：检查项目根目录的 .env 文件，确保已填入有效的 API Key")
            print(f"  详细：{msg[:200]}")
        elif "No such file" in msg or "not found" in msg.lower():
            print(f"[错误] 文件不存在：{msg[:200]}")
            print("  提示：检查文件路径是否正确")
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            print("[错误] 请求超时")
            print("  提示：检查网络连接，或稍后重试")
        elif "memory" in msg.lower() or "MemoryError" in str(type(e)):
            print("[错误] 内存不足")
            print("  提示：尝试分批处理，或关闭其他程序释放内存")
        else:
            print(f"[错误] 命令 '{args.command}' 执行失败")
            print(f"  原因：{msg[:300]}")
            print("  提示：如果是第一次运行，请先执行 python _cli.py status 检查环境是否正常")
        sys.exit(1)


if __name__ == "__main__":
    main()
