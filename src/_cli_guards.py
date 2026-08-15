# -*- coding: utf-8 -*-
"""CLI 生成前后检查守卫：pre_check / post_check / auto_review。"""
import os
import time


# 生成前必读 skill（仅作用于哨兵门禁 REQUIRE_SKILL_SENTINEL=true 时，默认关）
# 此清单是"全量机械拦截"清单，与 session-start 的提示层（AI 自判层级）解耦
# delivery-pipeline = 交付顺序（HTML 先行->确认->PPT）
# spec-writing-guide = spec 字段/容量/confirmed 门禁
# de-ai-style = 客户可见文案去 AI 化
# presentation-content-design = 表达内容设计（做方案/汇报前置）
REQUIRED_GEN_SKILLS = ["delivery-pipeline", "spec-writing-guide", "de-ai-style", "presentation-content-design"]

# 哨兵开关（环境变量，默认关）。观察当前模型不老实读 skill 时手动开启：
#   设为 true/1/yes 后，*-build 前必须先用 `python _cli.py load-skill <名称>` 读必读 skill
_SENTINEL_FLAG = "REQUIRE_SKILL_SENTINEL"


def _sentinel_enabled():
    return os.environ.get(_SENTINEL_FLAG, "").strip().lower() in ("1", "true", "yes")


