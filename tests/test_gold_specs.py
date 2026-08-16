# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""Gold spec 示范库资产回归（§8 v1.2 候选 4 三层示范库之 Gold spec 库）。

库文件由 _tools/extract_gold_specs.py 从已验收产出反向切片生成。防回归：
- 文件名 {diagram_type}__{subtype}.yml 与内容一致且是合法 subtype
- 全部过 schema.validate_element 零错误（注入 prompt 的示范本身必须合法）
- 头部注释含验收来源与"为什么好"
- 注入读取 load_gold_demo 截断后不超 token 预算
"""
import os

import yaml

from _outline_to_spec import (GOLD_DEMO_MAX_TOKENS, GOLD_SPECS_DIR,
                              _est_tokens, load_gold_demo)
from _renderer.schema import DIAGRAM_SCHEMA, validate_element

# 截断标注行（"# …（超出示范 token 预算，余下截断）"）约 16 tokens，预算外余量
TRUNC_MARKER_SLACK = 20

# v1.2-4 要求优先保证的高频类
HIGH_FREQUENCY = [("flow", "sequence"), ("architecture", "4a"),
                  ("architecture", "layered"), ("matrix", "fit_gap"),
                  ("timeline", "horizontal")]


def _gold_files():
    assert os.path.isdir(GOLD_SPECS_DIR), f"gold spec 库不存在: {GOLD_SPECS_DIR}"
    return sorted(f for f in os.listdir(GOLD_SPECS_DIR) if f.endswith(".yml"))


def _load(fn):
    with open(os.path.join(GOLD_SPECS_DIR, fn), encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestGoldSpecAssets:
    def test_library_not_empty(self):
        assert _gold_files(), "gold spec 库为空"

    def test_high_frequency_subtypes_covered(self):
        covered = {fn[:-4] for fn in _gold_files()}
        for dt, st in HIGH_FREQUENCY:
            assert f"{dt}__{st}" in covered, f"高频 subtype 缺 gold: {dt}/{st}"

    def test_filename_matches_schema_and_content(self):
        for fn in _gold_files():
            dt, st = fn[:-4].split("__")
            assert st in DIAGRAM_SCHEMA.get(dt, {}), \
                f"{fn} 不是合法 diagram_type/subtype"
            elem = _load(fn)
            assert elem.get("type") == "diagram", f"{fn} 不是 diagram 元素"
            assert elem.get("diagram_type") == dt, f"{fn} 内容与文件名不符"
            assert elem.get("subtype") == st, f"{fn} 内容与文件名不符"

    def test_all_gold_pass_schema_zero_errors(self):
        for fn in _gold_files():
            errs = validate_element(_load(fn))
            assert errs == [], f"{fn} schema 校验未过: {errs}"

    def test_header_comments_present(self):
        for fn in _gold_files():
            with open(os.path.join(GOLD_SPECS_DIR, fn), encoding="utf-8") as f:
                text = f.read()
            assert "# 验收来源：" in text, f"{fn} 缺验收来源注释"
            assert "# 为什么好：" in text, f"{fn} 缺为什么好注释"

    def test_injection_within_token_budget(self):
        for fn in _gold_files():
            dt, st = fn[:-4].split("__")
            demo = load_gold_demo(dt, st)
            assert demo, f"{fn} 注入加载为空"
            assert _est_tokens(demo) <= GOLD_DEMO_MAX_TOKENS + TRUNC_MARKER_SLACK, \
                f"{fn} 注入超 token 预算: {_est_tokens(demo)}"
