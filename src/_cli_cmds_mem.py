# -*- coding: utf-8 -*-
"""CLI 记忆面命令（T1 拆分自 _cli.py，2026-09-01）。
承载：记忆面·防幻觉 / 状态写入 / 世界书与语义。不改命令行为。"""
import os
import re
import json
import sys

from _session import (
    show_all_clients, list_clients, get_context_path, load_context,
    save_session, parse_args as parse_session_args, onboard_client, recall,
    build_client_graph, query_graph, add_graph_node, add_graph_edge,
)
from _classify import classify, classify_and_extract
from _archive_auto import auto_archive, archive_note, list_pending
from _aliases import normalize_query_with_aliases
from _theme_guard import save_decision, pre_check, resolve_conflict, list_conflicts
from _state import get_state, set_state, reset_state, list_states
from _cli_infra import SCRIPT_DIR, _open_file

def cmd_status(args):
    json_output = getattr(args, 'json', False)
    show_all_clients(json_output=json_output)
    if json_output:
        return
    # M3-F2：状态一览追加各客户阶段（text 分支；JSON 分支已由 show_all_clients 注入 stage）
    try:
        states = list_states()
        if states:
            print("\n阶段状态:")
            for c, s in states.items():
                print(f"  {c:<20} {s.get('stage', 'intake')}")
    except Exception as e:
        print(f"[state] 阶段状态读取跳过: {e}")


def cmd_state(args):
    """M3-F2：展示/设置阶段状态。

    用法：
      python _cli.py state <客户>                # 查看单客户
      python _cli.py state                        # 查看所有客户
      python _cli.py state <客户> --stage html_confirmed
      python _cli.py state <客户> --confirm-html  # 等价 --stage html_confirmed
      python _cli.py state <客户> --reset         # 重置为 intake
    """
    import json as _json

    client = getattr(args, 'client', None) or getattr(args, 'client_name', None)
    stage = getattr(args, 'stage', None)
    confirm_html = getattr(args, 'confirm_html', False)
    reset = getattr(args, 'reset', False)
    json_output = getattr(args, 'json', False)

    # --confirm-html 快捷方式优先级高于 --stage
    if confirm_html:
        stage = "html_confirmed"

    try:
        if client and reset:
            state = reset_state(client)
        elif client and stage:
            state = set_state(client, stage=stage)
        elif client:
            state = get_state(client)
        else:
            states = list_states()
            if json_output:
                print(_json.dumps({
                    "clients": states,
                }, ensure_ascii=False, indent=2))
                return
            if not states:
                print("（暂无阶段状态）")
                return
            for c, s in states.items():
                print(f"{c:<20} {s.get('stage', 'intake')}")
            return

        if json_output:
            print(_json.dumps(state, ensure_ascii=False, indent=2))
            return
        print(f"客户: {state.get('client')}")
        print(f"阶段: {state.get('stage')}")
        print(f"模式: {state.get('mode')}")
        if state.get("taskId"):
            print(f"任务: {state.get('taskId')}")
        review = state.get("lastReview") or {}
        if review.get("verdict"):
            print(f"最近评审: {review.get('verdict')}")
    except ValueError as e:
        print(f"[state] 参数错误: {e}")
        sys.exit(1)


def cmd_pending(args):
    """扫描所有客户 context.md，列出未完成待办。"""
    clients = list_clients()
    if not clients:
        print("暂无客户项目")
        return

    print("未完成待办：")
    found = 0
    for c in clients:
        ctx_path = get_context_path(c)
        if not os.path.exists(ctx_path):
            continue
        with open(ctx_path, "r", encoding="utf-8") as f:
            content = f.read()

        sessions = re.findall(r'## \[(\d{4}-\d{2}-\d{2})\][^\n]*\n(.*?)(?=## \[|\Z)', content, re.DOTALL)
        if not sessions:
            continue
        last_date, last_body = sessions[-1]

        pending_match = re.search(r'### 待办[^\n]*\n(.*?)(?=\n###|\Z)', last_body, re.DOTALL)
        if pending_match:
            pending_text = pending_match.group(1).strip()
            if pending_text and pending_text != "(未记录)":
                for line in pending_text.split('\n'):
                    line = line.strip().lstrip('-').strip()
                    if line:
                        print(f"  [{c}] {last_date}  {line}")
                        found += 1

    if not found:
        print("  （无未完成待办）")


