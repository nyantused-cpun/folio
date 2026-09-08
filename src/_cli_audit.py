# -*- coding: utf-8 -*-
"""CLI 审计模块：config/runtime/theme 审计 + 引用审查 + 主题覆盖检查。"""
import os
import sys

from _cli_infra import SCRIPT_DIR
from _paths import LOGS_DIR, REVIEW_LOG as _REVIEW_LOG, list_client_dirs, rel_to_script

from _cli_audit_p0 import (
    _audit_p0_required_skills, _audit_p0_engineering_wording,
    _audit_p0_route_table, _audit_p0_preset_sentinel, _audit_p0_spec_guide,
    _audit_p0_skill_broken_links, _audit_p0_delivery_decision,
    _audit_p0_core_command_coverage, _audit_p0_file_size_ratchet,
    _audit_p0_skills_compliance,
    _audit_knowledge_terms_drift, _audit_knowledge_anchor_integrity,
)



def cmd_audit(args):
    """审计：检查配置一致性 / 运行时功能 / 对话行为 / 主题格式。

    --config: 静态检查（入口 MD / CLI 命令数 / _renderer 阻断 / persistence 格式）
    --runtime: 动态功能测试（recall / import 阻断 / spec 阻断 / 路径阻断）
    --behavior: 对话行为统计（task_history 行为台账，只报不判恒不 FAIL；C-A1 最小实现）
    --theme <客户>: 检查 decisions.md persistence 字段格式
    --memory <客户>: 记忆证据健康（待补/待核/冲突未决/refs 状态，警告级）
    --mode worldbook [--client <客户>]: 世界书/版本链新鲜度（R1-5，警告级）
    --mode keynote [--client <客户>]: keynote hash 对账（I-3 A6，警告级）
    --mode knowledge: 知识层检查（C2 术语漂移 + S11 锚点完整性，警告级只报不判）
    --mode debt: 历史债对账（outputs_index 悬空/空壳元数据 + 重复决策 + 残留，只报不判）
    --mode drift: 代际漂移+成色（文件覆盖矩阵 + meta_version + 结构代际，只报不判）
    --mode cost: 观测成本体检（telemetry 体量/LLM 用量/probe 缓存，恒不 FAIL）
    --all: 全部检查（含 track 轨一致性，S9 2b；详见 _cli_audit_track 模块 docstring）
    """
    mode = args.mode or "config"
    if mode == "all":
        modes = ["config", "runtime", "theme", "memory", "review", "worldbook", "context", "keynote", "knowledge",
                 "debt", "drift", "cost", "track"]
    else:
        modes = [mode]

    all_ok = True
    for m in modes:
        print(f"\n{'='*60}")
        print(f"  审计模式: {m}")
        print(f"{'='*60}\n")
        if m == "config":
            ok = _audit_config()
        elif m == "runtime":
            ok = _audit_runtime()
        elif m == "theme":
            ok = _audit_theme(getattr(args, 'client', None))
        elif m == "memory":
            ok = _audit_memory(getattr(args, 'client', None))
        elif m == "review":
            ok = _audit_review_log(getattr(args, 'client', None))
        elif m == "worldbook":
            ok = _audit_worldbook_freshness(getattr(args, 'client', None))
        elif m == "context":
            ok = _audit_context_health(getattr(args, 'client', None))
        elif m == "keynote":
            ok = _audit_keynote_hash(getattr(args, 'client', None))
        elif m == "knowledge":
            ok = _audit_knowledge_terms_drift()
            ok = _audit_knowledge_anchor_integrity() and ok
        elif m == "debt":
            ok = _audit_debt(getattr(args, 'client', None))
        elif m == "drift":
            ok = _audit_drift(getattr(args, 'client', None))
        elif m == "cost":
            ok = _audit_cost()
        elif m == "track":
            ok = _audit_track()
        elif m == "behavior":
            ok = _audit_behavior()
        else:
            print(f"未知审计模式: {m}")
            continue
        if not ok:
            all_ok = False

    # 防再生 audit lint（Step 4 后挂入；all 与 config 都跑）
    if "config" in modes or "all" in modes:
        if not _audit_anti_regeneration():
            all_ok = False

    # F0-12：报告本月累计 usage（仅报告，不影响 pass/fail）
    try:
        from datetime import datetime
        from _cloud_llm import get_usage_summary
        month = datetime.now().strftime("%Y-%m")
        usage = get_usage_summary(month=month)
        print(f"\n本月 LLM 用量：{usage.get('total_calls', 0)} 次 / "
              f"{usage.get('total_tokens', 0)} tokens")
        for p, s in usage.get("by_provider", {}).items():
            print(f"  - {p}: {s.get('calls', 0)} 次 / {s.get('tokens', 0)} tokens")
    except Exception as e:
        print(f"[warn] 本月 LLM 用量读取失败: {e}")

    # M3-F3-5：打印 DSH sessionStats 本地落盘汇总（folio-stats-audit 写入；仅报告）
    _print_session_stats_summary()

    print(f"\n{'='*60}")
    print(f"  审计结果: {'[OK] 全部通过' if all_ok else '[FAIL] 有问题需修复'}")
    print(f"{'='*60}")

    sys.exit(0 if all_ok else 1)


def _print_session_stats_summary():
    """读取 DSH folio-stats-audit 落盘的 sessionStats 快照，打印汇总。

    文件不存在/为空时不视为失败（DSH 插件未在跑或尚未产生数据）。
    """
    try:
        import json
        from _paths import LOGS_DIR
        log_path = os.path.join(LOGS_DIR, "session_stats.jsonl")
        if not os.path.exists(log_path):
            print("\nDSH sessionStats：暂无本地落盘数据（预销售会话运行后生成）")
            return
        rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if not rows:
            print("\nDSH sessionStats：暂无有效记录")
            return
        total_turns = sum(int(r.get("stats", {}).get("turns") or 0) for r in rows)
        total_steps = sum(int(r.get("stats", {}).get("steps") or 0) for r in rows)
        total_llm_ms = sum(int(r.get("stats", {}).get("llmMs") or 0) for r in rows)
        total_tool_ms = sum(int(r.get("stats", {}).get("toolMs") or 0) for r in rows)
        total_decode_tokens = sum(int(r.get("stats", {}).get("decodeTokens") or 0) for r in rows)
        print(f"\nDSH sessionStats（{len(rows)} 条快照）："
              f"turns={total_turns} steps={total_steps} "
              f"llmMs={total_llm_ms} toolMs={total_tool_ms} decodeTokens={total_decode_tokens}")
    except Exception as e:
        print(f"[warn] DSH sessionStats 汇总读取失败: {e}")


