# -*- coding: utf-8 -*-
"""分析 pptd 工程中 overlap 警告对的真实坐标，区分真穿/边缘贴合/设计性。"""
import glob
import os
import sys

import yaml


def main(root):
    pages = {}
    for p in glob.glob(os.path.join(root, "pages", "*.page")):
        pages[os.path.basename(p)] = yaml.safe_load(open(p, encoding="utf-8"))

    pairs = {
        "03_p02": [("ar-2-3-r0", "nd-4"), ("ar-1-4", "nd-1"), ("ar-1-4", "nd-2"),
                   ("ar-1-4", "nd-3"), ("ar-1-4", "nd-3-t")],
        "10_p09": [("ar-0-1", "ar-1-2-r0"), ("ar-1-2-r0", "nd-1"), ("ar-2-3-r2", "nd-1")],
        "11_p10": [("ar-0-3-r2", "nd-3"), ("ar-2-3-r0", "nd-2")],
        "14_p13": [("hub-l-CRM", "hub-t")],
        "16_p15": [("dep-z-云端-sep", "dep-lnk-l-0"), ("dep-lnk-0", "dep-z-云端-n0-i"),
                   ("dep-lnk-0", "dep-z-本地-n0-i")],
        "18_p17": [("mg-g0-c0-0", "mg-g0-ct0-0"), ("mg-g0-c1-0", "mg-g0-ct1-0"),
                   ("mg-g1-c2-0", "mg-g1-ct2-0")],
        "24_p23": [("er0-w1", "er0-lt")],
        "35_p34": [("msg-dep1-0", "msg-b0-t"), ("msg-dep1-0", "msg-b1-t")],
    }
    for page, pids in pairs.items():
        elems = {}
        for e in pages[f"{page}.page"].get("elements", []):
            eid = str(e.get("elementId", ""))
            elems[eid] = e
            stem = eid.split("-", 1)[1] if eid.startswith("dg") else eid
            elems.setdefault(stem, e)
        print(f"== {page} ==")
        for a, b in pids:
            ea, eb = elems.get(a), elems.get(b)
            if not ea or not eb:
                print(f"  MISS {a}/{b}")
                continue
            ba, bb = ea["bounds"], eb["bounds"]
            inter = (min(ba[0] + ba[2], bb[0] + bb[2]) - max(ba[0], bb[0]),
                     min(ba[1] + ba[3], bb[1] + bb[3]) - max(ba[1], bb[1]))
            print(f"  {a:18s} [{ba[0]:6.1f},{ba[1]:6.1f},{ba[2]:6.1f}x{ba[3]:6.1f}] {ea.get('elementType'):9s}")
            print(f"    x {b:18s} [{bb[0]:6.1f},{bb[1]:6.1f},{bb[2]:6.1f}x{bb[3]:6.1f}] {eb.get('elementType'):9s}"
                  f"  inter={inter[0]:.1f}x{inter[1]:.1f}")


if __name__ == "__main__":
    main(sys.argv[1])