def cmd_load(args):
    load_context(args.client)


def cmd_memory_health(args):
    """记忆证据健康：扫描客户 context.md / decisions.md 的证据与冲突状态（P0 记忆溯源 · T4）。

    输出四组计数：会话/证据段、决策/冲突、待补/待核、refs 状态。
    「没做/读不到」≠「0 条」：refs 不存在报「未摄入或未归档」而非「0 个材料」。
    P3：与 audit --mode memory 共用 _memory_guard.format_report（同源同口径）。
    """
    from _memory_guard import scan_memory_health, format_report
    h = scan_memory_health(args.client)
    print(f"=== 记忆证据健康: {args.client} ===")
    print(format_report(h))


def cmd_save(args):
    kwargs = parse_session_args(args.extra)
    if not any(kwargs.values()):
        result = save_session(args.client)
    else:
        result = save_session(args.client, **kwargs)
    # P0 记忆溯源（T2）：--strict-evidence 阻断时 save_session 返回 False -> 退出码 2（脚本/CI 可判）。
    # 旧版 save_session 隐式返回 None，不会触发此分支（前向兼容接线）。
    if result is False:
        sys.exit(2)
    # 归档目标客户：与 save_session 内部保持一致（别名/近似解析到正式客户名）
    try:
        from _aliases import resolve_client_name
        resolved, _, matched_by = resolve_client_name(args.client)
        if matched_by == 'alias':
            args.client = resolved
    except Exception:
        pass
    # 会话后自动归档（归属在会话内产生，save 时消费；失败不影响保存主流程）
    try:
        result = auto_archive(args.client)
        if result["archived"]:
            print(f"[归档] 自动归档 {len(result['archived'])} 个文件 -> {args.client}/refs/：")
            for fn in result["archived"]:
                print(f"        {fn}")
        if result["pending_review"]:
            print(f"[归档] 以下 {len(result['pending_review'])} 个未归档（会话窗口外或失败），待确认：")
            for fn in result["pending_review"]:
                print(f"        {fn}")
        if result["ignored"]:
            print(f"[归档] 跳过残留类型 {len(result['ignored'])} 个：{', '.join(result['ignored'])}")
        if result["reason"] and not result["archived"]:
            print(f"[归档] {result['reason']}")
    except Exception as e:
        print(f"[归档] 自动归档跳过: {e}")


def cmd_resolve_conflict(args):
    """裁决 decisions.md 同主题矛盾决策（P0 记忆溯源 · T3）。

    --list：只读枚举未决冲突组（主题截断 40 字 + 日期 + 未决块数），不裁决。
    裁决是显式人工动作：--keep old/new 二选一，败方标已废弃、双形态冲突标记
    统一清理，胜方清除「待人工裁决」过期措辞。无可决冲突时明确报错（exit 1），
    不静默成功。
    """
    if getattr(args, "list", False):
        groups = list_conflicts(args.client)
        if not groups:
            print("（无未决冲突）")
            return
        for g in groups:
            shown = g["topic"][:40] + ("…" if len(g["topic"]) > 40 else "")
            dates = "/".join(g["dates"]) if g["dates"] else "(无日期)"
            print(f"- {shown}｜{dates}｜未决 {g['pending_blocks']} 块")
        return
    result = resolve_conflict(args.client, args.topic, args.keep)
    if result.get("resolved"):
        print(f"[裁决] {result['detail']}")
    else:
        print(f"[裁决] {result['detail']}")
        sys.exit(1)


def cmd_classify(args):
    client = getattr(args, 'client', None)
    if getattr(args, 'extract', False):
        result = classify_and_extract(client=client)
        print(f"分类 {result['classified_count']} 个，提取 {result['extracted_count']} 个")
        for w in result.get("warnings", []):
            print(f"[warn] {w}")
    else:
        classify(client=client)


