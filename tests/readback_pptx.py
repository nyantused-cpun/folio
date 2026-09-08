# -*- coding: utf-8 -*-
"""pptx 读回核对：逐页 shape 计数 + 首个文本（工程冒烟工具）。

用法：.venv/Scripts/python.exe tests/readback_pptx.py <pptx路径>
"""
import sys

from pptx import Presentation


def main(path):
    p = Presentation(path)
    empty = []
    for i, s in enumerate(p.slides, 1):
        texts = [sh.text_frame.text.replace("\n", " ")[:24]
                 for sh in s.shapes
                 if sh.has_text_frame and sh.text_frame.text.strip()]
        n = len(s.shapes)
        first = texts[0] if texts else "(无文本)"
        print(f"{i:02d} shapes={n:3d} | {first}")
        if n == 0:
            empty.append(i)
    print(f"\n总页数: {len(p.slides.__iter__.__self__._sldIdLst)}  空页: {empty or '无'}")


if __name__ == "__main__":
    main(sys.argv[1])
