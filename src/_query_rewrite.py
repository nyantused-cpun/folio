# -*- coding: utf-8 -*-
"""查询改写模块（T2）。

输入原查询 + 客户/日期/决策摘要，调用便宜档 chat 模型输出：
  - rewritten: 改写后的查询
  - changes[]: 逐项改动说明
  - confidence: 0~1 自评置信度

失败/超时/解析失败均回退原查询，并带 degraded 标记，保证召回链路不中断。
"""
import os

from _paths import SCRIPT_DIR
from _cloud_llm import chat, _parse_json

REWRITE_SYSTEM = (
    "你是售前知识库检索查询改写器。只输出 JSON，不要输出额外文字。"
    "JSON 格式：{\"rewritten\": \"改写后的查询\", \"changes\": [\"改动说明\"], \"confidence\": 0.0}"
)

REWRITE_PROMPT = """请根据客户上下文改写下面的检索查询，使其更可能命中知识库中的客户材料。

客户：{client}
当前日期：{current_date}
决策摘要：{decisions}

原查询：{query}

改写原则：
- 补全指代（如“他们/这个项目”换成客户名/具体对象）
- 补充同义词/别名，但不改变原意
- 不要臆造知识库中不存在的细节
- 若原查询已经清晰，可原样返回（changes 为空数组）
- confidence 表示“改写后查询比原查询更可能召回”的置信度，0~1
"""


def _load_config():
    """读取 recall_config.yml 的 query_rewrite 节；缺失/损坏返回默认。"""
    defaults = {"enabled": True, "confidence_threshold": 0.6}
    try:
        import yaml
        path = os.path.join(SCRIPT_DIR, "recall_config.yml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        section = data.get("query_rewrite", {}) or {}
        merged = dict(defaults)
        merged.update(section)
        return merged
    except Exception:
        return defaults


def _fallback(input_text, degraded):
    return {
        "rewritten": input_text,
        "changes": [],
        "confidence": 1.0,
        "degraded": degraded,
    }


def _build_prompt(input_text, client=None, current_date=None, decisions=None):
    return REWRITE_PROMPT.format(
        client=client or "未指定",
        current_date=current_date or "未知",
        decisions=(decisions or "")[:2000] or "无",
        query=input_text,
    )


def rewrite_query(input_text, client=None, current_date=None, decisions=None,
                  config=None):
    """查询改写入口。始终返回 dict，失败不抛异常。"""
    cfg = config if config is not None else _load_config()
    if not cfg.get("enabled", True):
        return _fallback(input_text, ["REWRITE_DISABLED"])

    try:
        raw = chat(
            _build_prompt(input_text, client, current_date, decisions),
            system=REWRITE_SYSTEM,
            json_mode=True,
            task="query_rewrite",
            temperature=0.1,
            max_tokens=500,
        )
        if not raw:
            return _fallback(input_text, ["REWRITE_FALLBACK"])

        data = _parse_json(raw) or {}
        rewritten = str(data.get("rewritten") or "").strip()
        if not rewritten:
            return _fallback(input_text, ["REWRITE_EMPTY"])

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        changes = data.get("changes") if isinstance(data.get("changes"), list) else []
        return {
            "rewritten": rewritten,
            "changes": changes,
            "confidence": confidence,
            "degraded": [],
        }
    except Exception:
        return _fallback(input_text, ["REWRITE_FALLBACK"])