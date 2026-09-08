# -*- coding: utf-8 -*-
"""CLI 生成执行模块：共享助手真源 + review/confirm + 构建族/deliver 族分派。

R3-1 拆小（2026-09-08）：_cli_generate 体量棘轮 1200/1200 顶满，按功能域拆分——
  - _cli_generate_build：html-build/quote-build/spec-gen/docx-build/
    outline-to-spec/pptd-gen/pptd-build 七个构建族命令（含 R3-2 育种登记钩子）；
  - _cli_generate_deliver：deliver 编排 + receipt sidecar；
  - 本文件：共享助手真源（生成前门/快照/状态推进/预算告警/fail-closed review
    等）+ review/confirm 命令 + cmd_* re-export（_cli.py 与测试访问面不变）。

打桩面契约：测试经 ``monkeypatch.setattr(_cli_generate, "<name>", ...)`` 打桩
共享助手（_run_pre_check/backup_before_generate/_auto_review 等），子模块对
助手一律经 ``_g.<name>`` 属性调用解析，打桩本文件命名空间即全链生效。
"""
import os
import sys
import hashlib
import json
from datetime import datetime

# 打桩面真源：测试 monkeypatch 本模块命名空间的这几个名字，子模块经 _g. 属性
# 解析；本文件助手不再直呼（R3-1 拆小后），保留 re-import 故 noqa。
from _cli_guards import (  # noqa: F401
    _run_pre_check, _run_post_check, _auto_review,
)

# spec/HTML 漂移门（S0 棘轮处置拆分，2026-09-07）：三件套迁 _spec_drift_gate，
# re-import 保持 _g.<name> 调用面与打桩面不变（R3-1 后本文件不直呼，故 noqa）。
from _spec_drift_gate import (  # noqa: F401
    _check_html_drift, _pptd_apply_spec_gates, _record_html_hash,
)

# 备份工具（生成前 .bak 快照）
try:
    from _backup import backup_before_generate
except ImportError:
    def backup_before_generate(file_path, max_versions=5):
        """无 _backup.py 时降级为空操作。"""
        pass


def _run_context_health_gate(client, command):
    """P1-3：L3 生成命令自动前置 context-health。

    非 L3/L4 不强行；无 client 时跳过；前 2 次 WARN 放行，第 3 次阻断。
    """
    if not client:
        return
    try:
        from _context_health import run_context_health
        result = run_context_health(client, command=command)
        print(f"[context-health] {result.get('message', '')}")
        if result.get("verdict") == "block":
            print("[context-health] 阻断生成")
            sys.exit(2)
    except Exception as e:
        # 检查自身异常不静默放过：fail-closed 打印警告但保持原有生成可继续，
        # 因为 context-health 是概率性防线，不能因检查代码 bug 锁死业务。
        print(f"[context-health] 检查失败（{e}），本次不阻断")


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


def _advance_state(client, stage):
    """M3-F2 阶段推进：仅命令成功路径调用；失败不阻断主流程。"""
    if not client:
        return
    try:
        from _state import advance
        advance(client, stage)
        print(f"[state] 阶段推进: {client} -> {stage}")
    except Exception as e:
        print(f"[state] 阶段推进失败（不阻断）: {e}")


def _advance_html_done(client, want_html):
    """M3-F2：html-build 只有实际生成 HTML 产物时才推进 html_done。

    `--pptd-only` 生成的是 pptd 工程而非 HTML artifact，应保持原 stage，
    由后续 pptd-build 推进到 pptx_done。
    """
    if want_html:
        _advance_state(client, "html_done")


def _run_layout_lint(issues):
    """§七 2.8 版式 lint 结果处理：打印明细；有 error 级返回 False（调用方阻断）。"""
    from _layout_lint import format_issues, has_errors
    if issues:
        print(format_issues(issues))
    if has_errors(issues):
        print("[阻断] 版式 lint 发现 error，请修复后重试")
        return False
    return True


