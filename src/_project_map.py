# -*- coding: utf-8 -*-
"""项目地图生成器：扫描根目录 *_py 与 _renderer/*.py，产出单文件交互式 HTML 地图。

用法：.venv/Scripts/python.exe _project_map.py
输出：docs/项目地图.html（file:// 直开，无外部依赖，随代码重跑刷新）

设计约束：
- 只做静态观测，不 import 项目模块（防副作用），全部 ast/regex 提取。
- 模块归属六大域手工维护（DOMAIN），比正则猜更稳；新模块落"其他"域并打印提醒。
- 体量闸门预览：>1200 行 warning 高亮、>2000 行 error 红框（与 engineering_standards §1.0 同步）。
"""
import ast
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "项目地图.html"
WARN_LINES, ERROR_LINES = 1200, 2000

# ── 六大域（顺序即页面展示顺序）──────────────────────────────────────────
DOMAINS = [
    ("entry",  "入口与编排", "用户敲下 python _cli.py <命令> 后，先到这里；决定走不走流程、拦不拦截。",
     "前台与总调度：你的每个命令从这里进、从这里分派给对的人。"),
    ("gen",    "生成线",     "把客户材料/大纲变成 spec 契约，再把 spec 变成 HTML/PPT/报价草案。",
     "写方案的团队：从想法到施工图纸（spec），再到方案/报价半成品。"),
    ("render", "渲染与视觉", "spec 的唯一消费者；主题、版式、图形、三端（HTML/PPT/DOCX）差异都在这层。",
     "排版印刷车间：把图纸变成好看的成品（网页/PPT/Word）。"),
    ("know",   "知识检索",   "客户材料进来、证据片段出去；BM25+向量双路，回答'之前做过类似的吗'。",
     "档案室：存着你的历史与客户材料，要什么翻什么。"),
    ("mem",    "会话与记忆", "跨会话记住客户上下文、决策、主题铁律；会话开始加载、结束落盘。",
     "助理的记忆：记住每个客户聊过什么、定过什么、做到哪一步了。"),
    ("guard",  "质检与防线", "verify/review/style_guard 三道闸 + audit 总检；AI 写的代码由它们兜底。",
     "质检科和保安：不合格不让出厂，危险操作有人拦。"),
]

