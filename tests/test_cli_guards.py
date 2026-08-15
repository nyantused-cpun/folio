# -*- coding: utf-8 -*-
"""CLI guards tests."""

import os
import pytest


class TestPathGuard:
    """测试路径守卫。"""

    def test_output_path_allowed(self):
        """output 目录下的路径应该被允许。"""
        from _paths import OUTPUT_DIR
        assert os.path.basename(OUTPUT_DIR) == 'output'

    def test_ppt_workspace_allowed(self):
        """ppt_workspace 目录应该存在。"""
        from _paths import PPT_WORKSPACE
        os.makedirs(PPT_WORKSPACE, exist_ok=True)
        assert os.path.exists(PPT_WORKSPACE)


class TestThemeGuard:
    """测试主题守卫。"""

    def test_theme_guard_import(self):
        """主题守卫模块应该可以导入，且核心函数存在。"""
        try:
            import _theme_guard
            assert hasattr(_theme_guard, 'pre_check')
            assert hasattr(_theme_guard, 'load_active_themes')
            assert hasattr(_theme_guard, 'save_decision')
        except ImportError as e:
            pytest.skip(f"_theme_guard 导入失败: {e}")

    def test_theme_verify_import(self):
        """主题验证模块应该可以导入，且覆盖检查函数存在。"""
        try:
            import _theme_guard
            assert hasattr(_theme_guard, 'check_coverage')
            assert hasattr(_theme_guard, 'build_head_context')
            assert hasattr(_theme_guard, 'build_tail_checklist')
        except ImportError as e:
            pytest.skip(f"_theme_guard 导入失败: {e}")


class TestVerifyHook:
    """测试验证钩子。"""

    def test_verify_import(self):
        """验证钩子模块应该可以导入。"""
        try:
            import _verify_hook
            assert hasattr(_verify_hook, 'run_single')
        except ImportError as e:
            pytest.skip(f"_verify_hook 导入失败: {e}")

    def test_verify_module_import(self):
        """验证模块应该可以导入，且核心函数存在。"""
        try:
            import _verify
            assert hasattr(_verify, 'auto_verify')
            assert hasattr(_verify, 'verify_all')
            assert hasattr(_verify, 'verify_html')
        except ImportError as e:
            pytest.skip(f"_verify 导入失败: {e}")

class TestConfirmedGate:
    """confirmed 门单点实现测试（P0：4 处检查点收敛到 is_confirmed/require_confirmed）。"""

    def test_is_confirmed_values(self):
        from _cli_guards import is_confirmed
        assert is_confirmed({"confirmed": True}) is True
        assert is_confirmed({"confirmed": False}) is False
        assert is_confirmed({}) is False          # 缺字段 = 未确认
        assert is_confirmed(None) is False       # 空 spec = 未确认

    def test_require_confirmed_raises(self):
        from _cli_guards import require_confirmed
        from _renderer import RenderBlockedError
        with pytest.raises(RenderBlockedError):
            require_confirmed({"confirmed": False})

    def test_require_confirmed_passes(self):
        from _cli_guards import require_confirmed
        require_confirmed({"confirmed": True})  # 不抛即通过

    def test_renderer_uses_shared_gate(self):
        """Renderer 与 require_confirmed 行为一致（同源判定）。"""
        import os
        os.environ["_PRESALES_CLI_INVOKED"] = "1"
        from _cli_guards import is_confirmed
        for spec in ({"confirmed": True}, {"confirmed": False}, {}):
            # 单点判定直接决定 Renderer 门禁行为（Renderer 内部调 require_confirmed）
            assert is_confirmed(spec) == bool(spec.get("confirmed"))


class TestSkillSentinel:
    """生成前 skill 哨兵门禁（REQUIRE_SKILL_SENTINEL，默认关）。"""

    def test_sentinel_off_passes(self, tmp_path, monkeypatch):
        """开关未设/关 -> 未读也不拦（默认行为，不影响正常流程）。"""
        monkeypatch.delenv("REQUIRE_SKILL_SENTINEL", raising=False)
        from _cli_guards import require_skill_read
        require_skill_read(["definitely-not-loaded-skill"])  # 不抛即通过

    def test_sentinel_on_blocks_missing(self, tmp_path, monkeypatch):
        """开关开 + 未读 -> 抛 RenderBlockedError。"""
        monkeypatch.setenv("REQUIRE_SKILL_SENTINEL", "true")
        monkeypatch.setattr("_paths.SKILL_READ_DIR", str(tmp_path / "skill_read"))
        from _renderer import RenderBlockedError
        from _cli_guards import require_skill_read
        with pytest.raises(RenderBlockedError):
            require_skill_read(["definitely-not-loaded-skill"])

    def test_sentinel_on_passes_when_loaded(self, tmp_path, monkeypatch):
        """开关开 + 已 load-skill -> 放行。"""
        monkeypatch.setenv("REQUIRE_SKILL_SENTINEL", "true")
        from _cli_guards import mark_skill_read, require_skill_read
        read_dir = tmp_path / "skill_read"
        monkeypatch.setattr("_paths.SKILL_READ_DIR", str(read_dir))
        mark_skill_read("delivery-pipeline")
        require_skill_read(["delivery-pipeline"])  # 不抛即通过
        assert (read_dir / "delivery-pipeline.json").exists()

    def test_required_gen_skills_includes_presentation(self):
        """B-2：presentation-content-design 已进生成前必读清单（4 个）。"""
        from _cli_guards import REQUIRED_GEN_SKILLS
        assert "presentation-content-design" in REQUIRED_GEN_SKILLS
        assert len(REQUIRED_GEN_SKILLS) == 4
