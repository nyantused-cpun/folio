"""DOCX 图片环绕方式（OOXML 层）。

python-docx 的 ``run.add_picture()`` 只能产出嵌入型（``wp:inline``）图。本模块把
已插入的图片提升为**浮动图**（``wp:anchor``），支持 Word 的「上下型环绕」等版式，
供方案文档的图题排版复用（用户 2026-09-13 指令：图要上下环绕，不要嵌入型）。

实现在 OOXML 层做 `wp:inline` → `wp:anchor` 的**原地提升**：``extent`` /
``effectExtent`` / ``docPr`` / ``cNvGraphicFramePr`` / ``a:graphic`` 逐个子元素搬迁，
不重建，保留 ``r:embed`` 图片关系，避免丢图。

子元素顺序必须遵循 CT_Anchor schema：
``simplePos → positionH → positionV → extent → effectExtent → <wrap*> → docPr →
cNvGraphicFramePr → graphic``。
"""

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# spec 侧 wrap 取值别名（含中文，容忍手写 spec）
TOP_BOTTOM_ALIASES = {
    "top_bottom", "top-bottom", "topandbottom", "top_and_bottom",
    "上下型", "上下环绕", "上下型环绕",
}
# 需要搬迁进 anchor 的子元素（顺序即 schema 顺序，wrap 单独插）
_MOVE_TAGS = ("wp:extent", "wp:effectExtent", "wp:docPr",
              "wp:cNvGraphicFramePr", "a:graphic")

_EMU_PER_CM = 360000


def normalize_wrap(value):
    """把 spec 的 wrap 值归一为内部枚举：''（嵌入型）/ 'top_bottom'。"""
    v = str(value or "").strip().lower().replace(" ", "")
    if v in TOP_BOTTOM_ALIASES:
        return "top_bottom"
    return ""


def set_image_wrap_top_bottom(run, alignment="center", relative_height=1,
                              dist_cm=0.0):
    """把 run 内的嵌入型图片改成「上下型环绕」浮动图。

    :param run: 含图片的 docx Run（由 ``run.add_picture()`` 产生）
    :param alignment: 水平对齐——center（缺省，相对版心/栏居中）| left | right
    :param relative_height: anchor 的 z 序（相对高度），递增即可
    :param dist_cm: 与上下文字的间距（cm）
    :return: (ok, reason) —— ok=False 时 reason 给出未提升的原因
    """
    drawing = run._element.find(qn("w:drawing"))
    if drawing is None:
        return False, "run 内无 w:drawing（未插入图片？）"
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        # 已是浮动图（anchor）或未知结构：幂等跳过
        if drawing.find(qn("wp:anchor")) is not None:
            return True, "已是浮动图（anchor），跳过"
        return False, "w:drawing 内既无 wp:inline 也无 wp:anchor"

    dist = str(int(dist_cm * _EMU_PER_CM))
    anchor = OxmlElement("wp:anchor")
    for k, v in (("distT", dist), ("distB", dist),
                 ("distL", "114300"), ("distR", "114300"),
                 ("simplePos", "0"),
                 ("relativeHeight", str(int(relative_height))),
                 ("behindDoc", "0"), ("locked", "0"),
                 ("layoutInCell", "1"), ("allowOverlap", "1")):
        anchor.set(k, v)

    simple_pos = OxmlElement("wp:simplePos")
    simple_pos.set("x", "0")
    simple_pos.set("y", "0")
    anchor.append(simple_pos)

    pos_h = OxmlElement("wp:positionH")
    pos_h.set("relativeFrom", "column")
    if alignment in ("left", "right"):
        align_el = OxmlElement("wp:align")
        align_el.text = alignment
    else:
        align_el = OxmlElement("wp:align")
        align_el.text = "center"
    pos_h.append(align_el)
    anchor.append(pos_h)

    pos_v = OxmlElement("wp:positionV")
    pos_v.set("relativeFrom", "paragraph")
    offset = OxmlElement("wp:posOffset")
    offset.text = "0"
    pos_v.append(offset)
    anchor.append(pos_v)

    # 逐个子元素搬迁（顺序 = schema 顺序）
    for tag in _MOVE_TAGS:
        el = inline.find(qn(tag))
        if el is not None:
            anchor.append(el)

    wrap = OxmlElement("wp:wrapTopAndBottom")
    wrap.set("distT", dist)
    wrap.set("distB", dist)
    doc_pr = anchor.find(qn("wp:docPr"))
    if doc_pr is not None:
        doc_pr.addprevious(wrap)          # wrap 必须排在 docPr 之前
    else:                                  # 兜底：docPr 缺失时追加（不常见）
        anchor.append(wrap)

    drawing.replace(inline, anchor)
    return True, "已改为上下型环绕"
