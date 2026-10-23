# 数据字段说明（对接前置文档）V1

面向队友：本文件说明**营养表有哪些字段**以及**识别模型输出什么结构**，并说明**模型训练之后反馈了哪些东西**。  
所有字段名均来自 `food_pipeline` 实际产物（`data/*.csv`、`reports/*.json`、`web/serve.py` 真实响应），不是设计稿。

- 生成时间：2026-10-23
- 代码位置：`D:/workbuddy/kkk/food_pipeline`
- 相关文档：`model_output_contract.md`（模型契约）、`data_quality_report.md`（数据质量）、`eval_report.md`（评测）、`error_analysis.md`（错例）

---

## 0. 一页速览

| 你要什么           | 去哪拿                                                                                |
| -------------- | ---------------------------------------------------------------------------------- |
| 菜品的营养数据（351 类） | `data/nutrition_clean.csv`，主键 `food_id`（0–350）                                     |
| 菜名 / 类别 / 图片数  | `data/class_mapping.csv`                                                           |
| 每道菜的参考份量（克）    | `data/reference_portions.csv`（仅 10 类，reference_only）                               |
| 模型识别出什么菜       | `POST /api/analyze` → `detection.detections[]` / `classification.top5[]`           |
| 算出多少热量、触发什么预警  | 同一响应的 `items[]` / `meal` / `targets` / `alerts[]`                                  |
| 模型训得怎么样        | `models/*/results.csv`、`reports/eval_metrics.json`、`reports/real_image_infer.json` |

**最重要的一条**：模型只输出 `food_id + 置信度 + 框`，**不输出重量**。重量由上层决定（用户填 / 份量参考 / 估算），这是硬约束。

---

## 1. 全局约定

| 约定     | 说明                                                                        |
| ------ | ------------------------------------------------------------------------- |
| 主键     | `food_id`：int，0–350 连续无重复，与 DFoodTJ-Rec 类别 ID 一一对应                        |
| 单位     | 质量统一 **g / 100g**；能量统一 **kcal**；密度 **g/ml**                               |
| 浮点精度   | CSV 里保留原始浮点（如米饭能量写作 `115.99999999999999`）；接口层统一 `round(2)`。**不要做字符串等值比较** |
| 空值     | 缺失一律留空（NaN），**禁止填 0**（任务书约束 R2）                                           |
| 坐标     | `bbox_xyxy` = 原始图像**像素坐标** `[x1,y1,x2,y2]`（左上原点），非归一化                     |
| 编码     | 全部 UTF-8；CSV 首列可能带 BOM，读取请用 `encoding='utf-8-sig'`                        |
| 模型类别索引 | 检测/分类各有自己的 `class_id`（0–9），**不等于** `food_id`；映射见 §2.3                     |

---

## 2. 营养表（已按数据清洗定稿）

### 2.1 `data/nutrition_clean.csv` — 351 行 × 17 列

| #  | 字段                     | 类型    | 单位        | 说明                                                          |
| -- | ---------------------- | ----- | --------- | ----------------------------------------------------------- |
| 1  | `food_id`              | int   | -         | 主键 0–350                                                    |
| 2  | `name_zh`              | str   | -         | 中文标准名（已校验无重复）                                               |
| 3  | `name_en`              | str   | -         | 英文名                                                         |
| 4  | `tier`                 | int   | -         | `1` = 10 类高频试点（模型已覆盖）；`2` = 其余 341 类（模型不覆盖）                 |
| 5  | `density_g_ml`         | float | g/ml      | 食物整体密度，用于体积↔质量换算                                            |
| 6  | `carb_g_per_100g`      | float | g/100g    | 碳水化合物                                                       |
| 7  | `fat_g_per_100g`       | float | g/100g    | 脂肪                                                          |
| 8  | `protein_g_per_100g`   | float | g/100g    | 蛋白质                                                         |
| 9  | `fiber_g_per_100g`     | float | g/100g    | 膳食纤维                                                        |
| 10 | `energy_kcal_per_100g` | float | kcal/100g | 能量                                                          |
| 11 | `carb_g_per_ml`        | float | g/ml      | 碳水**体积**密度（仅体积估重路径用）                                        |
| 12 | `fat_g_per_ml`         | float | g/ml      | 脂肪体积密度                                                      |
| 13 | `protein_g_per_ml`     | float | g/ml      | 蛋白质体积密度                                                     |
| 14 | `fiber_g_per_ml`       | float | g/ml      | 纤维体积密度                                                      |
| 15 | `energy_kcal_per_ml`   | float | kcal/ml   | 能量体积密度                                                      |
| 16 | `data_status`          | str   | -         | `complete` = 四项核心营养素齐全（当前 351 条全部 complete）；`partial` = 有缺失 |
| 17 | `source`               | str   | -         | 固定值 `DFoodTJ-Nutr/density.xlsx (Aqua-Calc; Mint Health)`    |

