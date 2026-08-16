# -*- coding: utf-8 -*-
"""CLI 审计模块：config/runtime/theme 审计 + 引用审查 + 主题覆盖检查。"""
import os
import sys

from _cli_infra import SCRIPT_DIR


def cmd_audit(args):
    """审计：检查配置一致性 / 运行时功能 / 对话行为 / 主题格式。

    --config: 静态检查（入口 MD / CLI 命令数 / _renderer 阻断 / persistence 格式）
    --runtime: 动态功能测试（recall / import 阻断 / spec 阻断 / 路径阻断）
    --behavior: 对话行为审计（需要 AI 对话日志）
    --theme <客户>: 检查 decisions.md persistence 字段格式
    --all: 全部检查
    """
    mode = args.mode or "config"
    if mode == "all":
        modes = ["config", "runtime", "theme"]
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
        else:
            print(f"未知审计模式: {m}")
            continue
        if not ok:
            all_ok = False

    print(f"\n{'='*60}")
    print(f"  审计结果: {'[OK] 全部通过' if all_ok else '[FAIL] 有问题需修复'}")
    print(f"{'='*60}")

    sys.exit(0 if all_ok else 1)


def _audit_config():
    """静态配置检查。"""
    import os
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

    # 5. 文件溯源：output/ 下文件是否有 verify 记录
    output_provenance_ok = _audit_output_provenance()
    if not output_provenance_ok:
        ok = False

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
                    all_verified_paths.update(verify.keys())
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
            rel_fpath = os.path.relpath(fpath, SCRIPT_DIR)
            # 路径在 task_history 里既可能是绝对，也可能是相对 — 两种都尝试
            found = False
            for v in all_verified_paths:
                v_norm = os.path.normpath(v)
                if (os.path.normcase(v_norm) == os.path.normcase(norm_fpath)
                        or os.path.normcase(v_norm) == os.path.normcase(rel_fpath)):
                    found = True
                    break
            if not found:
                rel_path = os.path.relpath(fpath, SCRIPT_DIR)
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
    import os
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
        clients = [d for d in os.listdir(clients_dir)
                   if os.path.isdir(os.path.join(clients_dir, d)) and not d.startswith("_")]
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

    # 写入文件
    output_path = args.output or spec_path.replace(".yml", "_审查报告.md")
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
    """检查产出文件是否覆盖了 permanent 主题（v2.0 关键词匹配）。"""
    from _theme_guard import load_active_themes, check_coverage
    themes = load_active_themes(args.client, only_permanent=True)
    if not themes:
        print(f"客户 '{args.client}' 无 permanent 主题记录")
        return
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
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


def cmd_key_doctor(args):
    """key-doctor：列出各 API key 的来源/掩码/控制功能，默认做活体探测。

    key 来源优先级：系统环境变量 > .env（_load_dotenv 不覆盖已有变量）。
    GUI 工具正常但 CLI 异常时，先用本命令确认来源是否一致。
    """
    dotenv = _read_dotenv_map()
    conflicts = []

    def _mask(v):
        return f"{v[:6]}***{v[-4:]}" if len(v) >= 12 else "***"

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
