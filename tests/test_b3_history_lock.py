# -*- coding: utf-8 -*-
"""B3 批 A8 组回归测试：
1. P1-15 task_history 全局锁（D1：.folio/logs/.task_history.lock 复用 _save_lock 机制）
2. P2 conflict 标记日期口径统一（memory_guard 标题行优先，与 theme_guard 锚定同块）
3. P2 _graph 增量 hash 语义（成功才记 hash + 决策编辑/删除传播 + outputs 读失败不误删）
"""
import json
import threading


import _session
import _cli_cmds_mem
import _verify_hook
from _save_lock import acquire_save_lock, release_save_lock
from _memory_guard import detect_conflict
from _theme_guard import _append_conflict_flag
from _graph import _incremental_update


# ---------------------------------------------------------------------------
# P1-15 全局锁机制与三处接线
# ---------------------------------------------------------------------------

class TestGlobalTaskHistoryLock(object):
    def test_acquire_release_custom_lock_name(self, tmp_path):
        fd = acquire_save_lock(str(tmp_path), lock_name=".task_history.lock")
        assert fd is not None
        assert (tmp_path / ".task_history.lock").exists()
        release_save_lock(str(tmp_path), fd, lock_name=".task_history.lock")
        assert not (tmp_path / ".task_history.lock").exists()

    def test_lock_name_independence(self, tmp_path):
        fd1 = acquire_save_lock(str(tmp_path), lock_name=".save_lock")
        fd2 = acquire_save_lock(str(tmp_path), lock_name=".task_history.lock")
        assert fd1 is not None and fd2 is not None
        release_save_lock(str(tmp_path), fd1)
        release_save_lock(str(tmp_path), fd2, lock_name=".task_history.lock")

    def test_second_acquirer_times_out(self, tmp_path):
        fd = acquire_save_lock(str(tmp_path), lock_name=".task_history.lock")
        try:
            assert acquire_save_lock(str(tmp_path), timeout=1.0,
                                     lock_name=".task_history.lock") is None
        finally:
            release_save_lock(str(tmp_path), fd, lock_name=".task_history.lock")

    def test_update_task_history_concurrent_no_lost_update(self, tmp_path, monkeypatch):
        """4 客户线程并发更新 task_history：20 条 verify 全部落盘且 JSON 合法。"""
        logs = tmp_path / "logs"
        clients = tmp_path / "clients"
        logs.mkdir()
        clients.mkdir()
        history_path = logs / "task_history.json"
        history_path.write_text(json.dumps(
            [{"date": "2026-09-06", "project": "client:A", "verify": {}}],
            ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(_verify_hook, "TASK_HISTORY", str(history_path))
        monkeypatch.setattr(_verify_hook, "LOGS_DIR", str(logs))
        monkeypatch.setattr(_verify_hook, "CLIENTS_DIR", str(clients))

        errors = []

        def _worker(tag):
            try:
                for i in range(5):
                    _verify_hook.update_task_history(
                        f"output/{tag}{i}.html", True, "html", client_name=tag)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(t,)) for t in "ABCD"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        data = json.loads(history_path.read_text(encoding="utf-8"))
        verify_keys = set(data[-1].get("verify", {}).keys())
        assert len(verify_keys) == 20, f"丢更新：只剩 {len(verify_keys)} 条"
        assert not (logs / ".task_history.lock").exists()  # 锁不残留

    def test_global_lock_wiring_present(self):
        """三处写点接线静态哨兵：源码含同款全局锁调用。"""
        for src in (_session.__file__, _cli_cmds_mem.__file__):
            code = open(src, encoding="utf-8").read()
            assert '.task_history.lock' in code, f"{src} 未接全局锁"


# ---------------------------------------------------------------------------
# P2 conflict 日期口径统一
# ---------------------------------------------------------------------------

OLD_FORMAT_DECISIONS = """# 决策索引

## 2026-08-26 旧主题
- **决策**: 旧内容A
- 参考: 见 [2026-01-01] 另一份文档

### D-002 · 新主题
- **日期**: 2026-09-01
- **决策**: 新内容
"""


class TestConflictDateAlignment(object):
    def test_old_date_from_heading_not_body(self, tmp_path):
        """旧格式块（无括号日期标题）：old_date 取标题日期，不被正文 [日期] 带偏。"""
        p = tmp_path / "decisions.md"
        p.write_text(OLD_FORMAT_DECISIONS, encoding="utf-8")
        result = detect_conflict("旧主题", "不同的新决策", str(p))
        assert result["conflict"] is True
        assert result["old_date"] == "2026-08-26"

    def test_marker_lands_in_same_block(self, tmp_path):
        """两模块同口径后：pending 标记插进 detect_conflict 锚定的同一块。"""
        p = tmp_path / "decisions.md"
        p.write_text(OLD_FORMAT_DECISIONS, encoding="utf-8")
        result = detect_conflict("旧主题", "不同的新决策", str(p))
        _append_conflict_flag(str(p), result["old_date"], "旧主题")
        content = p.read_text(encoding="utf-8")
        assert content.count("<!-- conflict: pending -->") == 1
        marker_pos = content.index("<!-- conflict: pending -->")
        assert content.index("旧内容A") < marker_pos < content.index("### D-002")


# ---------------------------------------------------------------------------
# P2 _graph 增量 hash 语义
# ---------------------------------------------------------------------------

def _decision_block(num, title, text, date="2026-09-01"):
    return (f"### D-{num:03d} · {title}\n- **日期**: {date}\n"
            f"- **决策**: {text}\n- persistence: permanent\n- scope: client\n")


def _existing_decision_node(num, title, text):
    return {
        "id": f"n{num:03d}", "type": "decision", "title": title,
        "summary": text[:200], "details_path": f"decisions.md#{title[:30]}",
        "metadata": {"date": "2026-09-01", "reason": "", "persistence": "permanent",
                     "scope": "client", "subtype": "direction", "decision_num": num,
                     "source": "", "task_id": "", "status": "", "superseded_by": ""},
    }


class TestGraphIncrementalHash(object):
    def _run(self, tmp_path, decisions_text, oij_payload, existing_nodes,
             existing_hashes=None):
        client = "测试客户"
        decisions_path = tmp_path / "decisions.md"
        if decisions_text is not None:
            decisions_path.write_text(decisions_text, encoding="utf-8")
        oij_path = tmp_path / "outputs_index.json"
        if oij_payload is not None:
            oij_path.write_text(json.dumps(oij_payload, ensure_ascii=False),
                                encoding="utf-8")
        insights = tmp_path / "insights"
        insights.mkdir(exist_ok=True)
        existing_graph = {
            "client": client, "industry": "", "created": "2026-09-01",
            "nodes": existing_nodes, "edges": [],
            "_source_hashes": existing_hashes or {},
        }
        new_hashes = {"decisions.md": "h-dec", "outputs_index.json": "h-oij"}
        graph = _incremental_update(
            client, existing_graph, new_hashes, str(decisions_path), str(oij_path),
            str(insights),
            lambda c: str(tmp_path / "client_graph.json"),
            lambda c: str(tmp_path / "client_index.md"))
        return graph

    def test_decision_deleted_propagates(self, tmp_path):
        """存量决策在 decisions.md 中被删除 -> 节点从图移除。"""
        node = _existing_decision_node(7, "拍板方向A", "旧内容")
        graph = self._run(tmp_path, "### D-002 · 另一条\n- **决策**: x\n",
                          {"outputs": []}, [node])
        ids = [n["id"] for n in graph["nodes"] if n["type"] == "decision"]
        assert "n007" not in ids

    def test_decision_edit_same_key_refreshes(self, tmp_path):
        """同 D-NNN 编辑内容 -> 节点原位刷新（保 id），不重复追加。"""
        node = _existing_decision_node(7, "拍板方向A", "旧内容")
        graph = self._run(
            tmp_path, _decision_block(7, "拍板方向A", "新内容已修订"),
            {"outputs": []}, [node])
        dec = [n for n in graph["nodes"] if n["type"] == "decision"]
        assert len(dec) == 1 and dec[0]["id"] == "n007"
        assert "新内容已修订" in dec[0]["summary"]

    def test_decision_edit_new_key_adds_and_keeps_old(self, tmp_path):
        """编辑改号（旧 key 消失）：旧节点移除、新节点追加（对账语义）。"""
        node = _existing_decision_node(7, "拍板方向A", "旧内容")
        graph = self._run(
            tmp_path, _decision_block(8, "拍板方向B", "改口后的决策"),
            {"outputs": []}, [node])
        dec = [n for n in graph["nodes"] if n["type"] == "decision"]
        assert [n["id"] for n in dec] == ["n008"]

    def test_decisions_read_failure_keeps_nodes_and_skips_hash(self, tmp_path):
        """decisions 提取失败：决策节点保留、hash 不落（下次重试）。"""
        node = _existing_decision_node(7, "拍板方向A", "旧内容")
        bad_dir = tmp_path / "as_dir"
        bad_dir.mkdir()  # 对目录 open() 必失败
        graph = _incremental_update(
                "测试客户",
                {"client": "t", "nodes": [node], "edges": [], "_source_hashes": {}},
                {"decisions.md": "h-dec", "outputs_index.json": "h-oij"},
                str(bad_dir),  # decisions_path = 目录 -> 读失败
                str(tmp_path / "oij.json"),  # 不存在 -> outputs 无变化路径
                str(tmp_path / "insights"),
                lambda c: str(tmp_path / "client_graph.json"),
                lambda c: str(tmp_path / "client_index.md"))
        assert [n["id"] for n in graph["nodes"] if n["type"] == "decision"] == ["n007"]
        assert "decisions.md" not in graph["_source_hashes"]

    def test_outputs_read_failure_no_mass_remove(self, tmp_path):
        """outputs_index 读失败：存量 output 原样保留（不误标 removed）、hash 不落。"""
        node = _existing_decision_node(7, "拍板方向A", "x")
        out_node = {"id": "n901", "type": "output", "title": "output/x.html",
                    "details_path": "output/x.html", "metadata": {"status": "done"}}
        bad_dir = tmp_path / "oij_dir"
        bad_dir.mkdir()
        graph = _incremental_update(
            "测试客户",
            {"client": "t", "nodes": [node, out_node], "edges": [], "_source_hashes": {}},
            {"decisions.md": "h-dec", "outputs_index.json": "h-oij"},
            str(tmp_path / "nonexist_decisions.md"),  # 不存在 -> decisions 无对账
            str(bad_dir),  # outputs_index = 目录 -> 读失败
            str(tmp_path / "insights"),
            lambda c: str(tmp_path / "client_graph.json"),
            lambda c: str(tmp_path / "client_index.md"))
        outs = [n for n in graph["nodes"] if n["type"] == "output"]
        assert len(outs) == 1 and outs[0]["metadata"]["status"] == "done"
        assert "outputs_index.json" not in graph["_source_hashes"]

    def test_success_records_hashes(self, tmp_path):
        """全部处理成功：hash 正常记录（skip 检测不受影响）。"""
        node = _existing_decision_node(7, "拍板方向A", "x")
        graph = self._run(tmp_path, _decision_block(7, "拍板方向A", "x"),
                          {"outputs": []}, [node])
        assert graph["_source_hashes"] == {"decisions.md": "h-dec",
                                           "outputs_index.json": "h-oij"}

    def test_output_missing_marks_node_removed(self, tmp_path):
        """W1-5：outputs_index 条目 missing -> 不进增量产出集，存量节点标 removed。"""
        out_node = {"id": "n901", "type": "output", "title": "output/x.html",
                    "details_path": "output/x.html", "metadata": {"status": "在用"}}
        oij = {"outputs": [{"file": "output/x.html", "missing": True,
                            "status": "已归档/缺失"}]}
        graph = self._run(tmp_path, None, oij, [out_node])
        outs = [n for n in graph["nodes"] if n["type"] == "output"]
        assert len(outs) == 1
        assert outs[0]["metadata"]["status"] == "removed"

    def test_output_missing_creates_no_node(self, tmp_path):
        """W1-5：missing 条目不新建 output 节点（与全量重建口径一致）。"""
        oij = {"outputs": [{"file": "output/new.html", "missing": True}]}
        graph = self._run(tmp_path, None, oij, [])
        assert [n for n in graph["nodes"] if n["type"] == "output"] == []

    def test_output_recovered_restores_removed_node(self, tmp_path):
        """归档物回迁自愈：missing 清除后再增量，removed 节点状态回在用。"""
        out_node = {"id": "n901", "type": "output", "title": "output/x.html",
                    "details_path": "output/x.html", "metadata": {"status": "removed"}}
        oij = {"outputs": [{"file": "output/x.html", "status": "在用"}]}
        graph = self._run(tmp_path, None, oij, [out_node])
        outs = [n for n in graph["nodes"] if n["type"] == "output"]
        assert len(outs) == 1
        assert outs[0]["metadata"]["status"] == "在用"
