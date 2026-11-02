#!/usr/bin/env python3
"""面積與容積檢討表引擎。

每一格只定義一次算式（{key} 指向參數或其他格），同一個算式
同時用來在 Python 算出數值、以及寫成 Excel 公式，兩邊不會各算各的。

用法：
  python tingarea.py check  case.json
  python tingarea.py build  case.json --out 結果.xlsx [--tables site,coverage,per-floor-volume,summary]
  python tingarea.py show   case.json [--tables ...]      # 只印數值，不產檔
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES_DIR = HERE.parent / "rules"
PING = 0.3025
CITIES = {"taipei": "臺北市", "newtaipei": "新北市", "taoyuan": "桃園市"}
TABLES = {
    "site": "可建量試算",
    "coverage": "建蔽率檢討",
    "per-floor-volume": "各層容積檢討",
    "summary": "各層樓地板面積總表",
}


# ---------- 規則與參數 ----------

def load_rules(city):
    """全國 → 縣市 → 經驗值，後者覆寫前者。回傳 {key: {value,label,source,status}}。"""
    out = {}
    files = ["national.json"]
    if city:
        if city not in CITIES:
            raise SystemExit(f"不支援的縣市 {city}，可用：{', '.join(CITIES)}")
        files.append(f"{city}.json")
    files.append("assumptions.json")
    for name in files:
        data = json.loads((RULES_DIR / name).read_text(encoding="utf-8"))
        for k, v in data.get("params", {}).items():
            v = dict(v)
            v.setdefault("source", data["name"])
            out[k] = v
    return out


def excavation_formula(tiers):
    """級距開挖率 → 算式，例如 (MIN({usable},500)*0.7+MAX({usable}-500,0)*0.6)/{usable}"""
    parts, lower = [], 0
    for t in tiers:
        upto, r = t["upto"], t["ratio"]
        if upto is None:
            parts.append(f"MAX({{usable}}-{lower},0)*{r}")
        else:
            parts.append(f"MAX(MIN({{usable}},{upto})-{lower},0)*{r}")
            lower = upto
    return "(" + "+".join(parts) + ")/{usable}"


# ---------- 算式模型 ----------

class Model:
    """key → 算式或常數。Python 取值與 Excel 公式都從這裡來。"""

    def __init__(self):
        self.defs = {}      # key -> ("const", value) | ("expr", str)
        self.addr = {}      # key -> "'工作表'!$C$5"
        self._cache = {}

    def const(self, key, value):
        self.defs[key] = ("const", value)

    def expr(self, key, text):
        self.defs[key] = ("expr", text)

    def value(self, key):
        if key in self._cache:
            return self._cache[key]
        kind, v = self.defs[key]
        if kind == "const":
            val = v
        else:
            py = re.sub(r"\{(\w+)\}", lambda m: repr(self.value(m.group(1))), v)
            val = eval(py, {"__builtins__": {}}, _FUNCS)
        self._cache[key] = val
        return val

    def excel(self, key):
        kind, v = self.defs[key]
        if kind == "const":
            return v
        return "=" + re.sub(r"\{(\w+)\}", lambda m: self.addr[m.group(1)], v)


def _round(x, n=0):
    q = 10 ** n
    v = math.floor(abs(x) * q + 0.5) / q * (1 if x >= 0 else -1)
    return int(v) if n == 0 else v


_FUNCS = {
    "MIN": min,
    "MAX": max,
    "ROUND": _round,
    "INT": math.floor,
    "IF": lambda c, a, b: a if c else b,
}


def build_model(case):
    rules = load_rules(case.get("city"))
    for k, v in (case.get("assumptions") or {}).items():
        if k not in rules:
            raise SystemExit(f"assumptions 裡的 {k} 不是已知參數")
        rules[k] = dict(rules[k], value=v, source="案件檔覆寫", status=None)

    m = Model()
    site = case["site"]
    inputs = [  # (key, label, value, unit)
        ("site_area", "基地面積（謄本）", site["area_m2"], "㎡"),
        ("reserved", "法定保留地", site.get("reserved_m2", 0), "㎡"),
        ("arcade", "騎樓面積", site.get("arcade_m2", 0), "㎡"),
        ("coverage", "建蔽率", site["coverage_ratio"], ""),
        ("far", "容積率", site["far"], ""),
        ("basement_floors", "地下開挖層數", case.get("basement", {}).get("floors", 0), "層"),
        ("rooftop_floors", "屋突層數", case.get("rooftop", {}).get("floors", 0), "層"),
    ]
    params = []
    for key, label, val, unit in inputs:
        m.const(key, val)
        params.append((key, label, unit, "案件輸入", None))
    bonuses = case.get("bonuses") or []
    for i, b in enumerate(bonuses):
        m.const(f"bonus_ratio_{i}", b["ratio"])
        params.append((f"bonus_ratio_{i}", f"{b['name']}（基準容積比例）", "", "案件輸入", None))

    for k, r in rules.items():
        if k == "excavation_tiers":
            continue
        m.const(k, r["value"])
        params.append((k, r["label"], "", r.get("source", ""), r.get("status")))

    excav = case.get("basement", {}).get("excavation_ratio")
    if excav is not None:
        m.const("excav_ratio", excav)
        params.append(("excav_ratio", "地下開挖率", "", "案件輸入", None))
    elif "excavation_tiers" in rules:
        r = rules["excavation_tiers"]
        m.expr("excav_ratio", excavation_formula(r["value"]))
        params.append(("excav_ratio", r["label"], "", r["source"], r.get("status")))
    else:
        m.const("excav_ratio", 0)  # check() 會擋下需要開挖率的表
    return m, params, bonuses


# ---------- 各張表的版面 ----------
# 算式都在 rules/formulas.json（網頁計算器共用同一份）。
# 每列：(key, 標題, 算式 或 None 表示引用既有 key, 單位, 是否換算坪)

FORMULAS = json.loads((RULES_DIR / "formulas.json").read_text(encoding="utf-8"))
COVERAGE_ROWS = [tuple(r) for r in FORMULAS["coverage"]]
FLOOR_COLS = [tuple(r) for r in FORMULAS["floor"]]  # (後綴, 欄名, 算式)


def site_rows(bonuses):
    rows = [tuple(r) for r in FORMULAS["site_head"]]
    bonus_keys = []
    for i, b in enumerate(bonuses):
        key, _, f, unit, ping = FORMULAS["site_bonus"]
        rows.append((key.replace("@I@", str(i)), b["name"], f.replace("@I@", str(i)), unit, ping))
        bonus_keys.append(rows[-1][0])
    bonus_sum = "+".join("{%s}" % k for k in bonus_keys) or "0"
    for key, label, f, unit, ping in FORMULAS["site_tail"]:
        rows.append((key, label, f.replace("@BONUS_SUM@", bonus_sum), unit, ping))
    return rows


# ---------- 檢查與輸出 ----------

def check(case):
    """回傳 [(table, 可否, 說明)]"""
    floors = case.get("floors") or []
    basement = case.get("basement") or {}
    no_excav = (basement.get("floors", 0) > 0 and basement.get("excavation_ratio") is None
                and "excavation_tiers" not in load_rules(case.get("city")))
    if no_excav:
        out = [("site", False, "這個縣市還沒有開挖率規則，請填 basement.excavation_ratio")]
    else:
        out = [("site", True, "基地面積、容積率、建蔽率齊全")]
    if case.get("building_area_m2") and no_excav:
        out.append(("coverage", False, "可建量試算做不出來"))
    elif case.get("building_area_m2"):
        out.append(("coverage", True, "有設計建築面積"))
    else:
        out.append(("coverage", False, "缺 building_area_m2（設計建築面積）"))
    if floors:
        out.append(("per-floor-volume", True, f"{len(floors)} 層資料，每層一張"))
        out.append(("summary", not no_excav, "全案一張" if not no_excav else "可建量試算做不出來"))
    else:
        out.append(("per-floor-volume", False, "缺 floors（各層面積）"))
        out.append(("summary", False, "缺 floors（各層面積）"))
    return out


def compute(case, tables):
    """回傳 (model, params, layout)。layout 描述每張表的列與欄，供 show/build 使用。"""
    m, params, bonuses = build_model(case)
    layout = {}
    if "site" in tables or "summary" in tables or "coverage" in tables:
        rows = site_rows(bonuses)
        for key, _, f, _, _ in rows:
            m.expr(key, f)
        layout["site"] = rows
    if "coverage" in tables:
        m.const("cov_design", case["building_area_m2"])
        for key, _, f, _, _ in COVERAGE_ROWS:
            if f:
                m.expr(key, f)
        layout["coverage"] = COVERAGE_ROWS
    if "per-floor-volume" in tables or "summary" in tables:
        floors = case["floors"]
        for i, fl in enumerate(floors):
            p = f"f{i}_"
            m.const(p + "a0", fl["floor_area_m2"])
            m.const(p + "bal", fl.get("balcony_m2", 0))
            m.const(p + "lob", fl.get("lobby_m2", 0))
            m.const(p + "oth", fl.get("other_exempt_m2", 0))
            for suf, _, f in FLOOR_COLS:
                if f:
                    m.expr(p + suf, f.replace("{%", "{" + p))
        layout["per-floor-volume"] = floors
    if "summary" in tables:
        n = len(case["floors"])
        for suf in ("a0", "bal", "lob", "oth", "vol"):
            m.expr("sum_" + suf, "+".join("{f%d_%s}" % (i, suf) for i in range(n)))
        m.expr("sum_diff", "{allowed}-{sum_vol}")
        m.expr("sum_result", 'IF({sum_vol}<={allowed},"符合","超過")')
        layout["summary"] = case["floors"]
    return m, params, layout


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def show(case, tables):
    m, _, layout = compute(case, tables)
    lines = []
    if "site" in tables:
        lines.append(f"【{TABLES['site']}】")
        for key, label, _, unit, ping in layout["site"]:
            v = m.value(key)
            extra = f"  ＝ {fmt(v * PING)} 坪" if ping else ""
            lines.append(f"  {label}：{fmt(v)} {unit}{extra}")
    if "coverage" in tables:
        lines.append(f"【{TABLES['coverage']}】")
        for key, label, _, unit, _ in COVERAGE_ROWS:
            lines.append(f"  {label}：{fmt(m.value(key))} {unit}")
    if "per-floor-volume" in tables:
        lines.append(f"【{TABLES['per-floor-volume']}】")
        for i, fl in enumerate(layout["per-floor-volume"]):
            p = f"f{i}_"
            lines.append(f"  {fl['name']}：(A) {fmt(m.value(p+'A'))}  (B) {fmt(m.value(p+'B'))}"
                         f"  (C) {fmt(m.value(p+'C'))}  容積 {fmt(m.value(p+'vol'))} ㎡")
    if "summary" in tables:
        lines.append(f"【{TABLES['summary']}】")
        lines.append(f"  各層容積合計：{fmt(m.value('sum_vol'))} ㎡")
        lines.append(f"  允建容積：{fmt(m.value('allowed'))} ㎡")
        lines.append(f"  餘裕：{fmt(m.value('sum_diff'))} ㎡　判定：{m.value('sum_result')}")
    return "\n".join(lines)


def build_xlsx(case, tables, out):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    m, params, layout = compute(case, tables)
    wb = Workbook()
    deferred = []  # 公式最後才寫，因為算式可能指向後面才排位置的格子

    def put(ws, r, c, key):
        cell = ws.cell(r, c)
        deferred.append((cell, key))
        return cell
    thin = Side(style="thin", color="999999")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head = PatternFill("solid", fgColor="E8E4DA")
    bold = Font(bold=True)
    num = "#,##0.00"

    def title(ws, text):
        ws["A1"] = f"{case.get('name', '')}　{text}"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"縣市：{CITIES.get(case.get('city'), '未指定')}　單位：㎡（坪 = ㎡ × {PING}）"

    def header(ws, row, names):
        for c, n in enumerate(names, 1):
            cell = ws.cell(row, c, n)
            cell.font, cell.fill, cell.border = bold, head, box
            cell.alignment = Alignment(wrap_text=True, vertical="center")

    # 參數頁：先排位置，讓其他頁的公式可以指過來
    ws = wb.active
    ws.title = "參數"
    title(ws, "參數與法源")
    header(ws, 4, ["項目", "數值", "單位", "來源", "狀態"])
    r = 5
    for key, label, unit, source, status in params:
        m.addr[key] = f"'參數'!$B${r}"
        ws.cell(r, 1, label)
        ws.cell(r, 3, unit)
        ws.cell(r, 4, source)
        ws.cell(r, 5, status or "")
        r += 1
    for row, (key, *_rest) in enumerate(params, 5):
        put(ws, row, 2, key)
        for c in range(1, 6):
            ws.cell(row, c).border = box
    for col, w in zip("ABCDE", (40, 14, 6, 48, 14)):
        ws.column_dimensions[col].width = w

    def vertical_sheet(name, rows):
        ws = wb.create_sheet(name)
        title(ws, name)
        header(ws, 4, ["項目", "㎡ / 數值", "單位", "坪"])
        start = 5
        for i, (key, *_rest) in enumerate(rows):
            m.addr.setdefault(key, f"'{name}'!$B${start + i}")  # 已在別頁的就引用過去
        for i, (key, label, _, unit, ping) in enumerate(rows):
            r = start + i
            ws.cell(r, 1, label)
            if m.addr[key] == f"'{name}'!$B${r}":
                put(ws, r, 2, key)
            else:
                ws.cell(r, 2, "=" + m.addr[key])
            ws.cell(r, 3, unit)
            if ping:
                ws.cell(r, 4, f"=B{r}*{PING}")
            for c in range(1, 5):
                ws.cell(r, c).border = box
                if c in (2, 4):
                    ws.cell(r, c).number_format = "0.00%" if c == 2 and not unit else num
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["D"].width = 14

    if "site" in layout and "site" in tables:
        vertical_sheet(TABLES["site"], layout["site"])
    elif "site" in layout:
        # 其他表會引用允建容積等數值，放在隱藏頁
        vertical_sheet(TABLES["site"], layout["site"])
        wb[TABLES["site"]].sheet_state = "hidden"
    if "coverage" in tables:
        name = TABLES["coverage"]
        m.addr["cov_design"] = f"'{name}'!$B$7"
        vertical_sheet(name, COVERAGE_ROWS)

    if "per-floor-volume" in layout:
        name = TABLES["per-floor-volume"]
        ws = wb.create_sheet(name)
        title(ws, name)
        ws["A3"] = "(A)−(B)+(C)：陽台與梯廳超過上限的部分回計容積。上限比例見「參數」頁。"
        header(ws, 4, ["樓層"] + [c[1] for c in FLOOR_COLS])
        floors = layout["per-floor-volume"]
        for i in range(len(floors)):
            for j, (suf, _, _) in enumerate(FLOOR_COLS):
                m.addr[f"f{i}_{suf}"] = f"'{name}'!${get_column_letter(j + 2)}${5 + i}"
        for i, fl in enumerate(floors):
            r = 5 + i
            ws.cell(r, 1, fl["name"]).border = box
            for j, (suf, _, _) in enumerate(FLOOR_COLS):
                cell = put(ws, r, j + 2, f"f{i}_{suf}")
                cell.border, cell.number_format = box, num
        ws.column_dimensions["A"].width = 8
        for j in range(len(FLOOR_COLS)):
            ws.column_dimensions[get_column_letter(j + 2)].width = 14
        ws.row_dimensions[4].height = 48
        if "per-floor-volume" not in tables:
            ws.sheet_state = "hidden"

    if "summary" in tables:
        name = TABLES["summary"]
        ws = wb.create_sheet(name)
        title(ws, name)
        cols = [("a0", "樓地板面積（不含陽台）"), ("bal", "陽台"), ("lob", "梯廳"),
                ("oth", "其他免計"), ("vol", "容積樓地板面積")]
        header(ws, 4, ["樓層"] + [c[1] for c in cols])
        floors = layout["summary"]
        for i, fl in enumerate(floors):
            r = 5 + i
            ws.cell(r, 1, fl["name"]).border = box
            for j, (suf, _) in enumerate(cols):
                cell = ws.cell(r, j + 2, "=" + m.addr[f"f{i}_{suf}"])
                cell.border, cell.number_format = box, num
        r = 5 + len(floors)
        ws.cell(r, 1, "合計").font = bold
        for j, (suf, _) in enumerate(cols):
            m.addr["sum_" + suf] = f"'{name}'!${get_column_letter(j + 2)}${r}"
        for j, (suf, _) in enumerate(cols):
            cell = put(ws, r, j + 2, "sum_" + suf)
            cell.font, cell.border, cell.number_format = bold, box, num
        for k, label, rr in (("allowed", "允建容積樓地板面積", r + 2),
                             ("sum_diff", "餘裕（允建 − 合計）", r + 3),
                             ("sum_result", "判定", r + 4)):
            ws.cell(rr, 1, label)
            if k == "allowed":
                ws.cell(rr, 6, "=" + m.addr["allowed"])
            else:
                m.addr[k] = f"'{name}'!$F${rr}"
                put(ws, rr, 6, k)
            ws.cell(rr, 6).number_format = num
        ws.column_dimensions["A"].width = 20
        for j in range(len(cols)):
            ws.column_dimensions[get_column_letter(j + 2)].width = 16

    for cell, key in deferred:
        cell.value = m.excel(key)
    order = ["參數"] + [TABLES[t] for t in TABLES if TABLES[t] in wb.sheetnames]
    wb._sheets = [wb[n] for n in order]
    wb.active = 0
    wb.save(out)
    return m


def parse_tables(arg, case):
    ok = {t for t, can, _ in check(case) if can}
    if not arg or arg == "all":
        return [t for t in TABLES if t in ok]
    want = [t.strip() for t in arg.split(",") if t.strip()]
    for t in want:
        if t not in TABLES:
            raise SystemExit(f"沒有 {t} 這張表，可用：{', '.join(TABLES)}")
        if t not in ok:
            reason = next(msg for tt, _, msg in check(case) if tt == t)
            raise SystemExit(f"{TABLES[t]} 做不出來：{reason}")
    return want


def main(argv=None):
    ap = argparse.ArgumentParser(description="面積與容積檢討表引擎")
    ap.add_argument("cmd", choices=["check", "show", "build"])
    ap.add_argument("case")
    ap.add_argument("--tables", default="all")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    case = json.loads(Path(a.case).read_text(encoding="utf-8"))

    if a.cmd == "check":
        print(f"案名：{case.get('name', '')}　縣市：{CITIES.get(case.get('city'), '未指定')}")
        for t, can, msg in check(case):
            print(f"  {'✓' if can else '✗'} {TABLES[t]}（{t}）：{msg}")
        rules = load_rules(case.get("city"))
        pending = [r["label"] for r in rules.values() if r.get("status")]
        if pending:
            print(f"  ⚠ {len(pending)} 條法規參數待建築師核對，見產出檔「參數」頁")
        return 0
    tables = parse_tables(a.tables, case)
    if a.cmd == "show":
        print(show(case, tables))
        return 0
    out = a.out or f"{case.get('name', 'case')}-面積檢討.xlsx"
    build_xlsx(case, tables, out)
    print(f"已產出 {out}（{', '.join(TABLES[t] for t in tables)}）")
    print(show(case, tables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
