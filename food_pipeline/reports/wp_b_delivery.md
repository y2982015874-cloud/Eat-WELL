# 工作包 B 交付说明：YOLOv8 训练与调优

生成时间：2026-10-23　环境：Python 3.12 / torch 2.5.0+cpu / ultralytics 8.4.184
硬件：13th Gen Intel Core i7-1360P（**无独立显卡，纯 CPU**），16 GB 内存

---

## 1. 任务边界（先说清楚做了什么、没做什么）

| 项 | 结论 |
|---|---|
| 训练数据 | **两个模型、两套数据**：分类器用**真实** DFoodTJ-Rec 图片；检测器用**合成**多菜品图（经用户确认） |
| 类别范围 | 351 类中的 **10 类高频试点**（米饭/馒头/饺子/红烧肉/青椒肉丝/西红柿炒鸡蛋/清蒸鲈鱼/麻婆豆腐/蚝油西兰花/冬瓜汤），因纯 CPU 环境 |
| `food-test.v1i.yolov8` | 实测为 **UEC-Food100 日餐**、9472 图/9472 框（平均每图 1 个近全图框），**无定位价值且非中餐**，未纳入主训练 |
| 训练真实性 | 两个模型均为**真实训练产出**（有 `results.csv` / `args.yaml` / 权重 / 早停），非占位、非伪造 |

---

## 2. B1 训练前检查（已通过）

脚本：`scripts/pretrain_check.py` → 报告：`reports/pretrain_check.md`
**36 项检查全部 PASS（FAIL=0 / WARN=0）**，覆盖：

- cls10：目录结构（10 类）、图像可解码（train 4000 / val 500 / test 500，损坏 0）、类别均衡、**划分无重叠**
- det10：`data.yaml` 字段完整、图像可解码、标签格式合法（5 列、索引 ∈[0,9]、坐标 ∈[0,1]、w/h>0）、空标注 0、目标数分布、**划分无重叠**
- 关键防泄漏：train/val/test 无同名文件；合成图源图严格按 DFoodTJ-Rec 官方 split 取

---

## 3. B2 训练过程

| 模型 | 基模型 | 数据 | imgsz | batch | epochs | seed | 实际 | 耗时 | 产出 |
|---|---|---|---|---|---|---|---|---|---|
| cls10 | `yolov8n-cls.pt` | cls10 真实图 5000 张 | 224 | 64 | 30 | 2026 | **第 19 轮早停**（patience=10，best=第 9 轮） | 1498 s（≈25 min） | `models/cls10/weights/best.pt` |
| det10 | `yolov8n.pt`（本地落盘） | det10 合成图 2000 张 / 4201 框 | 416 | 8 | 25 | 2026 | **跑满 25 轮**（best=第 25 轮） | 3908 s（≈65 min） | `models/det10/weights/best.pt` |

- 训练曲线与超参存档：`models/cls10/results.csv`、`models/det10/results.csv`、各自 `args.yaml`
- cls 训练第 9 轮 val top1=**0.958** / top5=**1.000**（第 19 轮 0.946，触发早停后回退到 best）
- det 训练 mAP50-95 从第 1 轮 0.516 → 第 25 轮 **0.851**（单调上升，未过拟合）
- **踩坑记录**：`YOLO("yolov8n.pt")` 走 GitHub 下载被代理拦截（502）；已改为 `hf-mirror` 下载并落盘为
  落盘为 `models/pretrained/yolov8n.pt`（另含 `yolov8n-cls.pt`），新增 `scripts/train_det_only.py` 走本地权重，断网可复现

---

## 4. B3 评测结果（独立 test 集，未参与训练/调参）

### 4.1 分类模型（PRD MI-01 口径）——**达标**

| 指标 | 目标 | 实测 | 结论 |
|---|---|---|---|
| **Top-3 准确率** | ≥ 85% | **99.60%**（498/500） | ✅ 通过 |
| Top-1 准确率 | 参考 | 93.40% | 高于论文全量 351 类 ResNet50 的 76.57% |
| 单张推理 | — | 13.6~17.1 ms（CPU） | — |

每类 Top-3：馒头/饺子/红烧肉/青椒肉丝/西红柿炒鸡蛋/清蒸鲈鱼/麻婆豆腐/蚝油西兰花 = 100%，米饭/冬瓜汤 = 98%。

### 4.2 检测模型（合成 test 集 200 张 / 429 个真实框）

| 指标 | 实测 |
|---|---|
| Precision | 0.880 |
| Recall | 0.778 |
| **mAP@0.5** | **0.8902** |
| **mAP@0.5:0.95** | **0.8636** |

最弱三类：馒头 mAP50 0.802、饺子 0.854、冬瓜汤 0.846（外观相近主食/汤类）。

### 4.3 真实图片推理核验（域差距，500 张 DFoodTJ-Rec 官方 test 真实照片）

| 指标 | 检测 det10 | 分类 cls10 |
|---|---|---|
| 检出率（≥1 框） | **93.8%** | — |
| 主框类别正确率 / Top-1 | **79.6%** | **93.4%** |
| 任一框类别正确率 / Top-3 | 81.8% | **99.6%** |
| 单菜品图多框率（误检信号） | 9.2% | — |
| 单张推理 P50 / P95 | 41.7 / **59.2 ms** | 14.9 / **21.0 ms** |

> **PRD MI-03（P95 ≤ 5s）**：模型侧 P95 最高 59.2 ms，远低于 5s。

