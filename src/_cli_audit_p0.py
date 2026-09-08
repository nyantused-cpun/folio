# -*- coding: utf-8 -*-
"""CLI 审计 P0 检查子模块（T9 拆分自 _cli_audit.py，2026-09-01）。
承载：_audit_p0_required_skills ~ _audit_p0_skills_compliance 共 10 项；
批5（2026-09-05）知识层观察级检查 _audit_knowledge_terms_drift（C2 术语漂移）/升级条件: 连续两季全绿且有消费方依赖 → 评估入门禁（需拍板；盘点#15）
_audit_knowledge_anchor_integrity（S11 锚点完整性）亦置此（_cli_audit.py 容量封顶）。
其余检查（config/runtime/theme/memory/context/review_log/provenance + cmd_*）留 _cli_audit.py。"""
import os
import re

from _cli_infra import SCRIPT_DIR

# 体量棘轮基线 cap（_audit_p0_file_size_ratchet 用；调整须走 decisions.md）。
# 模块级常量便于测试注入，避免测试依赖真实工程体量。
# 2026-09-01 收紧：T1/T9 拆分完成后按「实际值 +10% 余量」重置（原 3200/1600/
# 1400/1400 是拆分前的存量挂账，留 +4144 行反弹空间等于成果未锁）。
# _renderer/schema 新入基线：1199 行距通用红线 1200 仅 1 行，且随 37 种 diagram
# 自然增长，给 1250 缓冲避免加图形时被迫停工拆文件。
# 2026-09-03 _outline_to_spec 入基线：视觉重构阶段 2（2-2 --narrative 接线、
# 2-7 chapters 补页）按计划书落进本文件，1214 行 +10% 余量取 1350；
# 阶段 3（3-4/3-6）仍改本文件，到顶即拆，不许再升。
# 2026-09-04 S1 拆分兑现"到顶即拆"：role 表/gold/校验器群迁 _diagram_extract、
# chapters 补页迁 _narrative_apply，本文件 1350→780 行；cap 同步收紧 780+10%=860，
# 锁住拆分成果防反弹（新模块走默认 1200 警戒线）。
# 2026-09-04 盲区修复：扫描改 os.walk 递归——原实现只 listdir 一层，_renderer/diagram/
# 子包整体逃逸（architecture/pptd_emit 1632/1594 行从未被检）。两存量入基线挂账
# （S4 还债待办），cap 按"实际值+小余量"取，不许继续涨。
# 2026-09-05 P4-S3 拆分：_verify 观察/检查类函数群迁 _verify_checks（1175→726/476），
# 两文件按「实际值 +10%」入基线锁成果（726→800 / 476→530），后续批次只许往
# _verify_checks 加检查函数，cap 到顶即再拆，不许升。
_RATCHET_CAPS = {
    "_cli": 1000,
    # 2026-09-08 R3-1 拆小兑现"到顶即拆"：_cli_generate 1191/1200 顶满（育种钩子
    # P3-2 净增无处落），构建族七命令迁 _cli_generate_build、deliver 族迁
    # _cli_generate_deliver（两新模块走默认 1200 警戒线），本文件 1191→360；
    # cap 按「实际值+10%」锁 400，防拆分成果反弹。
    "_cli_generate": 400,
    "_pptd_gen": 850,
    # 2026-09-06 B5b 重定基（P3 修复净增守卫/注释，拆小挂账 B6；_cloud_llm 拆分
    # 设计稿见总计划 Q2）：_cloud_llm 1000→1022 / _cli_audit 1050→1059 /
    # _outline_to_spec 860→861 / _verify_checks 530→534 / pptd_emit 1600→1606。
    # 重定基后只许降不许升。
    # 2026-09-07 #57/Q2 方案A 下沉 _post_json 到 _cloud_transport：_cloud_llm 回线内 1022→988。
    # 2026-09-07 同日 #43 新增 provider 卫生熔断（台账项净增 27 行，B5b 重定基先例）：988→1015。
    "_cloud_llm": 1015,
    # 2026-09-07 Q3 debt/drift/cost 三模式产品化净增约 330 行（B5b/同日 #43 重定基先例）：
    # _cli_audit 1059→1395。
    "_cli_audit": 1395,
    "_renderer/schema": 1250,
    "_outline_to_spec": 861,
    "_verify": 800,
    "_verify_checks": 534,
    # 2026-09-07 #58 渲染端补点对点简式分支净增约 250 行（重定基先例）：architecture 1650→1740。
    "_renderer/diagram/architecture": 1740,
    # 2026-09-07 S8-B 拆分兑现"到顶即拆"：chrome 构件发射器族迁
    # pptd_emit_chrome/pptd_emit_ext（两新模块走默认 1200 警戒线），
    # 本文件 1826→651 行，cap 同步收紧 1606→720 锁住拆分成果防反弹。
    "_renderer/diagram/pptd_emit": 720,
}