# 手工归属表：模块名（不含 .py）→ 域 id。未列出的落 other 并在生成时提醒。
DOMAIN_MAP = {
    # 入口与编排
    "_cli": "entry", "_cli_generate": "entry", "_cli_audit": "entry",
    "_cli_generate_build": "entry",  # R3-1 拆小：构建族七命令实现体
    "_cli_generate_deliver": "entry",  # R3-1 拆小：deliver 编排 + receipt
    "_cli_guards": "entry", "_cli_infra": "entry", "_aliases": "entry",
    "_pipeline": "entry", "_skills_sync": "entry",
    "_cli_cmds_mem": "entry", "_cli_cmds_qa": "entry",
    "_cli_cmds_idx": "entry", "_cli_cmds_gen": "entry",
    "_cli_cmds_recall_v2": "entry", "_cli_audit_p0": "entry",
    "_cli_audit_behavior": "entry", "_spec_drift_gate": "entry",
    # 生成线
    "_outline_to_spec": "gen", "_spec_edit": "gen", "_bid_parse": "gen",
    "_diagram_extract": "gen", "_narrative_apply": "gen",
    "_quote_spec_gen": "gen", "_quote_engine": "gen", "_quote_data": "gen",
    "_quote_html": "gen", "_quote_gate": "gen",
    "_pptd": "gen", "_pptd_gen": "gen", "_pptd_convert": "gen",
    "_pptd_parts": "gen",
    # 渲染与视觉
    "_theme_guard": "render", "_layout_lint": "render",
    # 知识检索
    "_recall": "know", "_recall_eval": "know", "_embed_index": "know",
    "_bm25": "know", "_graph": "know", "_worldbook": "know",
    "_semantic_catalog": "know", "_indexer": "know", "_doc_extract": "know",
    "_classify": "know", "_compress": "know", "_density": "know",
    "_snippet": "know", "_cloud_llm": "know",
    "_cloud_llm_search": "know", "_cloud_llm_vision": "know",
    "_cloud_transport": "know",
    "_query_rewrite": "know", "_query_trace": "know",
    # 会话与记忆
    "_session": "mem", "_context": "mem", "_context_health": "mem",
    "_memory_guard": "mem", "_save_lock": "mem", "_reflect": "mem",
    "_state": "mem", "_inbox_scan": "mem", "_archive_auto": "mem",
    "_onboard": "mem", "_backup": "mem", "_inbox_registry": "mem",
    # 质检与防线
    "_verify": "guard", "_verify_hook": "guard", "_review": "guard",
    "_style_guard": "guard", "_spec_diff": "guard", "_doctor": "guard",
    "_verify_checks": "guard", "_domain_guard": "guard", "_fact_guard": "guard",
    "_verify_evidence": "guard", "_verify_diagram": "guard",
    "_verify_desens": "guard",  # S8-B 棘轮拆小：C-E5 脱敏扫描自 _verify 外迁
    "_review_screenshot": "guard", "_review_gate": "guard",  # S9-2a/2d：截图对抗审视 + crafted 禁直出门
    "_review_parallel": "guard",  # WP-A5 R1 拆小：并行两族自 _review 外迁
    "_review_incremental": "guard",  # WP-A5 R1：增量审查（同文件迭代复审，快照+3轮全量）
    "_cli_audit_track": "entry", "_crafted_brief": "guard",  # S9-2b 轨一致性 audit / S9-2c 简报五件套机检
    "_breeding": "guard",  # S10-3a 育种登记闭环 + 3e TTL 机检（观察治理；_verify_desens 外迁先例，guard 域）
    "_paths": "guard",  # 路径契约被所有防线依赖
    "_project_map": "guard",  # 本生成器：观测工具，与 audit 同属防线域
}

# 关键模块的一句话职责（覆盖 docstring 的场合 / docstring 过长时截断）；没写的用 docstring。
DESC_OVERRIDE = {
    "_cli": "唯一命令入口：60 个子命令的注册与分发，只做参数解析，业务都在下游模块",
    "_cli_guards": "硬门禁所在地：confirmed:true / load-skill 哨兵 / REQUIRED_GEN_SKILLS 清单",
    "_cli_audit": "audit 总检：P0 逐项机检（路由表/哨兵/版本断言/断链），规范的执行者",
    "_cli_generate": "生成线共享助手真源 + review/confirm + cmd_* 分派（R3-1 拆小后）",
    "_cli_generate_build": "构建族七命令实现体：html-build/quote-build/spec-gen/docx-build/outline-to-spec/pptd-gen/pptd-build（R3-1 拆小，打桩面经 _g. 属性解析）",
    "_cli_generate_deliver": "deliver 一键编排 + receipt sidecar + venv 解释器定位（R3-1 拆小）",
    "_renderer_schema": "渲染端校验核心：PAGE_LAYOUTS / COMPOSITIONS / DIAGRAM_SCHEMA 全在这",
    "_renderer": "渲染门面：三端（HTML/PPTD/DOCX）渲染调度与能力矩阵打印",
    "_theme_guard": "客户永久铁律：HEAD 注入 + theme-verify 关键词覆盖检查",
    "_quote_gate": "报价门禁：报价生成前的机检拦截",
    "_recall": "知识召回主引擎：BM25 关键词 + embedding 语义双路融合",
    "_session": "会话 facade：session-start / save 的聚合层（star import 聚合 _context/_graph/_recall）",
    "_cloud_llm": "云端 LLM 适配：rerank/语义调用的外部请求都在这",
    "_paths": "路径契约：全部目录常量的唯一出处，谁都不许手写路径",
    "_skills_sync": "skill 双树同步：.folio（事实源）→ .agents（派生），并生成路由表",
}

