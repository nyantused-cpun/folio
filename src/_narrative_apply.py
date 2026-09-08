# -*- coding: utf-8 -*-
"""container=chapters 的自动补页逻辑（S1 拆分自 _outline_to_spec.py，条目 2-7）。

职责：_toc_page（P12 目录页）/ _section_page（P02 章节页）/
_apply_chapters_container（按叙事设计单 beat 分组补页 + 目录页判重插入）。
纯函数（print 提示保留原文），不 import 本项目其他模块。
"""

def _toc_page(page_titles):
    """P12 目录页（必需构件：section_tag + action_title + toc_cards）。"""
    return {
        "id": "auto_toc",
        "title": "目录",
        "layout": "P12",
        "elements": [
            {"type": "section_tag", "index": "CONTENTS", "label": "目录"},
            {"type": "action_title", "segments": [{"t": "目录", "hl": ""}]},
            {"type": "toc_cards", "cards": [
                {"num": f"{i + 1:02d}", "title": t, "desc": ""}
                for i, t in enumerate(page_titles)
            ]},
        ],
    }


def _section_page(beat, index):
    """P02 章节页（必需构件：section_tag + action_title）。"""
    return {
        "id": f"auto_section_{index:02d}",
        "title": beat,
        "layout": "P02",
        "elements": [
            {"type": "section_tag", "index": f"SECTION {index:02d}", "label": beat},
            {"type": "action_title", "segments": [{"t": beat, "hl": ""}]},
        ],
    }


def _apply_chapters_container(pages, page_map=None):
    """container=chapters 的自动补页（条目 2-7，D-a=A）。

    - 补 P12 目录页：紧跟封面 P01 之后（无封面则插到最前并提示）；
      toc_cards 由内容页 title 生成（排除封面/章节页/目录页自身）。
    - 有设计单时按 page_map 的 beat 分组，在 beat 切换处补 P02 章节页
      （封面 P01 所在的 beat 不补，封面即开场）；无设计单时章节边界
      无来源，不强补 P02，打印说明。
    - 已存在 P12/P02 的页（按 layout 判重）则不重复补。
    """
    pages = list(pages)

    # P02 章节页先插（beat 切换处），目录卡生成时按 layout 排除
    if not any(p.get("layout") == "P02" for p in pages):
        if page_map:
            augmented = []
            prev_beat = None
            beat_idx = 0
            for i, page in enumerate(pages):
                beat = page_map[i].get("beat", "") if i < len(page_map) else ""
                if beat and beat != prev_beat and page.get("layout") != "P01":
                    beat_idx += 1
                    augmented.append(_section_page(beat, beat_idx))
                augmented.append(page)
                prev_beat = beat
            if beat_idx:
                print(f"  [chapters] 按叙事设计单 beat 分组补 {beat_idx} 页 P02 章节页")
            pages = augmented
        else:
            print("  [chapters] 无叙事设计单，章节边界无来源，不自动补 P02 章节页")

    # P12 目录页
    if not any(p.get("layout") == "P12" for p in pages):
        toc_titles = [p["title"] for p in pages
                      if p.get("layout") not in ("P01", "P02") and p.get("title")]
        cover_idx = next((i for i, p in enumerate(pages)
                          if p.get("layout") == "P01"), None)
        insert_at = cover_idx + 1 if cover_idx is not None else 0
        if cover_idx is None:
            print("  [chapters] 未找到 P01 封面页，P12 目录页插到最前")
        pages.insert(insert_at, _toc_page(toc_titles))
        print(f"  [chapters] 补 P12 目录页（{len(toc_titles)} 张目录卡，"
              f"插入位置 pages[{insert_at}]）")
    return pages
