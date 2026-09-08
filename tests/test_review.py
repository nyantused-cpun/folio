# -*- coding: utf-8 -*-
"""_review：GBK 打印兜底 + A-4 结构完整度第 5 维。"""

import json
import sys

import _review


def test_safe_print_special_chars_no_crash(capsys):
    """特殊字符（GBK 不可编码）打印不崩——曾缺 import sys，兜底路径 NameError。"""
    _review._safe_print("特殊字符 ✓ 😀 —— 破折号")
    out = capsys.readouterr().out
    assert "特殊字符" in out


def test_safe_print_gbk_fallback(monkeypatch):
    """print 抛 UnicodeEncodeError 时走 sys.stdout.buffer utf-8 兜底。"""
    written = []

    class _FakeBuffer:
        def write(self, b):
            written.append(b)

    class _FakeStdout:
        buffer = _FakeBuffer()

        def flush(self):
            pass

    def _raising_print(text):
        raise UnicodeEncodeError("gbk", str(text), 0, 1, "illegal")

    monkeypatch.setattr("builtins.print", _raising_print)
    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    _review._safe_print("特殊 ✓")
    assert written == ["特殊 ✓".encode("utf-8", errors="replace") + b"\n"]


# ---------------------------------------------------------------------------
# A-4 结构完整度第 5 维
# ---------------------------------------------------------------------------
class TestStructureDimension:
    def test_checklist_has_categories(self):
        assert len(_review.STRUCTURE_CHECKLIST) == 12
        for key in ("叙事组件", "指标组件", "流程时序", "架构图", "数据图表",
                    "图形化表达", "证据台账", "风险登记", "责任矩阵",
                    "决策面板", "层级金字塔", "四象限"):
            assert key in _review.STRUCTURE_CHECKLIST

    def _mock_llm(self, monkeypatch, tmp_path, scores, verdict="PASS"):
        import _cloud_llm
        payload = json.dumps({
            "verdict": verdict,
            "scores": scores,
            "issues": [],
            "summary": "ok",
        }, ensure_ascii=False)
        captured = {}

        def fake_chat(**kwargs):
            captured["prompt"] = kwargs.get("prompt", "")
            return payload

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        return str(out), captured

    def test_total_15_passes(self, monkeypatch, tmp_path):
        out, _ = self._mock_llm(monkeypatch, tmp_path, {
            "设计": 3, "原创": 3, "工艺": 3, "功能": 3, "结构": 3, "总分": 15})
        assert _review.review(out, quiet=True)["verdict"] == "PASS"

    def test_total_14_fails(self, monkeypatch, tmp_path):
        out, _ = self._mock_llm(monkeypatch, tmp_path, {
            "设计": 3, "原创": 3, "工艺": 3, "功能": 3, "结构": 2, "总分": 14})
        assert _review.review(out, quiet=True)["verdict"] == "FAIL"

    def test_prompt_contains_structure_checklist(self, monkeypatch, tmp_path):
        out, captured = self._mock_llm(monkeypatch, tmp_path, {
            "设计": 3, "原创": 3, "工艺": 3, "功能": 3, "结构": 3, "总分": 15})
        _review.review(out, quiet=True)
        prompt = captured["prompt"]
        assert "结构完整度" in prompt
        assert "叙事组件" in prompt
        assert "架构图" in prompt


