# -*- coding: utf-8 -*-
"""spec -> pptd 工程生成器（L3 确定性生成，无 LLM 调用）。

从已确认的 spec.yml 机械生成 pptd 工程骨架（主 pptd + pages/*.page +
media/ + DESIGN_GUIDE.md），让分页代理只做内容润色。

设计依据：docs/dev_plan_pptd_spec_gen_2026-07-18.md
方言母版：output/蓝海/蓝海_七层架构高管宣讲_v3/（v3 工程实例）
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
import shutil

import yaml

from _renderer.elements import RenderReport, _esc, degrade_text, empty_payload_reason, is_empty_payload, normalize_element
from _renderer.spacing import GAP_MD, INSET_X
from _renderer.theme import DEFAULT_FONT, DEFAULT_VEIL, WHITE, resolve_theme, style_name_for_entry


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
            v2_theme_name=v2_theme_name, spec=spec, spec_dir=spec_dir)
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

    色板 12 槽消费样式单一源 resolve_theme(...).pptd_colors（§七 2.1/2.2，
    含 R-3 阴影槽 shadow）：
    enterprise 锚定 DEFAULT_PPTD_SLOTS（基线零 diff），其余风格从 5 基色
    派生。style 是 theme 名字符串（可含旧 style 名，经 normalize 映射）。
    textStyles 七套（pagetitle/lead/
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
            "headerColor": WHITE,
            "headerBold": True,
            "bodyColor": "$body",
            "border": [None, None, {"style": "solid", "width": 0.75, "color": "$hairline"}, None],
        }
    }
    return {"colors": colors, "textStyles": text_styles, "tableStyles": table_styles}



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

    veil = cover_cfg.get("veil", DEFAULT_VEIL)
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
            "color": WHITE,
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
                "color": f"{WHITE}D9",
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
                "color": f"{WHITE}A6",
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
                "color": f"{WHITE}CC",
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
                        style_name=None, v2_theme_name=None, spec=None, spec_dir=None):
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
                           "toc_cards", "duo_compare", "pros_cons", "cta_block",
                           # Step 5 新增元素
                           "ui_mock", "conclusion_band",
                           # S8 Wave B（C-E2 三件套）
                           "sla_block", "profile_card", "logo_wall"):
            # v2 页面构件 PPTD 端 RENDER（§5.2/§7）：原生形状映射，零图像化
            # 含图构件（logo/头像）先预解析资产路径（同 screenshot 链路，
            # chrome emit 无 spec_dir 上下文），缺失置空走文字牌兜底
            if elem_type == "logo_wall":
                _asset_field, _asset_key = "logos", "src"
            elif elem_type == "profile_card":
                _asset_field, _asset_key = "profiles", "photo"
            else:
                _asset_field = None
            if _asset_field:
                for _it in normalized.get(_asset_field) or []:
                    _src = _it.get(_asset_key)
                    if not _src:
                        continue
                    _resolved = _resolve_screenshot_path(
                        _src, spec_dir, spec.get("client_name"))
                    if _resolved:
                        _it[_asset_key] = _resolved
                    else:
                        _it[_asset_key] = ""
                        report.warn(f"{page_id} {elem_type}: 图片缺失 "
                                    f"({_src})，PPTD 降级为文字兜底")
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
        elif elem_type == "screenshot":
            # PPTD 端 RENDER：图片 + 原生形状标注层
            src_path = _resolve_screenshot_path(
                normalized["src"], spec_dir, spec.get("client_name"))
            if not src_path or not os.path.exists(src_path):
                text = degrade_text(elem_type, normalized, "pptd")
                report.warn(f"{page_id} screenshot: 图片缺失，PPTD 降级为文本")
                _emit_degrade_text(elements, content_x, y_cursor, content_w,
                                   text, report, page_id, index, "pptd",
                                   shrink=shrink, deck_font=deck_font)
                continue
            ss_w = int(content_w * normalized["width"])
            ss_h = 360  # 默认高度；无 PIL 时不读取真实宽高
            caption = normalized["caption"]
            caption_h = 0
            if caption:
                caption_h = 24
            total_h = ss_h + caption_h + (10 if normalized["annotations"] else 0)
            eid = f"ss-{int(y_cursor)}"
            clamped_h = _clamp_bottom(page_id, eid, y_cursor, total_h, report, font_size=14)
            if clamped_h is None:
                report.skip(page_id, index, elem_type, "可用空间不足一行，内容超量请拆页")
                continue
            img_h = min(ss_h, clamped_h - caption_h)
            elements.append({
                "elementId": eid,
                "elementType": "image",
                "bounds": [content_x, y_cursor, ss_w, img_h],
                "src": src_path,
                "fit": {"mode": "contain"},
            })
            # 标注层：按图片内相对坐标映射到当前 bounds
            scale = img_h / 360 if ss_h else 1.0
            for ai, ann in enumerate(normalized["annotations"]):
                ax = content_x + int(ann["x"] * (ss_w / 720) * scale)
                ay = y_cursor + int(ann["y"] * scale)
                elements.append({
                    "elementId": f"{eid}-ann-{ai}",
                    "elementType": "shape",
                    "bounds": [ax, ay, 8, 8],
                    "shapeName": "oval",
                    "fill": {"type": "solid", "color": "$primary"},
                })
                elements.append({
                    "elementId": f"{eid}-ann-{ai}-text",
                    "elementType": "text",
                    "bounds": [ax + 10, ay, 200, 18],
                    "content": {
                        "fontSize": 11,
                        "color": "$ink",
                        "fontFamily": deck_font,
                        "align": ["left", "middle"],
                        "wrap": False,
                        "text": _esc(ann["text"]) + "\n",
                    },
                })
            if caption and img_h == ss_h:
                elements.append({
                    "elementId": f"{eid}-caption",
                    "elementType": "text",
                    "bounds": [content_x, y_cursor + img_h + 6, ss_w, caption_h],
                    "content": {
                        "style": "$small",
                        "align": ["center", "middle"],
                        "wrap": False,
                        "text": _esc(caption) + "\n",
                    },
                })
            y_cursor += min(total_h, clamped_h) + GAP_MD
        elif elem_type == "raw_html":
            # PPTD 端显式不支持：降级文本明示
            text = degrade_text(elem_type, normalized, "pptd")
            deg_h = _emit_degrade_text(elements, content_x, y_cursor, content_w,
                                       text, report, page_id, index, "pptd",
                                       shrink=shrink, deck_font=deck_font)
            if deg_h:
                y_cursor += deg_h + GAP_MD
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
        # 页面底色走主题 card 槽（S2 清尾：各主题现值均 #FFFFFF，零视觉变化）
        "background": {"type": "solid", "color": theme["colors"]["card"]},
        "elements": elements,
    }
    return yaml.safe_dump(page, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# 富元素：cards / table / phases / pullquote（P2）
# ---------------------------------------------------------------------------

# 内容区横向边界（版式改进：1280 画布左右各 80 = 6.25% 对称边距，内容居中
# 加宽——原 192/40 不对称边距导致内容整体偏右）。页标题/页脚/内容元素/
# diagram 传入宽度全走这两个常量，封面页是全画布布局不引用



# === T9 拆分：部件/资源子模块 re-import（保持模块级名字可用）===
from _pptd_parts import (
    _deck_font, _CONTENT_W, _CONTENT_X, _CONTENT_Y_MAX, _CONTENT_Y_SHRINK,
    _SHRINK_BODY_SIZE, _SHRINK_BODY_LINE_HEIGHT, _PULLQUOTE_QUOTE_SIZE,
    _SHRINK_QUOTE_SIZE, _fill_content_area, _shrink_diagram_to_fit,
    _scale_group_bounds, _snap_page_elements, _clamp_bottom, _emit_cards,
    _emit_table, _emit_phases, _estimate_pullquote_height, _emit_pullquote,
    _resolve_logo, _resolve_background_image, _resolve_screenshot_path,
    _media_abs_path, _emit_degrade_text,
    _build_design_guide, _estimate_text_height, _estimate_bullets_height,
    _opacity_to_hex, _page_slug, _slugify_name,  # noqa: F401
    _probe_logo_in_dir, _probe_logo_in_output_media,  # noqa: F401
)
