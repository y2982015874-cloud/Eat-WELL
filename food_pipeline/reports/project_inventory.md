# 项目文件清单与清理说明

盘点对象：`D:/workbuddy/kkk/food_pipeline`（工作空间内的工程目录）
盘点时间：2026-10-23　盘点后总大小 **1.2 GB**，其中数据集占 1.19 GB

> 工作空间根目录另有 4 个原始/交付文档（PRD V1.4 原件、PRD V1.5 对齐版、项目任务书、DFood-TJ 论文）
> 与 `DFoodTJ-Nutr/`（营养源表）。这些属于**用户提供的资料与交付物，未做任何改动**。

---

## 一、总览

| 目录 | 大小 | 文件数 | 性质 | 能否删 |
|---|---|---|---|---|
| `data/` | 104 K | 6 | 清洗后的营养库与映射表 | **不可删**（交付核心） |
| `datasets/` | 1.19 G | 21 255 | 训练数据 | 见 §4（子集可释放） |
| `models/` | 28 M | 41 | 训练产物 | best.pt 不可删，其余过程图可再生成 |
| `nutrition/` | 58 K | 4 | 营养 Python 包 | **不可删**（交付核心） |
| `scripts/` | 288 K | 13 | 流程脚本 | **不可删**（可复现） |
| `reports/` | 284 K | 17 | 全部文档 | **不可删**（交付物） |
| `web/` | 68 K | 3 | 验收面板 | **不可删** |
| `tests/` | 16 K | 2 | 单测 38 项 | **不可删** |
| `prompts/` | 4 K | 1 | 大模型提示词模板 | 保留（接入即用） |
| `requirements.txt` / `README.md` | — | 2 | 依赖清单 / 导航 | 配置，保留 |

---

## 二、逐文件说明

### 2.1 `data/`（营养库，清洗定稿）

| 文件 | 内容 | 说明 |
|---|---|---|
| `nutrition_clean.csv` | 351 行 × 17 列 | **营养库主表**，每 100g 口径；主键 `food_id` 0–350 |
| `class_mapping.csv` | 351 行 × 6 列 | 类别↔ID 映射 + `tier` + `img_total`（各类图片数） |
| `reference_portions.csv` | 10 行 × 6 列 | 10 类份量参考（g/份），`status=reference_only` |
| `nutrition_field_dictionary.csv` | 字段字典 | 原始字段 / 清洗字段 / 转换规则 R1–R5 |
| `data_inventory.md` | 资料盘点 | 工作空间内 5 类资料的核查记录与矛盾说明 |
| `clean_log.txt` | 清洗日志 | `build_nutrition_db.py` 的执行记录，可追溯 |

### 2.2 `datasets/`（训练数据）

| 文件 | 大小 | 内容 |
|---|---|---|
| `dfoodtj_subset/` | 764 M / 12 239 图 | 从 DFoodTJ-Rec.zip 解压出的 10 类源图，按官方 `train/val/test` 分目录（**cls10、det10 的上游**） |
| `cls10/` | 324 M / 5 000 图 | 分类数据集：每类 400 训练 / 50 验证 / 50 测试（8:1:1） |
| `det10/` | 103 M / 2 000 图 + 2 000 标签 | 检测数据集（合成）：1600/200/200，`data.yaml` 定义 nc=10 |
| `det10_preview/` | 756 K / 10 图 | 合成样本可视化，用于人工检查合成质量 |
| `segreal_food1/` | ~2 M / 3 932 标签 | **单类 food 真实域检测评测集**（DFoodTJ-Seg 3,932 张真实照片，GT=实例掩码→bbox，class-agnostic）；图片不落盘，评测时从 zip 流式读 |
| `cls10_split_manifest.csv` | 412 K | 5 000 行逐图清单（可追溯每张图的来源与划分） |
| `det10_synth_manifest.csv` | 368 K | 2 000 图 / 4 201 个目标框的合成参数记录 |

### 2.3 `models/`（训练产物）

| 文件 | 说明 |
|---|---|
| `cls10/weights/best.pt` | **分类模型**（第 9 轮，val Top-1 0.958）—— 推理/评测用这个 |
| `det10/weights/best.pt` | **检测模型**（第 25 轮，test mAP50 0.890）—— 推理/评测用这个 |
| `cls10/results.csv`、`det10/results.csv` | 逐轮训练指标（字段说明见 `data_field_spec.md` §4.2） |
| `cls10/args.yaml`、`det10/args.yaml` | 训练超参（epochs / imgsz / batch / seed） |
| `*/results.png`、`*curve.png`、`confusion_matrix*.png` | 训练与验证曲线、混淆矩阵（可视化证据） |
| `*/train_batch*.jpg`、`val_batch*_labels/pred.jpg` | 训练/验证批次样本图（可视化证据） |
| `train_log.txt` | 训练过程日志 |
| `pretrained/yolov8n.pt`、`yolov8n-cls.pt` | COCO 预训练权重（12 M），**离线训练必需**，脚本已改读此路径 |