def _audit_p0_required_skills():
    """P0-2/P0-3：必读 Skill 三方口径一致性。"""
    from _cli_guards import REQUIRED_GEN_SKILLS, OPTIONAL_GEN_SKILLS
    ok = True
    expected = ["delivery-pipeline", "spec-writing-guide", "visual-craft-guide"]
    if REQUIRED_GEN_SKILLS != expected:
        print(f"✗ REQUIRED_GEN_SKILLS 应为 {expected}，实际 {REQUIRED_GEN_SKILLS}")
        ok = False
    if OPTIONAL_GEN_SKILLS != ["de-ai-style", "presentation-content-design"]:
        print(f"✗ OPTIONAL_GEN_SKILLS 应为按需 2，实际 {OPTIONAL_GEN_SKILLS}")
        ok = False

    agents_path = os.path.join(SCRIPT_DIR, "AGENTS.md")
    tests_path = os.path.join(SCRIPT_DIR, "tests", "test_cli_guards.py")
    try:
        agents_text = open(agents_path, "r", encoding="utf-8").read()
        if "REQUIRED_GEN_SKILLS" not in agents_text:
            print("✗ AGENTS.md 未注明以 _cli_guards.REQUIRED_GEN_SKILLS 为准")
            ok = False
        missing = [s for s in expected if s not in agents_text]
        if missing:
            print(f"✗ AGENTS.md 必读 Skill 缺失: {missing}")
            ok = False
    except OSError as e:
        print(f"✗ AGENTS.md 读取失败: {e}")
        ok = False

    try:
        # T1 拆分后哨兵提示逻辑随质量面命令迁至 _cli_cmds_qa.py（_cli.py 仅剩 parser/dispatch）
        cli_paths = [os.path.join(SCRIPT_DIR, "_cli.py")]
        qa_path = os.path.join(SCRIPT_DIR, "_cli_cmds_qa.py")
        if os.path.isfile(qa_path):
            cli_paths.append(qa_path)
        cli_text = "\n".join(open(p, "r", encoding="utf-8").read() for p in cli_paths)
        if "REQUIRED_GEN_SKILLS" not in cli_text or "OPTIONAL_GEN_SKILLS" not in cli_text:
            print("✗ _cli.py/_cli_cmds_qa.py 未从 _cli_guards.REQUIRED_GEN_SKILLS/OPTIONAL_GEN_SKILLS 生成提示")
            ok = False
    except OSError as e:
        print(f"✗ CLI 提示检查读取失败: {e}")
        ok = False

    try:
        tests_text = open(tests_path, "r", encoding="utf-8").read()
        if "OPTIONAL_GEN_SKILLS" not in tests_text:
            print("✗ tests/test_cli_guards.py 未同步按需 2 断言")
            ok = False
    except OSError as e:
        print(f"✗ tests/test_cli_guards.py 读取失败: {e}")
        ok = False

    if ok:
        print("✓ 必读 Skill 口径一致：强制 3 / 按需 2，AGENTS.md / _cli.py / 测试均指向 _cli_guards")
    return ok


