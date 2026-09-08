# -*- coding: utf-8 -*-
"""会话管理模块：save_session + parse_args + auto_for_input。

从原 _session.py 拆分（候选 4 · 模块化）。
拆出的模块：
  - _context.py: context.md schema、层级判定、客户目录管理
  - _graph.py: 版本链索引 client_graph.json（历史/调试）
  - _worldbook.py: 世界书 client_index.md 直生（M2-R1）
  - _recall.py: BM25 + Embedding 双路召回 + RRF 融合
  - _onboard.py: 一键接单 + BM25 索引重建

re-export 保持 `from _session import xxx` 向后兼容。
"""
import os
import json
import re
import sys
import time
from datetime import datetime

from _paths import SCRIPT_DIR, TASK_HISTORY, INBOX_DIR, KNOWLEDGE_DIR

# Re-export for backward compatibility（from _session import xxx 无需修改）
from _context import *
from _graph import *
from _recall import *
from _onboard import *


# 产出索引可识别的交付物扩展名（中间产物如截图/临时文件不入索引）
_OUTPUT_INDEX_EXTS = (".html", ".pptx", ".docx", ".xlsx", ".md")


def update_outputs_index(client_name):
    """扫描 output/{客户}/ 顶层交付物，合并写入 outputs_index.json。

    outputs_index.json 此前无程序写入方（只能手工维护），本函数补上写入路径：
    - 已有条目原样保留（version/type 等人工维护字段不动，字符串格式旧条目
      一并规范化为 dict——W1-5）；
    - 新文件按命名规范 `{客户}_{类型}_{版本}.{格式}` 解析补默认条目；
    - 不删除已消失的文件（保留历史），但 W1-5 起对每条 file 路径做存在性检查：
      不存在 -> 条目补 `missing: true, status: 已归档/缺失`（消费端据此跳过）；
      存在 -> 清除 missing 标记（归档物回迁自愈，本函数写入的缺失态 status 回位「在用」）。
    output/{客户}/ 目录缺失时跳过「新增扫描」，但存量索引条目的存在性标记
    照常执行（否则该客户 outputs_index 里的悬空条目永远拿不到 missing 标记）。
    返回新增条目数。
    """
    import _paths

    client_out_dir = os.path.join(_paths.OUTPUT_DIR, client_name)
    # #48/D2：按名解析支持 _internal/ 内部账本目录回退（账本 outputs_index 照写不散落顶层）
    client_path = _paths.client_dir(client_name)
    index_path = os.path.join(client_path, "outputs_index.json")
    has_out_dir = os.path.isdir(client_out_dir)
    if not has_out_dir and not os.path.exists(index_path):
        # 无产出目录且无存量索引：无事可做，也不凭空建目录/建文件（原 noop 语义）
        return 0
    os.makedirs(client_path, exist_ok=True)

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
    except (OSError, ValueError):
        idx = None
    if not isinstance(idx, dict):
        idx = {"outputs": []}
    outputs = idx.get("outputs")
    if not isinstance(outputs, list):
        outputs = []
        idx["outputs"] = outputs

    known = set()
    for e in outputs:
        if isinstance(e, dict):
            known.add(e.get("file"))
        elif isinstance(e, str):
            known.add(e)

    # W1-5：存在性标记（改删除为标记）。字符串旧条目一并规范化为 dict
    # （在盘默认「在用」，缺失由下方检查改标）；缺失条目补 missing/status，
    # 回迁条目自愈清除。
    for i, e in enumerate(outputs):
        if isinstance(e, str):
            e = {"file": e, "method": "auto-normalize", "status": "在用"}
            outputs[i] = e
        if not isinstance(e, dict):
            continue
        rel = e.get("file")
        if not isinstance(rel, str) or not rel:
            continue
        if os.path.isabs(rel):
            abs_path = rel
        else:
            abs_path = os.path.join(_paths.SCRIPT_DIR,
                                    *rel.replace("\\", "/").split("/"))
        if os.path.exists(abs_path):
            e.pop("missing", None)
            if e.get("status") == "已归档/缺失":
                e["status"] = "在用"
        else:
            e["missing"] = True
            e["status"] = "已归档/缺失"

    added = 0
    if has_out_dir:
        for fname in sorted(os.listdir(client_out_dir)):
            fpath = os.path.join(client_out_dir, fname)
            if not os.path.isfile(fpath) or fname.startswith(("~$", ".")):
                continue
            if not fname.lower().endswith(_OUTPUT_INDEX_EXTS):
                continue
            rel = _paths.rel_to_script(fpath).replace(os.sep, "/")
            if rel in known:
                continue
            stem = os.path.splitext(fname)[0]
            parts = stem.split("_")
            version = parts[-1] if len(parts) > 1 and re.fullmatch(r"v\d+", parts[-1]) else ""
            out_type = parts[-2] if version and len(parts) > 2 else ""
            outputs.append({
                "version": version,
                "file": rel,
                "type": out_type,
                "status": "在用",
                "date": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d"),
                "method": "auto-scan",
            })
            known.add(rel)
            added += 1

    idx["client"] = idx.get("client") or client_name
    idx["last_update"] = datetime.now().strftime("%Y-%m-%d")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    return added


def _sync_bm25_if_stale(log_dir, today):
    """save 内调用：BM25 落后检测 + 每自然日一次节流重建（D-117/P1-5）。

    触发条件：当天未重建过（marker 文件记录日期）+ corpus 存在比
    bm25_index.pkl 更新的文件。全量重建约 37s，节流避免每次 save 都跑。
    """
    from _bm25 import BM25_INDEX_PATH
    from _paths import CLIENTS_DIR
    marker_path = os.path.join(log_dir, "bm25_rebuild_date.txt")
    last_date = ""
    if os.path.exists(marker_path):
        with open(marker_path, encoding="utf-8") as f:
            last_date = f.read().strip()
    if last_date == today:
        return
    bm25_mtime = (os.path.getmtime(BM25_INDEX_PATH)
                  if os.path.exists(BM25_INDEX_PATH) else 0)
    newest = bm25_mtime
    _ext = (".md", ".txt", ".docx", ".pdf", ".pptx", ".xlsx")
    for root, dirs, files in os.walk(CLIENTS_DIR):
        # E 组收口（#48）：clients/ 顶层 `_` 前缀内部目录（_internal/、_template/ 等）
        # 整体剪枝，不参与新鲜度扫描（与 list_client_dirs 读端枚举同口径）；
        # 账本件变动不应触发全量 BM25 重建
        if root == CLIENTS_DIR:
            dirs[:] = [d for d in dirs if not d.startswith("_")]
        if ".cache" in root:
            continue
        for fn in files:
            if fn.lower().endswith(_ext):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
    if newest > bm25_mtime:
        print("[索引] BM25 落后于 corpus，自动重建（每自然日最多一次）...")
        from _onboard import rebuild_bm25_index_all
        r = rebuild_bm25_index_all()
        print(f"[索引] BM25 重建完成: {r.get('indexed_count', 0)} 块")
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write(today)


