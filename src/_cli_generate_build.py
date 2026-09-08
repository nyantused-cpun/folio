# -*- coding: utf-8 -*-
"""CLI 生成执行——构建族命令实现体（R3-1 拆小外迁，2026-09-08）。

体量棘轮动因：_cli_generate 1200/1200 顶满（育种自动登记钩子 P3-2 净增无处落），
按功能域拆分：本文件承载 html-build / quote-build / spec-gen / docx-build /
outline-to-spec / pptd-gen / pptd-build 七个构建族命令；deliver 编排在
_cli_generate_deliver；共享助手与废弃桩留 _cli_generate。

打桩面契约：测试经 ``monkeypatch.setattr(_cli_generate, "<name>", ...)`` 打桩
（_run_pre_check / backup_before_generate / _auto_review 等 16+6 处），故本模块
对共享助手一律经 ``_g.<name>`` 模块属性在调用时解析，不经 from-import 绑定——
打桩 _cli_generate 命名空间即对本模块生效。下游模块（_renderer/_pptd_gen/
_cli_guards 等）仍在函数体内延迟 import，其打桩面不变。
"""
import os
import sys

import _cli_generate as _g


def cmd_html_build(args):
    """html-build：spec -> .html + .pptd 双输出（D-088）+ HTML 可编辑（D-091）。

    默认双出：HTML 为主产物；--pptd-only 只出 pptd 工程；--html-only 只出 HTML。
    --pptd <目录> 指定 pptd 工程目录（默认与 .html 同名同目录）。
    """
    # 生成前强制验证
    client = getattr(args, 'client', None)
    _g._run_context_health_gate(client, "html-build")
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    from _renderer import Renderer, _resolve_style

    # Step 6：事件化 confirm 门（sidecar 哈希校验）
    import yaml as _yaml2
    from _cli_guards import require_confirmed as _require_confirm
    with open(args.spec, "r", encoding="utf-8") as _f:
        _spec_head = _yaml2.safe_load(_f) or {}
    _require_confirm(_spec_head, context="html-build", spec_path=args.spec)

    html_only = getattr(args, 'html_only', False)
    pptd_only = getattr(args, 'pptd_only', False)
    want_html = not pptd_only
    want_pptd = not html_only

    # §八 3.1：Renderer 构造前快照 confirmed spec 本体（挂接点理由见该函数 docstring）
    _g._snapshot_spec_if_confirmed(args.spec)

    r = Renderer(args.spec, client_industry=args.industry)
    if args.style:
        # --style 覆盖 spec.style：HTML 端经 r.style_name -> resolve_theme 生效，
        # pptd 端经 r.style 生效
        r.style_name = args.style
        r.style = _resolve_style(args.style)

    # ---- HTML 产物 ----
    if want_html:
        _g.backup_before_generate(args.output)
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
            ok, blocked = run_single(args.output, client_name=client,
                                     render_report=r.report, return_blocked=True,
                                     density_gate=getattr(args, "density_gate", "verify"))
            if not ok:
                print("[阻断] verify 失败，请修复后重试")
                _g._record_last_review(client, "FAIL",
                                       [f"verify 未通过: {args.output}"]
                                       + _g._blocked_issue_summary(blocked),
                                       "html-build verify")
                sys.exit(1)
        except Exception as e:
            print(f"[验证] 无法验证（{e}），fail-closed exit 1")
            _g._record_last_review(client, "ERROR", [f"无法验证: {e}"], "html-build verify")
            sys.exit(1)

        # 生成后主题覆盖检查
        _g._run_post_check(args.output, client_name=client)

        # R3-2 育种自动登记（P3-2）：crafted 页出现即登记候选（register_candidate
        # 幂等）；尽力而为不阻断生成链（纪律见 docs/育种闭环流程_2026-09-08.md §2）
        try:
            notify_breeding(args.spec, args.output, client)
        except Exception as _breed_err:
            print(f"[breed] 自动登记跳过（不影响生成）: {_breed_err}")

        # 独立审查（独立 LLM 会话，不带对话历史）；FAIL/ERROR/None -> exit 2
        _g._fail_closed_review(_g._auto_review(
            args.output, client_name=client, spec_path=args.spec,
            skip_review=getattr(args, 'skip_review', False)),
            client_name=client, source="html-build review")

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
        _g.backup_before_generate(main_pptd_path)
        from _renderer.elements import RenderReport
        report = RenderReport()
        files, media_files = _pptd_gen.build_deck(
            r.spec, args.spec, style, name, pptd_dir, client_name=client,
            report=report)
        # 版式 lint 兜底（§七 2.8）：error 级阻断生成，工程不落盘
        from _layout_lint import lint_pptd_files, has_errors
        lint_issues = lint_pptd_files(files)
        if not _g._run_layout_lint(lint_issues):
            sys.exit(1)
        # 走到这里即 error 已被阻断（上面 sys.exit），计数恒为 0；保留计数防未来策略放宽
        lint_error_count = sum(1 for i in lint_issues if has_errors([i]))
        _pptd_gen.emit_deck(files, media_files, pptd_dir)
        if report.has_issues():
            print(report.summary())
        page_count = sum(1 for p in files if p.endswith(".page"))
        print(f"已生成 pptd 工程: {pptd_dir}（{page_count} 页 + 主 {name}.pptd）")
        # Step 6：记录 HTML 内容哈希 + spec 哈希（供 pptd-build 漂移检测）
        if want_html:
            _g._record_html_hash(pptd_dir, args.output,
                                 spec_path=getattr(args, "spec", None))

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

    # Step 6 双端差异报告：仅当本 spec 存在降级字段时打印（纯查表，零 LLM）
    if want_html:
        from _renderer.elements import dual_end_diff_lines
        try:
            import yaml as _yaml
            with open(args.spec, "r", encoding="utf-8") as f:
                _spec_obj = _yaml.safe_load(f) or {}
            diff_lines = dual_end_diff_lines(_spec_obj)
            if diff_lines:
                print("\n[双端差异] 本 spec 以下字段在 PPT/DOCX 端将降级或丢失：")
                for line in diff_lines:
                    print(f"  - {line}")
        except Exception:
            pass  # 差异报告是提示，读不到 spec 时静默跳过

    # M3-F2：html-build 整体成功且实际生成 HTML 产物时才推进到 html_done。
    # --pptd-only 只产出 pptd 工程、没有 HTML artifact，因此不设置 html_done；
    # 它保持调用前的 stage（例如 spec_confirmed），后续由 pptd-build 推进 pptx_done。
    _g._advance_html_done(client, want_html)

    # F3-4：token 预算软告警（触阈值提醒，不阻断）
    _g._budget_soft_warning()