**结论**：合成域 mAP 是**同分布上限**，真实域主框类别正确率降到 79.6%。
→ 检测模型在**单菜品整图**（一道菜占满画面）上定位可用，但在**真实多菜品照片上不可用**（2026-10-23 修正，见 segreal_eval_report.md）。

### 4.4 B4 模型输出接口

契约文档：`reports/model_output_contract.md`；实现：`scripts/infer.py`
字段：`image_id / model_version / task_type / image_width / image_height /
detections[{class_id, food_id, food_name, confidence, bbox_xyxy}] / status / warnings / infer_ms`
- `food_id` 直接等于 DFoodTJ 营养库主键，可零映射直连营养计算（工作包 C）
- 低置信（<0.3）丢弃并警告；0.3~0.6 标 `confidence_flag=low`；空检测 `status=empty`；异常 `status=error`
- 真实输出样例：`reports/real_image_infer.json → samples`

### 4.5 B5 错误案例分析

文档：`reports/error_analysis.md`；逐条错例：`reports/error_cases.csv`（339 条）

- 分类错例 33 条：米饭↔红烧肉/麻婆豆腐、馒头↔饺子、冬瓜汤↔饺子 为主
- 检测（合成域，conf=0.25 + IoU≥0.5 贪心匹配）：429 GT / 451 预测 → 匹配 403、
  **类别错 84（占 GT 19.6%）**、漏检 26、误检 48
- 检测（真实域）：主框类别错 71、单菜品多框 46、未检出 31
- 根因：合成背景与真实餐盘/桌面分布不同；框尺度先验偏差；主食类外观相近；检测头分类能力弱于专用分类器
- 改进建议（按性价比）：真实背景增强合成 → 扩类扩分辨率 → 人工标注真实多菜品 ≥200 张 → 推理侧同 food_id 框合并 + 低置信人工确认

---

## 5. 交付物清单（B5）

| 交付项 | 路径 |
|---|---|
| 数据集配置文件 | `datasets/det10/data.yaml`、`datasets/cls10/{train,val,test}/` |
| 训练代码 | `scripts/train_models.py`、`scripts/train_det_only.py` |
| 推理代码 | `scripts/infer.py`（契约化输出） |
| 评测代码 | `scripts/evaluate.py`、`scripts/real_image_check.py`、`scripts/error_analysis.py` |
| 训练前检查 | `scripts/pretrain_check.py` → `reports/pretrain_check.md` |
| 依赖清单 | `requirements.txt` |
| 最佳权重 | `models/cls10/weights/best.pt`、`models/det10/weights/best.pt` |
| 训练日志与曲线 | `models/cls10/results.csv`、`models/det10/results.csv`、`args.yaml`、`results.png` |
| 评测结果 | `reports/eval_metrics.json`、`reports/eval_report.md` |
| 真实图片推理结果 | `reports/real_image_infer.json`、`reports/real_image_check.md` |
| 模型输出接口定义 | `reports/model_output_contract.md` |
| 错误案例分析 | `reports/error_analysis.md`、`reports/error_cases.csv` |
| 模型使用说明 | `reports/README_usage.md` |

复现命令：
```bash
python scripts/pretrain_check.py
python scripts/train_models.py        # 或 python scripts/train_det_only.py（断网）
python scripts/evaluate.py
python scripts/real_image_check.py
python scripts/error_analysis.py
python scripts/infer.py --model models/det10/weights/best.pt --source <图片或目录>
```

---

## 6. 验收对照

| 验收项 | 目标 | 实测 | 结论 |
|---|---|---|---|
| PRD MI-01 Top-3 准确率 | ≥85% | 99.60%（真实图片 500 张） | ✅ 通过 |
| 检测 mAP@0.5 | 无硬指标 | 0.8902（合成域） | ⚠️ 参考值，真实域见下 |
| 检测真实域可用性 | 无硬指标 | segreal_food1（3,932 真实照片）AP50=0.1511，多实例 AP50=0.0003 | ❌ 多菜品不可用，详见 reports/segreal_eval_report.md（已修正早期"定位可外推"的宽松口径） |
| PRD MI-03 P95 ≤5s | ≤5s | 模型侧 59.2 ms | ✅ 通过（端到端另见工作包 C） |
| 真实测试图片推理 | 必须提供 | `reports/real_image_infer.json`（500 张逐图） | ✅ 提供 |
| 错误案例分析 | 必须提供 | `reports/error_analysis.md` + 339 条错例 | ✅ 提供 |

---

## 7. 已知问题（不掩饰）

1. **检测训练数据是合成的**：工作区内不存在真实多菜品标注数据。合成域 mAP 不能直接外推，
   真实域检测模型的**正式验收基准仍缺**（需人工标注真实多菜品照片 ≥200 张）。
2. **仅 10 类**：351 类中覆盖 2.8%，其余类别当前无法识别（会走 `status=empty` + 人工录入分支）。
3. **检测模型分类能力弱于分类模型**（79.6% vs 93.4%），生产上建议"检测定位 + 裁剪后分类器识别"两级串联。
4. **`DFoodTJ-Seg`（带 mask 的分割子集）工作区内缺失**，无法做基于分割的份量估计。
5. 纯 CPU 训练限制了规模：imgsz 416 / 25 轮 / 10 类；若有 GPU 可显著扩类与提分辨率。

## 8. 待人工决策

1. 是否投入人力标注**真实多菜品照片**（决定检测模型能否有真实验收基准）。
2. 10 类高频清单是否符合业务预期，是否需要扩到 50/100 类。
3. `DFoodTJ-Seg` 是否需要补获（影响后续"按面积估重量"能力）。
4. DFoodTJ 数据集许可条款核实（Science Databank 条目页）。
