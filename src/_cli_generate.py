# -*- coding: utf-8 -*-
"""CLI 生成执行模块：HTML/PPT/DOCX/报价/spec 生成 + 质量自评 + review。"""
import os
import sys

from _cli_guards import _run_pre_check, _run_post_check, _auto_review

# 备份工具（生成前 .bak 快照）
try:
    from _backup import backup_before_generate
except ImportError:
    def backup_before_generate(file_path, max_versions=5):
        """无 _backup.py 时降级为空操作。"""
        pass


def _snapshot_spec_if_confirmed(spec_path):
    """§八 3.1：confirmed spec 在渲染前快照本体到 spec 同目录 .versions/（保留 5 版）。

    挂接点选 CLI 生成命令（html-build / docx-build / pptd-gen）、Renderer 构造
    之前，而非 Renderer.__init__：快照是管线动作不是渲染职责——Renderer 在测试、
    审计等上下文也会被构造，放 __init__ 会每次构造都写盘；CLI 层一次命令至多
    一次快照，旧版本由 backup_before_generate 自清理（保留最近 5 版），不刷屏。
    未 confirmed 不快照（Renderer 的 confirmed 门随即阻断，本就不该产生版本）。
    与最新一份快照内容相同（hash 判重）则跳过——重复构建同内容 spec 不再
    产生新快照挤占 5 版容量。
    """
    try:
        import yaml
        from _cli_guards import is_confirmed
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
    except Exception:
        return  # spec 读不出时不快照，交给 Renderer 报出真正的错误
    if is_confirmed(spec):
        if _same_as_latest_snapshot(spec_path):
            return  # 内容与最新快照一致：跳过（防重复构建挤占 5 版容量）
        backup_before_generate(spec_path)


def _same_as_latest_snapshot(spec_path):
    """spec 与 .versions/ 最新一份快照内容相同（hash 判重）则返回 True。

    快照文件名带时间戳（backup_before_generate），字典序最大即最新；
    目录不存在/读不出时返回 False 照常快照（保守）。
    """
    import hashlib
    versions_dir = os.path.join(os.path.dirname(spec_path), ".versions")
    basename = os.path.basename(spec_path)
    try:
        existing = sorted(f for f in os.listdir(versions_dir)
                          if f.startswith(basename + "."))
        if not existing:
            return False
        with open(spec_path, "rb") as f:
            current = hashlib.sha256(f.read()).digest()
        with open(os.path.join(versions_dir, existing[-1]), "rb") as f:
            return hashlib.sha256(f.read()).digest() == current
    except Exception:
        return False


def _deprecated(name, replacement):
    """退役命令统一废弃提示（D-090：保留注册 1 个版本，调用即提示后退出）。"""
    def _stub(args):
        print(f"[废弃] {name} 已退役（D-090，2026-07-19 起）")
        print(f"  替代：{replacement}")
        sys.exit(1)
    return _stub


def _run_layout_lint(issues):
    """§七 2.8 版式 lint 结果处理：打印明细；有 error 级返回 False（调用方阻断）。"""
    from _layout_lint import format_issues, has_errors
    if issues:
        print(format_issues(issues))
    if has_errors(issues):
        print("[阻断] 版式 lint 发现 error，请修复后重试")
        return False
    return True


cmd_ppt_page = _deprecated(
    "ppt-page", "HTML 可编辑模式：浏览器打开方案 HTML -> 工具条「编辑」改单页 ->「导出 HTML」")

cmd_ppt_build = _deprecated(
    "ppt-build", "python _cli.py html-build <spec> --pptd-only -> pptd-build（同源双输出，D-088）")

cmd_html_to_ppt = _deprecated(
    "html-to-ppt", "html-build 双输出已 HTML/PPT 同源同步，无需转换（D-088）")


