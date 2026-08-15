# -*- coding: utf-8 -*-
"""D-123：save 钩子案例卡自动提取测试（幂等 + 结构指纹）。"""

import os

import _session


def _make_spec(path, pages):
    import yaml
    spec = {"document": {"title": "测试方案"},
            "pages": pages}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True)


class TestCaseCards:
    def test_extract_and_idempotent(self, tmp_path, monkeypatch):
        out = tmp_path / "output" / "测试客户"
        out.mkdir(parents=True)
        _make_spec(out / "测试客户_方案_v1.spec.yml", [
            {"id": "p1", "title": "t", "composition": ["data_narrative"],
             "elements": [{"type": "kpi_cards", "cards": [{"label": "x", "to": "1"}]}]},
            {"id": "p2", "title": "t", "composition": ["architecture_board"],
             "elements": [{"type": "diagram", "diagram_type": "architecture",
                           "subtype": "4a"}]},
        ])
        import _paths
        monkeypatch.setattr(_paths, "OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr(_paths, "SCRIPT_DIR", str(tmp_path))
        n = _session._extract_case_cards("测试客户")
        assert n == 1
        card_dir = os.path.join(str(tmp_path), "_knowledge", "cases")
        files = os.listdir(card_dir)
        assert len(files) == 1
        with open(os.path.join(card_dir, files[0]), encoding="utf-8") as f:
            content = f.read()
        assert "data_narrative" in content and "architecture_board" in content
        assert "kpi_cards" in content and "diagram" in content
        # 幂等：再跑一次不新增
        n2 = _session._extract_case_cards("测试客户")
        assert n2 == 0
        assert len(os.listdir(card_dir)) == 1
