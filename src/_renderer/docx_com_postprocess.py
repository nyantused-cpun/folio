# -*- coding: utf-8 -*-
"""DOCX COM 后处理模块（pywin32）。

python-docx 建骨架后：
1. 多级标题编号（一、(一)、1.、1.1、…）：统一用 python-docx 手动写入
   （两条路径共用 _manual_numbering，与是否有 pywin32 无关）
2. 自动生成目录（TOC 域）：有 pywin32 用 Word COM 生成并刷新；
   无 pywin32 插入 TOC 域代码（Word 打开后 Ctrl+A -> F9 更新）
3. 页眉页脚（非暗标时插入项目名/页码）：仅 COM 路径
"""
import os


# ============================================================
# 编号风格命名唯一事实源（P3：手动编号与 COM 重排两套命名体系互不认，
# chapter/legal/simple 在手动路径静默退化平铺）——canonical 名 + 别名归一，
# _manual_numbering 与 renumber_headings 共用本层。
# ============================================================

# canonical 风格名：renumber_headings / CLI word-com --style 消费
NUMBERING_STYLES = ("chinese_multi", "legal", "chapter", "simple")
DEFAULT_NUMBERING_STYLE = "chinese_multi"

# 别名 -> canonical：chinese_multi_level 是 spec.format.numbering_style 的
# 历史缺省名（手动编号路径），与 chinese_multi 同义
_NUMBERING_STYLE_ALIASES = {
    "chinese_multi_level": "chinese_multi",
}


def normalize_numbering_style(style):
    """编号风格别名归一（唯一事实源）：别名/大小写归一到 canonical 名。

    未知风格回退 DEFAULT_NUMBERING_STYLE。返回 (canonical, known)，
    known=False 表示传入的是未知风格（调用方可打印告警，行为同原兜底）。
    """
    key = str(style or "").strip().lower()
    key = _NUMBERING_STYLE_ALIASES.get(key, key)
    if key not in NUMBERING_STYLES:
        return DEFAULT_NUMBERING_STYLE, False
    return key, True


def com_postprocess(docx_path, fmt_config):
    """COM 后处理主入口。

    Args:
        docx_path: docx 文件路径
        fmt_config: spec.format 字典
    """
    abs_path = os.path.abspath(docx_path)

    try:
        import win32com.client  # noqa: F401 - pywin32 可用性探测，缺失走 fallback
    except ImportError:
        _fallback_postprocess(docx_path, fmt_config)
        return

    # 多级编号：先用 python-docx 手动写入（原 COM 版 _apply_numbering 是
    # no-op——把 OutlineLevel 读出来再赋回自身，已删除）
    if fmt_config.get("numbering"):
        try:
            from docx import Document
            _doc = Document(abs_path)
            _manual_numbering(_doc, fmt_config.get("numbering_style", "chinese_multi_level"))
            _doc.save(abs_path)
            print("[docx] 多级编号已应用（手动模式）")
        except Exception as e:
            print(f"[docx] 多级编号失败: {e}")

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        # 自动目录
        if fmt_config.get("toc"):
            _generate_toc(doc, fmt_config.get("toc_levels", "1-3"))

        # 页眉页脚（非暗标）
        if not fmt_config.get("dark_bid", False):
            _add_headers_footers(doc, fmt_config)

        doc.Save()
    finally:
        # 统一走 _close_word（异常守卫 + 等待进程释放）；裸 Quit 曾在
        # Close 抛异常时跳过 Quit，Word 进程残留
        _close_word(word, doc)


def _generate_toc(doc, levels="1-3"):
    """在文档开头插入目录。

    使用 Word COM 的 TablesOfContents.Add 方法。
    """
    try:
        # 跳到文档开头
        rng = doc.Range(0, 0)

        # 插入"目录"标题
        rng.InsertBefore("\n目录\n")
        rng = doc.Range(0, 0)

        # 插入 TOC 域
        # levels 格式 "1-3" -> Word 用 "1-3"
        toc_range = doc.Range(0, 0)
        doc.TablesOfContents.Add(
            Range=toc_range,
            UseHeadingStyles=True,
            UpperHeadingLevel=int(levels.split("-")[0]),
            LowerHeadingLevel=int(levels.split("-")[1]),
        )

        # 更新目录
        for toc in doc.TablesOfContents:
            toc.Update()

        print("[COM] 目录已生成")
    except Exception as e:
        print(f"[COM] 目录生成失败: {e}")


