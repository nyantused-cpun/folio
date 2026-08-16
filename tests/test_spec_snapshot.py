# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""§八 3.1 spec 版本快照：confirmed spec 渲染前快照到 spec 同目录 .versions/。

挂接点在 CLI 生成命令（html-build / docx-build / pptd-gen）、Renderer 构造之前；
复用 _backup.backup_before_generate（.bak + .versions/，保留最近 5 版）。
Renderer 本体不做快照（测试/审计也会构造 Renderer，不能每次构造都写盘）。
"""

import os
import shutil
import sys

import yaml


def _write_spec(tmp_path, confirmed=True):
    spec = {
        "confirmed": confirmed,
        "author": "测试公司",
        "date": "2026-07-21",
        "style": "enterprise",
        "document": {"title": "快照测试", "subtitle": ""},
        "pages": [{"id": "p01", "title": "一页", "elements": [
            {"type": "text", "content": "正文。"}]}],
    }
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


def _run_main_allow_success(argv, monkeypatch):
    """调用 _cli.main()，允许成功路径（返回 None 或退出码）。"""
    import _cli
    monkeypatch.setattr(sys, "argv", argv)
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    try:
        _cli.main()
        return None
    except SystemExit as e:
        return e.code
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


def _mock_generate_pipeline(monkeypatch):
    """mock 生成链路外围环节（pre_check / 编辑器注入 / verify / review / post_check），
    保留真实的 Renderer 渲染与 backup_before_generate 快照。"""
    import _cli_generate
    monkeypatch.setattr(_cli_generate, "_run_pre_check",
                        lambda client_name=None: {"ok": True})
    monkeypatch.setattr(_cli_generate, "_run_post_check", lambda *a, **k: None)
    monkeypatch.setattr(_cli_generate, "_auto_review", lambda *a, **k: None)
    monkeypatch.setattr("_renderer.html_editor_injector.inject", lambda *a, **k: None)
    monkeypatch.setattr("_verify_hook.run_single", lambda *a, **k: True)


class TestSnapshotHelper:
    """_snapshot_spec_if_confirmed 单元行为。"""

    def test_confirmed_spec_snapshotted(self, tmp_path):
        import _cli_generate
        spec = _write_spec(tmp_path, confirmed=True)
        _cli_generate._snapshot_spec_if_confirmed(spec)
        versions_dir = tmp_path / ".versions"
        assert versions_dir.is_dir()
        snapshots = [f for f in os.listdir(versions_dir) if f.startswith("spec.yml.")]
        assert len(snapshots) == 1
        assert (tmp_path / "spec.yml.bak").exists()

    def test_unconfirmed_spec_not_snapshotted(self, tmp_path):
        import _cli_generate
        spec = _write_spec(tmp_path, confirmed=False)
        _cli_generate._snapshot_spec_if_confirmed(spec)
        assert not (tmp_path / ".versions").exists()
        assert not (tmp_path / "spec.yml.bak").exists()

    def test_missing_spec_noop(self, tmp_path):
        """spec 读不出时不快照、不抛异常（真正的错误交给 Renderer 报出）。"""
        import _cli_generate
        _cli_generate._snapshot_spec_if_confirmed(str(tmp_path / "不存在.yml"))
        assert not (tmp_path / ".versions").exists()

    @staticmethod
    def _freeze_backup_time(monkeypatch, *timestamps):
        """backup 时间戳打桩：每次快照取下一个时间戳（防同秒文件名碰撞）。"""
        import _backup
        from datetime import datetime as _dt
        ticks = iter(timestamps)

        class _FakeDT:
            @staticmethod
            def now():
                return _dt.strptime(next(ticks), "%Y%m%d%H%M%S")

        monkeypatch.setattr(_backup, "datetime", _FakeDT)

    def test_same_content_not_snapshotted_twice(self, tmp_path, monkeypatch):
        """内容 hash 判重：与最新快照一致则跳过（防重复构建挤占 5 版容量）。"""
        self._freeze_backup_time(monkeypatch, "20260101000000", "20260102000000")
        import _cli_generate
        spec = _write_spec(tmp_path, confirmed=True)
        _cli_generate._snapshot_spec_if_confirmed(spec)
        _cli_generate._snapshot_spec_if_confirmed(spec)
        snapshots = [f for f in os.listdir(tmp_path / ".versions")
                     if f.startswith("spec.yml.")]
        assert len(snapshots) == 1, "同内容重复构建不得产生第二份快照"

    def test_changed_content_snapshotted_again(self, tmp_path, monkeypatch):
        """内容变化后仍产生新快照（hash 判重不误伤正常迭代）。"""
        self._freeze_backup_time(monkeypatch, "20260101000000", "20260102000000")
        import _cli_generate
        spec = _write_spec(tmp_path, confirmed=True)
        _cli_generate._snapshot_spec_if_confirmed(spec)
        p = tmp_path / "spec.yml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        data["document"]["title"] = "改动后标题"
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        _cli_generate._snapshot_spec_if_confirmed(spec)
        snapshots = [f for f in os.listdir(tmp_path / ".versions")
                     if f.startswith("spec.yml.")]
        assert len(snapshots) == 2


class TestHtmlBuildSnapshot:
    """CLI 层：html-build 后 confirmed spec 同目录出现 .versions/ 快照。"""

    OUT_DIR = os.path.join("output", "通用", "_snapshot_test")

    def setup_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def teardown_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def test_confirmed_spec_snapshot_after_html_build(self, monkeypatch, tmp_path):
        _mock_generate_pipeline(monkeypatch)
        spec = _write_spec(tmp_path, confirmed=True)
        out_html = os.path.join(self.OUT_DIR, "方案.html")
        code = _run_main_allow_success(
            ["_cli.py", "html-build", spec, out_html, "--html-only"], monkeypatch)
        assert code in (None, 0)
        assert os.path.exists(out_html)
        versions_dir = tmp_path / ".versions"
        assert versions_dir.is_dir()
        snapshots = [f for f in os.listdir(versions_dir) if f.startswith("spec.yml.")]
        assert len(snapshots) == 1

    def test_unconfirmed_spec_no_snapshot_and_blocked(self, monkeypatch, tmp_path):
        """unconfirmed spec 过不了 confirmed 门：无快照、无产出、exit 1。"""
        _mock_generate_pipeline(monkeypatch)
        spec = _write_spec(tmp_path, confirmed=False)
        out_html = os.path.join(self.OUT_DIR, "方案.html")
        code = _run_main_allow_success(
            ["_cli.py", "html-build", spec, out_html, "--html-only"], monkeypatch)
        assert code == 1
        assert not (tmp_path / ".versions").exists()
        assert not os.path.exists(out_html)


class TestPptdGenSnapshot:
    """CLI 层：pptd-gen 在 confirmed 门后快照 spec 本体。"""

    OUT_DIR = os.path.join("output", "通用", "_snapshot_pptd_test")

    def setup_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def teardown_method(self):
        if os.path.exists(self.OUT_DIR):
            shutil.rmtree(self.OUT_DIR)

    def test_pptd_gen_snapshots_spec(self, monkeypatch, tmp_path):
        import _cli_generate
        monkeypatch.setattr(_cli_generate, "_run_pre_check",
                            lambda client_name=None: {"ok": True})
        # 只 mock 产物备份（pptd 主文件），spec 快照走真实 backup_before_generate
        real_backup = _cli_generate.backup_before_generate

        def _backup_only_spec(path, *a, **k):
            if str(path).endswith(".yml"):
                return real_backup(path, *a, **k)
            return None
        monkeypatch.setattr(_cli_generate, "backup_before_generate", _backup_only_spec)

        spec = _write_spec(tmp_path, confirmed=True)
        code = _run_main_allow_success(
            ["_cli.py", "pptd-gen", spec, "--client", "测试",
             "--output", self.OUT_DIR], monkeypatch)
        assert code in (None, 0)
        versions_dir = tmp_path / ".versions"
        assert versions_dir.is_dir()
        snapshots = [f for f in os.listdir(versions_dir) if f.startswith("spec.yml.")]
        assert len(snapshots) == 1