def mark_skill_read(skill_name):
    """记录 skill 已读（load-skill 命令调用）。返回哨兵文件路径。"""
    from _paths import SKILL_READ_DIR
    os.makedirs(SKILL_READ_DIR, exist_ok=True)
    path = os.path.join(SKILL_READ_DIR, f"{skill_name}.json")
    data = {"skill": skill_name, "read_at": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": int(time.time())}
    with open(path, "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def require_skill_read(skill_names=None):
    """哨兵门禁：REQUIRE_SKILL_SENTINEL=true 且未 load-skill 时抛 RenderBlockedError。

    机械拦截"没读 skill"这一行为（对无 Hook 环境/不遵循 skill 的模型）。
    默认关——env 未设/false 时直接放行，不影响正常流程。
    """
    if not _sentinel_enabled():
        return
    names = skill_names or REQUIRED_GEN_SKILLS
    from _paths import SKILL_READ_DIR
    missing = [n for n in names
               if not os.path.exists(os.path.join(SKILL_READ_DIR, f"{n}.json"))]
    if missing:
        from _renderer import RenderBlockedError  # 延迟 import 防循环
        hint = "\n".join(f"  python _cli.py load-skill {m}" for m in missing)
        raise RenderBlockedError(
            "REQUIRE_SKILL_SENTINEL=true：生成前必须先读必读 skill（未检测到已读记录）：\n"
            f"{hint}\n"
            "（load-skill 会打印 SKILL.md 全文并记录已读；这是对不遵循 skill 加载的模型设置的机械门禁）"
        )


def is_confirmed(spec):
    """confirmed 门唯一判定（单点实现）。

    所有 confirmed 检查点（Renderer / quote-build / pptd-gen / _auto_review）
    必须走这里，不得各自 spec.get("confirmed")。
    见 docs/refactor_plan_spec_pipeline_2026-07-20.md §五 0.6。
    """
    return bool((spec or {}).get("confirmed"))


def require_confirmed(spec, context=""):
    """confirmed 门硬阻断：未确认抛 RenderBlockedError（与 Renderer 同异常）。"""
    if not is_confirmed(spec):
        from _renderer import RenderBlockedError  # 延迟 import 防循环
        suffix = f"（{context}）" if context else ""
        raise RenderBlockedError(f"spec.confirmed 未设为 true，无法生成{suffix}")


def _run_pre_check(client_name=None):
    """生成前强制验证（机械阻断）。加载反模式 + 主题守卫。

    P0-2 修复：原 try/except 把 MANDATORY 的 style_guard 包成"跳过"，
    削弱了 project_rules.md 声称的机械阻断保证。改为：
    - ImportError（依赖未装）-> 打印提示返回 None，调用方应阻断
    - 其他异常（代码 bug / 文件损坏）-> 直接抛出阻断生成
    - _style_guard.pre_check 内部已 catch 软失败（塞到 warnings），不会抛
    """
    # 哨兵门禁（默认关，REQUIRE_SKILL_SENTINEL=true 时生效）：
    # 未读必读 skill 直接抛 RenderBlockedError，机械拦截"没读 skill"
    require_skill_read()

    try:
        from _style_guard import pre_check as style_pre_check
    except ImportError as e:
        print(f"[style_guard] ✗ 依赖缺失，阻断生成: {e}")
        print("  请安装所需依赖后再生成产出物。")
        return None
    # pre_check 内部已处理所有软失败（文件不存在 / theme_guard 加载失败都塞到 warnings）
    # 这里抛出的异常是真正的代码问题，应阻断而非吞掉
    guard = style_pre_check(client_name=client_name)
    for w in guard.get("warnings", []):
        print(f"[style_guard] [warn] {w}")

    # 检查上次 review 结果（spec 5.1.1）
    try:
        import json
        import _paths
        if os.path.exists(_paths.REVIEW_LOG):
            with open(_paths.REVIEW_LOG, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if isinstance(entries, list) and entries:
                last = None
                for e in reversed(entries):
                    if e.get("client") == client_name:
                        last = e
                        break
                if last and last.get("verdict") == "FAIL":
                    n = len(last.get("issues", []))
                    warning = (f"上次 review 发现 {n} 个问题"
                               f"（{os.path.basename(last.get('file', ''))}），请先处理")
                    guard.setdefault("warnings", []).append(warning)
                    print(f"[review] [warn] {warning}")
    except Exception:
        pass  # review_log 损坏不阻断

    if not guard.get("required_reads"):
        print("[style_guard] [warn] 未找到必读文件（style.md / 语感样本）")
    # 主题守卫
    tg = guard.get("theme_guard")
    if tg and tg.get("head_context"):
        print(f"[theme_guard] HEAD: {tg['head_context'][:120]}")
    if tg and tg.get("tail_checklist"):
        print(f"[theme_guard] TAIL: {tg['tail_checklist'][:120]}")
    return guard


def print_visual_check_advice(lint_errors=0, new_component=False):
    """L2 目检降级建议（思维链规约 §5，2026-07-21 P0-2 修复）。

    环境中性：只陈述 L2 规则，不点名任何环境专属工具
    （旧文案点名的 "webapp-testing skill" 是 Trae 生态名，Kimi / 其他 CLI 不存在）。
    纪律从 AI 自觉变为 CLI 指令：
      - lint 0 error 且无新组件     -> 无需目检，直接交付
      - lint 有 error               -> 只目检报错页 + 1 张抽样（≤3 张）
      - 新组件首用 / 重大改版       -> 建议全量目检
    """
    if new_component:
        print("[目检] L2 规则：新组件首用 / 重大改版 → 建议全量目检")
    elif lint_errors > 0:
        print(f"[目检] L2 规则：lint 有 {lint_errors} 个 error → 只目检报错页 + 1 张抽样（≤3 张）")
    else:
        print("[目检] L2 规则：lint 0 error 且无新组件 → 无需目检，直接交付")
        print("  （例外：本次若实际有新组件首用或重大改版，仍按 L2 全量目检）")


def _run_post_check(output_path, client_name=None):
    """生成后自动检查主题覆盖 + 质量验证。

    P0-2 修复（2026-07-21）：删除原 playwright UI 验证建议（点名 Trae 专属
    webapp-testing skill，且与思维链规约 §5 L2「lint 0 error 不截图」正面冲突）。
    目检建议改由 print_visual_check_advice 按 L2 规则输出，由调用方在拿到
    lint 结果后调用。
    """
    # 主题覆盖检查（仅 HTML，因为 PPT/DOCX 是二进制）
    if client_name and output_path.endswith((".html", ".htm")):
        try:
            from _theme_guard import pre_check as theme_pre_check, check_coverage
            tg = theme_pre_check(client_name)
            themes = tg.get("themes", [])
            if themes:
                with open(output_path, "r", encoding="utf-8") as f:
                    text = f.read()
                result = check_coverage(text, themes)
                for m in result.get("missing", []):
                    print(f"[theme_guard] [warn] 未覆盖核心诉求: {m['theme']}")
                if result.get("covered"):
                    print(f"[theme_guard] 已覆盖 {len(result['covered'])} 个核心诉求")
        except Exception as e:
            print(f"[theme_guard] 跳过覆盖检查: {e}")


def _auto_review(output_path, client_name=None, spec_path=None):
    """generate 命令内部自动调用的审查（静默模式，PASS 时不打印）。

    P2 优化（2026-07-20）：条件触发跳过 LLM review。
    跳过条件（全部满足才跳过）：
      1. spec.confirmed=true（用户已确认 spec）
      2. 本地禁用词检查通过（_review._check_banned 无命中）
    跳过时仍写 verdict="SKIP" 到 review_log.json，保持 _run_pre_check 闭环。
    首次生成或 spec 未 confirmed 时仍跑 LLM review。
    """
    import os

    # --- 条件触发判断 ---
    can_skip_llm = False

    if spec_path and os.path.exists(spec_path):
        try:
            import yaml
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = yaml.safe_load(f) or {}
            # 注意方向：confirmed=true 是"可跳过 LLM review"的条件之一，
            # 不是阻断条件（阻断走 require_confirmed）
            if not is_confirmed(spec):
                pass
            else:
                # 本地禁用词检查
                try:
                    from _review import _check_banned, _read_output_text
                    output_text = _read_output_text(output_path)
                    if output_text is None:
                        pass
                    else:
                        banned = _check_banned(output_text)
                        if banned:
                            print(f"[独立审查] 禁用词命中 {len(banned)} 处，不跳过 LLM review")
                        else:
                            can_skip_llm = True
                except Exception:
                    pass
        except Exception:
            pass
    else:
        pass

    # --- 跳过 LLM，写 SKIP 记录保持闭环 ---
    if can_skip_llm:
        try:
            from _review import write_review_log
            skip_result = {
                "verdict": "SKIP",
                "issues": [],
                "summary": "spec.confirmed=true + 本地禁用词检查通过，跳过 LLM review",
                "scores": {},
            }
            write_review_log(skip_result, output_path, client_name)
            print("[独立审查] 跳过 LLM review（spec 已 confirmed + 禁用词检查通过）")
            return skip_result
        except Exception as e:
            print(f"[独立审查] SKIP 记录写入失败，回退到 LLM review: {e}")

    # --- 正常调 LLM review ---
    try:
        from _review import review as _do_review
        return _do_review(
            output_path=output_path,
            client_name=client_name,
            spec_path=spec_path,
            quiet=True,
        )
    except Exception as e:
        print(f"[独立审查] 跳过（{e}）")
        return None
