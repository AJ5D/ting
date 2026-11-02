---
name: table-area-per-floor-volume
description: 產出「各層容積檢討」。每層一張，陽台 1/8、梯廳 10%、合計 15% 上限檢討，(A)−(B)+(C) 算出各層容積樓地板面積。觸發詞：各層容積、陽台梯廳檢討、回計。
---

# 各層容積檢討

照 `table-area` 技能的流程做（蒐集資料 → check → build → 交付），只是 build 時指定這張表：

```
python <table-area 技能資料夾>/scripts/tingarea.py build 案件.json --out 案名-各層容積檢討.xlsx --tables per-floor-volume
```

`table-area` 技能資料夾和本技能資料夾放在同一層（`../table-area/`）。check 顯示這張表做不出來時，把缺的資料問清楚再做。
