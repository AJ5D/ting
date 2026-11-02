---
name: table-area-coverage
description: 產出「建蔽率檢討」。法定建築面積與設計建築面積比較。觸發詞：建蔽率、建築面積檢討。
---

# 建蔽率檢討

照 `table-area` 技能的流程做（蒐集資料 → check → build → 交付），只是 build 時指定這張表：

```
python <table-area 技能資料夾>/scripts/tingarea.py build 案件.json --out 案名-建蔽率檢討.xlsx --tables coverage
```

`table-area` 技能資料夾和本技能資料夾放在同一層（`../table-area/`）。check 顯示這張表做不出來時，把缺的資料問清楚再做。
