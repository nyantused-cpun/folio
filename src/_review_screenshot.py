# -*- coding: utf-8 -*-
"""S9-2a：review 截图对抗审视（crafted 定制页后验美学门，stage 2）。

与文本对抗 review（_review.review_adversarial）的区别：
  - 截图输入：playwright 无头渲染，对 ``data-track="crafted"`` 定制页逐页截图
    （复用 _density 视口/存档/本地路由助手，不重写；无 crafted 标记时回退
    整稿首屏），截图 base64 进 VLM——审「客户高层 3 秒看到什么」；
  - 三秒测试主门：高层看 3 秒定印象，说不出核心结论即 FAIL（其余维度佐证）；
  - 独立会话：每次调用是一次全新 vision_chat 单轮 API 会话，不带生成历史；
  - 预算熔断联动：复用 _review review_budget（_budget_fused_result/_budget_record），
    熔断行为与文本 review 完全一致；
  - 3 轮修正上限：SCREENSHOT_MAX_ROUNDS 单一事实源在 _review；轮次持久化在
    review_log 条目 screenshot_review_rounds 字段；判定用
    _review.screenshot_round_decision（创作子代理派发循环 2c 复用同一函数）；
  - 诚实上限：VLM 会漏细节、不承诺收敛；playwright/VLM 不可用时显式降级
    （SKIP/ERROR + 说明），绝不佯装通过（#43 先例：_verify 美学观察降级标注）。

轮次口径：只计 verdict ∈ (PASS, FAIL) 的 screenshot_adversarial 条目——
ERROR/SKIP（服务不可得/降级）与熔断条目不是修正轮，不计入。
"""
import os
import json
import yaml

import _density
import _review


def _vision_chat(prompt, image_path, provider):
    """VLM 通道薄封装（独立会话单轮调用；测试 monkeypatch 此函数隔离外呼）。"""
    from _cloud_llm_vision import vision_chat
    return vision_chat(prompt, image_path=image_path, provider=provider,
                       task="adversarial_review")


def _open_sync_playwright():
    """playwright 导入薄封装（测试 monkeypatch 此函数模拟缺失/异常）。"""
    from playwright.sync_api import sync_playwright
    return sync_playwright()


_CRAFTED_SHOT_CAP = 3  # 单次审视最多截取的 crafted 页数（协议纪律每 deck ≤2，留 1 余量）


def _render_screenshot(html_path):
    """渲染 HTML → 截图列表（复用 _density 截图助手，不重写渲染层）。

    优先对每个 ``[data-track="crafted"]`` 定制页做元素级截图（全稿整页截图
    会被 VLM 预处理压缩到 1600px 导致不可读；元素级保真且天然对齐「crafted
    页必须过审」）；无 crafted 标记时回退整稿首屏视口截图。
    playwright 缺失/渲染异常上抛，由调用方显式降级（不佯装通过）。

    Returns:
        list[str]: 截图 PNG 路径（_tmp/density_shots/YYYYMMDD/ 存档，与密度
        检查同址，便于人工目检回看）。
    """
    viewport = _density._VIEWPORTS[0]
    shots = []
    with _open_sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            _density._install_local_only_route(page)
            page.set_viewport_size(
                {"width": viewport["width"], "height": viewport["height"]})
            page.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
            page.wait_for_load_state("networkidle")
            os.makedirs(_density._shot_dir(), exist_ok=True)
            crafted = page.query_selector_all('[data-track="crafted"]')
            if crafted:
                for i, el in enumerate(crafted[:_CRAFTED_SHOT_CAP]):
                    shot = _density._shot_path(html_path, viewport, seq=i)
                    el.screenshot(path=shot)
                    shots.append(shot)
            else:
                shot = _density._shot_path(html_path, viewport, seq=0)
                page.screenshot(path=shot, full_page=False)
                shots.append(shot)
        finally:
            browser.close()
    return shots


def count_screenshot_rounds(output_path):
    """统计该产物已完成的截图审视修正轮数（review_log 持久化读侧）。

    只计 verdict ∈ (PASS, FAIL) 的 screenshot_adversarial 条目（口径见模块
    docstring）；路径按 normcase+abspath 归一化匹配。
    """
    want = os.path.normcase(os.path.abspath(output_path))
    rounds = 0
    for entry in _review.read_review_log():
        if not isinstance(entry, dict):
            continue
        if entry.get("mode") != "screenshot_adversarial":
            continue
        if entry.get("verdict") not in ("PASS", "FAIL"):
            continue
        f = str(entry.get("file") or "")
        if os.path.normcase(os.path.abspath(f)) == want:
            rounds += 1
    return rounds