def _audit_p0_engineering_wording():
    """P0-3：AGENTS.md 工程模式措辞与 preset 实际插件面一致。"""
    ok = True
    path = os.path.join(SCRIPT_DIR, "AGENTS.md")
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"✗ AGENTS.md 读取失败: {e}")
        return False
    if "无兰亭插件" in text:
        print("✗ AGENTS.md 仍写“无兰亭插件”过时措辞")
        ok = False
    if "无 folio/gewu/vision 业务工具，仅保留通用" not in text:
        print("✗ AGENTS.md 未更新为“无 folio/gewu/vision 业务工具，仅保留 folio-search”")
        ok = False
    if "folio-search" not in text:
        print("✗ AGENTS.md 工程模式未提及通用 folio-search")
        ok = False
    if ok:
        print("✓ AGENTS.md 工程模式措辞已更新")
    return ok


def _audit_p0_route_table():
    """P0-3/P0-4：路由表与 Skill frontmatter 一致 + overrides 合法。"""
    from _skills_sync import (
        scan_skill_routing, load_route_overrides, apply_route_overrides,
        render_routing_section, _ROUTE_MARKER_BEGIN, _ROUTE_MARKER_END,
    )
    ok = True
    skills_dir = os.path.join(SCRIPT_DIR, ".folio", "skills")
    ref_path = os.path.join(SCRIPT_DIR, "AGENTS_REFERENCE.md")
    overrides_path = os.path.join(SCRIPT_DIR, "route_overrides.yml")

    entries = scan_skill_routing(skills_dir)
    overrides = load_route_overrides(overrides_path)
    entries = apply_route_overrides(entries, overrides)
    generated = render_routing_section(entries)
    try:
        text = open(ref_path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"✗ AGENTS_REFERENCE.md 读取失败: {e}")
        return False

    norm_text = text.replace("\r\n", "\n")
    if _ROUTE_MARKER_BEGIN not in norm_text or _ROUTE_MARKER_END not in norm_text:
        print("✗ AGENTS_REFERENCE.md 缺少 AUTO-GENERATED 路由区")
        ok = False
    elif generated not in norm_text:
        print("✗ 路由表被手改或未同步：请运行 python _cli.py skills-sync 重新生成")
        ok = False

    known = {e["name"] for e in entries}
    for key in ("force_include", "force_exclude"):
        for name in overrides.get(key) or []:
            if name not in known:
                print(f"✗ route_overrides.yml {key} 引用不存在 Skill: {name}")
                ok = False
    for alias in overrides.get("trigger_alias") or []:
        if isinstance(alias, dict) and alias.get("skill") not in known:
            print(f"✗ route_overrides.yml trigger_alias 引用不存在 Skill: {alias.get('skill')}")
            ok = False
    if ok:
        print(f"✓ 路由表 AUTO-GENERATED 一致（{len(entries)} 个 skill），overrides 合法")
    return ok


def _audit_p0_preset_sentinel():
    """P0-1：创作模式挂载 sentinelOnly，且 tool-bootstrap 支持 early-exit。"""
    ok = True
    creator_agent = os.path.join(SCRIPT_DIR, ".dsh", "preset", "pre-sales-creator", "agent.cordis.yml")
    bootstrap = os.path.join(SCRIPT_DIR, ".dsh", "preset", "pre-sales", "tool-bootstrap.mjs")
    creator_preset = os.path.join(SCRIPT_DIR, ".dsh", "preset", "pre-sales-creator", "preset.yml")

    try:
        text = open(creator_agent, "r", encoding="utf-8").read()
        if "tool-bootstrap" not in text or "sentinelOnly: true" not in text:
            print("✗ pre-sales-creator/agent.cordis.yml 未挂载 tool-bootstrap sentinelOnly")
            ok = False
    except OSError as e:
        print(f"✗ pre-sales-creator/agent.cordis.yml 读取失败: {e}")
        ok = False

    try:
        text = open(bootstrap, "r", encoding="utf-8").read()
        if "sentinelOnly" not in text or "if (config.sentinelOnly === true)" not in text:
            print("✗ tool-bootstrap.mjs 未实现 sentinelOnly early-exit")
            ok = False
    except OSError as e:
        print(f"✗ tool-bootstrap.mjs 读取失败: {e}")
        ok = False

    try:
        text = open(creator_preset, "r", encoding="utf-8").read()
        if "sentinelOnly" not in text:
            print("✗ pre-sales-creator/preset.yml 未更新 sentinelOnly 描述")
            ok = False
    except OSError as e:
        print(f"✗ pre-sales-creator/preset.yml 读取失败: {e}")
        ok = False

    if ok:
        print("✓ 创作模式哨兵 sentinelOnly 挂载与描述已就位")
    return ok