示例（`food_id=0`）：

```csv
0,米饭,Rice,1,0.73,25.9,0.3,2.6,0.3,115.99999999999999,0.1891,0.00219,0.01898,0.00219,0.8468,complete,DFoodTJ-Nutr/density.xlsx (Aqua-Calc; Mint Health)
```

### 2.2 单位换算规则（**最容易踩的坑**）

源表 `density.xlsx` 的"质量密度"是 **g/g（每 1 g 食物的含量）**，清洗时统一 **×100** 变成"每 100 g"：

| 规则 | 内容                                                                                                  |
| -- | --------------------------------------------------------------------------------------------------- |
| R1 | `carb/fat/protein/fiber_g_per_100g` = 源表 g/g **× 100**；`energy_kcal_per_100g` = 源表 kcal/g **× 100** |
| R2 | 缺失留空（NaN），不填 0                                                                                      |
| R3 | 口径为**成品熟菜**（如"红烧肉"是做好后的成品），不做生熟换算                                                                   |
| R4 | `fiber=0`（49 条）、`fat=0`（2 条）属实测零值，**不是缺失**                                                          |
| R5 | 能量与 Atwater 估算偏差 >20% 的 33 条**保留原值**，仅列入质量报告                                                        |

> 换算错了会差 100 倍（米饭 200 g：正确 232 kcal，错误 2.32 kcal）。已由单测 `tests/test_nutrition.py::test_r1_conversion_sanity` 锁死（断言米饭 `energy_kcal_per_100g == 116.0`）。

### 2.3 `data/class_mapping.csv` — 6 列（含类别↔ID 映射）

| 字段                    | 说明                                    |
| --------------------- | ------------------------------------- |
| `food_id`             | 0–350                                 |
| `name_zh` / `name_en` | 中英文名                                  |
| `tier`                | 1 / 2                                 |
| `tier1_name_check`    | 仅 tier1 填菜名，其余为空                      |
| `img_total`           | DFoodTJ-Rec 中该类图片总数（例如米饭 546、卤鹅 1593） |

**模型 10 类的 `class_id ↔ food_id` 映射**（模型输出用 `class_id`，查营养必须用 `food_id`）：

| class_id | food_id | 菜名     |
| -------- | ------- | ------ |
| 0        | 0       | 米饭     |
| 1        | 22      | 馒头     |
| 2        | 70      | 饺子     |
| 3        | 83      | 红烧肉    |
| 4        | 37      | 青椒肉丝   |
| 5        | 40      | 西红柿炒鸡蛋 |
| 6        | 66      | 清蒸鲈鱼   |
| 7        | 82      | 麻婆豆腐   |
| 8        | 136     | 蚝油西兰花  |
| 9        | 74      | 冬瓜汤    |

### 2.4 `data/reference_portions.csv` — 6 列（10 类，经验值）

| 字段                    | 说明                                                 |
| --------------------- | -------------------------------------------------- |
| `food_id` / `name_zh` | 菜品                                                 |
| `label`               | 份量单位名，如 `1碗` `1个` `1份`                             |
| `grams_per_portion`   | 一份的克数（米饭 200、馒头 100、饺子 250、红烧肉 150、其余 200、冬瓜汤 250） |
| `source`              | 说明串                                                |
| `status`              | **`reference_only`** —— 经验值，**未人工校准**，不能当称重值用      |

