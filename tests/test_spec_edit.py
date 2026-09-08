# -*- coding: utf-8 -*-
"""_spec_edit.py 类型化增量变更直测（S2=V-A 批 T-1）。

覆盖 7 个函数：add_page / update_page / delete_page / add_element /
update_element / delete_element / _find_page（页定位私有助手）。
边界：越界索引、重复 id、元素不存在、校验失败不落盘、保存往返
（改完重新读回 spec.yml 验证持久化）。fixture 用 tmp_path 造最小 spec，
backup_before_generate 的 .bak/.versions 同步落在 tmp_path 内隔离。
"""
import os
import sys

import pytest

pytest.importorskip("yaml")

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

import yaml

from _spec_edit import (
    add_page, update_page, delete_page,
    add_element, update_element, delete_element,
    _find_page, _load_spec,
)


def _write_spec(tmp_path, pages=None):
    """最小合法 spec：confirmed + document + pages。"""
    if pages is None:
        pages = [
            {"id": "p01", "title": "首页", "layout": "bullets",
             "elements": [{"type": "bullets", "items": ["甲", "乙"]}]},
            {"id": "p02", "title": "次页", "layout": "bullets", "elements": []},
        ]
    spec = {"confirmed": True, "document": {"title": "直测"}, "pages": pages}
    p = tmp_path / "spec.yml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return str(p)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestFindPage:
    def test_found_returns_index_and_page(self, tmp_path):
        spec = _load_spec(_write_spec(tmp_path))
        idx, page = _find_page(spec, "p02")
        assert idx == 1 and page["title"] == "次页"

    def test_missing_returns_none_pair(self, tmp_path):
        spec = _load_spec(_write_spec(tmp_path))
        assert _find_page(spec, "nope") == (None, None)


class TestAddPage:
    def test_add_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_page(spec, "p03", "新页", layout="bullets",
                     elements=[{"type": "text", "content": "正文"}])
        assert r["ok"] and r["page_index"] == 2
        # 保存往返：重新读回验证持久化
        pages = _read(spec)["pages"]
        assert pages[2]["id"] == "p03"
        assert pages[2]["elements"][0]["type"] == "text"
        # 顶层字段保留
        assert _read(spec)["confirmed"] is True

    def test_duplicate_page_id_rejected(self, tmp_path):
        spec = _write_spec(tmp_path)
        before = _read(spec)
        r = add_page(spec, "p01", "重复页")
        assert not r["ok"] and r["page_index"] is None
        assert any("已存在" in e for e in r["errors"])
        assert _read(spec) == before  # 失败不落盘

    def test_invalid_element_rejected(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_page(spec, "p03", "坏页",
                     elements=[{"type": "bogus_type"}])
        assert not r["ok"]
        assert len(_read(spec)["pages"]) == 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            add_page(str(tmp_path / "nope.yml"), "p01", "T")


class TestUpdatePage:
    def test_update_title_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = update_page(spec, "p01", {"title": "改后标题", "layout": "cards"})
        assert r["ok"]
        page = _read(spec)["pages"][0]
        assert page["title"] == "改后标题" and page["layout"] == "cards"

    def test_page_not_found(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = update_page(spec, "p99", {"title": "X"})
        assert not r["ok"] and any("不存在" in e for e in r["errors"])

    def test_cannot_update_id(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = update_page(spec, "p01", {"id": "pXX"})
        assert not r["ok"] and any("不允许修改 id" in e for e in r["errors"])
        assert _read(spec)["pages"][0]["id"] == "p01"


class TestDeletePage:
    def test_delete_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = delete_page(spec, "p01")
        assert r["ok"] and r["deleted_index"] == 0
        pages = _read(spec)["pages"]
        assert [p["id"] for p in pages] == ["p02"]

    def test_page_not_found(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = delete_page(spec, "p99")
        assert not r["ok"] and r["deleted_index"] is None
        assert len(_read(spec)["pages"]) == 2


class TestAddElement:
    def test_append_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p02", {"type": "text", "content": "尾巴"})
        assert r["ok"] and r["element_index"] == 0
        elems = _read(spec)["pages"][1]["elements"]
        assert elems[0]["content"] == "尾巴"

    def test_insert_at_index(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p01", {"type": "text", "content": "插队"}, index=0)
        assert r["ok"] and r["element_index"] == 0
        elems = _read(spec)["pages"][0]["elements"]
        assert elems[0]["type"] == "text" and elems[1]["type"] == "bullets"

    def test_index_beyond_end_appends(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p01", {"type": "text", "content": "超界"}, index=99)
        assert r["ok"] and r["element_index"] == 1

    def test_negative_index_rejected(self, tmp_path):
        """P3 口径统一：负索引一律报越界，不走 list.insert 倒数语义。"""
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p01", {"type": "text", "content": "负"}, index=-1)
        assert not r["ok"] and any("越界" in e for e in r["errors"])
        assert len(_read(spec)["pages"][0]["elements"]) == 1

    def test_page_not_found(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p99", {"type": "text", "content": "X"})
        assert not r["ok"] and r["element_index"] is None

    def test_invalid_element_rejected(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = add_element(spec, "p01", {"type": "bullets"})  # 缺 items
        assert not r["ok"]
        assert len(_read(spec)["pages"][0]["elements"]) == 1


class TestUpdateElement:
    def test_update_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = update_element(spec, "p01", 0, {"items": ["丙", "丁", "戊"]})
        assert r["ok"]
        elems = _read(spec)["pages"][0]["elements"]
        assert elems[0]["items"] == ["丙", "丁", "戊"]

    @pytest.mark.parametrize("bad_index", [-1, 1, 99])
    def test_index_out_of_range(self, tmp_path, bad_index):
        spec = _write_spec(tmp_path)
        r = update_element(spec, "p01", bad_index, {"items": ["X"]})
        assert not r["ok"] and any("越界" in e for e in r["errors"])
        assert _read(spec)["pages"][0]["elements"][0]["items"] == ["甲", "乙"]

    def test_page_not_found(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = update_element(spec, "p99", 0, {"items": ["X"]})
        assert not r["ok"] and any("不存在" in e for e in r["errors"])

    def test_update_to_invalid_not_saved(self, tmp_path):
        """更新后重校验失败 → 不落盘（内存已改但文件保持原样）。"""
        spec = _write_spec(tmp_path)
        r = update_element(spec, "p01", 0, {"type": "bogus_type"})
        assert not r["ok"]
        assert _read(spec)["pages"][0]["elements"][0]["type"] == "bullets"


class TestDeleteElement:
    def test_delete_and_read_back(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = delete_element(spec, "p01", 0)
        assert r["ok"]
        assert _read(spec)["pages"][0]["elements"] == []

    @pytest.mark.parametrize("bad_index", [-2, 0, 5])
    def test_index_out_of_range(self, tmp_path, bad_index):
        # p02 无元素：任何索引（含 0、-2）都越界
        spec = _write_spec(tmp_path)
        r = delete_element(spec, "p02", bad_index)
        assert not r["ok"] and any("越界" in e for e in r["errors"])

    def test_page_not_found(self, tmp_path):
        spec = _write_spec(tmp_path)
        r = delete_element(spec, "p99", 0)
        assert not r["ok"] and any("不存在" in e for e in r["errors"])