# ---------------------------------------------------------------------------
# 并行审查：5 路独立会话维度隔离 + 汇总去重 + 单路失败降级
# ---------------------------------------------------------------------------
class TestParallelReview:
    def _mock_llm(self, monkeypatch, tmp_path, responder):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", responder)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        return str(out)

    @staticmethod
    def _pass_payload():
        return json.dumps({"verdict": "PASS", "issues": [], "summary": "ok"},
                          ensure_ascii=False)

    def test_all_pass_merges_scores_and_coverage(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            system = kwargs.get("system", "")
            if "质量评审员" in system:
                return json.dumps({"verdict": "PASS", "issues": [],
                                   "scores": {"设计": 3, "原创": 3, "工艺": 3,
                                              "功能": 3, "结构": 3, "总分": 15},
                                   "summary": "ok"}, ensure_ascii=False)
            if "铁律覆盖" in system:
                return json.dumps({"verdict": "PASS", "issues": [],
                                   "theme_coverage": {"覆盖数": 2, "未覆盖": []},
                                   "summary": "ok"}, ensure_ascii=False)
            return self._pass_payload()

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        assert result["verdict"] == "PASS"
        assert result["scores"]["总分"] == 15
        assert result["theme_coverage"]["覆盖数"] == 2
        assert result["mode"] == "parallel"

    def test_one_dim_fail_flips_verdict(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            if "内容一致性" in kwargs.get("system", ""):
                return json.dumps({"verdict": "FAIL", "issues": ["与 spec 不一致"],
                                   "summary": "有偏差"}, ensure_ascii=False)
            return self._pass_payload()

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        assert result["verdict"] == "FAIL"
        assert any("与 spec 不一致" in i for i in result["issues"])

    def test_low_total_auto_fail(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            if "质量评审员" in kwargs.get("system", ""):
                return json.dumps({"verdict": "PASS", "issues": [],
                                   "scores": {"设计": 3, "原创": 3, "工艺": 3,
                                              "功能": 2, "结构": 2, "总分": 13},
                                   "summary": "ok"}, ensure_ascii=False)
            return self._pass_payload()

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        assert result["verdict"] == "FAIL"

    def test_one_dim_error_isolated(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            if "文风检查员" in kwargs.get("system", ""):
                return None  # 模拟 provider 失败
            return self._pass_payload()

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        # 单路失败不阻断：verdict 由其余维度决定，issues 记录失败信息
        assert result["verdict"] == "PASS"
        assert any("去AI化" in i for i in result["issues"])

    def test_all_dims_error(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            return None

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        assert result["verdict"] == "ERROR"

    def test_issues_dedup(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            return json.dumps({"verdict": "PASS", "issues": ["重复问题"],
                               "summary": "ok"}, ensure_ascii=False)

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_parallel(out, quiet=True)
        assert result["issues"].count("重复问题") == 1


# ---------------------------------------------------------------------------
# 并行对抗审查：多角色挑刺者角度隔离 + 汇总去重 + 单路失败降级
# ---------------------------------------------------------------------------
class TestAdversarialParallel:
    def _mock_llm(self, monkeypatch, tmp_path, responder):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", responder)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        return str(out)

    @staticmethod
    def _pass_payload():
        return json.dumps({"verdict": "PASS", "findings": [], "summary": "未发现问题"},
                          ensure_ascii=False)

    def test_all_pass(self, monkeypatch, tmp_path):
        out = self._mock_llm(monkeypatch, tmp_path, lambda **kw: self._pass_payload())
        result = _review.review_adversarial_parallel(out, quiet=True)
        assert result["verdict"] == "PASS"
        assert result["mode"] == "parallel_adversarial"

    def test_one_angle_fail_flips_verdict(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            if "论断挑刺者" in kwargs.get("system", ""):
                return json.dumps({"verdict": "FAIL", "findings": ["论断1 - 可被反驳"],
                                   "summary": "有可反驳论断"}, ensure_ascii=False)
            return self._pass_payload()

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_adversarial_parallel(out, quiet=True)
        assert result["verdict"] == "FAIL"
        assert any("[可反驳论断] 论断1 - 可被反驳" in i for i in result["issues"])

    def test_all_angles_error(self, monkeypatch, tmp_path):
        out = self._mock_llm(monkeypatch, tmp_path, lambda **kw: None)
        result = _review.review_adversarial_parallel(out, quiet=True)
        assert result["verdict"] == "ERROR"

    def test_findings_dedup(self, monkeypatch, tmp_path):
        def fake_chat(**kwargs):
            return json.dumps({"verdict": "PASS", "findings": ["同一条挑刺", "同一条挑刺"],
                               "summary": "ok"}, ensure_ascii=False)

        out = self._mock_llm(monkeypatch, tmp_path, fake_chat)
        result = _review.review_adversarial_parallel(out, quiet=True)
        # 单路内重复去重；不同角度的同文本保留各角度前缀（共 5 条）
        assert result["issues"].count("[可反驳论断] 同一条挑刺") == 1
        assert len(result["issues"]) == 5


# ---------------------------------------------------------------------------
# F5-2：REVIEW_PROVIDER / REVIEW_MODEL 独立审查模型
# ---------------------------------------------------------------------------
class TestReviewModelOverride:
    def test_review_llm_kwargs_empty_by_default(self, monkeypatch):
        monkeypatch.delenv("REVIEW_PROVIDER", raising=False)
        monkeypatch.delenv("REVIEW_MODEL", raising=False)
        assert _review._review_llm_kwargs() == {}

    def test_review_llm_kwargs_reads_env(self, monkeypatch):
        monkeypatch.setenv("REVIEW_PROVIDER", "zhipu")
        monkeypatch.setenv("REVIEW_MODEL", "glm-5.2")
        assert _review._review_llm_kwargs() == {
            "provider": "zhipu",
            "model": "glm-5.2",
        }

    def test_review_passes_override_to_chat(self, monkeypatch, tmp_path):
        import _cloud_llm
        monkeypatch.setenv("REVIEW_PROVIDER", "zhipu")
        monkeypatch.setenv("REVIEW_MODEL", "glm-5.2")
        captured = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return json.dumps({"verdict": "PASS", "issues": [], "summary": "ok",
                               "scores": {"设计": 3, "原创": 3, "工艺": 3,
                                          "功能": 3, "结构": 3, "总分": 15}},
                              ensure_ascii=False)

        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        _review.review(str(out), quiet=True)
        assert captured.get("provider") == "zhipu"
        assert captured.get("model") == "glm-5.2"


# ---------------------------------------------------------------------------
# 运行验收 §9-B 回归：HTML 文本提取必须剔除 style/script/head 块
# ---------------------------------------------------------------------------
class TestReadOutputTextStripsNonBody:
    """修复前 CSS 规则占满 MAX_OUTPUT_CHARS 截断窗口 → review 假阴性 FAIL。"""

    def _html(self):
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>方案标题</title><style>.x{color:red}</style></head>"
            "<body><style>.big{width:100%;background:#fff}</style>"
            "<script>var secret=1;</script><h1>核心结论</h1><p>正文内容 ABC123</p>"
            "</body></html>"
        )

    def test_body_text_survives_css_script_stripped(self, tmp_path):
        p = tmp_path / "d.html"
        p.write_text(self._html(), encoding="utf-8")
        text = _review._read_output_text(str(p))
        assert text is not None
        # 正文保留
        assert "核心结论" in text
        assert "正文内容" in text
        # 非正文（CSS/JS/head 内容）剔除
        assert ".big" not in text
        assert "color:red" not in text
        assert "var secret" not in text
        assert "方案标题" not in text
        # 标签本身也被去除
        assert "<style" not in text and "<script" not in text
        assert "<head" not in text and "<h1>" not in text

    def test_css_flood_does_not_occupy_truncation_window(self, tmp_path):
        big_css = "<style>" + "a{color:#fff;}\n" * 3000 + "</style>"
        p = tmp_path / "flood.html"
        p.write_text("<html><head></head><body>" + big_css
                     + "<p>真正的内容在这</p></body></html>", encoding="utf-8")
        text = _review._read_output_text(str(p))
        # CSS 约 5 万字符 > MAX_OUTPUT_CHARS，修复前正文会被截断窗口吞掉
        assert "真正的内容在这" in text
        assert "color:#fff" not in text

    def test_non_html_file_unaffected(self, tmp_path):
        p = tmp_path / "t.txt"
        p.write_text("纯文本 <style>不剔除</style>", encoding="utf-8")
        text = _review._read_output_text(str(p))
        assert "纯文本" in text
        assert "<style>不剔除</style>" in text


# ---------------------------------------------------------------------------
# P1 双向判分：verdict 缺省 FAIL + scores 缺失/非数值不做 <15 比较（三处统一）
# ---------------------------------------------------------------------------
class TestBidirectionalVerdict:
    def _mock_llm(self, monkeypatch, tmp_path, payload):
        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", lambda **kw: payload)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        return str(out)

    def test_missing_verdict_defaults_fail_serial(self, monkeypatch, tmp_path):
        payload = json.dumps({"issues": [], "summary": "ok"}, ensure_ascii=False)
        out = self._mock_llm(monkeypatch, tmp_path, payload)
        assert _review.review(out, quiet=True)["verdict"] == "FAIL"

    def test_missing_scores_no_false_auto_fail(self, monkeypatch, tmp_path):
        """LLM 判 PASS 但缺 scores → 不做 <15 比较、不追加"总分 0"误导 issue。"""
        payload = json.dumps({"verdict": "PASS", "issues": [], "summary": "ok"},
                             ensure_ascii=False)
        out = self._mock_llm(monkeypatch, tmp_path, payload)
        r = _review.review(out, quiet=True)
        assert r["verdict"] == "PASS"
        assert not any("总分" in i for i in r["issues"])

    def test_low_total_still_auto_fails(self, monkeypatch, tmp_path):
        payload = json.dumps({"verdict": "PASS",
                              "scores": {"设计": 2, "原创": 3, "工艺": 3,
                                         "功能": 3, "结构": 3, "总分": 14},
                              "issues": [], "summary": "ok"}, ensure_ascii=False)
        out = self._mock_llm(monkeypatch, tmp_path, payload)
        r = _review.review(out, quiet=True)
        assert r["verdict"] == "FAIL"
        assert any("低于阈值" in i for i in r["issues"])

    def test_missing_verdict_defaults_fail_parallel_dim(self, monkeypatch, tmp_path):
        """并行模式：维度返回缺 verdict → 汇总 verdict 翻 FAIL。"""
        payload = json.dumps({"issues": [], "summary": "ok"}, ensure_ascii=False)

        def fake_chat(**kw):
            return payload

        import _cloud_llm
        monkeypatch.setattr(_cloud_llm, "chat", fake_chat)
        monkeypatch.setattr(_review, "write_review_log", lambda *a, **k: None)
        out = tmp_path / "t.html"
        out.write_text("<html>test</html>", encoding="utf-8")
        assert _review.review_parallel(str(out), quiet=True)["verdict"] == "FAIL"

    def test_merge_scores_without_total_no_false_fail(self):
        """并行汇总：scores 有值但缺"总分"键 → 不误判低分。"""
        ok = {"verdict": "PASS", "issues": [], "summary": "s"}
        dim_results = {
            "铁律覆盖": dict(ok, dim="铁律覆盖"),
            "内容一致性": dict(ok, dim="内容一致性"),
            "去AI化": dict(ok, dim="去AI化"),
            "事实可追溯": dict(ok, dim="事实可追溯"),
            "五维打分": dict(ok, dim="五维打分", extra_key="scores",
                           extra={"设计": 3, "原创": 3, "工艺": 3,
                                  "功能": 3, "结构": 3}),
        }
        r = _review._merge_parallel_results(dim_results, [])
        assert r["verdict"] == "PASS"
        assert not any("总分" in i for i in r["issues"])
