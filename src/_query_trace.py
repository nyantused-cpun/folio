# -*- coding: utf-8 -*-
"""query_trace 全链路查询日志（T7）。

每次召回查询写一行 JSONL，落盘 _knowledge/.cache/query_trace.jsonl。
一期只负责可靠落盘，不做统计界面。
"""
import json
import os
import time

from _paths import SCRIPT_DIR

QUERY_TRACE_PATH = os.path.join(SCRIPT_DIR, "_knowledge", ".cache", "query_trace.jsonl")


def write_query_trace(entry):
    """追加一条查询 trace。entry 为 dict，自动补 ts。失败不阻断召回。"""
    try:
        os.makedirs(os.path.dirname(QUERY_TRACE_PATH), exist_ok=True)
        record = dict(entry or {})
        record["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(QUERY_TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_query_trace(limit=None):
    """读取 query_trace；文件不存在返回 []。limit 限制返回最近 N 条。"""
    if not os.path.exists(QUERY_TRACE_PATH):
        return []
    records = []
    try:
        with open(QUERY_TRACE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    if limit is not None and limit > 0:
        return records[-limit:]
    return records