### 2.5 查询约束（`nutrition/db.py`）

- 必须按 **int 型 `food_id`** 精确查询；传字符串会抛 `TypeError`（**禁止字符串模糊匹配**）
- 未收录抛 `FoodNotFoundError`；数据缺失抛 `NutritionDataError`
- 按名字查询只有 `lookup_by_exact_name`，整名精确、多命中直接报错

---

## 3. 模型输出结构

### 3.1 两个模型

| 模型 | 权重                                          | 任务       | 输出                     |
| -- | ------------------------------------------- | -------- | ---------------------- |
| 分类 | `models/cls10/weights/best.pt`（yolov8n-cls） | 整图判 1 个菜 | `top5` 概率列表            |
| 检测 | `models/det10/weights/best.pt`（yolov8n）     | 一图多菜     | `detections[]`（框 + 类别） |

### 3.2 检测输出（`detection` 对象）

真实实例（真实红烧肉照片）：

```json
{
  "image_id": "3_test_000012",
  "model_version": "det10-v1",
  "task_type": "detection",
  "image_width": 341,
  "image_height": 256,
  "detections": [
    {"class_id": 3, "food_id": 83, "food_name": "红烧肉",
     "confidence": 0.976, "bbox_xyxy": [0.1, 0.0, 341.0, 256.0],
     "crop_b64": "<该框裁剪小图的 JPEG base64>"}
  ],
  "status": "ok",
  "warnings": []
}
```

字段表：

| 字段                             | 类型          | 说明                                                |
| ------------------------------ | ----------- | ------------------------------------------------- |
| `image_id`                     | str         | 调用方传入的标识（文件名去扩展名 / UUID）                          |
| `model_version`                | str         | `det10-v1` / `cls10-v1`                           |
| `task_type`                    | str         | `detection` / `classification`                    |
| `image_width` / `image_height` | int         | 原图尺寸                                              |
| `detections`                   | list        | 按置信度降序；无检测时为 `[]`                                 |
| ∟ `class_id`                   | int         | 模型内部类别 0–9（**非 food_id**）                         |
| ∟ `food_id`                    | int         | 已映射回 351 类标准 ID，**可直接查营养表**                       |
| ∟ `food_name`                  | str         | 中文菜名                                              |
| ∟ `confidence`                 | float       | 0–1                                               |
| ∟ `bbox_xyxy`                  | list[float] | `[x1,y1,x2,y2]` 像素坐标                              |
| ∟ `crop_b64`                   | str         | 该框裁剪图的 JPEG base64（Web 接口附加，便于前端展示；体积较大，离线批处理可忽略） |
| `status`                       | str         | `ok` / `empty` / `low_confidence` / `error`       |
| `warnings`                     | list[str]   | 低置信、未收录、异常提示                                      |

边界行为：

| 场景          | 行为                                              |
| ----------- | ----------------------------------------------- |
| 零检测         | `detections=[]`、`status="empty"`、warning 提示人工录入 |
| 置信度 0.3–0.6 | 保留，`status="low_confidence"`，提示复核               |
| 置信度 < 0.3   | 丢弃该框                                            |
| 读图失败        | `status="error"`，不抛未捕获异常                        |

### 3.3 分类输出（`classification` 对象）

```json
{"top5": [{"class_id": 3, "food_id": 83, "food_name": "红烧肉", "prob": 1.0}, ...],
 "status": "ok"}
```

`prob` 为归一化概率，降序；`top5` 恒为 5 项（不足时按实际类别数）。

### 3.4 Web 接口完整响应（`POST /api/analyze`）

**这是队友最可能对接的结构**，一次请求同时返回检测、分类、营养、目标、预警：

