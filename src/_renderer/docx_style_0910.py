# -*- coding: utf-8 -*-
"""把 docx 的样式定义照抄 0910《信息化系统建设规划方案》的实测规格。

纯 python-docx 实现，**不依赖 Word COM**（沙箱内 COM 不可靠），且**只改格式层**：
样式定义（Normal / Heading 1-5 / Title / Subtitle）+ 两类段落级格式化（图题段、
表格单元格段、文档副标题段）。全程不写 ``w:t``，因此段落文字一字不动。

0910 实测规格（源：``refs/信息化系统建设规划方案_0910.docx`` 的 word/styles.xml）：

====================  ==========================================================
正文 Normal           仿宋_GB2312 三号(16pt)／行距固定 25pt／首行缩进 2 字符／两端对齐
标题 1                黑体 二号(22pt) 加粗／行距 1.5 倍
标题 2                楷体_GB2312 三号(16pt) 不加粗／无缩进
标题 3、4             仿宋_GB2312 四号(14pt) 加粗／无缩进
标题 5                仿宋_GB2312 三号(16pt) 加粗
图题                  黑体 五号(10.5pt) 居中／行距固定 25pt
表格文字              仿宋_GB2312 小四(12pt)／单倍行距／无缩进
====================  ==========================================================
"""

import os
import re
import zipfile

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

STYLE_SET = "gs0910"

#: 多级自动编号（对标 0910：标题样式挂 numPr，正文标题里不写节号）
NUM_ABSTRACT_ID = 90
NUM_ID = 90
NUM_START_L1 = 2          # 本包是 0910 的片段，章级从 2 起（010 的 2/3/4 章）
NUM_LEVELS = 5

#: CT_PPr 中必须排在 numPr 之后的元素（插入位点判定用）
_AFTER_NUMPR_TAGS = (
    "<w:suppressLineNumbers", "<w:pBdr", "<w:shd", "<w:tabs",
    "<w:suppressAutoHyphens", "<w:kinsoku", "<w:wordWrap", "<w:overflowPunct",
    "<w:topLinePunct", "<w:autoSpaceDE", "<w:autoSpaceDN", "<w:bidi",
    "<w:adjustRightInd", "<w:snapToGrid", "<w:spacing", "<w:ind",
    "<w:contextualSpacing", "<w:mirrorIndents", "<w:suppressOverlap", "<w:jc",
    "<w:textDirection", "<w:textAlignment", "<w:textboxTightWrap",
    "<w:outlineLvl", "<w:divId", "<w:cnfStyle", "<w:rPr", "<w:sectPr",
)

#: 图题识别：0910 的图题形如「图39 电子会计档案系统架构图」「图：52 办公系统架构图」
CAPTION_RE = re.compile(r"^图\s*[:：]?\s*\d+")
#: 表格/图题专用样式名（沿 0910 的叫法）
TABLE_STYLE_NAME = "表格正文"
CAPTION_STYLE_NAME = "图题"

_ALIGN = {
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "left": WD_ALIGN_PARAGRAPH.LEFT,
}

#: 规格表：字号单位 pt，line_pt 为「固定值行距」，line_ratio 为倍数行距
PROFILE = {
    "normal": {
        "east": "仿宋_GB2312", "ascii": "仿宋_GB2312", "size": 16.0,
        "line_pt": 25.0, "first_line_pt": 32.0, "align": "justify",
        "space_before": 0.0, "space_after": 0.0,
    },
    "title": {
        "east": "黑体", "ascii": "Calibri", "size": 22.0, "bold": True,
        "align": "center", "space_before": 0.0, "space_after": 12.0,
    },
    "subtitle": {
        "east": "楷体_GB2312", "ascii": "仿宋_GB2312", "size": 16.0,
        "bold": False, "align": "center", "indent0": True,
    },
    "h1": {
        "east": "黑体", "ascii": "Calibri", "size": 22.0, "bold": True,
        "line_ratio": 1.5, "indent0": True, "keep_next": True,
        "space_before": 12.0, "space_after": 12.0,
    },
    "h2": {
        "east": "楷体_GB2312", "ascii": "仿宋_GB2312", "size": 16.0,
        "bold": False, "indent0": True, "keep_next": True,
        "space_before": 6.0, "space_after": 6.0,
    },
    "h3": {
        "east": "仿宋_GB2312", "ascii": "仿宋_GB2312", "size": 14.0,
        "bold": True, "indent0": True, "keep_next": True,
        "space_before": 6.0, "space_after": 3.0,
    },
    "h4": {
        "east": "仿宋_GB2312", "ascii": "仿宋_GB2312", "size": 14.0,
        "bold": True, "indent0": True, "keep_next": True,
        "space_before": 3.0, "space_after": 0.0,
    },
    "h5": {
        "east": "仿宋_GB2312", "ascii": "仿宋_GB2312", "size": 16.0,
        "bold": True, "indent0": True, "keep_next": True,
        "space_before": 0.0, "space_after": 0.0,
    },
    "caption": {
        "east": "黑体", "ascii": "Consolas", "size": 10.5, "bold": False,
        "align": "center", "line_pt": 25.0, "indent0": True,
        "space_before": 3.0, "space_after": 6.0,
    },
    "table": {
        "east": "仿宋_GB2312", "ascii": "仿宋_GB2312", "size": 12.0,
        "line_ratio": 1.0, "indent0": True,
        "space_before": 0.0, "space_after": 0.0,
    },
}

