# -*- coding: utf-8 -*-
"""增量审查（WP-A5，B6 #19，2026-09-08 R1 波）——同文件迭代复审的 opt-in 优化。

目标：审查 tokens/会话 318K → <150K（B6 KPI 表第 1 行）。deck 迭代改版时，
每次 review 全量注入 12000 字是最大浪费源；本模块按页对比上次审查快照，
只把**变更页全文**送 LLM，未变更页以「标题|首行」轻摘要注入保持全局视野，
每 3 轮强制 1 轮全量防跨页一致性漂移累积。

设计稿：docs/WP-A5增量审查_Q1设计稿_2026-09-08.md（Q1 三问裁决）。
设计约束（B6 §六）三条的落实：
  1. 机械检查全量跑——banned 检查在 _review._prepare_context 内对全文跑，
     不受 LLM 注入覆盖影响；diagram 机检清单同样全文提取。
  2. 未变更页轻摘要——_page_digest 取页文本前 SUMMARY_HEAD_CHARS 字。
  3. 每 3 轮强制 1 轮全量——round % INCREMENTAL_EVERY == 0。

退化语义（永不劣于现状）：非 HTML / 读失败 / 无页容器（含单页件）/ 无基线
快照 / 轮到全量轮 → 全量，等价 review() 原行为。

依赖纪律：对 _review 的共用件一律函数内 import（同 _review_parallel.py，
本模块被 _review.resolve_review_fn 惰性引用，保持 mock 语义与加载安全）。
"""
import hashlib
import json
import os
import re
from datetime import datetime

# 快照读写持锁（W1-4 review_log 锁先例：_save_lock 原子创建 + 失败重试 1 次
# + 最终失败「不阻断」——审查结论不因快照写入失败而中断）
SNAPSHOT_LOCK_NAME = ".review_snapshots.lock"
SNAPSHOT_LOCK_TIMEOUT = 5.0
SNAPSHOT_LOCK_RETRY_TIMEOUT = 10.0

INCREMENTAL_EVERY = 3        # 每 3 轮强制 1 轮全量（round % 3 == 0）
SUMMARY_HEAD_CHARS = 60      # 轻摘要「标题|首行」截断
PAGE_TEXT_MAX_CHARS = 6000   # 单变更页注入上限（页级防超窗）
CHANGED_TOTAL_MAX_CHARS = 12000  # 变更页全文合计上限（对齐 _review.MAX_OUTPUT_CHARS）

# deck 页容器（蓝海 v3 13 页实测；老管线无此容器的产出自动退化全量）
_PAGE_DIV_RE = re.compile(r'<div[^>]*class="ppt-page[^"]*"[^>]*>', re.I)


def snapshots_path():
    """快照文件路径：review_log.json 同目录（.folio/logs/）。

    路径每次调用时取——测试 monkeypatch _paths.REVIEW_LOG 即可整体隔离。
    """
    import _paths
    return os.path.join(os.path.dirname(_paths.REVIEW_LOG), "review_snapshots.json")


def split_pages(output_path):
    """deck HTML 按 <div class="ppt-page..."> 容器切页，去标签取页纯文本。

    返回 [(page_key, page_text)]（page_key="p01"起）；非 HTML / 读失败 /
    页容器少于 2 个（单页件增量无意义）→ None（调用方退化全量）。
    去标签口径与 _review._read_output_text 一致（先剔 style/script/head）；
    页边界取「本页起点到下页起点」，规避 </div> 配对复杂性——页尾可能混入
    页间杂项，哈希对比只需稳定，不需精确页界。
    """
    if not str(output_path).lower().endswith((".html", ".htm")):
        return None
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None
    raw = re.sub(r"<(style|script)\b[^>]*>.*?</\1\s*>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<head\b[^>]*>.*?</head\s*>", " ", raw, flags=re.S | re.I)
    starts = [m.start() for m in _PAGE_DIV_RE.finditer(raw)]
    if len(starts) < 2:
        return None
    starts.append(len(raw))
    pages = []
    for i in range(len(starts) - 1):
        chunk = raw[starts[i]:starts[i + 1]]
        text = re.sub(r"<[^>]+>", " ", chunk)
        text = re.sub(r"\s+", " ", text).strip()
        pages.append((f"p{i + 1:02d}", text))
    return pages


def page_hash(text):
    """页基线哈希：sha1(页纯文本) hex。快照对比的唯一判据。

    usedforsecurity=False：此处 sha1 仅作内容变更检测（非安全用途），
    显式声明同时过 bandit B324 门。
    """
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def _page_digest(text):
    """未变更页轻摘要：首行语义即「标题|首行」——页去标签文本的前 N 字。"""
    if not text:
        return "(空白页)"
    return text[:SUMMARY_HEAD_CHARS] + ("…" if len(text) > SUMMARY_HEAD_CHARS else "")


