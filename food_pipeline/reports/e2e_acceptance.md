# 端到端验收记录（第三阶段 · 真实图片）

- 执行时间：2026-10-23 19:06:34
- 被测服务：`http://127.0.0.1:8765`（`web/serve.py`，CPU）
- 模型：`models/det10/weights/best.pt`（det10-v1）、`models/cls10/weights/best.pt`（cls10-v1）
- 营养库：`data/nutrition_clean.csv`（351 条，DFoodTJ-Nutr）
- 方法：脚本 `scripts/e2e_acceptance.py` 实际发 HTTP 请求；前端渲染由 `tests/frontend_render_check.js` 用真实响应驱动页面真实函数验证
- 原始响应：`reports/_evidence/T*.json`（未加工）

## 1. 汇总

| 场景 | 说明 | HTTP | 后端断言 | 前端渲染 |
|---|---|---|---|---|
| T1 | 正常上传：真实照片·红烧肉（项目支持类别） | 200 | PASS | PASS |
| T2 | 多菜品图片（合成多菜品图；真实多菜品人工标注缺失） | 200 | PASS | PASS |
| T3 | 不支持的文件格式（伪造 PDF 字节） | 200 | PASS | PASS |
| T4 | 无效文件（随机字节） | 200 | PASS | PASS |
| T5 | 无法识别/无有效检测结果（纯灰非食物图） | 200 | PASS | PASS |
| T6 | 识别成功但营养库无对应记录（人工补录 food_id=999） | 200 | PASS | PASS |
| T7 | 缺少重量/份量信息（不传 weights） | 200 | PASS | PASS |
| T8 | 分析环节异常（非法活动量枚举） | 200 | PASS | PASS |
| T9 | 预警频控：already_fired 生效且不在新请求中残留 | 200 | PASS | PASS |

后端断言 9/9 通过；前端渲染 9/9 通过。

## 2. 逐场景记录

### T1 · 正常上传：真实照片·红烧肉（项目支持类别）

- **输入**：datasets/cls10/test/3_红烧肉/083_test_000003.png（341×256 真实照片）
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 249640 字符
- **预期**：HTTP 200；检出红烧肉；产出营养、每日目标；五节全部渲染
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：120.8 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][29699eed] decode              3.4ms OK    341x256
  [analyze][29699eed] detect             44.9ms ok    1框:红烧肉0.98
  [analyze][29699eed] classify           11.1ms ok    5候选:红烧肉1.00
  [analyze][29699eed] nutrition[0]        0.0ms OK    food_id=83 150.0g src=portion_reference
  [analyze][29699eed] targets+alerts      0.0ms OK    alerts=0
  [analyze][29699eed] TOTAL              81.0ms OK    items=1 meal=有 alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 1,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 83,
   "food_name": "红烧肉",
   "status": "ok",
   "weight_g": 150.0,
   "weight_source": "portion_reference",
   "energy_kcal": 430.49,
   "warnings": [
    "重量按份量参考 1份=150.0g × 1.0 折算，非称重值"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 5.07,
  "fat_g": 79.19,
  "protein_g": 12.91,
  "fiber_g": 0.82,
  "energy_kcal": 430.49
 },
 "meal.warnings": [],
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T1.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T1.json ---
    第2节 检测结果: 694 字符
    第3节 分类Top5: 1638 字符
    第6节 营养计算: 861 字符
    第7节 每日目标: 304 字符
    第8节 预警: 35 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T2 · 多菜品图片（合成多菜品图；真实多菜品人工标注缺失）

