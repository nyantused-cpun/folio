# -*- coding: utf-8 -*-
"""客户入库模块：一键接单 + BM25 索引重建。

从 _session.py 拆分（候选 4 · 模块化），依赖 _context + _recall。
"""
import os
import re

from _paths import SCRIPT_DIR, CLIENTS_DIR
from _context import ensure_client_dir
from _recall import _RECALL_CONFIG


__all__ = [
    "onboard_client", "rebuild_bm25_index_all",
]


def onboard_client(client, scene="整体信息化规划", html=False, quote=False):
    """IDE 模式：一键接单。等价 CLI new。

    6 步：建目录->分类->全文解析->提取素材->读 profile->生成 spec（可选 HTML/报价）。

    返回 schema:
    {
        "client_path": str,
        "output_dir": str,
        "materials": [{"file": str, "summary": str}, ...],
        "key_numbers": list,        # 关键数字
        "sys_words": list,           # 提及的系统/流程
        "theme_colors": list,        # [[name, color], ...]
        "spec_path": str | None,
        "html_path": str | None,
        "quote_paths": dict | None,  # {"html": ..., "xlsx": ...}
        "warnings": list
    }
    """
    warnings = []
    result = {
        "client_path": None, "output_dir": None, "materials": [],
        "key_numbers": [], "sys_words": [], "theme_colors": [],
        "spec_path": None, "html_path": None, "quote_paths": None,
        "warnings": warnings,
    }

    # [1/6] 建客户目录
    try:
        client_path = ensure_client_dir(client)
        refs_dir = os.path.join(client_path, "refs")
        output_dir = os.path.join(SCRIPT_DIR, "output", client)
        os.makedirs(output_dir, exist_ok=True)
        result["client_path"] = client_path
        result["output_dir"] = output_dir
        print(f"=== 一键接单: {client} ===\n[1/6] 建客户目录: {client_path}")
    except Exception as e:
        warnings.append(f"建目录失败: {e}")
        return result

    # [2/6] 分类 inbox/
    try:
        from _classify import classify
        print("[2/6] 分类 inbox/...")
        classify()
    except Exception as e:
        warnings.append(f"classify 失败: {e}")

    # [3/6] 全文解析 refs/
    print(f"[3/6] 全文解析 {refs_dir}/ ...")
    if os.path.isdir(refs_dir):
        try:
            from _pipeline import read_full
            for fname in os.listdir(refs_dir):
                fpath = os.path.join(refs_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".xls", ".txt", ".md"):
                    continue
                print(f"  解析: {fname}")
                summary, cache = read_full(fpath)
                result["materials"].append({"file": fname, "summary": summary})
        except Exception as e:
            warnings.append(f"全文解析失败: {e}")

    # [4/6] 提取素材
    all_text = "\n".join(m["summary"] for m in result["materials"])
    if all_text:
        result["key_numbers"] = list(set(re.findall(r'\d+[%万千百十亿万\.]+', all_text)))[:20]
        result["sys_words"] = list(set(re.findall(r'[\u4e00-\u9fff]{2,6}(?:系统|流程|平台|模块|管理)', all_text)))[:20]
        print(f"[4/6] 关键数字: {result['key_numbers'][:5]}, 系统: {result['sys_words'][:5]}")

    # [5/6] 读 profile 主题色
    profile_path = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = f.read()
            result["theme_colors"] = re.findall(r'-\s*([\u4e00-\u9fff]+)\s*->\s*(#[0-9a-fA-F]+)', profile)
            print(f"[5/6] 可用主题色: {result['theme_colors'][:3]}")
        except Exception:
            pass

    # [6/6] 生成 spec（+可选 HTML/报价）
    if result["materials"]:
        print("[6/6] 调用 outline-to-spec 生成 spec 草稿...")
        try:
            from _outline_to_spec import build_spec_from_outline
            spec_path = os.path.join(output_dir, f"{client}_spec_draft.yml")
            # 备份（复用 _cli.backup_before_generate 的逻辑，避免循环 import）
            from _backup import backup_before_generate
            backup_before_generate(spec_path)
            material_paths = [os.path.join(refs_dir, m["file"]) for m in result["materials"]]
            build_spec_from_outline(scene, material_paths, client_name=client, output_path=spec_path)
            result["spec_path"] = spec_path
            print(f"  spec 草稿: {spec_path}")
        except Exception as e:
            warnings.append(f"outline-to-spec 失败: {e}")

        # 可选 HTML
        if html and result["spec_path"]:
            # P0 修复：spec 草稿固定 confirmed=False，Renderer 门禁必抛
            # RenderBlockedError，此前该路径必然失败只留一条 warning。
            # 改为明确提示人工确认后走 html-build。
            print("  [提示] spec 草稿未确认（confirmed: false），跳过 HTML 生成。")
            print("        人工检查 spec 并设 confirmed: true 后运行:")
            print(f"        python _cli.py html-build \"{result['spec_path']}\" \"{os.path.join(output_dir, client + '_方案.html')}\" --client {client}")
            result["html_pending"] = True

        # 可选报价
        if quote and result["spec_path"]:
            try:
                from _quote_spec_gen import gen_quote_spec
                from _quote_data import QuoteBuilder
                from _quote_html import render_html as render_quote_html
                from _quote_engine import ExcelRenderer
                from _outline_to_spec import _infer_style_from_client
                from _backup import backup_before_generate
                style_name = _infer_style_from_client(client)
                quote_spec = os.path.join(output_dir, f"{client}_quote_spec.yml")
                backup_before_generate(quote_spec)
                gen_quote_spec(refs_dir, client_name=client, output_path=quote_spec)
                qd = QuoteBuilder().build(quote_spec)
                quote_html = os.path.join(output_dir, f"{client}_报价.html")
                quote_xlsx = os.path.join(output_dir, f"{client}_报价.xlsx")
                render_quote_html(qd, quote_html, style_name=style_name)
                ExcelRenderer().render(qd, "一页报价模板", quote_xlsx, style_name=style_name)
                result["quote_paths"] = {"html": quote_html, "xlsx": quote_xlsx}
                print("  报价 HTML + Excel 已生成")
            except Exception as e:
                warnings.append(f"报价生成失败: {e}")

    return result