```
meta              {image_width, image_height, det_ms, cls_ms, total_ms, device, cls_version, det_version}
image_b64          str   检测框叠加图（JPEG base64）
orig_b64           str   原图（JPEG base64）
detection          obj   §3.2
fallback           bool  true = 检测为空、已用分类 Top-1 兜底出营养
classification     obj   §3.3
items[]            list  §5.1 每个菜的营养明细
meal               obj   §5.2 整餐汇总（null 表示无可用项）
targets            obj   §5.3 每日目标
alerts[]           list  §5.4 预警（最多 2 条）
```

真实实例节选：

```json
{"meta": {"image_width": 341, "image_height": 256, "det_ms": 40.1, "cls_ms": 11.0,
          "total_ms": 73.1, "device": "CPU", "cls_version": "cls10-v1", "det_version": "det10-v1"},
 "detection": {"status": "ok", "detections": [{"food_id": 83, "food_name": "红烧肉", "confidence": 0.976}]},
 "fallback": false,
 "classification": {"top5": [{"food_id": 83, "food_name": "红烧肉", "prob": 1.0}], "status": "ok"},
 "items": [{"food_id": 83, "food_name": "红烧肉", "weight_g": 150.0,
             "weight_source": "portion_reference",
             "carb_g": 5.07, "fat_g": 79.19, "protein_g": 12.91, "fiber_g": 0.82,
             "energy_kcal": 430.49,
             "per_100g": {"carb_g": 3.38, "fat_g": 52.79, "protein_g": 8.61, "fiber_g": 0.55, "energy_kcal": 286.99},
             "status": "ok",
             "warnings": ["重量按份量参考 1份=150.0g × 1.0 折算，非称重值"],
             "ref_portion": {"label": "1份", "grams": 150.0, "status": "reference_only"},
             "confidence": 0.976, "bbox_xyxy": [0.1, 0.0, 341.0, 256.0]}],
 "meal": {"items": [...], "totals": {"carb_g": 5.07, "fat_g": 79.19, "protein_g": 12.91,
                                     "fiber_g": 0.82, "energy_kcal": 430.49},
          "status": "ok", "warnings": []},
 "targets": {"bmr": 1648.8, "tdee": 2555.6, "target_kcal": 2172.2,
             "target_protein_g": 162.9, "target_fat_g": 60.3, "target_carb_g": 244.4,
             "bmi": 22.9, "bmi_advice": false, "notes": []},
 "alerts": []}
```

接口入口：`POST http://127.0.0.1:8765/api/analyze`，body = `{"image_b64": ..., "profile": {...}, "day_totals": {...}, "weights": {...}}`。

---

## 4. 模型训练之后反馈的东西

### 4.1 训练产物清单

| 产物    | 路径                                                    | 说明                              |
| ----- | ----------------------------------------------------- | ------------------------------- |
| 分类权重  | `models/cls10/weights/best.pt` / `last.pt`            | 各 2.98 MB                       |
| 检测权重  | `models/det10/weights/best.pt` / `last.pt`            | 各 6.48 MB                       |
| 训练日志  | `models/cls10/results.csv`、`models/det10/results.csv` | 逐 epoch 指标                      |
| 训练超参  | `models/*/args.yaml`                                  | epochs / imgsz / batch / seed 等 |
| 评测指标  | `reports/eval_metrics.json`                           | 分类 + 检测最终指标                     |
| 真实图核验 | `reports/real_image_infer.json`                       | 500 张真实照片的逐图输出                  |
| 错例清单  | `reports/error_cases.csv`（339 条）                      | 逐条失败样本                          |
| 评测报告  | `reports/eval_report.md`、`error_analysis.md`          | 人读版                             |

实际超参：cls = `epochs 30(19 早停) / imgsz 224 / batch 64 / seed 2026`；det = `epochs 25 / imgsz 416 / batch 8 / seed 2026 / lr0 0.01`，均 CPU。

### 4.2 训练日志字段（`results.csv`）

**分类 `models/cls10/results.csv`（9 列，19 行）**

