# 工作包 C：营养分析与预警链路 — 交付说明

## 1. 模块与文件

| 文件 | 职责 |
|---|---|
| `nutrition/db.py` | C1 营养查询：按 `food_id` 整数精确查询；整名精确匹配辅助入口 |
| `nutrition/calculator.py` | C2 营养计算：单项/整餐，per-100g × 重量折算 |
| `nutrition/advisor.py` | C3 推荐（PRD 表 4-1）+ 预警规则 AL-01~AL-05（PRD 表 4-2） |
| `prompts/llm_advice_prompt.md` | C3 大模型建议提示词（仅解释性，数值全部来自计算结果） |
| `tests/test_nutrition.py` | 单元测试 38 项（全部通过） |
| `scripts/run_example.py` | 全链路运行示例（固定输入可复现） |
| `data/nutrition_clean.csv` | 营养数据源（351 条） |
| `data/reference_portions.csv` | 10 类试点菜品份量参考基准（仅参考值） |
| `reports/wp_c_example_output.json` | 示例运行输出 |

运行方式：
```bash
python -m unittest tests.test_nutrition -v   # 38 tests OK
python scripts/run_example.py
```

## 2. 输入/输出数据结构

### 2.1 整餐计算输入
```json
[{"food_id": 0, "weight_g": 200, "weight_source": "user_input"},
 {"food_id": 83, "weight_source": "portion_reference", "portions": 1.0},
 {"food_id": 74, "weight_g": 250, "weight_source": "model_estimate"}]
```

### 2.2 整餐计算输出
```json
{"items": [{"food_id":0,"food_name":"米饭","weight_g":200.0,"weight_source":"user_input",
            "carb_g":51.8,"fat_g":0.6,"protein_g":5.2,"fiber_g":0.6,"energy_kcal":232.0,
            "per_100g":{"carb_g":25.9,"fat_g":0.3,"protein_g":2.6,"fiber_g":0.3,"energy_kcal":116.0},
            "status":"ok","warnings":[]}],
 "totals":{"carb_g":59.25,"fat_g":84.01,"protein_g":19.01,"fiber_g":2.32,"energy_kcal":711.44},
 "status":"ok",
 "warnings":["[红烧肉] 重量按份量参考 1份=150.0g × 1.0 折算，非称重值",
             "[冬瓜汤] 重量为模型估算值，非称重实测，存在份量误差"]}
```
**重量来源三态（不得混用表述）**：`user_input`=用户输入/确认；`portion_reference`=份量参考折算；`model_estimate`=模型估算（明确标注非称重）。

### 2.3 预警输出
```json
{"code":"AL-04","name":"碳水超标","severity":"high",
 "message":"今日碳水已达目标的 126%，建议减少主食份额",
 "basis":"goal=control_sugar 且 289.25 > 229.3×1.1",
 "record_date":"2026-10-23","trigger_time":"21:15"}
```

## 3. 异常处理矩阵

| 场景 | 处理 | 抛出/提示 |
|---|---|---|
| food_id 非整数（如字符串"83"） | 拒绝 | `TypeError`（杜绝字符串模糊匹配） |
| food_id 未收录（<0 或 >350） | 拒绝 | `FoodNotFoundError` |
| 名称模糊匹配 | 不支持 | `lookup_by_exact_name` 仅整名精确；未收录抛 `FoodNotFoundError` |
| 同名异物（整名重复） | 拒绝并要求用 ID | `NutritionDataError` |
| weight 缺失/NaN | 拒绝 | `NutritionItemError` |
| weight ≤ 0（负数/零） | 拒绝 | `NutritionItemError` |
| weight > 5000g（疑似单位错误） | 拒绝 | `NutritionItemError` |
| weight_source 非法 | 拒绝 | `NutritionItemError` |
| model_estimate 来源 | 放行但打标 | warnings 中注明"非称重实测" |
| 核心营养素缺失（partial） | 部分计算 | status=partial + warnings 列出缺失字段 |
| 整餐 entries 为空 | 拒绝 | `NutritionItemError` |
| BMR 输入越界（身高/体重/年龄/性别） | 拒绝 | `ValueError`（PRD 4.3 范围校验） |
| BMI<18.5 或 >30 | 放行 + 提示 | notes 提示咨询营养师/医生 |

## 4. 预警规则配置（全部来自 PRD，无自造阈值）

| 规则 | 条件 | 阈值来源 | 单测 |
|---|---|---|---|
| AL-01 热量超标 | 当日热量 > 目标×110% | PRD 表 4-1/4-2 | ✅ test_al01_over |
| AL-02 热量不足 | 当日热量 < 目标×70% 且 ≥20:00 | 同上 | ✅ test_al02_under_late / _before_20 |
| AL-03 蛋白不足 | 当日蛋白 < 目标×70% 且 ≥20:00 | 同上 | ✅ test_al03_protein |
| AL-04 碳水超标 | 仅控糖目标：碳水 > 目标×110% | 同上 | ✅ test_al04_only_control_sugar |
| AL-05 单餐占比 | 单餐热量 > 日目标×50%（提示） | 同上 | ✅ test_al05_single_meal |
| 频控去重 | 同一 (规则编号, record_date) 至多 1 条 | PRD 4.9.1 | ✅ test_dedup_same_day |
| 卡片截断 | 按严重度排序取前 2 | PRD 4.9 | ✅ test_max_two_and_severity_order |
| 推荐摄入 | Mifflin-St Jeor + 活动系数 + 供能比 | PRD 表 4-1 | ✅ test_bmr_male/_female/_tdee_and_macros 等 |

大模型角色：**只做解释性表达**（提示词含 6 条硬约束 + 反例），禁止自行计算数值或引入输入之外的阈值。

## 5. 已知局限性

1. **营养数据源口径单一**：全部来自 density.xlsx（Aqua-Calc / Mint Health），未与 USDA FDC 交叉校验（USDA 为英文食材级、口径不同，未在本期对齐）。
2. **能量非 Atwater 重算**：33 条记录能量与四大营养素推算偏差 >20%，保留实测原值。
3. **份量参考值为经验值**：`reference_portions.csv` 标注 `reference_only`，仅覆盖 10 类试点菜品，需人工校准后才能用于验收口径 MI-02。
4. **份量估算误差**：模型估算重量非称重，热量偏差受"识别 × 重量 × 成分表"三层误差叠加，PRD 已声明该固有误差（任务书 6.3）。
5. **预警不做跨日/补算**：仅在记录落库后判定一次，无定时任务（与 PRD 4.9.1 一致）；修改历史记录后的预警重算属于 WebApp 层职责，本期未覆盖。
6. **未做控糖以外目标的碳水预警**：AL-04 仅在 control_sugar 目标生效（与 PRD 一致）。
