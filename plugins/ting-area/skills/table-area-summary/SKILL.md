---
name: table-area-summary
description: 產出「各層樓地板面積總表」。全案一張，彙總各層面積、免計與容積，和允建容積比較。觸發詞：面積總表、樓地板面積總表。
---

# 各層樓地板面積總表

照 `table-area` 技能的流程做（蒐集資料 → check → build → 交付），只是 build 時指定這張表：

```
python <table-area 技能資料夾>/scripts/tingarea.py build 案件.json --out 案名-各層樓地板面積總表.xlsx --tables summary
```

`table-area` 技能資料夾和本技能資料夾放在同一層（`../table-area/`）。check 顯示這張表做不出來時，把缺的資料問清楚再做。