def cmd_archive_note(args):
    """会话内显式登记文件归属（save 自动归档时消费）。"""
    if getattr(args, 'list', False):
        # list_pending() 返回 {"entries": [{file,dest,client,ts,...}, ...]}
        entries = list_pending().get("entries", [])
        if not entries:
            print("（无待归档登记）")
            return
        for e in entries:
            owner = e.get("client", "") if e.get("dest") == "client" else "general"
            print(f"[{owner}]  {e.get('file', '')}  ({e.get('ts', '')})")
        return
    client = args.client
    files = args.files
    if not client:
        print("用法: python _cli.py archive-note <客户> <文件...> 或 --list")
        return
    if not files:
        print("用法: python _cli.py archive-note <客户> <文件...> 或 --list")
        return
    # workspace 版签名: archive_note(filenames, dest="client", client_name="")
    result = archive_note(files, dest="client", client_name=client)
    print(f"已登记 {len(result['added'])} 个文件归属 {client}：")
    for fn in result["added"]:
        print(f"  {fn}")
    if result["ignored"]:
        print(f"忽略无效条目: {result['ignored']}")
    if result["errors"]:
        print(f"登记失败: {result['errors']}")


def cmd_inbox_scan(args):
    """定期 inbox 扫描（Hook + 手动均可调用）。"""
    from _inbox_scan import main_entry
    project_dir = getattr(args, "project_dir", None)
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)
    quiet = getattr(args, "quiet", False)
    emit_json = getattr(args, "emit_json", False)

    report = main_entry(project_dir=project_dir, dry_run=dry_run, force=force)

    if emit_json:
        # Hook 调用：输出 JSON 便于解析
        import json as _json
        print(_json.dumps(report, ensure_ascii=False))
        return

    swept = report.get("swept", [])
    errors = report.get("errors", [])
    todo_path = report.get("todo_path", "")
    migrated = report.get("migrated_uncategorized", 0)

    if quiet:
        # Hook 调用：只输出关键摘要，不啰嗦
        if swept or errors or migrated:
            print(f"[inbox-scan] 收进待定 {len(swept)} 个，异常 {len(errors)} 个")
        return

    # 手动调用：完整输出（main_entry 返回 dict：swept/todo_path/errors/migrated_uncategorized）
    from datetime import datetime
    print(f"[inbox-scan] @ {datetime.now().isoformat(timespec='seconds')}")
    print(f"  收进待定: {len(swept)} 个" + (f"；退役 _uncategorized 迁移 {migrated} 个" if migrated else ""))
    for item in swept:
        print(f"    - {item.get('file', '?')} → {item.get('dest', '?')}（{item.get('reason', '')}）")
    if todo_path:
        print(f"  催办清单: {todo_path}")
    if errors:
        print(f"  错误: {len(errors)}")
        for e in errors:
            print(f"    - {e}")




def cmd_new(args):
    """一键接单：建目录->分类->全文解析->打印素材->提示 AI 起草。"""
    result = onboard_client(
        args.client,
        scene=getattr(args, 'scene', None) or "整体信息化规划",
        html=getattr(args, 'html', False),
        quote=getattr(args, 'quote', False),
    )
    # 建目录失败（client_path 为空）是失败路径，非零退出供脚本/Hook 判断
    if not result.get("client_path"):
        sys.exit(1)
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"[warn] {w}")




