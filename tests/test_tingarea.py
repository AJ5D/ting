"""引擎測試。執行：python -m pytest tests  或  python tests/test_tingarea.py"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/ting-area/skills/table-area"
sys.path.insert(0, str(SKILL / "scripts"))
import tingarea  # noqa: E402

SAMPLE = json.loads((SKILL / "examples/sample-case.json").read_text(encoding="utf-8"))


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1, abs(b))


def test_site_matches_hand_calc():
    m, _, _ = tingarea.compute(SAMPLE, ["site"])
    v = m.value
    assert approx(v("base_far"), 800 * 1.5)
    assert approx(v("allowed"), 1200 * 1.2)
    assert approx(v("stair_mech"), 1440 * 0.15)
    assert approx(v("above"), (1440 + 216) / 0.94)
    assert approx(v("rooftop"), 400 / 8 * 3)
    # 新北開挖率：前 500㎡ 70%，其餘 60%
    assert approx(v("excav_ratio"), (500 * 0.7 + 300 * 0.6) / 800)
    assert approx(v("sales_m2"), (1440 + v("balcony")) / 0.66)


def test_per_floor_caps():
    case = dict(SAMPLE, floors=[
        {"name": "低於上限", "floor_area_m2": 400, "balcony_m2": 40, "lobby_m2": 10},
        {"name": "陽台超過1/8", "floor_area_m2": 400, "balcony_m2": 60, "lobby_m2": 0},
        {"name": "合計超過15%", "floor_area_m2": 400, "balcony_m2": 50, "lobby_m2": 40},
    ])
    m, _, _ = tingarea.compute(case, ["per-floor-volume"])
    assert approx(m.value("f0_C"), 0)
    assert approx(m.value("f0_vol"), 440 - 50)  # 陽台、梯廳都在上限內，全數免計
    assert approx(m.value("f1_C"), 10)            # 60 − 400/8
    assert approx(m.value("f2_C"), 90 - 60)      # 50+40 − 400×15%
    assert approx(m.value("f2_vol"), 400 + 50 - 90 + 30)


def test_check_reports_missing_inputs():
    case = {k: v for k, v in SAMPLE.items() if k not in ("floors", "building_area_m2")}
    status = {t: ok for t, ok, _ in tingarea.check(case)}
    assert status == {"site": True, "coverage": False, "per-floor-volume": False, "summary": False}


def test_assumption_override():
    case = dict(SAMPLE, assumptions={"public_ratio": 0.3})
    m, _, _ = tingarea.compute(case, ["site"])
    assert approx(m.value("sales_m2"), (m.value("allowed") + m.value("balcony")) / 0.7)


def test_excel_formulas_equal_python():
    """產出的 xlsx 交給 LibreOffice 重算，每一格要跟 Python 算的一樣。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("skip: 沒有 LibreOffice")
        return
    from openpyxl import load_workbook
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "out.xlsx"
        m = tingarea.build_xlsx(SAMPLE, list(tingarea.TABLES), src)
        subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx",
                        "--outdir", str(Path(d) / "re"), str(src)],
                       check=True, capture_output=True, timeout=120)
        wb = load_workbook(Path(d) / "re" / "out.xlsx", data_only=True)
        checked = 0
        for key, addr in m.addr.items():
            sheet, cell = addr.split("!")
            got = wb[sheet.strip("'")][cell.replace("$", "")].value
            want = m.value(key)
            if isinstance(want, str):
                assert got == want, (key, got, want)
            else:
                assert approx(float(got), float(want)), (key, got, want)
            checked += 1
        assert checked > 50


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
