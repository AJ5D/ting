# Ting 面積與容積檢討表

在 Claude 裡打 `/table-area`，把基地與樓層資料整理成 Excel 檢討表。表格裡寫的是公式，打開就能看到每一格怎麼算出來的。

| 表 | 內容 |
|---|---|
| 可建量試算 | 允建容積、地上與地下樓地板面積、屋突、銷坪（公設比法與係數法）、戶數、車位 |
| 建蔽率檢討 | 法定與設計建築面積比較 |
| 各層容積檢討 | 每層陽台 1/8、梯廳 10%、合計 15% 上限，(A)−(B)+(C) |
| 各層樓地板面積總表 | 各層彙總，與允建容積比較 |

## 安裝

在 Claude Code 或 Claude 桌面版：

```
/plugin marketplace add AJ5D/ting
/plugin install ting-area@ting
```

裝好後打 `/table-area`，或直接說「林口那塊 747.78㎡，二住，容積 150%，容移 20%，可以蓋多少？」。

## 規則檔

`plugins/ting-area/skills/table-area/rules/`

- `national.json`：建築技術規則（陽台、梯廳、屋突上限），每條附法源
- `newtaipei.json`、`taipei.json`、`taoyuan.json`：縣市差異（目前只有新北的開挖率級距）
- `assumptions.json`：前期估算經驗值（公設比、銷坪係數、梯廳與陽台估算比例等），可在案件檔覆寫

標記「待建築師核對」的參數尚未經建築師確認。送審數字以建築師簽證圖說為準。

## 不用 Claude 也能跑

```
python plugins/ting-area/skills/table-area/scripts/tingarea.py check plugins/ting-area/skills/table-area/examples/sample-case.json
python plugins/ting-area/skills/table-area/scripts/tingarea.py build plugins/ting-area/skills/table-area/examples/sample-case.json --out 範例.xlsx
```

## 測試

```
python tests/test_tingarea.py
```

會用 LibreOffice 重算產出的 Excel，確認每一格公式的結果都跟引擎一致。

## 個案資料

這個 repo 是公開的。案件檔和產出的 Excel 不要提交（`.gitignore` 已排除 `cases/` 與 `*.xlsx`）。
