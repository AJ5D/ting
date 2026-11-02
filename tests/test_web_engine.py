"""網頁引擎（web/engine.js）與 Python 引擎逐格比對。需要 node。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/ting-area/skills/table-area"
sys.path.insert(0, str(SKILL / "scripts"))
import tingarea  # noqa: E402

SAMPLE = json.loads((SKILL / "examples/sample-case.json").read_text(encoding="utf-8"))
CASES = [
    SAMPLE,
    dict(SAMPLE, bonuses=[]),
    dict(SAMPLE, bonuses=[{"name": "都更獎勵", "ratio": 0.3}, {"name": "容積移轉", "ratio": 0.2}],
         assumptions={"public_ratio": 0.3, "sales_factor": 1.55}),
    dict(SAMPLE, city="taipei", basement={"floors": 4, "excavation_ratio": 0.7}),
    dict(SAMPLE, city="taoyuan", basement={"floors": 3}),  # 沒有開挖率 → 可建量做不出來
    dict({k: v for k, v in SAMPLE.items() if k != "site"}, parcels=[
        {"land_no": "甲段1地號", "area_m2": 500, "zone": "住二", "coverage_ratio": 0.5, "far": 1.5},
        {"land_no": "甲段2地號", "area_m2": 312.5, "zone": "商二", "coverage_ratio": 0.7, "far": 3.0}]),
    dict(SAMPLE, parcels=[{"land_no": "乙段3地號", "area_m2": 400, "coverage_ratio": 0.5}]),  # 缺容積率
]

NODE_SCRIPT = r"""
const fs = require('fs'), path = require('path');
const E = require(process.argv[1]);
const dir = process.argv[2];
const RULES = {};
for (const n of ['national','newtaipei','taipei','taoyuan','assumptions','formulas'])
  RULES[n] = JSON.parse(fs.readFileSync(path.join(dir, n + '.json'), 'utf8'));
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(c => {
  const r = E.compute(RULES, c);
  const vals = {};
  for (const k of Object.keys(r.model.defs)) {
    try { vals[k] = r.model.value(k); } catch (e) { vals[k] = 'ERR'; }
  }
  return {status: r.status, values: vals};
});
process.stdout.write(JSON.stringify(out));
"""


def test_js_matches_python():
    node = shutil.which("node")
    if not node:
        print("skip: 沒有 node")
        return
    res = subprocess.run([node, "-e", NODE_SCRIPT, str(ROOT / "web/engine.js"), str(SKILL / "rules")],
                         input=json.dumps(CASES, ensure_ascii=False), capture_output=True,
                         text=True, check=True)
    js = json.loads(res.stdout)
    for case, got in zip(CASES, js):
        py_status = [[t, ok] for t, ok, _ in tingarea.check(case)]
        assert [s[:2] for s in got["status"]] == py_status, (case.get("city"), got["status"], py_status)
        tables = [t for t, ok in py_status if ok]
        if not tables:
            continue
        m, _, _ = tingarea.compute(case, tables)
        compared = 0
        for key in m.defs:
            try:
                want = m.value(key)
            except (TypeError, KeyError):  # 依賴缺資料或未產生的格子，該案本來就不會用到
                continue
            have = got["values"].get(key)
            if want is None:  # 缺資料的欄位，兩邊都應該是空的
                assert have is None, (key, have)
            elif isinstance(want, str):
                assert have == want, (key, have, want)
            else:
                assert have is not None and abs(have - want) <= 1e-9 * max(1, abs(want)), (key, have, want)
            compared += 1
        assert compared > 30




def test_built_page_is_current():
    """改了規則或網頁原始檔，要重跑 python web/build.py。"""
    sys.path.insert(0, str(ROOT / "web"))
    import build
    assert (ROOT / "docs/index.html").read_text(encoding="utf-8") == build.render("pages"), \
        "docs/index.html 過期，請執行 python web/build.py"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