def _spec_summary_text(spec_path):
    """spec 摘要（三秒测试对照本页意图）；不可读降级为占位说明。"""
    if spec_path and os.path.exists(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = yaml.safe_load(f) or {}
            if isinstance(spec, dict):
                return _review._format_spec_summary(spec)
        except Exception:
            pass
    return "（无 spec——仅凭截图判断）"


_PROMPT_TEMPLATE = """你是截图对抗审视员。下面是这份方案定制页（crafted 页）的截图，独立会话，只看图与摘要，只找问题不打分。

## 本页意图（spec 摘要，供三秒测试对照）
{spec_summary}

## 审视三项（按优先级）
1. **三秒测试（主门）**：假设客户高层只看 3 秒——能否说出本页核心结论？
   说不出（无视觉主角/信息平铺/结论不显眼）→ three_second=FAIL；能 → PASS 并写出一句话结论。
2. **越轨反模式速查**：信息过载（元素/文字密度压过主表达）、低对比（文字与背景难分辨）等，逐条列入 antipatterns。
3. **与 standard 页的视觉连贯性**：字体层级/留白节奏/色彩体系是否与方案其余标准页同族（不要求同构），违和处列入 coherence。

## 输出格式（严格 JSON，不要解释）
{{"three_second": "PASS" 或 "FAIL", "three_second_conclusion": "3 秒结论一句话（≤30 字）",
"antipatterns": ["问题 - 位置"], "coherence": ["违和点"],
"verdict": "PASS" 或 "FAIL", "issues": ["问题1", "问题2"], "summary": "一句话总结（≤80 字）"}}

注意：
- verdict=PASS 仅当三项都找不到问题时；三秒测试 FAIL 则 verdict 必须 FAIL
- 禁止平衡评价；无问题则 summary 写「未发现问题」
"""


def _review_one_shot(shot, spec_summary, provider):
    """单张截图的 VLM 审视。返回 (parsed dict | None, raw_text)。"""
    prompt = _PROMPT_TEMPLATE.format(spec_summary=spec_summary)
    text = _vision_chat(prompt, shot, provider)
    if not text:
        return None, ""
    try:
        return _review._parse_review_json(text), text
    except (json.JSONDecodeError, TypeError):
        return None, text


def _emit(result, output_path, client_name, quiet):
    """收尾：预算记账 + 写 review_log + 打印（熔断/降级路径共用）。"""
    if result.get("_record_budget"):
        _review._budget_record(client_name, result["verdict"])
    result.pop("_record_budget", None)
    _review.write_review_log(result, output_path, client_name)
    if not quiet or result["verdict"] != "PASS":
        _review._print_adversarial_review(result, output_path)
    return result


def review_screenshot_adversarial(output_path, client_name=None, spec_path=None,
                                  quiet=False):
    """截图对抗审视（S9-2a）：crafted 页截图进 VLM，三秒测试主门，双熔断。

    熔断序：①预算熔断（同日连续 ≥3 次 ERROR，与文本 review 同一状态）→
    ②轮次熔断（该产物修正轮数 ≥ SCREENSHOT_MAX_ROUNDS；无 LLM 调用，
    不计预算 ERROR）。playwright 缺失 → SKIP 显式降级；VLM 不可得 → ERROR
    显式降级并计预算（两者都不是 PASS，也不产生内容 FAIL）。

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"SKIP"|"ERROR", "issues": [...],
               "summary": str, "mode": "screenshot_adversarial",
               "screenshot": [路径...], "screenshot_review_rounds": int,
               "max_rounds": int}
    """
    print("[review] 截图对抗审视模式（三秒测试主门；VLM 会漏细节，不承诺收敛）")
    result = {"verdict": "SKIP", "issues": [], "summary": "",
              "mode": "screenshot_adversarial", "screenshot": [],
              "screenshot_review_rounds": 0,
              "max_rounds": _review.SCREENSHOT_MAX_ROUNDS}

    # --- 0a. 预算熔断（复用 S6 实现，行为与文本 review 完全一致） ---
    fused = _review._budget_fused_result(client_name)
    if fused is not None:
        fused["mode"] = result["mode"]
        fused["max_rounds"] = result["max_rounds"]
        _review.write_review_log(fused, output_path, client_name)
        if not quiet:
            _review._print_adversarial_review(fused, output_path)
        return fused

    # --- 0b. 轮次熔断（修正循环 ≤3 轮；未发起 LLM 调用，不记预算） ---
    rounds = count_screenshot_rounds(output_path)
    result["screenshot_review_rounds"] = rounds
    decision = _review.screenshot_round_decision(rounds)
    if decision["action"] == "fuse":
        result["verdict"] = "ERROR"
        result["summary"] = decision["reason"]
        return _emit(result, output_path, client_name, quiet)

    if not os.path.exists(output_path):
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    # --- 1. 渲染截图（playwright 缺失/失败 → 显式降级 SKIP，不佯装通过） ---
    try:
        shots = _render_screenshot(output_path)
    except Exception as e:
        result["summary"] = (f"截图审视降级未执行（playwright 不可用: {e}）"
                             "——显式降级、非通过，请人工目检或修复渲染环境")
        result["issues"].append(
            "playwright 截图不可用，截图对抗审视未执行（显式降级，非通过）")
        return _emit(result, output_path, client_name, quiet)
    if not shots:
        result["summary"] = "截图审视降级未执行（未取得任何截图）——显式降级、非通过"
        return _emit(result, output_path, client_name, quiet)
    result["screenshot"] = shots

    # --- 2. 逐张 VLM 审视（独立会话；不可得 → ERROR 计预算，与文本 review 同轨） ---
    provider = _review._review_llm_kwargs().get("provider") or "minimax"
    spec_summary = _spec_summary_text(spec_path)
    parsed_list, raw_fail = [], ""
    for shot in shots:
        parsed, raw = _review_one_shot(shot, spec_summary, provider)
        if parsed is None:
            if raw:
                raw_fail = raw  # VLM 可达但返回非 JSON：按解析失败处理
            else:
                # VLM 不可得（未配 key/provider 失败/超时/host 模式）：ERROR 降级
                result["verdict"] = "ERROR"
                result["summary"] = ("VLM 判定不可得（未配置 key/provider 失败/"
                                     "超时/被声明跳过）——显式降级，判定未取得")
                result["_record_budget"] = True
                return _emit(result, output_path, client_name, quiet)
            break
        parsed_list.append(parsed)

    if not parsed_list and raw_fail:
        result["verdict"] = "FAIL"
        result["summary"] = f"VLM 返回非 JSON: {raw_fail[:200]}"
        result["issues"].append("截图审视结果解析失败")
        result["_record_budget"] = True
        return _emit(result, output_path, client_name, quiet)

    # --- 3. 合并判定（三秒测试主门 fail-closed；verdict 缺失不得当 PASS） ---
    result["verdict"] = "PASS"  # 有 parsed 结果才有判定权；单项 FAIL 下沉为整体 FAIL
    if raw_fail:
        result["issues"].append("截图审视部分截图返回非 JSON（该张结论缺失）")
    for parsed in parsed_list:
        verdict = parsed.get("verdict", "FAIL")
        if verdict == "FAIL":
            result["verdict"] = "FAIL"
        for key in ("antipatterns", "coherence"):
            items = parsed.get(key, [])
            if isinstance(items, list):
                for item in items:
                    result["issues"].append(f"[{key}] {item}")
            elif items:
                result["issues"].append(f"[{key}] {items}")
        if not result["summary"] and parsed.get("summary"):
            result["summary"] = parsed["summary"]
        if parsed.get("three_second_conclusion"):
            result["three_second_conclusion"] = str(parsed["three_second_conclusion"])
    if any(p.get("three_second") != "PASS" for p in parsed_list):
        result["verdict"] = "FAIL"
        result["issues"].append(
            "三秒测试未通过（主门）：高层 3 秒内说不出本页核心结论")

    result["screenshot_review_rounds"] = rounds + 1
    result["_record_budget"] = True
    return _emit(result, output_path, client_name, quiet)