# 人话词典（2026-08-31 用户要求）：mod_id → 大白话职责，面向非技术阅读；
# 模块卡以人话为主行、技术描述降为灰色小字。新模块未写人话则只显示技术描述。
PLAIN_TALK = {
    # 入口与编排
    "_cli": "前台总机：你敲的所有命令都从这进，它分派给对应的同事",
    "_cli_generate": "总包工头：「做方案/做报价」这类命令的具体指挥官，调度各条生产线",
    "_cli_generate_build": "施工队：html-build/quote-build/pptd 系列命令的具体活计在这干",
    "_cli_generate_deliver": "交付调度员：一条龙跑完网页和 PPT，中途停下来等你签字确认",
    "_cli_audit": "内部稽核队长：定期体检整个项目，规范有没有被违反它说了算",
    "_cli_guards": "出厂检查岗：方案确认没确认、该读的说明书读了没，不合格它拦下",
    "_cli_infra": "开机自检：启动时加载配置、检查环境、保证中文不乱码",
    "_aliases": "外号登记簿：「蓝海/CTQ/蓝海集团」都指同一家客户，防止认错人",
    "_pipeline": "翻译官：Word/PDF/PPT/Excel 统一翻译成纯文字供后面使用",
    "_skills_sync": "技能搬运工：把说明书库从事实源同步到 AI 读取的地方",
    # 生成线
    "_outline_to_spec": "策划：把想法和客户材料整理成一份「施工图纸」（每页写什么）",
    "_spec_edit": "图纸修改员：图纸要改一页/加一段，用它改不会改坏别处",
    "_bid_parse": "标书解读员：帮你看懂招标文件要什么、怎么评分、什么会废标",
    "_quote_spec_gen": "报价项提取员：从材料里把「要报哪些价」挑出来",
    "_quote_engine": "报价 Excel 装订机：把报价数据排成正式的 Excel 表",
    "_quote_data": "报价资料库：存着你历史报价的内容和价格素材",
    "_quote_html": "报价网页排版：生成可打印成 PDF 的网页版报价单",
    "_quote_gate": "报价合规门：出报价前查一遍价格口径，不对就拦下",
    "_pptd": "PPT 流水线调度：PPT 从毛坯到成品的工序管理",
    "_pptd_gen": "PPT 毛坯生成：先确定每页放什么搭出空架子（不用 AI，可重跑）",
    "_pptd_convert": "PPT 精装修：把毛坯变成真正的 .pptx 文件",
    # 渲染与视觉
    "_renderer": "排版车间：按图纸把方案做成好看的网页，配色字体版式全按规范",
    "_renderer/__init__": "车间总装线：渲染调度主入口",
    "_renderer/schema": "图纸审核员：图纸字段/版式/图形的合法性全归它管",
    "_renderer/elements": "零件规格书：36 种内容零件怎么渲染、缺料怎么降级",
    "_renderer/theme": "配色方案册：6 套主题的唯一定义处",
    "_renderer/page_chrome": "页面装修工：页眉页脚、标题条这些固定装饰",
    "_renderer/html_editor_injector": "编辑器安装工：给成品网页装上「可直接改字」的工具条",
    "_renderer/docx_com_postprocess": "Word 精修工：用 Word 自身能力修编号/目录/页眉",
    "_renderer/spacing": "间距尺子：所有间距的统一刻度",
    "_layout_lint": "版式巡检：查字有没有出框、页面会不会太空太挤",
    # 知识检索
    "_recall": "找材料的人：你说个事儿，它去档案里翻出最相关的几段给你",
    "_recall_eval": "考官：定期测「找材料」找得准不准，退步了会报警",
    "_embed_index": "意思索引卡：按「说的是同一回事」建立检索卡片",
    "_bm25": "关键词索引卡：按字面关键词建立检索卡片",
    "_graph": "客户履历时间线：这个客户做过什么、先后关系如何",
    "_worldbook": "客户全景一页纸：把客户所有关键信息浓缩成一页",
    "_semantic_catalog": "能力目录管理员：管着一份「我们会做什么」的清单（已设计冻结）",
    "_indexer": "贴标签的：给每份材料写摘要贴标签方便检索",
    "_doc_extract": "拆文件提取员：一键把各种文件的内容抽出来",
    "_classify": "收发室分拣员：你丢进收件箱的文件，自动分给对应客户",
    "_compress": "浓缩机：太长的记录压缩成短摘要，省空间省注意力",
    "_density": "页面胖瘦检查：查做出来的页面是不是太空或太挤",
    "_snippet": "好句收藏夹：验证通过的方案片段自动收藏，供日后检索",
    "_cloud_llm": "外请专家：需要动脑的活（总结/改写/判断）打电话给云端大模型",
    # 会话与记忆
    "_session": "会谈记录员：「保存一下」就是它，把这次聊的定下的全记下来",
    "_context": "笔记本管理员：下次见客户前，把笔记里相关的内容翻出来",
    "_context_health": "开工前体检：干活前检查「该看的材料都看了没」",
    "_memory_guard": "证据保安：写进记忆的每条结论都要有出处，防编造",
    "_save_lock": "防打架锁：同时保存同一个客户时加锁，防止文件写坏",
    "_reflect": "复盘助理：会话结束提炼「这次学到什么」，生成待确认的决策",
    "_state": "进度公告牌：这个客户的方案做到哪一步了（接单→出图→交付）",
    "_inbox_scan": "收件箱巡逻员：定期检查收件箱有没有该处理没处理的",
    "_archive_auto": "归档小助手：会话结束自动把材料归到客户名下",
    "_onboard": "报到办理员：新客户一来，一键建档案、分类材料、出初稿",
    "_backup": "备份员：动生成类操作前先把旧文件留底，坏了能退回",
    # 质检与防线
    "_verify": "成品质检员：方案交付前强制过检（错字/AI 味/废标风险）",
    "_verify_hook": "质检记录员：执行质检、写检验记录、更新任务台账",
    "_review": "独立评审专家：另请一个 AI 挑刺，只找问题不打分",
    "_style_guard": "去 AI 味检查：专揪「赋能/抓手」这类机器腔",
    "_spec_diff": "图纸对比员：两版施工图纸哪里改了，一目了然",
    "_doctor": "体检医生：查环境装没装对、钥匙有没有失效",
    "_paths": "地址簿：全项目所有「东西放哪」的唯一出处",
    "_project_map": "摄影师：拍下这张项目地图（就是本工具自己）",
}

