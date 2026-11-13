# -*- coding: utf-8 -*-
"""CLI 生成面命令（T1 拆分自 _cli.py，2026-09-01）。
承载：生成面·文档工具 / quote 与标书。不改命令行为。"""
import os
import sys
import json

import yaml

from _cli_infra import SCRIPT_DIR
from _cli_guards import _run_pre_check
from _quote_spec_gen import gen_quote_spec
from _quote_engine import ExcelRenderer
from _quote_data import Library
from _bid_parse import parse_tender, save_bid_criteria

def _resolve_path(p):
    """把相对路径解析到项目根（与 pdf-pages/extract-md 一致）。"""
    if not p or os.path.isabs(p):
        return p
    return os.path.join(SCRIPT_DIR, p)


def _open_word_doc(docx_path):
    """打开 Word COM 实例与文档，返回 (word, doc)；异常由调用方捕获。"""
    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    # 安全 P1-2：打开外部文档前强制禁宏（msoAutomationSecurityForceDisable）
    word.AutomationSecurity = 3
    word.Visible = False
    word.DisplayAlerts = False
    doc = word.Documents.Open(os.path.abspath(docx_path))
    return word, doc


def _page_of(rng):
    """返回某个 Range 所在页码（wdActiveEndPageNumber=3），失败返回 0。"""
    try:
        return int(rng.Information(3))
    except Exception:  # noqa: BLE001
        return 0


def _paragraph_text(p):
    """去掉段尾回车/单元格结束符后的纯文本。"""
    try:
        return (p.Range.Text or "").replace("\r", "").replace("\x07", "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _table_caption(doc, table):
    """查找表格上方最近的『表X：…』段落作为题注，找不到返回空串。"""
    try:
        prev = table.Range.Previous(1)  # wdParagraph = 1
        text = _paragraph_text(prev)
        if text.startswith(("表", "Table", "表格")):
            return text
    except Exception:  # noqa: BLE001
        pass
    return ""


def cmd_docx_inspect(args):
    """docx-inspect：提取 Word 文档结构（页数/段落数/大纲树/表格/图片），输出 JSON。

    纯只读，不修改文档；依赖 Word COM（pywin32）。
    """
    path = args.docx
    if not os.path.exists(path):
        print(f"[docx-inspect] 文件不存在: {path}")
        sys.exit(1)

    word = None
    doc = None
    try:
        word, doc = _open_word_doc(path)
        result = {
            "file": os.path.abspath(path),
            "pages": _page_of(doc.Range()),
            "paragraphs": 0,
            "outline": [],
            "tables": [],
            "images": [],
        }
        try:
            result["paragraphs"] = int(doc.ComputeStatistics(4))  # wdStatisticParagraphs
        except Exception:  # noqa: BLE001
            result["paragraphs"] = len(doc.Paragraphs)

        # 大纲树：OutlineLevel 1-9 视为标题
        for p in doc.Paragraphs:
            try:
                level = int(p.OutlineLevel)
            except Exception:  # noqa: BLE001
                continue
            if level < 1 or level > 9:
                continue
            text = _paragraph_text(p)
            if not text:
                continue
            result["outline"].append({
                "level": level,
                "text": text,
                "page": _page_of(p.Range),
                "chars": len(text),
            })

        # 表格清单
        for i, t in enumerate(doc.Tables, start=1):
            try:
                rows = int(t.Rows.Count)
            except Exception:  # noqa: BLE001
                rows = 0
            try:
                cols = int(t.Columns.Count)
            except Exception:  # noqa: BLE001
                cols = 0
            result["tables"].append({
                "index": i,
                "rows": rows,
                "cols": cols,
                "page": _page_of(t.Range),
                "caption": _table_caption(doc, t),
            })

        # 图片清单：内嵌图 + 浮动图（Type=3 为图片）
        img_index = 0
        for shape in doc.InlineShapes:
            try:
                if int(shape.Type) != 3:  # wdInlineShapePicture
                    continue
                img_index += 1
                result["images"].append({
                    "index": img_index,
                    "page": _page_of(shape.Range),
                    "width": round(float(shape.Width), 1),
                    "height": round(float(shape.Height), 1),
                })
            except Exception:  # noqa: BLE001
                continue
        for shape in doc.Shapes:
            try:
                if int(shape.Type) != 3:  # wdShapePicture
                    continue
                img_index += 1
                anchor = getattr(shape, "Anchor", None)
                result["images"].append({
                    "index": img_index,
                    "page": _page_of(anchor) if anchor is not None else 0,
                    "width": round(float(shape.Width), 1),
                    "height": round(float(shape.Height), 1),
                })
            except Exception:  # noqa: BLE001
                continue

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ImportError:
        print("[docx-inspect] 缺少 pywin32，无法使用 Word COM")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"[docx-inspect] 失败: {e}")
        sys.exit(1)
    finally:
        if doc:
            try:
                doc.Close(False)
            except Exception:  # noqa: BLE001
                pass
        if word:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                pass