| 字段                         | 说明          |
| -------------------------- | ----------- |
| `epoch`                    | 轮次（1-based） |
| `time`                     | 累计训练耗时（秒）   |
| `train/loss`               | 训练损失        |
| `metrics/accuracy_top1`    | 验证集 Top-1   |
| `metrics/accuracy_top5`    | 验证集 Top-5   |
| `val/loss`                 | 验证损失        |
| `lr/pg0`、`lr/pg1`、`lr/pg2` | 三组参数学习率     |

实测：**best epoch 9，Top-1 = 0.958，Top-5 = 1.000，val_loss 0.1999**，总耗时 1497.9 s。

**检测 `models/det10/results.csv`（13 列，25 行）**

| 字段                                                 | 说明                     |
| -------------------------------------------------- | ---------------------- |
| `epoch`、`time`                                     | 同上                     |
| `train/box_loss`、`train/cls_loss`、`train/dfl_loss` | 框回归 / 分类 / DFL 训练损失    |
| `metrics/precision(B)`、`metrics/recall(B)`         | 验证集精确率 / 召回率           |
| `metrics/mAP50(B)`、`metrics/mAP50-95(B)`           | mAP@0.5 / mAP@0.5:0.95 |
| `val/box_loss`、`val/cls_loss`、`val/dfl_loss`       | 验证损失                   |
| `lr/pg0`…`lr/pg2`                                  | 学习率                    |

实测：**best epoch 25**，验证集（det10/val）`P=0.8938, R=0.7808, mAP50=0.8758, mAP50-95=0.8511`，总耗时 3908.3 s；首轮 mAP50 仅 0.5607。

> 注意区分：训练日志里的指标是 **val split**；§4.3 是**独立 test split**，两者数值不同，别混用。

### 4.3 评测指标（`reports/eval_metrics.json`）

```json
{"classification": {"top1_acc": 0.934, "top3_acc": 0.996, "n_images": 500,
                    "infer_s_per_img": 0.0136, "hardware": "CPU 8 threads",
                    "per_class": {"0_米饭": {"top1": 0.92, "top3": 0.98, "n": 50}, ...}},
 "detection": {"precision": 0.88, "recall": 0.7781, "mAP50": 0.8902, "mAP50_95": 0.8636,
               "n_images": 0,
               "per_class": {"米饭": {"precision": 0.9499, "recall": 0.8065,
                                      "mAP50": 0.9402, "mAP50_95": 0.8965, "n_instances": 47}, ...}}}
```


- `classification.per_class` 键格式 `<class_id>_<菜名>`，含 `top1` / `top3` / `n`（该类测试图数）
- `detection.per_class` 键为菜名，含 `precision` / `recall` / `mAP50` / `mAP50_95` / `n_instances`
- **已知缺陷**：`detection.n_images` 取值为 `0`（评测脚本未取到该字段），实际测试集为 **200 张**；其余字段有效
- 分类 Top-3 = **99.6%** 即 PRD MI-01 口径（10 类高频、每类 50 张、逐张推理、前 3 候选命中）

### 4.4 真实域核验（`reports/real_image_infer.json`）

`summary` 字段：

| 字段                                        | 值                               | 含义                                   |
| ----------------------------------------- | ------------------------------- | ------------------------------------ |
| `n_images`                                | 500                             | 真实照片数（DFoodTJ-Rec 官方 test，10 类 × 50） |
| `detection.any_box_rate`                  | 0.938                           | 检出率                                  |
| `detection.top1_class_correct_rate`       | 0.796                           | 主框类别正确率                              |
| `detection.any_box_class_correct_rate`    | 0.818                           | 任一框类别正确率                             |
| `detection.multi_box_rate_on_single_dish` | 0.092                           | 单菜品图被切成多框的比例                         |
| `detection.avg_boxes_per_image`           | 1.036                           | 平均框数                                 |
| `detection.avg_top_conf`                  | 0.8343                          | 平均最高置信度                              |
| `detection.latency_ms`                    | p50 41.7 / p95 59.2 / max 151.3 | 检测延迟                                 |
| `classification.top1_acc`                 | 0.934                           | 真实图分类 Top-1                          |
| `classification.top3_acc`                 | 0.996                           | 真实图分类 Top-3                          |
| `classification.latency_ms`               | p50 14.9 / p95 21.0             | 分类延迟                                 |