def _extract_case_cards(client_name, max_age_days=30):
    """save 钩子：从 output/{客户}/ 的 spec 自动提取案例卡（D-123，业务启动包）。

    机械提取（不调 LLM）：标题/页面指纹（layout+composition+元素类型）/组件清单/
    构图母板清单/版本。写入 _knowledge/cases/，同 key 内容相同则跳过（幂等）。
    """
    import yaml as _yaml
    from _paths import OUTPUT_DIR, SCRIPT_DIR

    cases_dir = os.path.join(SCRIPT_DIR, "_knowledge", "cases")
    out_dir = os.path.join(OUTPUT_DIR, client_name)
    if not os.path.isdir(out_dir):
        return 0
    cutoff = time.time() - max_age_days * 86400
    written = 0
    try:
        entries = os.listdir(out_dir)
    except OSError:
        return 0
    for fn in sorted(entries):
        if not (fn.endswith(".yml") and "spec" in fn):
            continue
        spath = os.path.join(out_dir, fn)
        try:
            if os.path.getmtime(spath) < cutoff:
                continue
            with open(spath, "r", encoding="utf-8") as f:
                spec = _yaml.safe_load(f) or {}
        except Exception:
            continue
        if not isinstance(spec, dict) or not spec.get("pages"):
            continue
        # 版本：三种已知形态 {类型}_v{N}.spec.yml / {类型}_v{N}_spec.yml /
        # {类型}_spec_v{N}.yml
        m = re.search(r"(?:[_]v|_spec_v)(\d+(?:\.\d+)?)(?:\.spec|_spec)?\.yml$", fn)
        ver = m.group(1) if m else "0"
        title = (spec.get("document") or {}).get("title", "") or ""
        pages = []
        comps = set()
        comp_types = set()
        for p in spec.get("pages", []) or []:
            if not isinstance(p, dict):
                continue
            comp = p.get("composition") or []
            if isinstance(comp, str):
                comp = [comp]
            comps.update(comp)
            ptypes = []
            for e in p.get("elements", []) or []:
                if isinstance(e, dict) and e.get("type"):
                    comp_types.add(e["type"])
                    ptypes.append(e["type"])
            pages.append(f"{p.get('layout', '')}|{'+'.join(ptypes)}")
        if not pages:
            continue
        # 案例卡内容（结构指纹 = 页面序列，机械可比对复用）
        card = []
        card.append(f"# 案例卡：{client_name} · {title or fn}")
        card.append("")
        card.append(f"- 来源: `{os.path.join('output', client_name, fn)}`")
        card.append(f"- 版本: v{ver}")
        card.append(f"- 生成日期: {datetime.now().strftime('%Y-%m-%d')}")
        card.append(f"- 组件清单: {', '.join(sorted(comp_types))}")
        if comps:
            card.append(f"- 构图母板: {', '.join(sorted(comps))}")
        card.append("")
        card.append("## 页面结构指纹")
        card.append("")
        card.append("```")
        card.append("\n".join(pages))
        card.append("```")
        content = "\n".join(card) + "\n"
        os.makedirs(cases_dir, exist_ok=True)
        case_fn = f"{client_name}_{title or '方案'}_案例卡_v{ver}.md".replace(
            "/", "_").replace("\\", "_").replace(":", "_")
        cpath = os.path.join(cases_dir, case_fn)
        if os.path.exists(cpath):
            with open(cpath, "r", encoding="utf-8") as f:
                if f.read() == content:
                    continue  # 幂等：内容相同跳过
        with open(cpath, "w", encoding="utf-8") as f:
            f.write(content)
        written += 1
    return written


def _render_decisions_with_marker(decisions, marker):
    """决策正文拼接证据标记（P0 记忆溯源 T2）。

    decisions 非空且 marker 非空时追加 marker，否则原样返回（含 None / 空串）。
    纯函数，供测试直接覆盖三态拼接。
    """
    return (decisions + marker) if (decisions and marker) else decisions


def _build_session_entry(today, session_num, input_desc, decisions_rendered, outputs,
                         pending, evidence_lines, dsh_session):
    """构造会话块文本（T8a）。

    dsh_session 非空时在标题行下一行写 HTML 注释标记 `<!-- dsh:session:ID -->`；
    dsh_session 为空时输出与旧版 f-string 逐字节一致（P0 回归零感知）。
    纯函数，供测试直接覆盖两种输出。
    """
    entry = f"""
### [{today}] 第 {session_num} 次会话
#### 本次输入
{input_desc or '(未记录)'}
#### 关键决策
{decisions_rendered or '(未记录)'}
#### 产出文件
{outputs or '(未记录)'}
#### 待办 / 下次要做的
{pending or '(未记录)'}
"""
    if dsh_session:
        entry = entry.replace(
            f"### [{today}] 第 {session_num} 次会话\n",
            f"### [{today}] 第 {session_num} 次会话\n<!-- dsh:session:{dsh_session} -->\n",
            1,
        )
    if evidence_lines:
        entry += "#### 证据\n" + "\n".join(evidence_lines) + "\n"
    return entry


_SESSION_HEADING_RE = re.compile(r'^(#{2,3}) \[(\d{4}-\d{2}-\d{2})\]\s*第 (\d+) 次会话')
_DSH_SESSION_MARKER_RE = re.compile(r'<!--\s*dsh:session:([^\s>]+)\s*-->')


def _extract_session_heading(line):
    """从会话块标题行解析 (日期, 会话号)；无法解析返回 None。"""
    m = _SESSION_HEADING_RE.match(line)
    if m:
        return m.group(2), int(m.group(3))
    return None