def _find_heading_para(doc, title):
    """按文本精确匹配标题段落，返回 Paragraph 对象或 None。"""
    for p in doc.Paragraphs:
        if _paragraph_text(p) == title:
            return p
    return None


def _edit_insert_after(doc, title, text):
    """在指定标题后插入一个新段落。"""
    para = _find_heading_para(doc, title)
    if para is None:
        raise RuntimeError(f"找不到标题「{title}」")
    rng = para.Range
    rng.Collapse(0)  # wdCollapseEnd=0 -> 标题末尾
    rng.InsertParagraphAfter()
    rng.MoveEnd(1)
    rng.Text = text
    print(f"[docx-edit] 已在「{title}」后插入段落")


def _edit_replace(doc, title, paragraph_index, new_text):
    """替换指定标题下的第 N 段（标题本身算第 0 段，N>=1 为后续正文段）。"""
    para = _find_heading_para(doc, title)
    if para is None:
        raise RuntimeError(f"找不到标题「{title}」")
    cur = para
    target = None
    for _i in range(paragraph_index):
        nxt = cur.Next()
        if nxt is None:
            raise RuntimeError(f"标题「{title}」下没有第 {paragraph_index} 段")
        cur = nxt
        target = cur
    if target is None:
        raise RuntimeError(f"标题「{title}」下没有第 {paragraph_index} 段")
    target.Range.Text = new_text
    print(f"[docx-edit] 已替换标题「{title}」下第 {paragraph_index} 段")


def _edit_delete_section(doc, title):
    """删除以指定标题起、到下一个同级/更高级标题之前的整节内容。"""
    para = _find_heading_para(doc, title)
    if para is None:
        raise RuntimeError(f"找不到标题「{title}」")
    start = int(para.Range.Start)
    try:
        cur_level = int(para.OutlineLevel)
    except Exception:  # noqa: BLE001
        cur_level = 1
    end = int(doc.Range().End)
    for p in doc.Paragraphs:
        if int(p.Range.Start) <= start:
            continue
        try:
            lvl = int(p.OutlineLevel)
        except Exception:  # noqa: BLE001
            continue
        if 1 <= lvl <= cur_level:
            end = int(p.Range.Start)
            break
    rng = doc.Range(start, end)
    rng.Delete()
    print(f"[docx-edit] 已删除节「{title}」")


def _edit_insert_image(doc, title, image_path, caption):
    """在指定标题后插入图片（含可选图题）。"""
    para = _find_heading_para(doc, title)
    if para is None:
        raise RuntimeError(f"找不到标题「{title}」")
    if not os.path.exists(image_path):
        raise RuntimeError(f"图片不存在: {image_path}")
    rng = para.Range
    rng.Collapse(0)  # 标题末尾
    rng.InsertParagraphAfter()
    rng.MoveEnd(1)
    rng.InlineShapes.AddPicture(FileName=os.path.abspath(image_path), Range=rng)
    if caption:
        rng.Collapse(0)
        rng.InsertParagraphAfter()
        rng.MoveEnd(1)
        rng.Text = caption
        try:
            rng.ParagraphFormat.Alignment = 1  # wdAlignParagraphCenter
        except Exception:  # noqa: BLE001
            pass
    print(f"[docx-edit] 已在「{title}」后插入图片")