- **输入**：datasets/det10/test/images/test_00000.jpg（640×640，含米饭+麻婆豆腐）
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 71420 字符
- **预期**：HTTP 200；检出 ≥2 个目标；整餐汇总包含全部检出项
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：383.5 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][5d527d40] decode              3.2ms OK    640x640
  [analyze][5d527d40] detect            228.7ms ok    2框:米饭0.92,麻婆豆腐0.78
  [analyze][5d527d40] classify           15.6ms low_confidence 5候选:馒头0.34
  [analyze][5d527d40] nutrition[0]        0.0ms OK    food_id=0 200.0g src=portion_reference
  [analyze][5d527d40] nutrition[1]        0.0ms OK    food_id=82 200.0g src=portion_reference
  [analyze][5d527d40] targets+alerts      0.0ms OK    alerts=0
  [analyze][5d527d40] TOTAL             333.9ms OK    items=2 meal=有 alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 2,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 0,
   "food_name": "米饭",
   "status": "ok",
   "weight_g": 200.0,
   "weight_source": "portion_reference",
   "energy_kcal": 232.0,
   "warnings": [
    "重量按份量参考 1碗=200.0g × 1.0 折算，非称重值"
   ]
  },
  {
   "food_id": 82,
   "food_name": "麻婆豆腐",
   "status": "ok",
   "weight_g": 200.0,
   "weight_source": "portion_reference",
   "energy_kcal": 305.66,
   "warnings": [
    "重量按份量参考 1份=200.0g × 1.0 折算，非称重值"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 63.54,
  "fat_g": 24.04,
  "protein_g": 19.06,
  "fiber_g": 0.88,
  "energy_kcal": 537.66
 },
 "meal.warnings": [],
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T2.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T2.json ---
    第2节 检测结果: 1166 字符
    第3节 分类Top5: 1646 字符
    第6节 营养计算: 879 字符
    第7节 每日目标: 304 字符
    第8节 预警: 35 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T3 · 不支持的文件格式（伪造 PDF 字节）

- **输入**：base64(b'%PDF-1.4\nfake pdf')
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 24 字符
- **预期**：HTTP 200（不再 500）；detection.status=error 且 warnings 有原因；字段恒在
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：7.2 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][1b1ff990] decode              3.6ms FAIL  UnidentifiedImageError
  [analyze][1b1ff990] targets+alerts      0.0ms OK    alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "error",
 "detection.n": 0,
 "detection.warnings": [
  "图片读取失败：UnidentifiedImageError: cannot identify image file 'C:\\\\Users\\\\29820\\\\AppData\\\\Local\\\\Temp\\\\tmpu151pz9b.jpg'（请上传 jpg/png 等有效图片文件）"
 ],
 "items": [],
 "meal.totals": null,
 "meal.warnings": null,
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T3.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T3.json ---
    第2节 检测结果: 339 字符
    第3节 分类Top5: 148 字符
    第6节 营养计算: 125 字符
    第7节 每日目标: 304 字符
    第8节 预警: 54 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T4 · 无效文件（随机字节）

- **输入**：base64(os.urandom(64))
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 88 字符
- **预期**：同 T3：受控失败，不抛未捕获异常
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：10.5 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][9a18fffc] decode              3.4ms FAIL  UnidentifiedImageError
  [analyze][9a18fffc] targets+alerts      0.0ms OK    alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "error",
 "detection.n": 0,
 "detection.warnings": [
  "图片读取失败：UnidentifiedImageError: cannot identify image file 'C:\\\\Users\\\\29820\\\\AppData\\\\Local\\\\Temp\\\\tmphwxmu8kr.jpg'（请上传 jpg/png 等有效图片文件）"
 ],
 "items": [],
 "meal.totals": null,
 "meal.warnings": null,
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T4.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T4.json ---
    第2节 检测结果: 339 字符
    第3节 分类Top5: 148 字符
    第6节 营养计算: 125 字符
    第7节 每日目标: 304 字符
    第8节 预警: 54 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T5 · 无法识别/无有效检测结果（纯灰非食物图）

- **输入**：480×480 纯灰 JPEG
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 5636 字符
- **预期**：HTTP 200；status=empty；items=[]、meal=null 且前端显式提示（不静默）
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：77.2 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][0f16b923] decode              2.6ms OK    480x480
  [analyze][0f16b923] detect             41.4ms empty 0框:
  [analyze][0f16b923] classify           12.6ms empty 5候选:饺子0.20
  [analyze][0f16b923] targets+alerts      0.0ms OK    alerts=0
  [analyze][0f16b923] TOTAL              73.2ms OK    items=0 meal=无 alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "empty",
 "detection.n": 0,
 "detection.warnings": [
  "未检出已收录菜品，建议人工录入"
 ],
 "items": [],
 "meal.totals": null,
 "meal.warnings": null,
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T5.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T5.json ---
    第2节 检测结果: 218 字符
    第3节 分类Top5: 1639 字符
    第6节 营养计算: 125 字符
    第7节 每日目标: 304 字符
    第8节 预警: 54 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T6 · 识别成功但营养库无对应记录（人工补录 food_id=999）

