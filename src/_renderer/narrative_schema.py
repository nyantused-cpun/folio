# -*- coding: utf-8 -*-
"""叙事设计单 schema 校验（阶段 2-1，开发计划书 §2.1：
docs/视觉生产线知识体系重构_开发计划_2026-09-03.md）。

叙事设计单（output/{客户}/{客户}_叙事设计_v{N}.yml）是 deck 级设计层的
落地物：受众 / 阅读行为 / 页数预算 / 叙事弧线 / 页面地图，先于 spec 产出；
spec 通过顶层可选字段 narrative_ref 溯源（渲染不消费，见 schema.py）。

枚举单点原则：reading 复用 schema.CONTAINERS，「讲法」复用
schema.COMPOSITIONS（D-122 十二值），layout 复用 schema.PAGE_LAYOUTS
键集，graphic（"族/subtype"）合法性用 schema.all_subtypes() 判定——
本文件不复制任何枚举值。

校验风格同 schema.validate_element：逐字段收集错误返回列表（空=合法），
不抛异常；错误信息中文并带字段路径定位（如 page_map[2].layout: 非法值 'P20'）。
"""

import os

import yaml

from _renderer import schema

# 必填非空字符串字段（其余必填项有类型/枚举约束，单独校验）
_REQUIRED_STR_FIELDS = ("audience", "arc")


def _validate_graphic(graphic, where):
    """graphic 字段：null（无意图）或 "族/subtype" 字符串（如 matrix/fit_gap）。"""
    if graphic is None:
        return []
    if not isinstance(graphic, str):
        return [f"{where}.graphic: 必须是 null 或 '族/subtype' 字符串，"
                f"实际为 {type(graphic).__name__}"]
    if graphic.count("/") != 1:
        return [f"{where}.graphic: 格式应为 '族/subtype'（如 matrix/fit_gap），"
                f"实际 '{graphic}'"]
    family, subtype = graphic.split("/")
    legal = schema.all_subtypes()
    families = sorted({dt for dt, _ in legal})
    if family not in families:
        return [f"{where}.graphic: 未知族 '{family}'"
                f"（合法值：{'/'.join(families)}）"]
    if (family, subtype) not in legal:
        subs = "/".join(sorted(st for dt, st in legal if dt == family))
        return [f"{where}.graphic: subtype '{subtype}' 不属于 {family}"
                f"（合法值：{subs}）"]
    return []