def _audit_p0_spec_guide():
    """P0-3：spec-writing-guide 版本号与“10 种合法 type”旧口径。"""
    ok = True
    path = os.path.join(SCRIPT_DIR, ".folio", "skills", "spec-writing-guide", "SKILL.md")
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"✗ spec-writing-guide 读取失败: {e}")
        return False
    m = re.search(r'version:\s*"(\d+)\.(\d+)"', text)
    if not m or (int(m.group(1)), int(m.group(2))) < (1, 8):
        print("✗ spec-writing-guide frontmatter version 未对齐到 1.8")
        ok = False
    if "10 种合法 type" in text or "10种合法 type" in text:
        print("✗ spec-writing-guide 仍有“10 种合法 type”旧口径")
        ok = False
    # 口径锚点随元素全集走：2026-09-07 S8-A 双注册 34→36；S8-B 三件套 36→39
    if "当前 39 种" not in text:
        print("✗ spec-writing-guide 未标明动态/正确元素类型口径")
        ok = False
    if ok:
        print("✓ spec-writing-guide 版本/枚举口径已修复")
    return ok


def _audit_p0_skill_broken_links():
    """P0-3：Skill 内部指向其他 skill 的断链扫描。

    只检查“skill `name`”/“转 `name`”等明显的 Skill 引用，避免把命令/文件名误报。
    """
    import re
    ok = True
    skills_dir = os.path.join(SCRIPT_DIR, ".folio", "skills")
    known = set()
    for name in os.listdir(skills_dir):
        if os.path.isdir(os.path.join(skills_dir, name)):
            known.add(name)
    visited = 0
    for name in sorted(known):
        path = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        visited += 1
        try:
            text = open(path, "r", encoding="utf-8").read()
        except OSError:
            continue
        for m in re.finditer(r"(?:skill|Skill|技能)\s*`([a-zA-Z0-9][a-zA-Z0-9-]*)`", text):
            ref = m.group(1)
            if ref not in known:
                print(f"✗ {name}/SKILL.md 指向不存在 Skill: {ref}")
                ok = False
    if ok:
        print(f"✓ Skill 内部断链扫描通过（{visited} 个 SKILL.md）")
    return ok


def _audit_p0_delivery_decision():
    """P0-3：delivery-pipeline 决策记录是否为当前双入口写法。"""
    import re
    ok = True
    path = os.path.join(SCRIPT_DIR, ".folio", "skills", "delivery-pipeline", "SKILL.md")
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"✗ delivery-pipeline 读取失败: {e}")
        return False
    if "save --decisions" not in text or "theme-guard <客户> --set" not in text:
        print("✗ delivery-pipeline 未使用 save --decisions / theme-guard --set 双入口")
        ok = False
    if re.search(r"record key decisions to `?_knowledge/clients/\{客户\}/decisions\.md", text):
        print("✗ delivery-pipeline 仍保留直接写 decisions.md 旧写法")
        ok = False
    if ok:
        print("✓ delivery-pipeline 决策写法已更新")
    return ok


def _audit_p0_core_command_coverage():
    """P0-3：AGENTS_REFERENCE 核心命令入口覆盖。"""
    ok = True
    path = os.path.join(SCRIPT_DIR, "AGENTS_REFERENCE.md")
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"✗ AGENTS_REFERENCE.md 读取失败: {e}")
        return False
    core = ["session-start", "theme-guard", "confirm", "spec-gen", "html-build",
            "pptd-build", "deliver", "docx-build", "quote-build", "verify",
            "review", "save", "context-health", "skills-sync", "load-skill"]
    missing = [c for c in core if c not in text]
    if missing:
        print(f"✗ AGENTS_REFERENCE 核心命令缺失: {missing}")
        ok = False
    if ok:
        print("✓ AGENTS_REFERENCE 核心命令覆盖")
    return ok


