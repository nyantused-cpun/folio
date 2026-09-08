# -*- coding: utf-8 -*-
"""定制页 pattern 育种登记闭环（S10-3a，C-G3）+ 观察项 TTL 最小机检（S10-3e）。

规格源：docs/视觉生产线_创意模式_开发计划_2026-09-07.md §四 3a/3e +
docs/plans/2026-09-07_总体修改计划_发版稳定版.md §四 S10。crafted 定制页跑稳
后，验证过的高层核心图 pattern 不随产物散佚——育种区把「候选 → 量化门槛 →
提炼评审 → 入库」变成可审计的登记闭环（状态机）：

  candidate ── add_confirmation(≥2 客户) ──▶ evaluate(双条件) ──▶ promote
     │                                          │                  │
     │ archive_stale(N 月未动)                  │            无 refs → breeding（提炼中）
     ▼                                          │            带 refs → promoted（入账）
  archived ◀────────────────────────────────────┴── P6 六问评审（流程文档 §3）

量化门槛（evaluate 双条件，缺一不可）：
  ① ≥2 个**不同客户**的确认（同客户重复确认不叠加）；
  ② registered_at 距今 ≥14 天（结构稳定期：刚登记的好看不作数）。
尸体清理：candidate/breeding 超 N 月（按 30 天/月折算）末次无活动 → archived；
季度审计：近 90 天登记数 vs promote 数，0 转化且有登记 → 复盘建议 flag。

读写纪律：登记库单文件 `_knowledge/breeding/registry.json`（JSON 数组），
读-合并-写全程持锁——复用 _save_lock 原子创建语义（W1-4 `.review_log.lock`
先例），锁文件 `.breeding.lock` 与 registry 同目录；获取失败重试 1 次后大声
失败，绝不绕锁写。只读面（list/evaluate/quarterly_audit）不加锁。

「候选自动登记」口径：本批交付登记件（API/CLI/钩子测试）；渲染链自动触发
钩子受 `_cli_generate` cap 顶满（1200/1200 一字不加）所限挂账后续，先以
「人工登记 + `breed audit` 季度审计兜底」节律运行。

3e 附 `scan_observation_ttl`（最小机检）：扫「观察级/观察模式/观察中/观察项」
命中行，缺 `TTL(YYYY-MM-DD):` 或 `升级条件:` 标注的列出清单。机制与存量盘点
见 docs/观察项TTL盘点_2026-09-08.md；_cli_audit cap 顶满不动，audit 集成不
强制（`breed ttl` 可跑，观察级恒不 FAIL）。
"""
import datetime
import glob
import json
import os
import re
import sys

from _cli_infra import SCRIPT_DIR
from _paths import rel_to_script

REGISTRY_REL_DIR = os.path.join("_knowledge", "breeding")  # 登记库目录（相对项目根）
LOCK_NAME = ".breeding.lock"
LOCK_TIMEOUT = 5.0        # 首次获取超时（秒），对齐 _review.py 先例
LOCK_RETRY_TIMEOUT = 10.0  # 重试一次的超时（秒）
STATUSES = ("candidate", "breeding", "promoted", "archived")
MIN_DISTINCT_CLIENTS = 2  # 量化门槛①：不同客户确认数
MIN_STABLE_DAYS = 14      # 量化门槛②：结构稳定期（天）
STALE_MONTHS = 3          # 尸体清理默认阈值（月，按 30 天折算）
DAYS_PER_MONTH = 30
AUDIT_WINDOW_DAYS = 90    # 季度审计窗口

# 3e 观察项机检口径：命中词 + 合法标注（一行内可 grep：TTL\(\d{4}-\d{2}-\d{2}\)|升级条件:）
_OBS_TERM_RE = re.compile(r"观察级|观察模式|观察中|观察项")
_TTL_RE = re.compile(r"TTL\(\d{4}-\d{2}-\d{2}\)|升级条件:")


# ── 路径与底层读写 ────────────────────────────────────────────────────────

def breeding_dir():
    """登记库目录（读模块全局，测试 monkeypatch SCRIPT_DIR 后跟随）。"""
    return os.path.join(SCRIPT_DIR, REGISTRY_REL_DIR)


