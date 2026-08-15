# -*- coding: utf-8 -*-
"""招标文件解析模块。

规则引擎 + LLM 双驱动：
- 格式要求（字体/页边距/编号/暗标）-> 正则匹配，不走 LLM
- 评分标准 -> LLM 提取，prompt 中给结构化 schema 约束输出
- 资质/废标条款 -> 正则匹配关键词 + LLM 补充

输出 bid_criteria.json，供 outline-to-spec 消费。
"""
import os
import re
import json

from _cli_infra import SCRIPT_DIR


# ============================================================
# 文件读取
# ============================================================

def _read_tender(file_path):
    """读取招标文件，返回全文文本。"""
    if not os.path.isabs(file_path):
        file_path = os.path.join(SCRIPT_DIR, file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"招标文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        from _pipeline import read_pdf
        return read_pdf(file_path)
    elif ext in (".docx", ".doc"):
        from _pipeline import read_docx
        return read_docx(file_path)
    elif ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"不支持的招标文件格式: {ext}（支持 .pdf .docx .txt .md）")


# ============================================================
# 格式要求提取（纯正则，不走 LLM）
# ============================================================

def _extract_format_requirements(text):
    """从招标文件文本中提取格式要求。

    政府采购标书常见格式要求：
    - 字体：仿宋/宋体/黑体/楷体
    - 字号：三号/四号/小四
    - 页边距：上下左右 cm
    - 行距：固定值磅
    - 编号方式：一、(一)、1.、(1)
    - 目录要求
    - 暗标（不显示投标人信息）
    """
    fmt = {
        "body_font": None,
        "body_size": None,
        "heading1_font": None,
        "heading1_size": None,
        "line_spacing": None,
        "first_line_indent": None,
        "margin": {"top": None, "bottom": None, "left": None, "right": None},
        "numbering": None,
        "toc": None,
        "toc_levels": None,
        "dark_bid": False,
        "max_pages": None,
    }

    # 暗标检测
    dark_bid_patterns = [
        r"暗标",
        r"不[得能]出现.*?(投标人|供应商|公司名|单位名)",
        r"不[得能].*?(署名|盖章|标识)",
        r"技术标.*?暗标",
        r"无名.*?标",
    ]
    for pat in dark_bid_patterns:
        if re.search(pat, text):
            fmt["dark_bid"] = True
            break

    # 字体提取
    font_patterns = [
        (r"正文字体[为是][:：]?\s*([\u4e00-\u9fa5]+(?:_GB2312)?)", "body_font"),
        (r"正文.*?(仿宋|宋体|黑体|楷体)(?:_GB2312)?", "body_font"),
        (r"(?:使用|采用).*?(仿宋|宋体|黑体|楷体)(?:_GB2312)?", "body_font"),
        (r"标题字体[为是][:：]?\s*([\u4e00-\u9fa5]+(?:_GB2312)?)", "heading1_font"),
        (r"标题.*?(黑体|宋体|楷体|仿宋)(?:_GB2312)?", "heading1_font"),
    ]
    for pat, key in font_patterns:
        m = re.search(pat, text)
        if m and not fmt[key]:
            font = m.group(1)
            # 补全 _GB2312 后缀
            if font in ("仿宋", "楷体") and "_GB2312" not in font:
                font = font + "_GB2312"
            fmt[key] = font

    # 字号提取（三号=16, 四号=14, 小四=12, 二号=22, 小二=18, 三号=16）
    size_map = {"初号": 42, "小初": 36, "一号": 26, "小一": 24,
                "二号": 22, "小二": 18, "三号": 16, "小三": 15,
                "四号": 14, "小四": 12, "五号": 10.5, "小五": 9}
    size_patterns = [
        (r"正文字号[为是][:：]?\s*(初号|小初|一号|小一号|二号|小二|三号|小三|四号|小四|五号|小五)", "body_size"),
        (r"正文.*?(初号|小初|一号|小一号|二号|小二|三号|小三|四号|小四|五号|小五)", "body_size"),
        (r"标题字号[为是][:：]?\s*(初号|小初|一号|小一号|二号|小二|三号|小三|四号|小四|五号|小五)", "heading1_size"),
    ]
    for pat, key in size_patterns:
        m = re.search(pat, text)
        if m and not fmt[key]:
            sz_name = m.group(1)
            # 归一化：小一号 -> 小一
            if sz_name == "小一号":
                sz_name = "小一"
            fmt[key] = size_map.get(sz_name)

    # 行距提取
    spacing_patterns = [
        r"行距[为是][:：]?\s*(?:固定值[:：]?)?\s*(\d+(?:\.\d+)?)\s*磅",
        r"行间距[为是][:：]?\s*(?:固定值[:：]?)?\s*(\d+(?:\.\d+)?)\s*磅",
        r"固定行距\s*(\d+(?:\.\d+)?)\s*磅",
    ]
    for pat in spacing_patterns:
        m = re.search(pat, text)
        if m:
            fmt["line_spacing"] = float(m.group(1))
            break

    # 首行缩进
    indent_patterns = [
        r"首行缩进\s*(\d+)\s*字符",
        r"首行缩进\s*(\d+)\s*字",
    ]
    for pat in indent_patterns:
        m = re.search(pat, text)
        if m:
            fmt["first_line_indent"] = int(m.group(1))
            break

    # 页边距提取
    margin_patterns = [
        r"页边距[:：]?\s*上\s*(\d+(?:\.\d+)?)\s*cm.*?下\s*(\d+(?:\.\d+)?)\s*cm.*?左\s*(\d+(?:\.\d+)?)\s*cm.*?右\s*(\d+(?:\.\d+)?)\s*cm",
        r"上边距\s*(\d+(?:\.\d+)?)\s*cm.*?下边距\s*(\d+(?:\.\d+)?)\s*cm.*?左边距\s*(\d+(?:\.\d+)?)\s*cm.*?右边距\s*(\d+(?:\.\d+)?)\s*cm",
        r"页边距[:：]?\s*上下各\s*(\d+(?:\.\d+)?)\s*cm.*?左右各\s*(\d+(?:\.\d+)?)\s*cm",
    ]
    for pat in margin_patterns:
        m = re.search(pat, text)
        if m:
            groups = m.groups()
            if len(groups) == 4:
                fmt["margin"] = {
                    "top": float(groups[0]), "bottom": float(groups[1]),
                    "left": float(groups[2]), "right": float(groups[3]),
                }
            elif len(groups) == 2:
                fmt["margin"] = {
                    "top": float(groups[0]), "bottom": float(groups[0]),
                    "left": float(groups[1]), "right": float(groups[1]),
                }
            break

    # 编号方式检测
    if re.search(r"一[、，]\s*（一）\s*1\.", text):
        fmt["numbering"] = "chinese_multi_level"
    elif re.search(r"1[、，]\s*1\.1\s*1\.1\.1", text):
        fmt["numbering"] = "arabic_multi_level"
    elif re.search(r"第[一二三四五]章", text):
        fmt["numbering"] = "chapter_style"

    # 目录要求
    if re.search(r"目录|自动生成目录|须有目录|含目录", text):
        fmt["toc"] = True
        m = re.search(r"目录.*?(\d)\s*[-至]\s*(\d)\s*级", text)
        if m:
            fmt["toc_levels"] = f"{m.group(1)}-{m.group(2)}"
        else:
            fmt["toc_levels"] = "1-3"
    else:
        fmt["toc"] = False

    # 页数限制
    m = re.search(r"(?:不超过|最多|限)\s*(\d+)\s*页", text)
    if m:
        fmt["max_pages"] = int(m.group(1))

    return fmt