def _audit_config():
    """静态配置检查。"""
    ok = True

    # 1. 入口 MD 存在（project_rules.md 为 Trae 委托桩，不作硬性检查）
    for md in ["AGENTS.md"]:
        if os.path.exists(md):
            print(f"✓ {md} 存在")
        else:
            print(f"✗ {md} 缺失")
            ok = False

    # 2. CLI 命令数：parser 与 dispatch 动态一致性（不再硬编码目标数）
    try:
        from _cli import build_parser, _build_dispatch, _DEPRECATED
        parser = build_parser()
        subactions = [a for a in parser._actions if hasattr(a, 'choices') and a.choices]
        all_cmds = set(subactions[0].choices.keys()) if subactions else set()
        dispatch_cmds = set(_build_dispatch().keys())
        missing = all_cmds - dispatch_cmds
        extra = dispatch_cmds - all_cmds
        if missing or extra:
            print(f"✗ parser 与 dispatch 不一致: 无 handler {sorted(missing)} / 未注册 {sorted(extra)}")
            ok = False
        else:
            print(f"✓ CLI 命令数: 活跃 {len(all_cmds)}（parser 与 dispatch 一致）+ 废弃 {len(_DEPRECATED)}")
    except Exception as e:
        print(f"✗ CLI 命令数检查失败: {e}")
        ok = False

    # 3. _renderer 阻断
    try:
        from _renderer import NotInvokedViaCLIError  # noqa: F401
        print("✓ _renderer.NotInvokedViaCLIError 已定义")
    except ImportError:
        print("✗ _renderer 阻断异常未定义")
        ok = False

    # 4. persistence 格式
    print("✓ persistence 格式: permanent/task + client/task（在 _theme_guard.save_decision 中校验）")

    # 5. P0 新增漂移自检
    p0_checks = {
        "必读 Skill 三方口径": _audit_p0_required_skills,
        "工程模式措辞": _audit_p0_engineering_wording,
        "Skill 路由表自动生成": _audit_p0_route_table,
        "创作模式哨兵挂载": _audit_p0_preset_sentinel,
        "spec-writing-guide 版本/旧口径": _audit_p0_spec_guide,
        "Skill 内部断链": _audit_p0_skill_broken_links,
        "delivery-pipeline 决策旧写法": _audit_p0_delivery_decision,
        "核心命令覆盖": _audit_p0_core_command_coverage,
        "Skills 规范合规": _audit_p0_skills_compliance,
        "文件体量闸门（棘轮）": _audit_p0_file_size_ratchet,
    }
    for _label, check in p0_checks.items():
        if not check():
            ok = False

    # 6. 文件溯源：output/ 下文件是否有 verify 记录
    output_provenance_ok = _audit_output_provenance()
    if not output_provenance_ok:
        ok = False

    return ok


def _audit_anti_regeneration():
    """Step 4 后挂入的防再生 audit lint（3 个定点，只钉再生热点）。

    1. diagram 计数跨文件一致：schema.DIAGRAM_SCHEMA 子类型数 == skill 文档声明数（当前 37）
    2. 容量数字单点性：容量预算表只出现在 graphics.md
    3. spec 字段清单单点性：顶层字段表只出现在 spec_protocol_v1.md
    """
    import re
    ok = True

    # 1. diagram 计数
    try:
        from _renderer.schema import all_subtypes
        actual = len(all_subtypes())
        skill_files = [
            os.path.join(SCRIPT_DIR, ".folio", "skills", "visual-craft-guide", "SKILL.md"),
            os.path.join(SCRIPT_DIR, ".folio", "skills", "visual-craft-guide", "references", "graphics.md"),
            os.path.join(SCRIPT_DIR, ".folio", "skills", "spec-writing-guide", "SKILL.md"),
        ]
        # P3：逐文件核销——曾用集合归属（多文件声明并集含 actual 即过），
        # 某文件声明陈旧数字会被另一文件的正确声明掩盖而漏检
        declaring = []  # [(相对路径, 该文件声明的数字列表)]
        for p in skill_files:
            if os.path.exists(p):
                text = open(p, "r", encoding="utf-8").read()
                nums = [int(m.group(1)) for m in re.finditer(r"(\d+)\s*种子类型", text)]
                if nums:
                    declaring.append((rel_to_script(p), nums))
        drifted = [(f, nums) for f, nums in declaring if actual not in nums]
        if not declaring:
            print("✗ diagram 计数漂移：skill 文档无任何「N 种子类型」声明")
            ok = False
        elif drifted:
            for f, nums in drifted:
                print(f"✗ diagram 计数漂移：{f} 声明 {nums}，schema.py {actual}")
            ok = False
        else:
            print(f"✓ diagram 计数单点：schema.py {actual} == skill 文档声明"
                  f"（逐文件核销 {len(declaring)} 个文件）")
    except Exception as e:
        print(f"✗ diagram 计数检查失败: {e}")
        ok = False

    # 2. 容量预算表单点
    canonical = os.path.join(SCRIPT_DIR, ".folio", "skills", "visual-craft-guide", "references", "graphics.md")
    duplicates = []
    skills_root = os.path.join(SCRIPT_DIR, ".folio", "skills")
    for root, _dirs, files in os.walk(skills_root):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(root, fn)
            if os.path.normpath(path) == os.path.normpath(canonical):
                continue
            try:
                text = open(path, "r", encoding="utf-8").read()
            except Exception:
                continue
            if re.search(r"^\|\s*元素\s*\|\s*预算\s*\|", text, re.M):
                duplicates.append(rel_to_script(path))
    if duplicates:
        print(f"✗ 容量预算表出现在非唯一位置: {duplicates}")
        ok = False
    else:
        print("✓ 容量预算表单点：仅 graphics.md")

    # 3. spec 顶层字段表单点
    proto = os.path.join(SCRIPT_DIR, "docs", "spec_protocol_v1.md")
    field_dups = []
    roots = [os.path.join(SCRIPT_DIR, "docs"), os.path.join(SCRIPT_DIR, ".folio", "skills")]
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(dirpath, fn)
                if os.path.normpath(path) == os.path.normpath(proto):
                    continue
                try:
                    text = open(path, "r", encoding="utf-8").read()
                except Exception:
                    continue
                if re.search(r"\| 字段 \| 必填 \| 缺省 \| 说明 \|", text):
                    field_dups.append(rel_to_script(path))
    if field_dups:
        print(f"✗ spec 顶层字段表出现在非唯一位置: {field_dups}")
        ok = False
    else:
        print("✓ spec 字段清单单点：仅 spec_protocol_v1.md")

    return ok