def _record_last_review(client_name, verdict, issues, source):
    """F3-2：生成链失败清单回流 session_state.json.lastReview。

    goal 闭环（M3-F3）依赖每步注入携带最近一次失败清单，让下一轮 goal round
    自然接住（F3-2）。尽力而为：任何异常只打 warn，绝不改变调用方
    fail-closed 退出码；client 缺省（无法归属客户）时跳过。
    """
    if not client_name:
        return
    try:
        from _state import set_state
        clean = []
        for item in (issues or [])[:20]:
            text = str(item).strip()
            if text:
                clean.append(text[:300])
        set_state(client_name, lastReview={
            "verdict": str(verdict or "ERROR"),
            "issues": clean,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        print(f"[state] 失败清单已回流 lastReview（{source}: {verdict}，{len(clean)} 条）")
    except Exception as e:
        print(f"[warn] lastReview 回流失败（不影响退出码）: {e}")


def _blocked_issue_summary(blocked):
    """F0-6 blocked_coverage（L3 缺失主题/渲染降级 dict）-> 人类可读 issue 列表。"""
    out = []
    for item in blocked or []:
        if isinstance(item, dict) and item.get("theme"):
            out.append(f"L3 未覆盖: {item.get('theme')}")
        elif isinstance(item, dict):
            out.append(
                f"渲染降级: {item.get('page')} elements[{item.get('index')}] "
                f"{item.get('type')} -> {item.get('target')}: {item.get('message')}")
        else:
            text = str(item).strip()
            if text:
                out.append(text)
    return out


def _budget_soft_warning():
    """F3-4：token 预算软告警起步——本月用量触阈值打印提醒，不阻断。

    CLI_BUDGET_WARN_TOKENS 设 0/负值关闭；缺省 5,000,000 tokens/月。
    触顶语义（对模型）：输出进展摘要+阻塞点+下一步，禁止静默截断。
    """
    try:
        raw = os.environ.get("CLI_BUDGET_WARN_TOKENS", "").strip()
        threshold = int(raw) if raw else 5_000_000
        if threshold <= 0:
            return
        from _cloud_llm import get_usage_summary
        month = datetime.now().strftime("%Y-%m")
        summary = get_usage_summary(month=month)
        used = int(summary.get("total_tokens") or 0)
        calls = int(summary.get("total_calls") or 0)
        if used >= threshold:
            print(f"[预算] 本月 LLM 用量 {calls} 次 / {used} tokens ≥ 软阈值 {threshold}"
                  "（仅告警不阻断；触顶时输出进展摘要+阻塞点+下一步，不静默截断）")
    except Exception:
        pass


def _fail_closed_review(result, client_name=None, source="review"):
    """F0-1: auto_review 返回结构化结果，FAIL/ERROR/None/未知 verdict 一律 exit 2。

    SKIP 是调用方显式跳过（--skip-review），视为用户知情放行；PASS 通过。
    F3-2：FAIL/ERROR 时把失败清单回流 lastReview（尽力而为，不改退出码）。
    """
    if isinstance(result, dict):
        verdict = result.get("verdict")
    else:
        verdict = "ERROR"
    if verdict == "SKIP":
        return
    if verdict != "PASS":
        issues = result.get("issues") if isinstance(result, dict) else []
        print(f"[审查] 独立审查未通过（verdict={verdict}），fail-closed exit 2")
        # W1-2（2026-09-06）：预算熔断时补明确文案——ERROR≠FAIL，是审查服务不可得，
        # 请稍后重试或人工审查（只加展示，不改退出码）
        if verdict == "ERROR" and isinstance(result, dict):
            summary = str(result.get("summary", ""))
            if "审查预算熔断" in summary:
                print(f"[审查] {summary}")
        _record_last_review(client_name, verdict, issues, source)
        sys.exit(2)


cmd_ppt_page = _deprecated(
    "ppt-page", "HTML 可编辑模式：浏览器打开方案 HTML -> 工具条「编辑」改单页 ->「导出 HTML」")

cmd_ppt_build = _deprecated(
    "ppt-build", "python _cli.py html-build <spec> --pptd-only -> pptd-build（同源双输出，D-088）")

cmd_html_to_ppt = _deprecated(
    "html-to-ppt", "html-build 双输出已 HTML/PPT 同源同步，无需转换（D-088）")


def cmd_review(args):
    """独立审查：用独立 LLM 会话审查产出质量（不带对话历史）。
    用法：python _cli.py review <产出文件> [--client <客户>] [--spec <spec.yml>] [--adversarial|--parallel|--screenshot|--incremental]（--screenshot=S9-2a 截图对抗审视，三秒测试主门；--adversarial --parallel=并行对抗；--incremental=同文件迭代复审增量审查，WP-A5）
    """
    output_path = args.output_file
    client = getattr(args, 'client', None)
    spec_path = getattr(args, 'spec', None)

    if not os.path.exists(output_path):
        print(f"错误：文件不存在: {output_path}")
        sys.exit(1)

    # WP-A5 拆小（R1，2026-09-08）：模式分派外移 _review.resolve_review_fn
    # （--incremental/截图/并行/对抗的分支与提示语单一事实源在那边）
    from _review import resolve_review_fn
    _do_review, mode_notice = resolve_review_fn(args)
    if mode_notice:
        print(mode_notice)

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
        _record_last_review(client, verdict, result.get("issues"), "review")
        sys.exit(2)


def _host_label():
    """确认 sidecar host 标记：dsh | kimi | unknown。"""
    try:
        from _doctor import _host_detect
        hosts = _host_detect()
    except Exception:
        hosts = []
    if "DSH" in hosts:
        return "dsh"
    if "Kimi" in hosts:
        return "kimi"
    return "unknown"


def cmd_confirm(args):
    """confirm：确认 spec 并写 sidecar（<spec 同目录>/<名>.confirm.json）。

    幂等：重算 SHA-256 覆盖 sidecar；同时把 spec 顶层 confirmed 置 true。
    写入复用 _save_lock，保持并发纪律。
    """
    import yaml
    from _save_lock import acquire_save_lock, release_save_lock

    spec_path = os.path.abspath(args.spec)
    if not os.path.exists(spec_path):
        print(f"[error] spec 文件不存在: {spec_path}")
        sys.exit(1)

    spec_dir = os.path.dirname(spec_path) or "."
    if not os.path.isdir(spec_dir):
        os.makedirs(spec_dir, exist_ok=True)
    lock_fd = acquire_save_lock(spec_dir)
    if lock_fd is None:
        print(f"[confirm] 获取保存锁失败：{spec_dir} 被其他进程持有")
        sys.exit(1)

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        if not isinstance(spec, dict):
            print("[error] spec 顶层必须是对象")
            sys.exit(1)
        spec["confirmed"] = True
        with open(spec_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False)

        with open(spec_path, "rb") as f:
            spec_sha256 = hashlib.sha256(f.read()).hexdigest()

        sidecar_name = os.path.splitext(os.path.basename(spec_path))[0] + ".confirm.json"
        sidecar_path = os.path.join(spec_dir, sidecar_name)
        payload = {
            "spec_sha256": spec_sha256,
            "confirmed_at": datetime.now().isoformat(timespec="seconds"),
            "host": _host_label(),
            "client": getattr(args, "client", None) or "",
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[confirm] 已确认 spec: {spec_path}")
        print(f"[confirm] sidecar: {sidecar_path}")
        print(f"[confirm] spec_sha256: {spec_sha256}")
    finally:
        release_save_lock(spec_dir, lock_fd)


# R3-1 拆小 re-export（2026-09-08）：cmd_* 实现体迁子模块，_cli.py 与测试仍从
# 本模块取名，访问面不变；置于尾部使子模块 import 时助手真源已定义完备。
from _cli_generate_build import (  # noqa: E402,F401
    cmd_html_build, cmd_quote_build, cmd_spec_gen, cmd_docx_build,
    cmd_outline_to_spec, cmd_pptd_gen, cmd_pptd_build, notify_breeding,
)
from _cli_generate_deliver import (  # noqa: E402,F401
    cmd_deliver, _repo_venv_python, _write_deliver_receipt,
)