def cmd_html_build(args):
    """html-build：spec -> .html + .pptd 双输出（D-088）+ HTML 可编辑（D-091）。

    默认双出：HTML 为主产物；--pptd-only 只出 pptd 工程；--html-only 只出 HTML。
    --pptd <目录> 指定 pptd 工程目录（默认与 .html 同名同目录）。
    """
    # 生成前强制验证
    client = getattr(args, 'client', None)
    pre_check_result = _run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    from _renderer import Renderer, _resolve_style

    html_only = getattr(args, 'html_only', False)
    pptd_only = getattr(args, 'pptd_only', False)
    want_html = not pptd_only
    want_pptd = not html_only

    # §八 3.1：Renderer 构造前快照 confirmed spec 本体（挂接点理由见该函数 docstring）
    _snapshot_spec_if_confirmed(args.spec)

    r = Renderer(args.spec, client_industry=args.industry)
    if args.style:
        # --style 覆盖 spec.style：HTML 端经 r.style_name -> resolve_theme 生效，
        # pptd 端经 r.style 生效
        r.style_name = args.style
        r.style = _resolve_style(args.style)

    # ---- HTML 产物 ----
    if want_html:
        backup_before_generate(args.output)
        r.render_html(args.output)
        if r.report.has_issues():
            print(r.report.summary())
        # D-091：注入可编辑能力（工具条 + 配色 + 导出 + 重置）
        try:
            from _renderer.html_editor_injector import inject
            inject(args.output, inline=getattr(args, 'inline_editor', False))
            print("已注入可编辑能力（编辑/配色/导出/重置）")
        except Exception as e:
            print(f"[可编辑注入] 失败（不影响 HTML 本体）: {e}")
        print(f"已生成方案 HTML: {args.output}")
        try:
            from _verify_hook import run_single
            ok = run_single(args.output, client_name=client, render_report=r.report)
            if not ok:
                print("[阻断] verify 失败，请修复后重试")
                sys.exit(1)
        except Exception as e:
            print(f"[验证] 失败（非跳过）: {e}")

        # 生成后主题覆盖检查
        _run_post_check(args.output, client_name=client)

        # 独立审查（独立 LLM 会话，不带对话历史）
        _auto_review(args.output, client_name=client, spec_path=args.spec)

    # ---- pptd 工程产物 ----
    lint_error_count = 0
    if want_pptd:
        import _pptd_gen
        from _renderer import _validate_output_path

        pptd_dir = getattr(args, 'pptd', None) or os.path.splitext(args.output)[0]
        pptd_dir = os.path.abspath(pptd_dir)
        try:
            _validate_output_path(pptd_dir)
        except Exception as e:
            print(f"[阻断] {e}")
            sys.exit(1)

        name = os.path.basename(pptd_dir.rstrip(os.sep)) or "deck"
        name = _pptd_gen._slugify_name(name) or "deck"
        style = r.style or _resolve_style(r.style_name)

        main_pptd_path = os.path.join(pptd_dir, f"{name}.pptd")
        backup_before_generate(main_pptd_path)
        from _renderer.elements import RenderReport
        report = RenderReport()
        files, media_files = _pptd_gen.build_deck(
            r.spec, args.spec, style, name, pptd_dir, client_name=client,
            report=report)
        # 版式 lint 兜底（§七 2.8）：error 级阻断生成，工程不落盘
        from _layout_lint import lint_pptd_files, has_errors
        lint_issues = lint_pptd_files(files)
        if not _run_layout_lint(lint_issues):
            sys.exit(1)
        # 走到这里即 error 已被阻断（上面 sys.exit），计数恒为 0；保留计数防未来策略放宽
        lint_error_count = sum(1 for i in lint_issues if has_errors([i]))
        _pptd_gen.emit_deck(files, media_files, pptd_dir)
        if report.has_issues():
            print(report.summary())
        page_count = sum(1 for p in files if p.endswith(".page"))
        print(f"已生成 pptd 工程: {pptd_dir}（{page_count} 页 + 主 {name}.pptd）")

        # pptd check 兜底（python-pptx 后端；dev plan §6.2 verify 双产物）
        try:
            import _pptd
            backend = _pptd.get_backend()
            if backend is not None:
                _ok, _wc = backend.check(main_pptd_path)
                _pptd.write_check_report(main_pptd_path, _wc)
                if _ok:
                    print("[pptd] check PASS")
                else:
                    print("[阻断] pptd check 未通过，请修复后重试")
                    sys.exit(1)
            else:
                print("[pptd] 后端不可用，跳过 check（pptd-build 时会再检）")
        except Exception as e:
            print(f"[pptd] check 跳过: {e}")
        print(f"  下一步：python _cli.py pptd-build {main_pptd_path} --client {client or '<客户名>'}")

    # L2 目检建议（思维链规约 §5，P0-2）：拿到真实 lint 结果后输出，环境中性
    if want_html:
        from _cli_guards import print_visual_check_advice
        print_visual_check_advice(lint_errors=lint_error_count)