`samples[]` 是逐图完整模型输出（结构与 §3.2 一致），可直接用于复盘。

### 4.5 错例清单（`reports/error_cases.csv`，339 条）

| 字段             | 说明                                |
| -------------- | --------------------------------- |
| `split`        | `real`（真实照片）/ `synth_test`（合成测试集） |
| `task`         | `classification` / `detection`    |
| `image`        | 相对路径                              |
| `gt`           | 真实类别                              |
| `pred`         | 模型预测类别                            |
| `pred_conf`    | 预测置信度                             |
| `failure_mode` | 失败模式原文（见下表）                       |

实际取值分布（339 条）：

| split      | task           | failure_mode              | 条数 |
| ---------- | -------------- | ------------------------- | -- |
| real       | detection      | 真实照片主框类别错误                | 71 |
| synth_test | detection      | 误检（背景/重复框，无匹配 GT）         | 48 |
| real       | detection      | 单菜品真实图出现多框（过分割/误检）        | 46 |
| synth_test | detection      | 定位正确但类别错误 (IoU=0.51~1.00) | 75 |
| real       | classification | top1 类别错误                 | 33 |
| real       | detection      | 未检出（真实照片无框）               | 31 |
| synth_test | detection      | 漏检（无 IoU≥0.5 的预测框）        | 26 |

> `synth_test` 行的 IoU 值写在 failure_mode 字符串里（如 `定位正确但类别错误 (IoU=0.99)`），按 IoU 分档统计共 75 条。

### 4.6 训练反馈结论（一句话版）

- **分类可用**：真实照片 Top-3 **99.6%**、Top-1 93.4%，延迟 p95 21 ms —— **菜品识别以分类模型为准**
- **检测定位可用、类别不稳**：mAP50 0.890（合成域），真实照片检出率 93.8% 但主框类别正确率仅 **79.6%**，单菜被切多框 9.2% —— **检测用于"切分出几个菜"，类别必须回查分类器**
- 因此 Web 链路设计了 `fallback`：检测为空时用分类 Top-1 兜底（`fallback=true`）

---

## 5. 下游：营养计算与预警字段

### 5.1 `items[]`（每个菜的营养明细）

| 字段                                                           | 说明                                                                                                |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `food_id` / `food_name`                                      | 菜品                                                                                                |
| `weight_g`                                                   | 采用重量（g）                                                                                           |
| `weight_source`                                              | **`user_input`**（用户称重）/ **`portion_reference`**（份量参考）/ **`model_estimate`**（估算，会带 warning"非称重实测"） |
| `carb_g` / `fat_g` / `protein_g` / `fiber_g` / `energy_kcal` | 实际摄入量 = `per_100g × weight_g / 100`，保留 2 位                                                        |
| `per_100g`                                                   | 该菜每 100g 的五项基准值（来自营养表）                                                                            |
| `status`                                                     | `ok` / `partial`（有营养素缺失）                                                                          |
| `warnings[]`                                                 | 如"重量按份量参考 1份=150.0g × 1.0 折算，非称重值"                                                                |
| `ref_portion`                                                | `{label, grams, status}`，份量参考溯源（status=reference_only）                                            |
| `confidence` / `bbox_xyxy`                                   | 回带模型输出，便于溯源                                                                                       |

重量校验：缺失 / NaN / inf / ≤0 / >5000 g 一律抛 `NutritionItemError`（防止单位填错成 kg）。

### 5.2 `meal`

`{items: [...], totals: {carb_g, fat_g, protein_g, fiber_g, energy_kcal}, status, warnings}`

### 5.3 `targets`

