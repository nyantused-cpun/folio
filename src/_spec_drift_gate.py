# -*- coding: utf-8 -*-
"""spec/HTML 漂移门（S0 棘轮处置拆分自 _cli_generate.py，2026-09-07）。

职责：pptd 工程的双漂移通道 + spec 门（表达模式计划书 0b）：
  - _record_html_hash（构建时记录 .html_sha256 / .spec_sha256）
  - _check_html_drift（pptd-build 前比对 HTML 内容哈希，提示不阻断）
  - _pptd_apply_spec_gates（spec 哈希漂移 exit 2 + require_confirmed confirm 门）
"""
import hashlib
import os
import sys


def _record_html_hash(pptd_dir, html_path, spec_path=None):
    """构建时在 pptd 工程内记录 HTML 内容哈希 + spec 哈希（漂移通道）。

    spec 哈希（.spec_sha256）供 pptd-build 检测「confirm 后改 spec 仍用旧
    工程出 PPT」的漂移（表达模式计划书 0b）。
    """
    if not html_path or not os.path.exists(html_path):
        return
    try:
        with open(html_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        meta_path = os.path.join(pptd_dir, ".html_sha256")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"{os.path.abspath(html_path)}|{digest}")
        if spec_path and os.path.exists(spec_path):
            with open(spec_path, "rb") as f:
                spec_digest = hashlib.sha256(f.read()).hexdigest()
            with open(os.path.join(pptd_dir, ".spec_sha256"), "w",
                      encoding="utf-8") as f:
                f.write(f"{os.path.abspath(spec_path)}|{spec_digest}")
    except Exception:
        pass  # 哈希记录失败不阻断构建


def _check_html_drift(pptd_dir):
    """pptd-build 前比对 HTML 内容哈希；被改则提示编辑不生效，不阻断。"""
    meta_path = os.path.join(pptd_dir, ".html_sha256")
    if not os.path.exists(meta_path):
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            html_path, recorded = f.read().strip().rsplit("|", 1)
        if not os.path.exists(html_path):
            return False
        with open(html_path, "rb") as f:
            current = hashlib.sha256(f.read()).hexdigest()
        return current != recorded
    except Exception:
        return False


def _pptd_apply_spec_gates(deck_dir):
    """pptd-build 的 spec 漂移门 + confirm 门（表达模式计划书 0b，fail-closed）。

    读 .spec_sha256 得到构建时 spec 快照：
    ① spec 文件已改（哈希漂移）→ exit 2（改 spec 应重新 html-build）
    ② spec 未过 confirm（sidecar 缺失/哈希不一致）→ require_confirmed 抛
       RenderBlockedError 传播到 _cli 顶层兜底 exit 2
    旧工程无 .spec_sha256 → 不校验（向后兼容）。
    """
    meta_path = os.path.join(deck_dir, ".spec_sha256")
    if not os.path.exists(meta_path):
        return
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            spec_path, recorded = f.read().strip().rsplit("|", 1)
        if not os.path.exists(spec_path):
            # spec 已挪走/删除：无法判定漂移，confirm 门也无从执行；
            # 向后兼容不阻断（与元数据损坏同语义），但打印提示保证可见
            print(f"[提示] .spec_sha256 记录的 spec 不存在（{spec_path}），"
                  f"spec 漂移门/confirm 门跳过")
            return
        with open(spec_path, "rb") as f:
            current = hashlib.sha256(f.read()).hexdigest()
        if current != recorded:
            print(f"[阻断] spec 已变更（{os.path.basename(spec_path)}），"
                  f"请重新 html-build 后再出 PPT（fail-closed）")
            sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        return  # 元数据损坏不判定漂移（与 HTML drift 同语义）
    # confirm 门：未过 confirm 的 spec 不允许出 PPT（RenderBlockedError 传播）。
    # spec 读盘/解析失败按 fail-closed 收口（S4 增强，此前裸 traceback 崩进程）
    try:
        import yaml
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        print(f"[阻断] spec 读取/解析失败（{os.path.basename(spec_path)}）: "
              f"{e}（fail-closed，请检查 spec 后重试）")
        sys.exit(2)
    if not isinstance(spec, dict):
        spec = {}  # 非 dict 按未确认处理，confirm 门自然阻断
    from _cli_guards import require_confirmed
    require_confirmed(spec, context="pptd-build", spec_path=spec_path)
