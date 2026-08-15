# -*- coding: utf-8 -*-
"""Skill 提示机制（与 Trae .trae/skills/ 目录协同）。

历史：v1 在 _knowledge/skills/ 存自定义格式 MD（无 description，Trae 不加载）。
v2 起 Skill 迁移到 .trae/skills/<name>/SKILL.md（Trae 自动加载）。
本模块仅保留 suggest_skill_from_insight，用于洞察发现可复用工作流时提示
用户去 .trae/skills/ 创建标准 SKILL.md。
"""


def suggest_skill_from_insight(insight_text):
    """M8: 洞察发现可复用工作流时提示保存为 Skill。

    检查洞察文本是否含可复用模式，返回提示语或 None。
    提示用户在 .trae/skills/<name>/SKILL.md 创建标准格式（含 name + description frontmatter）。
    """
    if not insight_text:
        return None

    # 简单检测：洞察含"可复用"/"工作流"/"模式"/"步骤"时提示
    keywords = ["可复用", "工作流", "模式", "步骤", "流程", "规律"]
    if any(kw in insight_text for kw in keywords):
        return ("洞察发现可复用工作流。要保存为 Skill 吗？\n"
                "在 .trae/skills/<skill-name>/SKILL.md 创建文件，"
                "含 name + description（<200 字符，含 what + when）frontmatter，"
                "或用 skill-creator skill 辅助生成。")

    return None
