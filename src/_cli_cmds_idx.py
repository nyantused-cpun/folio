# -*- coding: utf-8 -*-
"""CLI 检索面命令（T1 拆分自 _cli.py，2026-09-01）。
承载：检索面·索引 / 读取与大纲。不改命令行为。"""
import os
import sys

import yaml

from _cli_infra import SCRIPT_DIR, _open_file, _guard_read_path
from _paths import CLIENTS_DIR
from _session import read_chunk, rebuild_bm25_index_all
from _pipeline import read_full
from _indexer import update_index
from _aliases import (
    load_global, load_client, diff_clients, export_to_excel, import_from_excel,
    suggest_aliases, ALIAS_TYPE_SECTIONS,
    resolve_client_name, GLOBAL_ALIASES_PATH,
)
from _embed_index import build_embedding_index, get_stats, inspect_chunks, scan_corpus

def cmd_read(args):
    path = _guard_read_path(args, args.file, label="read")
    summary, cache = read_full(path)
    print("=== 注意力摘要 ===")
    print(summary)
    print(f"\n=== 缓存路径 ===\n{cache}")
    print(f"\n=== 提示 ===\nAI 可 Read 此缓存读全文：{cache}")


def cmd_doc_extract(args):
    """doc-extract：统一文档读取（P0-1，dev_plan_cli_panel_2026-08-18）。

    补齐 PROJECT_DESIGN §1.3 欠账：二进制解析（pdf/docx/xlsx/pptx）归 CLI。
    纯只读、不落缓存、不调 LLM。
    """
    from _doc_extract import extract_document

    path = _guard_read_path(args, args.file, label="doc-extract")
    out = extract_document(
        path,
        fmt_hint=getattr(args, "fmt", "auto"),
        mode=getattr(args, "mode", "text"),
        as_json=bool(getattr(args, "json", False)),
    )
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(out)
    if isinstance(out, dict) and not out.get("ok"):
        sys.exit(1)


def cmd_pdf_pages(args):
    """pdf-pages：把 PDF 逐页渲染成 PNG 截图（图片型/扫描 PDF 的视觉/OCR 前置）。

    纯读取、输出到 --out 目录、不调 LLM；依赖 PyMuPDF（fitz，doc-extract 的 pdf 分支同款）。
    """
    import fitz
    from _renderer import _validate_output_path, OutputPathNotAllowedError

    path = _guard_read_path(args, args.file, label="pdf-pages")
    out_dir = args.out
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(SCRIPT_DIR, out_dir)
    # P2-3：--out 是写路径，必须过 output/ 白名单（默认值已改为 output/通用/pdf_pages）
    try:
        _validate_output_path(out_dir)
    except OutputPathNotAllowedError as e:
        print(f"[pdf-pages] {e}")
        print("  提示：渲染截图属临时产物，请放 output/ 下（如 output/通用/pdf_pages）")
        sys.exit(1)
    dpi = int(getattr(args, "dpi", 150))

    # 魔数校验：fitz 修复模式会把任意文件"读出"伪页（曾把文本文件渲染成 42 张垃圾图），
    # 非真 PDF 一律拒绝并 exit 1。
    try:
        with open(path, "rb") as fh:
            head = fh.read(1024)
    except OSError as e:
        print(f"[pdf-pages] 打开失败: {e}")
        sys.exit(1)
    if b"%PDF" not in head:
        print(f"[pdf-pages] 非 PDF 文件（头部未含 %PDF 魔数），拒绝渲染: {path}")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        print(f"[pdf-pages] 打开失败: {e}")
        sys.exit(1)
    try:
        print(f"[pdf-pages] {path} 共 {doc.page_count} 页 -> {out_dir}")
        saved = 0
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=dpi)
            fn = os.path.join(out_dir, f"page_{i:02d}.png")
            pix.save(fn)
            print(f"  {fn}")
            saved += 1
        print(f"[pdf-pages] 完成，共 {saved} 张")
    finally:
        doc.close()