# ============================================================
# 评分标准提取（LLM）
# ============================================================

def _extract_scoring(text):
    """用 LLM 从招标文件中提取评分标准。

    返回 list of {item, score, sub_items, detail}
    """
    from _cloud_llm import chat, LLM_MODE

    # 截取评分相关段落（减少 token 消耗）
    scoring_section = _find_scoring_section(text)
    if not scoring_section:
        scoring_section = text[:8000]

    system = """你是招标文件分析专家。提取评分标准，输出严格 JSON。
格式要求：
{
  "scoring": [
    {
      "item": "评分项名称",
      "score": 分值(数字),
      "sub_items": [{"name": "子项名", "score": 分值, "detail": "评分细则"}],
      "detail": "该评分项的总体说明"
    }
  ]
}
注意：
- 只提取评分标准部分，不要提取资格要求或废标条款
- 分值必须是数字
- 如果没有子项，sub_items 为空数组"""

    prompt = f"""请从以下招标文件内容中提取评分标准：

{scoring_section[:6000]}

输出 JSON。"""

    result = chat(prompt, system=system, temperature=0.1, max_tokens=4000,
                  json_mode=True, task="bid_parse_scoring")
    if not result:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
            return []
        print("[bid-parse] 评分标准提取失败（LLM 无响应）")
        return []

    try:
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result
        return data.get("scoring", [])
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"[bid-parse] 评分标准解析失败: {e}")
        return []