def rebuild_bm25_index_all():
    """IDE 模式：重建 BM25 索引（扫描所有客户文件，含别名展开）。等价 CLI index-rebuild。

    P1-2 修复：原实现与 _embed_index.scan_corpus() 有 90%+ 重复分块逻辑，
    现改为调用公共函数 scan_corpus_with_warnings()，单一数据源。

    返回 schema:
    {
        "indexed_count": int,
        "warnings": list
    }
    """
    warnings = []

    if not os.path.isdir(CLIENTS_DIR):
        return {"indexed_count": 0, "warnings": ["无客户目录"]}

    # 复用 _embed_index 的公共分块逻辑（单一数据源，避免逻辑漂移）
    from _embed_index import scan_corpus_with_warnings
    corpus, scan_warnings = scan_corpus_with_warnings()
    warnings.extend(scan_warnings)

    if not corpus:
        return {"indexed_count": 0, "warnings": warnings or ["无可索引内容"]}

    paths = [p for p, _ in corpus]
    texts = [t for _, t in corpus]

    try:
        from _bm25 import build_bm25_index
        bm25_cfg = _RECALL_CONFIG.get("bm25", {})
        build_bm25_index(paths, texts,
                         k1=bm25_cfg.get("k1", 1.5),
                         b=bm25_cfg.get("b", 0.75))
    except Exception as e:
        warnings.append(f"build_bm25_index 失败: {e}")

    return {"indexed_count": len(paths), "warnings": warnings}
