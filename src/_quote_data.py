# -*- coding: utf-8 -*-
"""报价数据层 — 数据结构 + Library + QuoteBuilder。
纯数据逻辑，不碰任何渲染。

数据流: spec.yml → QuoteBuilder → QuoteData → 渲染器(HTML/Excel)
"""
import os
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
LIBRARY_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "quote_library")
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "报价版式")


# ============================================================
# 数据结构
# ============================================================

class QuoteData:
    """报价的标准化中间表示"""
    def __init__(self):
        self.metadata = {}   # client/contact/date/quote_number/version/valid_until/payment_terms
        self.sections = []   # list[Section]
        self.summary = []    # list[(label, amount_or_formula)]
        self.summary_total = 0
        self.payments = []   # list[dict: time/type/ratio/amount]

    def total_amount(self):
        return sum(s.total_amount for s in self.sections)


class Section:
    """一个报价区块（模块/实施/许可...）"""
    def __init__(self, title, headers, section_id="", sheet_ref=""):
        self.title = title
        self.section_id = section_id
        self.sheet_ref = sheet_ref   # 对应的 sheet 名（多 sheet 模板用）
        self.headers = headers       # ["编号","名称","描述","单价","折扣","数量","金额"]
        self.items = []              # list[Item]
        self.total_label = ""
        self.total_amount = 0.0
        self.col_keys = []           # ["index","name","description","unit_price","discount","quantity","amount"]

    @property
    def total_amount_computed(self):
        # P2：浮点累加后取整到 2 位，避免 0.01 级别误差
        return round(sum(it.amount for it in self.items), 2)

    @property
    def original_amount(self):
        """折前原价 = Σ(单价 × 数量)"""
        return round(sum(it.unit_price * it.quantity for it in self.items), 2)

    @property
    def discount_summary(self):
        """折扣摘要文本"""
        if not self.items:
            return ""
        discounts = set()
        for it in self.items:
            if it.is_gift:
                discounts.add("赠送")
            elif it.discount == 1:
                discounts.add("不参与折扣")
            else:
                discounts.add(f"{int(it.discount * 100)}%")
        if len(discounts) == 1:
            return discounts.pop()
        return "部分折扣"


class Item:
    """一行报价明细"""
    def __init__(self, index=0, name="", description="", unit_price=0,
                 discount=1, quantity=1, amount=0, is_gift=False, discount_display="",
                 role=""):
        self.index = index
        self.name = name
        self.description = description
        self.role = role
        self.unit_price = unit_price
        self.discount = discount         # 数字折扣值
        self.discount_display = discount_display  # 显示值（可能是文字）
        self.quantity = quantity
        self.amount = amount
        self.is_gift = is_gift


# ============================================================
# 折扣标准化
# ============================================================

def normalize_discount(discount_value, global_discount=1.0):
    """标准化折扣值。
    返回 (numeric_discount, is_gift, display_text)
    - 数字 → (数字, False, "30%")
    - 文字（赠送/特批赠送/免费开放） → (0, True, "文字本身")
    - 空/None → (global_discount, False, "100%")
    """
    if discount_value is None or discount_value == "":
        d = global_discount if global_discount is not None else 1
        return d, False, f"{int(d * 100)}%" if isinstance(d, (int, float)) else str(d)
    if isinstance(discount_value, (int, float)):
        return discount_value, False, f"{int(discount_value * 100)}%"
    # 字符串
    # P1-6：先尝试解析百分号字符串（"50%" → 0.5），再回退到赠送
    if isinstance(discount_value, str):
        stripped = discount_value.strip()
        if stripped.endswith("%"):
            try:
                pct = float(stripped[:-1])
                ratio = pct / 100.0
                return ratio, False, f"{int(ratio * 100)}%"
            except (ValueError, TypeError):
                pass  # 解析失败则走赠送逻辑
    try:
        d = float(discount_value)
        return d, False, f"{int(d * 100)}%"
    except (ValueError, TypeError):
        return 0, True, str(discount_value)


# ============================================================
# Library — 内容库
# ============================================================

