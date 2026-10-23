# 模型输出契约（B4）— model_output_contract.md

## 1. 契约总则
- **坐标系**：`bbox_xyxy` 为**原始图像像素坐标**（左上原点，x 向右、y 向下），非 YOLO 归一化坐标。
- **数据类型**：坐标与置信度为 `float`（保留 4 位小数）；ID 为 `int`；名称为 `str`（UTF-8 中文）。
- **单次推理只返回一个 JSON 对象**；字段恒在（无数据时为 `null` 或空数组），不做字段省略。

## 2. 结构定义

```json
{
  "image_id": "test_00042",
  "model_version": "det10-v1-epoch25",
  "task_type": "detection",
  "image_width": 640,
  "image_height": 640,
  "detections": [
    {"class_id": 3,
     "food_name": "红烧肉",
     "food_id": 83,
     "confidence": 0.8731,
     "bbox_xyxy": [182.0, 210.5, 401.0, 428.0]}
  ],
  "status": "ok",
  "warnings": []
}
```

### 字段说明
| 字段 | 类型 | 说明 |
|---|---|---|
| image_id | str | 调用方传入的图片标识（文件名去扩展名 / UUID） |
| model_version | str | 模型标识 + 权重 epoch，用于结果追溯 |
| task_type | str | `"detection"` 或 `"classification"` |
| image_width / image_height | int | 推理所用原图尺寸 |
| detections | list | 按置信度降序；空检测时为 `[]` |
| detections[].class_id | int | 模型输出类别索引（det/cls 各自 0..9） |
| detections[].food_id | int | **映射回 DFoodTJ 351 类标准 ID**（经 `class_mapping.csv`），供营养查询直接使用 |
| detections[].food_name | str | 中文菜名（来自营养库） |
| detections[].confidence | float | 0..1 |
| detections[].bbox_xyxy | list[float] | `[x1,y1,x2,y2]` 像素坐标；classification 任务无此字段（置 null） |
| status | str | `ok` / `empty` / `low_confidence` / `error` |
| warnings | list[str] | 低置信、未收录、异常提示 |

## 3. 边界与错误处理
| 场景 | 行为 |
|---|---|
| 零检测 | `detections=[]`，`status="empty"`，warnings 提示"未检出已收录菜品，建议人工录入" |
| 置信度 0.3–0.6 | 保留该检测，`status="low_confidence"`，warnings 注明该子项"建议人工复核"（对齐 PRD 4.4） |
| 置信度 < 0.3 | 丢弃该框，warnings 提示"存在低置信区域，建议人工录入" |
| 图片读取失败 | `status="error"`，detections=[]，warnings 给出原因；**不抛未捕获异常** |
| 类别未在营养库 | 不会发生（模型类别即来自营养库 ID），防御性检查保留 |

## 4. 关键约束（与工作包 C 衔接）
- **检测框 ≠ 重量**。bbox 面积/像素数**不得**直接换算为克数；重量必须来自：
  1) 用户输入（user_input）；2) 份量参考（portion_reference）；3) 独立估算模块（model_estimate，需标注非称重）。
- 检测结果只提供 `food_id` 候选清单 + 置信度，供上层确认修正后进入营养计算。

## 5. 推理入口
```bash
python scripts/infer.py --model models/det10/weights/best.pt --source <图片或目录> [--conf 0.25]
python scripts/infer.py --model models/cls10/weights/best.pt --source <图片> --task classification
```
输出：控制台 JSON + `reports/infer_results.json`（批量时）。