def _find_scoring_section(text):
    """定位评分标准相关段落，减少 LLM 输入 token。"""
    markers = [
        r"评分标准",
        r"评标办法",
        r"评审办法",
        r"评分细则",
        r"打分标准",
        r"评议标准",
    ]
    for marker in markers:
        idx = text.find(marker)
        if idx >= 0:
            # 从标记位置前后取 8000 字符
            start = max(0, idx - 200)
            end = min(len(text), idx + 8000)
            return text[start:end]
    return None


# ============================================================
# 资质/废标条款提取（正则 + LLM）
# ============================================================

def _extract_qualifications(text):
    """提取资质要求和废标条款。

    正则匹配关键词，LLM 补充结构化。
    """
    # 正则匹配资质关键词
    qual_patterns = [
        r"(?:须|应|必须).{0,10}?(?:具备|拥有|取得|具有).{0,30}?(ISO\d+|CMMI\s?\d|CCRC|ITSS|CS\d|涉密|保密|安全)",
        r"(?:资质|资格|证书).{0,20}?(ISO\d+|CMMI\s?\d|CCRC|ITSS)",
        r"(ISO\d+|CMMI\s?\d|CCRC|ITSS|CS\d级?|涉密集成)",
    ]
    found = set()
    for pat in qual_patterns:
        for m in re.finditer(pat, text):
            qual = m.group(1).replace(" ", "").replace("\t", "")
            found.add(qual)

    # 正则匹配废标条款关键词
    disqual_patterns = [
        r"废标.{0,200}",
        r"否决.{0,200}",
        r"无效投标.{0,200}",
        r"(?:不|未).{0,10}?(?:符合|满足|响应).{0,30}?(?:废标|否决|无效)",
    ]
    disqual_texts = []
    for pat in disqual_patterns:
        for m in re.finditer(pat, text):
            snippet = m.group(0).strip()[:200]
            if snippet not in disqual_texts:
                disqual_texts.append(snippet)

    # LLM 补充：结构化废标条款
    must_mention = list(found)
    disqual_items = []

    if disqual_texts:
        from _cloud_llm import chat, LLM_MODE
        joined = "\n".join(disqual_texts[:10])
        system = """你是招投标专家。从以下废标条款片段中提取关键要求，输出 JSON。
格式：{"items": ["要求1", "要求2", ...]}"""

        result = chat(f"废标条款片段：\n{joined}", system=system,
                      temperature=0.1, max_tokens=2000, json_mode=True,
                      task="bid_parse_disqual")
        if result:
            try:
                if isinstance(result, str):
                    data = json.loads(result)
                else:
                    data = result
                disqual_items = data.get("items", [])
            except (json.JSONDecodeError, AttributeError):
                pass
        elif LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")

    return {
        "must_mention": must_mention,
        "disqualify_rules": disqual_items,
    }


# ============================================================
# 技术标/商务标拆分
# ============================================================

def _split_tech_commercial(scoring, text):
    """将评分项拆分为技术标和商务标。

    判断依据：
    - 技术标：技术方案、实施方案、售后、团队、架构等
    - 商务标：报价、资质、业绩、财务等
    """
    tech_keywords = ["技术", "方案", "实施", "售后", "运维", "团队",
                     "架构", "安全", "功能", "性能", "项目管理", "培训"]
    commercial_keywords = ["报价", "价格", "资质", "业绩", "财务",
                          "商务", "信誉", "资格", "证书", "营业执照"]

    tech_scoring = []
    commercial_scoring = []

    for item in scoring:
        name = item.get("item", "")
        if any(kw in name for kw in commercial_keywords):
            commercial_scoring.append(item)
        elif any(kw in name for kw in tech_keywords):
            tech_scoring.append(item)
        else:
            # 无法分类的默认归技术标
            tech_scoring.append(item)

    return tech_scoring, commercial_scoring


def _detect_bid_type(text):
    """检测标书类型：split（拆分）/ single（一体）。"""
    split_markers = ["技术标", "商务标", "技术部分", "商务部分",
                     "技术文件", "商务文件", "技术标段", "商务标段"]
    count = 0
    for marker in split_markers:
        if marker in text:
            count += 1
    return "split" if count >= 2 else "single"


