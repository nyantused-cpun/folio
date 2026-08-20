# -*- coding: utf-8 -*-
"""save_session 按客户文件锁（P1 健壮性 · T7）。

纯函数、零第三方依赖、Windows+POSIX 通用。

锁文件：<client_dir>/.save_lock（点开头，索引/归档 walk 按扩展名或点文件规则
天然跳过：_embed_index 只读 context.md/outputs/*.md/refs/*；BM25 按扩展名匹配，
`.save_lock` 无扩展名不入选；_snapshot_context 只认 context.md.snapshot.*）。

设计依据（Windows 语义红利）：
  活进程持有的文件 fd 保持打开，此时 os.remove 抛 PermissionError（共享冲突）；
  死进程的 fd 被 OS 关闭后，os.remove 成功——remove 本身就是活性探测。
  POSIX 下 remove 对打开文件同样成功，故先做 mtime 陈旧判定（> stale_after，
  默认 300s，容忍长 embedding），只有长期未更新的锁才进入 remove 探测路径。

用法：
    from _save_lock import acquire_save_lock, release_save_lock

    fd = acquire_save_lock(client_dir)          # 成功返回 fd（持锁期间保持打开）
    if fd is None:                              # timeout 内未拿到 -> 大声失败，绝不绕锁
        print("...")                            # 调用方 print 明确中文原因并返回 False
        return False
    try:
        ... 全部写入 ...
    finally:
        release_save_lock(client_dir, fd)       # close(fd) + remove(lock)
"""
import os
import time

LOCK_FILENAME = ".save_lock"


def acquire_save_lock(client_dir, timeout=30.0, stale_after=300.0):
    """原子创建 <client_dir>/.save_lock 获取按客户写锁。

    成功：返回打开的 fd（持锁期间必须保持打开，Windows 上即活性证据），
          锁文件内容为 "{pid}|{int(time.time())}"。
    超时：返回 None。调用方应大声失败（print 明确原因 + return False），
          绝不静默跳过、绝不绕锁写入。

    竞态处理（FileExistsError 时）：
      - 读 mtime 抛 FileNotFoundError = 锁刚被释放，立即重试；
      - mtime 超过 stale_after（陈旧锁）-> 尝试 os.remove：
          PermissionError = 活进程持有（Windows 共享冲突），继续等；
          remove 成功 = 死进程残留（fd 已随进程关闭），立即重试获取；
      - 其余情况 sleep 0.5 循环，直到 timeout 到期返回 None。
    """
    lock_path = os.path.join(client_dir, LOCK_FILENAME)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # 锁已存在：陈旧判定 -> remove 活性探测
            try:
                mtime = os.path.getmtime(lock_path)
            except FileNotFoundError:
                continue  # 锁刚被释放（竞态），立即重试获取
            if time.time() - mtime > stale_after:
                try:
                    os.remove(lock_path)  # 死锁应能删掉；活锁（Windows）抛 PermissionError
                except PermissionError:
                    pass  # 活锁：fd 仍被活进程持有，继续等
                except FileNotFoundError:
                    continue  # 被其他进程抢先清理，立即重试
                else:
                    continue  # remove 成功 = 死锁已清，立即重试获取
            if time.time() >= deadline:
                return None
            time.sleep(0.5)
            continue
        except OSError:
            # 其他系统错误（目录不存在/权限不足等）：等待重试，超时返回 None
            if time.time() >= deadline:
                return None
            time.sleep(0.5)
            continue
        # 原子创建成功：写入 "{pid}|{ts}"，fd 保持打开直至 release
        try:
            os.write(fd, f"{os.getpid()}|{int(time.time())}".encode("utf-8"))
        except OSError:
            try:
                os.close(fd)
            except OSError:
                pass
            return None
        return fd


def release_save_lock(client_dir, fd):
    """释放锁：close(fd) + remove(lock)。自己持有的锁 remove 必成功。

    先 close 再 remove：Windows 上 fd 关闭后共享冲突解除，remove 才可能成功。
    """
    lock_path = os.path.join(client_dir, LOCK_FILENAME)
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.remove(lock_path)
    except OSError:
        pass