def _find_last_session_block(content):
    """定位 content 中最后一块会话块，返回 (start, end, head_line, block_text)。

    兼容 `### [日期]` 新格式与 `## [日期]` compact 格式；块尾止于下一个
    H2/H3 标题，避免吞掉后续非会话段。
    """
    matches = list(re.finditer(r'(?m)^#{2,3} \[\d{4}-\d{2}-\d{2}\]', content))
    if not matches:
        return None
    start = matches[-1].start()
    head_line_end = content.find("\n", start)
    search_from = head_line_end + 1 if head_line_end != -1 else len(content)
    next_heading = re.search(r'(?m)^#{2,3} ', content[search_from:])
    end = search_from + next_heading.start() if next_heading else len(content)
    block = content[start:end]
    head_line = block.split("\n", 1)[0]
    return start, end, head_line, block


def _upsert_session_block(content, entry, dsh_session):
    """T8a：context.md 会话级 upsert —— 定位「最后一块」并整块替换。

    两种匹配模式：
      1. dsh_session 非空：最后一块带同 ID 的 `<!-- dsh:session:ID -->` 标记则替换；
      2. dsh_session 为空：按新 entry 的「日期 + 会话号」匹配最后一块（无 DSH
         会话 ID 时的 upsert 兜底），但遇到已有 DSH 标记的块不覆盖，避免跨宿主
         混写。

    合并语义（监工修复 2026-08-19）：新 entry 某字段为空（含 "(未记录)"）时
    保留旧块对应字段；新 entry 无证据段但旧块有则保留。否则 light/dispose 的
    空参数 save 会把先前更丰富的内容覆盖掉。

    返回 (new_content, replaced, old_head)：
      - replaced=True 时 old_head = (旧日期, 旧会话号)，无法解析则为 None。
    """
    found = _find_last_session_block(content)
    if not found:
        return content, False, None
    start, end, head_line, last_block = found

    old_head = _extract_session_heading(head_line)
    has_dsh_marker = _DSH_SESSION_MARKER_RE.search(last_block)

    if dsh_session:
        if not has_dsh_marker or has_dsh_marker.group(1) != dsh_session:
            return content, False, None
    else:
        # 按日期/会话号匹配：新 entry 的标题行必须与最后一块完全一致
        entry_head_line = entry.lstrip("\n").split("\n", 1)[0]
        new_head = _extract_session_heading(entry_head_line)
        if not new_head or new_head != old_head or has_dsh_marker:
            return content, False, None

    merged_entry = _merge_session_entry(entry, _parse_session_sections(last_block))
    body = merged_entry[1:] if merged_entry.startswith("\n") else merged_entry  # 去掉前导换行
    nl = body.find("\n")
    new_block = (head_line + body[nl:]) if nl >= 0 else (head_line + body)
    if end < len(content) and not new_block.endswith("\n"):
        new_block += "\n"  # 块后有保留内容时补行分隔，防止两段挤同一行
    return content[:start] + new_block + content[end:], True, old_head


_SESSION_SECTION_RE = re.compile(
    r'(?ms)^#### (本次输入|关键决策|产出文件|待办 / 下次要做的|证据)\n(.*?)(?=^#### |\Z)')


def _parse_session_sections(block_text):
    """T8a 合并用：解析会话块的五个字段（含可选 证据 段）。纯函数。"""
    sections = {}
    for m in _SESSION_SECTION_RE.finditer(block_text):
        sections[m.group(1)] = m.group(2).rstrip("\n")
    return sections


def _merge_session_entry(entry, old_sections):
    """T8a 合并语义（监工修复 2026-08-19）：新 entry 字段为空或 "(未记录)" 时
    保留旧块同名字段；新 entry 无证据段但旧块有则保留旧证据段。

    纯函数：无字段可合并时返回原 entry（逐字节不变）。
    """
    if not old_sections:
        return entry
    changed = False

    def _repl(m):
        nonlocal changed
        key, body = m.group(1), m.group(2)
        had_nl = body.endswith("\n")
        body = body.rstrip("\n")
        if not body.strip() or body.strip() == "(未记录)":
            old = old_sections.get(key)
            if old is not None and old.strip():
                changed = True
                # 保留原段尾换行（组 2 惰性匹配会吞掉它，必须补回，
                # 否则下一段标题与正文挤同一行）
                return f"#### {key}\n{old}" + ("\n" if had_nl else "")
        return m.group(0)

    out = _SESSION_SECTION_RE.sub(_repl, entry)
    if "#### 证据" not in out:
        old_ev = old_sections.get("证据")
        if old_ev is not None and old_ev.strip():
            changed = True
            out = out.rstrip("\n") + "\n#### 证据\n" + old_ev.rstrip("\n") + "\n"
    return out if changed else entry


def _find_task_history_entry(history, client_name, dsh_session):
    """T8a：task_history 按 (project, dsh_session) 查重，返回条目下标或 None。"""
    project = f"client:{client_name}"
    for i, e in enumerate(history):
        if isinstance(e, dict) and e.get("project") == project \
                and e.get("dsh_session") == dsh_session:
            return i
    return None


def _find_task_history_entry_by_date_session(history, client_name, date, session):
    """S8 兜底：无 dsh_session 时按 (project, date, session) 查重。"""
    project = f"client:{client_name}"
    for i, e in enumerate(history):
        if (isinstance(e, dict) and e.get("project") == project
                and e.get("date") == date
                and e.get("session") == session):
            return i
    return None


# ============================================================
# #49③/D4 preferences 机器链：save 从偏好类决策自动摘要维护 preferences.md
# ============================================================
# 保守关键词匹配（D4 拍板口径，刻意收窄；不追求召回，误收比漏收更伤）。
_PREFERENCE_KEYWORDS = ("偏好", "喜欢", "不喜欢", "禁用", "风格", "色", "字体", "称谓")

# 纪要元记录过滤（S5 遗留根治 P3-9①，2026-09-08）：save --decisions= 的创作会话
# 四要素纪要整块流经本链，含「色/风格」等词的行（如调试纪要「…[Red]须写[红色]…」）
# 会被误当客户偏好收进。保守判据=行内出现 ①-⑤ 纪要要素标号或四要素标签词即视为
# 元记录整行跳过——误收比漏收更伤口径下宁可少收（存量合法偏好条目无一使用这些
# 标记，全库 preferences.md 实测校准）。
_PREFERENCE_META_MARKERS = ("①", "②", "③", "④", "⑤",
                            "讨论主题", "对话过程", "用户要求改", "为什么改", "会话纪要")

# preferences.md 不存在时按此最小骨架创建（读端 _context.load_context_by_level L3）。
_PREFERENCES_SKELETON = (
    "# 客户偏好\n\n"
    "> 机器链维护：save 自动从偏好类决策摘要追加（只增不改）；人工可直接编辑本文件。\n\n"
    "## 偏好记录\n"
)