# ============================================================
# 主函数
# ============================================================

def parse_tender(file_path, client_name="", do_split=True):
    """解析招标文件，返回 bid_criteria dict。

    Args:
        file_path: 招标文件路径
        client_name: 客户名（用于输出路径）
        do_split: 是否拆分技术标/商务标

    Returns:
        bid_criteria dict
    """
    print("=== 招标文件解析 ===")
    print(f"文件: {file_path}")
    print(f"客户: {client_name or '(未指定)'}")

    # 1. 读取文件
    print("\n[1/4] 读取招标文件...")
    text = _read_tender(file_path)
    print(f"  文本长度: {len(text)} 字符")

    # 2. 提取格式要求（纯正则）
    print("[2/4] 提取格式要求（正则匹配）...")
    fmt = _extract_format_requirements(text)
    _print_format_summary(fmt)

    # 3. 提取评分标准（LLM）
    print("\n[3/4] 提取评分标准（LLM）...")
    scoring = _extract_scoring(text)
    print(f"  评分项: {len(scoring)} 个")
    total_score = sum(s.get("score", 0) for s in scoring)
    print(f"  总分: {total_score}")

    # 4. 提取资质/废标条款
    print("\n[4/4] 提取资质/废标条款...")
    quals = _extract_qualifications(text)
    print(f"  资质要求: {quals['must_mention']}")
    print(f"  废标条款: {len(quals['disqualify_rules'])} 条")

    # 组装结果
    bid_type = _detect_bid_type(text) if do_split else "single"

    result = {
        "bid_type": bid_type,
        "source_file": os.path.basename(file_path),
        "client": client_name,
        "format_requirements": fmt,
        "scoring": scoring,
        "qualifications": quals,
    }

    # 拆分技术标/商务标
    if bid_type == "split" and do_split:
        tech_scoring, commercial_scoring = _split_tech_commercial(scoring, text)
        result["tech_spec"] = {
            "scoring": tech_scoring,
            "format_requirements": {**fmt, "dark_bid": fmt.get("dark_bid", False)},
            "variable_sections": [s["item"] for s in tech_scoring],
            "must_mention": quals["must_mention"],
        }
        result["commercial_spec"] = {
            "scoring": commercial_scoring,
            "format_requirements": {**fmt, "dark_bid": False},
            "fixed_sections": ["公司简介", "营业执照", "资质证书"],
            "variable_sections": [s["item"] for s in commercial_scoring],
        }
        print("\n拆分结果:")
        print(f"  技术标: {len(tech_scoring)} 评分项, 总分 {sum(s.get('score', 0) for s in tech_scoring)}")
        print(f"  商务标: {len(commercial_scoring)} 评分项, 总分 {sum(s.get('score', 0) for s in commercial_scoring)}")

    return result


def save_bid_criteria(criteria, client_name=""):
    """保存 bid_criteria.json 到 output/{客户}/ 目录。"""
    if client_name:
        output_dir = os.path.join(SCRIPT_DIR, "output", client_name)
    else:
        output_dir = os.path.join(SCRIPT_DIR, "output", "通用")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "bid_criteria.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(criteria, f, ensure_ascii=False, indent=2)

    print(f"\n已保存: {output_path}")
    return output_path


def _print_format_summary(fmt):
    """打印格式要求摘要。"""
    parts = []
    if fmt["dark_bid"]:
        parts.append("暗标")
    if fmt["body_font"]:
        parts.append(f"正文:{fmt['body_font']}")
    if fmt["body_size"]:
        parts.append(f"字号:{fmt['body_size']}")
    if fmt["line_spacing"]:
        parts.append(f"行距:{fmt['line_spacing']}磅")
    if fmt["numbering"]:
        parts.append(f"编号:{fmt['numbering']}")
    if fmt["toc"]:
        parts.append(f"目录({fmt.get('toc_levels', '1-3')}级)")
    if fmt["max_pages"]:
        parts.append(f"限{fmt['max_pages']}页")

    margin = fmt["margin"]
    if margin.get("top"):
        parts.append(f"页边距:上{margin['top']}/下{margin['bottom']}/左{margin['left']}/右{margin['right']}cm")

    if parts:
        print(f"  {' | '.join(parts)}")
    else:
        print("  (未检测到明确格式要求，将使用默认值)")