def registry_path(registry=None):
    """registry 显式参数优先；缺省 `_knowledge/breeding/registry.json`。"""
    return registry or os.path.join(breeding_dir(), "registry.json")


def _load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _save(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _mutate(registry, mutator):
    """读-合并-写全程持锁（W1-4 先例）。mutator(entries) -> (entries|None, payload)。

    entries=None 表示只读突变（dry-run），不落盘。锁获取失败重试 1 次，
    仍失败 print 中文原因并返回 None（调用方降级为失败，绝不绕锁写）。
    """
    from _save_lock import acquire_save_lock, release_save_lock
    path = registry_path(registry)
    lock_dir = os.path.dirname(path)
    fd = acquire_save_lock(lock_dir, timeout=LOCK_TIMEOUT, lock_name=LOCK_NAME)
    if fd is None:
        fd = acquire_save_lock(lock_dir, timeout=LOCK_RETRY_TIMEOUT, lock_name=LOCK_NAME)
    if fd is None:
        print(f"[breeding] 登记库写入失败（不绕锁）: {LOCK_NAME} 获取超时"
              "（可能有并发写会话，稍后重试）")
        return None
    try:
        entries, payload = mutator(_load(path))
        if entries is not None:
            _save(path, entries)
        return payload
    finally:
        release_save_lock(lock_dir, fd, lock_name=LOCK_NAME)


def _slugify(name):
    """模式名 → id slug：保留中文/字母数字/-/_，其余折叠为 -，空则 breed。"""
    s = re.sub(r"\s+", "-", str(name).strip())
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]", "", s).strip("-")
    return (s or "breed")[:60]


def _find(entries, breed_id):
    """按 id 精确匹配，name 兜底（CLI 人操场景允许报名字）。"""
    key = str(breed_id).strip()
    for e in entries:
        if isinstance(e, dict) and key and key in (e.get("id"), e.get("name")):
            return e
    return None


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _today():
    return datetime.date.today()


def _last_active(entry):
    """末次活动日期 = max(registered_at, breeding_at, 各确认 date)。"""
    dates = [_parse_date(entry.get("registered_at")), _parse_date(entry.get("breeding_at"))]
    dates += [_parse_date(c.get("date"))
              for c in entry.get("confirmations", []) or [] if isinstance(c, dict)]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def _distinct_clients(entry):
    return sorted({str(c.get("client")) for c in entry.get("confirmations", []) or []
                   if isinstance(c, dict) and c.get("client")})


# ── 育种 API（读-合并-写 + 锁）────────────────────────────────────────────

def register_candidate(name, source, notes="", registry=None, today=None):
    """登记候选 pattern。幂等：同名非归档条目已存在 → 原样返回 (entry, False)。

    返回 (entry, created)；锁获取失败 entry=None。
    """
    name = str(name or "").strip()
    if not name:
        return None, False
    day = (today or _today()).isoformat()

    def _mut(entries):
        for e in entries:
            if isinstance(e, dict) and e.get("name") == name and e.get("status") != "archived":
                return None, (e, False)  # entries=None：幂等命中不写盘
        used = {e.get("id") for e in entries if isinstance(e, dict)}
        base, bid, n = _slugify(name), _slugify(name), 2
        while bid in used:
            bid = f"{base}-{n}"
            n += 1
        entry = {"id": bid, "name": name, "source": str(source or ""),
                 "registered_at": day, "confirmations": [], "status": "candidate",
                 "promoted_refs": [], "notes": str(notes or "")}
        entries.append(entry)
        return entries, (entry, True)

    payload = _mutate(registry, _mut)
    return payload if payload is not None else (None, False)


def add_confirmation(breed_id, client, registry=None, today=None):
    """追加客户确认（同客户去重：重复确认幂等不叠加）。返回 (entry, added)。

    条目不存在 → (None, False)。
    """
    client = str(client or "").strip()
    day = (today or _today()).isoformat()

    def _mut(entries):
        e = _find(entries, breed_id)
        if e is None:
            return None, (None, False)
        if any(isinstance(c, dict) and c.get("client") == client
               for c in e.get("confirmations", []) or []):
            return None, (e, False)  # 同客户重复确认不写盘
        e.setdefault("confirmations", []).append({"client": client, "date": day})
        return entries, (e, True)

    payload = _mutate(registry, _mut)
    return payload if payload is not None else (None, False)