def _audit_p0_file_size_ratchet():
    """P0：单文件体量棘轮闸门（engineering_standards §1.0，2026-08-31 立）。

    棘轮规则——存量挂账、增量归零：
    - 非基线文件 > 1200 行 → FAIL（新文件不允许带债）
    - 基线文件超过各自 cap → FAIL（存量不许继续涨，只许拆小）
    - 基线文件 1200-2000 行 → 仅提示（还债待办，不阻断）
    基线 cap 调整须走 decisions.md（工程化改动协议）。

    扫描范围：根目录 `_*.py`（与 CODEBASE_INDEX 根模块口径一致）+ `_renderer/`
    下全部 `.py`（2026-09-04 起 **递归含子包**，如 `_renderer/diagram/`）。
    2026-09-01 修复：原实现把根模块**文件**路径收进 roots 后用
    `os.path.isdir()` 过滤，导致 62 个根模块全部被跳过（闸门对根模块从未生效）。
    2026-09-04 修复：原实现 listdir 只扫一层，`_renderer/diagram/` 子包整体逃逸。
    """
    import os
    ok = True
    warn_lines, error_lines = 1200, 2000
    caps = _RATCHET_CAPS
    debt = []
    for name in sorted(caps):
        path = os.path.join(SCRIPT_DIR, f"{name}.py")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                n = sum(1 for _ in f)
        except OSError as e:
            print(f"✗ 体量闸门读取失败 {name}: {e}")
            return False
        if n > caps[name]:
            print(f"✗ {name} {n} 行 > 基线 cap {caps[name]}（存量在涨，只许拆小不许加码）")
            ok = False
        elif n > warn_lines:
            debt.append(f"{name} {n} 行")
    for base in (SCRIPT_DIR, os.path.join(SCRIPT_DIR, "_renderer")):
        if not os.path.isdir(base):
            continue
        is_root = (base == SCRIPT_DIR)
        for dirpath, dirnames, filenames in os.walk(base):
            # 根目录不下钻（原行为：只扫顶层 `_*.py`，绝不能伸进 .agents/.scratch 等）；
            # _renderer 子树递归（2026-09-04 盲区修复），剪掉 __pycache__。
            if is_root:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in sorted(dirnames) if d != "__pycache__"]
            rel_dir = os.path.relpath(dirpath, SCRIPT_DIR).replace(os.sep, "/")
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                if is_root:
                    if not fn.startswith("_"):
                        continue
                    key = fn[:-3]
                else:
                    key = f"{rel_dir}/{fn[:-3]}"
                if key in caps:
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        n = sum(1 for _ in f)
                except OSError:
                    continue
                if n > error_lines:
                    print(f"✗ {key} {n} 行 > {error_lines}（非基线超红线，须拆分）")
                    ok = False
                elif n > warn_lines:
                    print(f"✗ {key} {n} 行 > {warn_lines}（新增超限，须拆分或经决策入基线）")
                    ok = False
    if debt:
        print(f"⚠ 体量还债待办（基线存量，允许）：{'、'.join(debt)}")
    if ok:
        print("✓ 文件体量棘轮：无新增超限")
    return ok