def _audit_output_provenance():
    """文件溯源：扫 output/ 下产出物，查 task_history 有无 verify 记录。

    无记录 = 违规（AI 绕过 CLI 直写）。
    """
    import os, json

    output_dir = os.path.join(SCRIPT_DIR, "output")
    if not os.path.isdir(output_dir):
        print("✓ output/ 不存在，跳过溯源")
        return True

    # 读 task_history 拿 verify 记录
    task_history_path = os.path.join(SCRIPT_DIR, ".folio", "logs", "task_history.json")
    all_verified_paths = set()

    if os.path.exists(task_history_path):
        try:
            with open(task_history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, dict):
                tasks = history.get("tasks", [])
            elif isinstance(history, list):
                tasks = history
            else:
                tasks = []
            for task in tasks:
                if isinstance(task, dict):
                    verify = task.get("verify", {})
                    # P3 类型守卫：verify 值非 dict（脏数据）时曾 .keys() 崩掉整个 audit
                    if isinstance(verify, dict):
                        all_verified_paths.update(verify.keys())
                    else:
                        print(f"  [warn] task_history 存在非 dict 的 verify 字段"
                              f"（类型 {type(verify).__name__}），已跳过该条")
        except (json.JSONDecodeError, OSError):
            pass

    # 扫 output/ 下文件
    # 跳过非产出物目录（D-118：单一数据源 _paths.OUTPUT_SKIP_DIRS，
    # 与 .folio/hooks/_output_skip_dirs.json + 快照测试保持一致）
    from _paths import OUTPUT_SKIP_DIRS
    SKIP_DIRS = set(OUTPUT_SKIP_DIRS)
    # 跳过备份文件
    SKIP_PATTERNS = (".bak", "_backup", "_bak")
    unverified = []
    for root, dirs, files in os.walk(output_dir):
        # 过滤目录：skip_dirs + portal-* 子工程目录模式
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS
                   and not d.startswith("portal-")
                   and not d.endswith("_audit")]  # _audit 目录是审查截图产物
        for fname in files:
            # 跳过隐藏文件与 Office 锁文件（~$ 前缀，非产出物；与 stop_verify.py 一致）
            if fname.startswith(".") or fname.startswith("~$"):
                continue
            if any(p in fname for p in SKIP_PATTERNS):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".html", ".htm", ".pptx", ".docx", ".xlsx"):
                continue
            fpath = os.path.join(root, fname)
            norm_fpath = os.path.normpath(fpath)
            rel_fpath = rel_to_script(fpath)
            # 路径在 task_history 里既可能是绝对，也可能是相对 — 两种都尝试
            found = False
            for v in all_verified_paths:
                v_norm = os.path.normpath(v)
                if (os.path.normcase(v_norm) == os.path.normcase(norm_fpath)
                        or os.path.normcase(v_norm) == os.path.normcase(rel_fpath)):
                    found = True
                    break
            if not found:
                rel_path = rel_to_script(fpath)
                unverified.append(rel_path)

    if unverified:
        print(f"✗ 发现 {len(unverified)} 个未验证产出物（无 verify 记录，疑似绕过 CLI）：")
        for u in unverified[:10]:
            print(f"  [未验证] {u}")
        if len(unverified) > 10:
            print(f"  ... 还有 {len(unverified) - 10} 个")
        return False
    else:
        print(f"✓ output/ 溯源通过（{len(all_verified_paths)} 个文件有 verify 记录）")
        return True


def _audit_runtime():
    """动态功能测试。"""
    ok = True

    # 1. 直接 import _renderer 应 raise NotInvokedViaCLIError
    os.environ.pop('_PRESALES_CLI_INVOKED', None)
    try:
        from _renderer import Renderer
        Renderer("nonexistent.yml")
        print("✗ 直接 import _renderer 未被阻断")
        ok = False
    except Exception as e:
        if 'NotInvokedViaCLI' in type(e).__name__:
            print("✓ 直接 import _renderer 被阻断（NotInvokedViaCLIError）")
        else:
            print(f"✗ 直接 import _renderer 抛出非预期异常（{type(e).__name__}: {e}）")
            ok = False

    # 2. 输出路径检查
    os.environ['_PRESALES_CLI_INVOKED'] = '1'
    try:
        from _renderer import _validate_output_path, OutputPathNotAllowedError
        _validate_output_path("C:/random/path/test.html")
        print("✗ 非法路径未被阻断")
        ok = False
    except OutputPathNotAllowedError:
        print("✓ 非法路径被阻断（OutputPathNotAllowedError）")
    except Exception as e:
        print(f"✗ 输出路径检查抛出非预期异常（{type(e).__name__}: {e}）")
        ok = False

    return ok


def _audit_review_log(client_name=None):
    """F0-2：review_log 会话窗口内 FAIL/ERROR -> 审计 FAIL。

    口径（已记录）：取 review_log.json 最近一条记录；指定 --client 时先按客户
    过滤。若最近一条 verdict 为 FAIL/ERROR 且未被后续 PASS/SKIP 覆盖，则审计
    不通过。日志按追加顺序存储，最后一条即最新窗口。
    """
    import json
    log_path = _REVIEW_LOG
    if not os.path.exists(log_path):
        print("✓ review_log 不存在（无 FAIL/ERROR）")
        return True
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as e:
        print(f"✗ review_log 读取失败: {e}")
        return False
    if not isinstance(entries, list):
        print("✗ review_log 格式非法（非 list）")
        return False
    if client_name:
        entries = [e for e in entries if e.get("client") == client_name]
    if not entries:
        print("✓ review_log 无可审计记录")
        return True
    latest = entries[-1]
    verdict = latest.get("verdict", "?")
    if verdict in ("FAIL", "ERROR"):
        print(f"✗ review_log 最近一次 {verdict}"
              f"（{os.path.basename(str(latest.get('file', '')))}），审计 FAIL")
        return False
    print(f"✓ review_log 最近一次 {verdict}，无未处理 FAIL/ERROR")
    return True


def _audit_memory(client_name=None, clients_dir=None):
    """记忆证据健康检查（P0 记忆溯源 · T4）。

    设计取向：只报健康度、不判 FAIL -- 待补/待核/冲突未决是「可见的债务」
    不是错误；把警告当失败会让审计被日常噪音淹没（门禁恒红只会教人忽略它）。
    「没做/读不到」≠「0 条」：refs 目录不存在报「未摄入或未归档」而非「0 个材料」。
    clients_dir 参数留给单测注入 tmp 目录（生产默认 _knowledge/clients 绝对路径）。
    """
    if clients_dir is None:
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if client_name:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]
    else:
        if not os.path.isdir(clients_dir):
            print("✗ _knowledge/clients/ 不存在")
            return False
        clients = list_client_dirs(clients_dir=clients_dir)

    from _memory_guard import scan_memory_health

    scanned = 0
    for client in clients:
        h = scan_memory_health(client, client_dir=os.path.join(clients_dir, client))
        if not h["context_exists"] and not h["decisions_exists"]:
            continue  # 无记忆文件的客户（如刚建目录）不算问题
        scanned += 1
        refs_dir = os.path.join(clients_dir, client, "refs")
        if os.path.isdir(refs_dir):
            n_refs = len([f for f in os.listdir(refs_dir) if not f.startswith(".")])
            refs_note = f"refs {n_refs} 个文件"
        else:
            refs_note = "无 refs 目录（未摄入或未归档）"  # 「没做」≠「0 条」
        # P3：与 cmd_memory_health 共用 scan_memory_health 数据源 + format_report
        # （同源同口径：audit 用紧凑单行，memory-health 用 format_report 全量文本）
        flags = []
        if h["pending_evidence"]:
            flags.append(f"待补证据 {h['pending_evidence']}")
        if h["unverified_evidence"]:
            flags.append(f"证据待核 {h['unverified_evidence']}")
        if h["conflicts_pending"]:
            flags.append(f"冲突未决 {h['conflicts_pending']}")
        mark = "⚠" if flags else "✓"
        flag_note = "；".join(flags) if flags else "证据健康"
        print(f"  {mark} [{client}] 会话 {h['sessions']} / 决策 {h['decision_entries']} / "
              f"证据段 {h['evidence_sections']} / {flag_note}；{refs_note}")

    if scanned == 0:
        print("ℹ 无可扫描客户（context.md 与 decisions.md 均不存在）")
    print("✓ 记忆证据健康检查完成（⚠ 为警告级，不影响审计结论）")
    return True