def _add_headers_footers(doc, fmt_config):
    """添加页眉页脚（非暗标模式）。"""
    try:
        for section in doc.Sections:
            # 页眉：项目名
            header = section.Headers(1)  # wdHeaderFooterPrimary = 1
            header.Range.Text = fmt_config.get("project_name", "")

            # 页脚：页码
            footer = section.Footers(1)
            footer.Range.Text = ""
            footer.PageNumbers.Add(
                PageNumberAlignment=2,  # wdAlignPageNumberCenter = 2
                FirstPage=True,
            )

        print("[COM] 页眉页脚已添加")
    except Exception as e:
        print(f"[COM] 页眉页脚失败: {e}")


# ============================================================
# 降级方案（无 pywin32 时）
# ============================================================

def _fallback_postprocess(docx_path, fmt_config):
    """无 pywin32 时，用 python-docx 手动处理。"""
    from docx import Document

    doc = Document(docx_path)

    # 手动编号：给标题加编号文本
    if fmt_config.get("numbering"):
        _manual_numbering(doc, fmt_config.get("numbering_style", "chinese_multi_level"))

    # 手动 TOC：插入 TOC 域代码（Word 打开时按 F9 更新）
    if fmt_config.get("toc"):
        _manual_toc(doc, fmt_config.get("toc_levels", "1-3"))

    doc.save(docx_path)
    print("[docx] 降级后处理完成（编号/目录为手动模式，Word 打开后请按 Ctrl+A -> F9 更新目录）")


def _manual_numbering(doc, style="chinese_multi_level"):
    """手动编号：给标题段落前加编号文本。

    风格名统一经 normalize_numbering_style 归一（P3：与 COM 侧
    renumber_headings 共用命名事实源，chapter/legal/simple 原在此静默
    退化平铺）。chinese_multi 保留本函数历史输出（二级半角括号，基线
    测试在案）；legal/chapter/simple 复用 COM 侧 _number_prefix 文本前缀。
    """
    canon, known = normalize_numbering_style(style)
    if not known:
        print(f"[docx] 未知编号风格 {style!r}，回退为 {DEFAULT_NUMBERING_STYLE}")
    counters = [0] * 9  # 9 级编号计数器（与 COM 侧 _number_prefix 对齐）

    cn_num = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    cn_paren = ["(一)", "(二)", "(三)", "(四)", "(五)", "(六)", "(七)", "(八)", "(九)", "(十)"]

    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            try:
                level = int(para.style.name.replace("Heading ", "").replace("标题", ""))
            except ValueError:
                continue
            if level < 1 or level > 7:
                continue

            # 更新计数器
            counters[level - 1] += 1
            # 重置下级
            for i in range(level, 9):
                counters[i] = 0

            # 生成编号文本
            n = counters[level - 1]
            if canon == "chinese_multi":
                if level == 1:
                    prefix = f"{cn_num[n - 1] if n <= 10 else n}、"
                elif level == 2:
                    prefix = f"{cn_paren[n - 1] if n <= 10 else f'({n})'} "
                elif level == 3:
                    prefix = f"{n}. "
                elif level == 4:
                    prefix = f"{counters[0]}.{counters[1]}.{counters[2]}.{counters[3]} "
                else:
                    prefix = f"({n}) "
            else:
                # legal/chapter/simple：与 COM 重排共用同一前缀生成器
                prefix = _number_prefix(level, counters, canon)

            # 在段落开头插入编号
            run = para.add_run(prefix)
            run.bold = True
            # 移到段落最前面：插在第一个 run 之前
            # （原实现 addprevious(para.runs[-1]) 是把自身移到自己前面，no-op，
            #   编号会留在段落末尾）
            if len(para.runs) > 1:
                para.runs[0]._element.addprevious(run._element)


