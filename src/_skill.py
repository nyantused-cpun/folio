# -*- coding: utf-8 -*-
"""Skill 提示机制（宿主无关的运行时技能目录）。

发布版技能事实源在仓库根 `skills/`（与宿主无关）；DSH 宿主用
`skills-sync` 同步到 `.agents/skills/` 供识别，其他宿主按各自 skill
目录约定放置/同步。
本模块仅保留 suggest_skill_from_insight，用于洞察发现可复用工作流时提示
用户按宿主约定创建标准 SKILL.md。
"""


def suggest_skill_from_insight(insight_text):
    """M8: 洞察发现可复用工作流时提示保存为 Skill。

    检查洞察文本是否含可复用模式，返回提示语或 None。
    提示用户按宿主约定的技能目录创建标准格式（含 name + description frontmatter）。
    """
    if not insight_text:
        return None

    # 简单检测：洞察含"可复用"/"工作流"/"模式"/"步骤"时提示
    keywords = ["可复用", "工作流", "模式", "步骤", "流程", "规律"]
    if any(kw in insight_text for kw in keywords):
        return ("洞察发现可复用工作流。要保存为 Skill 吗？\n"
                "在技能目录（发布版事实源 skills/<skill-name>/SKILL.md，"
                "DSH 识别副本 .agents/skills/<skill-name>/SKILL.md）创建文件，"
                "含 name + description（<200 字符，含 what + when）frontmatter，"
                "或用 skill-creator skill 辅助生成。")

    return None