def cmd_theme_guard(args):
    """主题守卫：列出/刷新/记录核心约束。

    无 --set：列出当前生效的 permanent 主题（HEAD 注入用）
    有 --set：记录一条 permanent 主题到 decisions.md
    有 --turn：按间隔检查是否需 re-grounding（步数化保真，借鉴 AAMAS 2026）
    """
    # P1-3 C2：标记本会话已执行 theme-guard
    if args.client:
        try:
            from datetime import datetime
            set_state(args.client, theme_guard_at=datetime.now().isoformat(timespec="seconds"))
        except Exception:
            pass

    if args.set_theme:
        # 记录新主题（原 theme-set 功能）
        scope = args.scope
        task_id = args.task_id
        if scope == "task" and not task_id:
            print("错误: scope=task 时必须提供 --task-id")
            sys.exit(1)

        reason_parts = [f"scope={scope}", f"priority={args.priority}"]
        if task_id:
            reason_parts.append(f"task_id={task_id}")

        written = save_decision(
            args.client,
            args.set_theme,
            args.set_theme,
            reason=", ".join(reason_parts),
            alternatives_rejected="",
            level="L4",
            persistence="permanent",
            scope=scope,
            task_id=task_id,
        )
        if written is None:
            print(f"[主题] 保存失败：{args.client} / {args.set_theme} 未写入（保存锁获取失败）")
            sys.exit(1)
        print(f"已记录主题: {args.client} / {args.set_theme} (persistence=permanent, scope={scope})")
        if scope == "client":
            print("  铁律：跨任务跨会话始终生效")
        else:
            print(f"  本次任务全程不变（task_id={task_id}）")
        return

    # 列出当前生效主题（原 theme-list 功能）
    # C-A2：不存在客户此前静默打印「共 0 条」仍 exit 0（V3 漏网；V1/V2 已随 B1#15 修）
    from _paths import CLIENTS_DIR
    if not os.path.isdir(os.path.join(CLIENTS_DIR, args.client)):
        print(f"错误: 客户不存在: {args.client}")
        sys.exit(1)
    result = pre_check(args.client, args.task_id)
    themes = result.get("themes", [])

    # Re-grounding 步数化检查（P0-2，借鉴 AAMAS 2026 O(√T) 漂移研究）
    # 每 REGROUND_INTERVAL 轮触发一次保真刷新提示
    REGROUND_INTERVAL = 10
    need_reground = False
    if args.turn > 0 and args.turn % REGROUND_INTERVAL == 0:
        need_reground = True
        print(f"=== Re-grounding 保真刷新（第 {args.turn} 轮）===")
        print("语义漂移随轮次增长（AAMAS 2026: O(√T)），周期性 re-grounding 保真\n")

    print("=== 核心约束刷新 ===")
    print(f"客户: {args.client} | task_id={args.task_id or '未指定'}")
    print(f"共 {len(themes)} 条主题，其中 {result.get('critical_count', 0)} 条硬约束\n")
    for t in themes:
        persistence = t.get("persistence", "task")
        scope = t.get("scope", "client")
        tag = f"[{persistence.upper()}-{scope.upper()}]"
        if t.get("task_id"):
            tag += f" task={t['task_id']}"
        pri_tag = "🔴" if t.get("priority") == "critical" else "🟡"
        print(f"{pri_tag} {tag} {t['theme']}")
        if t.get("description"):
            print(f"   {t['description'][:120]}")
        print(f"   来源: decisions.md {t.get('source_date', '?')}")
        print()
    # HEAD context 输出
    head = result.get("head_context", "")
    if head:
        print("--- HEAD 注入 ---")
        print(head)
    # TAIL 清单输出（re-grounding 时强调）
    tail = result.get("tail_checklist", "")
    if tail:
        if need_reground:
            print("\n--- TAIL 自检（re-grounding 时逐项确认）---")
        print(tail)
    for w in result.get("warnings", []):
        print(f"[warn] {w}")


def cmd_context_health(args):
    """P1-3：context-health <客户> [--skip ref --reason ...] [--ack]。"""
    from _context_health import run_context_health
    skip = list(getattr(args, "skip", []) or [])
    reasons = {}
    for item in (getattr(args, "reason", []) or []):
        if "=" in item:
            k, _, v = item.partition("=")
            reasons[k.strip()] = v.strip()
    result = run_context_health(
        args.client,
        skip=skip,
        reasons=reasons,
        ack=bool(getattr(args, "ack", False)),
        command="context-health",
        session_id=getattr(args, "session", None),
    )
    print(f"=== context-health: {result.get('client', '')} ===")
    for c in result.get("checks", []):
        mark = "✓" if c.get("status") == "ok" else "⚠"
        print(f"  {mark} {c.get('id')}: {c.get('detail', '')}")
    print(f"  判定: {result.get('verdict')}（累计 WARN {result.get('warn_count', 0)}/3）")
    print(f"  {result.get('message', '')}")
    if result.get("verdict") == "block":
        sys.exit(2)
    sys.exit(0)