#: spec 里的键 → docx 样式名（英文/中文双语兜底）
_STYLE_KEYS = {
    "normal": ("Normal", "正文"),
    "title": ("Title", "标题"),
    "subtitle": ("Subtitle", "副标题"),
    "h1": ("Heading 1", "标题 1"),
    "h2": ("Heading 2", "标题 2"),
    "h3": ("Heading 3", "标题 3"),
    "h4": ("Heading 4", "标题 4"),
    "h5": ("Heading 5", "标题 5"),
}


def _iter_styles(doc):
    for st in doc.styles:
        yield st


def _find_style(doc, names):
    """按候选名找样式：先精确名，再按小写归一比对。"""
    wanted = [n.strip().lower() for n in names]
    exact = {}
    for st in _iter_styles(doc):
        try:
            exact[str(st.name).strip().lower()] = st
        except Exception:  # pragma: no cover - 个别样式名不可读
            continue
    for n in wanted:
        if n in exact:
            return exact[n]
    return None


def _ensure_style(doc, name, base_name="Normal"):
    st = _find_style(doc, (name,))
    if st is not None:
        return st
    st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    base = _find_style(doc, (base_name,))
    if base is not None:
        try:
            st.base_style = base
        except Exception:  # pragma: no cover
            pass
    return st


def _apply_rpr(style, spec):
    """样式级字体：rFonts 置 rPr 首位（schema 顺序要求），字号/加粗/颜色齐平。"""
    font = style.font
    east = spec.get("east")
    ascii_ = spec.get("ascii")
    if east or ascii_:
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.insert(0, rfonts)
        if ascii_:
            rfonts.set(qn("w:ascii"), ascii_)
            rfonts.set(qn("w:hAnsi"), ascii_)
        if east:
            rfonts.set(qn("w:eastAsia"), east)
            rfonts.set(qn("w:cs"), east)
    if spec.get("size"):
        font.size = Pt(spec["size"])
    if "bold" in spec:
        font.bold = bool(spec["bold"])
    try:
        font.color.rgb = RGBColor(0, 0, 0)   # 覆盖 python-docx 默认标题蓝
    except Exception:  # pragma: no cover
        pass


def _apply_ppr(style, spec):
    pf = style.paragraph_format
    if spec.get("line_pt"):
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(spec["line_pt"])
    elif spec.get("line_ratio"):
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = float(spec["line_ratio"])
    if spec.get("indent0"):
        pf.first_line_indent = Pt(0)
    elif spec.get("first_line_pt"):
        pf.first_line_indent = Pt(spec["first_line_pt"])
    if spec.get("align"):
        pf.alignment = _ALIGN[spec["align"]]
    if spec.get("keep_next"):
        pf.keep_with_next = True
    if "space_before" in spec:
        pf.space_before = Pt(spec["space_before"])
    if "space_after" in spec:
        pf.space_after = Pt(spec["space_after"])


def _format_paragraph(p, spec):
    """段落级格式化（只碰 pPr/rPr，不碰文字）。"""
    pf = p.paragraph_format
    if spec.get("line_pt"):
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(spec["line_pt"])
    elif spec.get("line_ratio"):
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = float(spec["line_ratio"])
    if spec.get("indent0"):
        pf.first_line_indent = Pt(0)
    if spec.get("align"):
        pf.alignment = _ALIGN[spec["align"]]
    if "space_before" in spec:
        pf.space_before = Pt(spec["space_before"])
    if "space_after" in spec:
        pf.space_after = Pt(spec["space_after"])
    size = spec.get("size")
    if size:
        for run in p.runs:
            run.font.size = Pt(size)


