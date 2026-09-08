# -*- coding: utf-8 -*-
"""DSH 插件 node 自检的 pytest 包装（#53 遗留：probe 缓存修复 + tool-face 触发计数）。

用 subprocess 跑各插件自带的 run-check.mjs，保证 commit-msg 钩子对 fix: 提交的
回归测试要求在纯 Python 侧也可执行。node 不在 PATH 时整体跳过。
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

NODE_CHECKS = [
    REPO_ROOT / ".dsh" / "model-capability-probe" / "test" / "run-check.mjs",
    REPO_ROOT / ".dsh" / "folio-tool-face" / "test" / "run-check.mjs",
]


def _run_node_check(script: Path) -> subprocess.CompletedProcess:
    assert script.exists(), f"自检脚本缺失: {script}"
    return subprocess.run(
        ["node", str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不在 PATH，跳过 DSH 插件自检")
def test_model_capability_probe_run_check():
    r = _run_node_check(NODE_CHECKS[0])
    assert r.returncode == 0, f"model-capability-probe 自检失败:\n{r.stdout}\n{r.stderr}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不在 PATH，跳过 DSH 插件自检")
def test_folio_tool_face_run_check():
    r = _run_node_check(NODE_CHECKS[1])
    assert r.returncode == 0, f"folio-tool-face 自检失败:\n{r.stdout}\n{r.stderr}"


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