def load_snapshots():
    """读快照表（读侧容错同 _review.read_review_log：缺失/损坏一律 {}）。

    无锁读——快照仅是优化基线，窄竞态（读后他人改写）最坏导致一轮误增量/
    误全量，正确性由页哈希对比与 3 轮全量兜底；写侧 save_snapshots 持锁。
    路径每次调用时取——测试 monkeypatch _paths.REVIEW_LOG 即可整体隔离。
    """
    path = snapshots_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_snapshots(data):
    """快照表落盘（持锁；失败打印警告不阻断，语义同 write_review_log）。"""
    from _save_lock import acquire_save_lock, release_save_lock

    path = snapshots_path()
    logs_dir = os.path.dirname(path)
    lock_fd = acquire_save_lock(logs_dir, timeout=SNAPSHOT_LOCK_TIMEOUT,
                                lock_name=SNAPSHOT_LOCK_NAME)
    if lock_fd is None:
        import time
        time.sleep(1.0)
        lock_fd = acquire_save_lock(logs_dir, timeout=SNAPSHOT_LOCK_RETRY_TIMEOUT,
                                    lock_name=SNAPSHOT_LOCK_NAME)
    if lock_fd is None:
        print(f"[review] 快照写入失败（不阻断）: {SNAPSHOT_LOCK_NAME} 获取失败，"
              f"下次 review 将按全量处理")
        return
    try:
        os.makedirs(logs_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[review] 快照写入失败（不阻断）: {e}")
    finally:
        release_save_lock(logs_dir, lock_fd, lock_name=SNAPSHOT_LOCK_NAME)


def select_pages(pages, prev_pages, force_full):
    """基线对比选页：返回 (changed, unchanged)。

    changed=[(page_key, text)]（hash 不同或新增）；unchanged 同构（hash 相同）。
    被删除的页不出现也不注入（LLM 只需审现存内容）。
    """
    if force_full or pages is None or not prev_pages:
        return list(pages or []), []
    changed, unchanged = [], []
    for pk, text in pages:
        if prev_pages.get(pk) == page_hash(text):
            unchanged.append((pk, text))
        else:
            changed.append((pk, text))
    return changed, unchanged


def compose_llm_text(changed, unchanged):
    """组装增量注入文本：变更页全文（页级+合计预算内）+ 未变更页轻摘要区。

    预算装不下的变更页降级进摘要区（防超窗比漏审变更更可接受——超窗会撞
    max_tokens 导致审查整体失败，降级只损该页细度，轻摘要仍保全局视野）。
    """
    parts = []
    digests = []
    budget = CHANGED_TOTAL_MAX_CHARS
    for pk, text in changed:
        if budget <= 0:
            digests.append(f"{pk}（变更，超预算降级摘要）{_page_digest(text)}")
            continue
        piece = text[:min(PAGE_TEXT_MAX_CHARS, budget)]
        budget -= len(piece)
        head = f"[{pk} 本轮变更·全文]" if len(piece) >= len(text) else f"[{pk} 本轮变更·截断至{len(piece)}字]"
        parts.append(f"{head}\n{piece}")
    for pk, text in unchanged:
        digests.append(f"{pk}（未变更）{_page_digest(text)}")
    if digests:
        parts.append("[未变更页概览（仅全局视野参考，无需重复细审）]\n" + "\n".join(digests))
    return "\n\n".join(parts)


def review_incremental(output_path, client_name=None, spec_path=None, quiet=False):
    """增量审查入口（review --incremental，WP-A5）。

    流程：切页 → 读快照选页（退化条件命中即全量）→ 组装注入文本 →
    复用 _review.review(output_text=...)（机检/熔断/收尾全继承）→
    PASS/FAIL 后刷新快照（ERROR/SKIP 不刷——基线未知）。

    Returns:
        dict: 同 _review.review（result 带 review_mode=full|incremental）
    """
    from _review import review as _full_review

    pages = split_pages(output_path)
    key = os.path.abspath(output_path)
    entry = load_snapshots().get(key) or {}
    prev_pages = entry.get("pages") or {}
    prev_round = entry.get("round", 0)
    if not isinstance(prev_round, int) or prev_round < 0:
        prev_round = 0

    # 全量轮判定：无基线 / 轮到 INCREMENTAL_EVERY 整数轮 / 页切分失败
    force_full = (not prev_pages or pages is None
                  or (prev_round + 1) % INCREMENTAL_EVERY == 0)

    changed, unchanged = select_pages(pages, prev_pages, force_full)
    is_incremental = not force_full

    if is_incremental:
        print(f"[review] 增量选页: 变更 {len(changed)} 页（全文注入），"
              f"未变更 {len(unchanged)} 页（轻摘要），第 {prev_round + 1} 轮")
        llm_text = compose_llm_text(changed, unchanged)
    else:
        reason = ("页切分失败/非 deck HTML" if pages is None
                  else ("无基线快照" if not prev_pages else "轮到全量轮"))
        print(f"[review] 全量审查（{reason}；增量条件未命中）")
        llm_text = None

    result = _full_review(output_path, client_name, spec_path, quiet,
                          output_text=llm_text)

    # 快照刷新：只认 PASS/FAIL（ERROR=LLM 不可得、SKIP=显式跳过，基线未知；
    # 熔断轮 fused 在 review 内部早退，同样不出 PASS/FAIL）。重新 load-合并-
    # 写：审查期间其他会话可能已刷新别的文件条目（同 review_log 并发纪律）
    if result.get("verdict") in ("PASS", "FAIL") and pages is not None:
        data = load_snapshots()
        data[key] = {
            "round": prev_round + 1,
            "pages": {pk: page_hash(text) for pk, text in pages},
            "review_mode": result.get("review_mode", "full"),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        save_snapshots(data)

    return result
