---
name: table-area-site
description: 產出「可建量試算」。基地面積、容積率、建蔽率、獎勵與容移，算出允建容積、地上與地下樓地板面積、銷坪、戶數、車位。前期看地、合建分配、投報試算前使用。觸發詞：可建量、可以蓋多少、銷坪、容積試算、開發分析。
---

# 可建量試算

照 `table-area` 技能的流程做（蒐集資料 → check → build → 交付），只是 build 時指定這張表：

```
python <table-area 技能資料夾>/scripts/tingarea.py build 案件.json --out 案名-可建量試算.xlsx --tables site
```

`table-area` 技能資料夾和本技能資料夾放在同一層（`../table-area/`）。check 顯示這張表做不出來時，把缺的資料問清楚再做。