### 2.4 `nutrition/`（营养包）

| 文件 | 说明 |
|---|---|
| `__init__.py` | 导出 `NutritionDB` / `MealCalculator` / `RecommendationEngine` / `AlertEngine` |
| `db.py` | 按 `food_id` 精确查询；未收录抛 `FoodNotFoundError`，非 int 抛 `TypeError` |
| `calculator.py` | 单品与整餐计算；三态重量来源；重量边界校验（≤5000 g） |
| `advisor.py` | BMR/TDEE/目标（表 4-1）与 AL-01~AL-05 预警（表 4-2） |

### 2.5 `scripts/`（15 个，按流水线顺序）

| 脚本 | 作用 | 何时用 |
|---|---|---|
| `extract_subset.py` | 从 zip 按 split 解压 10 类源图 | 数据准备 |
| `build_nutrition_db.py` | density.xlsx → nutrition_clage.csv | 数据准备 |
| `prepare_cls_dataset.py` | 生成 cls10 | 数据准备 |
| `synthesize_det_dataset.py` | 生成 det10（合成） | 数据准备 |
| `build_segeval.py` | 生成 segreal_food1（只读 zip） | 评测集构建 |
| `check_seg_leak.py` / `verify_leak.py` | 泄漏排查（dHash 粗筛 → 4 方向 MAE 复核） | 评测可信性 |
| `eval_segreal.py` | segreal_food1 的 class-agnostic COCO AP 评测 | 评测 |
| `pretrain_check.py` | 训练前 36 项检查 | **训练前必跑** |
| `train_models.py` | 串行训练 cls + det（读本地预训练权重） | 训练 |
| `train_det_only.py` | 仅训练 det（cls 已完成时用，离线可跑） | 训练 |
| `evaluate.py` | 分类 Top-3 + 检测 P/R/mAP，产出评测报告 | 评测 |
| `real_image_check.py` | 500 张真实照片推理核验 | 评测 |
| `error_analysis.py` | 失败模式统计，产出 `error_cases.csv` | 评测 |
| `infer.py` | 单图/批量推理（输出模型契约 JSON） | 使用 |
| `run_example.py` | 全链路示例（识别→营养→预警） | 演示 |
| `patch_prd.py` | 按实现修订 PRD，另存 V1.5 | 文档维护 |
| `e2e_acceptance.py` | 9 场景真实图片端到端验收（T1–T9），产出验收记录与原始响应 | **验收必跑** |
| `contract_check.py` | 修复前后响应字段集合逐层比对，产出契约核对记录 | 契约回归 |

### 2.6 `web/`（验收面板）

| 文件 | 说明 |
|---|---|
| `serve.py` | 后端：标准库 `http.server`，零新增依赖，仅监听 127.0.0.1；端口 8765 |
| `index.html` | 前端：上传/示例图、检测框叠加、Top-5 概率条、营养卡、预警、原始 JSON |
| `serve.log` | 运行日志（服务当前占用中，重启后可自行删除） |

### 2.6b `tests/`（3 个）

| 文件 | 说明 |
|---|---|
| `test_nutrition.py` | 营养包单测 38 项（查询/计算/预警全分支） |
| `test_pipeline_contract.py` | 19 项针对性测试：class_id→food_id 映射、营养匹配、计算公式、`/api/analyze` 响应契约 |
| `frontend_render_check.js` | Node 运行：用真实响应驱动 `index.html` 的渲染函数，检测"前端读后端未返回字段"导致的中断（无需浏览器） |

### 2.7 `reports/`（21 个文档 + `_evidence/`）

