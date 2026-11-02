"""把 app.html、engine.js 與規則檔組成單一 HTML。

  python web/build.py                 → docs/index.html（GitHub Pages）
  python web/build.py --artifact OUT  → 給 claude.ai Artifact 用的版本（不含下載按鈕）

規則檔直接內嵌，所以網頁不用連網也能算；改了 rules/*.json 之後要重跑本腳本。
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SKILL = ROOT / "plugins/ting-area/skills/table-area"
RULE_FILES = ["national", "newtaipei", "taipei", "taoyuan", "assumptions", "formulas"]


def render(target):
    rules = {n: json.loads((SKILL / "rules" / f"{n}.json").read_text(encoding="utf-8")) for n in RULE_FILES}
    sample = json.loads((SKILL / "examples/sample-case.json").read_text(encoding="utf-8"))
    html = (WEB / "app.html").read_text(encoding="utf-8")
    dump = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    html = (html.replace("__RULES__", dump(rules))
                .replace("__SAMPLE__", dump(sample))
                .replace("__ENGINE__", (WEB / "engine.js").read_text(encoding="utf-8"))
                .replace("__TARGET__", target))
    if target == "pages":
        html = ('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '<style>body{margin:0}[hidden]{display:none!important}</style>\n'
                + html.replace("<body ", "</head>\n<body ", 1) + "\n</html>\n")
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact")
    a = ap.parse_args()
    if a.artifact:
        Path(a.artifact).write_text(render("artifact"), encoding="utf-8")
        print("wrote", a.artifact)
    else:
        out = ROOT / "docs/index.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render("pages"), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
