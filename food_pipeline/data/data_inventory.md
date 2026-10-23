# 数据盘点报告（A1）— data_inventory.md

生成时间：2026-10-23　盘点方式：**逐文件实测**（解压抽样、解析压缩包目录、解析文档原文），非依据论文摘要推断。

---

## 1. 资源清单

### 1.1 `D:/workbuddy/kkk/DFoodTJ-Nutr/density.xlsx`
| 项 | 实测 |
|---|---|
| 路径/格式/大小 | `D:/workbuddy/kkk/DFoodTJ-Nutr/density.xlsx`，xlsx，51 KB |
| 来源与许可 | 论文《Chinese Food Images for Full Cycle Nutrition Analysis Towards Diabetes Management》(Scientific Data 2026, 13:975, doi:10.1038/s41597-026-07334-9)；数据发布于 Science Databank doi:10.57760/sciencedb.28012。**许可待核实**（Science Databank 条目页未在本地核验，通常为 CC BY 4.0，需人工确认） |
| 内容 | 351 行 × 14 列：Food ID(0–350)、中英文名、密度(g/ml)、碳水/脂肪/蛋白/纤维的质量密度(g/g)与体积密度(g/ml)、能量密度(kcal/g 与 kcal/ml) |
| 营养字段与单位 | 质量口径 g/g（即每 1 g 食物所含克数，×100 = 每 100g）、能量 kcal/g；体积口径 g/ml、kcal/ml |
| 数据质量 | 无缺失、无负值；fat=0 共 2 条（鸡蛋/海参，属实）、fiber=0 共 49 条（属实）；能量与 Atwater 估算偏差 >20% 共 33 条（属实测值特例，仅提示） |
| 适用性 | **营养库主数据源，直接可用**。Food ID 与 DFoodTJ-Rec 类别 ID 一一对应（已核验 0..350 连续无重复） |

### 1.2 `D:/专业实训/DFoodTJ-Rec.zip`
| 项 | 实测 |
|---|---|
| 路径/格式/大小 | `D:/专业实训/DFoodTJ-Rec.zip`，zip，**19.24 GB**（19243155625 B） |
| 内部结构 | `DFoodTJ-Rec/{train,val,test}/{000..350}/xxxxxx.png` + `DFoodTJ-Rec/truth_list/{train,val,test}_list.txt` |
| 图像数量 | **284,933 张 PNG**（train 224,784 / val 31,848 / test 28,301，与 truth_list 逐行核对一致；论文宣称 284,933 一致） |
| 类别数量 | **351 类中餐**（文件夹 000–350，类别 ID 与 density.xlsx Food ID 对齐） |
| 标注类型 | **图像级分类标签**（`路径 类别ID`），**无边界框、无分割 mask** |
| 图像形态 | 抽样 9 张实测：真实实拍中餐，餐盘/桌面场景，单菜品为主体；部分带"大众点评"水印；分辨率 ~256px 短边 |
| 训练适用性 | ✅ 分类任务（YOLOv8-cls / ResNet 等直接可用）；❌ **不可直接用于 YOLOv8 检测或分割**（无框） |
| 已知问题 | 类别不均衡（261–1669 张/类）；含水印图片；论文称来源 ChineseFoodNet、Food2K、Internet —— **互联网抓取部分的再分发许可需人工确认** |

### 1.3 `D:/专业实训/food-test.v1i.yolov8`
| 项 | 实测 |
|---|---|
| 路径/格式/大小 | Roboflow 导出 YOLOv8 格式，train 6949 / valid 1633 / test 890 = **9472 图**，图-标 1:1 对应 |
| 类别数量 | 100 类，`data.yaml` 中 `nc:100` |
| **类别语言** | **全部为日餐/西餐类名**（Japanese-style-pancake, miso-soup, sushi, tempura, ramen-noodle, sukiyaki, oden…）— 与 UEC-Food100 类目一致，**非中餐** |
| **标注实测** | 9472 个标签文件共 **9472 个目标框（平均 1.0 框/图）**，且框尺寸普遍接近全图（例：cx=0.40, cy=0.51, w=0.73, h=0.96）；无分割多边形 |
| 结论 | **名义检测集，实为"全图单框"的分类集**。① 不支持"一图多食物"检测需求；② 类别与项目"中餐"要求冲突；③ 框无定位信息价值 |
| 许可 | README.roboflow.txt 标注 **CC BY 4.0**（已核实，Roboflow 导出说明） |
| 适用性 | 仅可作为"跑通 YOLOv8 检测流程"的对照基线，**不得作为项目主检测数据源** |