def _audit_worldbook_freshness(client_name=None, clients_dir=None):
    """世界书/版本链新鲜度检查（R1-5）：落后于 decisions.md 即 WARN。

    比较 client_index.md front matter 的 _source_hashes 与 client_graph.json 的
    _source_hashes；旧索引无 front matter 时降级用 mtime 对比。
    只输出 WARN，不影响审计 pass/fail。
    """
    import json
    if clients_dir is None:
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if client_name:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]
    else:
        if not os.path.isdir(clients_dir):
            print("✗ _knowledge/clients/ 不存在")
            return False
        clients = list_client_dirs(clients_dir=clients_dir)

    from _worldbook import compute_source_hashes, read_source_hashes

    scanned = 0
    stale = 0
    for client in clients:
        client_dir = os.path.join(clients_dir, client)
        decisions_path = os.path.join(client_dir, "decisions.md")
        oij_path = os.path.join(client_dir, "outputs_index.json")
        if not os.path.exists(decisions_path) and not os.path.exists(oij_path):
            continue
        scanned += 1
        current = compute_source_hashes(client_dir)

        # 1) client_index.md 世界书
        index_path = os.path.join(client_dir, "client_index.md")
        if not os.path.exists(index_path):
            print(f"  ⚠ [{client}] client_index.md 缺失，世界书未生成")
            stale += 1
        else:
            recorded = read_source_hashes(index_path)
            mismatch = []
            if not recorded:
                # C-A5：旧格式无 front matter——hash 比对必全 mismatch（死逻辑，
                # mtime 分支此前只追加不清空，恒 WARN），整体回退 mtime 比对。
                # mtime 兜底仅限此路径：有 front matter 时仍走 hash，真漂移不误判新鲜。
                index_mtime = os.path.getmtime(index_path)
                source_mtimes = []
                for src in [decisions_path, oij_path]:
                    if os.path.exists(src):
                        source_mtimes.append(os.path.getmtime(src))
                if source_mtimes and max(source_mtimes) > index_mtime:
                    mismatch.append("mtime")
            else:
                mismatch = [k for k, v in current.items() if recorded.get(k) != v]
            if mismatch:
                print(f"  ⚠ [{client}] client_index.md 落后于真源 ({', '.join(mismatch)})")
                stale += 1
            else:
                print(f"  ✓ [{client}] client_index.md 新鲜")
        # 2) client_graph.json 版本链
        graph_path = os.path.join(client_dir, "client_graph.json")
        if not os.path.exists(graph_path):
            print(f"  ⚠ [{client}] client_graph.json 缺失，版本链未生成")
            stale += 1
        else:
            try:
                with open(graph_path, "r", encoding="utf-8") as f:
                    graph = json.load(f)
            except Exception as e:
                print(f"  ⚠ [{client}] client_graph.json 解析失败: {e}")
                stale += 1
                continue
            graph_hashes = graph.get("_source_hashes", {}) or {}
            mismatch = [k for k, v in current.items() if graph_hashes.get(k) != v]
            if mismatch:
                print(f"  ⚠ [{client}] client_graph.json 落后于真源 ({', '.join(mismatch)})")
                stale += 1
            else:
                print(f"  ✓ [{client}] client_graph.json 版链新鲜")

    if scanned == 0:
        print("ℹ 无可扫描客户（decisions.md 或 outputs_index.json 均不存在）")
    print(f"✓ 世界书/版本链新鲜度检查完成（⚠ {stale} 项警告级，不影响审计结论）")
    return True


def _latest_keynote_change_hash(decisions_path):
    """从 decisions.md 提取最近一次 keynote_change 事件登记的 sha256。无 -> None。"""
    import re
    if not os.path.exists(decisions_path):
        return None
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None
    last = None
    for block in re.split(r'(?m)^(?=#{1,6} \[)', content):
        if "keynote_change" not in block:
            continue
        m = re.search(r'sha256[:：]\s*([0-9a-f]{64})', block)
        if m:
            last = m.group(1)  # 文件顺序后者覆盖前者 = 最近一次
    return last


def _audit_keynote_hash(client_name=None, clients_dir=None):
    """I-3 A6：keynote hash 对账（ADR-009 §4 防绕闸；观察级 WARN，不 FAIL）。升级条件: 对账漂移实测出现 → 升 FAIL（盘点#16）

    keynote.md 当前内容 sha256 ≠ 最近一次 keynote_change 事件登记 hash
    -> WARN「基调被改但无决策记录」；keynote 存在但无任何登记 -> WARN 提示补登记。
    clients_dir 参数供单测注入 tmp 目录（audit 测试封闭化先例，不依赖仓库真实状态）。
    """
    import hashlib
    if clients_dir is None:
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if client_name:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]
    else:
        if not os.path.isdir(clients_dir):
            print("✗ _knowledge/clients/ 不存在")
            return False
        clients = list_client_dirs(clients_dir=clients_dir)

    scanned = 0
    warned = 0
    for client in clients:
        kn_path = os.path.join(clients_dir, client, "keynote.md")
        if not os.path.exists(kn_path):
            continue  # 无 keynote 的客户不受对账约束（向后兼容）
        scanned += 1
        with open(kn_path, "rb") as f:
            current = hashlib.sha256(f.read()).hexdigest()
        registered = _latest_keynote_change_hash(
            os.path.join(clients_dir, client, "decisions.md"))
        if registered is None:
            print(f"  ⚠ [{client}] keynote.md 存在但无 keynote_change 登记"
                  "（未经 save 链入档？）")
            warned += 1
        elif registered != current:
            print(f"  ⚠ [{client}] 基调被改但无决策记录：keynote.md 当前 hash "
                  f"{current[:12]}… ≠ 最近登记 {registered[:12]}…")
            warned += 1
        else:
            print(f"  ✓ [{client}] keynote hash 对账一致")

    if scanned == 0:
        print("ℹ 无可对账客户（均无 keynote.md）")
    print(f"✓ keynote hash 对账完成（⚠ {warned} 项警告级，不影响审计结论）")
    return True


def _audit_context_health(client_name=None):
    """P1-3：audit context 维度——检查次数、PASS/WARN/BLOCK 分布、高频 WARN TOP3。

    这是统计报告，不因历史 WARN 判 FAIL（门禁在生成命令处执行）。
    """
    import json
    from collections import Counter

    path = os.path.join(SCRIPT_DIR, ".folio", "logs", "context_health.jsonl")
    if not os.path.exists(path):
        print("✓ context-health 暂无记录（生成命令运行后产生）")
        return True
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except OSError as e:
        print(f"✗ context_health.jsonl 读取失败: {e}")
        return False

    if client_name:
        rows = [r for r in rows if r.get("client") == client_name]
    if not rows:
        print("✓ context-health 无匹配记录")
        return True

    verdicts = Counter(r.get("verdict", "?") for r in rows)
    warn_counter = Counter()
    for r in rows:
        for c in r.get("checks", []):
            if c.get("status") == "warn":
                warn_counter[c.get("id", "?")] += 1
    print(f"✓ context-health 统计（{len(rows)} 条）："
          f"pass={verdicts.get('pass', 0)} warn={verdicts.get('warn', 0)} "
          f"block={verdicts.get('block', 0)}")
    if warn_counter:
        top = warn_counter.most_common(3)
        print("  高频 WARN TOP3: " + "；".join(f"{k}={v}" for k, v in top))
    return True


