# -*- coding: utf-8 -*-
"""事实一致性校验器（T5）一期最小可用版。

提供：
- normalize_num()：中文数字/百分比/日期归一化
- load_whitelist()：从 aliases.yml + methodology 词构建实体白名单
- guard_check()：抽取数字与实体，预留 violations 结构
- 隔离区队列：enqueue_guard_item / list_guard_queue（供后续 guard-audit --queue）

一期不做 enriched/expert 自动改写，只做可审计校验与队列入口。
"""
import json
import os
import re

from _paths import SCRIPT_DIR

GUARD_QUEUE_PATH = os.path.join(SCRIPT_DIR, "_knowledge", ".cache", "guard_queue.jsonl")

_CN_DIGITS = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
              "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}


def _cn_to_arabic(text):
    """把中文数字片段转阿拉伯数字；解析失败返回原文本。"""
    if not text:
        return text
    total = 0
    section = 0
    num = 0
    for ch in text:
        if ch in _CN_DIGITS:
            num = int(_CN_DIGITS[ch])
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if unit >= 10000:
                # 万/亿 是节单位：整体乘入当前节。万先不落总账——「一万亿」
                # 里亿要把「一万」整个乘进去（旧版把万先落总账，亿乘到 0，
                # 一万亿被算成 10000，应 1e12）
                section = (section + num) * unit
                if unit > 10000:
                    # 亿：节完结，落总账
                    total += section
                    section = 0
            else:
                section += (num if num else 1) * unit
            num = 0
        else:
            return text
    total += section + num
    return str(total) if total or text == "零" else text


def normalize_num(text):
    """归一化数字表达：中文数字→阿拉伯、百分之X→X%、日期→YYYY-MM-DD。"""
    if not text:
        return text
    s = text.strip().replace("％", "%")

    # 中文百分比：百分之五十 -> 50%
    m = re.fullmatch(r"百分之([零一二三四五六七八九十百千万亿两]+)", s)
    if m:
        return _cn_to_arabic(m.group(1)) + "%"

    # 日期：2026年9月1日 / 2026年09月01日
    m = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 纯中文数字
    if re.fullmatch(r"[零一二三四五六七八九十百千万亿两]+", s):
        return _cn_to_arabic(s)

    return s


def load_whitelist(client=None):
    """从客户 aliases + 少量方法论词构建实体白名单。"""
    whitelist = set()
    try:
        if client:
            from _aliases import load_client
            aliases = load_client(client) or {}
            for key, vals in aliases.items():
                if isinstance(key, str):
                    whitelist.add(key)
                if isinstance(vals, list):
                    whitelist.update(str(v) for v in vals if isinstance(v, str))
    except Exception:
        pass
    whitelist.update({
        "数据架构", "应用架构", "技术架构", "业务架构", "信息安全",
        "协同办公", "私有化部署", "微服务", "中台", "低代码",
    })
    return whitelist


def guard_check(text, client=None, whitelist=None):
    """抽取文本中的数字与白名单实体，返回结构化结果。

    一期只做可审计提取，不阻断生成；violations 预留后续 enriched/expert 规则。
    """
    whitelist = load_whitelist(client) if whitelist is None else whitelist
    text = text or ""

    numbers = re.findall(r"\d+(?:\.\d+)?(?:%|％)?", text)
    pct_numbers = re.findall(r"百分之[零一二三四五六七八九十百千万亿两]+", text)
    # P3：先把「百分之X」整体摘掉再扫裸中文数字（X 已由 pct_numbers 覆盖）。
    # 旧 lookbehind 只挡住 X 的匹配起点，「百分之五十」仍会漏出幽灵「百」
    # （被当独立数字抽出 100）与尾字「十」；替换为空格防相邻中文数字串粘连。
    text_wo_pct = re.sub(r"百分之[零一二三四五六七八九十百千万亿两]+", " ", text)
    cn_numbers = re.findall(
        r"(?<!百分之)[零一二三四五六七八九十百千万亿两]+(?:%|％)?", text_wo_pct)
    normalized = [normalize_num(n) for n in numbers + pct_numbers + cn_numbers]

    entities = sorted({w for w in whitelist if w and w in text})

    return {
        "numbers": numbers,
        "normalized_numbers": normalized,
        "entities": entities,
        "violations": [],
    }


def enqueue_guard_item(item):
    """写入隔离区队列（JSONL）。失败不抛异常。"""
    try:
        os.makedirs(os.path.dirname(GUARD_QUEUE_PATH), exist_ok=True)
        with open(GUARD_QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError:
        pass


def list_guard_queue():
    """读取隔离区队列。文件不存在返回 []。"""
    if not os.path.exists(GUARD_QUEUE_PATH):
        return []
    out = []
    try:
        with open(GUARD_QUEUE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    return out