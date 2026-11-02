---
name: table-area
description: 「面積與容積檢討表」的入口（hub）。使用者想做可建量試算、容積檢討、建蔽率檢討、各層容積檢討、樓地板面積總表，或問「這塊地可以蓋多少」「容積算一下」「銷坪多少」「這些表可以做哪些」時使用；即使沒說 skill 也要用。可帶關鍵字直接指定：可建量 / site、建蔽 / coverage、各層容積 / per-floor、總表 / summary。適用臺北市、新北市、桃園市。
---

# 面積與容積檢討表（入口）

本技能把使用者給的基地與樓層資料整理成「案件檔」（JSON），交給 `scripts/tingarea.py` 計算並產出 Excel。
所有數字都由引擎算出，不要自己心算或改數字；引擎寫進 Excel 的是公式，打開就能追。

引擎路徑：本技能資料夾下的 `scripts/tingarea.py`（規則檔在 `rules/`，範例在 `examples/sample-case.json`）。

## 流程

1. **蒐集資料，寫成案件檔。** 從對話、上傳的 Excel/PDF/面積表擷取，缺的才問。案件檔存在使用者的工作資料夾，不要存進外掛資料夾。
   格式見 `examples/sample-case.json`：
   - `city`：`taipei` / `newtaipei` / `taoyuan`
   - `site`：`area_m2`、`reserved_m2`、`arcade_m2`、`zone`、`coverage_ratio`、`far`（都用小數，150% 寫 1.5）
   - `bonuses`：每項 `{name, ratio}`，ratio 是基準容積的比例（容移 20% 寫 0.2）
   - `basement.floors`、`basement.excavation_ratio`（臺北、桃園尚無開挖率規則，必須給）、`rooftop.floors`
   - `building_area_m2`：設計建築面積（做建蔽率檢討才需要）
   - `floors`：地上各層 `{name, floor_area_m2（不含陽台）, balcony_m2, lobby_m2, other_exempt_m2}`
   - `assumptions`：要覆寫的經驗值，例如 `{"public_ratio": 0.32}`；可用的鍵見 `rules/assumptions.json`
   使用者給坪數時，先換成㎡（坪 ÷ 0.3025）。

2. **先檢查能做哪些表**，把結果用表格回報給使用者（表名、內容、負責技能）：
   ```
   python <本技能資料夾>/scripts/tingarea.py check 案件.json
   ```

3. **產出。** 使用者沒指定就做全部可做的表：
   ```
   python <本技能資料夾>/scripts/tingarea.py build 案件.json --out 案名-面積檢討.xlsx [--tables site,coverage,per-floor-volume,summary]
   ```
   需要 `openpyxl`；沒有就先 `pip install openpyxl`。

4. **交付。**
   - 若有 Google Drive 連接器，把 xlsx 上傳並轉成 Google 試算表，回報連結；沒有就給本機檔案路徑。
   - 摘要回報關鍵數字：允建容積、地上與地下樓地板面積、銷坪（公設比法與係數法兩個都列）、戶數、車位、各層是否有回計。
   - 一定要提醒：「參數」頁中標記「待建築師核對」的法規參數尚未經建築師確認；經驗值（公設比、銷坪係數等）是前期估算用，送審數字以建築師簽證圖說為準。

## 各張表

| 表 | 鍵 | 需要的資料 | 子技能 |
|---|---|---|---|
| 可建量試算 | `site` | 基地面積、容積率、建蔽率 | table-area-site |
| 建蔽率檢討 | `coverage` | ＋設計建築面積 | table-area-coverage |
| 各層容積檢討 | `per-floor-volume` | ＋各層面積 | table-area-per-floor-volume |
| 各層樓地板面積總表 | `summary` | ＋各層面積 | table-area-summary |

## 注意

- 法規或經驗值要調整時改 `rules/*.json`，不要在產出的 Excel 裡改公式。
- 產出的檔案與案件檔含個案資料，不要放進外掛的 Git repo。
