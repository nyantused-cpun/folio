# -*- coding: utf-8 -*-
"""CLI 生成前后检查守卫：pre_check / post_check / auto_review。"""
import os
import sys
import time
import json


# 生成前必读 skill（唯一事实源；作用于哨兵门禁 REQUIRE_SKILL_SENTINEL，默认开）
# 此清单是"生成前机械拦截"清单，AGENTS.md / _cli.py 提示 / 测试均由 audit 校验与本常量一致。
# delivery-pipeline = 交付顺序（HTML 先行->确认->PPT）
# spec-writing-guide = spec 字段/容量/confirmed 门禁
# visual-craft-guide = 视觉与图形规范（反模式/选型/容量/画法）
# 按需项（不进哨兵）：de-ai-style、presentation-content-design
REQUIRED_GEN_SKILLS = ["delivery-pipeline", "spec-writing-guide", "visual-craft-guide"]
OPTIONAL_GEN_SKILLS = ["de-ai-style", "presentation-content-design"]

# 哨兵开关（环境变量，阶段 4-6 拍板默认开：未设即视为开）。
# 显式 false/0/no/off 才关闭；开启后 *-build 前必须先用
# `python _cli.py load-skill <名称>` 读必读 skill，否则机械拦截。
_SENTINEL_FLAG = "REQUIRE_SKILL_SENTINEL"
_SENTINEL_OFF_VALUES = ("0", "false", "no", "off")