def evaluate(breed_id, registry=None, today=None):
    """量化门槛判定（双条件）。返回判定 dict；条目不存在 → None。

    {"id","name","status","distinct_clients","clients","days_stable",
     "suggest"("promote"|"wait"),"missing":[未达原因]}
    """
    e = _find(_load(registry_path(registry)), breed_id)
    if e is None:
        return None
    today_d = today or _today()
    reg = _parse_date(e.get("registered_at"))
    days = (today_d - reg).days if reg else -1
    clients = _distinct_clients(e)
    missing = []
    if len(clients) < MIN_DISTINCT_CLIENTS:
        missing.append(f"客户确认不足（{len(clients)}/{MIN_DISTINCT_CLIENTS}，同客户重复不叠加）")
    if days < MIN_STABLE_DAYS:
        missing.append(f"结构稳定期不足（登记 {days} 天 < {MIN_STABLE_DAYS} 天）")
    if e.get("status") == "archived":
        missing.append("条目已归档（重新登记再走门槛）")
    return {"id": e.get("id"), "name": e.get("name"), "status": e.get("status"),
            "distinct_clients": len(clients), "clients": clients, "days_stable": days,
            "suggest": "promote" if not missing else "wait", "missing": missing}


def promote(breed_id, refs=(), registry=None, today=None):
    """状态迁移：candidate/breeding → breeding（无 refs，进入 P6 提炼评审）
    或 → promoted（带 refs，提炼产物落库）。返回 (entry, ok, reason)。
    """
    day = (today or _today()).isoformat()
    ref_list = [r.strip() for r in refs or [] if str(r).strip()]

    def _mut(entries):
        e = _find(entries, breed_id)
        if e is None:
            return None, (None, False, f"未找到 breed: {breed_id}")
        if e.get("status") == "archived":
            return None, (e, False, "已归档条目不可 promote（重新登记）")
        if e.get("status") == "promoted":
            return None, (e, False, "已是 promoted 状态")
        if ref_list:
            e["status"] = "promoted"
            e["promoted_refs"] = ref_list
            e["promoted_at"] = day
            return entries, (e, True, "promoted")
        e["status"] = "breeding"
        e["breeding_at"] = day
        return entries, (e, True, "breeding")

    payload = _mutate(registry, _mut)
    return payload if payload is not None else (None, False, "锁获取失败")


def archive_stale(months=STALE_MONTHS, registry=None, today=None, apply=False):
    """尸体清理：candidate/breeding 超 N 月末次无活动 → archived。

    apply=False 只盘点（dry-run，不落盘）；返回触及条目清单
    [{"id","name","status","last_active","idle_days"}]。
    """
    today_d = today or _today()
    horizon = int(months * DAYS_PER_MONTH)

    def _mut(entries):
        stale = []
        for e in entries:
            if not isinstance(e, dict) or e.get("status") not in ("candidate", "breeding"):
                continue
            la = _last_active(e)
            idle = (today_d - la).days if la else None
            if idle is None or idle < horizon:
                continue
            stale.append({"id": e.get("id"), "name": e.get("name"),
                          "status": e.get("status"),
                          "last_active": la.isoformat(), "idle_days": idle})
            if apply:
                e["status"] = "archived"
                e["archived_at"] = today_d.isoformat()
        return (entries if apply else None), stale

    payload = _mutate(registry, _mut)
    return payload if payload is not None else []


