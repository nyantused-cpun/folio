# -*- coding: utf-8 -*-
"""去 AI 化守卫：检测 AI 套路，提示用户修改。
检测维度：排比/黑话/总结句/华丽形容词/对称句式/过度结构化。"""
import os
import re
import glob

from _paths import SCRIPT_DIR, BANNED_WORDS

ANTIPATTERN_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "snippets", "antipattern")
STYLE_SAMPLES_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "me", "style_samples")
UI_STYLES_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "ui")

AI_PATTERNS = {
    "排比三连": {
        "pattern": r'(不仅|不但)[^，。]{2,30}(更|还)[^，。]{2,30}(还|更)',
        "hint": "改为短句，一句一个信息点",
    },
    "黑话": {
        # P2：移除"深度/全面/有效"等日常高频词，降低误报率
        "pattern": r'(' + '|'.join(BANNED_WORDS) + r')',
        "hint": "用具体动词替代（如'缩短周期'而非'提升效率'）",
    },
    "总结句": {
        "pattern": r'(综上所述|总而言之|总的来说|由此可见|不难看出|可以说)',
        "hint": "删除总结句，PPT 不需要",
    },
    "华丽形容词": {
        "pattern": r'(卓越的|全方位的|一站式的|无与伦比的|领先的|世界级的|顶级的)',
        "hint": "删除形容词，直接给事实",
    },
    "对称句式": {
        "pattern": r'(既要|不但)[^，。]{2,20}(又要|更要|还要)',
        "hint": "选一个重点，不要面面俱到",
    },
    "过度结构化": {
        "pattern": r'(首先|其次|再次|最后|第一|第二|第三|第四)',
        "hint": "用自然句过渡，不强行编号",
    },
    # 2026-07-19 扩充：来源 GitHub 中文去AI味最佳实践（B1lli/remove-ai-flavor、stop-slop-zh、humanizer-zh）
    # 2026-08-14 升级：对齐 qu-ai-wei 对称骨架族 + khazix 翻案腔（动作级，不按字面）
    "对称骨架": {
        "pattern": r'((?:不是|并非|不只是|并非只是|不在于|绝不)[^。]{0,25}(?:而是|而在于|只是|更是)|(?:既是)[^。]{0,20}(?:也是)[^。]{0,20}(?:更是)|(?:与其说)[^。]{0,20}(?:不如说))',
        "hint": "直接说结论，不先立靶子、不强行'既是…也是…更是'三连",
    },
    "假揭示": {
        "pattern": r'(看似|表面上|表面上看)[^。]{0,20}(本质|背后|其实|实则)',
        "hint": "直接陈述事实与结论，不制造'表象 vs 本质'的揭示感",
    },
    "时代开场": {
        "pattern": r'(随着[^，。]{2,20}的(快速发展|不断进步|到来|深入)|在当今[^，。]{0,15}(时代|社会|背景下|浪潮下))',
        "hint": "删开场白，直接说事",
    },
    "本质宣称": {
        "pattern": r'(真正[^，。]{0,12}的是|本质上|核心在于|底层逻辑)',
        "hint": "直接给主语和事实，不升维总结",
    },
}


# 动态词库缓存（首次 check 时加载，避免每次扫文件都读目录）
_ANTIPATTERN_CACHE = None


def _get_all_patterns():
    """硬编码 AI_PATTERNS + 动态词库合并后的完整检测表。"""
    global _ANTIPATTERN_CACHE
    if _ANTIPATTERN_CACHE is None:
        merged = dict(AI_PATTERNS)
        merged.update(_load_antipatterns_from_dir())
        _ANTIPATTERN_CACHE = merged
    return _ANTIPATTERN_CACHE


def check(text):
    """检测文本中的 AI 套路。返回 [{name, count, matches, hint}, ...]。"""
    issues = []
    for name, config in _get_all_patterns().items():
        matches = re.findall(config["pattern"], text)
        if matches:
            issues.append({
                "name": name,
                "count": len(matches),
                "matches": matches[:5],
                "hint": config["hint"],
            })
    return issues


