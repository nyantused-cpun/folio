# -*- coding: utf-8 -*-
"""skills-sync：.folio/skills/ -> .agents/skills/ 单向镜像。

只同步含 SKILL.md 的目录；按内容哈希复制新增/变更；--prune 删除多余项。
"""
import os

import pytest

from _skills_sync import sync_skills


def _mk_skill(base, name, body="# skill\n"):
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


class TestSyncSkills:
    def test_copies_new_skill(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha")
        report = sync_skills(str(src), str(dst))
        assert report["added"] == ["alpha"]
        assert (dst / "alpha" / "SKILL.md").exists()

    def test_updates_changed_skill(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha", body="# v2\n")
        _mk_skill(dst, "alpha", body="# v1\n")
        report = sync_skills(str(src), str(dst))
        assert report["updated"] == ["alpha"]
        assert (dst / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "# v2\n"

    def test_unchanged_is_idempotent(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha")
        sync_skills(str(src), str(dst))
        report = sync_skills(str(src), str(dst))
        assert report["unchanged"] == ["alpha"]
        assert not report["added"] and not report["updated"]

    def test_prune_removes_extras(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha")
        _mk_skill(dst, "stale")
        report = sync_skills(str(src), str(dst), prune=True)
        assert report["pruned"] == ["stale"]
        assert not (dst / "stale").exists()
        # 不加 prune 时保留
        _mk_skill(dst, "stale")
        report = sync_skills(str(src), str(dst))
        assert report["pruned"] == []
        assert (dst / "stale").exists()

    def test_dirs_without_skill_md_skipped(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        (src / "not-a-skill").mkdir(parents=True)
        (src / "not-a-skill" / "readme.txt").write_text("x", encoding="utf-8")
        report = sync_skills(str(src), str(dst))
        assert report["added"] == []
        assert not (dst / "not-a-skill").exists()


class TestSymlinkSkip:
    """D-5：symlink 显式跳过——不参与 added/updated/unchanged/pruned/orphans，
    只计数留痕（report["symlinks_skipped"]），同步不报错。"""

    def _mk_symlink(self, link_path, target):
        """Windows 无权限造 symlink 时跳过（目录链接需开发者模式/管理员）。"""
        try:
            os.symlink(str(target), str(link_path), target_is_directory=True)
        except OSError as e:
            pytest.skip(f"当前环境无法创建目录 symlink: {e}")

    def test_src_symlink_skipped(self, tmp_path):
        src, dst = tmp_path / "src", tmp_path / "dst"
        real = _mk_skill(tmp_path / "elsewhere", "alpha")
        self._mk_symlink(src / "alpha", real)
        report = sync_skills(str(src), str(dst))
        assert report["symlinks_skipped"] == ["alpha"]
        for key in ("added", "updated", "unchanged", "pruned", "orphans"):
            assert report[key] == [], key
        assert not (dst / "alpha").exists()  # 不跟随复制

    def test_dst_symlink_not_overwritten(self, tmp_path):
        """dst 侧 symlink 与 src 真实技能同名：不复制覆盖、不计更新。"""
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha", body="# v2\n")
        dst.mkdir(parents=True)
        real = _mk_skill(tmp_path / "elsewhere", "alpha", body="# 物理在别处\n")
        self._mk_symlink(dst / "alpha", real)
        report = sync_skills(str(src), str(dst))
        assert report["symlinks_skipped"] == ["alpha"]
        assert "alpha" not in report["added"] and "alpha" not in report["updated"]
        # symlink 本体仍在，指向未动
        assert os.path.islink(str(dst / "alpha"))

    def test_dst_symlink_not_pruned_nor_orphan(self, tmp_path):
        """dst 侧 symlink 在事实源没有对应：--prune 不删、不报孤儿。"""
        src, dst = tmp_path / "src", tmp_path / "dst"
        _mk_skill(src, "alpha")
        dst.mkdir(parents=True)
        real = _mk_skill(tmp_path / "elsewhere", "ghost")
        self._mk_symlink(dst / "ghost", real)
        report = sync_skills(str(src), str(dst), prune=True)
        assert report["added"] == ["alpha"]
        assert report["symlinks_skipped"] == ["ghost"]
        assert report["pruned"] == [] and report["orphans"] == []
        assert os.path.islink(str(dst / "ghost"))


class TestRoutingTable:
    """P0-4：路由表自动生成与 overrides。"""

    def _mk_routing_skill(self, base, name, level="optional", triggers=None, negative=""):
        d = base / name
        d.mkdir(parents=True)
        if triggers is None:
            triggers = []
        trig_yaml = "[]" if not triggers else "\n" + "\n".join(f"  - {t!r}" for t in triggers)
        body = (
            "---\n"
            f"name: {name}\n"
            "description: test skill\n"
            f"route_level: {level}\n"
            f"negative: {negative!r}\n"
            f"triggers: {trig_yaml}\n"
            "---\n"
            f"# {name}\n"
        )
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        return d

    def test_scan_and_render_routing_table(self, tmp_path):
        from _skills_sync import (
            scan_skill_routing, render_routing_section,
            _ROUTE_MARKER_BEGIN, _ROUTE_MARKER_END,
        )
        self._mk_routing_skill(tmp_path / "src", "alpha", "mandatory", ["写方案"], "纯检索")
        entries = scan_skill_routing(str(tmp_path / "src"))
        assert entries[0]["route_level"] == "mandatory"
        assert entries[0]["triggers"] == ["写方案"]
        section = render_routing_section(entries)
        assert _ROUTE_MARKER_BEGIN in section
        assert _ROUTE_MARKER_END in section
        assert "`alpha`" in section

    def test_update_routing_table_replaces_generated_region(self, tmp_path):
        from _skills_sync import (
            scan_skill_routing, update_routing_table,
            _ROUTE_MARKER_BEGIN, _ROUTE_MARKER_END,
        )
        src = tmp_path / "src"
        self._mk_routing_skill(src, "alpha", "optional")
        ref = tmp_path / "AGENTS_REFERENCE.md"
        ref.write_text(
            "# Ref\n\n## Skill 路由\n\n"
            + _ROUTE_MARKER_BEGIN + "\n\nold\n\n" + _ROUTE_MARKER_END + "\n",
            encoding="utf-8",
        )
        entries = scan_skill_routing(str(src))
        result = update_routing_table(str(ref), entries)
        assert result == "updated"
        text = ref.read_text(encoding="utf-8")
        assert "`alpha`" in text
        assert "old" not in text

    def test_apply_overrides(self, tmp_path):
        from _skills_sync import apply_route_overrides
        entries = [{
            "name": "alpha",
            "route_level": "excluded",
            "triggers": [],
            "negative": "",
        }]
        out = apply_route_overrides(entries, {
            "force_include": ["alpha"],
            "trigger_alias": [{"skill": "alpha", "triggers": ["新增触发"]}],
        })
        assert out[0]["route_level"] == "optional"
        assert "新增触发" in out[0]["triggers"]
