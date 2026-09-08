# -*- coding: utf-8 -*-
"""B4-G2 回归：_doctor 诊断失真修复 + _project_map DOMAIN_MAP 归域补全。

背景（2026-09-06，符合性报告 M3「W5 清理波：删了模块没通知诊断」）：
- _doctor CORE_MODULES 曾引用 W5 已删除的 _skill（Skill 提示挂件）→ 诊断恒 FAIL；
  其机制已由 .folio/.agents skills 双树 + _skills_sync 承载，检查对象改指 _skills_sync。
- _doctor API_KEY_NAMES 中的 BYTE_SEARCH_API_KEY 全库无读取点（实际读
  ASK_ECHO_SEARCH_INFINITY_API_KEY，见 _cli_infra/_cloud_llm_search）→ 死名误导。
- _project_map DOMAIN_MAP 缺 13 个历次拆分产物 → explain-map 报「未归域」。
"""

import importlib.util
import json
from pathlib import Path

import _doctor
import _project_map

ROOT = Path(_doctor.__file__).resolve().parent


class TestDoctorCoreModules:
    """doctor 检查清单中的模块必须真实存在（防「删了模块没通知诊断」复发）。"""

    def test_core_modules_all_exist(self):
        for m in _doctor.CORE_MODULES:
            spec = importlib.util.find_spec(m)
            assert spec is not None, f"CORE_MODULES 引用了不存在的模块：{m}"

    def test_skill_replaced_by_skills_sync(self):
        # _skill 已在 W5 删除；skill 机制由 _skills_sync（双树同步）承载
        assert "_skill" not in _doctor.CORE_MODULES
        assert "_skills_sync" in _doctor.CORE_MODULES


class TestDoctorApiKeys:
    """doctor 的 key 清单必须与代码实际读取一致（防死名误导）。"""

    def test_byte_search_key_replaced_by_actual_env_name(self):
        # 代码实际读取点：_cli_infra.py / _cloud_llm_search.py / _cli_audit._KEY_FEATURES
        assert "BYTE_SEARCH_API_KEY" not in _doctor.API_KEY_NAMES
        assert "ASK_ECHO_SEARCH_INFINITY_API_KEY" in _doctor.API_KEY_NAMES

    def test_doctor_report_has_no_fail(self):
        # 验收口径：跑一次完整诊断，核心模块不得出现恒 FAIL 失真项
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            _doctor.run_doctor(as_json=True)
        report = json.loads(buf.getvalue())
        fails = {k: v for k, v in report["modules"].items() if str(v).startswith("FAIL")}
        assert fails == {}, f"doctor 核心模块存在 FAIL 项：{fails}"
        assert "ASK_ECHO_SEARCH_INFINITY_API_KEY" in report["api_keys"]
        assert "BYTE_SEARCH_API_KEY" not in report["api_keys"]


class TestProjectMapDomainMap:
    """DOMAIN_MAP 必须覆盖全部根目录模块且不引用已删除模块。"""

    def test_no_unmapped_root_modules(self):
        # 与 _project_map.main() 同口径：根目录 _*.py 逐一归域，unmapped 清零
        unmapped = [p.stem for p in sorted(ROOT.glob("_*.py"))
                    if p.stem not in _project_map.DOMAIN_MAP]
        assert unmapped == [], f"仍有未归域模块：{unmapped}"

    def test_domain_map_keys_all_exist(self):
        # 反向：映射表不得引用已删除模块（与 _doctor 的 _skill 教训同源）
        stale = [k for k in _project_map.DOMAIN_MAP
                 if not (ROOT / f"{k}.py").exists()]
        assert stale == [], f"DOMAIN_MAP 引用了不存在的模块：{stale}"

    def test_domain_ids_valid(self):
        valid = {d[0] for d in _project_map.DOMAINS}
        for mod, dom in _project_map.DOMAIN_MAP.items():
            assert dom in valid, f"DOMAIN_MAP[{mod}] 指向未知域：{dom}"

    def test_thirteen_split_modules_pinned(self):
        # 13 个历次拆分产物的归域决策逐一钉死，防止回归漂移
        expected = {
            "_cli_audit_p0": "entry",       # T9 拆分自 _cli_audit
            "_cli_cmds_recall_v2": "entry",  # CLI 命令面板域
            "_cloud_llm_search": "know",     # 拆分自 _cloud_llm
            "_cloud_llm_vision": "know",     # 拆分自 _cloud_llm
            "_diagram_extract": "gen",       # S1 拆分自 _outline_to_spec
            "_narrative_apply": "gen",       # S1 拆分自 _outline_to_spec
            "_pptd_parts": "gen",            # T9 拆分自 _pptd_gen
            "_query_rewrite": "know",        # 召回查询改写
            "_query_trace": "know",          # 召回查询日志
            "_inbox_registry": "mem",        # inbox 家族，随 _inbox_scan
            "_verify_checks": "guard",       # P4-S3 拆分自 _verify
            "_domain_guard": "guard",        # 被 _verify 引用的机械检查
            "_fact_guard": "guard",          # 事实一致性校验器
        }
        for mod, dom in expected.items():
            assert _project_map.DOMAIN_MAP.get(mod) == dom, mod