# 命令旅程：展示顺序即叙事顺序；footprint 从 cmd_ 函数体静态提取。
TRACES = ["html-build", "spec-gen", "session-start", "save"]


def module_desc(mod_id: str, doc: str) -> str:
    key = mod_id.replace("/", "_").lstrip("_") if mod_id.startswith("_renderer/") else mod_id
    key = mod_id.replace("/", "_")
    if key in DESC_OVERRIDE:
        return DESC_OVERRIDE[key]
    if doc:
        return doc
    return "（无 docstring——补一句职责描述，这是规范要求）"


def scan_module(path: Path) -> dict:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.count("\n") + 1
    doc = ""
    imports, classes, funcs = set(), 0, 0
    try:
        tree = ast.parse(src, filename=str(path))  # filename 使转义警告归属到真实文件
        doc = (ast.get_docstring(tree) or "").strip().split("\n")[0]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("_"):
                        imports.add(a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("_"):
                    imports.add(node.module)
            elif isinstance(node, ast.ClassDef):
                classes += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs += 1
    except SyntaxError:
        pass
    mod_id = path.stem if path.parent == ROOT else f"_renderer/{path.stem}"
    domain = DOMAIN_MAP.get(mod_id if not mod_id.startswith("_renderer") else "_renderer")
    if mod_id.startswith("_renderer/"):
        domain = "render"
    return {
        "id": mod_id, "file": str(path.relative_to(ROOT)), "lines": lines,
        "doc": doc, "plain": PLAIN_TALK.get(mod_id, ""),
        "imports": sorted(i for i in imports if i != mod_id.split("/")[0] or True),
        "classes": classes, "funcs": funcs, "domain": domain or "other",
    }


def scan_commands() -> list:
    src = (ROOT / "_cli.py").read_text(encoding="utf-8", errors="replace")
    cmds = []
    # 命令名 + help
    helps = {}
    for m in re.finditer(r'add_parser\(\s*"([^"]+)"[^)]*?help="([^"]*)"', src, re.S):
        helps[m.group(1)] = m.group(2)
    # cmd_ 函数体及其引用的模块
    spans = [(m.group(1), m.start()) for m in re.finditer(r"^def (cmd_\w+)\(", src, re.M)]
    spans.append(("", len(src)))
    footprints = {}
    for i in range(len(spans) - 1):
        name, s = spans[i]
        body = src[s:spans[i + 1][1]]
        seen = []
        for mm in re.finditer(r"\b(_[a-z][a-z_0-9]*)\.", body):
            if mm.group(1) not in seen:
                seen.append(mm.group(1))
        footprints[name] = seen
    # add_parser 顺序映射到 cmd_ 函数（同名转换：html-build → cmd_html_build）
    for name, help_txt in helps.items():
        fn = "cmd_" + name.replace("-", "_")
        cmds.append({"name": name, "help": help_txt,
                     "mods": footprints.get(fn, [])})
    return cmds


def build_trace(cmd: dict, modules: dict) -> list:
    steps = []
    for m in cmd["mods"]:
        node = modules.get(m) or modules.get(m.replace("_renderer_", "_renderer/"))
        if node is None:
            # 可能是 _renderer 下的子模块引用，折叠为 _renderer
            if m.startswith("_renderer"):
                node = modules.get("_renderer")
        if node:
            steps.append({"id": node["id"], "domain": node["domain"]})
    # 去重保序
    out, seen = [], set()
    for s in steps:
        if s["id"] not in seen:
            seen.add(s["id"])
            out.append(s)
    return out


def main():
    files = sorted(ROOT.glob("_*.py")) + sorted((ROOT / "_renderer").glob("*.py"))
    nodes = [scan_module(p) for p in files]
    modules = {n["id"]: n for n in nodes}
    unmapped = [n["id"] for n in nodes if n["domain"] == "other"]
    cmds = scan_commands()
    traces = []
    for t in TRACES:
        c = next((c for c in cmds if c["name"] == t), None)
        if c:
            traces.append({"cmd": t, "help": c["help"], "steps": build_trace(c, modules)})

    stats = {
        "modules": len(nodes), "total_lines": sum(n["lines"] for n in nodes),
        "commands": len(cmds),
        "tests": len(list((ROOT / "tests").glob("test_*.py"))),
        "docstring_pct": round(100 * sum(1 for n in nodes if n["doc"]) / max(len(nodes), 1)),
        "over_warn": sorted([n["id"] for n in nodes if n["lines"] > WARN_LINES],
                            key=lambda x: -modules[x]["lines"]),
        "over_error": sorted([n["id"] for n in nodes if n["lines"] > ERROR_LINES],
                             key=lambda x: -modules[x]["lines"]),
    }
    data = {
        "generated": datetime.date.today().isoformat(),
        "domains": [{"id": d, "name": n, "why": w, "plain": p} for d, n, w, p in DOMAINS],
        "nodes": nodes, "stats": stats, "traces": traces,
        "thresholds": {"warn": WARN_LINES, "error": ERROR_LINES},
    }
    html = HTML_SHELL.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"✓ 已生成 {OUT}（{len(nodes)} 模块 / {len(cmds)} 命令 / {len(traces)} 条旅程）")
    if unmapped:
        print(f"⚠ 未归域模块（落到'其他'，请补 DOMAIN_MAP）：{'、'.join(unmapped)}")
    if stats["over_error"]:
        print(f"🔴 超 {ERROR_LINES} 行（error）：{'、'.join(stats['over_error'])}")
    if stats["over_warn"]:
        print(f"🟡 超 {WARN_LINES} 行（warn）：{'、'.join(stats['over_warn'])}")


