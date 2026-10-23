# food_pipeline

中餐食物识别 → 营养查询 → 营养分析与预警 的最小可行流水线（10 类高频试点，CPU 可复现）。
详细文档在 `reports/`，本文件只做导航。

## 目录地图

| 目录 | 内容 | 说明 |
|---|---|---|
| `data/` | 营养库与映射表 | 清洗后的交付数据（351 类），**只读** |
| `datasets/` | 训练集 | cls10（分类）/ det10（检测合成）/ dfoodtj_subset（解压源图） |
| `models/` | 模型产物 | `cls10/weights/best.pt`、`det10/weights/best.pt`、`pretrained/`（预训练权重） |
| `nutrition/` | 营养 Python 包 | `db.py` 查询 / `calculator.py` 计算 / `advisor.py` 目标与预警 |
| `scripts/` | 流程脚本 | 数据 → 训练 → 评测 → 推理，按文件名顺序即流水线 |
| `web/` | 可视化验收面板 | `serve.py` + `index.html`，零新增依赖 |
| `tests/` | 单测 | 38 项，覆盖营养链路 |
| `reports/` | 全部文档 | 见下 |
| `prompts/` | 大模型提示词模板 | 本期未接入大模型 |

## 三步上手

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

python web/serve.py 8765          # 打开 http://127.0.0.1:8765 上传图片看结果
python -m unittest tests.test_nutrition -v    # 跑营养链路单测
```

## 文档索引

| 文档 | 用途 |
|---|---|
| `reports/README_usage.md` | **使用说明**（复现步骤、命令、已知限制） |
| `reports/data_field_spec.md` | **数据字段说明**（营养表字段 + 模型输出结构，队友对接看这份） |
| `reports/prd_alignment_review.md` | PRD 与实现的 14 处冲突及修订说明 |
| `reports/eval_report.md` / `error_analysis.md` | 评测结果与错误案例分析 |
| `reports/wp_b_delivery.md` / `wp_c_delivery.md` | 工作包 B / C 交付说明 |
| `reports/project_inventory.md` | 文件清单与冗余清理记录 |

## 数据流向

```
D:/专业实训/DFoodTJ-Rec.zip ──extract_subset──→ datasets/dfoodtj_subset（12239 张源图）
                                                    ├─prepare_cls_dataset─→ datasets/cls10（5000，真实图）
                                                    └─synthesize_det_dataset─→ datasets/det10（2000，合成图）
D:/专业实训/DFoodTJ-Nutr/density.xlsx ──build_nutrition_db──→ data/nutrition_clean.csv（351 类）

cls10 ──train──→ models/cls10/weights/best.pt ──→ 分类 Top-3（MI-01 口径）
det10 ──train──→ models/det10/weights/best.pt ──→ 一图多菜的框
两者 + nutrition/ ──→ web/serve.py ──→ 营养卡 + AL-01~AL-05 预警
```