def cmd_compact(args):
    """压缩客户历史：合并 context.md + 清理旧 task_history 条目。

    --keep N: 保留最近 N 条 task_history 记录（默认 10）
    --keep-sessions N: context.md 保留最近 N 次完整会话（默认 1，传 0 跳过 context.md 压缩）
    """
    client = args.client
    keep = args.keep
    keep_sessions = getattr(args, 'keep_sessions', 1)

    from _paths import CLIENTS_DIR, LOGS_DIR, client_dir
    clients_dir = CLIENTS_DIR
    # #48/D2：按名解析支持 _internal/ 内部账本目录回退
    client_path = client_dir(client, clients_dir=clients_dir)
    if not os.path.exists(client_path):
        print(f"客户 '{client}' 不存在")
        sys.exit(1)

    # 1. 压缩 task_history.json（保留最近 N 条）
    # P1-15（D1）：task_history 全客户共享，压缩重排与 save/verify_hook 并发需全局锁
    history_path = os.path.join(LOGS_DIR, "task_history.json")
    if os.path.exists(history_path):
        from _save_lock import acquire_save_lock, release_save_lock
        th_fd = acquire_save_lock(LOGS_DIR, lock_name=".task_history.lock")
        if th_fd is None:
            print("[锁] task_history 全局锁获取失败（30s 超时），压缩中止（防并发写坏）")
            sys.exit(1)
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            # 兼容旧版 dict 格式 {"tasks": [...]}（与 _verify_hook.update_task_history 同一兼容层）
            if isinstance(history, dict):
                history = history.get("tasks", [])

            # P3：project 字段可能显式为 null（旧数据/半截写入），.get 默认值不兜
            # 显式 None，直接 .replace 会 AttributeError；非 dict 条目一并归入“其他”保留
            def _is_client_record(r):
                if not isinstance(r, dict):
                    return False
                project = r.get("project")
                if not isinstance(project, str):
                    project = ""
                return project.replace("client:", "") == client or r.get("client") == client

            client_records = [r for r in history if _is_client_record(r)]
            if len(client_records) > keep:
                drop = client_records[:-keep]
                removed = len(drop)
                # P3：保持全局写入时序——仅原位剔除本客户被删旧条目；
                # 旧写法 other_records + kept 会把保留条目搬到列表尾部，重排全局时序
                drop_ids = {id(r) for r in drop}
                history[:] = [r for r in history if id(r) not in drop_ids]
                import shutil
                shutil.copy2(history_path, history_path + ".bak")  # 截断前留底
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                print(f"已压缩 {client} 的 task_history: 删除 {removed} 条旧记录，"
                      f"保留 {len(client_records) - removed} 条")
            else:
                print(f"{client} 的 task_history 仅 {len(client_records)} 条，无需压缩")
        finally:
            release_save_lock(LOGS_DIR, th_fd, lock_name=".task_history.lock")

    # 2. 压缩 context.md（调用 _context.compact，修复既有 bug：原代码只打印警告不调用）
    if keep_sessions > 0:
        from _context import compact as _compact_context
        print(f"\n[context] 压缩 {client} 的 context.md（保留最近 {keep_sessions} 次会话）...")
        _compact_context(client, keep_last=keep_sessions)
    else:
        print("\n[context] --keep-sessions=0，跳过 context.md 压缩")

    print(f"\n压缩完成: {client}")




def cmd_graph_build(args):
    """构建/更新版本链索引 client_graph.json（人工/调试）。世界书请用 worldbook-build。"""
    graph = build_client_graph(args.client)
    print(f"[graph-build] {args.client}: {len(graph['nodes'])} 节点, {len(graph['edges'])} 边")
    if graph.get("index_summary"):
        print(f"  摘要: {graph['index_summary']}")


def cmd_worldbook_build(args):
    """直读真源生成/更新世界书 client_index.md（R1-1，不经过 client_graph.json）。"""
    from _worldbook import build_worldbook
    md = build_worldbook(args.client)
    print(f"[worldbook-build] {args.client}: 已生成 client_index.md（{len(md)} 字符）")