HTML_SHELL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>售前助手 · 项目地图</title>
<style>
:root{--bg:#0e1116;--panel:#161b23;--line:#242c38;--tx:#d7dee8;--dim:#8a97a8;
--blue:#4f8ff7;--teal:#3fb6a8;--amber:#e0a34e;--red:#e0644e;--green:#59b96f;--purple:#9a7de0}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:15px/1.7 "Microsoft YaHei",system-ui,sans-serif;padding:32px 20px;max-width:1200px;margin:0 auto}
h1{font-size:26px;margin-bottom:4px}
h2{font-size:20px;margin:40px 0 6px;padding-left:10px;border-left:4px solid var(--blue)}
h3{font-size:16px;margin:18px 0 8px}
.sub{color:var(--dim);font-size:13px;margin-bottom:8px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-top:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;margin-top:12px}
.dom{cursor:pointer;transition:border-color .15s}
.dom:hover{border-color:var(--blue)}
.dom h3{margin:0 0 4px}
.dom .cnt{float:right;color:var(--dim);font-size:13px}
.why{color:var(--dim);font-size:13px}
.trace{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px}
.step{background:#1b2330;border:1px solid var(--line);border-radius:6px;padding:4px 10px;font-size:13px;cursor:pointer}
.step:hover{border-color:var(--blue)}
.arrow{color:var(--dim)}
.fcard{border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin-top:8px;background:var(--panel)}
.fcard.warn{border-left:4px solid var(--amber)}
.fcard.error{border-left:4px solid var(--red)}
.fhead{display:flex;align-items:baseline;gap:10px;cursor:pointer}
.fname{font-weight:600;font-family:Consolas,monospace}
.flines{color:var(--dim);font-size:12px}
.fdesc{color:var(--tx);font-size:13.5px;margin-top:4px}
.fdetail{display:none;margin-top:8px;border-top:1px dashed var(--line);padding-top:8px;font-size:13px}
.fcard.open .fdetail{display:block}
.imp{display:inline-block;background:#1b2330;border:1px solid var(--line);border-radius:4px;
padding:1px 8px;margin:2px 4px 2px 0;font-size:12px;font-family:Consolas,monospace;cursor:pointer}
.imp:hover{border-color:var(--blue);color:var(--blue)}
.badge{display:inline-block;border-radius:4px;padding:1px 8px;font-size:12px;margin-left:8px}
.badge.warn{background:#3a2f1a;color:var(--amber)}
.badge.error{background:#3a201a;color:var(--red)}
.hidden{display:none!important}
.filter{margin:10px 0}
.filter button{background:var(--panel);border:1px solid var(--line);color:var(--tx);
border-radius:6px;padding:5px 14px;margin-right:6px;cursor:pointer;font-size:13px}
.filter button.on{border-color:var(--blue);color:var(--blue)}
.stats{display:flex;gap:22px;flex-wrap:wrap;color:var(--dim);font-size:13px;margin-top:6px}
.stats b{color:var(--tx)}
.readpath li{margin:6px 0 6px 18px}
.legend{font-size:12px;color:var(--dim)}
</style></head><body>
<h1>售前助手 · 项目地图</h1>
<div class="sub">由 <code>_project_map.py</code> 自动生成于 <span id="gen"></span> ·
重跑命令：<code>.venv/Scripts/python.exe _project_map.py</code> · 数据与代码同源，过期即重跑</div>

<h2>这个项目是什么</h2>
<div class="card">一条把<b>客户材料</b>变成<b>可交付方案</b>的生产线：材料入库 → 需求/架构分析 →
写成 <code>spec.yml</code> 契约（confirmed 门禁）→ 渲染出 HTML/PPT/DOCX/报价。
你（人类）在两个点签字：<b>spec 确认</b>与 <b>HTML 交付确认</b>，其余环节由机器闸门兜底。</div>
<div class="stats" id="stats"></div>

<h2>六大模块域：谁负责什么、为什么存在</h2>
<div class="grid" id="domains"></div>

<h2>一个命令的旅程</h2>
<div class="card" id="traces"></div>

<h2>全部模块（点卡片下钻 · 红框=超 2000 行 · 黄条=超 1200 行）</h2>
<div class="filter" id="filter"></div>
<div id="files"></div>

<h2>你该怎么看这张图</h2>
<div class="card"><ol class="readpath">
<li><b>先看上面六大域</b>——10 秒建立全景：任何需求先判断落在哪个域。</li>
<li><b>再挑一条命令旅程</b>——看懂"一个请求经过哪些站"，改动的传播路径就是它。</li>
<li><b>然后按域下钻文件卡</b>——只细读你要动的那一域；每个卡片的"为什么存在"比文件名重要。</li>
<li><b>看完你能做的决策</b>：加功能 → 先找所属域的既有文件改，而不是新建（规范 §1.0）；
排查问题 → 沿命令旅程逐站查；评估风险 → 看目标模块被谁依赖（入度）。</li>
</ol></div>

<script>
const D = __DATA__;
document.getElementById('gen').textContent = D.generated;

// 统计条
const s = D.stats;
document.getElementById('stats').innerHTML =
 `<span>模块 <b>${s.modules}</b></span><span>总行数 <b>${s.total_lines.toLocaleString()}</b></span>`+
 `<span>CLI 命令 <b>${s.commands}</b></span><span>测试文件 <b>${s.tests}</b></span>`+
 `<span>docstring 覆盖 <b>${s.docstring_pct}%</b></span>`+
 `<span>🔴 超 ${D.thresholds.error} 行：<b>${s.over_error.join('、')||'无'}</b></span>`+
 `<span>🟡 超 ${D.thresholds.warn} 行：<b>${s.over_warn.length} 个</b></span>`;

// 六大域
const domEl = document.getElementById('domains');
D.domains.forEach(d=>{
  const ns = D.nodes.filter(n=>n.domain===d.id);
  const lines = ns.reduce((a,n)=>a+n.lines,0);
  const div = document.createElement('div');
  div.className='card dom'; div.onclick=()=>filterTo(d.id);
  div.innerHTML=`<h3>${d.name}<span class="cnt">${ns.length} 模块 / ${lines.toLocaleString()} 行</span></h3>
   <div class="fdesc">🗣 ${d.plain}</div>
   <div class="why">为什么存在：${d.why}</div>
   <div class="why" style="margin-top:6px">成员：${ns.map(n=>n.id.replace('_renderer/','renderer·')).join('、')}</div>`;
  domEl.appendChild(div);
});

// 命令旅程
const trEl = document.getElementById('traces');
D.traces.forEach(t=>{
  const box=document.createElement('div');
  box.innerHTML=`<h3>python _cli.py <span style="color:var(--blue)">${t.cmd}</span>
   <span class="sub" style="display:inline">—— ${t.help||''}</span></h3>
   <div class="trace"><span class="step">入口 _cli.py</span><span class="arrow">→</span>`+
   t.steps.map(st=>{const pn=(D.nodes.find(x=>x.id===st.id)||{}).plain||'';
    return `<span class="step" title="${pn}" onclick="jump('${st.id}')">${st.id}</span>`;}).join(`<span class="arrow">→</span>`)+
   `</div>`;
  trEl.appendChild(box);
});

// 过滤器
const fEl=document.getElementById('filter');
const mkBtn=(label,fn,on)=>{const b=document.createElement('button');b.textContent=label;
 if(on)b.className='on';b.onclick=()=>{[...fEl.children].forEach(x=>x.classList.remove('on'));
 b.classList.add('on');fn();};fEl.appendChild(b);return b;};
function filterTo(dom){ applyFilter(n=>n.domain===dom); 
 [...fEl.children].forEach(x=>x.classList.remove('on'));
 const btn=[...fEl.children].find(b=>b.textContent.includes(D.domains.find(d=>d.id===dom).name));
 if(btn)btn.classList.add('on'); window.scrollTo({top:fEl.offsetTop-80,behavior:'smooth'});}
function applyFilter(pred){document.querySelectorAll('.fcard').forEach(c=>{
 const n=D.nodes.find(x=>x.id===c.dataset.id); c.classList.toggle('hidden',!pred(n));});}

// 文件卡
const filesEl=document.getElementById('files');
const domName=Object.fromEntries(D.domains.map(d=>[d.id,d.name]));
D.nodes.slice().sort((a,b)=>a.domain===b.domain? b.lines-a.lines : D.domains.findIndex(d=>d.id===a.domain)-D.domains.findIndex(d=>d.id===b.domain))
.forEach(n=>{
  const cls = n.lines>D.thresholds.error?'error':(n.lines>D.thresholds.warn?'warn':'');
  const usedBy = D.nodes.filter(x=>x.imports.some(i=>i===n.id||i.startsWith(n.id+'/')||(n.id!=='_renderer'&&x.imports.includes(n.id))));
  const card=document.createElement('div');
  card.className='fcard '+cls; card.dataset.id=n.id;
  card.innerHTML=`<div class="fhead" onclick="this.parentNode.classList.toggle('open')">
    <span class="fname">${n.id}</span><span class="flines">${n.file} · ${n.lines.toLocaleString()} 行 · ${n.classes}类/${n.funcs}函数</span>
    ${n.lines>D.thresholds.error?`<span class="badge error">超限 ${n.lines} &gt; ${D.thresholds.error}</span>`:n.lines>D.thresholds.warn?`<span class="badge warn">超限</span>`:''}
    <span class="flines">域：${domName[n.domain]||'其他'}</span></div>
   <div class="fdesc">${n.plain?`🗣 ${n.plain}`:''}</div>
   <div class="fdesc" style="color:var(--dim);font-size:12.5px">${n.plain?'技术版：':''}${n.desc}</div>
   <div class="fdetail">
    <b>它 import 谁（它依赖谁）：</b>${n.imports.length?n.imports.map(i=>`<span class="imp" onclick="jump('${i}')">${i}</span>`).join(''):'<span class="flines">无本地依赖</span>'}<br>
    <b>谁 import 它（改动会影响谁）：</b>${usedBy.length?usedBy.map(u=>`<span class="imp" onclick="jump('${u.id}')">${u.id}</span>`).join(''):'<span class="flines">暂无（叶子模块，改动最安全）</span>'}
   </div>`;
  filesEl.appendChild(card);
});
function jump(id){const c=document.querySelector(`.fcard[data-id="${id}"]`);
 if(!c)return; applyFilter(n=>true);
 [...fEl.children].forEach(x=>x.classList.remove('on'));
 c.classList.add('open'); c.scrollIntoView({behavior:'smooth',block:'center'});
 c.style.borderColor='var(--blue)'; setTimeout(()=>c.style.borderColor='',1600);}

// 默认过滤器按钮
mkBtn('全部',()=>applyFilter(n=>true),true);
D.domains.forEach(d=>mkBtn(d.name,()=>applyFilter(n=>n.domain===d.id)));
mkBtn('其他',()=>applyFilter(n=>!D.domains.some(d=>d.id===n.domain)));
</script></body></html>
"""

if __name__ == "__main__":
    main()