def cmd_docx_edit(args):
    """docx-edit：精确修改 Word 文档（插入/替换/删节/插图/重排编号）。

    子操作（互斥，一次一个）：
        --insert-after "标题" --text "内容"
        --replace "标题" --paragraph N --text "新内容"
        --delete-section "标题"
        --insert-image "标题" --image "图片路径" --caption "图题"
        --renumber（全文重排编号，走 COM 契约函数）
    """
    path = args.docx
    if not os.path.exists(path):
        print(f"[docx-edit] 文件不存在: {path}")
        sys.exit(1)

    # 操作互斥与必填参数校验
    if getattr(args, "renumber", False):
        if (getattr(args, "insert_after", None) or getattr(args, "replace", None)
                or getattr(args, "delete_section", None) or getattr(args, "insert_image", None)):
            print("[docx-edit] --renumber 需单独使用")
            sys.exit(1)
        from _renderer.docx_com_postprocess import renumber_headings
        ok = renumber_headings(path)
        sys.exit(0 if ok else 1)

    if getattr(args, "insert_after", None):
        if not getattr(args, "text", None):
            print("[docx-edit] --insert-after 需要 --text 内容")
            sys.exit(1)
    elif getattr(args, "replace", None):
        if getattr(args, "paragraph", None) is None or not getattr(args, "text", None):
            print("[docx-edit] --replace 需要 --paragraph N 与 --text 新内容")
            sys.exit(1)
    elif getattr(args, "delete_section", None):
        pass
    elif getattr(args, "insert_image", None):
        if not getattr(args, "image", None):
            print("[docx-edit] --insert-image 需要 --image 图片路径")
            sys.exit(1)
    else:
        print("[docx-edit] 未指定任何操作（--insert-after/--replace/--delete-section/--insert-image/--renumber）")
        sys.exit(1)

    word = None
    doc = None
    try:
        word, doc = _open_word_doc(path)
        if getattr(args, "insert_after", None):
            _edit_insert_after(doc, args.insert_after, args.text)
        elif getattr(args, "replace", None):
            _edit_replace(doc, args.replace, args.paragraph, args.text)
        elif getattr(args, "delete_section", None):
            _edit_delete_section(doc, args.delete_section)
        elif getattr(args, "insert_image", None):
            _edit_insert_image(doc, args.insert_image, args.image, getattr(args, "caption", None) or "")
        doc.Save()
        print(f"[docx-edit] 完成，已保存: {os.path.abspath(path)}")
    except Exception as e:  # noqa: BLE001
        print(f"[docx-edit] 失败: {e}")
        sys.exit(1)
    finally:
        if doc:
            try:
                doc.Close(False)
            except Exception:  # noqa: BLE001
                pass
        if word:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                pass