def _manual_toc(doc, levels="1-3"):
    """手动插入 TOC 域代码（Word 打开时需手动更新）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # 在文档开头插入段落
    para = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    new_para = para.insert_paragraph_before("目录")
    new_para.style = doc.styles["Heading 1"]

    # 插入 TOC 域
    toc_para = para.insert_paragraph_before("")
    run = toc_para.add_run()

    fldChar_begin = OxmlElement("w:fldChar")
    fldChar_begin.set(qn("w:fldCharType"), "begin")

    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    upper, lower = levels.split("-")
    instrText.text = f' TOC \\o "{upper}-{lower}" \\h \\z \\u '

    fldChar_separate = OxmlElement("w:fldChar")
    fldChar_separate.set(qn("w:fldCharType"), "separate")

    fldText = OxmlElement("w:t")
    fldText.text = "[请按 Ctrl+A, F9 更新目录]"

    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")

    run._element.append(fldChar_begin)
    run._element.append(instrText)
    run._element.append(fldChar_separate)
    run._element.append(fldText)
    run._element.append(fldChar_end)

# ============================================================
# Windows COM Word 后处理引擎（pywin32）
# 以下每个函数独立打开/保存/关闭一个 Word 实例，不共享状态。
# ============================================================

# Word 内置样式常量（WdBuiltinStyle，跨中英文 UI 通用）
_WD_STYLE_NORMAL = -1
_WD_STYLE_HEADING_1 = -2
_WD_STYLE_HEADING_2 = -3
_WD_STYLE_HEADING_3 = -4
_WD_STYLE_HEADING_4 = -5
_WD_STYLE_HEADING_5 = -6

# WdListNumberStyle 常量
_WD_LIST_ARABIC = 0
_WD_LIST_CHINESE_COUNTING = 40  # 一、二、三…

# WdLineSpacing / 对齐 常量
_WD_LINE_SPACE_EXACTLY = 4
_WD_ALIGN_LEFT = 0
_WD_ALIGN_CENTER = 1


def _open_word():
    """创建并配置一个不可见的 Word.Application 实例。"""
    import time
    import win32com.client

    # 连续 COM 调用时旧实例可能未完全释放，重试几次
    for _ in range(3):
        try:
            word = win32com.client.Dispatch("Word.Application")
            # 安全 P1-2：打开外部文档前强制禁宏（msoAutomationSecurityForceDisable）
            word.AutomationSecurity = 3
            try:
                word.Visible = False
            except Exception:
                # 已有一个可见 Word 实例时 Visible 不可写，不影响操作
                pass
            word.DisplayAlerts = False
            return word
        except Exception:
            time.sleep(0.5)
            continue
    raise RuntimeError("无法启动 Word COM 实例")


def _close_word(word, doc=None):
    """安全关闭 Word 文档与实例，等待进程释放。"""
    import time
    if doc:
        try:
            doc.Close(False)
        except Exception:
            pass
    if word:
        try:
            word.Quit()
        except Exception:
            pass
        time.sleep(0.3)


def _get_style(doc, *names):
    """按中英文名依次查找内置样式，返回 Style 对象。"""
    for n in names:
        try:
            return doc.Styles(n)
        except Exception:
            continue
    return doc.Styles(names[0])


def _heading_style_local_name(doc, level):
    """返回 Heading N / 标题 N 的本地化样式名（用于多级列表链接）。"""
    en = "Heading %d" % level
    zh = "标题 %d" % level
    for name in (en, zh):
        try:
            return doc.Styles(name).NameLocal
        except Exception:
            continue
    return en


def _level_configs(style):
    """根据风格返回 9 级列表的配置。

    每项: (NumberFormat, NumberStyle, 是否链接标题样式)
    """
    arabic = _WD_LIST_ARABIC
    chinese = _WD_LIST_CHINESE_COUNTING

    if style == "legal":
        # 第X条 / X.Y / X.Y.Z
        return [
            ("第%1条", arabic, 1),
            ("%1.%2", arabic, 2),
            ("%1.%2.%3", arabic, 3),
            ("%1.%2.%3.%4", arabic, 4),
            ("%1.%2.%3.%4.%5", arabic, 5),
            ("%1.%2.%3.%4.%5.%6", arabic, 6),
            ("%1.%2.%3.%4.%5.%6.%7", arabic, 7),
            ("%1.%2.%3.%4.%5.%6.%7.%8", arabic, 8),
            ("%1.%2.%3.%4.%5.%6.%7.%8.%9", arabic, 9),
        ]
    if style == "chapter":
        # 第一章 / 1.1 / 1.1.1 / 1.1.1.1 / （一） / (1) / 1. / 2. …
        # 政府/事业单位报告标准：章 = 中文数字 + 章；节/子节 = 多层阿拉伯；
        # 深层条目 = 中文括号（一）、阿拉伯括号 (1)
        return [
            ("第%1章", chinese, 1),
            ("%1.%2", arabic, 2),
            ("%1.%2.%3", arabic, 3),
            ("%1.%2.%3.%4", arabic, 4),
            ("（%5）", chinese, 5),
            ("(%6)", arabic, 6),
            ("%7.", arabic, 7),
            ("%8.", arabic, 8),
            ("%9.", arabic, 9),
        ]
    if style == "simple":
        # 纯数字
        fmts = ["%1"]
        for i in range(2, 10):
            fmts.append(".".join("%d" % j for j in range(1, i + 1)))
        return [(fmts[i - 1], arabic, i) for i in range(1, 10)]

    # 默认 chinese_multi: 一、/（一）/1./1.1/(1)
    return [
        ("%1、", chinese, 1),
        ("（%2）", chinese, 2),
        ("%3.", arabic, 3),
        ("%3.%4", arabic, 4),
        ("(%5)", arabic, 5),
        ("(%6)", arabic, 6),
        ("(%7)", arabic, 7),
        ("(%8)", arabic, 8),
        ("(%9)", arabic, 9),
    ]


def _build_multilevel_list(doc, style):
    """用 ListTemplates.Add + ListLevels 构建多级列表。

    返回创建的 ListTemplate。正确链接方式是通过 `Style.LinkToListTemplate`
    把标题样式绑定到指定层级，而不是设置 ListLevel.LinkedStyle。
    """
    configs = _level_configs(style)
    lt = doc.ListTemplates.Add(OutlineNumbered=True)
    levels = lt.ListLevels
    for i, (fmt, num_style, heading_level) in enumerate(configs, start=1):
        lvl = levels(i)
        lvl.NumberFormat = fmt
        lvl.NumberStyle = num_style
        lvl.StartAt = 1
        lvl.ResetOnHigher = True
        lvl.Alignment = _WD_ALIGN_LEFT
        # 缩进：层级越深越靠右
        lvl.NumberPosition = 0
        lvl.TextPosition = 21 + (heading_level - 1) * 12
        lvl.TabPosition = 21 + (heading_level - 1) * 12
        lvl.TrailingCharacter = 0  # wdTrailingTab
    # 通过 Style.LinkToListTemplate 把标题样式绑定到列表层级
    for i in range(1, 6):
        try:
            style_name = _heading_style_local_name(doc, i)
            doc.Styles(style_name).LinkToListTemplate(lt, i)
        except Exception as e:
            print(f"[renumber] 第 {i} 级标题样式绑定失败: {e}")
    return lt


def _number_prefix(level, counters, style):
    """根据风格和计数器生成指定层级的编号前缀。

    counters 是 9 级计数器列表，已在此函数调用前更新。
    返回带尾随空格的前缀，例如 "第一章 "、"1.1 "、"（一） "。
    """
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    cn_paren = ["（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）", "（八）", "（九）", "（十）"]
    n = counters[level - 1]
    cn_n = cn[n - 1] if n <= 10 else str(n)

    if style == "chapter":
        # 第一章 / 1.1 / 1.1.1 / 1.1.1.1 / （一） / (1) / 1. / 2.
        if level == 1:
            return f"第{cn_n}章 "
        elif level == 2:
            return f"{counters[0]}.{counters[1]} "
        elif level == 3:
            return f"{counters[0]}.{counters[1]}.{counters[2]} "
        elif level == 4:
            return f"{'.'.join(str(counters[i]) for i in range(4))} "
        elif level == 5:
            return f"{cn_paren[n - 1] if n <= 10 else f'（{n}）'} "
        elif level == 6:
            return f"({n}) "
        else:
            return f"{n}. "
    elif style == "legal":
        # 第X条 / X.Y / X.Y.Z
        if level == 1:
            return f"第{n}条 "
        elif level == 2:
            return f"{counters[0]}.{counters[1]} "
        else:
            return f"{'.'.join(str(counters[i]) for i in range(level))} "
    elif style == "simple":
        # 纯数字
        return f"{'.'.join(str(counters[i]) for i in range(level))} "
    else:
        # chinese_multi: 一、/（一）/1./1.1/(1)
        if level == 1:
            return f"{cn_n}、"
        elif level == 2:
            return f"{cn_paren[n - 1] if n <= 10 else f'（{n}）'} "
        elif level == 3:
            return f"{n}. "
        elif level == 4:
            return f"{counters[0]}.{counters[1]}.{counters[2]}.{counters[3]} "
        else:
            return f"({n}) "


def _strip_number_prefix(text, style):
    """去掉标题文本开头的编号前缀（保留标题文字本身）。

    支持 styles: 一、/第一章/1.1/（一）/(1)/第X条 等。
    """
    import re
    # 依次尝试各风格前缀
    patterns = [
        r"^第[一二三四五六七八九十百\d]+[章条] ",          # 第一章 / 第1条
        r"^[一二三四五六七八九十百]+、",                     # 一、
        r"^（[一二三四五六七八九十百]+）",                   # （一）
        r"^\([一二三四五六七八九十\d]+\)",                   # (1) / (一)
        r"^[（(][一二三四五六七八九十]+[）)]",               # （一） / (一)
        r"^[（(]\d+[）)]",                                  # （1） / (1)
        r"^\d+(\.\d+)*[\.、．]\s*",                         # 1. / 1.1 / 1.1.1.
        r"^\d+(\.\d+)*\s+",                                 # 1.1 （空格分隔）
    ]
    for pat in patterns:
        m = re.match(pat, text)
        if m:
            return text[m.end():].lstrip()
    return text


def _get_heading_level(p):
    """从段落对象读取标题层级（1-9），非标题返回 0。"""
    try:
        return int(p.OutlineLevel)
    except Exception:
        return 0


def renumber_headings(docx_path, style="chinese_multi"):
    """确定性文本级重排所有标题编号。

    不依赖 Word 原生多级列表（PDF 转换不渲染自动域），而是：
    1. 遍历所有标题段落
    2. 剥离旧编号前缀
    3. 按层级计数器生成新编号前缀并写回标题文本
    4. 保存

    style:
        chinese_multi  — 一、/（一）/1./1.1/(1)
        legal          — 第X条 / X.Y / X.Y.Z
        chapter        — 第一章 / 1.1 / 1.1.1 / （一） / (1)
        simple         — 纯数字
    风格名经 normalize_numbering_style 归一（别名 chinese_multi_level 同义），
    与手动编号路径共用命名事实源。
    """
    canon, known = normalize_numbering_style(style)
    if not known:
        print(f"[renumber] 未知风格 {style!r}，回退为 {canon}")
    style = canon

    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[renumber] 缺少 pywin32，无法重排，跳过")
        return False

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        counters = [0] * 9
        changed = 0
        for p in doc.Paragraphs:
            level = _get_heading_level(p)
            if level < 1 or level > 9:
                continue

            # 更新计数器：当前级 +1，下级清零
            counters[level - 1] += 1
            for i in range(level, 9):
                counters[i] = 0

            # 生成新编号
            prefix = _number_prefix(level, counters, style)

            # 取标题文本（Range.Text 末尾带段落标记 \r）
            raw = p.Range.Text
            # 去掉末尾段落标记后再清洗编号
            text = raw.rstrip("\r\n").strip()
            cleaned = _strip_number_prefix(text, style)

            # 写回：开头插入编号 + 保留标题文字 + 恢复段落标记
            p.Range.Text = prefix + cleaned + "\r"
            changed += 1

        doc.Save()
        print(f"[renumber] 已重排 {changed} 个标题（{style} 风格）")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[renumber] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def normalize_headings(docx_path):
    """扫描文档，把“看起来像标题但没套 Heading 样式”的段落套上 Heading 1-5。

    仅处理 OutlineLevel=0（正文层级）的段落。规则：
        一、 开头 -> Heading 1
        （一） 开头 -> Heading 2
        1.1 开头  -> Heading 4
        1. 开头   -> Heading 3
        (1) 开头  -> Heading 5
    """
    import re

    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[normalize] 缺少 pywin32，跳过")
        return False

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        changed = 0
        for p in doc.Paragraphs:
            try:
                if p.OutlineLevel != 0:
                    continue
            except Exception:
                continue

            text = p.Range.Text.strip()
            if not text:
                continue

            # 注意 1.1 需在 1. 之前判断，避免被误判为 Heading 3
            if re.match(r"^[一二三四五六七八九十百]+、", text):
                level = 1
            elif re.match(r"^（[一二三四五六七八九十]+）", text):
                level = 2
            elif re.match(r"^\d+\.\d+", text):
                level = 4
            elif re.match(r"^\d+\.", text):
                level = 3
            elif re.match(r"^\(\d+\)", text):
                level = 5
            else:
                continue

            # wdStyleHeading1 = -2，故 HeadingN = -1 - N
            p.Style = -1 - level
            changed += 1

        doc.Save()
        print(f"[normalize] 已为 {changed} 个段落套用标题样式")
        return changed
    except Exception as e:
        print(f"[normalize] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def apply_style_set(docx_path, style_set="bid"):
    """注入预定义样式集。

    bid 样式：
        Normal   = 仿宋_GB2312 小四(12pt) 固定28磅行距 首行缩进2字符
        Heading1 = 黑体 三号(16pt) 加粗
        Heading2 = 楷体 四号(14pt) 加粗
        Heading3 = 仿宋 小四(12pt) 加粗
        页边距：上3.7 下3.5 左2.8 右2.6 cm
    """
    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[style] 缺少 pywin32，跳过")
        return False

    if style_set != "bid":
        print(f"[style] 未知样式集 {style_set!r}，仅支持 bid，回退为 bid")
        style_set = "bid"

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        # Normal：仿宋_GB2312 小四 28磅固定行距 首行缩进2字符
        normal = _get_style(doc, "Normal", "正文")
        normal.Font.NameFarEast = "仿宋_GB2312"
        normal.Font.NameAscii = "Times New Roman"
        normal.Font.Size = 12  # 小四
        pf = normal.ParagraphFormat
        pf.LineSpacingRule = _WD_LINE_SPACE_EXACTLY
        pf.LineSpacing = 28
        try:
            pf.CharacterUnitFirstLineIndent = 2  # 2 字符
        except Exception:
            pf.FirstLineIndent = word.CentimetersToPoints(0.74)

        # 标题字体（标书标题为黑色，覆盖 Word 默认蓝色）
        h1 = _get_style(doc, "Heading 1", "标题 1")
        h1.Font.NameFarEast = "黑体"
        h1.Font.Size = 16  # 三号
        h1.Font.Bold = True
        h1.Font.Color = 0  # wdColorBlack

        h2 = _get_style(doc, "Heading 2", "标题 2")
        h2.Font.NameFarEast = "楷体"
        h2.Font.Size = 14  # 四号
        h2.Font.Bold = True
        h2.Font.Color = 0  # wdColorBlack

        h3 = _get_style(doc, "Heading 3", "标题 3")
        h3.Font.NameFarEast = "仿宋"
        h3.Font.Size = 12  # 小四
        h3.Font.Bold = True
        h3.Font.Color = 0  # wdColorBlack

        # 页边距（1 cm = 28.3464567 pt，直接乘法避免 COM 方法不稳定）
        _CM_TO_PT = 28.3464567
        ps = doc.PageSetup
        ps.TopMargin = 3.7 * _CM_TO_PT
        ps.BottomMargin = 3.5 * _CM_TO_PT
        ps.LeftMargin = 2.8 * _CM_TO_PT
        ps.RightMargin = 2.6 * _CM_TO_PT

        doc.Save()
        print(f"[style] 样式集 {style_set} 已应用")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[style] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def apply_headers_footers(docx_path, project_name="", dark_bid=False):
    """页眉页脚。非暗标时：页眉=项目名，页脚=居中页码；暗标时跳过。"""
    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[headers] 缺少 pywin32，跳过")
        return False

    if dark_bid:
        print("[headers] 暗标模式，跳过页眉页脚")
        return True

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        for section in doc.Sections:
            # 页眉：项目名，左对齐
            header = section.Headers(1)  # wdHeaderFooterPrimary = 1
            header.Range.Text = project_name or ""
            header.Range.ParagraphFormat.Alignment = _WD_ALIGN_LEFT

            # 页脚：居中页码
            footer = section.Footers(1)
            footer.Range.Text = ""
            footer.PageNumbers.Add(
                PageNumberAlignment=_WD_ALIGN_CENTER,  # 2 = 居中
                FirstPage=True,
            )

        doc.Save()
        print("[headers] 页眉页脚已添加")
        return True
    except Exception as e:
        print(f"[headers] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def refresh_toc(docx_path):
    """刷新所有目录域（TablesOfContents.Update + Fields.Update）。"""
    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[toc] 缺少 pywin32，跳过")
        return False

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)

        toc_count = 0
        for toc in doc.TablesOfContents:
            toc.Update()
            toc_count += 1
        try:
            doc.Fields.Update()
        except Exception as e:
            print(f"[toc] 更新全部域失败: {e}")

        doc.Save()
        print(f"[toc] 已刷新 {toc_count} 个目录域")
        return True
    except Exception as e:
        print(f"[toc] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def save_as_pdf(docx_path, pdf_path=None):
    """另存为 PDF（FileFormat=17, wdFormatPDF）。"""
    abs_path = os.path.abspath(docx_path)
    if pdf_path is None:
        pdf_path = os.path.splitext(abs_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[pdf] 缺少 pywin32，跳过")
        return False

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)
        doc.SaveAs2(pdf_path, FileFormat=17)  # wdFormatPDF = 17
        print(f"[pdf] 已导出: {pdf_path}")
        return True
    except Exception as e:
        print(f"[pdf] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def accept_all_changes(docx_path):
    """接受所有修订（AcceptAllRevisions）。"""
    abs_path = os.path.abspath(docx_path)
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[accept] 缺少 pywin32，跳过")
        return False

    word = None
    doc = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)
        doc.AcceptAllRevisions()
        doc.Save()
        print("[accept] 已接受全部修订")
        return True
    except Exception as e:
        print(f"[accept] 失败: {e}")
        return False
    finally:
        _close_word(word, doc)


def compare_documents(docx_path, old_path):
    """比较两个文档（Word 原生 Compare），接受修订后保存回 docx_path。"""
    abs_path = os.path.abspath(docx_path)
    old_abs = os.path.abspath(old_path)
    if not os.path.exists(old_abs):
        print(f"[compare] 旧文档不存在: {old_abs}")
        return False

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[compare] 缺少 pywin32，跳过")
        return False

    word = None
    doc = None
    result = None
    try:
        word = _open_word()
        doc = word.Documents.Open(abs_path)
        # CompareTarget=2 (wdCompareTargetNew) 在新文档中生成比较结果
        result = doc.Compare(Name=old_abs, CompareTarget=2)
        result.AcceptAllRevisions()
        result.SaveAs(abs_path)
        print(f"[compare] 已比较 {os.path.basename(old_abs)} 并接受修订，保存回原文档")
        return True
    except Exception as e:
        print(f"[compare] 失败: {e}")
        return False
    finally:
        if result:
            try:
                result.Close(False)
            except Exception:
                pass
        # doc/word 释放统一走 _close_word（与全文件其他出口同款）
        _close_word(word, doc)


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    import glob as _glob

    _here = os.path.dirname(os.path.abspath(__file__))
    _inbox = os.path.abspath(os.path.join(_here, "..", "..", "inbox"))  # src/_renderer 上两级=仓库根
    _docs = sorted(_glob.glob(os.path.join(_inbox, "*.docx")))
    if not _docs:
        print("[自测] inbox 目录没有 docx 文件，跳过")
    else:
        _target = _docs[0]
        print(f"[自测] 使用文件: {_target}")
        normalize_headings(_target)
        renumber_headings(_target, style="chinese_multi")
        print("[自测] 完成（normalize + renumber）")