def _sentinel_enabled():
    """哨兵默认开（4-6）：env 未设或任意非显式关闭值都视为开。"""
    return os.environ.get(_SENTINEL_FLAG, "").strip().lower() \
        not in _SENTINEL_OFF_VALUES


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
    """哨兵门禁（默认开，4-6）：未 load-skill 时抛 RenderBlockedError。

    机械拦截"没读 skill"这一行为（对无 Hook 环境/不遵循 skill 的模型）。
    默认开——env 未设即生效；显式 REQUIRE_SKILL_SENTINEL=false/0/no/off 才放行。
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
            "生成前 skill 哨兵门禁（REQUIRE_SKILL_SENTINEL 默认开，"
            "显式 false 可关）：未检测到必读 skill 已读记录：\n"
            f"{hint}\n"
            "（load-skill 会打印 SKILL.md 全文并记录已读；这是对不遵循 skill 加载的模型设置的机械门禁）"
        )


def _sidecar_path(spec_path):
    """spec 同目录 <名>.confirm.json。"""
    base = os.path.splitext(os.path.basename(spec_path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(spec_path)),
                        base + ".confirm.json")


def _confirm_hash_ok(spec_path):
    """sidecar 存在且 spec_sha256 与当前文件一致时返回 True。"""
    import hashlib
    path = _sidecar_path(spec_path)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        with open(spec_path, "rb") as f:
            current = hashlib.sha256(f.read()).hexdigest()
        return payload.get("spec_sha256") == current
    except Exception:
        return False


def is_confirmed(spec, spec_path=None):
    """confirmed 门唯一判定（单点实现）。

    所有 confirmed 检查点（Renderer / quote-build / pptd-gen / _auto_review）
    必须走这里，不得各自 spec.get("confirmed")。
    见 docs/refactor_plan_spec_pipeline_2026-07-20.md §五 0.6。
    Step 6：传入 spec_path 时启用事件化 sidecar 校验（confirmed=True 且
    sidecar 存在且哈希一致）。
    """
    if not bool((spec or {}).get("confirmed")):
        return False
    if spec_path is None:
        return True
    return _confirm_hash_ok(spec_path)


def require_confirmed(spec, context="", spec_path=None):
    """confirmed 门硬阻断：未确认抛 RenderBlockedError（与 Renderer 同异常）。"""
    if not is_confirmed(spec, spec_path):
        from _renderer import RenderBlockedError  # 延迟 import 防循环
        suffix = f"（{context}）" if context else ""
        if spec_path and (spec or {}).get("confirmed"):
            raise RenderBlockedError(
                f"spec 已标记 confirmed，但 confirm sidecar 缺失或哈希不一致"
                f"（{suffix}）。请重新执行：python _cli.py confirm {spec_path}")
        raise RenderBlockedError(f"spec.confirmed 未设为 true，无法生成{suffix}")


def keynote_pre_check_warn(client_name):
    """I-3 A4：客户无 keynote.md -> 返回 WARN 文本（不 block）；有/无客户名 -> None。"""
    if not client_name:
        return None
    try:
        from _theme_guard import load_keynote
        if load_keynote(client_name) is None:
            return (f"客户 '{client_name}' 未定基调（keynote.md 缺失），"
                    "不得从材料猜权重——权重以人批 keynote 为唯一基准")
    except Exception:
        return None
    return None


def _run_pre_check(client_name=None):
    """生成前强制验证（机械阻断）。加载反模式 + 主题守卫。

    P0-2 修复：原 try/except 把 MANDATORY 的 style_guard 包成"跳过"，
    削弱了 project_rules.md 声称的机械阻断保证。改为：
    - ImportError（依赖未装）-> 打印提示返回 None，调用方应阻断
    - 其他异常（代码 bug / 文件损坏）-> 直接抛出阻断生成
    - _style_guard.pre_check 内部已 catch 软失败（塞到 warnings），不会抛
    """
    # 哨兵门禁（默认开，REQUIRE_SKILL_SENTINEL 显式 false 才关）：
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

    # I-3 A4：未定基调 WARN（不 block，新客户首轮入口提示）
    kn_warn = keynote_pre_check_warn(client_name)
    if kn_warn:
        guard.setdefault("warnings", []).append(kn_warn)
        print(f"[keynote] [warn] {kn_warn}")

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

    F0-5 fail-closed：不再裸 try/except 吞掉“无法判定”。
      - critical 主题缺失 → print FAIL + exit 2（与 theme-verify 同口径）
      - 非 critical 缺失 → warn 不阻断
      - 无法读文件 / 客户无主题 / 依赖异常 → exit 1（无法判定 ≠ 通过）
    """
    # 主题覆盖检查（仅 HTML，因为 PPT/DOCX 是二进制）
    # P3：lower() 归一扩展名——".HTML"/".Html" 旧写法会静默跳过主题覆盖检查
    if not (client_name and output_path.lower().endswith((".html", ".htm"))):
        return

    try:
        from _theme_guard import pre_check as theme_pre_check, check_coverage
        tg = theme_pre_check(client_name)
        themes = tg.get("themes", [])
        if not themes:
            print(f"[theme_guard] 客户 '{client_name}' 无 permanent 主题记录，"
                  "无法判定主题覆盖，fail-closed exit 1")
            sys.exit(1)
        with open(output_path, "r", encoding="utf-8") as f:
            text = f.read()
        result = check_coverage(text, themes)
        for m in result.get("missing", []):
            print(f"[theme_guard] [warn] 未覆盖核心诉求: {m['theme']}")
        if result.get("covered"):
            print(f"[theme_guard] 已覆盖 {len(result['covered'])} 个核心诉求")
        critical_missing = [m for m in result.get("missing", [])
                            if m.get("priority") == "critical"]
        if critical_missing:
            print(f"[theme_guard] [FAIL] {len(critical_missing)} 条 critical 铁律未覆盖"
                  "（fail-closed，exit 2）")
            sys.exit(2)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[theme_guard] 无法验证主题覆盖（{e}），fail-closed exit 1")
        sys.exit(1)


def _auto_review(output_path, client_name=None, spec_path=None, skip_review=False):
    """generate 命令内部自动调用的审查（静默模式，PASS 时不打印）。

    F0-1 fail-closed：不再因为 spec.confirmed=true 自动跳过 LLM review。
    只有调用方显式传 `skip_review=True` 才写 SKIP 记录并跳过；否则正常跑 LLM review。
    SKIP 仍通过 write_review_log 记录（显式跳过），保持 review_log 闭环。

    返回结构化 result（dict），或异常时返回 None（调用方应 fail-closed 处理）。
    """
    # --- 显式跳过：写 SKIP 记录保持闭环 ---
    if skip_review:
        try:
            from _review import write_review_log
            skip_result = {
                "verdict": "SKIP",
                "issues": [],
                "summary": "调用方显式 --skip-review 跳过 LLM review",
                "scores": {},
            }
            write_review_log(skip_result, output_path, client_name)
            print("[独立审查] 跳过 LLM review（--skip-review 显式指定）")
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
        print(f"[独立审查] 无法完成审查（{e}），fail-closed 由调用方处理")
        return None
