# -*- coding: utf-8 -*-
"""spec -> pptd 工程生成器（L3 确定性生成，无 LLM 调用）。

从已确认的 spec.yml 机械生成 pptd 工程骨架（主 pptd + pages/*.page +
media/ + DESIGN_GUIDE.md），让分页代理只做内容润色。

设计依据：docs/dev_plan_pptd_spec_gen_2026-07-18.md
方言母版：v3 工程实例（内部基准）
方言硬规则（§8 六陷阱）：
  1. 主 pptd 顶层不写 version 字段
  2. 粗体只发行内 <strong>；textStyles 不写 bold 属性
  3. 斜体 <em> 默认不用
  4. 图片 src 只写绝对路径
  5. 表格单元格必须是 {content: ...} 对象，不是裸字符串
  6. 表格样式走 headerFill 系列 + style: "$default" 引用
另：禁用 Icon 元素（convert 时退化，v3 踩坑）
"""

import os
import re
import shutil

import yaml

from _renderer.elements import RenderReport, _esc, degrade_text, empty_payload_reason, is_empty_payload, normalize_element
from _renderer.spacing import GAP_LG, GAP_MD, INSET_X, snap
from _renderer.theme import DEFAULT_FONT, resolve_theme, style_name_for_entry


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def load_spec(path):
    """读 spec.yml -> dict。文件不存在 -> FileNotFoundError。"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_deck(spec, spec_path, style, name, out_dir, logo_path=None, client_name=None,
               report=None):
    """从 spec 构建 pptd 工程文件映射（纯函数，不落盘）。

    返回 (files, media_files):
      files: {相对路径: 内容字符串}（主 pptd + pages/*.page + DESIGN_GUIDE.md）
      media_files: [(源绝对路径, media 内文件名)]（emit 时复制到 out_dir/media/）

    spec_path: spec.yml 绝对路径（解析 spec 内相对路径的基准）
    style: _resolve_style 返回的 dict（含 colors / fonts）
    name: 项目名（主 pptd 文件名，不含扩展名）
    out_dir: 工程输出目录绝对路径（写 media/ 绝对路径引用用）
    logo_path: 显式 logo 源文件绝对路径；None 则探测 spec/refs/output media/
    client_name: 客户名，用于 refs/ 探测 logo 和 DESIGN_GUIDE 个性化
    report: RenderReport 实例（缺省新建）；元素降级/跳过都进 report（§6.3）
    """
    report = report or RenderReport()
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    theme = _build_theme(style)
    style_name = style_name_for_entry(style)  # diagram 风格透传（P2-A2）
    # v2 主题包名（§5.1 双形态：str = v2 主题；dict/缺省 = None → legacy）
    _spec_theme = spec.get("theme")
    v2_theme_name = _spec_theme if isinstance(_spec_theme, str) else None

    files = {}
    media_files = []

    # logo 解析：--logo > spec.document.cover.logo_image > refs/ 探测 > output media/ 探测 > 跳过
    logo_src, logo_media_name = _resolve_logo(spec, spec_dir, logo_path, client_name)
    if logo_src:
        media_files.append((logo_src, logo_media_name))
    logo_abs_in_deck = _media_abs_path(out_dir, logo_media_name) if logo_media_name else None

    # cover 背景图
    bg_src, bg_media_name = _resolve_background_image(spec, spec_dir)
    if bg_src:
        media_files.append((bg_src, bg_media_name))
    bg_abs_in_deck = _media_abs_path(out_dir, bg_media_name) if bg_media_name else None

    # 主 pptd
    main_pptd = {
        "title": spec.get("document", {}).get("title", name),
        "size": [1280, 720],
        "theme": theme,
        "pages": [],
    }

    # v2 规格：P01 hero 已承载封面信息，跳过旧式 cover 页（防重复空白封面）
    _has_hero = any(
        isinstance(e, dict) and e.get("type") == "hero"
        for p in spec.get("pages", []) for e in p.get("elements", []))
    if not _has_hero:
        files["pages/01_cover.page"] = _build_cover_page(
            spec, logo_abs_in_deck, bg_abs_in_deck)
        main_pptd["pages"].append("pages/01_cover.page")

    # spec.pages -> content 页
    for idx, page_spec in enumerate(spec.get("pages", [])):
        page_num = idx + (2 if not _has_hero else 1)
        slug = _page_slug(page_spec, idx)
        filename = f"pages/{page_num:02d}_{slug}.page"
        files[filename] = _build_content_page(
            page_spec, theme, logo_abs_in_deck, page_num, report=report,
            author=spec.get("author"), style_name=style_name,
            v2_theme_name=v2_theme_name)
        main_pptd["pages"].append(filename)

    files[f"{name}.pptd"] = yaml.safe_dump(
        main_pptd, allow_unicode=True, sort_keys=False, default_flow_style=False)

    # DESIGN_GUIDE.md（P3：模板参数化）
    files["DESIGN_GUIDE.md"] = _build_design_guide(
        spec, theme, logo_abs_in_deck, bg_abs_in_deck, client_name, name, out_dir)
    return files, media_files


def emit_deck(files, media_files, out_dir):
    """落盘 files 到 out_dir + 复制 media_files 到 out_dir/media/。

    files: {相对路径: 内容字符串}
    media_files: [(源绝对路径, media 内文件名)]
    out_dir: 工程输出目录绝对路径
    """
    os.makedirs(out_dir, exist_ok=True)
    # 清理旧 pages/（防上一版 .page 残留，避免 pptd check 扫描到旧页）
    pages_dir = os.path.join(out_dir, "pages")
    if os.path.isdir(pages_dir):
        for fn in os.listdir(pages_dir):
            if fn.endswith(".page"):
                try:
                    os.remove(os.path.join(pages_dir, fn))
                except OSError:
                    pass
    for rel_path, content in files.items():
        full_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
    media_dir = os.path.join(out_dir, "media")
    for src, name in media_files:
        os.makedirs(media_dir, exist_ok=True)
        dst = os.path.join(media_dir, name)
        if os.path.abspath(src) != os.path.abspath(dst) and os.path.exists(src):
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# 主题
# ---------------------------------------------------------------------------

def _build_theme(style):
    """从 style dict 派生 pptd theme（colors + textStyles + tableStyles）。

    色板 11 槽消费样式单一源 resolve_theme(...).pptd_colors（§七 2.1/2.2）：
    enterprise 锚定 DEFAULT_PPTD_SLOTS（基线零 diff），其余风格从 5 基色
    派生。style 是 _resolve_style 返回的 styles.json entry（不含键名），
    键名经 style_name_for_entry 反查。textStyles 七套（pagetitle/lead/
    bodytext/small/footer/cardtitle/cardbody），fontFamily 统一
    theme.fonts.body（§七 2.3，原 MiSans 硬编码收敛）。陷阱 2：textStyles
    不写 bold 属性。tableStyles default：headerFill + headerColor +
    headerBold（tableStyles 允许 headerBold，陷阱 2 只约束 textStyles）。
    """
    theme = resolve_theme(style_name_for_entry(style))
    colors = dict(theme.pptd_colors)
    font = theme.fonts.get("body", DEFAULT_FONT)

    text_styles = {
        "pagetitle": {"fontSize": 32, "color": "$ink", "fontFamily": font, "lineHeight": 1.25},
        "lead": {"fontSize": 16, "color": "$lead", "fontFamily": font, "lineHeight": 1.6},
        "bodytext": {"fontSize": 14, "color": "$body", "fontFamily": font, "lineHeight": 1.65},
        "small": {"fontSize": 12, "color": "$gray", "fontFamily": font, "lineHeight": 1.5},
        "footer": {"fontSize": 11, "color": "$gray", "fontFamily": font},
        "cardtitle": {"fontSize": 15, "color": "$navy", "fontFamily": font},
        "cardbody": {"fontSize": 13, "color": "$body", "fontFamily": font, "lineHeight": 1.55},
    }
    table_styles = {
        "default": {
            "fontSize": 14,
            "fontFamily": font,
            "headerFill": "$navy",
            "headerColor": "#FFFFFF",
            "headerBold": True,
            "bodyColor": "$body",
            "border": [None, None, {"style": "solid", "width": 0.75, "color": "$hairline"}, None],
        }
    }
    return {"colors": colors, "textStyles": text_styles, "tableStyles": table_styles}


def _deck_font(theme):
    """甲板统一字体：textStyles.bodytext 的 fontFamily（theme dict 单一源）。"""
    return theme["textStyles"]["bodytext"].get("fontFamily", DEFAULT_FONT)


# ---------------------------------------------------------------------------
# cover 页（v3 全要素版）
# ---------------------------------------------------------------------------

def _build_cover_page(spec, logo_abs, bg_abs):
    """构建 01_cover.page 内容（v3 全要素版）。

    要素：background image + mask + logo + title + subtitle + author + confidential。
    所有字段从 spec.document.cover / spec.document / spec.author / spec.date 推导。
    """
    doc = spec.get("document", {})
    cover_cfg = doc.get("cover", {})

    veil = cover_cfg.get("veil", "#0A1540")
    veil_opacity = cover_cfg.get("veil_opacity", 0.8)
    mask_color = f"{veil}{_opacity_to_hex(veil_opacity)}"

    # 有背景图：image + mask；无背景图：纯色底（veil 色），避免 src='' 触发 EmptySrcError
    if bg_abs:
        background = {
            "type": "image",
            "src": bg_abs,
            "fit": {"mode": "cover"},
            "mask": {"type": "solid", "color": mask_color},
        }
    else:
        background = {"type": "solid", "color": veil}

    elements = []

    if logo_abs:
        elements.append({
            "elementId": "logo",
            "elementType": "image",
            "bounds": [38, 43, 209, 50],
            "src": logo_abs,
            "fit": {"mode": "contain"},
        })

    elements.append({
        "elementId": "title",
        "elementType": "text",
        "bounds": [102, 278, 1050, 66],
        "content": {
            "fontSize": 52,
            "color": "#FFFFFF",
            "align": ["left", "middle"],
            "wrap": False,
            "text": f"<p><strong>{_esc(doc.get('title', ''))}</strong></p>\n",
        },
    })

    if doc.get("subtitle"):
        elements.append({
            "elementId": "subtitle",
            "elementType": "text",
            "bounds": [102, 360, 1050, 34],
            "content": {
                "fontSize": 21,
                "color": "#FFFFFFD9",
                "align": ["left", "middle"],
                "wrap": False,
                "text": _esc(str(doc["subtitle"])) + "\n",
            },
        })

    if cover_cfg.get("show_author", True) and spec.get("author"):
        elements.append({
            "elementId": "author",
            "elementType": "text",
            "bounds": [102, 408, 500, 26],
            "content": {
                "fontSize": 15,
                "color": "#FFFFFFA6",
                "align": ["left", "middle"],
                "wrap": False,
                "text": _esc(str(spec["author"])) + "\n",
            },
        })

    if cover_cfg.get("confidential"):
        conf_text = str(cover_cfg["confidential"])
        if cover_cfg.get("show_date", True) and spec.get("date"):
            conf_text = f"{conf_text} · {spec['date']}"
        elements.append({
            "elementId": "confidential",
            "elementType": "text",
            "bounds": [880, 30, 360, 18],
            "content": {
                "fontSize": 11,
                "color": "#FFFFFFCC",
                "align": ["right", "middle"],
                "wrap": False,
                "text": _esc(conf_text) + "\n",
            },
        })

    _snap_page_elements(elements)
    page = {
        "pageType": "cover",
        "background": background,
        "elements": elements,
    }
    return yaml.safe_dump(page, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# content 页（三件套 + text/bullets）
# ---------------------------------------------------------------------------

def _build_content_page(page_spec, theme, logo_abs, page_num, report=None, author=None,
                        style_name=None, v2_theme_name=None):
    """构建 content 页：固定三件套 + spec 元素（text/heading/bullets/cards/table/phases/pullquote）。

    三件套：页眉 logo + 页标题（pagetitle 样式，<strong> 包裹）+ 页脚。
    页脚左版权文案取 spec.author，缺省回退 "Syzygit Technology"（§七 2.3 顺带小修）。
    内容区 y 游标从 130 起，按元素顺序堆叠。
    字段读取走 _renderer.elements normalize 层（§6.1）；architecture_4a
    走 degrade_text 显式降级，未知 type 进 report，不再静默跳过。
    用户文本统一过 _esc 转义（§七 2.6）。
    溢出三级防线（§七 2.5，§七 2.8 底边感知补强）：y 游标过 _CONTENT_Y_SHRINK
    先收缩正文排版（第二级 自动适配）；元素底边（y+h）预估超 _CONTENT_Y_MAX 时
    正文类元素提前升 shrink 重排，仍超线则高度裁剪到可用空间 + report.warn
    （不丢内容，PPT 文本框自然截断）；只有 y 游标起点过 _CONTENT_Y_MAX 的元素
    才整元素截断进 report（第三级 硬防线）。diagram 分支经 I-16 接入页底防线：
    超高先均匀缩放压回界内，缩到 0.5 仍超则整图 skip 进 report。
    product_intro_placeholder 分支同款：超高经 _clamp_bottom 裁切告警后均匀
    缩进可用高度，可用不足一行则整元素 skip。pullquote 分支同款三档（底边
    超线先 shrink 引文 18->16，仍超 _clamp_bottom 裁切，不足一行 skip）；
    cards/phases 整组 clamp 路径同样带"可用不足一行整组 skip"档（§七 2.8 d）。
    页级填充（版式改进）：所有内容元素 emit 完成后、页脚追加前，跑
    _fill_content_area——内容底边不足可用区 75% 时纵向放大到 ~88%，解决
    "内容挤在页面上部、下半页全空"；只向上填充，fontSize 不变（安全阀）。
    方言陷阱 5：表格单元格 {content: ...} 对象。
    方言陷阱 2：粗体只发行内 <strong>。
    PRD Q5：禁用 Icon 元素。
    """
    report = report or RenderReport()
    page_id = page_spec.get("id")
    deck_font = _deck_font(theme)
    elements = []

    # 三件套之 1：页眉 logo
    if logo_abs:
        elements.append({
            "elementId": "header-logo",
            "elementType": "image",
            "bounds": [26, 29, 46, 40],
            "src": logo_abs,
            "fit": {"mode": "contain"},
        })

    # 三件套之 2：页标题
    title_text = str(page_spec.get("title", ""))
    page_elems = page_spec.get("elements", [])
    # page_header（D-092 页眉横幅）居首时：navy 横幅顶替素标题，与 HTML 端
    # 页眉同构——此前 PPTD 端 page_header 落 else 被 skip，整稿无页眉条
    ph_type, ph_norm = (normalize_element(page_elems[0])
                        if page_elems else (None, None))
    ph_first = ph_type == "page_header"
    if ph_first:
        from _renderer.diagram.pptd_emit import emit_chrome_pptd
        ph_elems, ph_h = emit_chrome_pptd("page_header", ph_norm, _CONTENT_X,
                                          40, _CONTENT_W,
                                          theme_name=v2_theme_name)
        elements.extend(ph_elems)
        y_cursor = 40 + ph_h + GAP_MD
    else:
        elements.append({
            "elementId": "title",
            "elementType": "text",
            "bounds": [_CONTENT_X, 54, _CONTENT_W, 46],
            "content": {
                "style": "$pagetitle",
                "align": ["left", "middle"],
                "wrap": False,
                "text": f"<p><strong>{_esc(title_text)}</strong></p>\n",
            },
        })
        y_cursor = 130

    # 内容元素（y 游标堆叠；page_header 居首时游标已在横幅下方且首元素已消费）
    content_x = _CONTENT_X
    content_w = _CONTENT_W
    shrink = False
    for index, elem in enumerate(page_spec.get("elements", [])):
        if index == 0 and ph_first:
            continue
        elem_type, normalized = normalize_element(elem)
        # 已知类型但内容为空——多为字段名写错，计 skipped 而非静默丢失
        if is_empty_payload(elem_type, normalized):
            report.skip(page_id, index, elem_type,
                        empty_payload_reason(elem_type))
            continue
        # 第三级 硬防线（§七 2.5）：y 游标越过内容区下限（_CONTENT_Y_MAX，
        # 页脚 y=690 留 16px 间距）的元素不再 emit，进渲染报告
        if y_cursor > _CONTENT_Y_MAX:
            report.skip(page_id, index, elem_type, "页面溢出截断")
            continue
        # 第二级 自动适配：y 游标过收缩线（_CONTENT_Y_SHRINK）后，正文类元素
        # 缩字号 2px、bullets 压行距——抄 Beautiful.ai Smart Slides 作业：
        # 规则引擎发现内容超量时先自动缩排尝试放下，仍超高才走第三级截断
        if not shrink and y_cursor > _CONTENT_Y_SHRINK:
            shrink = True
        if elem_type == "text":
            text_content = normalized["content"]
            body_size = _SHRINK_BODY_SIZE if shrink else 14
            h = _estimate_text_height(text_content, font_size=body_size, line_height=1.65, width=content_w)
            if not shrink and y_cursor + h > _CONTENT_Y_MAX:
                # 底边感知（§七 2.8）：底边预估超线先升 shrink 重排
                shrink = True
                body_size = _SHRINK_BODY_SIZE
                h = _estimate_text_height(text_content, font_size=body_size, line_height=1.65, width=content_w)
            eid = f"elem-{int(y_cursor)}"
            h = _clamp_bottom(page_id, eid, y_cursor, h, report, font_size=body_size)
            if h is None:
                # 可用空间不足一行：不 emit 裁剪碎片（§七 2.8 d）
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            content = {
                "style": "$bodytext",
                "align": ["left", "top"],
                "text": _esc(text_content.rstrip("\n")) + "\n",
            }
            if shrink:
                # 显式 fontSize 覆盖 $bodytext 样式的 14px（行距保持 1.65）
                content["fontSize"] = body_size
            elements.append({
                "elementId": eid,
                "elementType": "text",
                "bounds": [content_x, y_cursor, content_w, h],
                "content": content,
            })
            y_cursor += h + GAP_MD
        elif elem_type == "heading":
            # heading 补格：比正文大的粗体主色文本（pagetitle 32 之下、bodytext 14 之上）
            heading_text = normalized["text"]
            font_size = max(16, 24 - (normalized["level"] - 1) * 2)
            if shrink:
                font_size = max(12, font_size - 2)
            h = _estimate_text_height(heading_text, font_size=font_size, line_height=1.3, width=content_w)
            if not shrink and y_cursor + h > _CONTENT_Y_MAX:
                # 底边感知（§七 2.8）：底边预估超线先升 shrink 重排
                shrink = True
                font_size = max(12, font_size - 2)
                h = _estimate_text_height(heading_text, font_size=font_size, line_height=1.3, width=content_w)
            eid = f"elem-{int(y_cursor)}"
            h = _clamp_bottom(page_id, eid, y_cursor, h, report, font_size=font_size)
            if h is None:
                # 可用空间不足一行：不 emit 裁剪碎片（§七 2.8 d）
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            elements.append({
                "elementId": eid,
                "elementType": "text",
                "bounds": [content_x, y_cursor, content_w, h],
                "content": {
                    "fontSize": font_size,
                    "color": "$primary",
                    "fontFamily": deck_font,
                    "lineHeight": 1.3,
                    "align": ["left", "middle"],
                    "text": f"<p><strong>{_esc(heading_text)}</strong></p>\n",
                },
            })
            y_cursor += h + GAP_MD
        elif elem_type == "bullets":
            items = normalized["items"]
            rendered = "\n".join(f"<p>• {_esc(it)}</p>" for it in items)
            text_block = rendered + "\n" if rendered else "\n"
            body_size = _SHRINK_BODY_SIZE if shrink else 14
            body_lh = _SHRINK_BODY_LINE_HEIGHT if shrink else 1.65
            h = _estimate_bullets_height(items, font_size=body_size, line_height=body_lh, width=content_w)
            if not shrink and y_cursor + h > _CONTENT_Y_MAX:
                # 底边感知（§七 2.8）：底边预估超线先升 shrink 重排
                shrink = True
                body_size = _SHRINK_BODY_SIZE
                body_lh = _SHRINK_BODY_LINE_HEIGHT
                h = _estimate_bullets_height(items, font_size=body_size, line_height=body_lh, width=content_w)
            eid = f"elem-{int(y_cursor)}"
            h = _clamp_bottom(page_id, eid, y_cursor, h, report, font_size=body_size)
            if h is None:
                # 可用空间不足一行：不 emit 裁剪碎片（§七 2.8 d）
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            content = {
                "style": "$bodytext",
                "align": ["left", "top"],
                "text": text_block,
            }
            if shrink:
                # 缩字号 + 压行距，显式覆盖 $bodytext 样式
                content["fontSize"] = body_size
                content["lineHeight"] = body_lh
            elements.append({
                "elementId": eid,
                "elementType": "text",
                "bounds": [content_x, y_cursor, content_w, h],
                "content": content,
            })
            y_cursor += h + GAP_MD
        elif elem_type == "cards":
            cards = normalized["cards"]
            if cards:
                # 整组底边超线时组内高度裁剪 + 警告；可用不足一行整组 skip（§七 2.8）
                card_h, consumed = _emit_cards(
                    elements, cards, content_x, y_cursor, content_w,
                    max_h=_CONTENT_Y_MAX - y_cursor, report=report, page_id=page_id,
                    index=index)
                if card_h == 0:
                    continue  # 整组 skip（可用空间不足一行），不推进 y 游标
                y_cursor += card_h + GAP_MD
        elif elem_type == "table":
            headers = normalized["headers"]
            rows = normalized["rows"]
            if headers or rows:
                n_before = len(elements)
                table_h = _emit_table(elements, headers, rows, content_x, y_cursor, content_w)
                # 底边兜底：table 无 shrink 档，超高直接裁高度（行高等比压缩）
                clamped_h = _clamp_bottom(page_id, f"table-{int(y_cursor)}", y_cursor, table_h,
                                          report, font_size=14)
                if clamped_h is None:
                    # 可用空间不足一行：回退已 emit 的表格，整元素 skip（§七 2.8 d）
                    del elements[n_before]
                    report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                    continue
                if clamped_h != table_h:
                    elements[n_before]["bounds"][3] = clamped_h
                    table_h = clamped_h
                y_cursor += table_h + GAP_MD
        elif elem_type == "phases":
            phases = normalized["phases"]
            if phases:
                # 经 normalize_phases 归一到 name/desc/actions；PPTD 仍只发
                # name/desc（不发 actions，保持现状），字段兼容只在 normalize 层做
                # 高度自适应 + 整组底边裁剪；可用不足一行整组 skip（§七 2.8）
                phase_h = _emit_phases(
                    elements, phases, content_x, y_cursor, content_w,
                    max_h=_CONTENT_Y_MAX - y_cursor, report=report, page_id=page_id,
                    index=index)
                if phase_h == 0:
                    continue  # 整组 skip（可用空间不足一行），不推进 y 游标
                y_cursor += phase_h + GAP_MD
        elif elem_type == "pullquote":
            quote = normalized["content"]
            cite = normalized["cite"]
            # 页底防线（§七 2.8，与 text/bullets 同款三档）：底边预估超线先升
            # shrink 重排（引文 18 -> 16），仍超则 _clamp_bottom 裁切 + warn；
            # 可用不足一行整元素 skip（y 游标过线由第三级硬防线拦截）
            quote_size = _SHRINK_QUOTE_SIZE if shrink else _PULLQUOTE_QUOTE_SIZE
            pq_h = _estimate_pullquote_height(quote, cite, quote_size,
                                              content_w - 2 * INSET_X)
            if not shrink and y_cursor + pq_h > _CONTENT_Y_MAX:
                # 底边感知（§七 2.8）：底边预估超线先升 shrink 重排
                shrink = True
                quote_size = _SHRINK_QUOTE_SIZE
                pq_h = _estimate_pullquote_height(quote, cite, quote_size,
                                                  content_w - 2 * INSET_X)
            pq_h = _clamp_bottom(page_id, f"pullquote-{int(y_cursor)}", y_cursor,
                                 pq_h, report, font_size=quote_size)
            if pq_h is None:
                # 可用空间不足一行：不 emit 裁剪碎片（§七 2.8 d）
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            pq_h = _emit_pullquote(elements, quote, cite, content_x, y_cursor, content_w,
                                   font=deck_font, quote_size=quote_size, max_h=pq_h)
            y_cursor += pq_h + GAP_MD
        elif elem_type == "architecture_4a":
            # 4A 架构图仅 DOCX 有原生渲染，PPTD 端显式降级（§6.1 能力矩阵）
            text = degrade_text(elem_type, normalized, "pptd")
            body_size = _SHRINK_BODY_SIZE if shrink else 14
            h = _estimate_text_height(text, font_size=body_size, line_height=1.65, width=content_w)
            if not shrink and y_cursor + h > _CONTENT_Y_MAX:
                # 底边感知（§七 2.8）：底边预估超线先升 shrink 重排
                shrink = True
                body_size = _SHRINK_BODY_SIZE
                h = _estimate_text_height(text, font_size=body_size, line_height=1.65, width=content_w)
            eid = f"elem-{int(y_cursor)}"
            h = _clamp_bottom(page_id, eid, y_cursor, h, report, font_size=body_size)
            if h is None:
                # 可用空间不足一行：不 emit 裁剪碎片（§七 2.8 d）
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            content = {
                "style": "$bodytext",
                "align": ["left", "top"],
                "text": text + "\n",
            }
            if shrink:
                content["fontSize"] = body_size
            elements.append({
                "elementId": eid,
                "elementType": "text",
                "bounds": [content_x, y_cursor, content_w, h],
                "content": content,
            })
            y_cursor += h + GAP_MD
            report.degrade(page_id, index, elem_type, "pptd", text)
        elif elem_type == "diagram":
            from _renderer.diagram import render_diagram_pptd
            # 数量型容量阈值（间距体系 v1 §六 5）：warning 只进 report 不改产出
            from _renderer.schema import validate_element_warnings
            for _w in validate_element_warnings(elem, index=index):
                report.warn(f"{page_id} {_w}")
            dg_elems, dg_h = render_diagram_pptd(elem, content_x, y_cursor, content_w,
                                                 style=style_name,
                                                 v2_theme=v2_theme_name)
            if dg_elems and y_cursor + dg_h > _CONTENT_Y_MAX:
                # 页底防线（I-16）：diagram 分支此前无 _clamp_bottom/shrink，
                # 超高直接越界。先均匀缩放（s<1，宽高比不变；字号同比缩，
                # 防缩盒后 text 溢出）压回界内；缩到 0.5 仍超则整图 skip
                dg_elems, dg_h = _shrink_diagram_to_fit(
                    dg_elems, dg_h, content_x, y_cursor, content_w,
                    report, page_id, index)
                if dg_elems is None:
                    continue
            elements.extend(dg_elems)
            y_cursor += dg_h + GAP_MD
        elif elem_type == "product_intro_placeholder":
            from _renderer.diagram import render_placeholder_pptd
            ph_elems, ph_h = render_placeholder_pptd(elem, content_x, y_cursor, content_w,
                                                     style=style_name)
            if ph_elems and y_cursor + ph_h > _CONTENT_Y_MAX:
                # 页底防线（与 diagram 分支 I-16 同款）：超高先 _clamp_bottom
                # 裁进 report.warn，可用不足一行整元素 skip（§七 2.8 d）；
                # 占位组是固定造型，均匀缩进裁后高度（宽高比不变防虚线框压字）
                clamped_h = _clamp_bottom(page_id, f"pi{int(y_cursor)}", y_cursor,
                                          ph_h, report, font_size=20)
                if clamped_h is None:
                    report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                    continue
                _scale_group_bounds(ph_elems, clamped_h / ph_h, content_x,
                                    float(y_cursor), scale_font=True)
                ph_h = clamped_h
            elements.extend(ph_elems)
            y_cursor += ph_h + GAP_MD
        elif elem_type in ("hero", "section_tag", "action_title", "stat_cards",
                           "kpi_cards", "pain_cards", "info_cards", "legend_bar",
                           "qa_block", "view_cards", "callout_block",
                           "page_header",
                           # v3.0 版式构件（P12/P14/P15/P16）
                           "toc_cards", "duo_compare", "pros_cons", "cta_block"):
            # v2 页面构件 PPTD 端 RENDER（§5.2/§7）：原生形状映射，零图像化
            from _renderer.diagram.pptd_emit import emit_chrome_pptd
            ch_elems, ch_h = emit_chrome_pptd(elem_type, normalized, content_x,
                                              y_cursor, content_w,
                                              theme_name=v2_theme_name)
            if ch_elems and y_cursor + ch_h > _CONTENT_Y_MAX:
                # 页底防线（与 diagram 分支 I-16 同款）：均匀缩放压回界内
                ch_elems, ch_h = _shrink_diagram_to_fit(
                    ch_elems, ch_h, content_x, y_cursor, content_w,
                    report, page_id, index)
                if ch_elems is None:
                    continue
            # 同页多个同类构件时 elementId 唯一化（pptd check DuplicateIdError）
            uid = f"v2{int(y_cursor)}"
            for el in ch_elems:
                el["elementId"] = f"{uid}-{el['elementId']}"
            elements.extend(ch_elems)
            y_cursor += ch_h + GAP_MD
        elif elem_type == "topnav":
            # PPTD 端 DEGRADE（§5.2）：降级页眉文本 + report.degraded
            text = degrade_text(elem_type, normalized, "pptd")
            body_size = _SHRINK_BODY_SIZE if shrink else 14
            h = _estimate_text_height(text, font_size=body_size, line_height=1.65, width=content_w)
            eid = f"elem-{int(y_cursor)}"
            h = _clamp_bottom(page_id, eid, y_cursor, h, report, font_size=body_size)
            if h is None:
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            elements.append({
                "elementId": eid,
                "elementType": "text",
                "bounds": [content_x, y_cursor, content_w, h],
                "content": {"style": "$bodytext", "align": ["left", "top"],
                            "text": text + "\n"},
            })
            y_cursor += h + GAP_MD
            report.degrade(page_id, index, elem_type, "pptd", text)
        else:
            # 未知 type 不再静默跳过，进渲染报告（§6.3）
            report.skip(page_id, index, elem_type, "PPTD 端不支持")

    # 页级填充（版式改进）：内容底边不足可用区 75% 时纵向放大到 ~88%，
    # 解决"内容挤在页面上部、下半页全空"。footer 之前、内容元素全部 emit 之后
    _fill_content_area(elements)

    # 三件套之 3：页脚（左版权 + 右页码）
    elements.append({
        "elementId": "footer-left",
        "elementType": "text",
        "bounds": [_CONTENT_X, 690, 400, 16],
        "content": {
            "style": "$footer",
            "wrap": False,
            "text": f"© 2026 – {_esc(author or 'Syzygit Technology')}\n",
        },
    })
    elements.append({
        "elementId": "footer-right",
        "elementType": "text",
        "bounds": [_CONTENT_X + _CONTENT_W - 142, 690, 142, 16],
        "content": {
            "style": "$footer",
            "align": ["right", "middle"],
            "wrap": False,
            "text": f"Page - {page_num}\n",
        },
    })

    _snap_page_elements(elements)
    page = {
        "pageType": "content",
        "background": {"type": "solid", "color": "#FFFFFF"},
        "elements": elements,
    }
    return yaml.safe_dump(page, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# 富元素：cards / table / phases / pullquote（P2）
# ---------------------------------------------------------------------------

# 内容区横向边界（版式改进：1280 画布左右各 80 = 6.25% 对称边距，内容居中
# 加宽——原 192/40 不对称边距导致内容整体偏右）。页标题/页脚/内容元素/
# diagram 传入宽度全走这两个常量，封面页是全画布布局不引用
_CONTENT_X = 80
_CONTENT_W = 1120

# cards/phases/pullquote 左侧强调竖条宽（px，照 v3）。竖条是容器 inset 区内
# 的装饰，条内文本框 x 偏移直接取 INSET_X（间距体系 v1：替代原 +22/+18 魔法数）
_BAR_W = 5

# 内容区下限（页脚 y=690，留 16px 间距）——第三级 硬防线（§七 2.5）：
# y 游标超线的元素不再 emit，进 report.skip("页面溢出截断")
_CONTENT_Y_MAX = 674

# 第二级 自动适配触发线（§七 2.5）：y 游标过线后正文类元素缩排。
# 取值 560 ≈ 内容区（130-674 共 544px）八成，给 shrink 档留出一排卡片的
# 收缩余量；基线 9 个溢出页实测见 docs/ 重构记录
_CONTENT_Y_SHRINK = 560

# shrink 档（单档，抄 Beautiful.ai Smart Slides 思路：先缩字号/压行距自适应，
# 仍超高才截断）：正文类 fontSize 14 -> 12，bullets 行距 1.65 -> 1.4
_SHRINK_BODY_SIZE = 12
_SHRINK_BODY_LINE_HEIGHT = 1.4

# pullquote 引文 shrink 档（§七 2.8 底边感知同款：缩字号 2px，18 -> 16；
# 署名 12pt 已到 small 档不再压）
_PULLQUOTE_QUOTE_SIZE = 18
_SHRINK_QUOTE_SIZE = 16

# cards/phases 整组 skip 阈值（§七 2.8 d）：可用高度不足一行卡正文
#（cardbody/desc 13pt × 1.55 行距 ≈ 20.2px）时不发压碎碎片，整组 skip
_CARD_LINE_H = 13 * 1.55

# 页级填充（版式改进：内容自适应填充可用区域）。可用区 = y 130（内容区顶，
# 即 y 游标起点）到页脚 y=690，共 560px
_FILL_Y_ANCHOR = 130.0
_FILL_AVAILABLE = 560.0
# 目标填充率：内容底边达到 130 + 0.88×560 ≈ 623；触发阈值：当前填充 < 75%
# （底边 < 550）。只向上填充、不向下压缩——内容超高仍走 shrink/裁剪防线
_FILL_TARGET_RATIO = 0.88
_FILL_TRIGGER_RATIO = 0.75
# 纵向拉伸倍率上限（视觉抽查口径：4 倍以上卡片过高过空显假）。目标 88%
# 达不到时停在 2 倍，接受留白
_FILL_MAX_SCALE = 2.0
# diagram 组均匀放大倍率上限（防卡通化：形状随盒子变大但字号不变，倍率过
# 大显空）
_FILL_DG_MAX_SCALE = 1.6
# 三件套不参与填充（页眉 logo / 页标题 / 页脚）
_FILL_EXCLUDE_IDS = frozenset({"header-logo", "title", "footer-left", "footer-right"})
# diagram 组 elementId 前缀（render_diagram_pptd 唯一化为 dg{int(y)}-*，同页
# 多图按此前缀分组）
_DG_GROUP_ID_RE = re.compile(r"^(dg\d+)-")


def _fill_content_area(elements):
    """页级填充 pass：内容底边不足可用区 75% 时，纵向放大到底边 ~88%。

    所有内容元素 emit 完成后、页脚追加前调用，就地改写内容元素 bounds
    （排除三件套）：
    - 非 diagram 元素：以 y=130 为锚纵向拉伸（y' = 130+(y-130)×s，h' = h×s），
      x/w 不变，s 上限 _FILL_MAX_SCALE（目标 88% 达不到就停在限速，接受
      留白）。加高盒子/卡片/形状无失真；fontSize 不变（安全阀）——文字
      顶锚不变，文本框变高只是底部留白，无溢出风险。同组元素（cards 一组、
      phases 一组、table、pullquote）相对位置保持：所有元素同锚同倍率，
      组内间距同比放大。
    - diagram 组（dg\\d+- 前缀）：纵向拉伸会压扁圆形/菱形等比例形状
      （ellipse 变椭圆），改做均匀缩放（x/y/w/h 同乘 s_dg，宽高比不变），
      s_dg = min(s, _CONTENT_W/组宽, 1.6)；组顶 y 随 s 重排（保持与上文
      元素的纵向顺序/间距同比），缩放后水平居中于内容区。全宽 diagram
      放大受宽度约束，可能达不到 88% 目标——接受的折中（不压扁形状优先）。
    只向上填充（内容不足才触发）；饱满页（填充 ≥75%）零改动。
    非幂等：限速（_FILL_MAX_SCALE / _FILL_DG_MAX_SCALE）下目标 88% 达不到时
    停在限速，多次调用会在限速内继续逼近目标——当前链路保证每页只调一次
    （_build_content_page 内、页脚追加前），幂等性不影响产出。
    """
    content = [e for e in elements
               if str(e.get("elementId")) not in _FILL_EXCLUDE_IDS
               and not str(e.get("elementId", "")).startswith("ph-")
               and isinstance(e.get("bounds"), list) and len(e["bounds"]) == 4]
    if not content:
        return
    bottom = max(float(e["bounds"][1]) + float(e["bounds"][3]) for e in content)
    content_h = bottom - _FILL_Y_ANCHOR
    if content_h <= 0 or content_h >= _FILL_TRIGGER_RATIO * _FILL_AVAILABLE:
        return
    s = min(_FILL_TARGET_RATIO * _FILL_AVAILABLE / content_h, _FILL_MAX_SCALE)

    dg_groups = {}
    for e in content:
        m = _DG_GROUP_ID_RE.match(str(e.get("elementId", "")))
        if m:
            dg_groups.setdefault(m.group(1), []).append(e)
        else:
            # 纵向拉伸：x/w 原样保留，只改写 y/h
            b = e["bounds"]
            b[1] = _fill_num(_FILL_Y_ANCHOR + (float(b[1]) - _FILL_Y_ANCHOR) * s)
            b[3] = _fill_num(float(b[3]) * s)

    for group in dg_groups.values():
        _fill_diagram_group(group, s)


def _fill_diagram_group(group, page_s):
    """diagram 组填充：组顶 y 随 page_s 同比下移，组内按 s_dg 均匀缩放并水平居中。

    s_dg 受宽度约束（组宽 × s_dg ≤ _CONTENT_W）与 _FILL_DG_MAX_SCALE 上限；
    只放大不缩小（s_dg ≥ 1）。全宽 diagram 独占页时 s_dg=1 且位置不变——
    零改动返回。
    """
    gx0 = min(float(e["bounds"][0]) for e in group)
    gw = max(float(e["bounds"][0]) + float(e["bounds"][2]) for e in group) - gx0
    gy0 = min(float(e["bounds"][1]) for e in group)
    width_cap = (_CONTENT_W / gw) if gw > 0 else page_s
    s = max(1.0, min(page_s, _FILL_DG_MAX_SCALE, width_cap))
    new_gx0 = _CONTENT_X + (_CONTENT_W - gw * s) / 2
    new_gy0 = _FILL_Y_ANCHOR + (gy0 - _FILL_Y_ANCHOR) * page_s
    if s == 1.0 and abs(new_gx0 - gx0) < 0.01 and abs(new_gy0 - gy0) < 0.01:
        return
    _scale_group_bounds(group, s, new_gx0, new_gy0)


def _shrink_diagram_to_fit(dg_elems, dg_h, x, y, total_w, report, page_id, index):
    """I-16：超高 diagram 组均匀缩小压回 _CONTENT_Y_MAX 界内。

    返回 (elems, 新高度)；缩到 0.5 仍超可用高度则整图 skip 进 report
    （复用拆页口径），返回 (None, 0)，调用方不 emit、不推进 y 游标。
    字号随盒子同比缩小（下限 8px）：缩盒不缩字会触发 lint text_overflow。
    缩放后底边恰贴 _CONTENT_Y_MAX（lint 对该线元素豁免 text_overflow，§七 2.8 a）。
    """
    s = (_CONTENT_Y_MAX - y) / dg_h if dg_h > 0 else 1.0
    if s < 0.5:
        report.skip(page_id, index, "diagram",
                    "可用空间不足，diagram 缩至 0.5 仍超高，内容超量请拆页")
        return None, 0
    report.warn(f"{page_id} dg{int(y)}: diagram 均匀缩小 {s:.2f} 防溢出")
    gx0 = min(float(e["bounds"][0]) for e in dg_elems)
    gw = max(float(e["bounds"][0]) + float(e["bounds"][2]) for e in dg_elems) - gx0
    new_gx0 = x + max(0.0, (total_w - gw * s) / 2)  # 缩小后水平居中
    _scale_group_bounds(dg_elems, s, new_gx0, float(y), scale_font=True)
    return dg_elems, dg_h * s


def _scale_group_bounds(group, s, new_gx0, new_gy0, scale_font=False):
    """dg 组均匀缩放：组 bbox 左上对齐到 (new_gx0, new_gy0)，x/y/w/h 同乘 s。

    scale_font=True 时 content.fontSize 同乘 s（下限 8px）——仅 I-16 缩盒
    防溢出用；填充 pass 不动字号（安全阀：文字顶锚不变，只撑盒子）。
    group 元素（elementType=group）的子元素 children 同步缩放，保持
    角标/框体/标题相对关系不变。
    """
    gx0 = min(float(e["bounds"][0]) for e in group)
    gy0 = min(float(e["bounds"][1]) for e in group)
    for e in group:
        _scale_element_bounds(e, s, gx0, gy0, new_gx0, new_gy0, scale_font)


def _scale_element_bounds(e, s, gx0, gy0, new_gx0, new_gy0, scale_font):
    """单元素 bounds 等比缩放，并递归处理 group 的 children。"""
    ex, ey, ew, eh = (float(v) for v in e["bounds"])
    e["bounds"] = [_fill_num(new_gx0 + (ex - gx0) * s),
                   _fill_num(new_gy0 + (ey - gy0) * s),
                   _fill_num(ew * s), _fill_num(eh * s)]
    if scale_font:
        content = e.get("content")
        if isinstance(content, dict) and content.get("fontSize") is not None:
            try:
                content["fontSize"] = max(8, round(float(content["fontSize"]) * s, 1))
            except (TypeError, ValueError):
                pass
    for child in e.get("children") or []:
        _scale_element_bounds(child, s, gx0, gy0, new_gx0, new_gy0, scale_font)


def _fill_num(v):
    """bounds 数值紧凑化：保留 2 位小数，整数值写回 int（yaml 输出整洁）。"""
    r = round(v, 2)
    return int(r) if r == int(r) else r


def _snap_page_elements(elements):
    """页出口坐标吸附（间距体系 v1 §3.3）：整页元素 bounds 统一过 spacing.snap。

    集中在页构建出口做一次（不在各 emit 点散落）。四角吸附（x1/y1/x2/y2 各自
    snap 后反推 w/h）：snap 单调，组内共享边与互不相交关系保持，宽高兜底 1
    （connector 近零厚度 bbox）。吸附前底边恰贴 _CONTENT_Y_MAX 的元素保边不
    吸附——那是溢出防线裁剪产物，lint 对该线豁免 text_overflow（§七 2.8 a），
    防线语义不被网格破坏。
    """
    for e in elements:
        _snap_element(e)


def _snap_element(e):
    """单元素四角吸附 + 递归处理 group 的 children。"""
    b = e.get("bounds")
    if isinstance(b, list) and len(b) == 4:
        try:
            x, y, w, h = (float(v) for v in b)
        except (TypeError, ValueError):
            x = y = w = h = 0.0
        x1, y1 = snap(x), snap(y)
        x2 = snap(x + w)
        if abs(y + h - _CONTENT_Y_MAX) <= 0.01:
            y2 = _CONTENT_Y_MAX  # 防线裁剪线保边（见 docstring）
        else:
            y2 = snap(y + h)
        e["bounds"] = [x1, y1, max(x2 - x1, 1), max(y2 - y1, 1)]
    for child in e.get("children") or []:
        _snap_element(child)


def _clamp_bottom(page_id, element_id, y, h, report, font_size=14):
    """底边兜底（§七 2.8 裁决 a+d 组合）：y+h 超 _CONTENT_Y_MAX 时分三档。

    - 未超线：原样返回 h
    - 可用高度不足一行（< fontSize × 1.3，fontSize 取元素实际生效字号）：
      返回 None——一行都显示不出的裁剪碎片无意义，调用方整元素
      report.skip("可用空间不足一行，内容超量请拆页")。注意 P1-D 语义
      skipped→verify FAIL：页面真实超量时逼用户拆页，是预期不是 bug
    - 其余：裁剪到可用空间 + report.warn（不丢内容，PPT 文本框自然截断；
      lint 对底边贴线元素豁免 text_overflow，见 _layout_lint）
    只有元素起点超线的才整元素 skip（_build_content_page 第三级硬防线）。
    """
    if y + h <= _CONTENT_Y_MAX:
        return h
    available = _CONTENT_Y_MAX - y
    if available < font_size * 1.3:
        return None
    report.warn(f"{page_id} {element_id}: 高度裁切防溢出")
    return max(0.0, available)


def _emit_cards(elements, cards, x, y, total_w, max_h=None, report=None, page_id=None,
                index=None):
    """cards：每卡 roundRect + 5px 竖条 + 标题 + body，横排均分。

    版式照 v3（07_p06_l1.page card-1/card-2）：
    - roundRect adjustments [8000] fill $card
    - 左侧 5px rect fill $primary（y 偏移 +18，高度 -36）
    - 标题 $cardtitle + <strong>
    - body $cardbody
    n 卡横排均分 total_w，卡间距 GAP_LG(24，间距令牌 §3.1)。
    elementId 带 y 坐标前缀（card-{int(y)}-{i}，§七 2.4，同 diagram 的
    dg{y}- 方案），保证同页多组 cards 不撞 ID。
    max_h 非空时整组高度裁到 max_h + report.warn（底边防线 §七 2.8）；
    max_h 不足一行卡正文（_CARD_LINE_H）时不 emit 压碎碎片，整组
    report.skip 并返回 (0, 0)（§七 2.8 d，同 text 类口径）。
    返回 (总高度, 卡数)。高度估算：标题 24 + body 4 行 ≈ 96 + padding。
    """
    uid = int(y)
    n = len(cards)
    if n == 0:
        return 0, 0
    gap = GAP_LG
    card_w = (total_w - gap * (n - 1)) / n
    # 文本框内边距折算（间距体系 v1 一层：方言无 insets 字段，折算进 bounds）：
    # x = 卡边 + INSET_X，宽 = 卡宽 - 2×INSET_X（替代 +22/-40 魔法数；
    # 竖条是 inset 区内的装饰，不再计入偏移）
    text_x_off = INSET_X
    text_w = max(card_w - 2 * INSET_X, 1)
    # 估算高度：标题 + body 行数
    max_body_h = 0
    for c in cards:
        body = str(c.get("body", ""))
        bh = _estimate_text_height(body, font_size=13, line_height=1.55, width=text_w)
        max_body_h = max(max_body_h, bh)
    card_h = 24 + 12 + max_body_h + 16  # padding-top + 标题 + 间距 + body + padding-bottom
    card_h = max(card_h, 100)  # 最小高度
    if max_h is not None and card_h > max_h:
        if max_h < _CARD_LINE_H:
            # 可用空间不足一行：不 emit 压碎碎片，整组 skip（§七 2.8 d）
            if report is not None:
                report.skip(page_id, index, "cards", "可用空间不足一行，内容超量请拆页")
            return 0, 0
        card_h = max(max_h, 0.0)
        if report is not None:
            report.warn(f"{page_id} card-{uid}: 高度裁切防溢出")

    for i, card in enumerate(cards):
        cx = x + i * (card_w + gap)
        title = str(card.get("title", ""))
        body = str(card.get("body", ""))
        elements.append({
            "elementId": f"card-{uid}-{i + 1}",
            "elementType": "shape",
            "bounds": [cx, y, card_w, card_h],
            "shapeName": "roundRect",
            "adjustments": [8000],
            "fill": {"type": "solid", "color": "$card"},
        })
        # 左侧竖条（y 偏移 +18，高度 -36，照 v3）
        bar_y = y + 18
        bar_h = max(card_h - 36, 8)
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-bar",
            "elementType": "shape",
            "bounds": [cx, bar_y, _BAR_W, bar_h],
            "shapeName": "rect",
            "fill": {"type": "solid", "color": "$primary"},
        })
        # 标题
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-title",
            "elementType": "text",
            "bounds": [cx + text_x_off, y + 10, text_w, 24],
            "content": {
                "style": "$cardtitle",
                "align": ["left", "middle"],
                "wrap": False,
                "text": f"<p><strong>{_esc(title)}</strong></p>\n",
            },
        })
        # body
        body_h = max(card_h - 24 - 16, 8)
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-body",
            "elementType": "text",
            "bounds": [cx + text_x_off, y + 38, text_w, body_h],
            "content": {
                "style": "$cardbody",
                "align": ["left", "top"],
                "text": _esc(body.rstrip("\n")) + "\n",
            },
        })
    return card_h, n


def _emit_table(elements, headers, rows, x, y, total_w):
    """table：整体 bounds + 均分 columnWidths/行高 hug rowHeights + {content:} + style "$default"。

    方言陷阱 5：单元格 {content: {text: ...}} 对象，禁裸字符串。
    方言陷阱 6：style "$default" 引用主题 tableStyles.default。
    首行表头：headerFill 由主题样式负责（headerBold/headerColor），单元格只写 text。
    其余行首列：加 <strong> + color $navy（照 v3 07_p06_l1.page dims-table）。
    行高走 table_hug_geometry（间距体系 v1 §五）：短内容与旧均分公式一致，
    长文本单元格撑高所在行。
    返回表总高度。
    """
    n_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if n_cols == 0:
        return 0
    len(rows) + (1 if headers else 0)

    # 均分列宽比例（和为 1）
    col_w = 1.0 / n_cols
    column_widths = [col_w] * n_cols

    # 行高 hug（间距体系 v1 §五，与 6 个 diagram 表格 subtype 同口径）：
    # 行高 = 行内单元格最大行数 × 行距 + 2×INSET_Y，下限原写死公式
    #（n×36 + 表头 0.1/其余均分；短内容与原输出逐字节一致，长文本单元格
    # 撑高不再静默裁剪）。撑高超页不在此截断，走调用方页底防线
    #（_clamp_bottom 裁切 + warn / 不足一行 skip）。
    from _renderer.diagram.pptd_emit import table_hug_geometry
    plain_rows = []
    if headers:
        plain_rows.append([str(h) for h in headers])
    for row in rows:
        plain_rows.append([str(c) for c in row])
    table_h, row_heights = table_hug_geometry(plain_rows, column_widths, total_w, 36, 0.1)

    # 构造 rows（方言陷阱 5：{content: {text: ...}}）
    emit_rows = []
    if headers:
        header_row = [{"content": {"text": _esc(str(h))}} for h in headers]
        emit_rows.append(header_row)
    for row in rows:
        cells = []
        for j, cell in enumerate(row):
            text = str(cell)
            if j == 0 and headers:
                # 首列加粗变色（照 v3）
                cells.append({
                    "content": {
                        "color": "$navy",
                        "text": f"<p><strong>{_esc(text)}</strong></p>\n",
                    }
                })
            else:
                cells.append({
                    "content": {
                        "align": ["left", "middle"],
                        "text": _esc(text),
                    }
                })
        emit_rows.append(cells)

    elements.append({
        "elementId": f"table-{int(y)}",
        "elementType": "table",
        "bounds": [x, y, total_w, table_h],
        "columnWidths": column_widths,
        "rowHeights": row_heights,
        "style": "$default",
        "rows": emit_rows,
    })
    return table_h


def _emit_phases(elements, phases, x, y, total_w, max_h=None, report=None, page_id=None,
                 index=None):
    """phases：每阶段 Shape + name(<strong>) + desc 横排（同 cards 布局）。

    spec 字段：phases[].name / phases[].desc（v3 实例确认，非 label/goal）。
    简化横排版（开发计划 §5 口径），v3 纵向时间轴是特殊页做法，归分页代理。
    elementId 带 y 坐标前缀（phase-{int(y)}-{i}，§七 2.4，同 cards）。
    高度自适应（§七 2.8，替代原固定 110——7 列窄卡时 desc 放不下，lint 实测
    溢出）：name 区 24 + desc 按文本框宽（卡宽 - 2×INSET_X，间距体系 v1
    内边距折算）用 est_text_w 估行数 × 行高（13px × 1.55，cardbody 样式）
    + padding，min 110。
    max_h 非空时整组高度裁到 max_h + report.warn（底边防线 §七 2.8）；
    max_h 不足一行 desc（_CARD_LINE_H）时不 emit 压碎碎片，整组
    report.skip 并返回 0（§七 2.8 d，同 text 类口径）。
    返回总高度。
    """
    n = len(phases)
    if n == 0:
        return 0
    uid = int(y)
    gap = GAP_LG
    phase_w = (total_w - gap * (n - 1)) / n
    from _renderer.diagram.pptd_emit import est_text_w  # 全角/半角区分，比全按全角准
    # 文本框内边距折算（同 cards）：x = 卡边 + INSET_X，宽 = 卡宽 - 2×INSET_X
    text_x_off = INSET_X
    desc_w = max(phase_w - 2 * INSET_X, 1)
    max_desc_h = 0.0
    for phase in phases:
        desc = str(phase.get("desc", ""))
        if not desc:
            continue
        lines = max(1, int(-(-est_text_w(desc, 13) // desc_w)))
        max_desc_h = max(max_desc_h, lines * 13 * 1.55)
    # padding-top + name + 间距 + desc + padding-bottom（公式同 cards），min 110
    phase_h = max(24 + 12 + max_desc_h + 16, 110)
    if max_h is not None and phase_h > max_h:
        if max_h < _CARD_LINE_H:
            # 可用空间不足一行：不 emit 压碎碎片，整组 skip（§七 2.8 d）
            if report is not None:
                report.skip(page_id, index, "phases", "可用空间不足一行，内容超量请拆页")
            return 0
        phase_h = max(max_h, 0.0)
        if report is not None:
            report.warn(f"{page_id} phase-{uid}: 高度裁切防溢出")

    for i, phase in enumerate(phases):
        px = x + i * (phase_w + gap)
        name = str(phase.get("name", ""))
        desc = str(phase.get("desc", ""))
        # 卡片底
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}",
            "elementType": "shape",
            "bounds": [px, y, phase_w, phase_h],
            "shapeName": "roundRect",
            "adjustments": [8000],
            "fill": {"type": "solid", "color": "$card"},
        })
        # 左侧竖条
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-bar",
            "elementType": "shape",
            "bounds": [px, y + 18, _BAR_W, max(phase_h - 36, 8)],
            "shapeName": "rect",
            "fill": {"type": "solid", "color": "$primary"},
        })
        # name（accent 色 <strong>）
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-name",
            "elementType": "text",
            "bounds": [px + text_x_off, y + 10, desc_w, 24],
            "content": {
                "style": "$cardtitle",
                "align": ["left", "middle"],
                "wrap": False,
                "text": f"<p><strong>{_esc(name)}</strong></p>\n",
            },
        })
        # desc
        desc_h = max(phase_h - 24 - 16, 8)
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-desc",
            "elementType": "text",
            "bounds": [px + text_x_off, y + 38, desc_w, desc_h],
            "content": {
                "style": "$cardbody",
                "align": ["left", "top"],
                "text": _esc(desc.rstrip("\n")) + "\n",
            },
        })
    return phase_h


def _estimate_pullquote_height(quote, cite, quote_size, text_w):
    """pullquote 总高估算（与 _emit_pullquote 版式公式同口径）：
    引文 quote_size pt × 1.4 行距 × 行数 + 署名 20 + padding 16。"""
    quote_h = _estimate_text_height(quote, font_size=quote_size, line_height=1.4,
                                    width=text_w)
    return quote_h + (20 if cite else 0) + 16


def _emit_pullquote(elements, quote, cite, x, y, total_w, font=DEFAULT_FONT,
                    quote_size=_PULLQUOTE_QUOTE_SIZE, max_h=None, report=None,
                    page_id=None):
    """pullquote：左侧 5px $primary 竖条 + 引文 18pt $navy + 署名 12pt $gray。

    版式照 v3 DESIGN_GUIDE「内嵌版」。font 默认 DEFAULT_FONT（调用方传
    甲板统一字体 _deck_font）。文本框 x = 左缘 + INSET_X、宽 = 总宽 - 2×INSET_X
    （间距体系 v1 内边距折算，替代 +18/-30 魔法数；竖条是 inset 区内装饰）。
    elementId 带 y 坐标前缀（pullquote-{int(y)}-*，同 cards 口径）。
    quote_size：引文字号（shrink 档 16，§七 2.8 底边感知升档）。max_h 非空且
    总高超限时整组裁到 max_h + report.warn：引文框吸收裁切量（PPT 文本框
    自然截断不丢内容）、署名沉底保持界内；署名连一行引文都放不下时只发
    引文（框撑满整组）。裁切后竖条底边贴防线裁剪线，lint 对组内文本框
    豁免 text_overflow（同组容器贴线，§七 2.8 a）。
    返回总高度。
    """
    uid = int(y)
    text_x = x + INSET_X
    text_w = total_w - 2 * INSET_X
    # 引文高度估算：quote_size pt × 行数
    quote_h = _estimate_text_height(quote, font_size=quote_size, line_height=1.4,
                                    width=text_w)
    cite_h = 20 if cite else 0
    total_h = quote_h + cite_h + 16
    if max_h is not None and total_h > max_h:
        # 底边防线（§七 2.8）：整组裁到 max_h；裁切 warn 由调用方
        # _clamp_bottom 记录（直调本函数时才在此 warn）
        total_h = max(max_h, 0.0)
        if cite_h and total_h - cite_h - 16 < quote_size * 1.4:
            cite_h = 0  # 署名随裁切舍弃，整组空间留给引文（至少保住一行）
            quote_h = total_h
        else:
            quote_h = total_h - cite_h - 16
        if report is not None:
            report.warn(f"{page_id} pullquote-{uid}: 高度裁切防溢出")

    # 左侧竖条
    elements.append({
        "elementId": f"pullquote-{uid}-bar",
        "elementType": "shape",
        "bounds": [x, y, _BAR_W, total_h],
        "shapeName": "rect",
        "fill": {"type": "solid", "color": "$primary"},
    })
    # 引文
    elements.append({
        "elementId": f"pullquote-{uid}-text",
        "elementType": "text",
        "bounds": [text_x, y, text_w, quote_h],
        "content": {
            "fontSize": quote_size,
            "color": "$navy",
            "fontFamily": font,
            "lineHeight": 1.4,
            "align": ["left", "top"],
            "text": _esc(quote.rstrip("\n")) + "\n",
        },
    })
    # 署名
    if cite_h:
        elements.append({
            "elementId": f"pullquote-{uid}-cite",
            "elementType": "text",
            "bounds": [text_x, y + quote_h + 8, text_w, cite_h],
            "content": {
                "fontSize": 12,
                "color": "$gray",
                "fontFamily": font,
                "align": ["left", "middle"],
                "wrap": False,
                "text": _esc(cite) + "\n",
            },
        })
    return total_h

def _resolve_logo(spec, spec_dir, logo_path, client_name=None):
    """logo 解析顺序（PRD Q6）：
    1. --logo 显式
    2. spec.document.cover.logo_image
    3. _knowledge/clients/{client}/refs/ 文件名含 logo 的图片
    4. output/{client}/*/media/ 文件名含 logo 的图片
    5. 跳过（返回 (None, None)，DESIGN_GUIDE 注明待补）

    返回 (源绝对路径, media 内文件名)。
    """
    # 1. 显式 --logo
    if logo_path and os.path.exists(logo_path):
        return os.path.abspath(logo_path), os.path.basename(logo_path)
    # 2. spec.document.cover.logo_image
    cover_logo = spec.get("document", {}).get("cover", {}).get("logo_image")
    if cover_logo:
        resolved = _resolve_relative_or_abs(cover_logo, spec_dir)
        if resolved and os.path.exists(resolved):
            return resolved, os.path.basename(resolved)
    # 3. refs/ 探测
    if client_name:
        found = _probe_logo_in_dir(os.path.join("_knowledge", "clients", client_name, "refs"))
        if found:
            return found
        # 4. output media/ 探测
        found = _probe_logo_in_output_media(client_name)
        if found:
            return found
    return None, None


def _probe_logo_in_dir(dir_path):
    """在目录下找文件名含 logo 的图片（png/jpg/jpeg/svg），返回 (abs_path, basename) 或 None。"""
    if not os.path.isdir(dir_path):
        return None
    logo_exts = (".png", ".jpg", ".jpeg", ".svg")
    for root, _, files in os.walk(dir_path):
        for fname in files:
            low = fname.lower()
            if "logo" in low and low.endswith(logo_exts):
                abs_p = os.path.abspath(os.path.join(root, fname))
                return abs_p, fname
    return None


def _probe_logo_in_output_media(client_name):
    """在 output/{client}/*/media/ 下找文件名含 logo 的图片。"""
    client_output = os.path.join("output", client_name)
    if not os.path.isdir(client_output):
        return None
    for entry in os.listdir(client_output):
        media_dir = os.path.join(client_output, entry, "media")
        found = _probe_logo_in_dir(media_dir)
        if found:
            return found
    return None


def _resolve_background_image(spec, spec_dir):
    """cover 背景图：spec.document.cover.background_image。没有返回 (None, None)。"""
    bg = spec.get("document", {}).get("cover", {}).get("background_image")
    if bg:
        resolved = _resolve_relative_or_abs(bg, spec_dir)
        if resolved and os.path.exists(resolved):
            return resolved, os.path.basename(resolved)
    return None, None


def _resolve_relative_or_abs(path, base_dir):
    """路径可能是绝对、相对 spec_dir、或相对 cwd；统一返回绝对路径。"""
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(base_dir, path))


def _media_abs_path(out_dir, media_name):
    """工程内 media 文件未来落盘后的绝对路径（方言陷阱 4）。"""
    return os.path.abspath(os.path.join(out_dir, "media", media_name))


# ---------------------------------------------------------------------------
# DESIGN_GUIDE.md 模板（P3）
# ---------------------------------------------------------------------------

def _build_design_guide(spec, theme, logo_abs, bg_abs, client_name, name, out_dir):
    """参数化 DESIGN_GUIDE.md（母版照 v3，参数换为客户/主题/logo/bg）。

    方言权威 pptd.md 路径失效，改为"方言规则见主 pptd + 本 GUIDE 六陷阱"。
    无 logo 时注明"待补 logo"。
    """
    colors = theme["colors"]
    primary = colors["primary"]
    navy = colors["navy"]
    deck_font = _deck_font(theme)
    doc = spec.get("document", {})
    title = doc.get("title", "")
    author = spec.get("author", client_name or "（待填客户名）")
    logo_note = logo_abs if logo_abs else "（待补 logo，页眉/封面 logo 元素未生成）"
    bg_note = bg_abs if bg_abs else "（待补封面背景图，cover 用纯色底）"

    return f"""# {title} - PPT 设计规范（子代理必读 · 执行口径）

> 由 pptd-gen 自动生成（{name}.pptd 配套）。母版照 v3 工程参数化。
> 写页面之前先读：
> 1. 方言六陷阱（见下，源 v3 实战 + 主 pptd 主题）
> 2. 内容源 spec.yml（L3 铁律：文案逐字取自 spec，只可视觉重排）
> 3. 示范页：pages/01_cover.page（封面）、pages/02_p01_*.page（标准内容页）
> 项目根：{out_dir}

## 方言六陷阱（踩过坑，务必遵守）

1. **主 pptd 顶层无 version 字段**。
2. **粗体只用行内 `<strong>`**；textStyles 无 bold 属性，写了不生效。
3. **斜体用 `<em>`**；中文斜体观感差，优先用粗细和颜色对比。
4. **图片 src 只认绝对路径**。media/ 素材引用写 `os.path.abspath`。
5. **表格单元格是 `{{content: {{...}}}}` 对象**，不是裸字符串。
6. **表格样式走 `headerFill` 系列 + `style: "$default"` 引用**。

另：**禁用 Icon 元素**（FA 图标 convert 时退化，v3 踩坑）。需要图形一律 Shape + Text。

## 主题与色板（来自主 pptd）

- 主色 primary：`{primary}`
- 深海军蓝 navy：`{navy}`
- 文字阶梯：ink `{colors["ink"]}` -> body `{colors["body"]}` -> lead `{colors["lead"]}` -> gray `{colors["gray"]}`
- 卡片底 card `{colors["card"]}`、浅蓝 chip `{colors["chip"]}`、分隔线 hairline `{colors["hairline"]}`
- 字体统一 {deck_font}（pagetitle 32 / lead 16 / bodytext 14 / small 12 / footer 11）
- 表格样式：headerFill `$navy` + headerColor 白 + headerBold true

## 画布与公共版式（1280×720）

- 内容页固定三件套（pptd-gen 已生成，仅改页码与标题；bounds 已按 4px 网格吸附）：
  - 页眉 logo：`bounds: [24, 28, 48, 40]`，`fit: {{mode: contain}}`
  - 页标题：`bounds: [80, 56, 1120, 44]`，`style: "$pagetitle"`，`wrap: false`，整体 `<strong>` 包裹
  - 页脚左：`bounds: [80, 688, 400, 16]`，`style: "$footer"`，`© 2026 – {author}`
  - 页脚右：`bounds: [1056, 688, 144, 16]`，`style: "$footer"`，`Page - N`
- 正文区：x 80–1200（宽 1120，左右各 80 对称边距），y 130–674
- 卡片：roundRect `adjustments: [8000]` fill `$card` + 左侧 5px `$primary` 竖条 + `$cardtitle`+`<strong>` + `$cardbody`
- pullquote：左侧 5px `$primary` 竖条 + 引文 18pt `$navy` + 署名 12pt `$gray`

## 媒体清单

- logo：{logo_note}
- 封面背景：{bg_note}

## 自检流程

1. 改完负责的 .page 文件后，复制主 pptd 为 `_check_批次.pptd`，pages 列表改成你的批次。
2. 跑 `python _cli.py pptd-build _check_批次.pptd --check-only --client {client_name or "客户名"}`。
3. 修到 0 errors, 0 warnings（TextOverflow/TextUnderfill/TextOcclusion 全修）。
4. 不要跑 convert（统一由 pptd-build 主流程做）。
5. 汇报：每页一行版式说明 + check 最终 Summary。
"""


# ---------------------------------------------------------------------------
# y 游标估算
# ---------------------------------------------------------------------------

def _estimate_text_height(text, font_size=14, line_height=1.65, width=_CONTENT_W):
    """估算文本块高度（px）。中文为主：字宽≈fontSize。

    按实际换行 + 按宽度估算每段行数。估算偏大不致命，分页代理会调。
    """
    if not text:
        return font_size * line_height
    chars_per_line = max(1, int(width / font_size))
    lines = 0
    for seg in str(text).split("\n"):
        seg = seg.rstrip()
        if not seg:
            lines += 1
            continue
        # 去 HTML 标签后算字数
        plain = re.sub(r"<[^>]+>", "", seg)
        seg_lines = max(1, (len(plain) + chars_per_line - 1) // chars_per_line)
        lines += seg_lines
    return max(font_size * line_height, lines * font_size * line_height)


def _estimate_bullets_height(items, font_size=14, line_height=1.65, width=_CONTENT_W):
    """bullets 高度：每条按 text 估算 + 条间距。"""
    if not items:
        return font_size * line_height
    total = 0
    for it in items:
        total += _estimate_text_height(str(it), font_size, line_height, width)
        total += font_size * 0.5  # 段间距
    return total


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _opacity_to_hex(opacity):
    """不透明度 0.0-1.0 -> 两位十六进制（00-FF）。0.8 -> 'CC'。"""
    v = max(0, min(1, float(opacity)))
    return f"{int(round(v * 255)):02X}"


def _page_slug(page_spec, idx):
    """从 page.id 推 slug；没 id 用 p{NN}。连字符转下划线。"""
    pid = page_spec.get("id") or f"p{idx + 1:02d}"
    return pid.replace("-", "_")


def _slugify_name(name):
    """项目名清洗：保留中文/字母/数字/下划线，其余转下划线。"""
    if not name:
        return "deck"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name, flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    return cleaned or "deck"