- **输入**：datasets/cls10/test/3_红烧肉/083_test_000003.png + manual:[{food_id:999, grams:100}]
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'manual', 'profile']`，`image_b64` 长度 249640 字符
- **预期**：HTTP 200（不再整体 500）；该项 status=error 且给出原因；已识别的红烧肉营养照常产出
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：369.3 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][94712bca] decode              4.5ms OK    341x256
  [analyze][94712bca] detect            155.0ms ok    1框:红烧肉0.98
  [analyze][94712bca] classify           72.6ms ok    5候选:红烧肉1.00
  [analyze][94712bca] nutrition[0]        0.0ms OK    food_id=83 150.0g src=portion_reference
  [analyze][94712bca] manual[0]           0.0ms FAIL  food_id=999 FoodNotFoundError
  [analyze][94712bca] targets+alerts      0.0ms OK    alerts=0
  [analyze][94712bca] TOTAL             360.7ms OK    items=2 meal=有 alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 1,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 83,
   "food_name": "红烧肉",
   "status": "ok",
   "weight_g": 150.0,
   "weight_source": "portion_reference",
   "energy_kcal": 430.49,
   "warnings": [
    "重量按份量参考 1份=150.0g × 1.0 折算，非称重值"
   ]
  },
  {
   "food_id": 999,
   "food_name": null,
   "status": "error",
   "weight_g": 100.0,
   "weight_source": "user_input",
   "energy_kcal": null,
   "warnings": [
    "营养库无此记录或计算失败：FoodNotFoundError: 'food_id=999 未收录（库范围 0..350）'"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 5.07,
  "fat_g": 79.19,
  "protein_g": 12.91,
  "fiber_g": 0.82,
  "energy_kcal": 430.49
 },
 "meal.warnings": [],
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T6.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T6.json ---
    第2节 检测结果: 761 字符
    第3节 分类Top5: 1638 字符
    第6节 营养计算: 861 字符
    第7节 每日目标: 304 字符
    第8节 预警: 35 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T7 · 缺少重量/份量信息（不传 weights）

- **输入**：datasets/cls10/test/3_红烧肉/083_test_000003.png，weights 为空
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 249640 字符
- **预期**：HTTP 200；weight_source=portion_reference；warnings 明确标注非称重值
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：99.6 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][5560af2e] decode              2.9ms OK    341x256
  [analyze][5560af2e] detect             52.5ms ok    1框:红烧肉0.98
  [analyze][5560af2e] classify           12.6ms ok    5候选:红烧肉1.00
  [analyze][5560af2e] nutrition[0]        0.0ms OK    food_id=83 150.0g src=portion_reference
  [analyze][5560af2e] targets+alerts      0.0ms OK    alerts=0
  [analyze][5560af2e] TOTAL              89.1ms OK    items=1 meal=有 alerts=0
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 1,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 83,
   "food_name": "红烧肉",
   "status": "ok",
   "weight_g": 150.0,
   "weight_source": "portion_reference",
   "energy_kcal": 430.49,
   "warnings": [
    "重量按份量参考 1份=150.0g × 1.0 折算，非称重值"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 5.07,
  "fat_g": 79.19,
  "protein_g": 12.91,
  "fiber_g": 0.82,
  "energy_kcal": 430.49
 },
 "meal.warnings": [],
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": []
}
```

- **完整原始响应**：`reports\_evidence\T7.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T7.json ---
    第2节 检测结果: 694 字符
    第3节 分类Top5: 1638 字符
    第6节 营养计算: 861 字符
    第7节 每日目标: 304 字符
    第8节 预警: 35 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T8 · 分析环节异常（非法活动量枚举）

- **输入**：datasets/cls10/test/3_红烧肉/083_test_000003.png，profile.activity='ultra'（非法）
- **请求**：`POST /api/analyze`，body 字段 `['day_totals', 'profile']`，`image_b64` 长度 249640 字符
- **预期**：HTTP 200；识别与营养照常；alerts 含 code=ERR 显式说明分析失败，不静默成功
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：325.7 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][5e4e1349] decode              3.4ms OK    341x256
  [analyze][5e4e1349] detect            253.0ms ok    1框:红烧肉0.98
  [analyze][5e4e1349] classify           42.1ms ok    5候选:红烧肉1.00
  [analyze][5e4e1349] nutrition[0]        0.0ms OK    food_id=83 150.0g src=portion_reference
  [analyze][5e4e1349] targets+alerts      0.0ms FAIL  ValueError: 'ultra' is not a valid ActivityLevel
  [analyze][5e4e1349] TOTAL             315.8ms OK    items=1 meal=有 alerts=1
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 1,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 83,
   "food_name": "红烧肉",
   "status": "ok",
   "weight_g": 150.0,
   "weight_source": "portion_reference",
   "energy_kcal": 430.49,
   "warnings": [
    "重量按份量参考 1份=150.0g × 1.0 折算，非称重值"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 5.07,
  "fat_g": 79.19,
  "protein_g": 12.91,
  "fiber_g": 0.82,
  "energy_kcal": 430.49
 },
 "meal.warnings": [],
 "targets": null,
 "alerts": [
  {
   "code": "ERR",
   "name": "目标/预警计算失败",
   "severity": "info",
   "message": "ValueError: 'ultra' is not a valid ActivityLevel"
  }
 ]
}
```