def cmd_graph_query(args):
    """人工/调试：查询版本链索引（client_graph.json）的节点和边。

    --node / --edges 是精确 ID 语义，始终原样传给 query_graph，不做别名展开；
    自由文本使用 --query，会先 normalize_query_with_aliases 再搜索节点标题/摘要。
    """
    query = getattr(args, "query", None)
    if query:
        if not getattr(args, "no_alias", False):
            query = normalize_query_with_aliases(
                query, client_name=args.client)
        from _graph import search_graph_nodes
        result = search_graph_nodes(args.client, query)
    else:
        result = query_graph(args.client, node_id=args.node,
                             node_type=args.type, edges_of=args.edges)
    if getattr(args, 'json', False):
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result.get("error"):
        print(f"[graph-query] 错误: {result['error']}")
        sys.exit(1)
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    print(f"[graph-query] {args.client}: {len(nodes)} 节点, {len(edges)} 边")
    for n in nodes[:20]:
        print(f"  {n['id']} [{n['type']}] {n['title'][:50]}")
    if len(nodes) > 20:
        print(f"  ...还有 {len(nodes)-20} 个")
    for e in edges[:10]:
        print(f"  {e['from']} --{e['type']}--> {e['to']}")


def cmd_graph_add(args):
    """人工调试：手动添加版本链索引节点（client_graph.json）。"""
    result = add_graph_node(args.client, node_type=args.type,
                            title=args.title, summary=args.summary)
    node = result["node"]
    print(f"[graph-add] 添加版本链索引节点: {node['id']} [{node['type']}] {node['title']}")


def cmd_graph_link(args):
    """人工调试：手动添加版本链索引边。"""
    result = add_graph_edge(args.client, from_id=args.from_id,
                           to_id=args.to_id, edge_type=args.type,
                           note=args.note)
    if result.get("error"):
        print(f"[graph-link] 错误: {result['error']}")
        sys.exit(1)
    edge = result["edge"]
    print(f"[graph-link] 添加边: {edge['from']} --{edge['type']}--> {edge['to']}")


def cmd_semantic_catalog(args):
    """校验能力目录 JSON。"""
    from _semantic_catalog import check_catalog, DEFAULT_CATALOG_PATH
    path = getattr(args, "path", None) or DEFAULT_CATALOG_PATH
    result = check_catalog(path)
    print(f"[semantic-catalog] {path}")
    if result["valid"]:
        print("  valid: True, 0 错误")
    else:
        print(f"  valid: False, {len(result['errors'])} 错误")
        for e in result["errors"]:
            print(f"  - {e}")
        sys.exit(1)




def cmd_recall(args):
    # --no-client-filter 显式禁用；--client-filter 显式启用；默认 None（由 recall 自动决策）
    if getattr(args, 'no_client_filter', False):
        client_filter = False
    elif getattr(args, 'client_filter', None):
        client_filter = True
    else:
        client_filter = None
    json_output = getattr(args, 'json', False)
    results = recall(" ".join(args.keywords),
                     force_keyword=args.keyword,
                     client_name=args.client,
                     rerank=args.rerank,
                     use_embedding=not args.no_embedding,
                     client_filter=client_filter,
                     permanent_only=getattr(args, 'permanent_only', False),
                     use_aliases=not getattr(args, 'no_alias', False),
                     use_query_rewrite=not getattr(args, 'no_rewrite', False),
                     return_results=json_output)
    if json_output and results is not None:
        import json as _json
        print(_json.dumps(results, ensure_ascii=False, indent=2))


