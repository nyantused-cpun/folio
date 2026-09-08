# -*- coding: utf-8 -*-
"""生成后验证钩子：验证 + 写日志 + 更新 task_history。
验证逻辑全部从 _verify 导入，本文件只负责钩子副作用。"""
import os
import sys
import json
from datetime import datetime

from _paths import CLIENTS_DIR, LOGS_DIR, TASK_HISTORY


def _now():
    return datetime.now().strftime("%H:%M:%S")


def _date():
    return datetime.now().strftime("%Y-%m-%d")


def _log_file():
    os.makedirs(LOGS_DIR, exist_ok=True)
    return os.path.join(LOGS_DIR, f"verify_LOG_{_date()}.log")


def write_log(message):
    with open(_log_file(), "a", encoding="utf-8") as f:
        f.write(f"[{_now()}] {message}\n")


def update_task_history(path, ok, file_type, client_name=None):
    """更新 task_history：客户锁（F0-8）+ 全局 task_history 锁（P1-15/D1）。

    client_name 提供时按客户目录取客户锁；task_history 本身是全客户共享文件，
    一律另取全局锁 .task_history.lock（save_session 同款），锁序恒为
    客户锁→全局锁，防 verify × save 跨客户并发写坏 JSON。
    """
    lock_dir = None
    lock_fd = None
    th_fd = None
    if client_name:
        # #48/D2：按名解析支持 _internal/ 内部账本目录回退（锁位与 save_session 同址，
        # 避免为已迁移账本在顶层复活同名目录）
        from _paths import client_dir as _resolve_client_dir
        lock_dir = _resolve_client_dir(client_name, clients_dir=CLIENTS_DIR)
        if not os.path.isdir(lock_dir):
            os.makedirs(lock_dir, exist_ok=True)
        from _save_lock import acquire_save_lock, release_save_lock
        lock_fd = acquire_save_lock(lock_dir)
        if lock_fd is None:
            write_log(f"TASK_HISTORY 获取保存锁失败: {lock_dir}")
            # P3 留痕：静默放弃会让 audit 溯源把本文件误报为「绕过 CLI」直写
            print(f"[warn] 保存锁获取失败（{lock_dir}），本次 verify 结果未写入 task_history；"
                  "audit 溯源可能将此文件误报为绕过 CLI", file=sys.stderr)
            return
    from _save_lock import acquire_save_lock, release_save_lock
    th_fd = acquire_save_lock(LOGS_DIR, lock_name=".task_history.lock")
    if th_fd is None:
        write_log("TASK_HISTORY 全局锁获取失败（30s 超时），跳过更新（防并发写坏）")
        # P3 留痕：同上，降级可以，但必须让调用方看得见
        print("[warn] task_history 全局锁获取失败（30s 超时），本次 verify 结果未写入 task_history；"
              "audit 溯源可能将此文件误报为绕过 CLI", file=sys.stderr)
        if lock_fd is not None:
            release_save_lock(lock_dir, lock_fd)
        return
    try:
        if not os.path.exists(TASK_HISTORY):
            write_log("TASK_HISTORY 不存在，跳过更新")
            return
        try:
            with open(TASK_HISTORY, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            write_log("TASK_HISTORY 解析失败，跳过更新")
            return

        # P1-2：兼容 dict 格式（旧版 {"tasks": [...]}），避免 AttributeError
        if isinstance(history, dict):
            if isinstance(history.get("tasks"), list):
                history = history["tasks"]
            else:
                write_log("TASK_HISTORY 格式无法识别（dict 无 tasks 字段），跳过更新")
                return

        if not isinstance(history, list):
            return

        if not history:
            history.append({"date": _date(), "project": "verify-only", "verify": {}})

        latest = history[-1]
        if not isinstance(latest, dict):
            write_log("TASK_HISTORY 最后一条记录非 dict，跳过更新")
            return
        verify_status = latest.get("verify", {})
        norm_path = os.path.normcase(os.path.normpath(path))
        verify_status[norm_path] = {"type": file_type, "ok": ok, "date": _date()}
        latest["verify"] = verify_status

        with open(TASK_HISTORY, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        write_log(f"TASK_HISTORY 已更新: {path} -> {'PASS' if ok else 'FAIL'}")
    finally:
        if lock_fd is not None:
            release_save_lock(lock_dir, lock_fd)
        if th_fd is not None:
            release_save_lock(LOGS_DIR, th_fd, lock_name=".task_history.lock")


def _print_result(ok, msg, file_type):
    if ok:
        print(f"  PASS [{file_type.upper()}]  {msg}")
    else:
        print(f"  FAIL [{file_type.upper()}]  {msg}")


def _extract_div_blocks(html_content, class_keyword):
    """P1-3：用栈匹配提取含指定 class 关键词的 div 块，正确处理嵌套 div。

    原 re.findall(r'<div[^>]*class="[^"]*card[^"]*"[^>]*>(.*?)</div>', ...)
    遇到内部 </div> 就截断，导致片段不完整。本函数用计数器匹配配对的 </div>。
    """
    import re
    results = []
    # 找所有带 class 含关键词的 <div ...> 起始位置
    pattern = re.compile(r'<div[^>]*class="[^"]*' + re.escape(class_keyword) + r'[^"]*"[^>]*>', re.IGNORECASE)
    open_tag_re = re.compile(r'<div\b[^>]*>', re.IGNORECASE)
    close_tag_re = re.compile(r'</div\s*>', re.IGNORECASE)

    for m in pattern.finditer(html_content):
        start = m.end()
        depth = 1
        pos = start
        while depth > 0:
            next_open = open_tag_re.search(html_content, pos)
            next_close = close_tag_re.search(html_content, pos)
            if not next_close:
                break
            if next_open and next_open.start() < next_close.start():
                depth += 1
                pos = next_open.end()
            else:
                depth -= 1
                pos = next_close.end()
                if depth == 0:
                    results.append(html_content[start:next_close.start()])
                    break
    return results


def _auto_snippet_capture(path, file_type):
    """验证通过后，自动把 HTML 中的卡片/图表片段入库。

    策略：只对 HTML 文件做，提取带 class 含 card/chart/section 的片段。
    失败不影响主流程。
    """
    if file_type != "html":
        return
    try:
        from _snippet import save_snippet
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 简单提取：找 <section> / class*="card" / class*="chart" 的块
        import re
        # 提取 section 块
        sections = re.findall(r'<section[^>]*>(.*?)</section>', content, re.DOTALL)
        # P1-3：提取 card 块时用栈匹配嵌套 div，避免 (.*?) 遇到内部 </div> 就截断
        cards = _extract_div_blocks(content, 'card')

        captured = 0
        base_name = os.path.splitext(os.path.basename(path))[0]
        for i, block in enumerate(sections[:3] + cards[:3]):
            block = block.strip()
            if len(block) < 50:
                continue
            snippet_name = f"{base_name}_片段{i+1}"
            try:
                save_snippet(
                    snippet_name, "card",
                    f"<div>{block}</div>",
                    source=path,
                    tags=["auto-capture"],
                    client=""
                )
                captured += 1
            except Exception:
                pass
        if captured:
            write_log(f"片段自动入库: {captured} 个 (from {path})")
            print(f"  [片段入库] 自动保存 {captured} 个片段")
    except Exception as e:
        write_log(f"片段自动入库失败: {e}")


def run_single(path, client_name=None, render_report=None, return_blocked=False,
               density_gate="verify"):
    """验证单个文件：L1 格式 + L3 主题覆盖检查（+ 可选渲染报告消费，§6.3）。

    density_gate（S8-C）：密度检查门档（"verify" 单视口 / "deliver" 全视口+截图
    存档），透传 auto_verify -> verify_html -> check_density_html；默认 verify
    保持独立 html-build/verify 命令现状行为，仅 deliver 编排传 "deliver"。

    返回 ok（bool）。L3 覆盖检查失败不阻断 ok（只警告），
    但 blocked_coverage 字段记录缺失主题供调用方决策。

    return_blocked=True 时返回 (ok, blocked_coverage)：blocked_coverage 是
    缺失主题列表 + 渲染降级明细，兼容旧调用方（默认仍返回 bool）。

    render_report（_renderer.elements.RenderReport，可选，缺省行为不变）：
    - skipped 非空 → 结果 FAIL，原因列出被跳过元素（页面/序号/类型/原因）。
      只有元素级 skip（未知类型等）触发 FAIL；schema 校验进的 warnings
      不影响结果。
    - degraded 非空 → 不降级结果，降级明细并入警告部分打印，同时计入
      blocked_coverage。
    """
    from _verify import auto_verify
    ok, msg = auto_verify(path, client_name or "", density_gate=density_gate)
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    file_type = "html" if ext in ("html", "htm") else ext

    # §6.3：消费渲染报告——元素被跳过即产出不完整，verify 判 FAIL
    degraded = getattr(render_report, "degraded", None) or []
    skipped = getattr(render_report, "skipped", None) or []
    if skipped:
        detail = "; ".join(
            f"{s.get('page')} elements[{s.get('index')}] "
            f"{s.get('type')}: {s.get('reason')}" for s in skipped)
        ok = False
        msg = f"{msg}；渲染报告 {len(skipped)} 个元素被跳过: {detail}"

    write_log(f"{'PASS' if ok else 'FAIL'} {file_type} {path}: {msg}")
    _print_result(ok, msg, file_type)
    for item in degraded:
        print(f"  [warn] [降级] {item.get('page')} elements[{item.get('index')}] "
              f"{item.get('type')} -> {item.get('target')}: {item.get('message')}")
    update_task_history(path, ok, file_type, client_name=client_name)

    # L3 主题覆盖检查（仅 HTML，且有客户名时）
    coverage_missing = []
    if ok and client_name and file_type == "html":
        try:
            from _theme_guard import pre_check as theme_pre_check, check_coverage
            tg = theme_pre_check(client_name)
            themes = tg.get("themes", [])
            if themes:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                result = check_coverage(text, themes)
                coverage_missing = result.get("missing", [])
                for m in coverage_missing:
                    print(f"  [warn] [L3] 未覆盖: {m['theme']}")
                if result.get("covered"):
                    print(f"  [L3] 已覆盖 {len(result['covered'])} 个核心诉求")
        except Exception as e:
            write_log(f"L3 覆盖检查失败: {e}")

    # F0-6：blocked_coverage = 缺失主题 + 渲染降级明细（供调用方决策）
    blocked_coverage = list(coverage_missing)
    for item in degraded:
        blocked_coverage.append(item)

    # 验证通过后自动入库片段
    if ok:
        _auto_snippet_capture(path, file_type)

    # S9-2d：crafted×无 review PASS 记录 → warn 提示（独立 build 不阻断产出，
    # 阻断交付在 _review_gate.deliver_gate / cmd_deliver --resume；机制互补非债）
    if ok and file_type == "html":
        from _review_gate import warn_crafted_without_review
        warn_crafted_without_review(path)

    if return_blocked:
        return ok, blocked_coverage
    return ok


def run_all(paths_dict):
    from _verify import verify_all
    all_ok, results = verify_all(paths_dict)
    passed = 0
    failed = 0
    for key, r in results.items():
        write_log(f"{'PASS' if r['ok'] else 'FAIL'} {key} {r['path']}: {r['msg']}")
        _print_result(r["ok"], r["msg"], key)
        update_task_history(r["path"], r["ok"], key)
        if r["ok"]:
            passed += 1
        else:
            failed += 1
    summary = f"合计: {passed} 通过, {failed} 失败"
    print(f"  {summary}")
    write_log(summary)
    return all_ok


def _main(argv):
    """CLI 入口：按验证结果透传 exit code（P3：曾忽略返回值恒 exit 0，
    verify FAIL 被包装成成功，调用方无从感知）。"""
    if len(argv) < 2:
        print("生成后验证钩子（验证 + 日志 + task_history）")
        print("用法:")
        print("  python _verify_hook.py <file_path>                  验证单个文件")
        print("  python _verify_hook.py --all <pptx> <html> <docx>   验证全部")
        return 0

    write_log("=== VERIFY HOOK START ===")
    arg1 = argv[1]

    if arg1 == "--all" and len(argv) >= 4:
        paths = {}
        args = argv[2:]
        for i, key in enumerate(["pptx", "html", "docx"]):
            if i < len(args):
                paths[key] = args[i]
        ok = run_all(paths)
    else:
        ok = run_single(arg1)

    write_log("=== VERIFY HOOK END ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