def _build_heading_numbering_xml(abstract_id=NUM_ABSTRACT_ID,
                                 start_l1=NUM_START_L1):
    """构造 0910 形态的多级编号定义（%1. / %1.%2. / … 段末带点）。"""
    lvls = []
    for ilvl in range(NUM_LEVELS):
        lvl_text = ".".join("%%%d" % (i + 1) for i in range(ilvl + 1)) + "."
        start = start_l1 if ilvl == 0 else 1
        lvls.append(
            '<w:lvl w:ilvl="%d"><w:start w:val="%d"/>'
            '<w:numFmt w:val="decimal"/><w:lvlText w:val="%s"/>'
            '<w:lvlJc w:val="left"/><w:suff w:val="space"/>'
            '<w:pPr><w:ind w:left="0" w:firstLine="0"/></w:pPr></w:lvl>'
            % (ilvl, start, lvl_text))
    return (
        '<w:abstractNum w:abstractNumId="%d"><w:nsid w:val="09100090"/>'
        '<w:multiLevelType w:val="multilevel"/><w:tmpl w:val="09100090"/>%s'
        '</w:abstractNum>'
        '<w:num w:numId="%d"><w:abstractNumId w:val="%d"/></w:num>'
        % (abstract_id, "".join(lvls), NUM_ID, abstract_id))


def _inject_numpr(style_block, level, num_id=NUM_ID):
    """给一个样式块注入 <w:numPr>（已存在则原样返回）。"""
    if "<w:numPr>" in style_block:
        return style_block, False
    numpr = ('<w:numPr><w:ilvl w:val="%d"/><w:numId w:val="%d"/></w:numPr>'
             % (level, num_id))
    m = re.search(r"<w:pPr>(.*)</w:pPr>", style_block, re.S)
    if m is None:
        if "<w:rPr" in style_block:
            return style_block.replace(
                "<w:rPr", "<w:pPr>%s</w:pPr><w:rPr" % numpr, 1), True
        return style_block.replace(
            "</w:style>", "<w:pPr>%s</w:pPr></w:style>" % numpr, 1), True
    body = m.group(1)
    pos = len(body)
    for tag in _AFTER_NUMPR_TAGS:
        i = body.find(tag)
        if i != -1 and i < pos:
            pos = i
    new_body = body[:pos] + numpr + body[pos:]
    start = m.start(1)
    return style_block[:start] + new_body + style_block[m.end(1):], True


