# -*- coding: utf-8 -*-
"""原型生成器统一命令面板。
纯 argparse 包装现有模块，零新依赖。"""
import os
import sys
import argparse


from _cli_audit import cmd_audit, cmd_cite_audit, cmd_key_doctor, cmd_theme_verify
from _cli_generate import (
    cmd_html_build, cmd_ppt_build, cmd_ppt_page, cmd_docx_build,
    cmd_quote_build, cmd_spec_gen, cmd_outline_to_spec,
    cmd_review, cmd_html_to_ppt, cmd_pptd_build,
    cmd_pptd_gen, cmd_deliver, cmd_confirm,
)
from _spec_diff import cmd_spec_diff
from _state import STAGES

from _cli_cmds_mem import (
    cmd_status, cmd_state, cmd_pending, cmd_load, cmd_memory_health,
    cmd_save, cmd_resolve_conflict, cmd_classify, cmd_archive_note,
    cmd_inbox_scan, cmd_me, cmd_new, cmd_compact, cmd_theme_guard,
    cmd_context_health, cmd_recall, cmd_recall_eval, cmd_graph_build,
    cmd_worldbook_build, cmd_graph_query, cmd_graph_add, cmd_graph_link,
    cmd_semantic_catalog,
)

from _cli_cmds_qa import (
    cmd_verify, cmd_spec_edit, cmd_doctor, cmd_ocr, cmd_style_check,
    cmd_vision_describe, cmd_web_search, cmd_session_start,
)

from _cli_cmds_idx import (
    cmd_read, cmd_doc_extract, cmd_pdf_pages, cmd_extract_md,
    cmd_chunk_read, cmd_index, cmd_index_rebuild, cmd_skills_sync,
    cmd_load_skill, cmd_outline_list, cmd_outline_apply,
    cmd_aliases, cmd_aliases_export, cmd_aliases_import,
    cmd_aliases_suggest, cmd_reflect, cmd_embed_rebuild, cmd_embed_stats,
    cmd_chunk_inspect,
)

from _cli_cmds_gen import (
    cmd_docx_inspect, cmd_docx_edit, cmd_word_com, cmd_template_fill,
    cmd_quote_spec_gen, cmd_quote_validate, cmd_quote_library,
    cmd_quote_search, cmd_bid_parse,
)
from _cli_cmds_recall_v2 import (
    cmd_query_rewrite, cmd_fact_guard, cmd_guard_audit,
    cmd_bm25_rebuild, cmd_eval_run, cmd_eval_report,
)
from _breeding import cmd_breed  # S10-3a：breed 育种登记闭环（业务在 _breeding.py）

# === T1 拆分后补 re-export：测试/外部仍经 _cli.<name> 打桩或访问 ===
# 到期复审：tests monkeypatch 面迁移至真源后退役（复审点：下一大批次开工前）。——2026-09-07 复审：tests 仍经此面打桩（test_b3_cli_face/test_m1_f0/test_recall_eval/test_verify_render_report 等），保留；退役点顺延至 monkeypatch 面迁移完成。
from _session import auto_for_input, recall  # noqa: F401
from _archive_auto import record_session_start  # noqa: F401
from _state import get_state  # noqa: F401
from _aliases import normalize_query_with_aliases  # noqa: F401
from _cloud_llm import vision_chat  # noqa: F401






class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """默认值自动显示 + epilog 保留原始换行。"""


