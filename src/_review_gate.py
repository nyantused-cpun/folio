# -*- coding: utf-8 -*-
"""S9-2d：crafted×review 产物侧门禁（组合强制 review + 禁直出交付）。

发散温度档（PROJECT_DESIGN §8 ``mode: creative``，temperature 0.8）是生成参数，
产物链无落痕（spec 顶层/CLI 参数均不持久化），故组合触发回退到唯一硬信号——
「spec 含 crafted 页」（raw_html 元素或叙事单 expression_mode=crafted，
复用 narrative_schema.collect_crafted_pages）。组合的本质 = crafted 页必须过
review 才能交付。

门禁形态（挂载点见各函数 docstring）：
  - deliver 链（cmd_deliver --resume Step 2 前）→ 阻断 exit 1，指路
    「先跑 review --adversarial --screenshot」（review_log 查询复用
    _review.read_review_log）；
  - 独立 html-build（_verify_hook.run_single 挂载）→ warn 提示，不阻断产出
    （阻断交付即可，机制互补非债；触发用产物侧硬信号 data-track="crafted"
    （1c 边界标记 = audit 唯一判定依据，run_single 无 spec 上下文时仍可计数）。
"""
import os
import sys


def _html_has_crafted(html_path):
    """产物侧硬信号：HTML 含 data-track="crafted" 边界标记（1c：audit 唯一依据）。"""
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return 'data-track="crafted"' in f.read()
    except OSError:
        return False


def _spec_crafted_pages(spec_path):
    """读 spec 返回 crafted 页标签清单（collect_crafted_pages 复用）。

    spec 不可读/非 dict → []（调用方以 data-track 硬信号兜底，不误放也不误拦）。
    """
    if not spec_path or not os.path.exists(spec_path):
        return []
    try:
        import yaml
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
    except Exception:
        return []
    if not isinstance(spec, dict):
        return []
    from _renderer.narrative_schema import collect_crafted_pages
    return collect_crafted_pages(spec, spec_path=spec_path)


def _has_pass_review(output_path):
    """review_log 中是否已有该产物的 PASS 记录（复用 _review.read_review_log）。"""
    from _review import read_review_log
    want = os.path.normcase(os.path.abspath(output_path))
    for entry in read_review_log():
        if not isinstance(entry, dict) or entry.get("verdict") != "PASS":
            continue
        f = str(entry.get("file") or "")
        if os.path.normcase(os.path.abspath(f)) == want:
            return True
    return False


def warn_crafted_without_review(html_path):
    """独立 html-build warn 提示（挂载 _verify_hook.run_single，仅 HTML）。

    不阻断产出（阻断交付在 deliver_gate）；已过审或非 crafted 产物静默。
    Returns:
        bool: 是否产生了 warn（测试断言用）。
    """
    if not _html_has_crafted(html_path):
        return False
    if _has_pass_review(html_path):
        return False
    print("[观察] 本产物含 crafted 定制页（data-track=crafted）但 review_log 尚无"
          "该产物 PASS 记录：建议交付前先跑 "
          "python _cli.py review <产出> --adversarial --screenshot（三秒测试主门）")
    return True


def deliver_gate(spec_path, html_path):
    """deliver 链阻断门（挂载 cmd_deliver --resume 定位 .pptd 后、Step 2 前）。

    spec 含 crafted 页（collect_crafted_pages 双源并集）或产物含 data-track
    硬信号，而 review_log 无该产物 PASS 记录 → exit 1 并指路补审。
    非 crafted 或已过审 → 静默放行（返回 False）。
    """
    crafted = _spec_crafted_pages(spec_path)
    if not crafted and not _html_has_crafted(html_path):
        return False
    if _has_pass_review(html_path):
        return False
    pages = "、".join(crafted) if crafted else "data-track=crafted 标记页"
    print(f"[阻断] 交付门（S9-2d）：本产物含 crafted 定制页（{pages}）"
          "但 review_log 中无该产物 PASS 记录——禁止未经 review 直出交付。"
          "请先跑：python _cli.py review <产出> --adversarial --screenshot"
          "（三秒测试主门），PASS 后重跑 deliver --resume")
    sys.exit(1)