def notify_breeding(spec_path, html_output, client=None, registry=None):
    """R3-2 育种自动登记（P3-2，2026-09-08）：crafted 页出现即登记候选 pattern。

    判定源与 _review_gate 同一双信号：spec 侧 collect_crafted_pages 页标签优先，
    产物侧 data-track="crafted" 硬信号兜底。register_candidate 幂等（同名非归档
    条目原样返回），同一 pattern 重复产出不重复登记。登记名 ``crafted:<页标签>``，
    确认/晋升仍走人工节律（breed confirm/promote，量化门槛见育种闭环流程 §2）。
    registry 透传 register_candidate（None=默认 _knowledge/breeding/registry.json；
    测试传 tmp_path 隔离）。
    Returns:
        list[str]: 本次新建条目 id 清单（测试断言用）；异常向上抛，由调用方兜住。
    """
    from _review_gate import _spec_crafted_pages, _html_has_crafted
    from _breeding import register_candidate
    labels = _spec_crafted_pages(spec_path) or (
        ["crafted-page"] if _html_has_crafted(html_output) else [])
    created_ids = []
    for label in labels:
        entry, created = register_candidate(
            f"crafted:{label}", source="html-build",
            notes=f"渲染链自动登记（client={client or '未署名'}）", registry=registry)
        if created and entry:
            created_ids.append(entry["id"])
            print(f"[breed] 已自动登记候选 pattern: {entry['id']}（{label}）")
    return created_ids


