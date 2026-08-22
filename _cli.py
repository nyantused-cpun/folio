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

if __name__ == "__main__":
    # 以脚本方式运行（python _cli.py <命令>）：转发到 src/_cli.py 并执行 main()。
    runpy.run_path(os.path.join(_SRC, "_cli.py"), run_name="__main__")
else:
    # 被 import（如测试 `from _cli import cmd_*`）时不得执行 main()：
    # src/_cli.py 的 `if __name__ == "__main__": main()` 仅在 run_name 为
    # "__main__" 时触发，这里用普通 run_name 加载模块体，再把公开 API
    # （cmd_* 等）暴露到本模块命名空间，测试可安全引用而不解析 sys.argv。
    _impl = runpy.run_path(os.path.join(_SRC, "_cli.py"), run_name="_cli")
    globals().update({_k: _v for _k, _v in _impl.items() if not _k.startswith("__")})