def cmd_extract_md(args):
    """extract-md：把多个文档全文抽取并合并为一个带索引的 Markdown 文档。

    用途：把若干 PPTX/PDF/DOCX 等材料文本汇总成一份可检索 MD（含目录索引）。
    纯本地读取+写入，不调 LLM。
    """
    from _doc_extract import extract_document
    from _renderer import _validate_output_path, OutputPathNotAllowedError

    out_path = args.out
    # P2-3：--out 是写路径，必须过 output/ 白名单
    try:
        _validate_output_path(out_path)
    except OutputPathNotAllowedError as e:
        print(f"[extract-md] {e}")
        print("  提示：合并 MD 属产出物，请放 output/ 下（如 output/通用/材料汇总.md）")
        sys.exit(1)
    docs = args.doc
    if not docs:
        print("用法: python _cli.py extract-md --out <输出.md> <文档...>")
        sys.exit(1)

    sections = []
    failed = 0
    for raw in docs:
        path = _guard_read_path(args, raw, label="extract-md")
        try:
            res = extract_document(path, fmt_hint="auto", mode="text", as_json=True)
        except Exception as e:  # noqa: BLE001
            sections.append((os.path.basename(path), f"(读取失败: {e})"))
            failed += 1
            continue
        text = res.get("text") if isinstance(res, dict) else res
        if not text:
            text = res.get("error", "(无文本)") if isinstance(res, dict) else str(res)
            if isinstance(res, dict) and not res.get("ok"):
                failed += 1
        sections.append((os.path.basename(path), text))

    lines = ["# 材料文本提取汇总（带索引）", "",
             "> 由 `python _cli.py extract-md` 抽取合并，纯本地读取，未调 LLM。", "",
             "## 索引", ""]
    for i, (name, text) in enumerate(sections, 1):
        lines.append(f"{i}. **{name}**　（约 {len(text)} 字符）")
    lines.append("")
    lines.append("---")
    for i, (name, text) in enumerate(sections, 1):
        lines.append(f"## {i}. {name}")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")

    if not os.path.isabs(out_path):
        out_path = os.path.join(SCRIPT_DIR, out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as e:
        print(f"[extract-md] 写入失败: {e}")
        sys.exit(1)
    print(f"[extract-md] 已合并 {len(sections)} 个文档 -> {out_path}")
    if failed:
        print(f"[extract-md] 注意：{failed}/{len(docs)} 个文档读取失败（已记录在输出中）", file=sys.stderr)
    if failed == len(docs):
        sys.exit(1)

# ============================================================
# Word 文档处理命令（docx-inspect / docx-edit / word-com / template-fill）
# 排版核心走 _renderer.docx_com_postprocess 契约函数；
# 结构提取与精确编辑直接用 win32com（Word COM）。
# ============================================================



def cmd_chunk_read(args):
    """按 path#anchor 读完整 chunk 全文。

    I-8 别名归一化：路径的客户目录段若为别名（如 _knowledge/clients/蓝海/...，
    蓝海 是 蓝海集团 的别名），经 resolve_client_name 解析为规范目录名后读取；
    精确/子串歧义不重写（只认 alias 命中）。
    """
    path_spec = str(args.path)
    head, _, anchor = path_spec.partition("#")
    # 别名归一化：仅当客户目录段为 alias 命中时重写
    try:
        rel = os.path.relpath(head, CLIENTS_DIR)
        parts = rel.split(os.sep)
        if len(parts) >= 1 and parts[0] not in (".", "..", ""):
            resolved, _, matched_by = resolve_client_name(parts[0])
            if matched_by == "alias" and resolved != parts[0]:
                head = os.path.join(CLIENTS_DIR, resolved, *parts[1:])
                print(f"[chunk-read] 客户别名解析: {parts[0]} -> {resolved}")
    except Exception:
        pass  # 解析失败按原路径读
    head = _guard_read_path(args, head, label="chunk-read")
    if not os.path.exists(head):
        print(f"错误: 文件不存在: {head}")
        sys.exit(1)
    spec = head + ("#" + anchor if anchor else "")
    text = read_chunk(spec)
    print(text)


def cmd_index(args):
    update_index()


def cmd_index_rebuild(args):
    """重建 BM25 索引（扫描所有客户文件，含别名展开）"""
    result = rebuild_bm25_index_all()
    print(f"已索引 {result['indexed_count']} 个文档块")
    for w in result.get("warnings", []):
        print(f"[warn] {w}")


def cmd_skills_sync(args):
    """.folio/skills/ -> .agents/skills/ 单向镜像（事实源在前者）+ 路由表自动生成。"""
    from _skills_sync import (
        sync_skills, scan_skill_routing, load_route_overrides,
        apply_route_overrides, update_routing_table,
        apply_disable_model_invocation,
    )
    src = os.path.join(SCRIPT_DIR, ".folio", "skills")
    dst = os.path.join(SCRIPT_DIR, ".agents", "skills")
    if not os.path.isdir(src):
        print(f"错误: 技能源目录不存在: {src}")
        sys.exit(1)
    report = sync_skills(src, dst, prune=args.prune)
    print("技能同步完成（.folio/skills -> .agents/skills）：")
    print(f"  新增 {len(report['added'])} · 更新 {len(report['updated'])} · 未变 {len(report['unchanged'])} · 剪枝 {len(report['pruned'])}")
    for label in ("added", "updated", "pruned"):
        for name in report[label]:
            print(f"  [{label}] {name}")
    if report.get("symlinks_skipped"):
        print(f"  跳过 symlink {len(report['symlinks_skipped'])} 个（显式 no-op，不计入变更）：")
        for name in report["symlinks_skipped"]:
            print(f"  [symlink-skip] {name}")
    if report.get("orphans"):
        print(f"  ⚠ 孤儿技能 {len(report['orphans'])} 个（目标端有、事实源无；回迁 .folio/skills/ 或用 --prune 清理）：")
        for name in report["orphans"]:
            print(f"  [orphan] {name}")

    overrides = load_route_overrides(os.path.join(SCRIPT_DIR, "route_overrides.yml"))
    changed = apply_disable_model_invocation(src, overrides)
    if changed:
        print(f"  [T3] excluded 且非 keep_active，自动加 disable-model-invocation: {len(changed)} 个")
        for name in changed:
            print(f"    [auto-disable] {name}")
        sync_skills(src, dst, prune=False)
    entries = scan_skill_routing(src)
    entries = apply_route_overrides(entries, overrides)
    result = update_routing_table(os.path.join(SCRIPT_DIR, "AGENTS_REFERENCE.md"), entries)
    print(f"  路由表: {result}（{len(entries)} 个 skill）")


def cmd_load_skill(args):
    """load-skill：打印 SKILL.md 全文 + 写已读哨兵。

    哨兵门禁（REQUIRE_SKILL_SENTINEL，默认开）：*-build 前必须先 load-skill
    读必读 skill，否则生成被机械拦截。显式 false/0/no/off 才关闭。
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

    skill_path = os.path.join(SCRIPT_DIR, ".folio", "skills", skill, "SKILL.md")
    if not os.path.isfile(skill_path):
        print(f"错误: 未找到技能 {skill}（.folio/skills/{skill}/SKILL.md 不存在）")
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
    # P2（B3）：edit 分支必须先于 --global 列表判断——旧序 `aliases --global --edit`
    # 被上面的 global_only 列表分支截胡 return，全局编辑功能整体失效（死分支）
    if args.edit:
        if args.global_only:
            path = GLOBAL_ALIASES_PATH
        else:
            if not args.client:
                print("用法: aliases edit --client <客户名>")
                sys.exit(1)
            path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", args.client, "aliases.yml")
        if not os.path.exists(path):
            print(f"[提示] 别名文件尚不存在，将创建空模板: {path}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# 标准词: [别名1, 别名2]\n")
        _open_file(path)
        return
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
    if not args.client:
        print("用法: aliases --client <客户名> | --global | <客户A> <客户B>（对比） | edit [--global | --client <客户名>]")
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


def cmd_aliases_suggest(args):
    """从 --text/--file 或客户 context.md/decisions.md 中提取别名建议（只输出不写）。"""
    client = args.client
    if not client:
        print("用法: python _cli.py aliases-suggest <客户> [--text 文本] [--file 文件]")
        sys.exit(1)

    text = getattr(args, "text", None)
    text_file = getattr(args, "file", None)
    if text_file:
        if not os.path.exists(text_file):
            print(f"[aliases-suggest] 文件不存在: {text_file}")
            sys.exit(1)
        with open(text_file, "r", encoding="utf-8") as f:
            text = f.read()
    if not text:
        # 默认取客户 context.md + decisions.md（只读不写）
        parts = []
        for name in ("context.md", "decisions.md"):
            p = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client, name)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    parts.append(f.read())
        text = "\n".join(parts)
    if not text:
        print("[aliases-suggest] 没有可供提取的文本（请用 --text/--file）")
        return

    existing = load_client(client)
    candidates = suggest_aliases(text, existing)
    if not candidates:
        print("[aliases-suggest] 未发现新的别名候选")
        return
    print(f"[aliases-suggest] {client} 可能新增别名建议（只输出，不自动写入）:")
    for section in ALIAS_TYPE_SECTIONS:
        items = [c for c in candidates if c["type"] == section]
        if not items:
            continue
        print(f"  ## {section}")
        for c in items:
            print(f"    - {c['term']}（{c['reason']}）")
    print("  确认后请人工更新 aliases.yml（aliases.md 已退役，存量文件仅作历史参考）")





def cmd_reflect(args):
    """会话反思：提取学习时刻，生成决策提案（供 AI 弹确认框后写入 decisions.md）。

    --apply（P3）：提案直接写入 decisions.md（persistence=task，AI 推断待确认）。
    """
    from _reflect import reflect_session, format_proposals_text
    import json as _json

    proposals, warning = reflect_session(args.client, apply=getattr(args, 'apply', False))
    if warning:
        print(f"[warn] {warning}")
    if getattr(args, 'json', False):
        print(_json.dumps(proposals, ensure_ascii=False, indent=2))
    elif proposals:
        print(format_proposals_text(proposals))
    else:
        print("（无提案）")


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


def _coverage_warn(name, indexed, corpus_count, rebuild_cmd):
    """C-B3 双路覆盖率告警：索引内文档数 vs 应有语料文档数（scan_corpus 分块数）。

    覆盖率口径沿用各索引构建日志的既有口径（build 时打印的块/文档数），
    不引入新概念；缺数据（corpus_count 为 None）时静默跳过，由调用方先打降级行。
    """
    if corpus_count is None or indexed >= corpus_count:
        return
    if indexed == 0:
        print(f"  [warn] {name} 覆盖率 0%（索引缺失/为空，语料 {corpus_count} 块），"
              f"运行 python _cli.py {rebuild_cmd} 重建")
    else:
        pct = indexed * 100.0 / corpus_count
        print(f"  [warn] {name} 覆盖率 {pct:.0f}%（索引 {indexed} 块 / 语料 {corpus_count} 块），"
              f"落后语料，运行 python _cli.py {rebuild_cmd} 重建")


def _bm25_index_count():
    """读 BM25 索引的文档数；返回 (count, error)。

    count=None 表示索引不存在；error 非空表示存在但读取失败（含 HMAC 拒绝）。
    """
    from _bm25 import BM25_INDEX_PATH
    from _paths import safe_pickle_load
    if not os.path.exists(BM25_INDEX_PATH):
        return None, None
    try:
        payload = safe_pickle_load(BM25_INDEX_PATH)
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"
    if payload is None:
        return 0, "HMAC 签名校验失败，索引被拒绝加载"
    if not isinstance(payload, dict):
        return 0, "索引内容格式非法（非 dict）"
    paths = payload.get("paths")
    return (len(paths) if isinstance(paths, list) else 0), None


def cmd_embed_stats(args):
    """查看 Embedding / BM25 双路索引统计（C-B3：双路覆盖率告警）。

    覆盖率 = 索引内文档数 / scan_corpus 应有语料文档数；任一路缺失或落后即 [warn]。
    """
    # 语料基线（双路共用口径）；扫描失败不阻断统计，覆盖率维度降级跳过
    try:
        corpus_count = len(scan_corpus())
    except Exception as e:
        corpus_count = None
        print(f"[warn] 语料扫描失败（{type(e).__name__}: {e}），覆盖率检查跳过")

    stats = get_stats()
    print("=== Embedding 索引统计 ===")
    if stats.get("error"):
        print(f"[embed-stats] 索引读取失败: {stats['error']}")
        print("  提示：可运行 python _cli.py embed-rebuild --force 重建索引")
        sys.exit(1)
    embed_count = 0
    if not stats.get("exists"):
        print("Embedding 索引不存在。运行 `python _cli.py embed-rebuild` 构建。")
    else:
        embed_count = stats["count"]
        print(f"  向量数: {embed_count}")
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
    _coverage_warn("Embedding", embed_count, corpus_count, "embed-rebuild")

    print("\n=== BM25 索引统计 ===")
    bm25_count, bm25_err = _bm25_index_count()
    if bm25_err:
        print(f"BM25 索引读取失败: {bm25_err}")
        print("  提示：可运行 python _cli.py index-rebuild 重建")
        _coverage_warn("BM25", 0, corpus_count, "index-rebuild")
    elif bm25_count is None:
        print("BM25 索引不存在。运行 `python _cli.py index-rebuild` 重建。")
        _coverage_warn("BM25", 0, corpus_count, "index-rebuild")
    else:
        print(f"  文档数: {bm25_count}")
        print("  路径: _knowledge/.cache/bm25_index.pkl")
        _coverage_warn("BM25", bm25_count, corpus_count, "index-rebuild")


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

