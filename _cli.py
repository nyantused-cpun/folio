# -*- coding: utf-8 -*-
"""发布版 CLI 薄转发入口：实现与依赖都在 src/ 下。

为什么保留根级 _cli.py：
  - skills 与文档统一写 `python _cli.py <命令>`（内部/发布版同一口径）；
  - DSH 插件（folio-tools / folio-events / guard）向上查找 `_cli.py` 定位仓库根；
  - guard 的 CLI 白名单只放行 `python.exe _cli.py ...`。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import runpy

runpy.run_path(os.path.join(_SRC, "_cli.py"), run_name="__main__")
