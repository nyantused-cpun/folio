# -*- coding: utf-8 -*-
"""_save_lock 单元测试（P1 健壮性 · T7 文件锁）。

全部用 tmp_path 造假目录，绝不读写真实 _knowledge/ 客户目录。
设计语义（Windows 语义红利）：活进程持有的 fd 使 os.remove 抛 PermissionError，
死进程 fd 被 OS 关闭后 remove 成功——remove 即活性探测；陈旧锁先按 mtime 判定。
"""

import os
import threading
import time

import _save_lock


# ============================================================
# 获取 / 释放 / 内容
# ============================================================
class TestAcquireRelease:
    def test_acquire_creates_lock_with_pid(self, tmp_path):
        fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd is not None
        try:
            lock = tmp_path / ".save_lock"
            assert lock.exists()
            content = lock.read_text(encoding="utf-8")
            # 锁文件内容含 pid："{pid}|{ts}"
            assert content.startswith(f"{os.getpid()}|")
            pid_part, ts_part = content.split("|", 1)
            assert pid_part == str(os.getpid())
            assert ts_part.strip().isdigit()
        finally:
            _save_lock.release_save_lock(str(tmp_path), fd)

    def test_release_removes_lock_file(self, tmp_path):
        fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd is not None
        assert (tmp_path / ".save_lock").exists()
        _save_lock.release_save_lock(str(tmp_path), fd)
        assert not (tmp_path / ".save_lock").exists()

    def test_release_allows_reacquire(self, tmp_path):
        fd1 = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd1 is not None
        _save_lock.release_save_lock(str(tmp_path), fd1)
        fd2 = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd2 is not None
        _save_lock.release_save_lock(str(tmp_path), fd2)


# ============================================================
# 持锁期间：二次获取 / 并发
# ============================================================
class TestHeldLock:
    def test_second_acquire_times_out_while_held(self, tmp_path):
        fd1 = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd1 is not None
        try:
            # 持锁时二次获取（短 timeout）返回 None
            fd2 = _save_lock.acquire_save_lock(str(tmp_path), timeout=1.0)
            assert fd2 is None
        finally:
            _save_lock.release_save_lock(str(tmp_path), fd1)

    def test_concurrent_acquire_single_winner(self, tmp_path):
        """并发两个 acquire 只有一个成功；胜者释放后无锁残留。

        两线程同时开抢（barrier 同步），各自 timeout=0.8、持锁 1.5s——
        无论谁先赢，败者 0.5s 间隔重试到超时（1.0s 左右）时胜者仍在持锁，
        因此败者必返回 None，只有胜者返回 fd。
        """
        barrier = threading.Barrier(2)
        results = []

        def worker():
            barrier.wait()
            fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=0.8, stale_after=300.0)
            if fd is not None:
                results.append(True)
                time.sleep(1.5)  # 持有超过败者超时窗口
                _save_lock.release_save_lock(str(tmp_path), fd)
            else:
                results.append(False)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1
        assert results.count(False) == 1
        assert not (tmp_path / ".save_lock").exists()


# ============================================================
# 陈旧锁（mtime 篡改）/ 活锁（remove 抛 PermissionError）
# ============================================================
class TestStaleAndLiveLock:
    def test_stale_lock_breakable_via_utime(self, tmp_path):
        """os.utime 篡改 mtime 到 6 分钟前 -> 陈旧锁可破（重新获取成功）。"""
        lock = tmp_path / ".save_lock"
        lock.write_text("99999|1111111111", encoding="utf-8")  # 死进程残留形态：无 fd 持有
        old = time.time() - 360  # 6 分钟前
        os.utime(lock, (old, old))

        fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=2.0)
        assert fd is not None
        try:
            content = lock.read_text(encoding="utf-8")
            assert content.startswith(f"{os.getpid()}|")  # 内容已刷新为当前进程
        finally:
            _save_lock.release_save_lock(str(tmp_path), fd)

    def test_fresh_lock_not_removed_even_if_utime_short(self, tmp_path):
        """非陈旧锁（mtime 距今 < stale_after）不被 remove，等待超时返回 None。"""
        lock = tmp_path / ".save_lock"
        lock.write_text("99999|1111111111", encoding="utf-8")
        old = time.time() - 60  # 1 分钟前：未超过 stale_after=300
        os.utime(lock, (old, old))

        fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=1.0)
        assert fd is None
        assert lock.exists()

    def test_live_lock_remove_permission_error_waits_to_timeout(self, tmp_path, monkeypatch):
        """monkeypatch os.remove 抛 PermissionError -> 按活锁处理，等待到超时返回 None。"""
        lock = tmp_path / ".save_lock"
        lock.write_text("99999|1111111111", encoding="utf-8")
        old = time.time() - 360  # 陈旧但 remove 被拒 = 活进程持有
        os.utime(lock, (old, old))

        def boom(path):
            raise PermissionError(13, "Access is denied")

        monkeypatch.setattr(os, "remove", boom)
        fd = _save_lock.acquire_save_lock(str(tmp_path), timeout=1.0)
        assert fd is None
        assert lock.exists()  # 活锁未被清掉
