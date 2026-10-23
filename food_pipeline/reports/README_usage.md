# food_pipeline 使用说明（B5）

中餐食物识别 → 营养数据库 → 营养分析与预警 的最小可行流水线（10 类高频试点，CPU 可复现）。

## 0. 先读这份（对接前置）
- **`reports/data_field_spec.md`** —— 数据字段说明：营养表字段、模型输出结构、训练反馈指标（队友对接看这一份）
- **`reports/fault_diagnosis_report.md`** —— 业务链路故障定位（只读审计结论）
- **`reports/fix_list.md`** —— 实际修改文件清单、逐项说明与修改前后差异
- **`reports/e2e_acceptance.md`** —— 9 场景真实图片端到端验收记录
- **`reports/contract_check.md`** —— 接口契约保持不变的核对记录（修复前后字段比对）

## 1. 环境
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```
Python 3.12+，无需 GPU。全部脚本在仓库根目录 `food_pipeline/` 下运行。

## 2. 一键复现数据
```bash
python scripts/extract_subset.py           # 按 split 解压 DFoodTJ-Rec 10 类源图
python scripts/build_nutrition_db.py       # 营养库清洗（density.xlsx → nutrition_clean.csv）
python scripts/prepare_cls_dataset.py      # 分类数据集 cls10
python scripts/synthesize_det_dataset.py   # 合成检测集 det10（seed=20261023）
```
输入路径写在各脚本头部（`D:/专业实训/...`），**原始数据只读，不覆盖**。

## 3. 训练
```bash
python scripts/train_models.py             # 串行训练 cls10 + det10，日志 models/train_log.txt
```
- cls: YOLOv8n-cls / imgsz 224 / epochs 30 / batch 64 / seed 2026 / CPU（第 19 轮早停，best 为第 9 轮）
- det: YOLOv8n / imgsz 416 / epochs 25 / batch 8 / seed 2026 / CPU（跑满 25 轮，best 为第 25 轮）
- 产出：`models/cls10/weights/best.pt`、`models/det10/weights/best.pt`、各自 `results.csv` / `args.yaml`
- 断网/代理失败时：预训练权重已随项目落盘（`models/pretrained/yolov8n.pt`、`yolov8n-cls.pt`），训练脚本直接读本地路径，
  用 `python scripts/train_det_only.py` 单独训练检测模型即可（不联网）。

## 4. 评测
```bash
python scripts/evaluate.py                 # 输出 reports/eval_metrics.json + eval_report.md
python scripts/real_image_check.py         # 真实照片推理核验 + 延迟 P50/P95
python scripts/error_analysis.py           # 混淆矩阵 / 失败模式 / 错例清单
```
- 分类：Top-1 / **Top-3（PRD MI-01 口径）**，独立 test 集 500 张（每类 50）
- 检测：P / R / mAP@0.5 / mAP@0.5:0.95 + 各类指标，独立 test 集
- 真实域：500 张 DFoodTJ-Rec 官方 test 真实照片上的检出率/类别正确率/多框率/延迟分位

## 5. 推理
```bash
python scripts/infer.py --model models/det10/weights/best.pt --source <图片或目录>
python scripts/infer.py --model models/cls10/weights/best.pt --source <图片> --task classification
```
输出结构见 `reports/model_output_contract.md`（含 food_id → 营养库直连映射、低置信/空检测/错误处理）。

## 6. 营养链路（工作包 C）
```bash
python -m unittest tests.test_nutrition -v   # 38 项单测
python scripts/run_example.py                # 查询→计算→推荐→预警 全链路示例
```
文档见 `reports/wp_c_delivery.md`（I/O 结构、异常矩阵、规则来源、局限性）。

## 7. 可视化验收面板（上传图片 → 看模型输出）

```bash
python web/serve.py 8765       # 仅监听 127.0.0.1，零第三方 Web 依赖（标准库 http.server）
# 浏览器打开 http://127.0.0.1:8765
```

- 上传/拖拽图片，或点内置示例（合成多菜品 / 真实红烧肉 / 真实米饭降级演示）
- 可视化内容：检测框叠加图（可切原图/标注图）、检测结果表（类别·置信度·food_id·重量·热量）、
  分类 Top-5 概率条、营养汇总与目标对比、预警（AL-01~AL-05）、原始契约 JSON
- 重量默认走「份量参考」（非称重），填入克数即切换为「称重」；
  可从 351 类中人工补录未识别菜品；改档案/重量会实时重算营养与预警
- 检测未检出时自动用分类器 Top-1 兜底（页面会标注"整图口径·无定位框"）

## 8. 目录结构
```
food_pipeline/
├── data/          营养库、字段字典、类别映射、份量参考、盘点与日志
├── datasets/      dfoodtj_subset / cls10 / det10 + 两个 manifest + 合成预览
├── models/        cls10 / det10（权重、训练曲线、args）
├── nutrition/     db.py calculator.py advisor.py
├── scripts/       上述全部脚本
├── tests/         test_nutrition.py
├── reports/       交付报告与评测结果
└── prompts/       LLM 建议提示词模板
```

## 9. 业务链路验收与回归（修复后新增）

```bash
python web/serve.py 8765                 # 启动验收面板（模型预加载约 20s）
python scripts/e2e_acceptance.py         # 9 场景真实图片端到端 → reports/e2e_acceptance.md
node   tests/frontend_render_check.js reports/_evidence/T1.json   # 前端渲染回归（无需浏览器）
python scripts/contract_check.py         # 修复前后响应字段集合比对 → reports/contract_check.md
python -m unittest tests.test_nutrition tests.test_pipeline_contract -v   # 57 项单测
```

- 前端渲染检查用**真实后端响应**驱动 `web/index.html` 的真实渲染函数，
  可捕获"前端读取后端未返回字段"导致的渲染中断（历史上 `t.weight_g` 即由此引发）
- 服务端阶段日志：`[analyze][<request_id>] 阶段 耗时ms 状态 细节`，写入 `web/serve.log`

## 10. 已知限制（重要）
1. det10 为**合成数据**：合成域 mAP@0.5=0.890，但真实照片上主框类别正确率降至 79.6%、
   单菜品图多框率 9.2%（见 `reports/real_image_check.md`）。**定位能力可外推，分类能力需分类器兜底**；
   工作区内**不存在**真实多菜品标注数据，检测模型的真实域验收基准仍需人工标注 ≥200 张。
2. 检测框不代表重量；重量走 user_input / portion_reference / model_estimate 三态标注。
3. 营养库许可待核实（Science Databank 条目）；`reference_portions.csv` 目前为 reference_only，未校准。
4. Top-3 为分类口径，与检测 mAP 不可混用。
5. 仅覆盖 351 类中的 10 类；`food-test.v1i.yolov8`（UEC-Food100 日餐、单近全图框）未纳入主训练。
