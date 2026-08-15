# -*- coding: utf-8 -*-
"""skills-sync：.trae/skills/ -> .agents/skills/ 单向镜像。

只同步含 SKILL.md 的目录；按内容哈希复制新增/变更；--prune 删除多余项。
"""

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