def _audit_p0_skills_compliance():
    """P0-5：Agent Skills 规范合规检查：name/description/frontmatter。"""
    import re
    from _skills_sync import _read_frontmatter
    ok = True
    skills_dir = os.path.join(SCRIPT_DIR, ".folio", "skills")
    names = sorted(n for n in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, n)))
    checked = 0
    for name in names:
        path = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        checked += 1
        fm = _read_frontmatter(path)
        if not fm:
            print(f"✗ {name}/SKILL.md 缺少 YAML frontmatter")
            ok = False
            continue
        skill_name = fm.get("name")
        if not skill_name:
            print(f"✗ {name}/SKILL.md 缺少 name")
            ok = False
        elif not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", str(skill_name)):
            print(f"✗ {name}/SKILL.md name 不合规: {skill_name}")
            ok = False
        desc = fm.get("description")
        if desc is None or str(desc).strip() == "":
            print(f"✗ {name}/SKILL.md 缺少 description")
            ok = False
        elif len(str(desc)) > 1024:
            print(f"✗ {name}/SKILL.md description 超 1024 字符（{len(str(desc))}）")
            ok = False
        route = fm.get("route_level")
        if route not in ("mandatory", "optional", "excluded"):
            print(f"✗ {name}/SKILL.md route_level 非法: {route}")
            ok = False
    if ok:
        print(f"✓ Skills 规范合规：{checked} 个 SKILL.md name/description/frontmatter/route_level 合规")
    return ok



# ── 批5（2026-09-05）：知识层检查（C2 + S11，只报不判）──
# 术语/锚点漂移本身仅 WARN，不影响审计结论；但基础设施缺失（总纲读取失败、
# domains / .folio/skills 目录不存在）返回 False 计 FAIL（_cli_audit.py 消费）。

_CN_DIGITS = "零一二三四五六七八九十"


def _cn_to_num(s):
    """中文数字（一~十九）→ 阿拉伯；无法转换返回 None。"""
    if s in _CN_DIGITS:
        return _CN_DIGITS.index(s)
    if s.startswith("十") and len(s) == 2 and s[1] in _CN_DIGITS:
        return 10 + _CN_DIGITS.index(s[1])
    return None


def _num_to_cn(n):
    """阿拉伯（1-19）→ 中文数字；超出范围返回 None。"""
    n = int(n)
    if 0 <= n <= 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    return None


def _parse_glossary_terms(glossary_path):
    """解析方法总纲 §8 标准名登记表 → [(标准名, [别名...])]。

    只认「标准名 | 别名/客户叫法 | 定义出处」表头的 Markdown 表格；
    别名单元格按 / 切分。无表 → 空表（跳过扫描，不发明规则）。
    """
    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    rows, in_table = [], False
    for line in lines:
        if not in_table:
            if line.strip().startswith("|") and "标准名" in line and "别名" in line:
                in_table = True
            continue
        if not line.strip().startswith("|"):
            in_table = False
            continue
        if re.match(r"\|\s*-", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] and cells[1]:
            rows.append((cells[0], [a for a in (x.strip() for x in cells[1].split("/")) if a]))
    return rows