def build_parser():
    parser = argparse.ArgumentParser(
        description="原型生成器统一命令面板",
        formatter_class=_HelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_status = sub.add_parser("status", help="所有客户状态一览")
    p_status.add_argument("--json", action="store_true", help="输出结构化 JSON")
    p_state = sub.add_parser("state", help="M3-F2：查看/设置阶段状态")
    p_state.add_argument("client", nargs="?", default=None, help="客户名（缺省查看所有客户）")
    p_state.add_argument("--client", dest="client_name", default=None, help="客户名（与位置参数等价）")
    p_state.add_argument("--stage", choices=STAGES, help="设置阶段")
    p_state.add_argument("--confirm-html", action="store_true", help="快捷设置 html_confirmed")
    p_state.add_argument("--reset", action="store_true", help="重置为 intake")
    p_state.add_argument("--json", action="store_true", help="输出结构化 JSON")
    sub.add_parser("pending", help="扫描所有客户未完成待办")
    p_recall = sub.add_parser("recall",
                              help="召回相关历史项目；--json 返回含 source/mode/degraded 字段")
    p_recall.add_argument("keywords", nargs="+", help="关键词")
    p_recall.add_argument("--keyword", action="store_true", help="强制关键词模式")
    p_recall.add_argument("--client", help="客户名（用于别名展开）")
    p_recall.add_argument("--rerank", action="store_true", help="云端 LLM rerank 精排")
    p_recall.add_argument("--no-embedding", action="store_true", help="禁用 Embedding 语义召回")
    p_recall.add_argument("--client-filter", action="store_true", default=None,
                          help="强制按客户过滤（默认指定 --client 时自动开启）")
    p_recall.add_argument("--no-client-filter", action="store_true",
                          help="禁用按客户过滤（跨客户搜索时使用）")
    p_recall.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费）")
    p_recall.add_argument("--permanent-only", action="store_true",
                          help="只返回 permanent 决策（排除 task 会话决策；非决策结果不受影响）")
    p_recall.add_argument("--no-alias", action="store_true",
                          help="关闭别名展开（查询原样进 BM25/Embedding）")
    p_recall.add_argument("--no-rewrite", action="store_true",
                          help="关闭查询改写（T2/I-2；评测 A0 基线用）")

    p_eval = sub.add_parser("recall-eval",
                            help="召回质量评估（golden query 评估集 + 三链路 Hit@1/Hit@3/MRR）")
    p_eval.add_argument("--file", help="评估集 yml 路径（默认 _knowledge/eval/golden_queries.yml）")
    p_eval.add_argument("--rerank", action="store_true",
                        help="加跑 BGE-Reranker 精排链路")
    p_eval.add_argument("--no-embedding", action="store_true",
                        help="加跑 BM25 单路链路（用于定位哪一路拖后腿）")
    p_eval.add_argument("--no-alias", action="store_true",
                        help="关闭别名展开（alias_on/off ablation 或单链路对比用）")
    p_eval.add_argument("--ablation", action="store_true",
                        help="BM25-only 别名开/关 ablation（alias_on / alias_off 两组）")
    p_eval.add_argument("--no-rewrite", action="store_true",
                        help="关闭查询改写（T2；A0 基线用）")
    p_eval.add_argument("--rewrite-ablation", action="store_true",
                        help="Gate 1：A0（关改写）vs A1（开改写）配对对比 + Wilcoxon p 值")
    p_eval.add_argument("--limit", type=int, default=None,
                        help="只跑前 N 条（调试用）")
    p_eval.add_argument("--save-baseline", action="store_true",
                        help="本次指标写为 _knowledge/eval/baseline.json")
    p_eval.add_argument("--gate", metavar="BASELINE.json",
                        help="对比指定 baseline.json，回归超容差 exit 1")
    p_eval.add_argument("--json", help="结构化报告落盘路径")
    p_eval.add_argument("--yes", action="store_true",
                        help="确认成本守门（>50 次云端调用时需此）")
    p_load = sub.add_parser("load", help="加载客户上下文")
    p_load.add_argument("client", help="客户名")
    p_memory = sub.add_parser("memory-health", help="记忆证据健康扫描（P0 记忆溯源）",
                              description="扫描客户 context.md/decisions.md 的证据引用与冲突状态")
    p_memory.add_argument("client", help="客户名")
    p_save = sub.add_parser("save", help="保存会话",
                            description="P0 决策单轨化：--decisions 写入 decisions.md（persistence=task 的会话决策条目，真源），context.md 只留一行引用；permanent 客户铁律请用 theme-guard --set",
                            epilog='示例: python _cli.py save 蓝海集团 --input="完成架构图" --decisions="两步走" --outputs="output/蓝海集团/x.html" --pending="等客户确认" --evidence="file:output/蓝海集团/x.html;user:微信确认" --strict-evidence=1')
    p_save.add_argument("client", help="客户名")
    p_save.add_argument("extra", nargs="*", help="会话内容键（原样传入）: --input= --decisions= --outputs= --pending= --evidence= --strict-evidence=1 --dsh-session=ID --light --notes")
    p_resolve = sub.add_parser("resolve-conflict", help="裁决 decisions.md 同主题矛盾决策（P0 记忆溯源）",
                               description="裁决未决冲突：--keep old 保留最早条目 / --keep new 保留最晚条目，败方标已废弃；支持主题子串匹配；--list 只读枚举未决组")
    p_resolve.add_argument("client", help="客户名")
    p_resolve.add_argument("--topic", required=False, help="冲突主题（全串或唯一子串；--list 时省略）")
    p_resolve.add_argument("--keep", required=False, choices=["old", "new"], help="保留哪一方（裁决时必填，缺省由运行时拦截 exit 1）")
    p_resolve.add_argument("--list", action="store_true", help="只列未决冲突组（主题截断 40 字/日期/未决块数），不裁决")
    p_classify = sub.add_parser("classify", help="分类 inbox/")
    p_classify.add_argument("--extract", action="store_true", help="分类后自动提取内容摘要到 context.md")
    p_classify.add_argument("--client", help="显式指定客户（跳过规则猜客户，直接归档到该客户 refs）")
    p_archive_note = sub.add_parser("archive-note", help="会话内登记文件归属（save 自动归档时消费）")
    p_archive_note.add_argument("client", nargs="?", help="客户名")
    p_archive_note.add_argument("files", nargs="*", help="文件（可带路径，只取文件名）")
    p_archive_note.add_argument("--list", action="store_true", help="查看全部待归档登记")
    p_inbox_scan = sub.add_parser("inbox-scan", help="定期 inbox 扫描（Hook + 手动均可）")
    p_inbox_scan.add_argument("--dry-run", action="store_true", help="只报告，不移动")
    p_inbox_scan.add_argument("--force", action="store_true", help="忽略时间窗/冷却期（排障用）")
    p_inbox_scan.add_argument("--quiet", action="store_true", help="Hook 调用：只输出关键摘要")
    p_inbox_scan.add_argument("--emit-json", action="store_true", help="Hook 调用：输出 JSON 便于解析")
    p_inbox_scan.add_argument("--project-dir", help="项目根目录（默认 cwd）")
    p_verify = sub.add_parser("verify", help="验证生成产出")
    p_verify.add_argument("file", help="文件路径")
    p_verify.add_argument("--only", choices=["style"], help="只跑 style+占位符扫描（不跑 Playwright）")
    p_verify.add_argument("--mode", choices=["quote"], help="P1-4：报价门禁判断检查（Q3-Q6）")

    # P1-3：context-health
    p_ch = sub.add_parser("context-health", help="生成前上下文健康检查（C1-C5，WARN 累计）")
    p_ch.add_argument("client", help="客户名")
    p_ch.add_argument("--skip", action="append", default=[], help="跳过指定 ref（可多次）")
    p_ch.add_argument("--reason", action="append", default=[], help="ref=原因（可多次）")
    p_ch.add_argument("--ack", action="store_true", help="人工确认，重置累计 WARN 一次")
    p_ch.add_argument("--session", default=None, help="会话隔离计数（#39）：传 session id 则 WARN 累计按会话隔离，不传保持客户级累计")
    p_me = sub.add_parser("me", help="打印/编辑个人画像")
    p_me.add_argument("--edit", action="store_true", help="用编辑器打开")

    p_read = sub.add_parser("read", help="全文读取（摘要+缓存）")
    p_read.add_argument("file", help="文件路径")
    p_read.add_argument("--allow-outside", action="store_true",
                        help="允许读取工作区外路径（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # P0-1 doc-extract：统一文档读取（dev_plan_cli_panel_2026-08-18）
    p_de = sub.add_parser(
        "doc-extract",
        help="统一文档读取：PDF/DOCX/XLSX/PPTX/TXT/MD 提取（text/structured，可 --json）",
    )
    p_de.add_argument("file", help="文件路径")
    p_de.add_argument("--format", dest="fmt", default="auto",
                      choices=["auto", "pdf", "docx", "xlsx", "pptx", "txt", "md"],
                      help="格式（默认 auto 按扩展名识别）")
    p_de.add_argument("--mode", default="text", choices=["text", "structured"],
                      help="text=纯文本（默认）；structured=结构化（xlsx 逐行带表头上下文）")
    p_de.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费）")
    p_de.add_argument("--allow-outside", action="store_true",
                      help="允许读取工作区外路径（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # pdf-pages：PDF 逐页渲染为 PNG（图片型/扫描 PDF 的视觉/OCR 前置）
    p_fyp = sub.add_parser("pdf-pages", help="把 PDF 逐页渲染成 PNG 截图（供 OCR/视觉读取）")
    p_fyp.add_argument("file", help="PDF 文件路径")
    p_fyp.add_argument("--out", default="output/通用/pdf_pages", help="输出目录（output/ 下；P2-3 写白名单）")
    p_fyp.add_argument("--dpi", type=int, default=150, help="渲染 DPI（默认 150）")
    p_fyp.add_argument("--allow-outside", action="store_true",
                       help="允许读取工作区外 PDF（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # extract-md：多文档全文抽取 -> 合并为一个带索引的 Markdown 文档
    p_emd = sub.add_parser("extract-md", help="多个文档全文抽取并合并为一个带索引的 Markdown")
    p_emd.add_argument("--out", required=True, help="输出 Markdown 路径（相对项目根或绝对路径）")
    p_emd.add_argument("doc", nargs="*", help="待抽取文档路径（pdf/docx/pptx/xlsx/txt/md）")
    p_emd.add_argument("--allow-outside", action="store_true",
                       help="允许读取工作区外文档（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # P0-2 doctor：只读环境诊断（dev_plan_cli_panel_2026-08-18）
    p_dr_cmd = sub.add_parser(
        "doctor",
        help="只读环境诊断：venv/依赖库/核心模块/宿主/API key 状态",
    )
    p_dr_cmd.add_argument("--json", action="store_true", help="输出结构化 JSON")

    # P0-3 ocr：图片逐字提取（dev_plan_cli_panel_2026-08-18）
    p_ocr = sub.add_parser(
        "ocr",
        help="图片逐字 OCR（精确层；无本地 tesseract 时走视觉链 fallback）",
    )
    p_ocr.add_argument("image", help="图片路径（png/jpg/gif/bmp/webp/svg/tiff/heic）")
    p_ocr.add_argument("--provider", default=None,
                       help="视觉 provider（默认 minimax；可指定其他 OpenAI 兼容视觉端点）")

    p_new = sub.add_parser("new", help="一键接单（建目录->分类->解析->outline-to-spec 生成 spec 草稿）")
    p_new.add_argument("client", help="客户名")
    p_new.add_argument("--scene", default="整体信息化规划", help="方案场景（默认整体信息化规划）")
    p_new.add_argument("--html", action="store_true", help="同时生成方案 HTML")
    p_new.add_argument("--quote", action="store_true", help="同时生成 Excel 报价")

    # P1: 索引与方案模板
    sub.add_parser("index", help="为 index.json 补全摘要+标签")
    p_rebuild = sub.add_parser("index-rebuild", help="重建 BM25 索引")
    p_rebuild.add_argument("--force", action="store_true", help="强制重建全部")
    sub.add_parser("outline-list", help="列出所有场景大纲")
    p_outline = sub.add_parser("outline-apply", help="查看场景大纲骨架")
    p_outline.add_argument("name", help="场景名")

    # 场景大纲 -> spec 草稿
    p_ots = sub.add_parser("outline-to-spec", help="场景大纲 + 客户材料 -> spec.yml 草稿")
    p_ots.add_argument("scene", help="场景名（如：整体信息化规划）")
    p_ots.add_argument("materials", nargs="*", help="客户材料文件路径（可多个，不传则自动扫描 --client 的 refs/）")
    p_ots.add_argument("--client", help="客户名")
    p_ots.add_argument("--output", help="输出 spec.yml 路径（须在 output/ 下，如 output/通用/spec_draft.yml）")
    p_ots.add_argument("--narrative", help="叙事设计单 yml 路径（设计单驱动页面顺序/id/layout，并注入 graphic 图形意图）")
    p_ots.add_argument("--allow-outside", action="store_true",
                       help="允许读取工作区外材料（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # Embedding 索引
    p_er = sub.add_parser("embed-rebuild", help="构建 Embedding 索引（增量更新）")
    p_er.add_argument("--batch-size", type=int, default=50, help="每批几个文档（默认50）")
    p_er.add_argument("--force", action="store_true", help="强制全量重建")
    sub.add_parser("embed-stats", help="查看 Embedding / BM25 双路索引统计与覆盖率告警")

    # 技能目录同步（.folio/skills -> .agents/skills 单向镜像）
    p_ssync = sub.add_parser("skills-sync", help="把 .folio/skills/ 单向同步到 .agents/skills/（事实源在前者，后者勿手改）")
    p_ssync.add_argument("--prune", action="store_true", help="删除 .agents/skills/ 中源端不存在的技能")

    # load-skill：读 skill + 写已读哨兵（REQUIRE_SKILL_SENTINEL 默认开的门禁入口）
    p_ls = sub.add_parser("load-skill", help="打印 SKILL.md 全文并记录已读哨兵（生成前必读；哨兵默认开，显式 REQUIRE_SKILL_SENTINEL=false 可关）")
    p_ls.add_argument("skill", help="技能名（.folio/skills/<名称>/SKILL.md）或 list")

    # explain-map：项目地图生成（_project_map.py 的 CLI 入口；presales-guard 合规通道）
    sub.add_parser("explain-map", help="生成项目地图 docs/项目地图.html（模块域/命令旅程/体量闸门预览，静态扫描零副作用）")

    # 切片审计
    p_ci = sub.add_parser("chunk-inspect", help="检查某文件的分块结果")
    p_ci.add_argument("path", help="文件路径（支持部分匹配）")

    # chunk-read：按 path#anchor 读完整 chunk
    p_cr = sub.add_parser("chunk-read",
                          help="按 path#anchor 读完整 chunk 全文（I-8：路径客户目录段支持别名归一化）")
    p_cr.add_argument("path", help="文件路径（可带 #anchor 锚点）")
    p_cr.add_argument("--allow-outside", action="store_true",
                      help="允许读取工作区外路径（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")


    # P1: 别名
    p_aliases = sub.add_parser("aliases", help="别名管理")
    p_aliases.add_argument("--client", help="客户名")
    p_aliases.add_argument("--global", dest="global_only", action="store_true", help="全局别名")
    p_aliases.add_argument("--edit", action="store_true", help="编辑")
    p_aliases.add_argument("diff", nargs="*", help="diff A B 对比两客户")

    # 别名 Excel 导入/导出
    p_aliases_export = sub.add_parser("aliases-export", help="导出全部别名到 Excel")
    p_aliases_export.add_argument("output", help="输出 Excel 路径（.xlsx）")
    p_aliases_import = sub.add_parser("aliases-import", help="从 Excel 导入别名（合并模式）")
    p_aliases_import.add_argument("file", help="输入 Excel 路径（.xlsx）")
    p_aliases_suggest = sub.add_parser("aliases-suggest", help="从会话/材料文本提取别名建议（只输出不写）")
    p_aliases_suggest.add_argument("client", help="客户名")
    p_aliases_suggest.add_argument("--text", help="待分析文本")
    p_aliases_suggest.add_argument("--file", help="待分析文本文件路径")


    # P1: 去 AI 化
    p_style = sub.add_parser("style-check", help="检测 AI 套路")
    p_style.add_argument("file", help="待检测文件")

    # P-vision: 图片转描述（给纯文本 agent 用）
    p_vd = sub.add_parser("vision-describe", help="把图片转成文字描述，供纯文本 agent 当上下文使用")
    p_vd.add_argument("image", help="图片路径（png/jpg/gif/bmp/webp/svg/tiff/heic）")
    p_vd.add_argument("--prompt", "-p", default=None, help="问图模型的问题（默认：请描述这张图片的内容，json 模式追加结构化模板）")
    p_vd.add_argument("--provider", default=None, help="vision provider（默认 minimax；可指定其他 OpenAI 兼容视觉端点）")
    p_vd.add_argument("--format", choices=["text", "json"], default="json",
                      help="输出格式：json（默认，含 source_image 字段，适合进 spec 引用）或 text")
    p_vd.add_argument("--rounds", type=int, choices=[1, 2], default=1,
                      help="观察轮数：1=单次（默认）；2=A/B 双观察+分歧仲裁（仅 json 格式，text 自动降级）")
    p_vd.add_argument("--show-rounds", action="store_true",
                      help="rounds=2 时在输出中附 A/B 两轮原文（_rounds 字段，审计用）")
    p_vd.add_argument("--allow-outside", action="store_true",
                      help="允许读取工作区外图片（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # 联网搜索（双引擎：Tavily + 字节搜索）
    p_ws = sub.add_parser("web-search", help="联网搜索（双引擎融合：Tavily + 字节搜索）")
    p_ws.add_argument("query", help="搜索关键词")
    p_ws.add_argument("--max-results", "-n", type=int, default=5, help="最多返回条数（默认 5）")
    p_ws.add_argument("--engines", "-e", default=None, help="指定引擎（逗号分隔，如 tavily,byte_search），默认自动检测可用引擎")

    # Spec 自动生成（走 outline-to-spec）
    p_sg = sub.add_parser("spec-gen", help="从客户材料生成 spec 草稿（走场景大纲 + LLM 防幻觉提取）")
    p_sg.add_argument("file", help="客户材料（docx/pdf/md）")
    p_sg.add_argument("--output", help="输出 spec.yml 路径（须在 output/ 下，如 output/通用/spec_gen.yml）")
    p_sg.add_argument("--client", help="客户名")
    p_sg.add_argument("--scene", help="场景名（默认：整体信息化规划）")
    p_sg.add_argument("--narrative", help="叙事设计单 yml 路径（设计单驱动页面顺序/id/layout，并注入 graphic 图形意图）")

    # 招标文件解析
    p_bp = sub.add_parser("bid-parse", help="解析招标文件，提取评分标准/格式要求/资质条款")
    p_bp.add_argument("file", help="招标文件路径（pdf/docx/txt/md）")
    p_bp.add_argument("--client", help="客户名（输出到 output/{客户}/）")
    p_bp.add_argument("--no-split", action="store_true", help="不拆分技术标/商务标")
    p_bp.add_argument("--allow-outside", action="store_true",
                      help="允许读取工作区外招标文件（D3 读边界默认拒绝仓外，此旗标为用户显式放行）")

    # PPT 单页热更新
    p_pp = sub.add_parser("ppt-page", help="[已废弃 D-090] PPT 单页重生成 -> 用 HTML 可编辑模式改单页")
    p_pp.add_argument("spec", help="spec.yml 路径")
    p_pp.add_argument("page_index", type=int, help="页码（从0开始）")
    p_pp.add_argument("output", help="输出 pptx 路径")
    p_pp.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_pp.add_argument("--base", help="基础 pptx（如有，替换其中对应页）")

    # PPT 分段构建（10+ 页自动分段）
    p_pb = sub.add_parser("ppt-build", help="[已废弃 D-090] 分段构建 PPT -> 用 html-build --pptd-only + pptd-build")
    p_pb.add_argument("spec", help="spec.yml 路径")
    p_pb.add_argument("output", help="输出 pptx 路径")
    p_pb.add_argument("--chunk-size", type=int, default=3, help="每段几页（默认3）")
    p_pb.add_argument("--no-quality", action="store_true", help="跳过质量自评")
    p_pb.add_argument("--client", default=None, help="客户名（触发生成前验证）")

    # HTML 方案生成（HTML 先行工作流入口）
    p_hb = sub.add_parser("html-build", help="从 spec.yml 生成方案 HTML + pptd 工程（双输出）",
                          epilog="前置: spec.yml 必须含 confirmed: true（人工确认后才允许渲染，否则 RenderBlockedError）\n"
                                 "示例: python _cli.py html-build spec.yml output/客户/方案_v1.html --client 客户名\n"
                                 "      python _cli.py html-build spec.yml output/客户/方案_v1.html --pptd-only --client 客户名")
    p_hb.add_argument("spec", help="spec.yml 路径")
    p_hb.add_argument("output", help="输出 .html 路径")
    p_hb.add_argument("--style", default="", help="强制样式: education/enterprise/tech/gov")
    p_hb.add_argument("--industry", default="", help="客户行业，从 profile.md 取主题色覆盖")
    p_hb.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_hb.add_argument("--pptd", default=None,
                      help="pptd 工程输出目录（默认与 .html 同名同目录）")
    p_hb.add_argument("--html-only", action="store_true", help="只出 HTML，不出 pptd")
    p_hb.add_argument("--pptd-only", action="store_true", help="只出 pptd 工程，不出 HTML")
    p_hb.add_argument("--inline-editor", action="store_true",
                      help="编辑器 JS/CSS 内联进 HTML（默认外部引用 _assets/）")
    p_hb.add_argument("--skip-review", action="store_true",
                      help="显式跳过生成后独立 LLM review（默认不再因 confirmed 自动跳过）")
    p_hb.add_argument("--density-gate", dest="density_gate",
                      choices=["verify", "deliver"], default="verify",
                      help="密度检查门档（S8-C）：verify=单视口（默认，日常验证）；"
                           "deliver=全视口+截图存档（deliver 编排自动传，独立使用慎选）")

    # confirm（Step 6：spec 确认事件化，写 sidecar + 置 confirmed）
    p_confirm = sub.add_parser(
        "confirm", help="确认 spec：写 SHA-256 sidecar 并置 confirmed: true",
        epilog="示例: python _cli.py confirm output/客户/方案_spec.yml --client 客户名\n"
               "      重复执行幂等，会重算哈希覆盖 sidecar")
    p_confirm.add_argument("spec", help="spec.yml 路径")
    p_confirm.add_argument("--client", default=None, help="客户名（写入 sidecar）")

    # deliver（一键编排，P1-5 协调逻辑外置）
    p_del = sub.add_parser("deliver", help="一键编排：spec -> html-build -> pptd-build（协调逻辑外置，AI 只做判断）",
                           epilog="示例: python _cli.py deliver spec.yml output/客户/方案_v1.html --client 客户名\n"
                                  "      python _cli.py deliver spec.yml output/客户/方案_v1.html --client 客户名 --shots")
    p_del.add_argument("spec", help="spec.yml 路径")
    p_del.add_argument("output", help="输出 .html 路径")
    p_del.add_argument("--style", default="", help="强制样式: education/enterprise/tech/gov")
    p_del.add_argument("--client", default=None, help="客户名")
    p_del.add_argument("--pptd", default=None, help="pptd 工程目录（默认与 .html 同名同目录）")
    p_del.add_argument("--inline-editor", action="store_true", help="HTML 内联编辑器")
    p_del.add_argument("--shots", action="store_true", help="pptd-build 后逐页截图目检")
    p_del.add_argument("--review", action="store_true",
                       help="P5：html-build 后插入 review，FAIL 即停（默认关）")
    p_del.add_argument("--skip-review", action="store_true",
                       help="透传给 html-build：显式跳过生成后独立 LLM review")
    p_del.add_argument("--resume", action="store_true",
                       help="续跑：跳过 html-build/确认暂停，直接从 pptd-build 继续")

    # HTML -> PPT 转换（HTML 高保真转可编辑 PPT）
    p_hp = sub.add_parser("html-to-ppt", help="[已废弃 D-090] HTML 转 PPT -> 用 html-build 双输出（同源同步）")
    p_hp.add_argument("input", help="输入 HTML 文件路径")
    p_hp.add_argument("output", help="输出 .pptx 路径")
    p_hp.add_argument("--multi-page", action="store_true", help="长 HTML 按视口分页（默认单页）")
    p_hp.add_argument("--mode", choices=["auto", "svg", "text"], default="auto",
                      help="转换模式: auto=自动检测, svg=SVG图形型, text=文本排版型")

    # pptd 工程生成器（spec -> pptd 骨架，L3 确定性生成，D-086 上游）
    p_pg = sub.add_parser("pptd-gen", help="从 spec.yml 生成 pptd 工程骨架（主pptd + pages + media）",
                          epilog="示例: python _cli.py pptd-gen output/客户/方案_spec.yml --client 客户 --name 方案\n"
                                 "生成后跑: python _cli.py pptd-build output/客户/方案/方案.pptd --shots --client 客户")
    p_pg.add_argument("spec", help="spec.yml 路径（必须 confirmed: true）")
    p_pg.add_argument("--client", default=None, help="客户名（触发生成前验证 + 默认输出目录）")
    p_pg.add_argument("--output", default=None, help="工程输出目录（默认 output/{client}/{name}/）")
    p_pg.add_argument("--name", default=None, help="项目名（默认取 spec.document.title 清洗）")
    p_pg.add_argument("--style", default="enterprise", help="样式名（同 html-build，默认 enterprise）")
    p_pg.add_argument("--logo", default=None, help="logo 文件路径（不填则从 spec.document.cover.logo_image 探测）")
    p_pg.add_argument("--final-page", action="store_true", help="末尾加致谢页（默认不加）")

    # pptd 富媒体 PPT 构建（python-pptx 后端，D-086 富媒体路线 + C 批次自研引擎）
    p_pd = sub.add_parser("pptd-build", help="pptd 富媒体 PPT 构建（check->convert->verify->可选截图）",
                          epilog="前置: python-pptx（venv 依赖；PPTD_BACKEND 可选后端选择，默认 python_pptx）\n"
                                 "示例: python _cli.py pptd-build output/客户/工程/方案.pptd --shots --client 客户名\n"
                                 "QA 循环: python _cli.py pptd-build output/客户/工程/方案.pptx --shots（仅重出截图）")
    p_pd.add_argument("pptd", help="主 .pptd 文件路径（或 .pptx + --shots 仅截图）")
    p_pd.add_argument("-o", "--output", default=None, help="输出 .pptx 路径（默认与 pptd 同名）")
    p_pd.add_argument("--check-only", action="store_true", help="只校验不转换")
    p_pd.add_argument("--shots", action="store_true", help="转换后逐页导出 PNG 截图目检（需本机 PowerPoint）")
    p_pd.add_argument("--shots-dir", default=None, help="截图输出目录（默认 <pptx目录>/_shots_<名称>/）")
    p_pd.add_argument("--client", default=None, help="客户名（触发生成前验证）")

    # 报价 Excel 生成
    p_qb = sub.add_parser("quote-build", help="生成报价（HTML/Excel）")
    p_qb.add_argument("spec", help="spec.yml 路径")
    p_qb.add_argument("--template", default="一页报价模板", help="模板版式名")
    p_qb.add_argument("--format", choices=["html", "xlsx", "all"], default="html", help="输出格式（默认 html）")
    p_qb.add_argument("--style", default="enterprise", help="样式名，与方案 HTML 统一")
    p_qb.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_qb.add_argument("output", help="输出文件路径（须在 output/ 下，扩展名自动处理）")

    p_qsg = sub.add_parser("quote-spec-gen", help="从客户材料提取报价 spec.yml")
    p_qsg.add_argument("materials_dir", help="材料目录")
    p_qsg.add_argument("output", help="输出 spec.yml 路径（须在 output/ 下）")
    p_qsg.add_argument("--client", default="", help="客户名")

    p_qv = sub.add_parser("quote-validate", help="校验报价 Excel 公式")
    p_qv.add_argument("xlsx", help="xlsx 路径")

    p_ql = sub.add_parser("quote-library", help="管理报价内容库")
    p_ql.add_argument("action", choices=["list", "search"], help="操作")
    p_ql.add_argument("type", choices=["modules", "licenses", "services", "thirdparty"], help="类型")
    p_ql.add_argument("--keyword", help="搜索关键词（search 用）")

    p_qs = sub.add_parser("quote-search", help="语义搜索全报价内容库")
    p_qs.add_argument("keyword", help="搜索关键词（名称+描述）")
    p_qs.add_argument("--top", type=int, default=10, help="返回数量")

    # Word 文档生成
    p_db = sub.add_parser("docx-build", help="从 spec.yml 生成 Word 文档")
    p_db.add_argument("spec", help="spec.yml 路径")
    p_db.add_argument("output", help="输出 docx 路径")
    p_db.add_argument("--client", default=None, help="客户名（触发生成前验证）")
    p_db.add_argument("--skip-review", action="store_true",
                      help="显式跳过生成后独立 LLM review（默认不再因 confirmed 自动跳过）")
    # docx-inspect：提取 Word 文档结构（页数/大纲/表格/图片）JSON
    p_dxi = sub.add_parser("docx-inspect", help="提取 Word 文档结构（页数/大纲/表格/图片）输出 JSON")
    p_dxi.add_argument("docx", help="docx 文件路径")

    # docx-edit：精确修改 Word 文档（插入/替换/删节/插图/重排编号）
    p_dxe = sub.add_parser("docx-edit", help="精确修改 Word 文档（插入/替换/删节/插图/重排编号）")
    p_dxe.add_argument("docx", help="docx 文件路径")
    p_dxe.add_argument("--insert-after", dest="insert_after", default=None, help="在指定标题后插入段落")
    p_dxe.add_argument("--text", default=None, help="插入/替换的文本内容")
    p_dxe.add_argument("--replace", default=None, help="替换指定标题下的内容")
    p_dxe.add_argument("--paragraph", type=int, default=None, help="替换标题下第 N 段")
    p_dxe.add_argument("--delete-section", dest="delete_section", default=None, help="删除整节（从该标题起）")
    p_dxe.add_argument("--insert-image", dest="insert_image", default=None, help="在指定标题后插入图片")
    p_dxe.add_argument("--image", default=None, help="图片路径")
    p_dxe.add_argument("--caption", default=None, help="图题")
    p_dxe.add_argument("--renumber", action="store_true", help="全文重排编号（调用 docx_com_postprocess.renumber_headings）")

    # word-com：Word 排版操作族（子命令）
    p_wc = sub.add_parser("word-com", help="Word 排版操作族（normalize/renumber/polish/apply-style/to-pdf/accept/compare）")
    wc_sub = p_wc.add_subparsers(dest="word_com_cmd", help="word-com 子命令")
    p_wc_n = wc_sub.add_parser("normalize", help="识别裸奔标题并套用 Heading 样式")
    p_wc_n.add_argument("file", help="docx 文件路径")
    p_wc_r = wc_sub.add_parser("renumber", help="全文重排编号")
    p_wc_r.add_argument("file", help="docx 文件路径")
    p_wc_r.add_argument("--style", default="chinese_multi", choices=["chinese_multi", "legal", "chapter", "simple"], help="编号风格")
    p_wc_p = wc_sub.add_parser("polish", help="一站式精排（normalize+renumber+样式集+页眉页脚+目录+可选PDF）")
    p_wc_p.add_argument("file", help="docx 文件路径")
    p_wc_p.add_argument("--style-set", default="bid", choices=["bid", "general"], help="样式集")
    p_wc_p.add_argument("--project-name", default="", help="项目名（页眉）")
    p_wc_p.add_argument("--pdf", action="store_true", help="同时导出 PDF")
    p_wc_s = wc_sub.add_parser("apply-style", help="只应用样式集（纯 python-docx，不改文字）")
    p_wc_s.add_argument("file", help="docx 文件路径")
    p_wc_s.add_argument("--style-set", default="gs0910", choices=["gs0910"],
                        help="样式集（gs0910 = 照抄 0910 规格：仿宋三号正文/黑体楷体标题/黑体五号图题）")
    p_wc_s.add_argument("--no-backup", action="store_true", help="不写 .versions/ 备份")
    p_wc_s.add_argument("--no-numbering", action="store_true",
                        help="不挂多级自动编号（缺省挂 Heading 1–5 自动编号，对标 0910）")
    p_wc_t = wc_sub.add_parser("to-pdf", help="另存为 PDF")
    p_wc_t.add_argument("file", help="docx 文件路径")
    p_wc_a = wc_sub.add_parser("accept", help="接受所有修订")
    p_wc_a.add_argument("file", help="docx 文件路径")
    p_wc_c = wc_sub.add_parser("compare", help="比较文档（与旧版比较并接受修订）")
    p_wc_c.add_argument("file", help="当前文档路径")
    p_wc_c.add_argument("--other", required=True, help="旧版文档路径")

    # template-fill：模板填充（docxtpl + COM 后处理）
    p_tf = sub.add_parser("template-fill", help="模板填充（docxtpl 渲染 + normalize + renumber + refresh_toc）")
    p_tf.add_argument("template", help="模板 docx 路径")
    p_tf.add_argument("--data", required=True, help="JSON 数据文件路径")
    p_tf.add_argument("--output", "-o", required=True, help="输出 docx 路径")


    # theme-guard（合并 theme-list + theme-set，PROJECT_DESIGN.md §13）
    p_tg = sub.add_parser("theme-guard", help="列出/刷新/记录核心约束")
    p_tg.add_argument("client", help="客户名")
    p_tg.add_argument("--task-id", help="任务ID")
    p_tg.add_argument("--set", dest="set_theme", help="记录新主题（省略则列出当前主题）")
    p_tg.add_argument("--scope", choices=["client", "task"], default="client", help="作用域（默认 client）")
    p_tg.add_argument("--priority", choices=["critical", "high"], default="high")
    p_tg.add_argument("--turn", type=int, default=0, help="当前对话轮次（>0 时按间隔检查是否需 re-grounding）")

    # theme-verify（原 theme-check 独立命令）
    p_tv = sub.add_parser("theme-verify", help="检查产出文件是否覆盖 permanent 主题")
    p_tv.add_argument("file", help="产出文件路径")
    p_tv.add_argument("client", help="客户名")

    # audit（验证与审计）
    p_kd = sub.add_parser("key-doctor", help="检查各 API key 来源与可用性（默认活体探测）")
    p_kd.add_argument("--no-probe", action="store_true", help="只列来源，不联网探测")
    p_audit = sub.add_parser("audit", help="审计：配置/运行时/主题/记忆/行为")
    p_audit.add_argument("--mode", choices=["config", "runtime", "behavior", "theme", "memory", "review", "worldbook", "context", "keynote", "knowledge", "debt", "drift", "cost", "track", "all"], default="config")
    p_audit.add_argument("--client", help="客户名（--mode theme/memory/worldbook/keynote/debt/drift 时使用）")

    p_cite = sub.add_parser("cite-audit", help="引用及审查报告：从 spec 提取引用 + 反向校验来源 + 主题覆盖")
    p_cite.add_argument("spec", help="spec.yml 路径")
    p_cite.add_argument("--client", help="客户名（用于主题守卫检查）")
    p_cite.add_argument("--output", help="输出报告路径（须在 output/ 下；默认 spec 同名_审查报告.md，spec 不在 output/ 下时必须显式指定）")
    p_cite.add_argument("--strict", action="store_true",
                        help="缺来源或 critical 主题缺失时 exit 2（deliver 链强制使用）")

    # spec-diff（两份 spec 结构化对比，配合 3.1 快照回溯历史版本）
    p_sdiff = sub.add_parser("spec-diff", help="两份 spec.yml 结构化 diff（退出码 0=无差异 1=有差异 2=错误）",
                             epilog="示例: python _cli.py spec-diff spec_v4.yml spec_v5.yml\n"
                                    "      python _cli.py spec-diff .versions/方案_spec.yml.20260720120000 方案_spec.yml  # 对比 §3.1 快照")
    p_sdiff.add_argument("spec_a", help="旧版 spec.yml 路径（对比基准）")
    p_sdiff.add_argument("spec_b", help="新版 spec.yml 路径")

    # spec-edit（类型化增量变更，P1-6）
    p_sedit = sub.add_parser("spec-edit", help="spec.yml 类型化增量变更（add_page/update_page/delete_page/add_element/update_element/delete_element）",
                             epilog="示例: python _cli.py spec-edit spec.yml --op add_page --page-id p04 --title 实施计划 --layout phases\n"
                                    "      python _cli.py spec-edit spec.yml --op add_element --page-id p03 --element '{\"type\":\"text\",\"content\":\"新增\"}'")
    p_sedit.add_argument("spec", help="spec.yml 路径")
    p_sedit.add_argument("--op", required=True, choices=["add_page", "update_page", "delete_page", "add_element", "update_element", "delete_element"], help="操作类型")
    p_sedit.add_argument("--page-id", default=None, help="目标页面 ID")
    p_sedit.add_argument("--title", default=None, help="页面标题（add_page 用）")
    p_sedit.add_argument("--layout", default=None, help="页面布局（add_page 用，默认 bullets）")
    p_sedit.add_argument("--index", type=int, default=None, help="元素序号（add_element/update_element/delete_element 用）")
    p_sedit.add_argument("--element", default=None, help='元素 JSON（add_element 用，如 \'{"type":"text","content":"内容"}\'）')
    p_sedit.add_argument("--updates", default=None, help='更新 JSON（update_page/update_element 用，如 \'{"title":"新标题"}\'）')
    p_sedit.add_argument("--confirm", action="store_true",
                         help="M3-F2：确认 spec 并推进到 spec_confirmed（需 --client 或 spec 在 output/<客户>/ 下可推断）")
    p_sedit.add_argument("--client", default=None, help="客户名（spec-edit --confirm 推进状态用）")

    # review（独立 LLM 审查）
    p_review = sub.add_parser("review", help="独立审查：用独立 LLM 会话审查产出质量")
    p_review.add_argument("output_file", help="产出文件路径（HTML；PPT/DOCX 二进制审查待实装）")
    p_review.add_argument("--client", help="客户名（用于加载铁律）")
    p_review.add_argument("--spec", help="spec.yml 路径（用于内容一致性检查）")
    p_review.add_argument("--adversarial", action="store_true", help="对抗性审查模式（挑刺者角色，只找问题不打分；与 --parallel 组合 = 多角色并行挑刺）")
    p_review.add_argument("--parallel", action="store_true", help="并行审查模式（5 路独立会话各查一个维度，汇总去重；与 --adversarial 组合 = 多角色并行挑刺）")
    p_review.add_argument("--screenshot", action="store_true", help="截图对抗审视（S9-2a）：playwright 截 crafted 页进 VLM，三秒测试主门；review_budget 熔断共用，修正轮 ≤3 轮")
    p_review.add_argument("--incremental", action="store_true", help="增量审查（WP-A5）：同文件迭代复审，未变更页轻摘要+变更页全文，每 3 轮强制全量；与其余模式互斥，首审无基线自动全量")

    # compact（替代 compress / compress-doc）
    p_compact = sub.add_parser("compact", help="压缩客户历史（task_history + context.md）")
    p_compact.add_argument("client", help="客户名")
    p_compact.add_argument("--keep", type=int, default=10, help="保留最近 N 条 task_history 记录（默认 10）")
    p_compact.add_argument("--keep-sessions", type=int, default=1, help="context.md 保留最近 N 次完整会话（默认 1，传 0 跳过）")

    # 会话开始（auto_for_input CLI 入口）
    p_ss = sub.add_parser("session-start", help="会话开始：判层级+加载上下文+语义召回",
                          epilog="AGENTS.md 规定的 MANDATORY 入口：每段会话收到第一条用户消息后先执行，再开始工作")
    p_ss.add_argument("input", help="用户输入文本")
    p_ss.add_argument("--client", default=None, help="客户名")
    p_ss.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费，省去 stdout 解析）")

    # 会话反思（学习时刻提取 → 决策提案）
    p_reflect = sub.add_parser("reflect", help="会话反思：提取学习时刻，生成决策提案",
                               description="P3：--apply 直接把提案写入 decisions.md（persistence=task，AI 推断待确认）")
    p_reflect.add_argument("client", help="客户名")
    p_reflect.add_argument("--json", action="store_true", help="输出结构化 JSON（供 folio_reflect 工具消费）")
    p_reflect.add_argument("--apply", action="store_true",
                           help="直接把提案写入 decisions.md（AI 推断，persistence=task，标待确认）")

    # 世界书 graph 命令
    sub.add_parser("graph-build", help="构建/更新版本链索引 client_graph.json（不写 client_index.md）").add_argument("client", help="客户名")
    sub.add_parser("worldbook-build", help="直读真源生成/更新世界书 client_index.md（R1-1）").add_argument("client", help="客户名")
    p_gq = sub.add_parser("graph-query",
                          help="人工/调试：查询版本链索引（client_graph.json）节点和边；"
                               "--node/--edges 精确 ID，--query 自由文本搜索")
    p_gq.add_argument("client", help="客户名")
    p_gq.add_argument("--node", default=None, help="节点 ID（精确匹配，不做别名展开）")
    p_gq.add_argument("--type", default=None, help="节点类型 (decision/output/insight/method/client_profile)")
    p_gq.add_argument("--edges", default=None, help="查询与该节点关联的边（精确 ID，不做别名展开）")
    p_gq.add_argument("--query", default=None,
                      help="按自由文本搜索节点标题/摘要（会先做别名展开；与 --node/--edges 互斥）")
    p_gq.add_argument("--json", action="store_true", help="输出结构化 JSON（供程序化消费）")
    p_gq.add_argument("--no-alias", action="store_true",
                      help="关闭 --query 的别名展开（精确 ID 查询从不做别名展开）")

    p_ga = sub.add_parser("graph-add", help="人工调试：添加版本链索引节点")
    p_ga.add_argument("client", help="客户名")
    p_ga.add_argument("--type", required=True, help="节点类型")
    p_ga.add_argument("--title", required=True, help="节点标题")
    p_ga.add_argument("--summary", default="", help="节点摘要")
    p_gl = sub.add_parser("graph-link", help="人工调试：添加版本链索引边")
    p_gl.add_argument("client", help="客户名")
    p_gl.add_argument("--from", dest="from_id", required=True, help="起点节点 ID")
    p_gl.add_argument("--to", dest="to_id", required=True, help="终点节点 ID")
    p_gl.add_argument("--type", required=True, help="边类型 (produced_by/revised_from/...)")
    p_gl.add_argument("--note", default="", help="备注")
    # 语义库（子计划1）
    p_sc = sub.add_parser("semantic-catalog", help="校验能力目录 JSON")
    p_sc.add_argument("--check", action="store_true", default=True, help="校验（默认行为）")
    p_sc.add_argument("--path", default=None, help="能力目录路径（默认 _knowledge/capability_catalog/能力目录_E9标准_v1.json）")

    # === 上下文召回一期（T6）===
    p_qr = sub.add_parser("query-rewrite", help="测试查询改写模块（T2）")
    p_qr.add_argument("query", nargs="?", default=None, help="待改写查询（缺省用内置示例）")
    p_qr.add_argument("--client", default=None, help="客户名（用于别名/上下文）")
    p_qr.add_argument("--json", action="store_true", help="输出结构化 JSON")

    p_fg = sub.add_parser("fact-guard", help="事实一致性检查（T5）")
    p_fg.add_argument("--text", default="", help="待检查文本")
    p_fg.add_argument("--client", default=None, help="客户名（用于实体白名单）")
    p_fg.add_argument("--json", action="store_true", help="输出结构化 JSON")

    p_ga = sub.add_parser("guard-audit", help="查看 fact_guard 隔离区队列（T5）")
    p_ga.add_argument("--queue", action="store_true", help="列出隔离区队列（默认行为）")
    p_ga.add_argument("--json", action="store_true", help="输出结构化 JSON")

    p_bmr = sub.add_parser("bm25-rebuild", help="重建 BM25 索引（T3/T6）")
    p_bmr.add_argument("--json", action="store_true", help="输出结构化 JSON")

    p_er = sub.add_parser("eval-run", help="运行召回评估集（T6 最小版；T8 完整统计）")
    p_er.add_argument("--file", default=None, help="评估集 yml/jsonl 路径")
    p_er.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    p_er.add_argument("--no-embedding", action="store_true", help="关闭 Embedding 路")
    p_er.add_argument("--no-alias", action="store_true", help="关闭别名展开")
    p_er.add_argument("--json", action="store_true", help="输出结构化 JSON")

    p_erep = sub.add_parser("eval-report", help="输出 eval-run 生成的 JSON 报告（T6）")
    p_erep.add_argument("--report", default=None, help="eval-run JSON 报告路径")

    p_br = sub.add_parser("breed", help="定制页 pattern 育种登记闭环（S10-3a，实现在 _breeding.py）：list/register/confirm/evaluate/promote/audit/ttl")
    p_br.add_argument("action", nargs="?", default="list", choices=["list", "register", "confirm", "evaluate", "promote", "audit", "ttl"], help="子动作")
    p_br.add_argument("target", nargs="?", default=None, help="模式名（register）/ breed id（confirm/evaluate/promote）")
    for _k, _h in (("--source", "出处页/deck 路径（register 必填）"), ("--client", "确认客户名（confirm）"), ("--refs", "提炼产物逗号分隔（promote）"), ("--notes", "备注（register）")):
        p_br.add_argument(_k, default="", help=_h)
    p_br.add_argument("--archive", action="store_true", help="audit 尸体清理实归档（默认 dry-run 展示）")

    return parser


# 命令分组总览（P2-5，dev_plan_cli_panel_2026-08-18）：
# 与 _build_dispatch 的分组注释保持一致；无参数运行 `_cli.py` 时打印（替代平铺 --help）。
# 数量以 audit 动态统计为准（parser 与 dispatch 一致性检查），此处只做展示分组。
_COMMAND_GROUPS = [
    # 2026-08-31 面系词表（对齐 folio 家族：记忆面/检索面/生成面/质量面；组边界与成员不变，仅标签改名）
    ("记忆面 · 防幻觉", ["status", "pending", "recall", "recall-eval", "me", "load",
                    "memory-health", "theme-guard", "theme-verify"]),
    ("记忆面 · 状态写入", ["new", "save", "resolve-conflict", "classify", "archive-note",
                 "inbox-scan", "compact", "state"]),
    ("生成面 · 主线", ["html-build", "deliver", "pptd-gen", "pptd-build", "docx-build",
                 "quote-build"]),
    ("质量面", ["verify", "style-check", "vision-describe", "ocr", "session-start",
                   "audit", "key-doctor", "doctor", "cite-audit", "review",
                   "web-search", "spec-diff", "spec-edit"]),
    ("检索面 · 索引", ["index", "index-rebuild", "skills-sync", "load-skill",
                 "embed-rebuild", "chunk-inspect", "chunk-read"]),
    ("检索面 · 读取与大纲", ["read", "doc-extract", "pdf-pages", "extract-md", "aliases", "aliases-suggest", "aliases-export",
                          "aliases-import", "outline-list", "outline-apply",
                          "outline-to-spec", "reflect", "embed-stats"]),
    ("记忆面 · 世界书与语义", ["graph-build", "worldbook-build", "graph-query", "graph-add", "graph-link",
                    "semantic-catalog"]),
    ("生成面 · quote 与标书", ["spec-gen", "bid-parse", "quote-spec-gen", "quote-validate",
                        "quote-library", "quote-search"]),
    ("生成面 · 文档工具", ["docx-inspect", "docx-edit", "word-com", "template-fill"]),
    ("观测面", ["explain-map"]),
]


def cmd_explain_map(args):
    """生成项目地图 docs/项目地图.html（静态扫描零副作用：模块域/命令旅程/体量闸门预览）。"""
    from _project_map import main as _pmap_main
    _pmap_main()


def _print_grouped_help():
    """无参数时按四层分组打印命令总览（Step 3 收敛：主链 11 白名单）。"""
    width = 26
    print("兰亭售前助手 CLI 命令总览（四层；`--help` 看单命令细节，`--json` 看结构化输出）")
    print("=" * 64)
    layers = [
        ("主链（11，其余命令需用户明确意图）",
         ["session-start", "theme-guard", "spec-gen", "html-build", "confirm",
          "pptd-build", "docx-build", "quote-build", "verify", "review", "save"]),
        ("工具面", ["doc-extract", "pdf-pages", "ocr", "docx-inspect", "docx-edit",
                    "word-com", "template-fill", "bid-parse", "quote-spec-gen",
                    "outline-to-spec", "new", "style-check"]),
        ("记忆·检索面", ["recall", "chunk-read", "graph-query", "graph-add",
                        "graph-build", "worldbook-build", "embed-rebuild",
                        "embed-stats", "semantic-catalog"]),
        ("质量与诊断面", ["doctor", "audit", "status",
                          "key-doctor", "cite-audit", "spec-diff", "spec-edit",
                          "memory-health", "context-health"]),
    ]
    for group, cmds in layers:
        print(f"■ {group}")
        for c in cmds:
            print(f"  {c:<{width}} python _cli.py {c} --help")
    print()
    print("【废弃命令】ppt-page/ppt-build/html-to-ppt → html-build 双输出路线（D-090），"
          "其余见 audit 输出")
    print("【命令总数】以 `audit` 动态统计为准（parser 与 dispatch 一致性检查）")


def _build_dispatch():
    """构建命令调度表（模块级函数，供 audit 检查）。

    活跃命令数以 audit 动态统计为准（parser 与 dispatch 一致性检查，不在此硬编码）。
    分组语义见 _COMMAND_GROUPS；废弃命令见 _DEPRECATED（24 个）。
    """
    return {
        # === 防幻觉查询（8）===
        "status": cmd_status,
        "state": cmd_state,
        "pending": cmd_pending,
        "recall": cmd_recall,
        "recall-eval": cmd_recall_eval,
        "me": cmd_me,
        "load": cmd_load,
        "memory-health": cmd_memory_health,
        "theme-guard": cmd_theme_guard,
        "context-health": cmd_context_health,
        "theme-verify": cmd_theme_verify,
        # === 状态写入（6）===
        "new": cmd_new,
        "save": cmd_save,
        "resolve-conflict": cmd_resolve_conflict,
        "classify": cmd_classify,
        "archive-note": cmd_archive_note,
        "inbox-scan": cmd_inbox_scan,
        "compact": cmd_compact,
        # === 生成执行（8）===
        "html-build": cmd_html_build,
        "confirm": cmd_confirm,
        "deliver": cmd_deliver,
        "ppt-build": cmd_ppt_build,
        "pptd-gen": cmd_pptd_gen,
        "pptd-build": cmd_pptd_build,
        "html-to-ppt": cmd_html_to_ppt,
        "docx-build": cmd_docx_build,
        "docx-inspect": cmd_docx_inspect,
        "docx-edit": cmd_docx_edit,
        "word-com": cmd_word_com,
        "template-fill": cmd_template_fill,
        "ppt-page": cmd_ppt_page,
        "quote-build": cmd_quote_build,
        # === 校验与审计（10）===
        "verify": cmd_verify,
        "style-check": cmd_style_check,
        "vision-describe": cmd_vision_describe,
        "ocr": cmd_ocr,
        "session-start": cmd_session_start,
        "audit": cmd_audit,
        "key-doctor": cmd_key_doctor,
        "doctor": cmd_doctor,
        "cite-audit": cmd_cite_audit,
        "review": cmd_review,
        "web-search": cmd_web_search,
        "spec-diff": cmd_spec_diff,
        "spec-edit": cmd_spec_edit,
        "breed": cmd_breed,  # S10-3a 育种登记闭环
        # === 索引管理（6）===
        "index": cmd_index,
        "index-rebuild": cmd_index_rebuild,
        "skills-sync": cmd_skills_sync,
        "load-skill": cmd_load_skill,
        "embed-rebuild": cmd_embed_rebuild,
        "chunk-inspect": cmd_chunk_inspect,
        "explain-map": cmd_explain_map,
        "chunk-read": cmd_chunk_read,
        # === 大纲与辅助（12）===
        "read": cmd_read,
        "doc-extract": cmd_doc_extract,
        "pdf-pages": cmd_pdf_pages,
        "extract-md": cmd_extract_md,
        "aliases": cmd_aliases,
        "aliases-suggest": cmd_aliases_suggest,

        "aliases-export": cmd_aliases_export,
        "aliases-import": cmd_aliases_import,
        "outline-list": cmd_outline_list,
        "outline-apply": cmd_outline_apply,
        "outline-to-spec": cmd_outline_to_spec,
        "reflect": cmd_reflect,
        "embed-stats": cmd_embed_stats,
        # === 世界书 graph（5）===
        "graph-build": cmd_graph_build,
        "worldbook-build": cmd_worldbook_build,
        "graph-query": cmd_graph_query,
        "graph-add": cmd_graph_add,
        "graph-link": cmd_graph_link,
        # === 语义库（子计划1：仅本命令；子计划2-4 各自追加）===
        "semantic-catalog": cmd_semantic_catalog,
        # === quote 辅助（6）===
        "spec-gen": cmd_spec_gen,
        "bid-parse": cmd_bid_parse,
        "quote-spec-gen": cmd_quote_spec_gen,
        "quote-validate": cmd_quote_validate,
        "quote-library": cmd_quote_library,
        "quote-search": cmd_quote_search,
        # === 上下文召回一期（T6）===
        "query-rewrite": cmd_query_rewrite,
        "fact-guard": cmd_fact_guard,
        "guard-audit": cmd_guard_audit,
        "bm25-rebuild": cmd_bm25_rebuild,
        "eval-run": cmd_eval_run,
        "eval-report": cmd_eval_report,
    }


# 已废弃命令 → 替代命令（argparse 之前拦截；_cli_audit 统计废弃命令数）
_DEPRECATED = {
    "ppt-pages": "ppt-build --preview",
    "ppt-outline": "ppt-build",
    "ppt-preview": "ppt-build --preview",
    "tpl-list": "outline-list",
    "tpl-parse": "outline-apply",
    "tpl-tune": "outline-apply",
    "tpl-save": "outline-apply",
    "tpl-apply": "outline-apply",
    "extract-batch": "new",
    "compress": "compact",
    "compress-doc": "compact",
    # P3 收敛：洞察/反模式并入 reflect（避免二级废弃，feedback/diff 直达 reflect）
    "feedback": "reflect",
    "diff": "reflect",
    "insight": "reflect",
    "diff-record": "reflect",
    # 2026-08-31 清理与下线工程（3B）：固化反复模式统一走 theme-guard --set / save --decisions
    "consolidate": "theme-guard",
    "quality-check": "verify",
    "theme-list": "theme-guard",
    "theme-set": "theme-guard",
    "theme-check": "theme-verify",
    "skill-list": "(已降级为内部函数)",
    "skill-save": "(已降级为内部函数)",
    "llm-usage": "(已删除)",
    "llm-providers": "(已删除)",
}


def main():
    # Windows 控制台默认 GBK，输出 emoji/符号会 UnicodeEncodeError；统一按 UTF-8 输出
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, 'reconfigure', None)
        if _reconfigure:
            _reconfigure(encoding='utf-8', errors='replace')

    # 客户 xlsx 里的旧式打印区域定义名会触发 openpyxl UserWarning 刷屏，与本工具无关
    import warnings
    warnings.filterwarnings("ignore", message=r"Print area cannot be set.*")

    # 在 argparse 之前拦截已废弃命令（argparse 会拒绝未注册的子命令）
    if len(sys.argv) > 1 and sys.argv[1] in _DEPRECATED:
        cmd = sys.argv[1]
        replacement = _DEPRECATED[cmd]
        print(f"[已废弃] 命令 `{cmd}` 已合并到 `{replacement}`")
        if not replacement.startswith("("):
            print(f"  请改用：python _cli.py {replacement} ...")
        sys.exit(1)

    parser = build_parser()
    argv = list(sys.argv)
    # save 的会话键值参数（--input= 等）是「带 -- 前缀的位置参数」（parse_session_args 解析），
    # argparse 会把无空格的未知选项判为 "unrecognized arguments"（有空格时又恰好能被吞进
    # 位置参数，行为不一致）。插入 `--` 分隔符让其后一切按位置参数解析（2026-08-16 修复，
    # 实测：纯中文无空格值此前必炸）。
    if len(argv) > 1 and argv[1] == "save":
        argv = argv[:2] + ["--"] + argv[2:]
    args = parser.parse_args(argv[1:])

    # P2（B3）：save 客户名 `--` 注入拦截。上方的 `--` 重写让 save 的一切
    # 选项式 token（--help/-h 等）落进位置参数 client，曾真实创建
    # _knowledge/clients/--help/ 并 exit 0。客户名是业务命名，合法形态
    # 不可能以 - 开头，一律拒绝。
    if args.command == "save" and str(getattr(args, "client", "") or "").startswith("-"):
        print(f"[错误] save 客户名不合法: {args.client}"
              f"（不能以 - 开头；总览: python _cli.py -h，分组: python _cli.py 不带参数）")
        sys.exit(1)

    if not args.command:
        _print_grouped_help()
        sys.exit(0)

    # 防线 2：CLI 是唯一执行路径（PROJECT_DESIGN.md §5.4）
    # _cli.py 调用 _renderer 前设置环境变量，防止 AI 直接 import _renderer 绕过
    os.environ['_PRESALES_CLI_INVOKED'] = '1'

    dispatch = _build_dispatch()

    fn = dispatch.get(args.command)
    if not fn:
        print(f"未知命令: {args.command}")
        parser.print_help()
        sys.exit(1)

    # P2：异常兜底，避免用户看到 Python traceback
    try:
        fn(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
        sys.exit(130)
    except FileNotFoundError as e:
        print(f"[错误] 找不到文件：{e}")
        print("  提示：检查文件路径是否正确，文件是否存在")
        sys.exit(1)
    except PermissionError as e:
        print(f"[错误] 没有权限访问：{e}")
        print("  提示：尝试以管理员身份运行，或检查文件是否被其他程序占用")
        sys.exit(1)
    except ModuleNotFoundError as e:
        print(f"[错误] 缺少依赖模块：{e}")
        print("  提示：运行 pip install -r requirements.txt 安装缺失的依赖")
        sys.exit(1)
    except ImportError as e:
        print(f"[错误] 导入失败：{e}")
        print("  提示：检查 Python 环境是否完整，或重新 pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        # 守卫阻断一律 exit 2（CLI 契约 v1 §2）：spec 未确认、confirm 哈希不匹配、
        # theme critical 缺失、哨兵未读 skill、review FAIL
        try:
            from _renderer import RenderBlockedError
            if isinstance(e, RenderBlockedError):
                print(f"[守卫] {e}")
                sys.exit(2)
        except ImportError:
            pass
        msg = str(e)
        if "API key" in msg.lower() or "api_key" in msg.lower():
            print("[错误] API Key 未配置或无效")
            print("  提示：检查项目根目录的 .env 文件，确保已填入有效的 API Key")
            print(f"  详细：{msg[:200]}")
        elif "No such file" in msg or "not found" in msg.lower():
            print(f"[错误] 文件不存在：{msg[:200]}")
            print("  提示：检查文件路径是否正确")
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            print("[错误] 请求超时")
            print("  提示：检查网络连接，或稍后重试")
        elif "memory" in msg.lower() or "MemoryError" in str(type(e)):
            print("[错误] 内存不足")
            print("  提示：尝试分批处理，或关闭其他程序释放内存")
        else:
            print(f"[错误] 命令 '{args.command}' 执行失败")
            print(f"  原因：{msg[:300]}")
            print("  提示：如果是第一次运行，请先执行 python _cli.py status 检查环境是否正常")
        sys.exit(1)


if __name__ == "__main__":
    main()
