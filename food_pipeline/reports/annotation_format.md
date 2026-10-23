# 标注文件与格式说明

## 1. det10（合成检测集，YOLOv8 目标检测格式）

```
datasets/det10/
├── data.yaml
├── train/{images,labels}/   1600 图
├── val/{images,labels}/       200 图
└── test/{images,labels}/      200 图
```

**data.yaml**：`nc: 10`，names 顺序 = `[米饭, 馒头, 饺子, 红烧肉, 青椒肉丝, 西红柿炒鸡蛋, 清蒸鲈鱼, 麻婆豆腐, 蚝油西兰花, 冬瓜汤]`（class_id 0..9）。

**labels/*.txt**：每行一个目标，YOLO 归一化格式
```
<class_id> <cx> <cy> <w> <h>      # 均为 0..1 归一化，cx/cy 为框中心
```
- 平均目标数 2.1/图；1–4 目标/图；无空标签文件
- **真值来源**：程序粘贴坐标（非人工标注），逐图参数见 `datasets/det10_synth_manifest.csv`
- 图像：640×640 JPG（quality=90），背景为程序化桌面渐变，目标为 DFoodTJ-Rec 真实菜品图（随机缩放 26–46%、±15° 旋转）

**类别 ID 映射**：det class_id ↔ DFoodTJ 标准 food_id
```
0→0(米饭) 1→22(馒头) 2→70(饺子) 3→83(红烧肉) 4→37(青椒肉丝)
5→40(西红柿炒鸡蛋) 6→66(清蒸鲈鱼) 7→82(麻婆豆腐) 8→136(蚝油西兰花) 9→74(冬瓜汤)
```

## 2. cls10（分类集，YOLOv8-cls 目录约定）

```
datasets/cls10/
├── train/<idx>_<中文名>/…   每类 400 张
├── val/<idx>_<中文名>/…     每类  50 张
└── test/<idx>_<中文名>/…    每类  50 张
```
- 类别索引即目录名前缀（0..9），与 det 相同的 food_id 映射
- 源图来自 DFoodTJ-Rec 官方 train/val/test 划分（`cls10_split_manifest.csv` 逐图可追溯），**无跨 split 泄漏**

## 3. 原始数据格式参考
- **DFoodTJ-Rec**：`<split>/<类别3位ID>/<序号>.png` + `truth_list/<split>_list.txt`（每行 `相对路径 类别ID`）
- **food-test.v1i.yolov8**：Roboflow YOLOv8 导出（`images/` + `labels/`，每图 1 个近全图框，类别为日餐 100 类——不作为本项目训练数据）

## 4. 转换与复现
```bash
python scripts/extract_subset.py           # 1. 按 split 解压 10 类源图
python scripts/prepare_cls_dataset.py      # 2. 生成 cls10
python scripts/synthesize_det_dataset.py   # 3. 合成 det10（seed=20261023）
python scripts/build_nutrition_db.py       # 4. 营养库
```
