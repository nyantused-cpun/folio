# -*- coding: utf-8 -*-
"""检查 v2 工程剩余警告涉及元素的 shapeName/elementType，验证豁免为何没生效。"""
import glob
import os
import sys

import yaml


def main(root):
    for p in sorted(glob.glob(os.path.join(root, "pages", "*.page"))):
        page = yaml.safe_load(open(p, encoding="utf-8"))
        els = page.get("elements", [])
        # 目标 id 段
        targets = ["ar-1-2-r0", "ar-1-4-r0", "ar-2-3-r0", "ar-1-4-r2",
                   "ar-0-1", "ar-2-3-r2", "ar-0-3-r2", "nd-1", "nd-3",
                   "nd-4", "nd-2"]
        hits = [e for e in els if any(t in str(e.get("elementId", "")) for t in targets)]
        if hits:
            print(f"== {os.path.basename(p)} ==")
            for e in hits:
                print(f"  {e.get('elementId'):22s} type={e.get('elementType'):9s} "
                      f"shape={e.get('shapeName','-')} bounds={e.get('bounds')}")
            print()


if __name__ == "__main__":
    main(sys.argv[1])
