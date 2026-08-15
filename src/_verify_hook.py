# -*- coding: utf-8 -*-
"""生成后验证钩子：验证 + 写日志 + 更新 task_history。
验证逻辑全部从 _verify 导入，本文件只负责钩子副作用。"""
import os
import sys
import json
from datetime import datetime

from _paths import LOGS_DIR, TASK_HISTORY


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


def update_task_history(path, ok, file_type):
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


def run_single(path, client_name=None, render_report=None):
    """验证单个文件：L1 格式 + L3 主题覆盖检查（+ 可选渲染报告消费，§6.3）。

    返回 ok（bool）。L3 覆盖检查失败不阻断 ok（只警告），
    但 blocked_coverage 字段记录缺失主题供调用方决策。

    render_report（_renderer.elements.RenderReport，可选，缺省行为不变）：
    - skipped 非空 → 结果 FAIL，原因列出被跳过元素（页面/序号/类型/原因）。
      只有元素级 skip（未知类型等）触发 FAIL；schema 校验进的 warnings
      不影响结果。
    - degraded 非空 → 不降级结果，降级明细并入警告部分打印。
    """
    from _verify import auto_verify
    ok, msg = auto_verify(path, client_name or "")
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
    update_task_history(path, ok, file_type)

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

    # 验证通过后自动入库片段
    if ok:
        _auto_snippet_capture(path, file_type)
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("生成后验证钩子（验证 + 日志 + task_history）")
        print("用法:")
        print("  python _verify_hook.py <file_path>                  验证单个文件")
        print("  python _verify_hook.py --all <pptx> <html> <docx>   验证全部")
        sys.exit(0)

    write_log("=== VERIFY HOOK START ===")
    arg1 = sys.argv[1]

    if arg1 == "--all" and len(sys.argv) >= 4:
        paths = {}
        args = sys.argv[2:]
        for i, key in enumerate(["pptx", "html", "docx"]):
            if i < len(args):
                paths[key] = args[i]
        run_all(paths)
    else:
        run_single(arg1)

    write_log("=== VERIFY HOOK END ===")