# ============================================================
# Q3 只读 forensic 模式（收编 _scratch/debt_audit / drift_audit / card_audit，
# 2026-09-07）。三者均只报不判（先例 memory/worldbook/
# keynote——历史债是「可见的债务」不是错误，门禁恒红只会教人忽略审计）。
# 只读，不写任何文件。
# ============================================================

# 快照保留数事实源 = _context._snapshot_context（#47 误诊更正后为 3，
# 原 scratch 按 5 报残留已过时）；两处须同步改。
_SNAPSHOT_KEEP = 3
# telemetry 单文件告警阈值（MB）；轮转机制 2026-09-07 上线（CHANGELOG #53）
_TELEMETRY_WARN_MB = 10
# outputs_index.json 顶层元数据 None 豁免清单（允许暂缺待补的字段）
_OI_NULL_WHITELIST = frozenset((
    "parent_company", "website", "vendor", "competitors",
    "winning_dimensions", "switch_strategy", "original_architecture",
))


def _audit_debt(client_name=None, clients_dir=None):
    """历史债对账（只读观察级）：outputs_index 悬空/空壳元数据/标记未清 + 升级条件: 连续两季全绿且有消费方依赖 → 评估入门禁（需拍板；盘点#15）
    decisions.md 同日同题重复 + 残留文件。

    悬空口径（W1-5 契约）：路径不存在且无 missing 标记才算债；带标记条目按
    设计保留（消费端过滤），在盘却带标记 = 自愈未跑，一并提示。
    conflict: pending 组是冲突队列待用户裁决，单独计数不计入重复。
    """
    import glob
    import json
    import re
    if clients_dir is None:
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if client_name:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]
    else:
        if not os.path.isdir(clients_dir):
            print("ℹ _knowledge/clients/ 不存在，无历史债可对账")
            return True
        clients = list_client_dirs(clients_dir=clients_dir)  # #48 收口：排除 _ 前缀内部目录

    debt_clients = 0
    for client in clients:
        base = os.path.join(clients_dir, client)
        notes, infos = [], []

        # 1) outputs_index.json：悬空未标 / 在盘带标记未清 / 元数据空壳
        oi_path = os.path.join(base, "outputs_index.json")
        if os.path.exists(oi_path):
            idx = None
            try:
                with open(oi_path, "r", encoding="utf-8") as f:
                    idx = json.load(f)
            except Exception as e:
                notes.append(f"outputs_index.json 解析失败（{e}）")
            if isinstance(idx, dict):
                outs = idx.get("outputs") or []
                nulls = [k for k, v in idx.items()
                         if v is None and k not in _OI_NULL_WHITELIST]
                if nulls:
                    notes.append("元数据空壳(None)：" + "、".join(str(k) for k in nulls[:3]))
            elif isinstance(idx, list):
                outs = idx
            else:
                outs = []
            dangling, stale_marked, marked = [], [], 0
            for o in outs:
                rel = o if isinstance(o, str) else (o.get("path") or o.get("file") or "")
                if not rel:
                    continue
                has_mark = isinstance(o, dict) and bool(o.get("missing"))
                on_disk = os.path.exists(os.path.join(SCRIPT_DIR, rel))
                if not on_disk:
                    if has_mark:
                        marked += 1  # 按设计：悬空打 missing 标记保留，消费端过滤
                    else:
                        dangling.append(os.path.basename(rel))
                elif has_mark:
                    stale_marked.append(os.path.basename(rel))
            if dangling:
                notes.append(f"悬空未标 {len(dangling)}/{len(outs)} 条（例：{dangling[0]}）")
            if stale_marked:
                notes.append(f"在盘带 missing 标记 {len(stale_marked)} 条（自愈未跑）")
            if marked:
                infos.append(f"已标记缺失 {marked} 条（按设计保留）")

        # 2) decisions.md：同日同题重复（conflict: pending 组单列待裁决）
        dp_path = os.path.join(base, "decisions.md")
        if os.path.exists(dp_path):
            with open(dp_path, "r", encoding="utf-8") as f:
                text = f.read()
            seen, pending_keys = {}, set()
            in_pending, prev_key = False, None
            for block in re.split(r"(?m)^(?=## )", text):
                m = re.match(r"## (.+)", block)
                if not m:
                    continue
                key = re.sub(r"\s+", "", m.group(1))[:36]
                if re.search(r"<!--\s*conflict:\s*pending\s*-->", block):
                    in_pending = True  # 标记落在本块：本块与前一块构成冲突组
                    if prev_key:
                        pending_keys.add(prev_key)
                    pending_keys.add(key)
                elif in_pending:
                    pending_keys.add(key)  # 冲突组的后一块仍属同组
                    in_pending = False
                prev_key = key
                seen[key] = seen.get(key, 0) + 1
            dups = [k for k, v in seen.items() if v > 1 and k not in pending_keys]
            pend = [k for k, v in seen.items() if v > 1 and k in pending_keys]
            if dups:
                notes.append("同日同题重复：" + "；".join(f"「{k}」×{seen[k]}" for k in dups[:3]))
            if pend:
                notes.append("冲突队列待裁决：" + "；".join(f"「{k}」×{seen[k]}" for k in pend[:3]))

        # 3) 残留文件：bak/临时/session_notes + snapshot 超当前保留数
        leftovers = []
        for pat in ("*.bak", "*.bak2", "*.tmp", "*~", "session_notes_*.md"):
            leftovers.extend(os.path.basename(p) for p in glob.glob(os.path.join(base, pat)))
        snaps = glob.glob(os.path.join(base, "context.md.snapshot*"))
        if len(snaps) > _SNAPSHOT_KEEP:
            leftovers.append(f"snapshot×{len(snaps)}(超{_SNAPSHOT_KEEP})")
        if leftovers:
            notes.append("残留：" + "、".join(sorted(leftovers)[:6]) + ("…" if len(leftovers) > 6 else ""))

        if notes:
            debt_clients += 1
            body = "；".join(notes + infos)
            print(f"  ⚠ [{client}] {body}")
        elif infos:
            print(f"  ℹ [{client}] " + "；".join(infos))
    if debt_clients:
        print(f"⚠ 历史债对账：{debt_clients} 个客户有债（只报不判，不影响审计结论；"
              "悬空跑 save 自愈、标记未清提示自愈、冲突组待用户裁决）")
    else:
        print(f"✓ 历史债对账：{len(clients)} 个客户无悬空/重复/残留")
    return True


