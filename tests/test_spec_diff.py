# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""spec-diff 结构化对比回归测试（§八 3.2）。

退出码语义：0 无差异 / 1 有差异 / 2 错误。
"""
import pytest
import yaml

from _spec_diff import diff_specs, format_diff, has_changes, cmd_spec_diff


def _spec(**overrides):
    spec = {
        "project": "测试项目",
        "style": "enterprise",
        "confirmed": True,
        "document": {"title": "测试方案", "subtitle": "副标题"},
        "pages": [
            {"id": "p01", "title": "第一页", "elements": [
                {"type": "text", "content": "正文一"},
                {"type": "cards", "cards": [
                    {"title": "卡1", "body": "体1"},
                    {"title": "卡2", "body": "体2"},
                ]},
            ]},
            {"id": "p02", "title": "第二页", "elements": [
                {"type": "bullets", "items": ["甲", "乙"]},
            ]},
            {"id": "p03", "title": "第三页", "elements": [
                {"type": "text", "content": "正文三"},
            ]},
        ],
    }
    spec.update(overrides)
    return spec


def _write(tmp_path, name, spec):
    path = tmp_path / name
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, sort_keys=False)
    return str(path)


class TestDiffSpecs:
    def test_identical_specs_no_diff(self):
        report = diff_specs(_spec(), _spec())
        assert not has_changes(report)
        assert "无差异" in format_diff(report, "a.yml", "b.yml")

    def test_top_level_changes(self):
        b = _spec(style="tech", confirmed=False)
        b["document"]["title"] = "新标题"
        report = diff_specs(_spec(), b)
        assert has_changes(report)
        paths = {path for _, path, _, _ in report["top"]}
        assert {"style", "confirmed", "document.title"} <= paths
        text = format_diff(report, "a", "b")
        assert '"enterprise" -> "tech"' in text
        assert "True -> False" in text

    def test_page_added_removed(self):
        b = _spec()
        b["pages"] = b["pages"][:2]  # 删 p03
        b["pages"].append({"id": "p04", "title": "新页", "elements": []})
        report = diff_specs(_spec(), b)
        assert [pid for pid, _ in report["pages_removed"]] == ["p03"]
        assert [pid for pid, _ in report["pages_added"]] == ["p04"]
        text = format_diff(report, "a", "b")
        assert "新增页 p04" in text and "删除页 p03" in text

    def test_page_reorder(self):
        b = _spec()
        b["pages"].insert(0, b["pages"].pop(2))  # p03 移到最前
        report = diff_specs(_spec(), b)
        moved = {pid for pid, _, _ in report["pages_reordered"]}
        # LIS 语义：p01/p02 相对顺序保持，只有 p03 是被移动的页
        assert moved == {"p03"}
        old_pos, new_pos = [(o, n) for pid, o, n in report["pages_reordered"]][0]
        assert (old_pos, new_pos) == (3, 1)

    def test_no_reorder_when_page_inserted(self):
        """新增页不应导致其余页被误报重排（相对顺序未变）。"""
        b = _spec()
        b["pages"].insert(1, {"id": "pXX", "title": "插入页", "elements": []})
        report = diff_specs(_spec(), b)
        assert report["pages_reordered"] == []

    def test_element_field_change(self):
        b = _spec()
        b["pages"][0]["elements"][1]["cards"][0]["title"] = "卡1改"
        report = diff_specs(_spec(), b)
        assert len(report["pages_changed"]) == 1
        entry = report["pages_changed"][0]
        assert entry["id"] == "p01"
        idx, etype, changes = entry["elements_changed"][0]
        assert idx == 1 and etype == "cards"
        paths = [path for _, path, _, _ in changes]
        assert "cards[0].title" in paths
        text = format_diff(report, "a", "b")
        assert "elements[1] (cards)" in text
        assert '"卡1" -> "卡1改"' in text

    def test_element_added_removed(self):
        b = _spec()
        b["pages"][1]["elements"].append({"type": "text", "content": "追加"})
        report = diff_specs(_spec(), b)
        entry = report["pages_changed"][0]
        assert entry["id"] == "p02"
        assert entry["elements_added"] == [(1, 'text:"追加"')]
        # 反向对比应报删除
        report_rev = diff_specs(b, _spec())
        entry_rev = report_rev["pages_changed"][0]
        assert entry_rev["elements_removed"] == [(1, 'text:"追加"')]

    def test_element_type_change_is_replace(self):
        """同 index 但 type 不同 → 报删+增，不报"改"。"""
        b = _spec()
        b["pages"][1]["elements"][0] = {"type": "text", "content": "换成文本"}
        report = diff_specs(_spec(), b)
        entry = report["pages_changed"][0]
        assert entry["elements_removed"] and entry["elements_added"]
        assert not entry["elements_changed"]

    def test_long_text_truncated(self):
        b = _spec()
        b["pages"][0]["elements"][0]["content"] = "长" * 200
        text = format_diff(diff_specs(_spec(), b), "a", "b")
        assert "…" in text
        assert "长" * 200 not in text  # 长文本不刷屏

    def test_page_field_change(self):
        b = _spec()
        b["pages"][0]["title"] = "第一页改"
        report = diff_specs(_spec(), b)
        entry = report["pages_changed"][0]
        assert any(path == "title" for _, path, _, _ in entry["field_changes"])


class TestCmdSpecDiff:
    def _run(self, tmp_path, spec_a, spec_b):
        pa = _write(tmp_path, "a.yml", spec_a)
        pb = _write(tmp_path, "b.yml", spec_b)
        args = type("A", (), {"spec_a": pa, "spec_b": pb})()
        with pytest.raises(SystemExit) as exc:
            cmd_spec_diff(args)
        return exc.value.code

    def test_exit_0_no_diff(self, tmp_path):
        assert self._run(tmp_path, _spec(), _spec()) == 0

    def test_exit_1_has_diff(self, tmp_path):
        assert self._run(tmp_path, _spec(), _spec(style="gov")) == 1

    def test_exit_2_missing_file(self, tmp_path, capsys):
        args = type("A", (), {"spec_a": str(tmp_path / "无此文件.yml"),
                              "spec_b": str(tmp_path / "b.yml")})()
        with pytest.raises(SystemExit) as exc:
            cmd_spec_diff(args)
        assert exc.value.code == 2
        assert "错误" in capsys.readouterr().out

    def test_exit_2_invalid_spec(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("- 列表\n- 顶层不是字典\n", encoding="utf-8")
        good = _write(tmp_path, "good.yml", _spec())
        args = type("A", (), {"spec_a": str(bad), "spec_b": good})()
        with pytest.raises(SystemExit) as exc:
            cmd_spec_diff(args)
        assert exc.value.code == 2


class TestCliWiring:
    """spec-diff 必须注册进 _cli 的 parser 与 dispatch（_PRESALES_CLI_INVOKED 守卫惯例）。"""

    def test_registered_in_parser_and_dispatch(self):
        import _cli
        args = _cli.build_parser().parse_args(["spec-diff", "a.yml", "b.yml"])
        assert args.command == "spec-diff"
        assert args.spec_a == "a.yml" and args.spec_b == "b.yml"
        assert "spec-diff" in _cli._build_dispatch()