def attach_heading_numbering(docx_path, verbose=True):
    """给 Heading 1–5 样式挂多级自动编号（zip 级注入，幂等）。

    对标 0910：标题文本不含节号，编号由样式自动生成，粘贴进 0910 后
    按其样式与位置自动出号（Ctrl+A → F9 刷新域即可）。
    返回 (ok, info)。
    """
    abs_path = os.path.abspath(docx_path)
    if not os.path.exists(abs_path):
        return False, {"error": f"文件不存在: {abs_path}"}
    with zipfile.ZipFile(abs_path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    if "word/numbering.xml" not in data:
        return False, {"error": "该 docx 无 word/numbering.xml，需另行注入编号部件"}

    styles = data["word/styles.xml"].decode("utf-8")
    numbering = data["word/numbering.xml"].decode("utf-8")
    injected = 0
    target_names = ["heading %d" % i for i in range(1, NUM_LEVELS + 1)]

    def _style_sub(m):
        nonlocal injected
        block = m.group(0)
        nm = re.search(r'<w:name w:val="([^"]*)"', block)
        if not nm:
            return block
        name = nm.group(1).strip().lower()
        if name not in target_names:
            return block
        level = target_names.index(name)
        new_block, changed = _inject_numpr(block, level)
        if changed:
            injected += 1
        return new_block

    styles_new = re.sub(r"<w:style [^>]*>.*?</w:style>", _style_sub, styles,
                        flags=re.S)

    numbering_note = "已存在，跳过"
    if 'w:abstractNumId="%d"' % NUM_ABSTRACT_ID not in numbering:
        block = _build_heading_numbering_xml()
        abstract_xml, num_xml = block.split("</w:abstractNum>")[0] + "</w:abstractNum>", \
            "<w:num " + block.split("<w:num ", 1)[1]
        if "<w:num " in numbering:
            numbering = numbering.replace("<w:num ", abstract_xml + "<w:num ", 1)
        else:
            numbering = numbering.replace("</w:numbering>",
                                          abstract_xml + "</w:numbering>", 1)
        # ⚠ 2026-09-20 修（同源同步）：原写法 `replace("</w:numbering>", num_xml, 1)`
        #   **丢掉了闭合标签** —— num_xml 是 `<w:num …>…</w:num>`，替换后
        #   `</w:numbering>` 不复存在，numbering.xml 从此不良构（Word 报「文件已损坏」、
        #   python-docx 报 `Premature end of data in tag numbering`）。该路径此前从未被
        #   跑到：历史 v2 件的编号走的是另一条路径（abstractNum 6 / numId 1），缺陷潜伏至今。
        numbering = numbering.replace("</w:numbering>", num_xml + "</w:numbering>", 1)
        numbering_note = "已注入 abstractNum %d / numId %d" % (
            NUM_ABSTRACT_ID, NUM_ID)

    # 良构断言（fail-closed）：编号部件不良构会让 Word 直接判文件损坏，
    # 宁可在这里报错，也不产出打不开的 docx。
    try:
        from xml.etree import ElementTree as _ET
        _ET.fromstring(numbering)
    except _ET.ParseError as e:
        return False, {"error": "numbering.xml 注入后不良构，已中止（未写盘）：%s" % e}

    data["word/styles.xml"] = styles_new.encode("utf-8")
    data["word/numbering.xml"] = numbering.encode("utf-8")
    tmp = abs_path + ".numtmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, data[n])
    os.replace(tmp, abs_path)

    info = {"heading_styles": injected, "numbering": numbering_note,
            "num_id": NUM_ID, "abstract_id": NUM_ABSTRACT_ID}
    if verbose:
        print("[numbering] Heading 1–%d 挂编号：%d 个样式；%s"
              % (NUM_LEVELS, injected, numbering_note))
    return True, info


def count_text_chars(docx_path):
    """全文文字长度（用于「文字未动」比对）；只读 w:t，不含格式。"""
    from docx import Document as _Doc
    d = _Doc(docx_path)
    n = 0
    for p in d.paragraphs:
        n += len(p.text or "")
    for t in d.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    n += len(p.text or "")
    return n


def apply_style_0910(docx_path, style_set=STYLE_SET, numbering=True, verbose=True):
    """把 docx 样式定义照抄 0910 规格；返回 (ok, info)。

    info = {"text_chars", "paragraphs", "captions", "table_paragraphs",
            "styles", "numbering"}
    numbering=True 时同时给 Heading 1–5 挂多级自动编号（对标 0910）。
    """
    abs_path = os.path.abspath(docx_path)
    if not os.path.exists(abs_path):
        return False, {"error": f"文件不存在: {abs_path}"}
    if style_set not in (STYLE_SET, "0910", "gs"):
        if verbose:
            print(f"[style] 未知样式集 {style_set!r}，仅支持 {STYLE_SET}")
        return False, {"error": f"未知样式集 {style_set!r}"}

    doc = Document(abs_path)
    done = []

    # ① 样式定义层
    for key in ("normal", "title", "subtitle", "h1", "h2", "h3", "h4", "h5"):
        st = _find_style(doc, _STYLE_KEYS[key])
        if st is None:
            continue
        _apply_rpr(st, PROFILE[key])
        _apply_ppr(st, PROFILE[key])
        done.append(key)

    # ② 图题 / 表格专用样式（0910 同名能力）
    cap_style = _ensure_style(doc, CAPTION_STYLE_NAME)
    _apply_rpr(cap_style, PROFILE["caption"])
    _apply_ppr(cap_style, PROFILE["caption"])
    tbl_style = _ensure_style(doc, TABLE_STYLE_NAME)
    _apply_rpr(tbl_style, PROFILE["table"])
    _apply_ppr(tbl_style, PROFILE["table"])

    # ③ 段落级：图题段 + 文档副标题段
    captions = 0
    subtitle_done = False
    body_paras = list(doc.paragraphs)
    for idx, p in enumerate(body_paras):
        txt = (p.text or "").strip()
        if not txt:
            continue
        if CAPTION_RE.match(txt):
            p.style = cap_style
            _format_paragraph(p, PROFILE["caption"])
            captions += 1
            continue
        if not subtitle_done and idx > 0:
            prev = body_paras[idx - 1]
            try:
                prev_is_title = str(prev.style.name).strip().lower() in ("title", "标题")
            except Exception:  # pragma: no cover
                prev_is_title = False
            if prev_is_title and len(txt) <= 80:
                p.style = _find_style(doc, _STYLE_KEYS["subtitle"]) or p.style
                _format_paragraph(p, PROFILE["subtitle"])
                subtitle_done = True

    # ④ 表格单元格段：仿宋小四、单倍行距、无缩进
    table_paras = 0
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.style = tbl_style
                    _format_paragraph(p, PROFILE["table"])
                    table_paras += 1

    doc.save(abs_path)
    info = {
        "styles": done,
        "captions": captions,
        "table_paragraphs": table_paras,
        "paragraphs": len(body_paras),
        "text_chars": count_text_chars(abs_path),
        "file": abs_path,
    }
    if numbering:
        ok_num, num_info = attach_heading_numbering(abs_path, verbose=verbose)
        info["numbering"] = num_info
        if not ok_num and verbose:
            print("[numbering] 未挂自动编号：%s" % num_info.get("error"))
    if verbose:
        print(f"[style] {STYLE_SET} 已应用：样式 {len(done)} 项／图题 {captions} 段／"
              f"表格段 {table_paras} 段／全文 {info['text_chars']} 字")
    return True, info
