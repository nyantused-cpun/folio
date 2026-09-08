# -*- coding: utf-8 -*-
"""A-3 反同壳检查测试（verify 观察模式）。"""

from _verify import check_shell_repetition


def _page(layout, types):
    """构造单页：layout + 元素类型序列（type 即可，检查只读 type/subtype）。"""
    return {"layout": layout, "elements": [{"type": t} for t in types]}


def _spec(pages):
    return {"pages": pages}


class TestShellRepetition:
    def test_three_same_shell_trigger(self):
        pages = [_page("P05", ["stat_cards"]) for _ in range(3)]
        msgs = check_shell_repetition(_spec(pages))
        assert len(msgs) == 1
        assert "[观察]" in msgs[0]
        assert "1-3" in msgs[0]  # 页面区间
        assert "P05" in msgs[0]  # 指纹描述含 layout
        assert "stat_cards" in msgs[0]  # 指纹描述含构件类型

    def test_two_same_not_trigger(self):
        pages = [_page("P05", ["stat_cards"]) for _ in range(2)]
        assert check_shell_repetition(_spec(pages)) == []

    def test_same_layout_diff_components_not_trigger(self):
        pages = [
            _page("P05", ["stat_cards"]),
            _page("P05", ["action_title"]),
            _page("P05", ["stat_cards"]),
        ]
        assert check_shell_repetition(_spec(pages)) == []

    def test_diagram_subtype_in_fingerprint(self):
        """diagram 指纹含 subtype：同 layout 同 diagram 类型但不同 subtype 不触发。"""
        pages = [
            {"layout": "P05", "elements": [
                {"type": "diagram", "diagram_type": "flow", "subtype": "sequence"}]},
            {"layout": "P05", "elements": [
                {"type": "diagram", "diagram_type": "flow", "subtype": "swimlane"}]},
            {"layout": "P05", "elements": [
                {"type": "diagram", "diagram_type": "flow", "subtype": "sequence"}]},
        ]
        assert check_shell_repetition(_spec(pages)) == []

    def test_three_same_diagram_trigger(self):
        pages = [
            {"layout": "P05", "elements": [
                {"type": "diagram", "diagram_type": "flow", "subtype": "sequence"}]}
            for _ in range(3)
        ]
        msgs = check_shell_repetition(_spec(pages))
        assert len(msgs) == 1
        assert "flow/sequence" in msgs[0]

    def test_non_dict_pages_ignored(self):
        pages = [
            _page("P05", ["stat_cards"]),
            None,
            _page("P05", ["stat_cards"]),
            _page("P05", ["stat_cards"]),
        ]
        msgs = check_shell_repetition(_spec(pages))
        # None 页被跳过，剩下 3 页连续同壳 → 仍触发
        assert len(msgs) == 1


class TestDensityDegradedNote:
    """#43：playwright 不可用时美学观察显式标注降级（曾静默过滤佯装通过）。"""

    def test_degraded_note_when_playwright_unavailable(self, tmp_path, monkeypatch):
        import _verify
        from _density import check_density_html as _orig  # noqa: F401
        html = tmp_path / "x.html"
        html.write_text(
            "<!DOCTYPE html><html><head><style>body{color:#333}</style></head>"
            "<body><p>密度降级标注测试</p></body></html>" + "<div>" + "x" * 600 + "</div>", encoding="utf-8")
        import _density
        monkeypatch.setattr(_density, "check_density_html",
                            lambda p, gate="verify": ["playwright 不可用，跳过密度检查"])
        ok, msg = _verify.verify_html(str(html))
        assert ok
        assert "显式降级" in msg
        assert "美学观察" in msg