def validate_narrative(doc: dict) -> list:
    """校验叙事设计单，返回错误描述列表（空=合法）。

    逐字段收集错误，不抛异常；doc 非 dict 时直接返回单条错误。
    """
    if not isinstance(doc, dict):
        return ["叙事设计单必须是 YAML 对象（键值对）"]
    errors = []

    for field in _REQUIRED_STR_FIELDS:
        value = doc.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field}: 必填非空字符串，实际 {value!r}")

    reading = doc.get("reading")
    if reading not in schema.CONTAINERS:
        errors.append(f"reading: 非法值 '{reading}'"
                      f"（合法值：{'/'.join(schema.CONTAINERS)}）")

    budget = doc.get("page_budget")
    if isinstance(budget, bool) or not isinstance(budget, int):
        errors.append(f"page_budget: 必填正整数，实际 {budget!r}")
    elif budget <= 0:
        errors.append(f"page_budget: 必须 >0，实际 {budget}")

    scene = doc.get("scene")
    if scene is not None and (not isinstance(scene, str) or not scene.strip()):
        errors.append(f"scene: 可选非空字符串，实际 {scene!r}")

    page_map = doc.get("page_map")
    if not isinstance(page_map, list) or not page_map:
        errors.append("page_map: 必填非空列表")
        return errors

    seen = {}  # page -> 首次出现的下标（全表唯一性校验）
    for i, item in enumerate(page_map):
        where = f"page_map[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: 必须是对象（page/beat/讲法/layout）")
            continue
        page = item.get("page")
        if not isinstance(page, str) or not page.strip():
            errors.append(f"{where}.page: 必填非空字符串，实际 {page!r}")
        elif page in seen:
            errors.append(f"{where}.page: '{page}' 与 page_map[{seen[page]}] 重复")
        else:
            seen[page] = i
        beat = item.get("beat")
        if not isinstance(beat, str) or not beat.strip():
            errors.append(f"{where}.beat: 必填非空字符串，实际 {beat!r}")
        comp = item.get("讲法")
        if comp not in schema.COMPOSITIONS:
            errors.append(f"{where}.讲法: 非法值 '{comp}'"
                          f"（合法值：{'/'.join(schema.COMPOSITIONS)}）")
        layout = item.get("layout")
        if layout not in schema.PAGE_LAYOUTS:
            errors.append(f"{where}.layout: 非法值 '{layout}'"
                          f"（合法值：{'/'.join(sorted(schema.PAGE_LAYOUTS))}）")
        errors.extend(_validate_graphic(item.get("graphic"), where))
        # 表达模式（2026-09-07 立项）：expression_mode/depth/density 字段；
        # crafted（定制页）必填 primary_expression / static_equivalent / density
        em = item.get("expression_mode", "standard")
        if em not in ("standard", "crafted"):
            errors.append(f"{where}.expression_mode: 非法值 '{em}'"
                          f"（合法值：standard/crafted）")
        depth = item.get("depth")
        if depth is not None and depth not in ("short", "standard", "deep"):
            errors.append(f"{where}.depth: 非法值 '{depth}'"
                          f"（合法值：short/standard/deep）")
        density = item.get("density")
        if density is not None and density not in ("high", "medium", "low"):
            errors.append(f"{where}.density: 非法值 '{density}'"
                          f"（合法值：high/medium/low）")
        if em == "crafted":
            for field in ("primary_expression", "static_equivalent", "density"):
                v = item.get(field)
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"{where}.{field}: crafted 页必填非空字符串")
    return errors


def load_and_validate(path: str) -> tuple:
    """加载 YAML 并校验，返回 (doc, errors)。

    文件不存在 / 解析失败 / 文件为空 / 顶层非对象 → (None, [错误描述])；
    解析成功但校验有错 → (doc, errors)，doc 仍返回供调用方排查。
    """
    if not os.path.isfile(path):
        return None, [f"文件不存在: {path}"]
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return None, [f"YAML 解析失败: {path}（{exc}）"]
    except OSError as exc:
        return None, [f"文件读取失败: {path}（{exc}）"]
    if doc is None:
        return None, [f"文件为空: {path}"]
    if not isinstance(doc, dict):
        return None, [f"{path}: 顶层必须是 YAML 对象（键值对）"]
    return doc, validate_narrative(doc)


# ======================================================================
# S8-A 2×3 合规矩阵（2026-09-07，crafted-track.md「2×3 合规矩阵」节）：
# weaver×crafted 默认禁止 + 特批通道（阻断级）、每 deck crafted ≤2 页
# （观察级）升级条件: 实测 >2 页 deck 占比上升 → 升阻断（长期纪律保留；盘点#5）。
# 检查单点在本函数组；构建侧 Renderer.__init__ 前置拦截 +
# verify 侧 verify_spec_layout_data 汇聚（与叙事一致性检查同门）。
# ======================================================================

# weaver 体系唯一判定键：spec 主题经 theme.normalize_theme_name 归一后
# == "weaver_blue" 即 weaver（泛微官方 VI）体系；LEGACY_STYLE_TO_THEME
# 无 weaver 项，未知/缺省回退 consulting_kpmg（generic 体系）
_WEAVER_THEME_KEY = "weaver_blue"

# 每 deck crafted 页默认上限（观察级告警阈值；crafted-track.md 使用纪律 1）升级条件: 实测 >2 页 deck 占比上升 → 升阻断（盘点#5）
CRAFTED_MAX_PAGES = 2

# weaver×crafted 特批标记（spec 顶层字段；语义=「特批已按官方模板精神
# 审查」，须在 decisions.md 登记；仅 spec 级字段，不是全局开关）
APPROVAL_FIELD = "crafted_special_approval"