| 字段                                                    | 说明                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| `bmr`                                                 | Mifflin-St Jeor 基础代谢                                                     |
| `tdee`                                                | = BMR × 活动系数（sedentary 1.2 / light 1.375 / moderate 1.55 / active 1.725） |
| `target_kcal`                                         | 减脂 `max(TDEE×0.85, BMR×1.1)`；增肌 `TDEE×1.10`；控糖/维持 `TDEE×1.00`            |
| `target_protein_g` / `target_fat_g` / `target_carb_g` | 按目标供能比换算（减脂 30/25/45，增肌 25/25/50，控糖 25/30/45，维持 20/30/50）                |
| `bmi` / `bmi_advice`                                  | BMI；<18.5 或 >30 时 `bmi_advice=true` 并提示咨询专业人士                            |
| `notes`                                               | 附加说明                                                                     |

### 5.4 `alerts[]`（最多 2 条，按 high→medium→info 排序，同码当日去重）

| 字段                             | 说明                                       |
| ------------------------------ | ---------------------------------------- |
| `code`                         | `AL-01`…`AL-05`                          |
| `name`                         | 中文名（热量超标 / 热量不足 / 蛋白质不足 / 碳水超标 / 单餐占比过高） |
| `message`                      | 面向用户的文案（含具体数值）                           |
| `basis`                        | **触发依据原文**（如 `2400 > 2172.2×1.10`），便于核对  |
| `severity`                     | `high` / `medium` / `info`               |
| `record_date` / `trigger_time` | 日期 / 触发时刻（`HH:MM`）                       |

规则与阈值（与 PRD 表 4-2 一致）：AL-01 日热量 > 目标×1.10（high）；AL-02 日热量 < 目标×0.70 且 ≥20:00（medium）；AL-03 蛋白质 < 目标×0.70 且 ≥20:00（medium）；AL-04 **仅控糖目标**下碳水 > 目标×1.10（high）；AL-05 单餐 > 日目标×50%（info）。

---

## 6. 对接注意事项（务必确认）

1. **检测框 ≠ 重量**。禁止用 bbox 面积换算克数；重量必须走三态来源。
2. **`class_id` ≠ `food_id`**。查营养表前必须映射（表见 §2.3）。
3. **只有 10 类**（tier=1）被模型覆盖，其余 341 类返回 `status="empty"` + `fallback=true`，需走人工补录（页面提供 351 类下拉）。
4. **Top-3 是分类口径**（PRD MI-01），检测的 mAP 是另一套指标，**不可混用、不可互相替代**。
5. **`reference_portions.csv` 是经验值未校准**，用于演示 OK，用于 MI-02（热量偏差 ≤15%）验收前必须人工校准。
6. **检测数据是合成的**（由单菜图拼贴生成，真值来自粘贴坐标）。合成域 mAP 是上限，**真实多菜照片的真实基准仍缺**（需人工标注 ≥200 张）。
7. 接口字段恒在（无数据时为 `null` 或 `[]`），不做字段省略，前端可放心直取。

---

## 7. 最小对接示例

启动服务（模型预加载约 20 s）：

```bash
cd D:/workbuddy/kkk/food_pipeline
python web/serve.py 8765
```

Python 调用：

```python
import base64, json, urllib.request

img = "your_photo.jpg"
payload = {
    "image_b64": base64.b64encode(open(img, "rb").read()).decode(),
    "profile": {"gender": "male", "height_cm": 175, "weight_kg": 70,
                "age": 30, "activity": "moderate", "goal": "lose_fat"},
    "day_totals": {},          # 今日已摄入：{"energy_kcal":1200, "protein_g":60, "carb_g":150}
    "weights": {},             # 指定重量：{"83": 150}（food_id -> 克）
}
req = urllib.request.Request("http://127.0.0.1:8765/api/analyze",
                              data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=180))
for d in r["detection"]["detections"]:
    print(d["food_id"], d["food_name"], round(d["confidence"], 3))
print(r["meal"]["totals"] if r["meal"] else "无结果")
```

离线批处理（不用 Web）：

```bash
python scripts/infer.py --model models/det10/weights/best.pt --source <图片或目录> [--conf 0.25]
python scripts/infer.py --model models/cls10/weights/best.pt --source <图片> --task classification
```