def _extract_preference_entries(decisions_text):
    """从会话决策文本提取偏好类条目（保守关键词匹配）。

    按 换行/分号 切分后逐条匹配关键词；命中纪要元记录标记的行整行跳过
    （S5 遗留根治：四要素纪要是过程记录，不是客户偏好）；返回去空后的
    条目列表（保序）。
    """
    entries = []
    for raw in re.split(r"[\n;；]+", str(decisions_text or "")):
        line = raw.strip()
        if not line:
            continue
        if any(m in line for m in _PREFERENCE_META_MARKERS):
            continue
        if any(k in line for k in _PREFERENCE_KEYWORDS):
            entries.append(line)
    return entries


def _append_preferences(client_path, decisions_text, session_ref=""):
    """偏好类决策摘要追加 preferences.md。返回新增条数（无命中/全重复返回 0）。

    - 去重：同条（按条目正文前缀匹配，无视日期尾巴）不重复追加；
    - 文件不存在按最小骨架创建；追加失败由调用方兜底（不影响 save 主流程）。
    """
    entries = _extract_preference_entries(decisions_text)
    if not entries:
        return 0
    pref_path = os.path.join(client_path, "preferences.md")
    if os.path.exists(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = ""
    else:
        content = _PREFERENCES_SKELETON
    today = datetime.now().strftime("%Y-%m-%d")
    suffix = f"（{today}" + (f" · {session_ref}" if session_ref else "") + "）"
    new_lines = [f"- {e}{suffix}" for e in entries if f"- {e}" not in content]
    if not new_lines:
        return 0
    if not content.endswith("\n"):
        content += "\n"
    with open(pref_path, "w", encoding="utf-8") as f:
        f.write(content + "\n".join(new_lines) + "\n")
    return len(new_lines)


def save_session(client_name, input_desc="", decisions="", outputs="", pending="", insight="",
                 evidence="", strict_evidence=False, dsh_session=None, light=False, notes=False,
                 entry_type=None):
    """追加一条会话记录到客户 context.md 和 task_history.json

    insight: 本次会话的洞察摘要（如有，由 _insight.py 生成）
    evidence: 分号分隔的来源引用串（file:/session:/decision:/user:），写入前经
              _memory_guard.gate_entry 校验；空串 = 不携带证据（老调用零感知）。
    strict_evidence: True 时证据校验失败即阻断（返回 False，不写任何文件），
                     否则仅警告并照写。
    entry_type: I-3 A2 决策条目类型（--entry-type=keynote_change）；keynote_change
                时 decisions.md 条目改走 append_keynote_change（摘要+版本化指针
                hash+批准人，不复述内容），三道闸语义不变。
    dsh_session: DSH 会话 ID（T8a）。非空时启用会话级 upsert：context.md 会话块
                 标题下一行写 `<!-- dsh:session:ID -->`，最后一块带同 ID 标记则整块
                 替换（会话号不变）；task_history 条目追加 dsh_session 键，同
                 (project, dsh_session) 已存在则原地更新。为空 = 现状 append。
    light: True 时只做证据守门 + context.md upsert + task_history upsert，
           跳过 embedding/版本链索引/bm25/case_cards/session_notes（终点全量 save 补齐索引）。
    notes: P4（2026-08-29）session_notes 默认关；--notes 显式开启才生成独立笔记
           （减负：session_notes 与 context.md 信息重复，默认不再多写一份文件）。
    """
    # 客户名纠错：避免把别名当新客户创建空目录
    try:
        from _aliases import resolve_client_name
        resolved, candidates, matched_by = resolve_client_name(client_name)
        if matched_by == 'alias':
            print(f"[save] 客户名 '{client_name}' 已解析为 '{resolved}'（别名匹配）")
            client_name = resolved
        elif matched_by == 'substring':
            print(f"[save] ⚠️ 客户 '{client_name}' 不存在，近似候选: {', '.join(candidates)}")
            print(f"[save] 继续使用 '{client_name}'，请确认是否需要切换")
    except Exception as e:
        print(f"[warn] 客户名解析失败: {e}")

    # P0 记忆溯源（T2）：写入前守门。放在别名解析之后、ensure_client_dir/快照/
    # 任何写入之前 —— strict 阻断路径零副作用（不建目录、不写快照、不写历史）。
    from _memory_guard import gate_entry
    gate = gate_entry(decisions, evidence, client_name, strict=strict_evidence,
                      entry_type=entry_type)
    if gate["verdict"] == "blocked":
        for r in gate["reasons"]:
            print(f"[证据] 阻断：{r}")
        print("[证据] --strict-evidence 生效，会话未保存")
        return False

    client_path = ensure_client_dir(client_name)
    context_path = os.path.join(client_path, "context.md")

    # P1 健壮性（T7）：按客户文件锁。放在别名解析与证据守门之后、任何写入之前；
    # 获取失败（默认 30s 超时）大声失败：print 明确中文原因并返回 False（不抛异常），
    # cmd_save 据此 exit 2 —— 绝不静默跳过、绝不绕锁写入。
    from _save_lock import acquire_save_lock, release_save_lock
    lock_fd = acquire_save_lock(client_path)
    if lock_fd is None:
        print(f"[锁] 获取保存锁失败：{os.path.join(client_path, '.save_lock')} "
              f"被其他进程持有且 30s 内未释放，会话未保存（避免并发写坏 context.md/task_history）")
        return False

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # P3（2026-09-06）：客户目录存在而 context.md 缺失（手工误删/半初始化）——
        # 锁内按模板补齐后再读，避免读时恒 FileNotFoundError。必须放锁内：
        # 「锁被持有即零写入」是 save 的硬语义（test_session_upsert 锁集成用例）。
        if not os.path.exists(context_path):
            print(f"[warn] 客户 '{client_name}' 目录已存在但 context.md 缺失，按模板补齐")
            from _context import _init_context_file
            _init_context_file(client_path)

        # P1: 写前快照（用于回溯）
        snapshot_path = _snapshot_context(context_path)
        if snapshot_path:
            print(f"[快照] context.md 快照已保存: {os.path.basename(snapshot_path)}")

        # F0-11：context.md 超过 200 行时在追加前自动 compact（保留快照，失败降级 warn）
        if os.path.exists(context_path):
            with open(context_path, "r", encoding="utf-8") as f:
                pre_content = f.read()
            # #50 防再发：存量 context.md 无结构版本标记 -> WARN 提示回填（不阻断）
            if not has_meta_version(pre_content):
                print(f"[warn] {client_name}/context.md 缺少 meta_version 标记"
                      f"（#50 卡片漂移防护），可跑 "
                      f"_scratch/backfill_meta_version.py 回填（不阻断本次保存）")
            if pre_content.count("\n") + 1 > CONTEXT_MAX_LINES:
                try:
                    compact(client_name)
                    print(f"[compact] context.md 超过 {CONTEXT_MAX_LINES} 行，已自动压缩")
                except Exception as e:
                    print(f"[warn] context.md 自动压缩失败（不阻断追加）: {e}")

        try:
            with open(context_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            # P3（2026-09-06）：客户目录存在而 context.md 缺失（或读取失败）时
            # 不再让整次 save 崩掉——ensure_client_dir 已尝试按模板补齐，此处
            # fail-soft 降级为空白上下文继续，报中文原因
            print(f"[warn] context.md 读取失败（{e}），按空白上下文继续保存")
            content = ""

        # 统计现有会话数（兼容旧 ## 格式和新 ### 格式）
        sessions = re.findall(r'#{2,3} \[(\d{4}-\d{2}-\d{2})\]', content)
        last_head = _find_last_session_block(content)

        # S8：save upsert 兜底——无 DSH 会话 ID 时，若最后一块是会话块且日期为今天、
        # 且不带 DSH 标记，则视为同一会话并复用其会话号；否则按原逻辑追加新块。
        if dsh_session:
            session_num = len(sessions) + 1
        else:
            if last_head is not None:
                _, _, _, last_block = last_head
                last_date, last_num = _extract_session_heading(
                    last_block.split("\n", 1)[0]) or (None, None)
                last_has_marker = _DSH_SESSION_MARKER_RE.search(last_block)
                if last_date == today and last_num is not None and not last_has_marker:
                    session_num = last_num
                else:
                    session_num = len(sessions) + 1
            else:
                session_num = len(sessions) + 1

        # P0 决策单轨化：decisions 非空 -> 写入 decisions.md（task 条目，真源），
        # context.md 决策段只留一行引用；同会话幂等由 append_session_decision 保证。
        if decisions and str(decisions).strip():
            session_ref = dsh_session or f"第{session_num}次"
            if entry_type == "keynote_change":
                # I-3 A2：keynote_change 只记变更事件（摘要+指针 hash+批准人），不复述内容
                from _theme_guard import (append_keynote_change, keynote_change_topic,
                                          load_keynote)
                # P3（2026-09-06）：引用标题与 decisions.md 写入标题同源
                # （keynote_change_topic，版本取自 keynote.md）——此前硬编码
                # 「基调变更（session_ref）」与写入的「基调变更 vN」不一致，引用悬空
                _kn = load_keynote(client_name) or {}
                task_topic = keynote_change_topic(_kn.get("version") or "")
                written = append_keynote_change(
                    client_name, str(decisions).strip(), session_ref=session_ref)
            else:
                task_topic = f"会话决策 {today} #{session_ref}"
                from _theme_guard import append_session_decision
                written = append_session_decision(
                    client_name, task_topic, decisions,
                    evidence_marker=gate["marker"], session_ref=session_ref,
                    entry_type=entry_type)
            if written:
                print(f"[决策] task 条目已写入/已更新 decisions.md: {task_topic}（I-6 后写赢）")
                decisions_rendered = f"（见 decisions.md：{task_topic}）"
            elif entry_type == "keynote_change":
                # keynote.md 缺失 -> append_keynote_change 拒写；decisions 不落 decisions.md，
                # 全量留在 context.md（显式可见，不假装登记成功）
                print("[决策] keynote_change 未登记（keynote.md 缺失），决策仅留 context.md")
                decisions_rendered = _render_decisions_with_marker(decisions, gate["marker"])
            else:
                decisions_rendered = f"（见 decisions.md：{task_topic}）"
        else:
            decisions_rendered = _render_decisions_with_marker(decisions, gate["marker"])
        entry = _build_session_entry(today, session_num, input_desc, decisions_rendered,
                                     outputs, pending, gate["evidence_lines"], dsh_session)

        # T8a：会话级 upsert。dsh_session 非空时按标记匹配；否则按日期/会话号匹配。
        # 匹配成功则整块替换（保留旧标题行：日期与会话号不变），否则走现有 append。
        replaced = False
        old_date = old_num = None
        content, replaced, old_head = _upsert_session_block(content, entry, dsh_session)
        if replaced:
            if old_head:
                old_date, old_num = old_head
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(context_path, "a", encoding="utf-8") as f:
                f.write(entry)

        # 会话号口径：upsert 替换时沿用旧块编号，其余情况用新计算值
        reported_num = old_num if replaced else session_num

        # P1: 写后 schema 校验
        schema_ok, schema_issues = _validate_context_schema(context_path)
        if not schema_ok:
            print("[warn] context.md schema 问题：")
            for issue in schema_issues:
                print(f"  - {issue}")

        # #49③/D4 preferences 机器链：偏好类决策自动摘要进 preferences.md
        # （保守关键词 + 同条去重 + 缺文件建骨架；失败不影响 save 主流程）
        if decisions and str(decisions).strip():
            try:
                n_pref = _append_preferences(
                    client_path, str(decisions),
                    session_ref=dsh_session or f"第{reported_num}次")
                if n_pref:
                    print(f"[偏好] preferences.md 新增 {n_pref} 条偏好记录")
            except Exception as e:
                print(f"[偏好] preferences.md 维护跳过: {e}")

        # P1-15（D1）：task_history 全客户共享，按客户锁锁不住跨客户并发
        # （save×save、save×verify_hook 竞态曾把 JSON 写坏后兜底清空全部历史）。
        # 全局锁复用 _save_lock 机制；获取顺序恒为 客户锁→全局锁（各写点一致），无死锁环。
        th_lock_fd = acquire_save_lock(os.path.dirname(TASK_HISTORY),
                                       lock_name=".task_history.lock")
        if th_lock_fd is None:
            print("[锁] task_history 全局锁获取失败且 30s 内未释放，会话未保存（防并发写坏）")
            return False
        try:
            # 同时写入 task_history
            if os.path.exists(TASK_HISTORY):
                with open(TASK_HISTORY, "r", encoding="utf-8") as f:
                    raw = f.read()
                try:
                    history = json.loads(raw)
                    if not isinstance(history, list):
                        # dict 格式（旧版兼容）：抽取 tasks 字段
                        if isinstance(history, dict) and isinstance(history.get("tasks"), list):
                            history = history["tasks"]
                        else:
                            history = []
                except Exception as e:
                    # JSON 解析失败：备份原文件再重置，避免历史记录全丢
                    backup = TASK_HISTORY + f".corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    try:
                        with open(backup, "w", encoding="utf-8") as f:
                            f.write(raw)
                        print(f"[警告] task_history.json 解析失败({e})，已备份到 {backup}")
                    except Exception:
                        print(f"[警告] task_history.json 解析失败({e})，备份失败")
                    history = []
            else:
                os.makedirs(os.path.dirname(TASK_HISTORY), exist_ok=True)
                history = []

            entry_task = {
                "date": today,
                "project": f"client:{client_name}",
                "session": reported_num,
                "input_desc": input_desc,
                # P0 决策单轨化：task_history 只留摘要（≤200 字），全文在 decisions.md
                "decisions": (str(decisions)[:200] if decisions else ""),
                "outputs": outputs,
                "pending": pending,
                "insight": insight,
                "evidence": evidence,
            }
            if dsh_session:
                entry_task["dsh_session"] = dsh_session
                # T8a：按 (project, dsh_session) 查重，已存在 -> 原地更新（date/session 等标识保持）
                idx = _find_task_history_entry(history, client_name, dsh_session)
            elif replaced and old_date:
                # S8 兜底：无 dsh_session 且 context.md 命中按日期/会话号 upsert 时，
                # 同步按 (project, date, session) 更新 task_history，避免双块双条目。
                idx = _find_task_history_entry_by_date_session(
                    history, client_name, old_date, old_num)
            else:
                idx = None

            if idx is not None:
                old = history[idx]
                # 监工修复（2026-08-19）：合并语义——新值非空才覆盖，
                # 空参 upsert 不抹掉先前内容（与 context.md 合并一致）
                # P0：decisions 用摘要版（≤200 字，全文在 decisions.md）
                for _k, _v in (("input_desc", input_desc),
                               ("decisions", entry_task["decisions"]),
                               ("outputs", outputs),
                               ("pending", pending), ("insight", insight),
                               ("evidence", evidence)):
                    if _v:
                        old[_k] = _v
            else:
                if replaced:
                    # 罕见情形：context.md 命中整块替换但 task_history 无对应条目
                    # （如历史被重置/清理）——用旧块的日期与会话号对齐，避免编号错位
                    entry_task["date"] = old_date or today
                    entry_task["session"] = old_num or reported_num
                history.append(entry_task)

            with open(TASK_HISTORY, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        finally:
            release_save_lock(os.path.dirname(TASK_HISTORY), th_lock_fd,
                              lock_name=".task_history.lock")

        # P0 记忆溯源（T2）：证据引用汇总。静默失效是最高优先级 bug，计数必须可见。
        if gate["counts"]["total_refs"] > 0:
            print(f"[证据] 引用 {gate['counts']['total_refs']}：通过 {gate['counts']['passed']} / 待核 {gate['counts']['failed']}{gate['marker']}")
        elif decisions and str(decisions).strip():
            print("[证据] 决策未携带证据（--evidence= 可补）")

        print(f"会话已保存: {client_name} 第 {reported_num} 次")

        # T8a：light 模式只做证据守门 + context.md upsert + task_history upsert，
        # 跳过 embedding/版本链索引/bm25/case_cards/session_notes（终点全量 save 补齐索引）。
        if light:
            print("[light-save] 跳过索引/版本链索引/笔记")
        else:
            # 自动增量更新 Embedding 索引（失败不影响主流程）
            try:
                from _embed_index import build_embedding_index
                print("[索引] 自动增量更新 Embedding...")
                result = build_embedding_index(batch_size=50, force=False)
                if result and isinstance(result, dict):
                    total = len(result.get("vectors", {}))
                    print(f"[索引] 完成: 总计 {total} 个向量")
            except Exception as e:
                print(f"[索引] 增量更新跳过: {e}")

            # 自动同步 BM25 索引（D-117/P1-5 修复：此前 save 只更 Embedding，
            # BM25 长期滞后导致 RRF 双路不对称；节流逻辑见 _sync_bm25_if_stale）
            try:
                _sync_bm25_if_stale(os.path.dirname(TASK_HISTORY), today)
            except Exception as e:
                print(f"[索引] BM25 同步跳过: {e}")

        # 自动更新 outputs_index.json（graph 读取它，必须先于 graph 更新；失败不影响主流程）
        try:
            n_added = update_outputs_index(client_name)
            if n_added:
                print(f"[索引] outputs_index 新增 {n_added} 条产出记录")
        except Exception as e:
            print(f"[索引] outputs_index 更新跳过: {e}")

        # 自动提取案例卡（D-123，业务启动包；失败不影响主流程）
        if not light:
            try:
                n_cards = _extract_case_cards(client_name)
                if n_cards:
                    print(f"[案例] 新增/更新 {n_cards} 张案例卡")
            except Exception as e:
                print(f"[案例] 案例卡提取跳过: {e}")

        # #48/D2 作用域治理：_internal/ 内部账本目录只记账（context/decisions/
        # outputs_index/task_history 照写），跳过版本链与世界书生成（账本不产世界书）
        from _paths import is_internal_client_dir
        _skip_graph_worldbook = is_internal_client_dir(client_path)

        # 自动更新版本链索引 client_graph.json（失败不影响主流程）
        if not light and not _skip_graph_worldbook:
            try:
                print("[graph] 自动更新 client_graph...")
                build_client_graph(client_name)
            except Exception as e:
                print(f"[graph] 更新跳过: {e}")

        # M2-R1：自动更新世界书 client_index.md（直读真源，失败不影响主流程）
        if not light and not _skip_graph_worldbook:
            try:
                from _worldbook import build_worldbook
                print("[worldbook] 自动更新 client_index...")
                build_worldbook(client_name)
            except Exception as e:
                print(f"[worldbook] 更新跳过: {e}")

        # 三项强制检查（project_rules.md 会话结束 MANDATORY）
        import glob
        warnings = []
        # 检查 1：inbox/ 残留 .py/.log/.tmp/.pyc/.bak
        for ext in (".py", ".log", ".tmp", ".pyc", ".bak"):
            junk = glob.glob(os.path.join(INBOX_DIR, f"*{ext}"))
            if junk:
                warnings.append(f"inbox/ 有残留: {[os.path.basename(f) for f in junk]}")
        # 检查 2：产出路径合规（outputs 字段提到的文件应落在 output/{客户}/ 下）
        if outputs and isinstance(outputs, str):
            for line in outputs.splitlines():
                line = line.strip()
                if line and (line.endswith(".html") or line.endswith(".pptx") or line.endswith(".docx") or line.endswith(".xlsx")):
                    # 检查是否在 output/{客户}/ 路径下
                    expected_prefix = os.path.join(SCRIPT_DIR, "output", client_name)
                    if not os.path.isabs(line):
                        line_abs = os.path.join(SCRIPT_DIR, line)
                    else:
                        line_abs = line
                    # P3（2026-09-06）：前缀比对补分隔符边界——裸 startswith 会让
                    # 「蓝海」误配「蓝海v2」（参考 _indexer._is_valid_proj_key 的边界口径）
                    expected_abs = os.path.abspath(expected_prefix)
                    if not os.path.abspath(line_abs).startswith(expected_abs + os.sep):
                        warnings.append(f"产出路径不合规（应在 output/{client_name}/）: {line}")
        # 检查 3：_uncategorized/ 堆积
        uncat = os.path.join(KNOWLEDGE_DIR, "clients", "_uncategorized")
        if os.path.isdir(uncat):
            n = len(os.listdir(uncat))
            if n > 0:
                warnings.append(f"_uncategorized/ 堆积 {n} 个文件")

        if warnings:
            print("[warn] 会话结束检查警告：")
            for w in warnings:
                print(f"  - {w}")

        # 生成 session_notes 独立笔记（P4：默认关，--notes 显式开启；light 模式跳过）
        if not light and notes:
            try:
                notes_path = os.path.join(client_path, f"session_notes_{today}.md")
                notes_lines = [
                    f"# 会话笔记 · {client_name} · {today}（第 {reported_num} 次）",
                    "",
                    "## 本次目标",
                    input_desc[:200] if input_desc else "(未记录)",
                    "",
                    "## 完成项",
                    outputs[:500] if outputs else "(未记录)",
                    "",
                    "## 待办",
                    pending[:500] if pending else "(无待办)",
                    "",
                    "## 关键决策",
                    decisions[:500] if decisions else "(未记录)",
                    "",
                ]
                with open(notes_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(notes_lines))
                print(f"[笔记] session_notes 已生成: {os.path.basename(notes_path)}")
            except Exception as e:
                print(f"[笔记] session_notes 生成失败（不阻断）: {e}")

        return True  # 正常完成（旧版返回 warnings 且调用方均忽略；T2 起改 bool 供 _cli 判阻断）
    finally:
        # P1 健壮性（T7）：任何路径（含异常传播）都释放锁；自己持有的锁 remove 必成功
        release_save_lock(client_path, lock_fd)


def parse_args(args):
    """解析 save 子命令的会话内容键（原样传入，见 _cli.py p_save 的 extra 参数）。

    返回 dict：
      - input_desc / decisions / outputs / pending：原有四键，行为不变；
      - evidence：分号分隔的来源引用串（file:/session:/decision:/user:），原样存；
      - strict_evidence："1"/"true"/"yes"（大小写不敏感）为 True，其余 False，缺省 False；
      - dsh_session：`--dsh-session=ID` 的 DSH 会话 ID（T8a），缺省 None；
      - light：`--light` 或 `--light=1` 为 True（T8a），缺省 False；
      - notes：`--notes` 为 True（P4，缺省 False——session_notes 默认不生成）。
      - entry_type：`--entry-type=keynote_change`（I-3 A2），缺省 None。
    """
    result = {"input_desc": "", "decisions": "", "outputs": "", "pending": "",
              "evidence": "", "strict_evidence": False,
              "dsh_session": None, "light": False, "notes": False,
              "entry_type": None}
    for arg in args:
        if arg.startswith("--input="):
            result["input_desc"] = arg[8:]
        elif arg.startswith("--decisions="):
            result["decisions"] = arg[12:]
        elif arg.startswith("--outputs="):
            result["outputs"] = arg[10:]
        elif arg.startswith("--pending="):
            result["pending"] = arg[10:]
        elif arg.startswith("--evidence="):
            result["evidence"] = arg[len("--evidence="):]
        elif arg.startswith("--strict-evidence="):
            result["strict_evidence"] = arg[len("--strict-evidence="):].strip().lower() in ("1", "true", "yes")
        elif arg.startswith("--dsh-session="):
            result["dsh_session"] = arg[len("--dsh-session="):] or None
        elif arg == "--light":
            result["light"] = True
        elif arg.startswith("--light="):
            result["light"] = arg[len("--light="):].strip().lower() in ("1", "true", "yes")
        elif arg == "--notes":
            result["notes"] = True
        elif arg.startswith("--entry-type="):
            result["entry_type"] = arg[len("--entry-type="):] or None
    return result


# ============================================================
# P1-2：客户简报（session-start 增强）
# ============================================================
def build_client_brief(client_name):
    """从客户档案派生 session-start 客户简报。

    不新增命令、不新增数据文件；只读既有 context.md / decisions.md /
    refs/ / client_index.md / session_state.json。
    """
    # E 组遗留：经 client_dir() 按名解析支持 _internal/ 内部账本目录回退——
    # #48 迁移后账本客户（通用/工程/专家等）session-start 不再误报「档案不存在」
    from _paths import CLIENTS_DIR, client_dir as _resolve_client_dir
    from _state import get_state

    brief = {
        "client": client_name,
        "exists": False,
        "stage": "intake",
        "task_id": "",
        "recent_decisions": [],
        "head_context": "",
        "refs": [],
        "missing": [],
    }
    if not client_name:
        brief["missing"].append("未指定客户")
        return brief

    cdir = _resolve_client_dir(client_name, clients_dir=CLIENTS_DIR)
    if not os.path.isdir(cdir):
        brief["missing"].append("客户档案不存在或未初始化")
        return brief
    brief["exists"] = True

    try:
        st = get_state(client_name)
        brief["stage"] = st.get("stage", "intake")
        brief["task_id"] = st.get("taskId", "")
    except Exception as e:
        brief["missing"].append(f"session_state 读取失败: {e}")

    try:
        from _theme_guard import load_recent_task_decisions, pre_check
        brief["recent_decisions"] = load_recent_task_decisions(client_name, limit=3) or []
        _pc = pre_check(client_name) or {}
        brief["head_context"] = (_pc.get("head_context") or "")[:400]
    except Exception as e:
        brief["missing"].append(f"决策/铁律读取失败: {e}")

    refs_dir = os.path.join(cdir, "refs")
    if os.path.isdir(refs_dir):
        brief["refs"] = sorted(
            f for f in os.listdir(refs_dir)
            if not f.startswith(".") and os.path.isfile(os.path.join(refs_dir, f))
        )
        if not brief["refs"]:
            brief["missing"].append("refs 目录为空（客户材料未摄入）")
    else:
        brief["missing"].append("无 refs 目录（客户材料未摄入）")

    context_path = os.path.join(cdir, "context.md")
    if not os.path.exists(context_path):
        brief["missing"].append("context.md 缺失")
    else:
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                ctx_text = f.read()
            if "待澄清" not in ctx_text and "open_questions" not in ctx_text.lower():
                brief["missing"].append("context.md 未见待澄清问题/open_questions 段")
        except OSError:
            brief["missing"].append("context.md 读取失败")

    if not brief["missing"]:
        brief["missing"] = []  # 保留字段为空数组，表示无缺口
    return brief


# ============================================================
# IDE 模式钩子（auto_for_input）
# ============================================================
def auto_for_input(user_input, client_name=None):
    """IDE 模式：AI 收到用户输入时自动调用。

    组合 detect_level + load_context_by_level + recall，返回结构化上下文。
    失败时返回降级结果（含 warnings），不抛异常。

    返回 schema:
    {
        "level": "L3"|"L4"|"L5",
        "mode": "directed"|"collaborative"|"autonomous",
        "context_summary": str,          # ≤2000 字（R1-4 放宽非 JSON 路径摘要）
        "loaded_context": dict,          # load_context_by_level 的返回
        "recall": list,                 # ≤5 条召回结果
        "warnings": list                 # 钩子失败时的降级警告
    }
    """
    warnings = []

    # 1. 判层级
    try:
        level, mode = detect_level(user_input)
    except Exception as e:
        level, mode = "L4", "collaborative"
        warnings.append(f"detect_level 失败，默认 L4: {e}")

    # 2. 按层级加载上下文
    loaded = {}
    if client_name:
        try:
            loaded = load_context_by_level(client_name, level) or {}
        except Exception as e:
            warnings.append(f"load_context_by_level 失败: {e}")

    # 3. 语义召回（≤5 条，token 预算控制）
    recall_results = []
    try:
        recall_results = recall(
            user_input, client_name=client_name,
            use_embedding=True, return_results=True
        ) or []
        recall_results = recall_results[:5]
    except Exception as e:
        warnings.append(f"recall 失败: {e}")

    # 3.5 P1：附带 HEAD/TAIL 结构化返回（供 DSH folio_session_start 消费；
    #      KIMI/CLI 非 JSON 分支同样打印等价出口）
    head_context = ""
    tail_checklist = ""
    keynote = None
    if client_name:
        try:
            from _theme_guard import pre_check
            _pc = pre_check(client_name)
            head_context = _pc.get("head_context", "") or ""
            tail_checklist = _pc.get("tail_checklist", "") or ""
            keynote = _pc.get("keynote")  # I-3 A3：只增不改（缺失为 None）
        except Exception as e:
            warnings.append(f"pre_check 失败: {e}")

    # 4. 生成摘要（R1-4：非 JSON 路径从 500 放宽到 2000，控制 token 预算）
    summary_cap = 2000
    summary_parts = []
    if loaded.get("client_index"):
        summary_parts.append(f"客户索引: {loaded['client_index'][:summary_cap]}")
    elif loaded.get("decisions"):
        summary_parts.append(f"上次决策: {loaded['decisions'][:summary_cap]}")
    if recall_results:
        summary_parts.append(f"相关召回 {len(recall_results)} 条")
    context_summary = " | ".join(summary_parts)[:summary_cap] if summary_parts else "无历史上下文"

    # P1-2：客户简报（阶段/任务状态/决策摘要/铁律 HEAD/refs/缺失信息）
    client_brief = {}
    if client_name:
        try:
            client_brief = build_client_brief(client_name)
        except Exception as e:
            client_brief = {"client": client_name, "missing": [f"客户简报生成失败: {e}"]}

    return {
        "level": level,
        "mode": mode,
        "context_summary": context_summary,
        "loaded_context": loaded,
        "client_index": (loaded.get("client_index") or ""),
        "recent_task_decisions": (loaded.get("recent_task_decisions") or []),
        "head_context": head_context,
        "tail_checklist": tail_checklist,
        "keynote": keynote,
        "client_brief": client_brief,
        "recall": recall_results,
        "warnings": warnings,
    }



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python _session.py list                                    列出所有客户")
        print("  python _session.py status                                  所有客户状态一览")
        print("  python _session.py load <客户名>                           加载客户上下文")
        print("  python _session.py save <客户名> [参数...]                 保存会话")
        print("       --input=\"描述\" --decisions=\"决策\" --outputs=\"文件\" --pending=\"待办\"")
        print("  python _session.py recall <关键词>                         召回相关项目")
        print("  python _session.py compact <客户名> [保留最近N次]          压缩历史上下文")
        sys.exit(0)

    action = sys.argv[1]

    if action == "list":
        print("客户项目:", list_clients())

    elif action == "status":
        show_all_clients()

    elif action == "load" and len(sys.argv) >= 3:
        load_context(sys.argv[2])

    elif action == "save" and len(sys.argv) >= 3:
        client = sys.argv[2]
        kwargs = parse_args(sys.argv[3:])
        if not any(kwargs.values()):
            print(f"保存 {client} 的会话记录：")
            kwargs["input_desc"] = input(" 本次输入（简述）: ").strip()
            kwargs["decisions"] = input(" 关键决策: ").strip()
            kwargs["outputs"] = input(" 产出文件: ").strip()
            kwargs["pending"] = input(" 待办事项: ").strip()
        save_session(client, **kwargs)

    elif action == "recall" and len(sys.argv) >= 3:
        recall(" ".join(sys.argv[2:]))

    elif action == "compact" and len(sys.argv) >= 3:
        client = sys.argv[2]
        keep_last = int(sys.argv[3]) if len(sys.argv) >= 4 else 1
        compact(client, keep_last)

    else:
        print("无效命令")