| 文件 | 用途 |
|---|---|
| `README_usage.md` | 使用说明（环境/复现/评测/推理/面板/已知限制） |
| `data_field_spec.md` | 数据字段说明（营养表 + 模型输出结构，**队友对接看这份**） |
| `prd_alignment_review.md` | PRD 与实现的 14 处冲突及修订说明 |
| `data_field_spec.md`、`model_output_contract.md` | 字段与模型输出契约 |
| `data_quality_report.md` | 数据质量与矛盾核查 |
| `pretrain_check.md` | 训练前 36 项检查结果（全 PASS） |
| `eval_report.md`、`eval_metrics.json` | 评测结论与指标 |
| `real_image_check.md`、`real_image_infer.json` | 500 张真实照片核验（逐图结果） |
| `error_analysis.md`、`error_cases.csv` | 错误分析与 339 条错例 |
| `annotation_format.md` | 标注格式说明 |
| `wp_b_delivery.md`、`wp_c_delivery.md`、`wp_c_example_output.json` | 工作包 B / C 交付说明与示例输出 |
| `fault_diagnosis_report.md` | **业务链路故障定位**（只读审计：各环节状态、缺陷清单、根因、证据） |
| `fix_list.md` | **修改清单与前后差异**（含评估后放弃的改动及原因） |
| `e2e_acceptance.md` | **端到端验收记录**（9 场景：请求/日志证据/响应/前端渲染） |
| `contract_check.md` | **接口契约不变核对**（修复前后字段集合 DIFF=0） |
| `_evidence/` | 原始响应证据：`E*.json` 修复前、`T*.json` 修复后（未加工） |
| `project_inventory.md` | 本文件 |
| `seg_audit/` | DFoodTJ-Seg 只读审计产物（全量统计 CSV + 14 张可视化） |
| `segreal_eval_report.md` / `segreal_eval/` | **真实域检测评测报告**与指标（含 per_image.csv、metrics.json、14 张 GT/Pred 可视化） |
| `segreal_leakcheck*.csv` | 泄漏排查（粗筛 + 像素级复核） |

---

## 三、本次清理明细

| 操作 | 对象 | 理由 |
|---|---|---|
| 删除 | `web/_t.json`(177 K)、`web/_r.json`(66 K)、`web/_r2.json`(111 K) | 端到端自测用的临时 payload 与响应，已被 `reports/` 中的正式产物覆盖 |
| 删除 | `runs/`（16 M） | ultralytics 评测时自动产出的曲线与混淆矩阵，**与 `models/det10/` 下已有图片完全重复** |
| 删除 | `models/cls10/weights/last.pt`、`models/det10/weights/last.pt`（共 9.4 M） | 交付只用 `best.pt`；det 的 last 即第 25 轮（=best 轮），cls 的 last 是早停末轮（非最佳），均无使用入口 |
| 删除 | `nutrition/__pycache__`（及编译缓存） | Python 字节码缓存 |
| 归置 | `yolov8n.pt`、`yolov8n-cls.pt` → `models/pretrained/` | 原本散落在根目录，与"models 存放模型"的约定不符 |
| 同步 | `train_models.py`、`train_det_only.py`、`README_usage.md`、`wp_b_delivery.md` | 权重路径改为 `models/pretrained/`，避免脚本找不到权重又去联网下载（代理会失败） |
| 补充 | `requirements.txt` | 增加 `python-docx==1.2.0`（`patch_prd.py` 依赖），并给每个依赖加注释 |
| 新增 | `README.md`（根目录） | 原本根目录没有任何说明文件，新增目录地图 + 三步上手 + 数据流图 |

**保留未删**：`web/serve.log`（服务正在占用句柄）、`datasets/dfoodtj_subset`（见下）。

---

## 四、可进一步释放的空间（需你确认）

| 对象 | 大小 | 删除代价 |
|---|---|---|
| `datasets/dfoodtj_subset/` | **764 M** | 它是 cls10/det10 的上游源图。删除后 **已训练好的模型不受影响**，但无法重新生成数据集——需从 19 GB 的 `DFoodTJ-Rec.zip` 再次解压（约数十分钟）。**建议：若要归档/传仓可删，若要继续调数据则留着。** |
| `datasets/det10_preview/` | 756 K | 合成质量的人工检查证据，可删 |
| `models/*/` 下的 png/jpg 过程图 | ~2 M | 训练曲线与样本图，可删（`results.csv` 保留了全部数值） |

我没有主动删这三项，因为它们的"可再生成成本"或"证据价值"需要你判断。

---

## 五、清理后的一致性校验（已实际执行）

| 检查 | 结果 |
|---|---|
| 营养链路单测 | `Ran 38 tests ... OK` |
| 面板服务健康 | `{"ready": true, "cls_weights": true, "det_weights": true}` |
| 全部脚本语法编译 | 通过（`scripts/` 13 个 + `nutrition/` 4 个 + `web/serve.py` + `tests/`） |
| 权重路径引用一致性 | 全局检索 `yolov8n` 仅命中 `models/pretrained/` 与两个训练脚本，无遗漏 |
| 文档与实际一致性 | `README_usage.md`、`wp_b_delivery.md` 中的权重路径已同步 |

---

## 六、未启用但有意保留的项

| 项 | 说明 |
|---|---|
| `prompts/llm_advice_prompt.md` | 大模型建议的提示词模板（含 6 条硬约束）。本期未接入大模型，接入后可直接使用 |
| `train_det_only.py` | 断点/离线单跑 det 的入口（cls 已训练完时避免重跑） |
| `run_example.py` | 全链路演示脚本，`wp_c_example_output.json` 即其输出 |
| `reports/annotation_format.md` | 标注格式说明，供后续人工标注真实多菜品数据时参照 |