def cmd_word_com(args):
    """word-com：Word 排版操作族（normalize/renumber/polish/to-pdf/accept/compare）。

    排版核心全部复用 _renderer.docx_com_postprocess 契约函数。
    """
    from _renderer.docx_com_postprocess import (
        renumber_headings, normalize_headings, apply_style_set,
        apply_headers_footers, refresh_toc, save_as_pdf,
        accept_all_changes, compare_documents,
    )

    sub = getattr(args, "word_com_cmd", None)
    path = getattr(args, "file", None)

    if not sub or not path:
        print("[word-com] 用法: python _cli.py word-com <normalize|renumber|polish|apply-style|to-pdf|accept|compare> <文件>")
        sys.exit(1)
    if not os.path.exists(path):
        print(f"[word-com] 文件不存在: {path}")
        sys.exit(1)

    if sub == "apply-style":
        # 只改样式定义与段落格式，不碰文字（纯 python-docx，无 COM）
        from _renderer.docx_style_0910 import apply_style_0910
        style_set = getattr(args, "style_set", "gs0910") or "gs0910"
        if not getattr(args, "no_backup", False):
            import shutil
            from datetime import datetime
            ver_dir = os.path.join(os.path.dirname(os.path.abspath(path)), ".versions")
            try:
                os.makedirs(ver_dir, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy2(path, os.path.join(
                    ver_dir, f"{os.path.basename(path)}.{stamp}"))
                print(f"[word-com] 已备份到 .versions/（{stamp}）")
            except Exception as e:  # pragma: no cover - 备份失败不阻断
                print(f"[word-com] 备份失败（不阻断）: {e}")
        ok, info = apply_style_0910(
            path, style_set=style_set,
            numbering=not getattr(args, "no_numbering", False))
        if not ok:
            print(f"[word-com] apply-style 失败: {info.get('error', '未知错误')}")
            sys.exit(1)
        print(f"[word-com] apply-style 完成（样式集 {style_set}）："
              f"样式 {len(info['styles'])} 项 / 图题 {info['captions']} 段 / "
              f"表格段 {info['table_paragraphs']} 段 / 全文 {info['text_chars']} 字"
              + (f" / 编号 {info.get('numbering', {}).get('numbering', '')}"
                 if isinstance(info.get("numbering"), dict) else ""))
        sys.exit(0)

    if sub == "normalize":
        n = normalize_headings(path)
        sys.exit(0 if n is not False else 1)

    if sub == "renumber":
        style = getattr(args, "style", "chinese_multi") or "chinese_multi"
        ok = renumber_headings(path, style=style)
        sys.exit(0 if ok else 1)

    if sub == "polish":
        style_set = getattr(args, "style_set", "bid") or "bid"
        project_name = getattr(args, "project_name", "") or ""
        # P3：各步骤尽力执行（失败不中断后续步骤），但逐项记账，
        # 结尾如实上报失败步骤并以 exit 1 退出——不再静默报"完成"
        failed = []
        if normalize_headings(path) is False:
            failed.append("normalize")
        if renumber_headings(path) is False:
            failed.append("renumber")
        if apply_style_set(path, style_set=style_set) is False:
            failed.append("style_set")
        if apply_headers_footers(path, project_name=project_name) is False:
            failed.append("headers_footers")
        if refresh_toc(path) is False:
            failed.append("toc")
        if getattr(args, "pdf", False):
            if save_as_pdf(path) is False:
                failed.append("pdf")
        if failed:
            print(f"[word-com] polish 失败 {len(failed)} 个步骤（{'、'.join(failed)}），未全部完成，请检查上方日志后重跑")
            sys.exit(1)
        print("[word-com] polish 完成")
        return

    if sub == "to-pdf":
        ok = save_as_pdf(path)
        sys.exit(0 if ok else 1)

    if sub == "accept":
        ok = accept_all_changes(path)
        sys.exit(0 if ok else 1)

    if sub == "compare":
        other = getattr(args, "other", None)
        if not other:
            print("[word-com] compare 需要 --other <旧版>")
            sys.exit(1)
        if not os.path.exists(other):
            print(f"[word-com] 旧版文件不存在: {other}")
            sys.exit(1)
        ok = compare_documents(path, other)
        sys.exit(0 if ok else 1)

    print(f"[word-com] 未知子命令: {sub}")
    sys.exit(1)


def cmd_template_fill(args):
    """template-fill：docxtpl 填充模板 + COM 后处理（normalize + renumber + refresh_toc）。"""
    template = args.template
    data_path = args.data
    out_path = args.output

    if not template or not os.path.exists(template):
        print(f"[template-fill] 模板不存在: {template}")
        sys.exit(1)
    if not data_path or not os.path.exists(data_path):
        print(f"[template-fill] 数据文件不存在: {data_path}")
        sys.exit(1)
    if not out_path:
        print("[template-fill] 需要输出路径（-o/--output）")
        sys.exit(1)
    out_path = _resolve_path(out_path)

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[template-fill] 读取数据失败: {e}")
        sys.exit(1)
    if not isinstance(data, dict):
        print("[template-fill] 数据文件须为 JSON 对象")
        sys.exit(1)

    try:
        from docxtpl import DocxTemplate
    except ImportError:
        print("[template-fill] 缺少 docxtpl，运行 pip install docxtpl")
        sys.exit(1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        tpl = DocxTemplate(template)
        tpl.render(data)
        tpl.save(out_path)
    except Exception as e:  # noqa: BLE001
        print(f"[template-fill] 模板渲染失败: {e}")
        sys.exit(1)

    from _renderer.docx_com_postprocess import (
        normalize_headings, renumber_headings, refresh_toc,
    )
    normalize_headings(out_path)
    renumber_headings(out_path)
    refresh_toc(out_path)
    print(f"[template-fill] 完成 -> {os.path.abspath(out_path)}")





def cmd_quote_spec_gen(args):
    """从客户材料提取报价 spec.yml。"""
    # 生成前强制验证
    client = getattr(args, 'client', None) or None
    pre_check_result = _run_pre_check(client_name=client)
    if pre_check_result is None:
        print("[阻断] 生成前检查失败（依赖缺失），停止生成")
        sys.exit(1)

    # §八 3.5：输出白名单前置校验，避免材料读取 + LLM 提取完才在写入点抛异常
    # （gen_quote_spec 入口同样有校验兜底）
    from _renderer import _validate_output_path, OutputPathNotAllowedError
    try:
        _validate_output_path(args.output)
    except OutputPathNotAllowedError as e:
        print(f"[阻断] {e}")
        print("  提示：报价 spec 属产出物，输出路径请放在 output/ 下"
              "（如 output/通用/quote_spec.yml）")
        sys.exit(1)

    output_path = gen_quote_spec(args.materials_dir, client_name=args.client, output_path=args.output)
    # P0-3：生成失败（材料缺失/无报价内容/写入失败）返回 None 时必须非零退出，
    # 否则交付链把失败当成功继续走
    if not output_path:
        print("[失败] quote-spec-gen 未能生成 spec（材料缺失或无报价内容），详见上方日志")
        sys.exit(1)

    # 生成后自动验证
    if os.path.exists(output_path):
        print("\n[验证] 自动验证生成产出...")
        try:
            from _verify_hook import run_single  # late import，同 cmd_verify
            run_single(output_path)
        except Exception as e:
            print(f"[验证] 跳过: {e}")


def cmd_quote_validate(args):
    """校验报价 Excel 公式"""
    renderer = ExcelRenderer()
    issues = renderer.validate(args.xlsx)
    if issues:
        # P1-3：有问题必须非零退出，否则流水线/脚本无法感知校验失败
        print("校验问题:")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    print("校验通过")


def cmd_quote_library(args):
    """管理报价内容库：list / search"""
    lib_dir = os.path.join(SCRIPT_DIR, "_knowledge", "quote_library")
    type_file = {
        "modules": "modules.yaml",
        "licenses": "licenses.yaml",
        "services": "services.yaml",
        "thirdparty": "thirdparty.yaml",
    }
    fname = type_file.get(args.type)
    if not fname:
        print(f"未知类型: {args.type}")
        sys.exit(1)
    path = os.path.join(lib_dir, fname)
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    root_key = args.type if args.type != "services" else "roles"
    items = data.get(root_key, []) or []
    if args.action == "search" and args.keyword:
        kw = args.keyword.lower()
        items = [it for it in items if kw in str(it.get("name", "")).lower() or kw in str(it.get("description", "")).lower()]
    print(f"=== {args.type} ({len(items)} 条) ===")
    for it in items:
        print(f"  [{it.get('id')}] {it.get('name', '')}  ¥{it.get('unit_price', it.get('price_register', '-'))}")
        if args.action == "search" and it.get("description"):
            desc = str(it["description"])[:60]
            print(f"      {desc}")


def cmd_quote_search(args):
    """语义搜索全报价内容库"""
    lib = Library()
    results = lib.search(args.keyword, args.top)
    if not results:
        print(f"未找到匹配 '{args.keyword}' 的内容")
        return
    print(f"=== 搜索 '{args.keyword}' ({len(results)} 条) ===")
    for r in results:
        print(f"  [{r['id']}] {r['name']}  ¥{r.get('unit_price', '-')}  [{r.get('group', '')}]")
        if r.get("description"):
            print(f"      {r['description']}")


# ============================================================
# theme-guard：合并 theme-list + theme-set（PROJECT_DESIGN.md §13）
# ============================================================


def cmd_bid_parse(args):
    """解析招标文件，提取评分标准/格式要求/资质条款。"""
    from _cli_infra import _guard_read_path
    path = _guard_read_path(args, args.file, label="bid-parse")
    client = getattr(args, 'client', None) or ""
    do_split = not getattr(args, 'no_split', False)
    criteria = parse_tender(path, client_name=client, do_split=do_split)
    save_bid_criteria(criteria, client_name=client)

