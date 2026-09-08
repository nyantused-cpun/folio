# -*- coding: utf-8 -*-
"""文件体量棘轮闸门（_audit_p0_file_size_ratchet）回归测试。

背景：2026-09-01 待办盘点实测发现扫描范围缺陷——原实现把 `_*.py` 的**文件**
路径收进 roots 后用 `os.path.isdir()` 过滤，导致 62 个根模块全部被跳过，
「非基线 >1200 行 FAIL」规则实际只在 `_renderer/` 生效。

TestRatchetScansRootModules 在旧逻辑下必然失败（缺陷复现），修复后应通过。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch):
    """审计模块沿用 CLI 守门约定。"""
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把棘轮指向一个临时工程根，并清空基线 cap（基线语义另行测试）。"""
    import _cli_audit_p0

    (tmp_path / "_renderer").mkdir()
    monkeypatch.setattr(_cli_audit_p0, "SCRIPT_DIR", str(tmp_path))
    monkeypatch.setattr(_cli_audit_p0, "_RATCHET_CAPS", {})
    return tmp_path


def _write(path, lines):
    path.write_text("# x\n" * lines, encoding="utf-8")


class TestRatchetScansRootModules:
    """缺陷复现：根模块必须真正进入扫描范围。"""

    def test_oversized_root_module_fails_audit(self, sandbox):
        """根目录下 >2000 行的非基线 `_*.py` 必须被判 FAIL。

        旧逻辑（isdir 过滤掉所有文件）会漏检并返回 True。
        """
        import _cli_audit_p0

        _write(sandbox / "_huge_module.py", 2500)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False

    def test_root_module_over_warn_line_fails(self, sandbox):
        """>1200 行的新增根模块同样阻断（棘轮：增量归零）。"""
        import _cli_audit_p0

        _write(sandbox / "_new_module.py", 1300)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False

    def test_normal_root_module_passes(self, sandbox):
        """未超限的根模块不应误报。"""
        import _cli_audit_p0

        _write(sandbox / "_small_module.py", 100)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is True

    def test_non_underscore_root_file_ignored(self, sandbox):
        """根目录只管 `_*.py`（与 CODEBASE_INDEX 根模块口径一致）。"""
        import _cli_audit_p0

        _write(sandbox / "conftest.py", 2500)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is True

    def test_renderer_subdir_still_scanned(self, sandbox):
        """`_renderer/` 扫全部 .py（不限 `_` 前缀），原有行为不得回退。"""
        import _cli_audit_p0

        _write(sandbox / "_renderer" / "bloated.py", 2500)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False


class TestRatchetCoversRendererSubdirs:
    """2026-09-04 盲区回归：子包必须进入扫描（原 listdir 只扫一层，
    `_renderer/diagram/` 整体逃逸——仓库最大两文件 architecture/pptd_emit
    1632/1594 行从未被检，audit 仍打印「无新增超限」）。"""

    def test_diagram_subdir_oversized_fails(self, sandbox):
        """`_renderer/diagram/` 下 >1200 行的非基线文件必须 FAIL。"""
        import _cli_audit_p0

        (sandbox / "_renderer" / "diagram").mkdir(parents=True)
        _write(sandbox / "_renderer" / "diagram" / "oversized.py", 1300)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False

    def test_deeper_nesting_also_scanned(self, sandbox):
        """任意深度的子包都在扫描范围内（os.walk 递归）。"""
        import _cli_audit_p0

        (sandbox / "_renderer" / "deep" / "nested").mkdir(parents=True)
        _write(sandbox / "_renderer" / "deep" / "nested" / "bloated.py", 1300)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False

    def test_subdir_baseline_cap_semantics(self, sandbox):
        """基线挂账语义在子目录同样成立：cap 内放行、超 cap 拦截。"""
        import _cli_audit_p0

        (sandbox / "_renderer" / "diagram").mkdir(parents=True)
        _write(sandbox / "_renderer" / "diagram" / "legacy.py", 1300)
        # cap 内（1300 ≤ 1400）：放行（sandbox fixture 已把 caps 换成空 dict，原地填）
        _cli_audit_p0._RATCHET_CAPS.update({"_renderer/diagram/legacy": 1400})
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is True
        # 超 cap（再写一行都不行）：拦截
        _write(sandbox / "_renderer" / "diagram" / "legacy.py", 1401)
        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False


class TestRatchetBaselineCaps:
    """基线 cap 语义：只许变小。"""

    def test_baseline_file_over_cap_fails(self, tmp_path, monkeypatch):
        import _cli_audit_p0

        (tmp_path / "_renderer").mkdir()
        _write(tmp_path / "_cli.py", 5000)
        monkeypatch.setattr(_cli_audit_p0, "SCRIPT_DIR", str(tmp_path))
        monkeypatch.setattr(_cli_audit_p0, "_RATCHET_CAPS", {"_cli": 1000})

        assert _cli_audit_p0._audit_p0_file_size_ratchet() is False

    def test_baseline_file_within_cap_passes(self, tmp_path, monkeypatch):
        """基线文件在 cap 内即通过，且不受 1200 通用红线影响。"""
        import _cli_audit_p0

        (tmp_path / "_renderer").mkdir()
        _write(tmp_path / "_legacy.py", 1300)
        monkeypatch.setattr(_cli_audit_p0, "SCRIPT_DIR", str(tmp_path))
        monkeypatch.setattr(_cli_audit_p0, "_RATCHET_CAPS", {"_legacy": 1400})

        assert _cli_audit_p0._audit_p0_file_size_ratchet() is True

    def test_caps_match_current_reality(self):
        """cap 必须贴近实际行数——防止拆分成果被无声反弹吃掉。

        规则：cap 不得超过实际行数的 1.35 倍（收紧时留 ~10% 余量，
        此处放宽到 1.35 容纳正常迭代；超出说明 cap 已失去约束力）。
        """
        import _cli_audit_p0

        stale = []
        for key, cap in _cli_audit_p0._RATCHET_CAPS.items():
            path = os.path.join(SCRIPT_DIR, f"{key}.py")
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                actual = sum(1 for _ in f)
            if actual and cap > actual * 1.35:
                stale.append(f"{key}: cap {cap} vs 实际 {actual}")
        assert not stale, f"cap 过松（拆分成果未锁住）: {stale}"


# v2.0 同源对齐（2026-09-08）：依赖主仓工作区契约/内部数据/DSH 插件 npm 面，发布面标记 internal 不随 CI 跑
pytestmark = pytest.mark.internal