# 覆盖矩阵列（不含 aliases.md——该机制已退役，绝不入审计面，tests 有退役断言）
_DRIFT_MATRIX = ("context.md", "decisions.md", "client_index.md", "client_graph.json",
                 "outputs_index.json", "aliases.yml", "preferences.md")


def _audit_drift(client_name=None, clients_dir=None):
    """代际漂移+成色（只读观察级）：文件覆盖矩阵（mtime + 条目成色计数）、升级条件: 连续两季全绿且有消费方依赖 → 评估入门禁（需拍板；盘点#15）
    context.md meta_version 结构标记缺失、结构代际检查（openQ/待补/老格式/继承）。

    clients_dir 参数供单测注入 tmp 目录（audit 测试封闭化先例）。
    """
    import datetime
    import json
    import re
    if clients_dir is None:
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
    if client_name:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]
    else:
        if not os.path.isdir(clients_dir):
            print("ℹ _knowledge/clients/ 不存在，无漂移可扫")
            return True
        clients = list_client_dirs(clients_dir=clients_dir)

    from _context import has_meta_version

    def _mt(p):
        return datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d")

    def _cell(base, name):
        """矩阵单元格：mtime 或 mtime + 成色计数（缺文件 = -）。"""
        p = os.path.join(base, name)
        if not os.path.exists(p):
            return "-"
        if name == "decisions.md":
            with open(p, "r", encoding="utf-8") as f:
                return f"{len(re.findall(r'(?m)^## ', f.read()))}条/{_mt(p)}"
        if name == "outputs_index.json":
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                n = len(d.get("outputs") or []) if isinstance(d, dict) else len(d)
                return f"{n}条/{_mt(p)}"
            except Exception:
                return "JSON-ERR"
        if name == "aliases.yml":
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    return f"{len(yaml.safe_load(f) or {})}键/{_mt(p)}"
            except Exception:
                return "YAML-ERR"
        if name == "preferences.md":
            with open(p, "r", encoding="utf-8") as f:
                t = f.read()
            return ("模板/" if ("暂无" in t or "待补" in t) else "实data/") + _mt(p)
        return _mt(p)

    print("  %-18s %-10s %-14s %-9s %-8s %-14s %-11s %s" % (
        "客户", "context", "decisions", "索引", "版链", "产出索引", "别名.yml", "偏好"))
    for client in clients:
        base = os.path.join(clients_dir, client)
        cells = [_cell(base, name) for name in _DRIFT_MATRIX]
        print("  %-18s %-10s %-14s %-9s %-8s %-14s %-11s %s" % (client[:17], *cells))

    warned = 0
    for client in clients:
        base = os.path.join(clients_dir, client)
        marks = []
        cp = os.path.join(base, "context.md")
        if os.path.exists(cp):
            with open(cp, "r", encoding="utf-8") as f:
                t = f.read()
            if not has_meta_version(t):
                marks.append("缺meta_version")
            if "open_questions" not in t and "待澄清" not in t:
                marks.append("context无openQ")
            if re.search(r"(行业|核心需求)[：:]\s*待补", t):
                marks.append("行业/需求=待补")
        dp = os.path.join(base, "decisions.md")
        if os.path.exists(dp):
            with open(dp, "r", encoding="utf-8") as f:
                t = f.read()
            n_h2 = len(re.findall(r"(?m)^## ", t))
            n_persist = t.count("persistence")
            if n_h2 and n_persist < n_h2:
                marks.append(f"decisions老格式 {n_h2 - n_persist}/{n_h2}")
        ap = os.path.join(base, "aliases.yml")
        if os.path.exists(ap):
            with open(ap, "r", encoding="utf-8") as f:
                if "extends" not in f.read():
                    marks.append("aliases.yml无extends继承")
        if marks:
            warned += 1
            print(f"  ⚠ [{client}] " + "；".join(marks))
    print(f"✓ 代际漂移扫描：矩阵 {len(clients)} 客户，⚠ {warned} 项结构代际标记"
          "（只报不判，不影响审计结论）")
    return True


