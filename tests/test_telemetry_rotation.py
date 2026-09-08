# -*- coding: utf-8 -*-
"""argo telemetry JSONL 写前按大小轮转单元测试（P3-8）。

事实源按文件路径动态定位加载（主仓 .folio/skills/argo/scripts/telemetry.py；
folio 侧无 argo skill 时 skip，不阻塞对齐后测试套件），
不依赖 sys.path 注入；全部写入走 tmp_path（ARGO_TELEMETRY_DIR 注入），
不触碰真实 ~/.cache 与日志目录。
"""
import importlib.util
import os
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CANDIDATES = [
    _ROOT / ".folio" / "skills" / "argo" / "scripts" / "telemetry.py",
    _ROOT / ".folio" / "skills" / "argo" / "scripts" / "telemetry.py",
    _ROOT / "skills" / "argo" / "scripts" / "telemetry.py",
]
_SCRIPT = next((p for p in _CANDIDATES if p.exists()), None)

if _SCRIPT is None:  # 无 argo skill 的工作区（如 folio 发布面）整文件跳过
    pytest.skip("argo telemetry.py 不在本工作区（folio 发布面无 argo skill）",
                allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("argo_telemetry_under_test", _SCRIPT)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


def _mk(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_no_rotate_under_limit(tmp_path):
    """未超限：不动文件，返回 False。"""
    main = _mk(tmp_path / "s.jsonl", '{"a":1}\n')
    assert _mod.rotate_if_oversized(main, max_bytes=1000) is False
    assert main.exists()
    assert main.read_text(encoding="utf-8") == '{"a":1}\n'


def test_rotate_over_limit_renames_main(tmp_path):
    """超限且无轮转件：主文件改名 .1。"""
    main = _mk(tmp_path / "s.jsonl", "old-main\n")
    assert _mod.rotate_if_oversized(main, max_bytes=5) is True
    assert not main.exists()
    assert (tmp_path / "s.jsonl.1").read_text(encoding="utf-8") == "old-main\n"


def test_rotate_shifts_and_caps_keep(tmp_path):
    """顺移 + 保留份数上限：.2→.3、.1→.2、主→.1，最旧 .3 被覆盖删除。"""
    main = _mk(tmp_path / "s.jsonl", "new-main\n")
    _mk(tmp_path / "s.jsonl.1", "rot-1\n")
    _mk(tmp_path / "s.jsonl.2", "rot-2\n")
    _mk(tmp_path / "s.jsonl.3", "rot-3-oldest\n")
    assert _mod.rotate_if_oversized(main, max_bytes=5, keep=3) is True
    assert not main.exists()
    assert (tmp_path / "s.jsonl.1").read_text(encoding="utf-8") == "new-main\n"
    assert (tmp_path / "s.jsonl.2").read_text(encoding="utf-8") == "rot-1\n"
    assert (tmp_path / "s.jsonl.3").read_text(encoding="utf-8") == "rot-2\n"
    # rot-3-oldest 已被顺移覆盖，轮转件总数恒为 keep 上限
    assert not (tmp_path / "s.jsonl.4").exists()
    rotated = [f for f in os.listdir(tmp_path) if f.startswith("s.jsonl.")]
    assert len(rotated) == 3


def test_emit_rotates_before_append(tmp_path, monkeypatch):
    """端到端：emit 追加前触发轮转，新记录落在全新主文件，旧内容进 .1。"""
    monkeypatch.setenv("ARGO_TELEMETRY_DIR", str(tmp_path))
    monkeypatch.setattr(_mod, "_ROTATE_MAX_BYTES", 10)
    main = tmp_path / "u.jsonl"
    _mk(main, "x" * 50 + "\n")
    assert _mod.emit("u", {"k": "v"}) is True
    assert "old" not in main.read_text(encoding="utf-8")
    recs = _mod.tail("u", 10)
    assert len(recs) == 1 and recs[0]["k"] == "v" and recs[0]["stream"] == "u"
    assert (tmp_path / "u.jsonl.1").read_text(encoding="utf-8") == "x" * 50 + "\n"


def test_emit_small_file_no_rotate(tmp_path, monkeypatch):
    """未超限的常规追加：不产生轮转件。"""
    monkeypatch.setenv("ARGO_TELEMETRY_DIR", str(tmp_path))
    assert _mod.emit("small", {"k": 1}) is True
    assert _mod.emit("small", {"k": 2}) is True
    assert list(tmp_path.glob("small.jsonl.*")) == []
    assert len(_mod.tail("small", 10)) == 2


@pytest.mark.parametrize("bad", ["/", "\x00"])
def test_rotate_failure_silent(tmp_path, bad):
    """异常路径静默返回 False，不抛（失败静默纪律）。"""
    ghost = tmp_path / "no-such-dir" / "s.jsonl"  # 父目录不存在 → stat 抛
    assert _mod.rotate_if_oversized(ghost, max_bytes=0) is False