def check_file(file_path):
    """检测文件。返回 (issues, total_chars)。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return check(text), len(text)


def print_report(file_path):
    """打印检测报告。返回 True 表示无问题。"""
    issues, total = check_file(file_path)
    print(f"=== 去 AI 化检测：{file_path} ===")
    print(f"文本长度：{total} 字\n")

    if not issues:
        print("未检测到 AI 套路，语感自然")
        return True

    print(f"发现 {len(issues)} 类问题：\n")
    for issue in issues:
        print(f"  [{issue['name']}] x{issue['count']}")
        print(f"    匹配：{issue['matches']}")
        print(f"    建议：{issue['hint']}\n")

    print("修改建议：读 _knowledge/me/style_samples/ 样本，模仿其语感重写")
    return False


# ============================================================
# IDE 模式钩子（pre_check）
# ============================================================
def _load_antipatterns_from_dir():
    """从 _knowledge/snippets/antipattern/ 动态加载反模式词库。

    目录不存在时返回空 dict（调用方用硬编码 AI_PATTERNS 兜底）。
    文件格式：每行一个反模式词，或 "- 词" / "* 词" 列表项。
    过滤：跳过 README.md；跳过 # / > 开头的注释引用行；跳过超长散文行（>40 字）。
    """
    extra = {}
    if not os.path.isdir(ANTIPATTERN_DIR):
        return extra
    for f in glob.glob(os.path.join(ANTIPATTERN_DIR, "*.md")):
        fname = os.path.splitext(os.path.basename(f))[0]
        if fname == "README":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                words = []
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith(">"):
                        continue
                    if line.startswith("- ") or line.startswith("* "):
                        line = line[2:].strip()
                    if len(line) > 40:
                        continue
                    words.append(line)
                if words:
                    extra[fname] = {"pattern": "|".join(words), "hint": f"避免 {fname}"}
        except Exception as e:
            # P1-3：原静默 pass，改为打印警告（反模式词库加载失败会让 AI 套路漏检）
            print(f"[warn] 反模式词库 {os.path.basename(f)} 加载失败: {e}")
    return extra


def pre_check(ui_style="auto", client_name=None, task_id=None):
    """IDE 模式：AI 写产出前必调。返回需避开的反模式 + 必读文件 + 主题守卫。

    返回 schema:
    {
        "ui_style": str,                    # 选定的 UI 风格
        "style_samples_loaded": bool,       # 是否加载了语感样本
        "antipatterns_to_avoid": list,      # 反模式名列表
        "required_reads": list,             # 必读文件路径列表
        "theme_guard": dict | None,         # 主题守卫结果（传 client_name 时有）
        "warnings": list
    }
    """
    warnings = []

    # 1. 检测 ui_style（auto 时默认 kpmg）
    if ui_style == "auto":
        ui_style = "kpmg"

    # 2. 必读文件：UI 风格说明 + 语感样本
    required = []
    ui_style_path = os.path.join(UI_STYLES_DIR, ui_style, "style.md")
    if os.path.exists(ui_style_path):
        required.append(ui_style_path)
    elif os.path.isdir(UI_STYLES_DIR):
        warnings.append(f"UI 风格 '{ui_style}' 无 style.md，可用: {os.listdir(UI_STYLES_DIR)}")

    style_samples_loaded = False
    if os.path.isdir(STYLE_SAMPLES_DIR):
        for f in glob.glob(os.path.join(STYLE_SAMPLES_DIR, "*.md")):
            required.append(f)
        style_samples_loaded = len(required) > 0

    # 3. 加载反模式（硬编码 + 动态目录合并）
    antipatterns = list(AI_PATTERNS.keys())
    try:
        extra = _load_antipatterns_from_dir()
        antipatterns.extend(extra.keys())
    except Exception as e:
        warnings.append(f"动态反模式加载失败: {e}")

    # 4. 主题守卫（HEAD-TAIL 注意力策略）
    theme_guard = None
    if client_name:
        try:
            from _theme_guard import pre_check as theme_pre_check
            theme_guard = theme_pre_check(client_name, task_id)
        except Exception as e:
            warnings.append(f"主题守卫加载失败: {e}")

    return {
        "ui_style": ui_style,
        "style_samples_loaded": style_samples_loaded,
        "antipatterns_to_avoid": antipatterns,
        "required_reads": required,
        "theme_guard": theme_guard,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python _style_guard.py <文件>")
        sys.exit(0)
    ok = print_report(sys.argv[1])
    sys.exit(0 if ok else 1)