def _audit_cost(logs_dir=None):
    """观测成本体检（只读观察级，恒不 FAIL）：telemetry_dsh.jsonl 体量与升级条件: 连续两季全绿且有消费方依赖 → 评估入门禁（需拍板；盘点#15）
    轮转状态、本月 LLM 用量聚合、probe 缓存健康。

    任何数据源缺失一律降级标注「数据源不存在」，不抛错不 FAIL。
    logs_dir 参数供单测注入 tmp 目录。
    """
    import datetime
    import json
    if logs_dir is None:
        logs_dir = LOGS_DIR
    month = datetime.datetime.now().strftime("%Y-%m")

    # ① telemetry 体量与轮转（轮转机制 2026-09-07 上线，CHANGELOG #53）
    tel_path = os.path.join(logs_dir, "telemetry_dsh.jsonl")
    if not os.path.exists(tel_path):
        print("  ℹ telemetry_dsh.jsonl 数据源不存在（DSH 会话运行后生成）")
    else:
        size_mb = os.path.getsize(tel_path) / (1024 * 1024)
        rotated = [f for f in os.listdir(logs_dir) if f.startswith("telemetry_dsh.jsonl.")]
        if size_mb > _TELEMETRY_WARN_MB:
            print(f"  ⚠ telemetry_dsh.jsonl {size_mb:.1f}MB > {_TELEMETRY_WARN_MB}MB"
                  f"（轮转产物 {len(rotated)} 份；超限未轮转或轮转积压）")
        else:
            print(f"  ✓ telemetry_dsh.jsonl {size_mb:.1f}MB ≤ {_TELEMETRY_WARN_MB}MB"
                  f"（轮转产物 {len(rotated)} 份）")

    # ② 本月 LLM 用量（llm_usage.jsonl 逐行聚合；读不到标注而非报错）
    usage_path = os.path.join(logs_dir, "llm_usage.jsonl")
    if not os.path.exists(usage_path):
        print("  ℹ 本月 LLM 用量：数据源不存在（llm_usage.jsonl，云调用后生成）")
    else:
        calls, tokens = 0, 0
        try:
            with open(usage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if str(row.get("time", "")).startswith(month):
                        calls += 1
                        try:
                            tokens += int(row.get("total_tokens") or 0)
                        except (TypeError, ValueError):
                            pass
        except OSError:
            pass
        print(f"  ✓ 本月（{month}）LLM 用量：{calls} 次 / {tokens} tokens（llm_usage.jsonl）")

    # ③ probe 缓存健康（能力缓存条目数 + probe-debug 日志尾部）
    cap_path = os.path.join(logs_dir, "model_capabilities.json")
    if not os.path.exists(cap_path):
        print("  ℹ probe 缓存 model_capabilities.json 数据源不存在（从未落盘，#53 挂遗留）")
    else:
        try:
            with open(cap_path, "r", encoding="utf-8") as f:
                n = len(json.load(f))
            print(f"  ✓ probe 缓存 model_capabilities.json 存在（{n} 条）")
        except Exception as e:
            print(f"  ⚠ probe 缓存存在但解析失败：{e}")
    probe_log = os.path.join(logs_dir, "model-capability-probe-debug.log")
    if os.path.exists(probe_log):
        try:
            with open(probe_log, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-3:]
            print("  probe-debug 尾部 3 行：")
            for ln in tail:
                print(f"    | {ln.rstrip()}")
        except OSError:
            pass
    else:
        print("  ℹ probe-debug 日志数据源不存在")
    print("✓ 观测成本体检完成（只报不判恒不 FAIL）")
    return True


# C-A1 behavior handler 独立小模块（体量棘轮 cap 1395 拆分外迁；import 保持引用面不变）
from _cli_audit_behavior import _audit_behavior  # noqa: E402
from _cli_audit_track import _audit_track  # noqa: E402  # S9 2b 同上外迁


def _audit_theme(client_name=None):
    """检查 decisions.md persistence 字段格式。

    向后兼容策略：旧无 persistence 字段的决策默认按 permanent + client 处理
    （写进 decisions.md 的本来就是铁律，不应因字段缺失而失效）。
    因此"无字段"不是错误，只是提示性信息。
    """
    import os, re
    ok = True

    if not client_name:
        # 扫描所有客户（绝对路径：audit 可能从非项目根目录执行，如 Kimi Work 会话）
        clients_dir = os.path.join(SCRIPT_DIR, "_knowledge", "clients")
        if not os.path.isdir(clients_dir):
            print("✗ _knowledge/clients/ 不存在")
            return False
        clients = list_client_dirs(clients_dir=clients_dir)
    else:
        from _paths import _validate_client_name
        _validate_client_name(client_name)
        clients = [client_name]

    for client in clients:
        decisions_path = os.path.join(SCRIPT_DIR, "_knowledge", "clients", client, "decisions.md")
        if not os.path.exists(decisions_path):
            continue
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 persistence 字段格式（缺失默认 permanent+client，不算错误）
        blocks = re.split(r'\n## (?:决策 \d+[：:]|\[\d{4}-\d{2}-\d{2}\])', content)
        legacy_count = 0
        explicit_count = 0
        for i, block in enumerate(blocks[1:], 1):  # 跳过文件头
            has_persistence = "persistence:" in block or "persistence：" in block
            if has_persistence:
                explicit_count += 1
                # 检查格式是否合法
                m = re.search(r'persistence[：:]\s*(\w+)', block)
                if m and m.group(1).lower() not in ("permanent", "task"):
                    first_line = block.strip().split("\n")[0][:60]
                    print(f"  ✗ [{client}] 决策 {i} persistence 值非法 '{m.group(1)}': {first_line}")
                    ok = False
            else:
                legacy_count += 1

        if legacy_count or explicit_count:
            print(f"  ℹ [{client}] 共 {legacy_count + explicit_count} 条决策"
                  f"（显式 persistence {explicit_count} / 旧无字段默认 permanent+client {legacy_count}）")

    if ok:
        print("✓ decisions.md persistence 格式检查通过（含向后兼容）")

    return ok


def cmd_cite_audit(args):
    """引用及审查报告：从 spec 的 evidence 字段提取引用，反向校验来源。

    用法：python _cli.py cite-audit <spec.yml> --client <客户>
    输出：Markdown 格式的引用及审查报告
    """
    import yaml

    spec_path = args.spec
    client = args.client or ""

    if not os.path.exists(spec_path):
        print(f"错误：spec 文件不存在: {spec_path}")
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    pages = spec.get("pages", [])
    if not pages:
        print("错误：spec 无 pages")
        sys.exit(1)

    print(f"=== 引用及审查报告：{spec_path} ===")
    print(f"客户：{client or '(未指定)'}")
    print(f"页面数：{len(pages)}\n")

    # 1. 收集所有 evidence
    all_evidence = []
    for i, page in enumerate(pages):
        ev_list = page.get("evidence", [])
        if not ev_list:
            continue
        for ev in ev_list:
            all_evidence.append({
                "page": page.get("title", f"page_{i+1}"),
                "source": ev.get("source", "?"),
                "snippet": ev.get("snippet", ""),
            })

    print(f"引用证据总数：{len(all_evidence)}")

    # 2. 反向校验：检查每个 evidence 的 source 文件是否存在
    verified = []
    missing = []
    for ev in all_evidence:
        source = ev["source"]
        # source 格式：path#anchor，取 path 部分
        path_part = source.split("#")[0] if "#" in source else source
        full_path = path_part
        if not os.path.isabs(full_path):
            full_path = os.path.join(SCRIPT_DIR, path_part)
        if os.path.exists(full_path):
            verified.append(ev)
        else:
            missing.append(ev)

    print(f"来源可验证：{len(verified)}")
    print(f"来源缺失：{len(missing)}\n")

    # 3. 主题守卫：检查 spec 是否覆盖 permanent 主题
    theme_result = None
    if client:
        try:
            from _theme_guard import load_active_themes, check_coverage
            themes = load_active_themes(client, only_permanent=True)
            if themes:
                # 把 spec 所有页面文本拼起来检查
                spec_text = ""
                for page in pages:
                    spec_text += page.get("title", "") + "\n"
                    for el in page.get("elements", []):
                        if el.get("type") == "text":
                            spec_text += el.get("content", "") + "\n"
                        elif el.get("type") == "bullets":
                            spec_text += "\n".join(el.get("items", [])) + "\n"
                        elif el.get("type") == "cards":
                            for c in el.get("cards", []):
                                spec_text += c.get("title", "") + " " + c.get("body", "") + "\n"
                theme_result = check_coverage(spec_text, themes)
        except Exception as e:
            print(f"[warn] 主题守卫检查失败: {e}")

    # 4. 输出报告
    report_lines = ["# 引用及审查报告\n"]
    report_lines.append(f"**文件**：{spec_path}")
    report_lines.append(f"**客户**：{client or '(未指定)'}")
    report_lines.append(f"**页面数**：{len(pages)}")
    report_lines.append(f"**引用证据**：{len(all_evidence)} 条（可验证 {len(verified)}，缺失 {len(missing)}）\n")

    # 引用清单
    report_lines.append("## 一、引用清单\n")
    if not all_evidence:
        report_lines.append("无引用证据。\n")
    else:
        for ev in all_evidence:
            report_lines.append(f"### {ev['page']}")
            report_lines.append(f"- **来源**：`{ev['source']}`")
            report_lines.append(f"- **片段**：{ev['snippet'][:200]}\n")

    # 来源校验
    report_lines.append("## 二、来源校验\n")
    if missing:
        report_lines.append("以下来源文件不存在，请检查：\n")
        for ev in missing:
            report_lines.append(f"- `{ev['source']}`（引用于：{ev['page']}）")
    else:
        report_lines.append("所有来源文件存在。\n")

    # 主题覆盖
    report_lines.append("\n## 三、主题覆盖\n")
    if theme_result:
        report_lines.append(f"已覆盖 {len(theme_result['covered'])} 条，缺失 {len(theme_result['missing'])} 条\n")
        if theme_result["covered"]:
            report_lines.append("### 已覆盖")
            for t in theme_result["covered"]:
                report_lines.append(f"- {t['theme']}")
        if theme_result["missing"]:
            report_lines.append("\n### 缺失（需补充）")
            for t in theme_result["missing"]:
                report_lines.append(f"- {t['theme']}")
    else:
        report_lines.append("无 permanent 主题记录或客户未指定。\n")

    # 输出
    report = "\n".join(report_lines)
    print(report)

    # F0-7：--strict 缺来源或 critical 主题缺失 -> exit 2（deliver 链强制）
    if getattr(args, "strict", False):
        critical_missing = [t for t in (theme_result or {}).get("missing", [])
                            if t.get("priority") == "critical"]
        if missing or critical_missing:
            print(f"\n[FAIL] cite-audit --strict 未通过："
                  f"来源缺失 {len(missing)}，critical 主题缺失 {len(critical_missing)}")
            sys.exit(2)

    # 写入文件
    # P1-2：默认路径用 splitext 派生——曾用 replace(".yml", ...)，.yaml 输入
    # 替换不生效导致 output_path == 源 spec，报告直接覆盖源文件
    output_path = args.output or os.path.splitext(spec_path)[0] + "_审查报告.md"
    # 写前断言双保险：无论默认派生还是显式 --output，都绝不写向源 spec 本身
    if os.path.abspath(output_path) == os.path.abspath(spec_path):
        print("[阻断] 输出路径与源 spec 相同，拒绝写入（防覆盖源文件）；请改用 --output")
        sys.exit(1)
    # §八 3.5：审查报告写入过 output/ 白名单。默认路径跟随 spec 所在目录——
    # spec 不在 output/ 下时默认路径出名单，阻断并提示显式 --output
    # （报告全文已打印到 stdout，阻断不丢信息）
    from _renderer import _validate_output_path, OutputPathNotAllowedError
    try:
        _validate_output_path(output_path)
    except OutputPathNotAllowedError as e:
        print(f"\n[阻断] {e}")
        print("  提示：请用 --output 指定 output/ 下路径（如 output/通用/审查报告.md）")
        sys.exit(1)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已生成：{output_path}")


def cmd_theme_verify(args):
    """检查产出文件是否覆盖了 permanent 主题（v2.0 关键词匹配）。

    P2 fail-closed 原生化：
      - critical 主题缺失 → exit 2（DSH folio_theme_verify 由 makeCliTool 包装，
        ok = exitCode===0，直接表现为工具失败）
      - 非 critical 缺失 → warn（exit 0，关键词快筛不因普通主题缺失卡交付）
      - 读不到文件 / 客户无主题 → exit 1（无法判定 = 失败，不静默放过）
    """
    from _theme_guard import load_active_themes, check_coverage
    themes = load_active_themes(args.client, only_permanent=True)
    if not themes:
        print(f"客户 '{args.client}' 无 permanent 主题记录")
        sys.exit(1)
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"读取文件失败: {e}")
        sys.exit(1)
    result = check_coverage(text, themes)
    print(f"=== 主题覆盖检查：{args.file} ===")
    print(f"已覆盖 {len(result['covered'])} 条，缺失 {len(result['missing'])} 条\n")
    if result["covered"]:
        print("已覆盖:")
        for t in result["covered"]:
            print(f"  [OK] {t['theme']}")
    if result["missing"]:
        print("\n缺失:")
        for t in result["missing"]:
            print(f"  [FAIL] {t['theme']}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"\n{w}")
    # P2：critical 缺失 → fail-closed exit 2
    critical_missing = [t for t in result["missing"] if t.get("priority") == "critical"]
    if critical_missing:
        print(f"\n[FAIL] {len(critical_missing)} 条 critical 铁律未覆盖（fail-closed，exit 2）")
        sys.exit(2)
    if result["missing"]:
        print("\n[warn] 有非 critical 主题未覆盖（关键词快筛；语义覆盖由 review 维度 1 兜底）")
    return


# key-doctor 检查的 key 及其控制的功能（与 .env.example 降级矩阵对齐）
_KEY_FEATURES = [
    ("ZHIPU_API_KEY", "Chat 主 provider + Embedding + LLM rerank（GLM_API_KEY 等效）"),
    ("SILICONFLOW_API_KEY", "BGE-reranker 精排"),
    ("TAVILY_API_KEY", "联网搜索（第一引擎）"),
    ("ASK_ECHO_SEARCH_INFINITY_API_KEY", "字节搜索（API Key 方式）"),
    ("VOLCENGINE_ACCESS_KEY", "字节搜索（AK/SK 方式，需配 SECRET_KEY）"),
    ("DEEPSEEK_API_KEY", "Chat 备选 provider"),
    ("MIMO_API_KEY", "Chat 备选 + 质量自评默认"),
    ("MINIMAX_API_KEY", "Chat 备选 + 图片理解（视觉槽位，可替换为其他兼容视觉端点）"),
]


def _read_dotenv_map():
    """按 _load_dotenv 同规则解析 .env，返回 {key: value}。"""
    env_path = os.path.join(SCRIPT_DIR, ".env")
    result = {}
    if not os.path.exists(env_path):
        return result
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return result


def _mask_key(v):
    """key 掩码只留末 4 位（安全报告 P3：前6后4 对短 key 暴露比例偏高）；
    不足 8 位时末 4 已过半，全掩。"""
    return f"***{v[-4:]}" if len(v) >= 8 else "***"


def cmd_key_doctor(args):
    """key-doctor：列出各 API key 的来源/掩码/控制功能，默认做活体探测。

    key 来源优先级：系统环境变量 > .env（_load_dotenv 不覆盖已有变量）。
    GUI 工具正常但 CLI 异常时，先用本命令确认来源是否一致。
    """
    dotenv = _read_dotenv_map()
    conflicts = []

    _mask = _mask_key  # 掩码单点：见 _mask_key（前0后4，短 key 全掩）

    print("=== API Key 来源 ===")
    for var, feature in _KEY_FEATURES:
        env_val = os.environ.get(var, "")
        dot_val = dotenv.get(var, "")
        if not env_val and not dot_val:
            print(f"  [缺失] {var}  —  {feature}")
            continue
        if env_val and dot_val and env_val != dot_val:
            src = "env（覆盖 .env 旧值）"
            conflicts.append(var)
        elif dot_val:
            src = ".env"
        else:
            src = "env"
        print(f"  [{src}] {var} = {_mask(env_val or dot_val)}  —  {feature}")
    for var in conflicts:
        print(f"  [warn] {var} 双源冲突：env 与 .env 值不同，当前生效的是 env；建议清理 .env 里的旧值")

    if getattr(args, "no_probe", False):
        return

    # 活体探测：只覆盖 chat provider + embedding（复用 _cloud_llm.check_providers）
    # 搜索类 key 探测会消耗额度，只做来源展示
    print("\n=== 活体探测（chat + embedding）===")
    from _cloud_llm import check_providers
    status = check_providers()
    failed = []
    for name, (ok, model) in status.items():
        if "未设置" in str(model):
            print(f"  [跳过] {name}（未配置 key）")
            continue
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {name} ({model})")
        if not ok:
            failed.append(name)
    if failed:
        print(f"\n探测失败: {', '.join(failed)}")
        print("  提示：key 无效或网络不通；先看上方来源表确认生效的是哪个值")
        sys.exit(1)