def cmd_recall_eval(args):
    """召回质量评估：跑 golden query 评估集，输出三链路 Hit@1/Hit@3/MRR 指标。

    L5 级确定性评估器，只读 recall() 结果做判定，不改算法。
    实施依据：docs/dev_plan_recall_eval_2026-07-19.md
    """
    from _recall_eval import (
        load_eval_set, run_eval, save_baseline, compare_baseline,
        estimate_api_calls, DEFAULT_EVAL_SET_PATH, DEFAULT_BASELINE_PATH,
    )

    eval_path = args.file or DEFAULT_EVAL_SET_PATH
    try:
        eval_set = load_eval_set(eval_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"[recall-eval] 评估集加载失败: {e}")
        sys.exit(1)
    if not eval_set:
        print(f"[recall-eval] 评估集为空: {eval_path}")
        sys.exit(1)

    # R3-3 --ablation：跑 BM25-only 别名开/关两组（alias_on/alias_off）。
    # 图扩展已移除（M2-R2），use_graph_expansion 已于 2026-09-07 退役删除（L6 清偿）。
    # --no-alias 在 ablation 模式下无意义，固定忽略：ablation 必须同时产出
    # alias_on/alias_off 两组对比数据。
    if args.ablation:
        if getattr(args, "no_alias", False):
            print("[recall-eval] 忽略 --no-alias：--ablation 固定执行 alias_on/alias_off 两组")
        if args.limit:
            eval_set = eval_set[: args.limit]
        reports = {}
        print("[recall-eval] 运行别名 ablation（BM25-only，离线）")
        for label, use_aliases in (
            ("alias_on", True),
            ("alias_off", False),
        ):
            print(f"\n=== Ablation: {label} ===")
            rep = run_eval(
                eval_set,
                rerank=False,
                use_embedding=False,
                use_aliases=use_aliases,
                use_query_rewrite=False,  # 别名 ablation 保持 BM25-only 离线（I-2）
            )
            rep["ablation_mode"] = label
            reports[label] = rep
            _print_chain_report(rep)
        if args.json:
            report_json = {"ablation": reports}
            os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(report_json, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n[recall-eval] Ablation 结构化报告: {args.json}")
        return

    # Gate 1（I-2）：A0（关查询改写）vs A1（开查询改写）配对对比 + Wilcoxon
    if args.rewrite_ablation:
        if args.limit:
            eval_set = eval_set[: args.limit]
        reps = {}
        per_query = {}
        for label, uqr in (("A0_no_rewrite", False), ("A1_rewrite", True)):
            print(f"\n=== Gate1 {label} ===")
            rep = run_eval(
                eval_set,
                rerank=False,
                use_embedding=True,
                use_aliases=not args.no_alias,
                use_query_rewrite=uqr,
            )
            reps[label] = rep
            per_query[label] = {e["id"]: e for e in rep["per_query"]}
            _print_chain_report(rep)

        from _eval.stats import paired_bootstrap_ci, wilcoxon_signed_rank_pvalue
        ids = [e["id"] for e in eval_set]
        pairs = []
        for qid in ids:
            a0 = per_query["A0_no_rewrite"].get(qid)
            a1 = per_query["A1_rewrite"].get(qid)
            if not a0 or not a1:
                continue
            a0_hit = 1 if a0.get("hit_rank") == 0 and not a0.get("is_negative") else 0
            a1_hit = 1 if a1.get("hit_rank") == 0 and not a1.get("is_negative") else 0
            pairs.append((a1_hit, a0_hit))

        n = len(pairs) or 1
        h1_a0 = sum(b for _, b in pairs) / n
        h1_a1 = sum(a for a, _ in pairs) / n
        rel = (h1_a1 - h1_a0) / h1_a0 if h1_a0 > 0 else float("nan")
        ci_low, ci_high, mean_diff = paired_bootstrap_ci(pairs)
        p = wilcoxon_signed_rank_pvalue(
            [a for a, _ in pairs], [b for _, b in pairs])
        passed = bool(rel >= 0.15 and p < 0.05) if rel == rel else False

        print("\n=== Gate 1: A0 vs A1（查询改写）===")
        print(f"  Hit@1 A0={h1_a0:.4f}  A1={h1_a1:.4f}  相对提升={rel*100:.1f}%" if rel == rel
              else "  Hit@1 A0=0（无正样本命中，无法算相对提升）")
        print(f"  Wilcoxon p={p:.4f}  配对 diff 均值={mean_diff:+.4f}  "
              f"95% CI=[{ci_low:+.4f},{ci_high:+.4f}]")
        print(f"  判定（相对提升≥15% 且 p<0.05）: {'PASS' if passed else 'FAIL'}")

        gate = {
            "A0": reps["A0_no_rewrite"]["metrics"],
            "A1": reps["A1_rewrite"]["metrics"],
            "hit_at_1_relative_improvement": round(rel, 4) if rel == rel else None,
            "wilcoxon_p": round(p, 4),
            "paired_mean_diff": round(mean_diff, 4),
            "bootstrap_ci": [round(ci_low, 4), round(ci_high, 4)],
            "passed": passed,
        }
        if args.json:
            os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(gate, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n[recall-eval] Gate1 报告: {args.json}")
        return

    # 三链路：默认 rrf 必跑；--rerank / --no-embedding 各加一条
    chains_to_run = [("rrf", False, True)]  # (chain_name, rerank, use_embedding)
    if args.rerank:
        chains_to_run.append(("rerank", True, True))
    if args.no_embedding:
        chains_to_run.append(("bm25_only", False, False))

    # 成本守门：预估云端调用数 >50 且无 --yes -> exit 1
    total_calls = sum(
        estimate_api_calls(len(eval_set), rerank=r, use_embedding=ue)
        for _, r, ue in chains_to_run
    )
    if total_calls > 50 and not args.yes:
        print(
            f"[recall-eval] 预估 {total_calls} 次云端调用（embedding+rerank），"
            f">50 次需 --yes 确认"
        )
        sys.exit(1)

    if args.limit:
        eval_set = eval_set[: args.limit]

    reports = {}
    for chain_name, rerank, use_embedding in chains_to_run:
        print(f"\n=== 链路: {chain_name} ===")
        rep = run_eval(
            eval_set,
            rerank=rerank,
            use_embedding=use_embedding,
            use_aliases=not args.no_alias,
        )
        reports[chain_name] = rep
        _print_chain_report(rep)

    # --save-baseline 落盘
    if args.save_baseline:
        config_snapshot = (
            reports["rrf"]["config"]
            if "rrf" in reports
            else next(iter(reports.values()))["config"]
        )
        chains_summary = {name: rep["metrics"] for name, rep in reports.items()}
        save_baseline(
            {"config": config_snapshot, "chains": chains_summary},
            path=DEFAULT_BASELINE_PATH,
        )
        print(f"\n[recall-eval] baseline 已落盘: {DEFAULT_BASELINE_PATH}")

    # --gate 回归门禁
    if args.gate:
        try:
            with open(args.gate, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[recall-eval] baseline 读取失败: {e}")
            sys.exit(1)
        # config 一致性告警（不阻断）
        current_config = next(iter(reports.values()))["config"]
        if baseline.get("config") and baseline["config"] != current_config:
            print(
                "[recall-eval] ⚠️ 警告: 当前 recall_config.yml 与 baseline 不一致，"
                "指标差异可能来自调参而非回归"
            )
        current_chains = {name: rep["metrics"] for name, rep in reports.items()}
        passed, diffs = compare_baseline(current_chains, baseline)
        print("\n=== Gate 对比 ===")
        for d in diffs:
            mark = "PASS" if d["passed"] else "FAIL"
            print(
                f"  [{mark}] {d['chain']}.{d['metric']}: "
                f"baseline={d['baseline']} current={d['current']} "
                f"delta={d['delta']:+} tol={d['tolerance']}"
            )
        if not passed:
            print("\n[recall-eval] 回归门禁 FAIL")
            sys.exit(1)
        print("\n[recall-eval] 回归门禁 PASS")

    # --json 结构化报告落盘
    if args.json:
        report_json = {"chains": reports}
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report_json, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n[recall-eval] 结构化报告: {args.json}")


def _print_chain_report(report):
    """打印单链路评估报告。"""
    m = report["metrics"]
    print(f"  正样本: {m['total']} 条 / 负样本: {m['neg_total']} 条")
    print(f"  Hit@1: {m['hit_at_1']:.4f}")
    print(f"  Hit@3: {m['hit_at_3']:.4f}  (核心指标)")
    print(f"  MRR:   {m['mrr']:.4f}")
    print(
        f"  负样本: no_hit 通过 {m['neg_pass_no_hit']} 条, "
        f"fallback 通过 {m['neg_pass_fallback']} 条, "
        f"不通过 {m['neg_fail']} 条"
    )
    if m["misses"]:
        print(f"  Miss ({len(m['misses'])} 条):")
        for miss in m["misses"]:
            err = f" [error: {miss.get('error')}]" if miss.get("error") else ""
            top3 = miss.get("top3_paths", [])
            print(f"    {miss['id']}: {miss['query'][:40]} -> top3: {top3}{err}")




def cmd_me(args):
    profile_path = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")
    if not os.path.exists(profile_path):
        print(f"profile.md 不存在: {profile_path}")
        sys.exit(1)
    if args.edit:
        _open_file(profile_path)
    else:
        with open(profile_path, "r", encoding="utf-8") as f:
            print(f.read())