def cmd_quote_build(args):
    """生成报价：spec + 模板 -> HTML/Excel"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    pre_check_result = _run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    # L3 硬约束：报价 spec 必须人工确认（单点 require_confirmed，与 Renderer 同异常同行为）
    import yaml as _yaml
    from _cli_guards import require_confirmed
    with open(args.spec, "r", encoding="utf-8") as f:
        _spec_head = _yaml.safe_load(f) or {}
    require_confirmed(_spec_head, context="quote-build")

    from _quote_data import QuoteBuilder
    from _quote_html import render_html
    from _quote_engine import ExcelRenderer
    from _renderer import _validate_output_path, OutputPathNotAllowedError

    fmt = getattr(args, "format", "html")
    base = os.path.splitext(args.output)[0]

    # §八 3.5：派生输出（base+.html/.xlsx）白名单前置校验，出名单即阻断并提示，
    # 避免 QuoteBuilder 构建完才在写入点抛异常（底层写入点同样有校验兜底）
    derived = []
    if fmt in ("html", "all"):
        derived.append(base + ".html")
    if fmt in ("xlsx", "all"):
        derived.append(base + ".xlsx")
    try:
        for _p in derived:
            _validate_output_path(_p)
    except OutputPathNotAllowedError as e:
        print(f"[阻断] {e}")
        print("  提示：报价属产出物，输出路径请放在 output/ 下（如 output/通用/报价_v1）")
        sys.exit(1)

    builder = QuoteBuilder()
    qd = builder.build(args.spec)

    outputs = []

    if fmt in ("html", "all"):
        html_path = base + ".html"
        backup_before_generate(html_path)
        render_html(qd, html_path, style_name=args.style)
        outputs.append(html_path)
        print(f"生成: HTML: {html_path}")

    if fmt in ("xlsx", "all"):
        xlsx_path = base + ".xlsx"
        backup_before_generate(xlsx_path)
        renderer = ExcelRenderer()
        renderer.render(qd, args.template, xlsx_path, style_name=args.style)
        issues = renderer.validate(xlsx_path)
        if issues:
            print("校验问题:")
            for i in issues:
                print(f"  - {i}")
        outputs.append(xlsx_path)
        print(f"生成: Excel: {xlsx_path}")

    # 生成后自动验证
    if outputs:
        print("\n[验证] 自动验证生成产出...")
        from _verify_hook import run_single
        for path in outputs:
            try:
                run_single(path)
            except Exception as e:
                print(f"[验证] 跳过 {path}: {e}")
        _run_post_check(outputs[0], client_name=client)
        # L2 目检建议（思维链规约 §5，P0-2）：报价无版式 lint，verify 通过即 0 error
        from _cli_guards import print_visual_check_advice
        print_visual_check_advice(lint_errors=0)
    else:
        print("未生成任何输出（--format 可选 html/xlsx/all）")


def cmd_spec_gen(args):
    """从客户材料生成 spec 草稿（走 outline-to-spec，默认"整体信息化规划"场景）。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    _run_pre_check(client_name=client)

    from _outline_to_spec import build_spec_from_outline
    scene = args.scene or "整体信息化规划"
    spec_path = args.output or "spec_gen.yml"
    # §八 3.5：spec 草稿写入过 output/ 白名单。选"明确提示"而非隐式改默认路径
    # （spec_gen.yml 在 cwd 根目录、不在白名单内）——默认路径是用户可见的合同，
    # 隐式改动会让既有脚本/习惯找不到文件；不传 --output 时在此阻断并给出提示
    from _renderer import _validate_output_path, OutputPathNotAllowedError
    try:
        _validate_output_path(spec_path)
    except OutputPathNotAllowedError as e:
        print(f"[阻断] {e}")
        print("  提示：spec 草稿属产出物，请用 --output 指定 output/ 下路径"
              "（如 output/通用/spec_gen.yml）")
        sys.exit(1)
    backup_before_generate(spec_path)
    build_spec_from_outline(scene, [args.file], client_name=args.client or "", output_path=spec_path)

    # 生成后自动验证
    if os.path.exists(spec_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            from _verify_hook import run_single
            run_single(spec_path)
        except Exception as e:
            print(f"[验证] 跳过: {e}")


def cmd_docx_build(args):
    """从 spec.yml 生成 Word 文档。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    pre_check_result = _run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    from _renderer import Renderer
    backup_before_generate(args.output)
    # §八 3.1：Renderer 构造前快照 confirmed spec 本体
    _snapshot_spec_if_confirmed(args.spec)
    r = Renderer(args.spec)
    r.render_docx(args.output)
    if r.report.has_issues():
        print(r.report.summary())
    if os.path.exists(args.output):
        print(f"已生成: {args.output} ({os.path.getsize(args.output)} bytes)")
    else:
        print("生成失败，请检查 spec 和依赖")
        return

    # 自动验证
    print("\n[验证] 自动验证生成产出...")
    try:
        from _verify_hook import run_single
        ok = run_single(args.output, client_name=client, render_report=r.report)
        if not ok:
            print("[阻断] verify 失败，请修复后重试")
            sys.exit(1)
    except Exception as e:
        print(f"[验证] 失败（非跳过）: {e}")

    # 生成后主题覆盖检查（DOCX 为二进制，_run_post_check 内部会跳过）
    _run_post_check(args.output, client_name=client)

    # 独立审查（独立 LLM 会话，不带对话历史）
    _auto_review(args.output, client_name=client, spec_path=args.spec)


def cmd_outline_to_spec(args):
    """场景大纲 + 客户材料 -> spec.yml 草稿（防幻觉 LLM 提取）。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    _run_pre_check(client_name=client)

    from _outline_to_spec import build_spec_from_outline
    output_path = args.output or "spec_draft.yml"
    # §八 3.5：spec 草稿写入过 output/ 白名单。选"明确提示"而非隐式改默认路径
    # （spec_draft.yml 在 cwd 根目录、不在白名单内）——理由同 cmd_spec_gen
    from _renderer import _validate_output_path, OutputPathNotAllowedError
    try:
        _validate_output_path(output_path)
    except OutputPathNotAllowedError as e:
        print(f"[阻断] {e}")
        print("  提示：spec 草稿属产出物，请用 --output 指定 output/ 下路径"
              "（如 output/通用/spec_draft.yml）")
        sys.exit(1)
    backup_before_generate(output_path)
    build_spec_from_outline(
        args.scene,
        args.materials,
        client_name=args.client or "",
        output_path=output_path
    )

    # 生成后自动验证
    if os.path.exists(output_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            from _verify_hook import run_single
            run_single(output_path)
        except Exception as e:
            print(f"[验证] 跳过: {e}")


def cmd_review(args):
    """独立审查：用独立 LLM 会话审查产出质量（不带对话历史）。

    用法：python _cli.py review <产出文件> --client <客户> [--spec <spec.yml>] [--adversarial] [--parallel]
    --adversarial：对抗性审查模式（挑刺者角色，只找问题不打分）
    --parallel：并行审查模式（5 路独立会话各查一个维度，汇总去重，单路失败不阻断）
    --adversarial --parallel：并行对抗审查（5 路独立挑刺者各查一个角度）
    """
    output_path = args.output_file
    client = getattr(args, 'client', None)
    spec_path = getattr(args, 'spec', None)
    adversarial = getattr(args, 'adversarial', False)
    parallel = getattr(args, 'parallel', False)

    if not os.path.exists(output_path):
        print(f"错误：文件不存在: {output_path}")
        sys.exit(1)

    if adversarial and parallel:
        from _review import review_adversarial_parallel as _do_review
        print("[review] 并行对抗审查模式（5 路独立挑刺者各查一个角度，单路失败不阻断）")
    elif adversarial:
        from _review import review_adversarial as _do_review
        print("[review] 对抗性审查模式（挑刺者角色，借鉴 Claude Dynamic Workflows adversarial verification）")
    elif parallel:
        from _review import review_parallel as _do_review
        print("[review] 并行审查模式（5 路独立会话，维度隔离防锚定，单路失败不阻断）")
    else:
        from _review import review as _do_review

    result = _do_review(
        output_path=output_path,
        client_name=client,
        spec_path=spec_path,
        quiet=False,
    )

    # T11 fail-closed：exit 0 ⇔ verdict == "PASS"（唯一通过）；
    # FAIL/ERROR/SKIP 一律 exit 2 —— 判定不可得（LLM/API 故障返回 ERROR）≠ 通过，
    # 此前只查 FAIL，ERROR 走 exit 0 → 工具层 ok:true → 审查静默通过（fail-open 漏洞）。
    verdict = result.get("verdict")
    if verdict != "PASS":
        if verdict == "FAIL":
            print("[审查] 发现问题，请检查上方报告")
        else:
            print(f"[审查] 判定不可得 ≠ 通过（verdict={verdict}），fail-closed 退出码 2")
        sys.exit(2)


def cmd_pptd_gen(args):
    """spec -> pptd 工程生成器（L3 确定性生成，无 LLM 调用）。

    从已确认 spec.yml 机械生成 pptd 工程骨架（主 pptd + pages/*.page +
    media/）。生成器不调 check/convert（归 pptd-build），但守门链对齐：
    pre_check + confirmed 门 + 输出白名单 + .bak。
    设计依据：docs/dev_plan_pptd_spec_gen_2026-07-18.md
    """
    import _pptd_gen
    from _renderer import _resolve_style, _validate_output_path

    client = getattr(args, 'client', None)
    pre = _run_pre_check(client_name=client)
    if pre is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    spec_path = args.spec
    if not os.path.exists(spec_path):
        print(f"[错误] spec 文件不存在: {spec_path}")
        sys.exit(1)

    spec = _pptd_gen.load_spec(spec_path)
    from _cli_guards import require_confirmed
    require_confirmed(spec, context="pptd-gen")

    # §八 3.1：confirmed 门后快照 spec 本体到 spec 同目录 .versions/（保留 5 版）
    backup_before_generate(spec_path)

    # 项目名：--name > spec.document.title 清洗 > "deck"
    name = getattr(args, 'name', None)
    if not name:
        title = spec.get("document", {}).get("title", "")
        name = _pptd_gen._slugify_name(title) or "deck"
    name = _pptd_gen._slugify_name(name)

    # 输出目录：--output > output/{client}/{name}/
    out_dir = args.output or os.path.join("output", client or "通用", name)
    out_dir = os.path.abspath(out_dir)
    try:
        _validate_output_path(out_dir)
    except Exception as e:
        print(f"[阻断] {e}")
        sys.exit(1)

    # 覆盖前备份主 pptd
    main_pptd_path = os.path.join(out_dir, f"{name}.pptd")
    backup_before_generate(main_pptd_path)

    style = _resolve_style(args.style or spec.get("style", "enterprise"))
    logo_path = getattr(args, 'logo', None)

    print(f"[pptd-gen] 生成工程 -> {out_dir}")
    print(f"  项目名: {name}")
    print(f"  主题: {args.style or spec.get('style', 'enterprise')}")
    if logo_path:
        print(f"  logo: {logo_path}")

    from _renderer.elements import RenderReport
    report = RenderReport()
    files, media_files = _pptd_gen.build_deck(
        spec, spec_path, style, name, out_dir, logo_path=logo_path, client_name=client,
        report=report)
    # 版式 lint 兜底（§七 2.8）：error 级阻断生成，工程不落盘
    from _layout_lint import lint_pptd_files
    if not _run_layout_lint(lint_pptd_files(files)):
        sys.exit(1)
    _pptd_gen.emit_deck(files, media_files, out_dir)
    if report.has_issues():
        print(report.summary())

    page_count = sum(1 for p in files if p.endswith(".page"))
    print(f"[完成] 生成 {page_count} 页 + 主 {name}.pptd")
    if media_files:
        print(f"  媒体: {len(media_files)} 个文件复制到 media/")
    print(f"\n下一步：分页润色 -> python _cli.py pptd-build {main_pptd_path} --shots --client {client or '<客户名>'}")


def cmd_pptd_build(args):
    """pptd 富媒体 PPT 构建：check -> convert -> verify（-> 可选 COM 截图）。

    C-2 起转换后端为自研 python-pptx（原 kimi_ppt_dsl.pyz 已删，见
    docs/材料生成管线C1_方言迁移差异清单_2026-08-12.md），流程与陷阱见
    _knowledge/skills/pptd-rich-ppt-pipeline.md。
    输入 .pptx + --shots 时跳过转换，仅重出截图（QA 修复循环用）。
    """
    # 生成前强制验证（与其他生成命令对齐）
    client = getattr(args, 'client', None)
    pre_check_result = _run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止构建")
        sys.exit(1)

    import _pptd

    src = args.pptd
    if not os.path.exists(src):
        print(f"[错误] 输入文件不存在: {src}")
        sys.exit(1)

    # .pptx 输入：仅截图目检（QA 修复循环，不重复 convert）
    if src.lower().endswith(".pptx"):
        if not args.shots:
            print("[错误] 输入是 .pptx 时请加 --shots（仅截图目检）")
            sys.exit(1)
        ok = _pptd.export_shots(src, args.shots_dir or _pptd.default_shots_dir(src))
        sys.exit(0 if ok else 1)

    # 输出路径（默认同名 .pptx），白名单校验（与 html-to-ppt 对齐）
    out_path = args.output or os.path.splitext(src)[0] + ".pptx"
    from _renderer import _validate_output_path
    try:
        _validate_output_path(out_path)
    except Exception as e:
        print(f"[阻断] {e}")
        sys.exit(1)

    # 转换后端（PPTD_BACKEND 环境变量选择；当前唯一实现 python_pptx）
    backend = _pptd.get_backend_or_exit()

    # [1/3] check（error 阻断，warning 目检定夺；五类 Warning 记录 check_report）
    print(f"[1/3] pptd check: {src}")
    check_ok, warn_counts = backend.check(src)
    _pptd.write_check_report(src, warn_counts)
    if not check_ok:
        print("[阻断] pptd check 未通过，修复后重试")
        sys.exit(1)

    # 版式维复检（§10 检查 7/8/9b）：打印不阻断 build；
    # 交付关卡 = python _cli.py verify <主.pptd>（检查 7 error 判 FAIL）
    from _verify import verify_pptd_deck
    _deck_ok, _deck_errors, _deck_warnings = verify_pptd_deck(
        os.path.dirname(os.path.abspath(src)) or ".")
    for _de in _deck_errors:
        print(f"  [版式维 error] {_de}")
    for _dw in _deck_warnings:
        print(f"  [版式维 warn] {_dw}")

    # 版式 lint（§七 2.8 确定性几何检查，落盘工程；error 阻断，check-only 也执行）
    from _layout_lint import lint_pptd_dir
    if not _run_layout_lint(lint_pptd_dir(os.path.dirname(os.path.abspath(src)) or ".")):
        sys.exit(1)

    if args.check_only:
        print("[完成] check 通过（--check-only，未转换）")
        return

    # [2/3] convert
    backup_before_generate(out_path)
    print(f"[2/3] pptd convert -> {out_path}")
    try:
        converted = backend.convert(src, out_path)
    except NotImplementedError as e:
        print(f"[阻断] {e}")
        sys.exit(1)
    if not converted:
        print("[阻断] convert 失败")
        sys.exit(1)
    print(f"已生成: {out_path} ({os.path.getsize(out_path)} bytes)")

    # [3/3] verify（防幻觉第四道防线，失败阻断）
    print("[3/3] verify...")
    try:
        from _verify_hook import run_single
        ok = run_single(out_path, client_name=client)
        if not ok:
            print("[阻断] verify 失败，请修复后重试")
            sys.exit(1)
    except Exception as e:
        print(f"[验证] 失败（非跳过）: {e}")

    # 可选：COM 截图目检（失败不阻断已生成的 pptx）
    if args.shots:
        out_dir = args.shots_dir or _pptd.default_shots_dir(out_path)
        print(f"[截图] 逐页导出 PNG -> {out_dir}")
        if not _pptd.export_shots(out_path, out_dir):
            print("[截图] 失败，不影响已生成的 pptx（可目检 PowerPoint 安装后重试）")


def cmd_deliver(args):
    """deliver：一键编排 spec -> html-build -> pptd-build（P1-5 协调逻辑外置）。

    借鉴 Claude Dynamic Workflows 判断/协调分离--AI 只做判断（spec 内容、确认门），
    CLI 承担协调（步骤顺序、状态传递）。deliver 内部串联：
      1. html-build（含 verify + auto_review）
      2. 自动定位 .pptd 文件
      3. pptd-build（含 verify）

    用法：python _cli.py deliver spec.yml output/客户/方案_v1.html --client 客户名 [--shots]
    """
    import subprocess

    py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      ".venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = sys.executable  # 降级用当前解释器

    spec = args.spec
    html_output = args.output
    client = args.client or ""

    # --- Step 1: html-build ---
    print("=" * 60)
    print("[deliver] Step 1/2: html-build")
    print("=" * 60)
    cmd1 = [py, "_cli.py", "html-build", spec, html_output]
    if client:
        cmd1.extend(["--client", client])
    if args.style:
        cmd1.extend(["--style", args.style])
    if args.inline_editor:
        cmd1.append("--inline-editor")
    # deliver 默认双输出（HTML + pptd 工程），不传 --html-only

    rc1 = subprocess.call(cmd1)
    if rc1 != 0:
        print(f"\n[deliver] Step 1 失败（exit {rc1}），停止编排")
        sys.exit(rc1)

    # --- 定位 .pptd 文件 ---
    # html-build 默认 pptd 目录与 .html 同名同目录
    base = os.path.splitext(html_output)[0]
    pptd_dir = args.pptd or base
    # 找主 .pptd 文件
    pptd_file = None
    if os.path.isdir(pptd_dir):
        for f in os.listdir(pptd_dir):
            if f.endswith(".pptd"):
                pptd_file = os.path.join(pptd_dir, f)
                break
    if not pptd_file:
        print(f"\n[deliver] 未找到 .pptd 文件（在 {pptd_dir} 中），停止编排")
        print("  可能原因：html-build 用了 --html-only，或 pptd 目录结构异常")
        sys.exit(1)

    # --- Step 2: pptd-build ---
    print("\n" + "=" * 60)
    print(f"[deliver] Step 2/2: pptd-build ({os.path.basename(pptd_file)})")
    print("=" * 60)
    cmd2 = [py, "_cli.py", "pptd-build", pptd_file]
    if client:
        cmd2.extend(["--client", client])
    if args.shots:
        cmd2.append("--shots")

    rc2 = subprocess.call(cmd2)
    if rc2 != 0:
        print(f"\n[deliver] Step 2 失败（exit {rc2}），HTML 已生成但 PPT 未完成")
        sys.exit(rc2)

    # --- 完成 ---
    pptx_output = os.path.splitext(pptd_file)[0] + ".pptx"
    print("\n" + "=" * 60)
    print("[deliver] 编排完成")
    print(f"  HTML: {html_output}")
    print(f"  PPT:  {pptx_output}")
    print("=" * 60)