### 1.4 `D:/专业实训/FoodData_Central_foundation_food_csv_2026-04-30`
| 项 | 实测 |
|---|---|
| 内容 | USDA FoodData Central **Foundation Foods** 全套 26 个 CSV（food.csv 7.2MB、food_nutrient.csv 10.1MB、food_portion.csv 等） |
| 用途 | 食材级营养补充源（英文、以西式/原料食品为主），可用于工作包 C 的补充查询与交叉校验 |
| 许可 | 美国农业部公有领域数据（无使用限制） |
| 已知限制 | 仅 Foundation Foods 子集（约数百条食材），**不含中餐成品菜**；单位为 USDA 口径（per 100g） |

### 1.5 文档
| 文件 | 大小 | 关键内容（已解析原文） |
|---|---|---|
| `AI饮食记录营养分析助手项目任务书V1.0.0.docx` | 23 KB | 技术栈 Python3.12+/PyTorch+YOLOv8/USDA/LangGraph/FastAPI/React/sqlite3；量化指标：常见菜品 Top-3≥85%、热量偏差≤15%、端到端 P95≤5s、报表一致率 100%；数据 8:1:1 |
| `AI饮食记录营养分析助手_网站开发PRD.docx` (V1.4) | 365 KB | MI-01 **Top-3 口径：10 类高频菜品、测试集≥200 张、逐张人工评测、前 3 候选命中即计**；表 4-1 BMR/TDEE/目标热量与营养素比例；表 4-2 预警规则 AL-01~AL-05；表 7-4 数据字典 |
| `DFood-TJ 论文.pdf` | 3.99 MB | 数据集构成、来源、基准（Rec: ResNet50 top-1 76.57%/top-5 94.35%；Seg: IoU 0.874） |

---

## 2. 关键矛盾与影响（约束第 7 条）

| # | 矛盾 | 影响 | 处理 |
|---|---|---|---|
| 1 | 项目要求"中餐 + 一图多食物 + 检测"，但 **本地无任何真实中餐多目标检测标注**（food-test 为日餐全图单框；DFoodTJ-Rec 为纯分类） | 工作包 B 无法用现有标注直接训练检测模型 | **经确认采用合成方案**：从 DFoodTJ-Rec 单菜图合成多菜品图（贴图位置已知→框真值），明确标注为合成数据，并在真实图上评估域差距 |
| 2 | PRD MI-01 为 **Top-3 分类指标**（10 类高频），与 YOLOv8 检测 mAP 是不同口径 | 不能混报 | 拆分为两个模型：YOLOv8n-cls（Top-3 口径）+ YOLOv8n-det（多菜品定位），分别按各自口径评测 |
| 3 | 本机 **无 NVIDIA GPU**（Intel Iris Xe 核显 / i7-1360P / 16GB RAM） | 训练规模受限 | 经确认采用 **10 类高频试点**：cls 每类 ≤400 训练图；det 合成集 2000 张 |
| 4 | 任务书写数据 8:1:1；food-test 实际 73/17/9.4；DFoodTJ-Rec 为 8:1:1（224784/31848/28301 ✓） | food-test 不符合任务书口径 | 合成检测集按 **8:1:1** 生成；分类沿用 DFoodTJ-Rec 原生 8:1:1 |
| 5 | 论文含 **DFoodTJ-Seg**（3932 图、187 类、带 mask），**工作区缺失** | 无法做分割训练 | 标记为缺口；如需分割能力须另行获取 |
| 6 | USDA 仅 Foundation Foods，不含中餐成品菜 | 中餐营养以 density.xlsx 为主，USDA 仅作食材级补充 | 在营养库中按来源分列，不混用口径 |

---

## 3. 尚需人工确认的事项

1. DFoodTJ-Rec（尤其 Internet 抓取子集）与 density.xlsx 的**最终再分发许可**——需到 Science Databank 条目页核对（本机未联网核验该页）。
2. DFoodTJ-Seg 是否需要另行下载（若项目后续要做分割/更精细份量估算）。
3. food-test.v1i.yolov8 若保留，仅作流程对照，不进入项目验收指标。
4. 10 类高频菜品清单是否需要按实际业务调整（当前清单见 `class_mapping.csv` tier=1）。
