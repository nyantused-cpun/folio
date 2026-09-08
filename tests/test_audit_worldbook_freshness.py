# -*- coding: utf-8 -*-
"""C-A5 回归：世界书新鲜度 mtime 死逻辑修复（0907 计划 W1）。

历史缺陷：_audit_worldbook_freshness 对旧格式（无 front matter）的
client_index.md 先做 hash 比对（全 mismatch 入列），mtime 降级分支只追加
"mtime" 不清空既有 mismatch——旧格式索引恒 WARN，审计信号失真。
修复后：无 front matter 整体回退 mtime 比对；有 front matter 仍走 hash
（真漂移不因 mtime 新而误判新鲜）。
"""

import os

from _cli_audit import _audit_worldbook_freshness
from _worldbook import compute_source_hashes


def _mk_client(tmp_path):
    """造一个可被扫描的客户（decisions.md + outputs_index.json 存在）。"""
    cdir = tmp_path / "测试客户"
    cdir.mkdir(parents=True)
    (cdir / "decisions.md").write_text("## 2026-09-07 测试决策\n", encoding="utf-8")
    (cdir / "outputs_index.json").write_text('{"outputs": []}', encoding="utf-8")
    return cdir


def _set_mtimes(cdir, decisions_ts, oij_ts, index_ts):
    os.utime(cdir / "decisions.md", (decisions_ts, decisions_ts))
    os.utime(cdir / "outputs_index.json", (oij_ts, oij_ts))
    os.utime(cdir / "client_index.md", (index_ts, index_ts))


class TestOldFormatMtimeFallback:
    def test_old_format_fresh_no_warn(self, tmp_path, capsys):
        """旧格式无 front matter + 索引比真源新 → 新鲜，不再恒 WARN（C-A5 主回归）。"""
        cdir = _mk_client(tmp_path)
        (cdir / "client_index.md").write_text("# 世界书\n正文，无 front matter\n", encoding="utf-8")
        _set_mtimes(cdir, 1000000000, 1000000000, 1000000500)
        assert _audit_worldbook_freshness("测试客户", clients_dir=str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "client_index.md 新鲜" in out
        assert "落后于真源" not in out

    def test_old_format_stale_warns_mtime(self, tmp_path, capsys):
        """旧格式 + 索引落后于真源 → WARN（mtime），兜底仍生效。"""
        cdir = _mk_client(tmp_path)
        (cdir / "client_index.md").write_text("# 世界书\n", encoding="utf-8")
        _set_mtimes(cdir, 1000000000, 1000000000, 999999000)
        assert _audit_worldbook_freshness("测试客户", clients_dir=str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "落后于真源 (mtime)" in out


class TestFrontmatterHashPathUnchanged:
    def test_frontmatter_fresh_no_warn(self, tmp_path, capsys):
        """有 front matter 且 hash 一致 → 新鲜（正常路径不受影响）。"""
        cdir = _mk_client(tmp_path)
        hashes = compute_source_hashes(str(cdir))
        fm = "---\n_source_hashes:\n" + "".join(
            f"  {k}: {v}\n" for k, v in hashes.items()) + "---\n\n# 世界书\n"
        (cdir / "client_index.md").write_text(fm, encoding="utf-8")
        assert _audit_worldbook_freshness("测试客户", clients_dir=str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "client_index.md 新鲜" in out

    def test_frontmatter_drift_warns_even_if_mtime_fresh(self, tmp_path, capsys):
        """真漂移不误判新鲜：front matter hash 落后但索引 mtime 更新，仍 WARN。

        这是「mtime 兜底仅限无 frontmatter 路径」的钉子——若有人把 mtime 回退
        扩大到 hash 路径，本例的漂移会被 mtime 新鲜掩盖。
        """
        cdir = _mk_client(tmp_path)
        stale_fm = "---\n_source_hashes:\n  decisions.md: " + "0" * 64 + "\n---\n\n# 世界书\n"
        (cdir / "client_index.md").write_text(stale_fm, encoding="utf-8")
        # 索引 mtime 明显新于真源
        _set_mtimes(cdir, 1000000000, 1000000000, 1000000500)
        assert _audit_worldbook_freshness("测试客户", clients_dir=str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "落后于真源 (decisions.md" in out, "hash 漂移必须仍 WARN（不被 mtime 新鲜掩盖）"
        assert "(mtime)" not in out.split("client_index.md")[1].split("\n")[0]
