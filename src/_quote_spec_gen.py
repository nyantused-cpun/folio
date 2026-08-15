# -*- coding: utf-8 -*-
"""从客户材料 LLM 提取报价 spec.yml。"""
import os
import yaml
from _cloud_llm import chat, _parse_json, LLM_MODE
from _pipeline import read_batch
from _outline_to_spec import _recall_evidence

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

QUOTE_EXTRACT_SYSTEM = """你是报价需求提取助手。从客户材料中提取报价相关需求，输出 JSON。
规则：
1. 只提取材料中明确提到的模块/服务/许可需求
2. 模块 id 按内容库格式（如 4.1.1），无法确定时留空
3. 折扣字段：材料明确提及才填，否则留空
4. 严格 JSON，不要解释"""


def gen_quote_spec(materials_dir, client_name="", output_path="quote_spec.yml"):
    # §八 3.5：报价 spec 写入过 output/ 白名单，入口前置校验，
    # 避免材料读取 + LLM 提取完才在写入点抛异常
    from _renderer import _validate_output_path
    _validate_output_path(output_path)

    if not os.path.isdir(materials_dir):
        print(f"错误：材料目录不存在: {materials_dir}")
        return None

    paths = [os.path.join(materials_dir, f) for f in os.listdir(materials_dir)
             if not f.startswith(".")]
    print(f"并行读取 {len(paths)} 个材料文件...")
    results = read_batch(paths, max_workers=4)
    materials_text = "\n\n---\n\n".join(s for _, s, _ in results if s)
    if not materials_text.strip():
        print("错误：材料为空（目录无文件或全部读取失败），无法生成报价 spec")
        return None

    # P1 优化（2026-07-20）：接入证据召回替代全量材料前 1 万字符
    # 与 spec 生成环节一致，按报价关键词召回证据，不足时 fallback 全量材料前 4000 字符
    evidence_block = ""
    evidence_text_for_prompt = ""
    if client_name:
        # 报价场景通用 query：召回所有报价相关证据
        query = "报价 模块 许可 实施 付款 折扣"
        evidence_chunks = _recall_evidence(query, client_name, top_k=5)
        if evidence_chunks:
            lines = []
            for i, ev in enumerate(evidence_chunks, 1):
                lines.append(f"[证据{i}] 来源：{ev.get('source', '?')}\n内容：{ev.get('snippet', '')}")
            evidence_block = "\n【语义召回证据（主要参考）】\n" + "\n\n".join(lines) + "\n"
            evidence_text_for_prompt = "\n".join(ev.get("snippet", "") for ev in evidence_chunks)
            print(f"  -> 召回 {len(evidence_chunks)} 条证据")

    # Fallback：evidence 不足时用全量材料前 4000 字符
    materials_fallback = ""
    if len(evidence_text_for_prompt) < 1500:
        materials_fallback = f"\n【客户材料（evidence 不足，前 4000 字符）】\n{materials_text[:4000]}\n"
        evidence_text_for_prompt = materials_text[:4000]
        if not evidence_block:
            print("  -> evidence 不足，fallback 到全量材料前 4000 字符")

    prompt = f"""【客户】{client_name or "(未指定)"}
{evidence_block}{materials_fallback}
---

【本任务】
请提取报价需求，输出 JSON：
{{
  "client": "{client_name}",
  "payment_terms": "材料中提及的付款条件，未提及则留空",
  "valid_until": "材料中提及的有效期，未提及则留空",
  "sheets": [{{
    "ref": "主报价",
    "sections": [
      {{"id": "modules", "items": [{{"id": "", "name": "材料提及的模块名", "quantity": 1, "discount": ""}}]}},
      {{"id": "implementation", "items": [{{"name": "材料提及的实施服务", "quantity": 1}}]}},
      {{"id": "user_license", "items": [{{"name": "材料提及的许可需求", "quantity": 1}}]}}
    ]
  }}]
}}"""

    resp = chat(prompt, system=QUOTE_EXTRACT_SYSTEM,
                temperature=0.0, json_mode=True, task="quote_spec_extract", max_tokens=4000)
    if not resp:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        else:
            print("LLM 调用失败")
        return None
    data = _parse_json(resp)
    if not data:
        print(f"JSON 解析失败: {resp[:200]}")
        return None

    if client_name:
        data["client"] = client_name

    # 草稿默认未确认，人工检查后改 confirmed: true 才允许 quote-build
    data.setdefault("confirmed", False)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"报价 spec 已生成: {output_path}")
    print(f"下一步: python _cli.py quote-build {output_path} --format all 报价输出")
    return output_path