def resolve_spec_theme_key(spec):
    """spec 顶层主题名归一为 THEMES 键（theme 优先，缺省回退旧 style）。"""
    from _renderer.theme import normalize_theme_name
    raw = spec.get("theme")
    if not isinstance(raw, str) or not raw.strip():
        raw = spec.get("style")
    return normalize_theme_name(raw if isinstance(raw, str) else None)


def collect_crafted_pages(spec, spec_path=None, doc=None):
    """收集 deck 内 crafted 页标签（保序去重，id 优先、缺 id 用 pages[i]）。

    双源并集（不会漏拦）：
    - raw_html 元素所在页恒为 crafted（crafted 页唯一容器，硬信号兜底，
      无叙事单的旧 spec 也能计数）；
    - 叙事单 page_map expression_mode=crafted 的页（设计意图源，需
      spec_path 解析 narrative_ref 同目录设计单；doc 直传时免读盘）。
    设计单不可读时静默降级——硬信号已兜底，不可读告警由
    check_narrative_consistency 负责，此处不重复。
    """
    if not isinstance(spec, dict):
        return []
    labels, seen = [], set()

    def _add(label):
        if label and label not in seen:
            seen.add(label)
            labels.append(label)

    pages = [p for p in (spec.get("pages") or []) if isinstance(p, dict)]
    for i, page in enumerate(pages):
        elements = page.get("elements") or []
        if any(isinstance(e, dict) and e.get("type") == "raw_html"
               for e in elements):
            _add(str(page.get("id")) if page.get("id") else f"pages[{i}]")
    if doc is None and spec_path and spec.get("narrative_ref"):
        doc_path = os.path.join(os.path.dirname(os.path.abspath(spec_path)),
                                str(spec.get("narrative_ref")))
        doc, _errs = load_and_validate(doc_path)
    if isinstance(doc, dict):
        crafted_ids = {str(m.get("page"))
                       for m in (doc.get("page_map") or [])
                       if isinstance(m, dict)
                       and m.get("expression_mode") == "crafted"
                       and m.get("page")}
        if crafted_ids:
            for page in pages:
                pid = str(page.get("id") or "")
                if pid and pid in crafted_ids:
                    _add(pid)
    return labels


def check_compliance_matrix(spec, spec_path=None):
    """2×3 合规矩阵机械执行：返回 (errors, warnings)（风格同
    check_narrative_consistency，errors 阻断 / warnings 观察）。

    - weaver（泛微官方 VI）× crafted：默认禁止——error（阻断），除非 spec
      顶层 APPROVAL_FIELD=true 特批放行（特批须 decisions.md 登记）；
    - syzygit / generic × crafted：可用——本检查不设限，VI 冻结值机检
      （_spec_hex）与反模式机检（_density）不豁免也不在此重复；
    - 每 deck crafted >CRAFTED_MAX_PAGES 页：warning（核心页稀缺性，
      建议拆页或回退 standard）。
    存量无 crafted 页的 spec 零影响（两项检查都先看 crafted 集合）。
    """
    errors, warnings = [], []
    crafted = collect_crafted_pages(spec, spec_path=spec_path)
    if not crafted:
        return errors, warnings
    if (resolve_spec_theme_key(spec) == _WEAVER_THEME_KEY
            and spec.get(APPROVAL_FIELD) is not True):
        page_list = "、".join(crafted)
        errors.append(
            "weaver（泛微官方 VI）主题默认禁止 crafted 定制页（2×3 合规矩阵，"
            f"当前 {len(crafted)} 页：{page_list}）；特批通道：spec 顶层置 "
            f"{APPROVAL_FIELD}: true，并在 decisions.md 登记特批审查"
            "（按官方模板精神，不逐像素 VI）")
    if len(crafted) > CRAFTED_MAX_PAGES:
        warnings.append(
            f"[观察] crafted 定制页 {len(crafted)} 页 > 每 deck 默认上限 "
            f"{CRAFTED_MAX_PAGES} 页（核心页稀缺性）：建议拆页或回退 standard")
    return errors, warnings
