# -*- coding: utf-8 -*-
"""上下文召回一期新增 CLI 命令（T6）。

最小可用版本：query-rewrite / fact-guard / guard-audit / bm25-rebuild /
eval-run / eval-report。
"""
import json
import os
import sys


def cmd_query_rewrite(args):
    """query-rewrite：测试查询改写模块。"""
    from _query_rewrite import rewrite_query
    query = args.query or "售前方案 报价 客户A"
    result = rewrite_query(query, client=args.client, config=None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"原查询: {query}")
        print(f"改写后: {result['rewritten']}")
        print(f"置信度: {result['confidence']}")
        for change in result["changes"]:
            print(f"  - {change}")
        if result["degraded"]:
            print(f"降级: {result['degraded']}")


def cmd_fact_guard(args):
    """fact-guard：对文本做事实一致性检查。"""
    from _fact_guard import guard_check
    text = args.text or ""
    if not text:
        print("[fact-guard] 请用 --text 提供待检查文本")
        sys.exit(1)
    result = guard_check(text, client=args.client)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"数字: {result['numbers']}")
        print(f"归一化数字: {result['normalized_numbers']}")
        print(f"实体命中: {result['entities']}")
        print(f"违规: {result['violations']}")


def cmd_guard_audit(args):
    """guard-audit：查看 fact_guard 隔离区队列。"""
    from _fact_guard import list_guard_queue
    items = list_guard_queue()
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print(f"隔离区队列: {len(items)} 条")
        for item in items[-20:]:
            print(json.dumps(item, ensure_ascii=False))


def cmd_bm25_rebuild(args):
    """bm25-rebuild：重建 BM25 索引。"""
    from _onboard import rebuild_bm25_index_all
    result = rebuild_bm25_index_all()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"BM25 重建完成，索引 {result.get('indexed_count', 0)} 块")
        for w in result.get("warnings", []):
            print(f"[warn] {w}")


def cmd_eval_run(args):
    """eval-run：跑评估集（T6 最小版，完整统计见 T8）。"""
    from _recall_eval import load_eval_set, run_eval, DEFAULT_EVAL_SET_PATH
    eval_path = args.file or DEFAULT_EVAL_SET_PATH
    try:
        eval_set = load_eval_set(eval_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"[eval-run] 评估集加载失败: {e}")
        sys.exit(1)
    if args.limit:
        eval_set = eval_set[: args.limit]
    report = run_eval(
        eval_set,
        rerank=False,
        use_embedding=not args.no_embedding,
        use_aliases=not args.no_alias,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"eval-run 完成，评估 {len(eval_set)} 条；报告键: {list(report.keys())}")


def cmd_eval_report(args):
    """eval-report：输出最近一次 eval-run 报告（T6 最小版）。"""
    report_path = args.report
    if not report_path or not os.path.exists(report_path):
        print("[eval-report] 请用 --report 指定 eval-run 生成的 JSON 报告路径")
        sys.exit(1)
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))