def quarterly_audit(today=None, registry=None):
    """季度转化率：近 90 天登记数 vs promote 数；0 转化且有登记 → 复盘 flag。"""
    today_d = today or _today()
    since = today_d - datetime.timedelta(days=AUDIT_WINDOW_DAYS)
    registered = promoted = 0
    for e in _load(registry_path(registry)):
        if not isinstance(e, dict):
            continue
        reg, pro = _parse_date(e.get("registered_at")), _parse_date(e.get("promoted_at"))
        if reg and since <= reg <= today_d:
            registered += 1
        if pro and since <= pro <= today_d:
            promoted += 1
    zero_convert = registered > 0 and promoted == 0
    return {"window_days": AUDIT_WINDOW_DAYS, "registered": registered,
            "promoted": promoted, "zero_convert": zero_convert,
            "review_suggested": zero_convert}


def list_breeds(registry=None, status=None):
    """登记库全量（可按 status 过滤），只读。"""
    entries = [e for e in _load(registry_path(registry)) if isinstance(e, dict)]
    return [e for e in entries if e.get("status") == status] if status else entries


# ── 3e：观察项 TTL 最小机检 ──────────────────────────────────────────────

def _default_ttl_targets():
    """默认扫描面：根目录 _*.py + _renderer/*.py + .folio/skills/**/*.md。

    docs/ 历史归档报告不扫（盘点表单点维护）；tests/ 与 output/ 不属观察项载体；
    本模块（TTL 机制自身）自排除——docstring/注释里的「观察」是机制元描述，不是债。
    """
    this = os.path.abspath(__file__)
    targets = [t for t in sorted(glob.glob(os.path.join(SCRIPT_DIR, "_*.py")))
               if os.path.abspath(t) != this]
    targets += sorted(glob.glob(os.path.join(SCRIPT_DIR, "_renderer", "*.py")))
    targets += sorted(glob.glob(os.path.join(SCRIPT_DIR, ".folio", "skills", "**", "*.md"),
                                recursive=True))
    return targets


def scan_observation_ttl(targets=None):
    """观察项 TTL 机检（3e）：命中观察词但缺 `TTL(日期)`/`升级条件:` 标注的行。

    返回 [(rel_path, line_no, text)]；targets 参数供单测注入 tmp 文件清单。
    观察级报告面（恒不 FAIL）；机制与存量盘点见 docs/观察项TTL盘点_2026-09-08.md。
    """
    if targets is None:
        targets = _default_ttl_targets()
    missing = []
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        rel = rel_to_script(path)
        for i, line in enumerate(lines, 1):
            if _OBS_TERM_RE.search(line) and not _TTL_RE.search(line):
                missing.append((rel, i, line.strip()[:100]))
    return missing


# ── CLI（_cli.py 仅注册，业务在此）────────────────────────────────────────