def _audit_knowledge_terms_drift(glossary_path=None, domains_dir=None):
    """C2 术语漂移扫描（总方案 §9.2 + §8 全局 glossary 规则）。

    漂移本身 WARN 不 FAIL；基础设施缺失（总纲读取失败/目录不存在）返回 False。

    判：域卡某行使用了总纲登记的别名/旧称，且同行不含标准名 → 术语漂移 WARN
    （卡名/行号/旧称/标准名）。
    不判：同行兼含标准名与别名 = 别名映射（各卡「客户口语 → 标准名词」速查表
    的真实形态），视为已映射放行；总纲未登记的用词不判（宁缺毋滥）。
    """
    if glossary_path is None:
        glossary_path = os.path.join(
            SCRIPT_DIR, "_knowledge", "methodology", "meta", "方法总纲与术语表.md")
    if domains_dir is None:
        domains_dir = os.path.join(SCRIPT_DIR, "_knowledge", "domains")
    terms = _parse_glossary_terms(glossary_path)
    if terms is None:
        print("✗ 术语漂移扫描：方法总纲读取失败")
        return False
    if not terms:
        print("ℹ 术语漂移扫描：总纲无标准名登记表，跳过")
        return True
    if not os.path.isdir(domains_dir):
        print("✗ 术语漂移扫描：_knowledge/domains/ 不存在")
        return False

    warned = 0
    for fn in sorted(os.listdir(domains_dir)):
        if not fn.endswith(".md"):
            continue
        path = os.path.join(domains_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                card_lines = f.read().splitlines()
        except OSError:
            continue
        for ln, line in enumerate(card_lines, 1):
            for std, aliases in terms:
                if std in line:
                    continue  # 同行含标准名 = 别名映射行（速查表/名词表），放行
                for alias in aliases:
                    if alias in line:
                        print(f"  ⚠ [{fn}:{ln}] 术语漂移：用了旧称「{alias}」且无别名映射"
                              f"（标准名「{std}」）")
                        warned += 1
    print(f"✓ 术语漂移扫描完成（标准名 {len(terms)} 条，⚠ {warned} 项警告级，不影响审计结论）")
    return True


# skill 文本中对 L2/L3 的文件锚形态：`_knowledge/methodology|domains/....md`
_KNOW_PATH_RE = re.compile(
    r"_knowledge/(?:methodology|domains)/[^\s`）)】」，。；;\"'#§]+?\.md")
# 文件锚同行的章节锚形态：§4 / §一（首个 § 即本节引用，`.md` #7 死法编号不判）
_KNOW_SEC_RE = re.compile(r"§(\d+|[一二三四五六七八九十]+)")


def _audit_knowledge_anchor_integrity(skills_dir=None, script_dir=None):
    """S11 锚点完整性检查（v0.2 §2.6 锚点治理三件套之三）。

    漂移本身 WARN 不 FAIL；基础设施缺失（.folio/skills 不存在）返回 False。

    判：`.folio/skills/**/*.md` 中对 `_knowledge/methodology|domains/` 的
    ①文件锚——目标文件不存在 → WARN；
    ②章节锚（文件锚同行首个 §N/§一）——目标文件无对应小节标题 → WARN。
    小节标题机械匹配 `^#{1,6}\\s*<序号>[\\.、\\s]`，阿拉伯/中文数字互为变体
    （真实形态两轨并存：总纲 `## 4.`、规划方法 `## 四、`）。
    不判：非全路径引用（如 `meta/xxx.md` 简写、`requirements.md` §2 同包引用）、
    `.md` #7 死法编号——提取不了的不发明规则（宁缺毋滥）。
    """
    if script_dir is None:
        script_dir = SCRIPT_DIR
    if skills_dir is None:
        skills_dir = os.path.join(script_dir, ".folio", "skills")
    if not os.path.isdir(skills_dir):
        print("✗ 锚点完整性检查：.folio/skills/ 不存在")
        return False

    checked, warned = 0, 0
    for dirpath, _dirs, files in os.walk(skills_dir):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            rel_src = os.path.relpath(path, script_dir)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src_lines = f.read().splitlines()
            except OSError:
                continue
            for ln, line in enumerate(src_lines, 1):
                matches = list(_KNOW_PATH_RE.finditer(line))
                for i, m in enumerate(matches):
                    checked += 1
                    target_rel = m.group(0)
                    target_path = os.path.join(script_dir, target_rel)
                    if not os.path.isfile(target_path):
                        print(f"  ⚠ [{rel_src}:{ln}] 失效文件锚：{target_rel}（目标不存在）")
                        warned += 1
                        continue
                    seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
                    sm = _KNOW_SEC_RE.search(line[m.end():seg_end])
                    if not sm:
                        continue
                    tok = sm.group(1)
                    variants = [tok]
                    if tok.isdigit():
                        cn = _num_to_cn(tok)
                        if cn:
                            variants.append(cn)
                    else:
                        num = _cn_to_num(tok)
                        if num is not None:
                            variants.append(str(num))
                    with open(target_path, "r", encoding="utf-8") as f:
                        target_text = f.read()
                    hit = any(
                        re.search(rf"(?m)^#{{1,6}}\s*{re.escape(v)}[\.、\s]", target_text)
                        for v in variants)
                    if not hit:
                        print(f"  ⚠ [{rel_src}:{ln}] 失效章节锚：{target_rel} §{tok}"
                              "（目标文件无此小节）")
                        warned += 1
    print(f"✓ 锚点完整性检查完成（文件锚 {checked} 处，⚠ {warned} 项警告级，不影响审计结论）")
    return True
