# -*- coding: utf-8 -*-
"""CLI 生成执行——deliver 编排族实现体（R3-1 拆小外迁，2026-09-08）。

体量棘轮动因同 _cli_generate_build（_cli_generate 1200/1200 顶满）：本文件承载
deliver 一键编排 + receipt sidecar + 仓库 venv 解释器定位。共享助手真源与
打桩契约见 _cli_generate_build 模块 docstring——本模块对 _cli_generate 命名空间
的助手一律经 ``_g.<name>`` 调用时解析，保持测试打桩面不变。
"""
import os
import sys
import hashlib
import json
from datetime import datetime

import _cli_generate as _g


def _repo_venv_python():
    """仓库内 .venv 解释器路径（子进程统一走解释器铁律）；不存在由调用方降级。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".venv", "Scripts", "python.exe")  # 仓库根/.venv


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

    py = _repo_venv_python()
    if not os.path.exists(py):
        py = sys.executable  # 降级用当前解释器

    spec = args.spec
    html_output = args.output
    client = args.client or ""

    resume = getattr(args, "resume", False)

    # --- Step 1: html-build（非 --resume） ---
    if not resume:
        print("=" * 60)
        print("[deliver] Step 1/2: html-build")
        print("=" * 60)
        cmd1 = [py, "_cli.py", "html-build", spec, html_output,
                "--density-gate", "deliver"]  # S8-C：deliver 门全视口（独立 html-build 默认 verify 不变）
        if client:
            cmd1.extend(["--client", client])
        if args.style:
            cmd1.extend(["--style", args.style])
        if args.inline_editor:
            cmd1.append("--inline-editor")
        if getattr(args, "skip_review", False):
            cmd1.append("--skip-review")
        # P2（B3）：--pptd 必须透传 Step 1——否则 pptd 工程落默认位置，
        # Step 2/`--resume` 按 args.pptd 定位必失败（帮助与实现矛盾）
        if args.pptd:
            cmd1.extend(["--pptd", args.pptd])
        # deliver 默认双输出（HTML + pptd 工程），不传 --html-only

        rc1 = subprocess.call(cmd1)
        if rc1 != 0:
            print(f"\n[deliver] Step 1 失败（exit {rc1}），停止编排")
            sys.exit(rc1)

        # --- Step 1.5: review（P5 可选，FAIL 即停）---
        if getattr(args, "review", False):
            print("\n" + "=" * 60)
            print("[deliver] Step 1.5: review（--review，FAIL 即停）")
            print("=" * 60)
            cmd_rev = [py, "_cli.py", "review", html_output]
            if client:
                cmd_rev.extend(["--client", client])
            rc_rev = subprocess.call(cmd_rev)
            if rc_rev != 0:
                print(f"\n[deliver] review 未通过（exit {rc_rev}），停止编排——先修复 HTML 再重跑")
                sys.exit(rc_rev)

        # --- Step 1.7: cite-audit 强制 strict（F0-7）---
        print("\n" + "=" * 60)
        print("[deliver] Step 1.7: cite-audit --strict")
        print("=" * 60)
        cite_report = os.path.splitext(html_output)[0] + "_审查报告.md"
        cmd_cite = [py, "_cli.py", "cite-audit", spec, "--output", cite_report, "--strict"]
        if client:
            cmd_cite.extend(["--client", client])
        rc_cite = subprocess.call(cmd_cite)
        if rc_cite != 0:
            print(f"\n[deliver] cite-audit --strict 未通过（exit {rc_cite}），停止编排——先补引用/铁律再重跑")
            sys.exit(rc_cite)

        # Step 6：HTML 已生成，暂停等待用户确认后再出 PPT
        print("\n" + "=" * 60)
        print("[deliver] HTML 已生成，PPT 暂缓")
        print(f"  awaiting confirm：python _cli.py confirm {spec}")
        print("  确认后可使用：python _cli.py deliver --resume ... 从 pptd-build 续跑")
        print("=" * 60)
        return

    # --- 定位 .pptd 文件 ---
    # html-build 默认 pptd 目录与 .html 同名同目录
    base = os.path.splitext(html_output)[0]
    pptd_dir = args.pptd or base
    # 找主 .pptd 文件
    pptd_file = None
    if os.path.isdir(pptd_dir):
        # P3：os.listdir 顺序任意，按修改时间取最新，避免多份 .pptd 时拿错工程
        candidates = [f for f in os.listdir(pptd_dir) if f.endswith(".pptd")]
        if candidates:
            candidates.sort(
                key=lambda f: os.path.getmtime(os.path.join(pptd_dir, f)),
                reverse=True)
            pptd_file = os.path.join(pptd_dir, candidates[0])
    if not pptd_file:
        print(f"\n[deliver] 未找到 .pptd 文件（在 {pptd_dir} 中），停止编排")
        print("  可能原因：html-build 用了 --html-only，或 pptd 目录结构异常")
        sys.exit(1)

    from _review_gate import deliver_gate  # S9-2d crafted 禁直出门（_review_gate.deliver_gate）
    deliver_gate(spec, html_output)

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

    # M3-F2：deliver 两端都成功 -> delivered
    _g._advance_state(client, "delivered")

    # F3-4：token 预算软告警（触阈值提醒，不阻断）
    _g._budget_soft_warning()

    # --- 完成 ---
    pptx_output = os.path.splitext(pptd_file)[0] + ".pptx"
    # C-F1：deliver receipt（产物哈希 + verify 验证摘要 sidecar；写失败降级 warn 不阻断）
    _write_deliver_receipt(spec, html_output, pptx_output, client)
    print("\n" + "=" * 60)
    print("[deliver] 编排完成")
    print(f"  HTML: {html_output}")
    print(f"  PPT:  {pptx_output}")
    print("=" * 60)


def _write_deliver_receipt(spec_path, html_output, pptx_output, client):
    """deliver receipt（C-F1，2026-09-07）：产物落盘时写 sidecar（<HTML 基名>.deliver.json）。

    命名与形态跟随 confirm sidecar 先例（<名>.confirm.json：同目录、JSON、
    host 标记，_cli_generate.cmd_confirm）：产物 sha256 + 字节数 + spec 哈希 +
    图级 verify 摘要（_verify_checks.check_diagram_level 聚合，规则单点在
    _renderer.schema，不另造摘要口径）。
    写入失败不阻断交付，降级 [warn] 留痕且必须可见（P3-5 措辞收口，防 TTL 机检
    把「观察模式」元描述误报为观察项声明）。
    """
    import yaml
    from _verify_checks import check_diagram_level

    def _artifact(path):
        entry = {"path": os.path.abspath(path)}
        try:
            with open(path, "rb") as f:
                entry["sha256"] = hashlib.sha256(f.read()).hexdigest()
            entry["bytes"] = os.path.getsize(path)
        except OSError as e:
            entry["error"] = str(e)
        return entry

    payload = {
        "delivered_at": datetime.now().isoformat(timespec="seconds"),
        "host": _g._host_label(),
        "client": client or "",
        "spec": _artifact(spec_path) if spec_path else {},
        "artifacts": {
            "html": _artifact(html_output),
            "pptx": _artifact(pptx_output),
        },
        "verify": {"diagram_level": {"diagrams": 0, "errors": [], "warnings": []}},
    }
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        if isinstance(spec, dict):
            payload["verify"]["diagram_level"] = check_diagram_level(spec)
    except Exception as e:
        payload["verify"]["error"] = f"图级摘要不可得: {e}"

    receipt_path = os.path.splitext(html_output)[0] + ".deliver.json"
    try:
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[deliver] receipt: {receipt_path}")
    except OSError as e:
        print(f"[warn] deliver receipt 写入失败（不阻断交付）: {e}")