class Library:
    """内容库 — id 刚性 + 名称模糊 + 描述搜索"""
    def __init__(self):
        self.data = {}
        self._name_index = {}
        for fname, root_key in [
            ("modules.yaml", "modules"),
            ("licenses.yaml", "licenses"),
            ("services.yaml", "roles"),
            ("services.yaml", "tasks"),
            ("thirdparty.yaml", "thirdparty"),
        ]:
            path = os.path.join(LIBRARY_DIR, fname)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            for it in (raw.get(root_key) or []):
                item_id = str(it.get("id", ""))
                self.data[item_id] = it
                name = str(it.get("name", "")).strip()
                if name:
                    self._name_index[name.lower()] = item_id

    def get(self, item_id):
        return self.data.get(str(item_id))

    def find_by_name(self, name):
        if not name:
            return None
        nl = name.lower().strip()
        if nl in self._name_index:
            return self.data[self._name_index[nl]]
        cands = []
        for lib_name, iid in self._name_index.items():
            if nl in lib_name or lib_name in nl:
                cands.append((len(lib_name), iid))
        if cands:
            cands.sort()
            return self.data[cands[0][1]]
        best_dist, best_id = 999, None
        for lib_name, iid in self._name_index.items():
            d = _levenshtein(nl, lib_name)
            if d < best_dist and d <= min(2, len(nl) // 3):
                best_dist = d
                best_id = iid
        return self.data.get(best_id) if best_id else None

    def search(self, keyword, top_n=10):
        if not keyword:
            return []
        kw = keyword.lower().strip()
        scored = []
        for iid, it in self.data.items():
            name = str(it.get("name", "")).lower()
            desc = str(it.get("description", "")).lower()
            score = 0.0
            if kw in name:
                score += 5.0
            elif name in kw:
                score += 4.0
            score += sum(1 for c in kw if c in name) / max(len(kw), 1) * 3.0
            if kw in desc:
                score += 2.0
            score += sum(1 for c in kw if c in desc) / max(len(kw), 1)
            if score > 1.0:
                scored.append((score, iid, it))
        scored.sort(reverse=True)
        return [{"id": sid, "name": s.get("name", ""), "group": s.get("group", ""),
                 "unit_price": s.get("unit_price"),
                 "description": str(s.get("description", ""))[:80]}
                for score, sid, s in scored[:top_n]]


def _levenshtein(s1, s2):
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


# ============================================================
# QuoteBuilder — 从 spec 构建 QuoteData
# ============================================================

SECTION_DEFAULTS = {
    "modules": {
        "title": "一、软件模块报价",
        "headers": ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
        "col_keys": ["index", "name", "description", "unit_price", "discount", "quantity", "amount"],
        "total_label": "软件模块费用合计（RMB）",
        "library_type": "modules",
    },
    "implementation": {
        "title": "二、实施服务报价",
        "headers": ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
        "col_keys": ["index", "name", "description", "unit_price", "discount", "quantity", "amount"],
        "total_label": "实施服务费用合计（RMB）",
        "library_type": "services",
    },
    "user_license": {
        "title": "三、用户许可报价",
        "headers": ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
        "col_keys": ["index", "name", "description", "unit_price", "discount", "quantity", "amount"],
        "total_label": "用户许可费用合计（RMB）",
        "library_type": "licenses",
    },
    "thirdparty": {
        "title": "四、第三方产品报价",
        "headers": ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
        "col_keys": ["index", "name", "description", "unit_price", "discount", "quantity", "amount"],
        "total_label": "第三方产品费用合计（RMB）",
        "library_type": "thirdparty",
    },
}


class QuoteBuilder:
    """从 spec.yml 构建 QuoteData"""
    def __init__(self, library=None):
        self.library = library or Library()

    def build(self, spec_path):
        spec = _load_yaml(spec_path)
        quote = spec.get("quote", spec)

        qd = QuoteData()

        # 元数据
        qd.metadata = {
            "client": quote.get("client", ""),
            "contact": quote.get("contact", ""),
            "date": quote.get("date", ""),
            "quote_number": quote.get("quote_number", ""),
            "version": quote.get("version", ""),
            "valid_until": quote.get("valid_until", ""),
            "payment_terms": quote.get("payment_terms", ""),
            # P2：支持自定义 title，避免 HTML 标题硬编码
            "title": quote.get("title", ""),
        }

        global_discount = quote.get("global_discount", 1.0)

        # 遍历 sections
        for sheet_ref in quote.get("sheets", []):
            for sec_spec in sheet_ref.get("sections", []):
                sec_id = sec_spec.get("id", "")
                defaults = SECTION_DEFAULTS.get(sec_id, {
                    "title": sec_id,
                    "headers": ["编号", "名称", "描述", "单价", "折扣", "数量", "金额"],
                    "col_keys": ["index", "name", "description", "unit_price", "discount", "quantity", "amount"],
                    "total_label": f"{sec_id}费用合计（RMB）",
                    "library_type": "modules",
                })

                section = Section(
                    title=sec_spec.get("title", defaults["title"]),
                    headers=defaults["headers"],
                    section_id=sec_id,
                    sheet_ref=sheet_ref.get("ref", ""),
                )
                section.col_keys = defaults["col_keys"]
                section.total_label = sec_spec.get("total_label", defaults["total_label"])

                lib_type = defaults.get("library_type", "modules")

                for i, item_spec in enumerate(sec_spec.get("items", [])):
                    item = self._resolve_item(item_spec, i + 1, global_discount, lib_type)
                    section.items.append(item)

                section.total_amount = section.total_amount_computed
                qd.sections.append(section)

        # 汇总
        qd.summary = [(s.title, s.total_amount) for s in qd.sections]
        qd.summary_total = qd.total_amount()

        # 付款方式
        total = qd.summary_total
        for p_spec in quote.get("payment", []):
            ratio_str = p_spec.get("ratio", "0%")
            # 接受 "30%" / 0.3 / 30（>1 的数按百分比理解）；解析失败按 0 并警告，不崩
            try:
                if isinstance(ratio_str, str) and ratio_str.strip().endswith("%"):
                    ratio = float(ratio_str.strip()[:-1]) / 100.0
                else:
                    v = float(ratio_str)
                    ratio = v / 100.0 if v > 1 else v
            except (TypeError, ValueError):
                print(f"[警告] 付款比例无法解析: {ratio_str!r}，按 0 处理")
                ratio = 0
            qd.payments.append({
                "time": p_spec.get("time", ""),
                "type": p_spec.get("type", ""),
                "ratio": ratio_str,
                "amount": round(total * ratio, 2),
            })

        return qd

    def _resolve_item(self, item_spec, index, global_discount, lib_type):
        """从 spec item + 库 → Item"""
        # 从库取（当 spec 指定了 role 时跳过库匹配，避免名称被库覆盖）
        has_role = bool(item_spec.get("role"))
        lib = self.library.get(item_spec.get("id"))
        if not lib and item_spec.get("name") and not has_role:
            lib = self.library.find_by_name(item_spec.get("name"))
        lib = lib or {}

        name = item_spec.get("name") or lib.get("name", "")
        desc = item_spec.get("description") or lib.get("description", "")

        # 价格解析（P0-6：条件定价许可 pricing_mode=conditional 时选择 register/concurrent）
        price = item_spec.get("unit_price")
        if price is None or price == "":
            pricing_mode = lib.get("pricing_mode", "fixed")
            if pricing_mode == "conditional":
                # spec 可指定 pricing_mode: register|concurrent，默认 register
                spec_mode = item_spec.get("pricing_mode", "register")
                if spec_mode == "concurrent":
                    price = lib.get("price_concurrent", 0)
                else:
                    price = lib.get("price_register", 0)
                if not price:
                    print(f"[警告] 许可 {item_spec.get('id', name)} 为条件定价但未取到价格(register={lib.get('price_register')}, concurrent={lib.get('price_concurrent')})")
            else:
                price = lib.get("unit_price", 0)
        if price == "":
            price = 0
        price = float(price) if price else 0

        discount_raw = item_spec.get("discount", global_discount)
        qty = item_spec.get("quantity", 1)
        qty = int(qty) if qty else 1

        numeric_disc, is_gift, display = normalize_discount(discount_raw, global_discount)

        if is_gift:
            amount = 0.0
        else:
            amount = round(price * numeric_disc * qty, 2)

        role = item_spec.get("role", "")

        return Item(
            index=index, name=name, description=desc,
            unit_price=price, discount=numeric_disc,
            discount_display=display, quantity=qty,
            amount=amount, is_gift=is_gift, role=role,
        )


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_slots(template_name):
    """加载模板的 slots.yml"""
    tpl_dir = os.path.join(TEMPLATE_DIR, template_name)
    slots_path = os.path.join(tpl_dir, "slots.yml")
    return _load_yaml(slots_path)


def get_template_source(template_name):
    """获取模板 source.xlsx 路径"""
    return os.path.join(TEMPLATE_DIR, template_name, "source.xlsx")