def cmd_quote_build(args):
    """生成报价：spec + 模板 -> HTML/Excel"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    _g._run_context_health_gate(client, "quote-build")
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    # L3 硬约束：报价 spec 必须人工确认（单点 require_confirmed，与 Renderer 同异常同行为）
    import yaml as _yaml
    from _cli_guards import require_confirmed
    with open(args.spec, "r", encoding="utf-8") as f:
        _spec_head = _yaml.safe_load(f) or {}
    require_confirmed(_spec_head, context="quote-build", spec_path=args.spec)

    # P1-4：报价门禁 Q1/Q2 确定性阻断
    try:
        from _quote_gate import check_build
        gate_issues = check_build(args.spec)
        if gate_issues:
            print("[报价门禁] 阻断（Q1/Q2）：")
            for issue in gate_issues:
                print(f"  - {issue}")
            sys.exit(2)
    except Exception as e:
        print(f"[报价门禁] 检查失败（{e}），fail-closed 阻断")
        sys.exit(2)

    from _quote_data import QuoteBuilder, load_slots
    from _quote_html import render_html
    from _quote_engine import ExcelRenderer, apply_section_capacity
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

    # B4：模板容量截断前移构建层（B3 A7 残余）。模板在 args.template 即可知，
    # 于 HTML/Excel 渲染分叉前先截断并回写 QuoteData，fmt=all 时两产物与汇总区
    # 读同一份已截断数据，杜绝数字不一致；fmt=html 无 Excel 模板约束，保持不截断
    # （HTML 无行上限，自身自洽）。渲染器内同名截断幂等兜底（直呼渲染器仍生效）。
    if fmt in ("xlsx", "all"):
        apply_section_capacity(qd, load_slots(args.template))

    outputs = []

    if fmt in ("html", "all"):
        html_path = base + ".html"
        _g.backup_before_generate(html_path)
        render_html(qd, html_path, style_name=args.style)
        outputs.append(html_path)
        print(f"生成: HTML: {html_path}")

    if fmt in ("xlsx", "all"):
        xlsx_path = base + ".xlsx"
        _g.backup_before_generate(xlsx_path)
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
                ok = run_single(path)
                if not ok:
                    print("[阻断] verify 失败，请修复后重试")
                    _g._record_last_review(client, "FAIL",
                                           [f"verify 未通过: {path}"], "quote-build verify")
                    sys.exit(1)
            except Exception as e:
                print(f"[验证] 无法验证（{e}），fail-closed exit 1")
                _g._record_last_review(client, "ERROR", [f"无法验证: {e}"], "quote-build verify")
                sys.exit(1)
        _g._run_post_check(outputs[0], client_name=client)
        # L2 目检建议（思维链规约 §5，P0-2）：报价无版式 lint，verify 通过即 0 error
        from _cli_guards import print_visual_check_advice
        print_visual_check_advice(lint_errors=0)
    else:
        print("未生成任何输出（--format 可选 html/xlsx/all）")


def cmd_spec_gen(args):
    """从客户材料生成 spec 草稿（走 outline-to-spec，默认"整体信息化规划"场景）。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

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
    _g.backup_before_generate(spec_path)
    # narrative 仅在显式传入时透传（理由同 cmd_outline_to_spec）
    if getattr(args, "narrative", None):
        build_spec_from_outline(scene, [args.file], client_name=args.client or "",
                                output_path=spec_path, narrative_path=args.narrative)
    else:
        build_spec_from_outline(scene, [args.file], client_name=args.client or "", output_path=spec_path)

    # 生成后自动验证
    if os.path.exists(spec_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            from _verify_hook import run_single
            ok = run_single(spec_path)
            if not ok:
                print("[阻断] verify 失败，请修复后重试")
                sys.exit(1)
        except Exception as e:
            print(f"[验证] 无法验证（{e}），fail-closed exit 1")
            sys.exit(1)

    # M3-F2：spec-gen 成功生成 spec 草稿 -> spec_draft
    _g._advance_state(client, "spec_draft")


def cmd_docx_build(args):
    """从 spec.yml 生成 Word 文档。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    _g._run_context_health_gate(client, "docx-build")
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    from _renderer import Renderer
    # Step 6：事件化 confirm 门（sidecar 哈希校验）
    import yaml as _yaml3
    from _cli_guards import require_confirmed as _require_confirm2
    with open(args.spec, "r", encoding="utf-8") as _f:
        _spec_head2 = _yaml3.safe_load(_f) or {}
    _require_confirm2(_spec_head2, context="docx-build", spec_path=args.spec)

    _g.backup_before_generate(args.output)
    # §八 3.1：Renderer 构造前快照 confirmed spec 本体
    _g._snapshot_spec_if_confirmed(args.spec)
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
        ok, blocked = run_single(args.output, client_name=client,
                                 render_report=r.report, return_blocked=True)
        if not ok:
            print("[阻断] verify 失败，请修复后重试")
            _g._record_last_review(client, "FAIL",
                                   [f"verify 未通过: {args.output}"]
                                   + _g._blocked_issue_summary(blocked),
                                   "docx-build verify")
            sys.exit(1)
    except Exception as e:
        print(f"[验证] 无法验证（{e}），fail-closed exit 1")
        _g._record_last_review(client, "ERROR", [f"无法验证: {e}"], "docx-build verify")
        sys.exit(1)

    # 生成后主题覆盖检查（DOCX 为二进制，_run_post_check 内部会跳过）
    _g._run_post_check(args.output, client_name=client)

    # 独立审查（独立 LLM 会话，不带对话历史）；FAIL/ERROR/None -> exit 2
    _g._fail_closed_review(_g._auto_review(
        args.output, client_name=client, spec_path=args.spec,
        skip_review=getattr(args, 'skip_review', False)),
        client_name=client, source="docx-build review")


def cmd_outline_to_spec(args):
    """场景大纲 + 客户材料 -> spec.yml 草稿（防幻觉 LLM 提取）。"""
    # 生成前强制验证
    client = getattr(args, 'client', None)
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

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
    _g.backup_before_generate(output_path)
    _allow_outside = bool(getattr(args, "allow_outside", False))
    # narrative 仅在显式传入时透传（无设计单保持原调用签名，兼容既有 monkeypatch 测试）
    if getattr(args, "narrative", None):
        build_spec_from_outline(
            args.scene,
            args.materials,
            client_name=args.client or "",
            output_path=output_path,
            narrative_path=args.narrative,
            allow_outside=_allow_outside,
        )
    else:
        build_spec_from_outline(
            args.scene,
            args.materials,
            client_name=args.client or "",
            output_path=output_path,
            allow_outside=_allow_outside,
        )

    # 生成后自动验证
    if os.path.exists(output_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            from _verify_hook import run_single
            ok = run_single(output_path)
            if not ok:
                print("[阻断] verify 失败，请修复后重试")
                sys.exit(1)
        except Exception as e:
            print(f"[验证] 无法验证（{e}），fail-closed exit 1")
            sys.exit(1)

    # M3-F2：outline-to-spec 成功生成 spec 草稿 -> spec_draft
    _g._advance_state(client, "spec_draft")


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
    pre = _g._run_pre_check(client_name=client)
    if pre is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    spec_path = args.spec
    if not os.path.exists(spec_path):
        print(f"[错误] spec 文件不存在: {spec_path}")
        sys.exit(1)

    spec = _pptd_gen.load_spec(spec_path)
    from _cli_guards import require_confirmed
    require_confirmed(spec, context="pptd-gen", spec_path=spec_path)

    # §八 3.1：confirmed 门后快照 spec 本体到 spec 同目录 .versions/（保留 5 版）
    _g.backup_before_generate(spec_path)

    # 项目名：--name > spec.document.title 清洗 > "deck"
    name = getattr(args, 'name', None)
    if not name:
        title = spec.get("document", {}).get("title", "")
        name = _pptd_gen._slugify_name(title) or "deck"
    # 末次清洗兜底与 html-build 同款（P3）：--name 全为符号时清洗结果为空仍回退 "deck"
    name = _pptd_gen._slugify_name(name) or "deck"

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
    _g.backup_before_generate(main_pptd_path)

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
    if not _g._run_layout_lint(lint_pptd_files(files)):
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
    _g._run_context_health_gate(client, "pptd-build")
    pre_check_result = _g._run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止构建")
        sys.exit(1)

    import _pptd

    src = args.pptd
    if not os.path.exists(src):
        print(f"[错误] 输入文件不存在: {src}")
        sys.exit(1)

    # Step 6 第二漂移通道：HTML 内联编辑后未导出，提示“不生效”，不阻断
    try:
        if _g._check_html_drift(os.path.dirname(os.path.abspath(src)) or "."):
            print("[提示] PPT 将从 spec 渲染，HTML 内联编辑不生效")
    except Exception:
        pass

    # 表达模式计划书 0b：spec 漂移门 + confirm 门（fail-closed）——
    # 此前 pptd-build 无 confirm/spec 校验，confirm 后改 spec 再 build
    # 会零告警用旧工程出 PPT
    _g._pptd_apply_spec_gates(os.path.dirname(os.path.abspath(src)) or ".")

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
    if not _g._run_layout_lint(lint_pptd_dir(os.path.dirname(os.path.abspath(src)) or ".")):
        sys.exit(1)

    # Step 6 bbox 机检：仅超出版心，warning 聚合不阻断
    try:
        from _layout_lint import check_pptd_bbox_margin
        _bbox_issues = check_pptd_bbox_margin(
            os.path.dirname(os.path.abspath(src)) or ".")
        if _bbox_issues:
            print(f"[bbox] 发现 {len(_bbox_issues)} 个 shape 超出版心（只报不判，不阻断）")
            for it in _bbox_issues:
                print(f"  [bbox warn] {it.page} {it.element_id}: {it.message}")
    except Exception as e:
        print(f"[bbox] 检查跳过: {e}")

    if args.check_only:
        print("[完成] check 通过（--check-only，未转换）")
        return

    # [2/3] convert
    _g.backup_before_generate(out_path)
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
        # F0-6 生产消费：pptd-build 的输入是 .pptd 工程而非 spec，构建阶段没有
        # Renderer/RenderReport 对象可传，所以此处不传 render_report；仍通过
        # return_blocked=True 消费 blocked_coverage，避免 F0-6 只有 API 暴露没有调用方。
        ok, blocked_coverage = run_single(out_path, client_name=client, return_blocked=True)
        if not ok:
            print("[阻断] verify 失败，请修复后重试")
            _g._record_last_review(client, "FAIL",
                                   [f"verify 未通过: {out_path}"]
                                   + _g._blocked_issue_summary(blocked_coverage),
                                   "pptd-build verify")
            sys.exit(1)
        if blocked_coverage:
            print(f"  [warn] verify blocked_coverage {len(blocked_coverage)} 项"
                  "（L3 未覆盖/渲染降级），请交付前确认")
    except Exception as e:
        print(f"[验证] 无法验证（{e}），fail-closed exit 1")
        sys.exit(1)

    # 可选：COM 截图目检（失败不阻断已生成的 pptx）
    if args.shots:
        out_dir = args.shots_dir or _pptd.default_shots_dir(out_path)
        print(f"[截图] 逐页导出 PNG -> {out_dir}")
        if not _pptd.export_shots(out_path, out_dir):
            print("[截图] 失败，不影响已生成的 pptx（可目检 PowerPoint 安装后重试）")

    # M3-F2：pptd-build 成功转换 -> pptx_done（--check-only / .pptx 截图路径不推进）
    _g._advance_state(client, "pptx_done")