- **完整原始响应**：`reports\_evidence\T8.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T8.json ---
    第2节 检测结果: 694 字符
    第3节 分类Top5: 1638 字符
    第6节 营养计算: 290 字符
    第7节 每日目标: 33 字符
    第8节 预警: 145 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T9 · 预警频控：already_fired 生效且不在新请求中残留

- **输入**：datasets/cls10/test/3_红烧肉/083_test_000003.png，day_totals=2600kcal；第 1 次 already_fired=[]，第 2 次=['AL-01']，第 3 次=[]
- **请求**：`POST /api/analyze`，body 字段 `['already_fired', 'day_totals', 'profile']`，`image_b64` 长度 249640 字符
- **预期**：第1次触发 AL-01；第2次因去重不重复；第3次（模拟换图后清空）重新触发
- **HTTP**：200｜**后端断言**：PASS｜**耗时**：275.7 ms

- **后端阶段日志证据**（`web/serve.log`）：
```
  [analyze][caab1087] decode              2.8ms OK    341x256
  [analyze][caab1087] detect             83.7ms ok    1框:红烧肉0.98
  [analyze][caab1087] classify           65.6ms ok    5候选:红烧肉1.00
  [analyze][caab1087] nutrition[0]        0.0ms OK    food_id=83 150.0g src=portion_reference
  [analyze][caab1087] targets+alerts      0.0ms OK    alerts=1
  [analyze][caab1087] TOTAL             226.8ms OK    items=1 meal=有 alerts=1
```

- **响应关键字段**：
```json
{
 "detection.status": "ok",
 "detection.n": 1,
 "detection.warnings": [],
 "items": [
  {
   "food_id": 83,
   "food_name": "红烧肉",
   "status": "ok",
   "weight_g": 150.0,
   "weight_source": "portion_reference",
   "energy_kcal": 430.49,
   "warnings": [
    "重量按份量参考 1份=150.0g × 1.0 折算，非称重值"
   ]
  }
 ],
 "meal.totals": {
  "carb_g": 5.07,
  "fat_g": 79.19,
  "protein_g": 12.91,
  "fiber_g": 0.82,
  "energy_kcal": 430.49
 },
 "meal.warnings": [],
 "targets": {
  "bmr": 1648.8,
  "tdee": 2555.6,
  "target_kcal": 2172.2,
  "bmi": 22.9
 },
 "alerts": [
  {
   "code": "AL-01",
   "name": "热量超标",
   "severity": "high",
   "message": "今日热量已达目标的 120%，超出约 428 kcal"
  }
 ]
}
```

- **完整原始响应**：`reports\_evidence\T9.json`
- **前端渲染检查**（`node tests/frontend_render_check.js`）：PASS
```
  --- T9.json ---
    第2节 检测结果: 694 字符
    第3节 分类Top5: 1638 字符
    第6节 营养计算: 861 字符
    第7节 每日目标: 304 字符
    第8节 预警: 144 字符
    结论: PASS
  
  合计 1 个响应，失败 0 个
```

### T9 预警频控追加验证

```
  第1次 already_fired=[]        -> ['AL-01']
  第2次 already_fired=['AL-01'] -> []   (同日去重生效)
  第3次 already_fired=[]        -> ['AL-01']   (换图后 LAST 清空，重新触发)
```

前端修复点：`handle()` / 示例按钮在换图时置 `LAST=null`，`payload()` 的 `already_fired` 不再携带上一张图的预警 code（修复前换图后预警永久消失）。

## 3. 预期与实际的差异

- 全部场景在本次执行中的实际结果见上表与逐场景记录；与预期的差异为：**无**（后端断言与前端渲染均按预期通过的项标记为 PASS）。
- **受限说明**：T2 使用合成多菜品图——工作区内不存在真实多菜品人工标注，真实多菜品场景的检测能力尚无验收基准（`reports/real_image_check.md`：真实单菜品检出率 93.8%、主框类别正确率 79.6%）。
- **未执行项**：浏览器截图/录屏未采集（无浏览器自动化环境）；改用 Node 驱动页面真实渲染函数输出各区块渲染结果作为替代证据。