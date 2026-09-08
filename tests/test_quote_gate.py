# -*- coding: utf-8 -*-
"""P1-4 报价门禁测试。"""
import yaml


def _write_spec(path, quote):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"quote": quote}, f, allow_unicode=True, sort_keys=False)


def test_check_build_blocks_missing_quantity_unit_tax(tmp_path):
    from _quote_gate import check_build
    spec = tmp_path / "quote.yml"
    _write_spec(spec, {
        "client": "测试客户",
        "tax_rate": None,
        "sheets": [{
            "sections": [{
                "id": "modules",
                "items": [{"name": "模块A", "quantity": 0}],
            }],
        }],
    })
    issues = check_build(str(spec))
    texts = " ".join(issues)
    assert "Q1" in texts
    assert "Q2" in texts


def test_check_build_passes_valid_quote(tmp_path):
    from _quote_gate import check_build
    spec = tmp_path / "quote.yml"
    _write_spec(spec, {
        "client": "测试客户",
        "tax_rate": 0.06,
        "sheets": [{
            "sections": [{
                "id": "modules",
                "items": [{"name": "模块A", "quantity": 1, "unit": "套"}],
            }],
        }],
    })
    assert check_build(str(spec)) == []


def test_verify_quote_warns_missing_meta(tmp_path):
    from _quote_gate import check_verify
    spec = tmp_path / "quote.yml"
    _write_spec(spec, {
        "client": "测试客户",
        "sheets": [{"sections": [{"items": [{"name": "模块A", "quantity": 1}]}]}],
    })
    issues, warnings = check_verify(str(spec))
    assert issues == []
    assert any("Q3" in w for w in warnings)
    assert any("Q5" in w for w in warnings)
