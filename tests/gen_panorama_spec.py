# -*- coding: utf-8 -*-
"""全景验收 spec 生成：schema 全部 diagram 子类型每页一种（工程冒烟工具）。

用法：
    .venv/Scripts/python.exe tests/gen_panorama_spec.py
生成 output/通用/图形全景验收_v0.spec.yml，供 html-build --pptd 双端冒烟。

覆盖面与 _renderer.schema.DIAGRAM_SCHEMA 对齐（P2-V1：此前 33 种冒烟面落后
schema 37 种，bar/waterfall/harvey_balls/infra 未进冒烟）；test_b3_gantt_extract
钉死「全景覆盖 = schema 全集」防再漂移。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("_PRESALES_CLI_INVOKED", "1")

import yaml  # noqa: E402

import test_diagram as T  # noqa: E402
import test_flow_rows  # noqa: E402

# milestone_gantt（B-7/D-4）无 test_diagram fixture，结构取自 test_milestone_gantt.py
MILESTONE_GANTT = {
    "type": "diagram", "diagram_type": "timeline",
    "subtype": "milestone_gantt", "title": "路线图",
    "columns": ["W1", "W2", "W3", "W4"],
    "tasks": [{"name": "调研", "start": 0, "span": 2, "deps": [1]},
              {"name": "设计", "start": 1, "span": 2}],
}

# infra（v1.4）同样无模块级 fixture，结构对齐 test_diagram.py 内联用例
INFRA = {
    "type": "diagram", "diagram_type": "architecture",
    "subtype": "infra", "title": "部署拓扑",
    "zones": [{"name": "DMZ", "nodes": [{"name": "防火墙", "icon": "firewall"}]},
              {"name": "核心内网", "nodes": [{"name": "ERP", "icon": "app"},
                                             {"name": "数据库", "icon": "db"}]}],
    "links": [{"from": "DMZ.防火墙", "to": "核心内网.ERP"}],
}

EXTRA = [
    ("flow/flow_rows", test_flow_rows._elem()),
    ("timeline/milestone_gantt", MILESTONE_GANTT),
    # P2-V1 补录四种（harvey/bar/waterfall 复用 test_diagram 既有 fixture）
    ("matrix/harvey_balls", T._harvey()),
    ("chart/bar", T._bar()),
    ("chart/waterfall", T._waterfall()),
    ("architecture/infra", INFRA),
]


def build_pages():
    pages = []
    for i, make in enumerate(T.ALL_P0 + T.ALL_P1, 1):
        elem = make()
        pages.append({
            "id": f"p{i:02d}",
            "title": f"{i:02d} · {elem['diagram_type']}/{elem['subtype']}",
            "elements": [elem],
        })
    j = len(pages)
    for tag, elem in EXTRA:
        j += 1
        pages.append({
            "id": f"p{j:02d}",
            "title": f"{j:02d} · {tag}",
            "elements": [elem],
        })
    return pages


def main():
    pages = build_pages()
    subtypes = sorted({p["elements"][0]["diagram_type"] + "/" + p["elements"][0]["subtype"]
                       for p in pages})
    spec = {
        "project": f"图形全景验收（{len(subtypes)} 子类型）",
        "author": "售前助手",
        "date": "2026-08-15",
        "style": "consulting_kpmg",
        "confirmed": True,
        "document": {
            "title": "图形全景验收",
            "subtitle": f"{len(subtypes)} 种 diagram 子类型 × HTML/PPT 双端冒烟",
        },
        "pages": pages,
    }
    out = os.path.join(ROOT, "output", "通用", "图形全景验收_v0.spec.yml")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False)
    print(f"pages: {len(pages)}  distinct subtypes: {len(subtypes)}")
    print("->", out)


if __name__ == "__main__":
    main()