def cmd_breed(args):
    """`breed` 子命令入口。exit 0 成功（含 warn）/ 1 失败，对齐 cli_contract v1。"""
    action = getattr(args, "action", None) or "list"
    target = str(getattr(args, "target", "") or "").strip()

    if action == "list":
        entries = list_breeds()
        if not entries:
            print("ℹ 育种登记库为空（_knowledge/breeding/registry.json；"
                  "breed register 登记首条）")
            return
        print(f"育种登记库共 {len(entries)} 条：")
        for e in entries:
            clients = "、".join(_distinct_clients(e)) or "无"
            refs = "、".join(e.get("promoted_refs") or [])
            print(f"  [{e.get('status', '?')}] {e.get('id')}  {e.get('name')}"
                  f"（登记 {e.get('registered_at')}，确认 {len(e.get('confirmations') or [])}"
                  f": {clients}）" + (f" refs: {refs}" if refs else ""))
        return

    if action == "register":
        if not target:
            print("[错误] 用法: breed register <模式名> --source <出处页/deck 路径> [--notes 备注]")
            sys.exit(1)
        if not str(getattr(args, "source", "") or "").strip():
            print("[错误] breed register 需要 --source <出处页/deck 路径>（候选必须可溯源）")
            sys.exit(1)
        entry, created = register_candidate(target, args.source, notes=getattr(args, "notes", ""))
        if entry is None:
            sys.exit(1)
        if created:
            print(f"✓ 已登记候选 {entry['id']}（{entry['name']}）→ candidate；"
                  f"量化门槛：≥{MIN_DISTINCT_CLIENTS} 客户确认 + 登记满 {MIN_STABLE_DAYS} 天"
                  "（流程：docs/育种闭环流程_2026-09-08.md）")
        else:
            print(f"= 同名候选已存在（幂等返回）: {entry['id']}（{entry['name']}，"
                  f"status={entry['status']}）")
        return

    if action == "confirm":
        client = str(getattr(args, "client", "") or "").strip()
        if not target or not client:
            print("[错误] 用法: breed confirm <id> --client <客户名>")
            sys.exit(1)
        entry, added = add_confirmation(target, client)
        if entry is None:
            print(f"[错误] 未找到 breed: {target}（breed list 查看）")
            sys.exit(1)
        if added:
            rep = evaluate(target)
            n = rep["distinct_clients"] if rep else "?"
            print(f"✓ 已记录确认：{entry['id']} ← {client}（不同客户 {n}）")
        else:
            print(f"= {client} 已确认过 {entry['id']}（同客户重复确认不叠加）")
        return

    if action == "evaluate":
        rep = evaluate(target) if target else None
        if rep is None:
            print("[错误] 用法: breed evaluate <id>（breed list 查看）")
            sys.exit(1)
        if rep["suggest"] == "promote":
            print(f"✓ {rep['id']}（{rep['name']}）达量化门槛：{rep['distinct_clients']} 客户确认 / "
                  f"稳定 {rep['days_stable']} 天 → 建议 promote（先过 P6 六问评审，"
                  "见 docs/育种闭环流程_2026-09-08.md §3）")
        else:
            print(f"… {rep['id']}（{rep['name']}）未达门槛：{'；'.join(rep['missing'])}")
        return

    if action == "promote":
        refs = [r.strip() for r in str(getattr(args, "refs", "") or "").split(",") if r.strip()]
        entry, ok, reason = promote(target, refs)
        if entry is None or not ok:
            print(f"[错误] promote 失败: {reason}")
            sys.exit(1)
        if entry.get("status") == "breeding":
            print(f"✓ {entry['id']} → breeding（提炼评审中）；"
                  "P6 六问通过后带 --refs 落库转 promoted")
        else:
            print(f"✓ {entry['id']} → promoted，refs={entry.get('promoted_refs')}")
            print("  入账动作：schema 元素/gold 样张落库 + decisions.md 登记"
                  "（清单见 docs/育种闭环流程_2026-09-08.md §4）")
        return

    if action == "audit":
        stale = archive_stale(apply=False)
        rep = quarterly_audit()
        if stale:
            print(f"尸体清理 dry-run（{len(stale)} 条超期未提炼；加 --archive 实归档）:")
            for s in stale:
                print(f"  {s['id']}（{s['name']}，{s['status']}，末次活动 "
                      f"{s['last_active']}，闲置 {s['idle_days']} 天）")
        else:
            print("尸体清理 dry-run：无超期 candidate/breeding")
        print(f"季度转化率（近 {rep['window_days']} 天）: 登记 {rep['registered']} / "
              f"promote {rep['promoted']}")
        if rep["review_suggested"]:
            print("⚠ 连续 0 转化：建议触发自由轨复盘（登记多提炼少——门槛是否过严/来源是否跑偏），"
                  "结论走 save --decisions= 入 decisions.md")
        if getattr(args, "archive", False) and stale:
            archive_stale(apply=True)
            print(f"✓ 已实归档 {len(stale)} 条 → archived")
        return

    if action == "ttl":
        missing = scan_observation_ttl()
        if missing:
            print(f"观察项 TTL 机检：{len(missing)} 行缺 TTL(YYYY-MM-DD)/升级条件 标注"
                  "（机制与存量盘点见 docs/观察项TTL盘点_2026-09-08.md）:")
            for rel, ln, text in missing[:20]:
                print(f"  {rel}:{ln}: {text}")
            if len(missing) > 20:
                print(f"  … 还有 {len(missing) - 20} 行")
        else:
            print("✓ 全部观察项命中行均带 TTL/升级条件 标注")
        print("（观察级报告，恒不 FAIL）")
        return

    print(f"[错误] 未知子动作: {action}")
    sys.exit(1)
