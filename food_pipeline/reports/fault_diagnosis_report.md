# 业务链路故障定位报告（第一阶段 · 只读审计）

- 审计时间：2026-10-23 18:39
- 审计范围：任务书第 2/3/4 项（食物识别 → 营养数据查询与计算 → 营养分析与建议）的真实调用链；
  **前端整体、后端 API 路由与路径、用户管理、日志统计、系统联调不在本次修改范围内**
- 审计方式：只读。未修改任何被审文件；全部结论来自实际发出的 HTTP 请求与落盘的原始响应
- 证据目录：`reports/_evidence/`（E1–E9 场景原始 JSON / HTTP 报文）

> **状态更新**：第二阶段最小范围修复已完成，缺陷 D1–D10 全部处理；
> 9 个端到端场景断言与前端渲染检查全部 PASS，修复前后响应字段集合 **DIFF=0**。
> 修改清单与前后差异见 `reports/fix_list.md`；验收记录见 `reports/e2e_acceptance.md`；
> 契约核对见 `reports/contract_check.md`。
- 被测服务：`http://127.0.0.1:8765`（`web/serve.py`，模型与营养库 `ready=true`）

---

## 1. 业务链路各环节实际状态

| # | 环节 | 代码位置 | 实测状态 | 结论 |
|---|---|---|---|---|
| 1 | 图片上传（前端 → `/api/analyze`） | `web/index.html:251 run()` / `web/serve.py:290 do_POST` | 请求能发出，后端能收到；参数 `image_b64`（dataURL 或裸 base64 均可） | ✅ 正常 |
| 2 | 文件解码 | `web/serve.py:105 Image.open(path).size` | 合法图正常；**非法文件抛 `UnidentifiedImageError` 冒泡** | ❌ 缺陷 D2 |
| 3 | 食物识别（检测 det10-v1） | `scripts/infer.py:31 infer_image()` | 真实红烧肉 conf=0.976、合成多菜图 2 目标（米饭 0.921 / 麻婆豆腐 0.780），非食物图 `status=empty` | ✅ 真实执行 |
| 4 | 食物识别（分类 cls10-v1） | `web/serve.py:124-133` | 红烧肉 prob=1.000；非食物图 top1=0.201 → `status=empty` | ✅ 真实执行 |
| 5 | 类别 → 营养库映射 | `scripts/infer.py:15 load_class_mapping()` | `class_id 3 → food_id 83`，映射正确、非字符串模糊匹配 | ✅ 正常 |
| 6 | 营养数据查询 | `nutrition/db.py NutritionDB.get()` | 351 条命中；`food_id=999` 抛 `FoodNotFoundError`（正确行为） | ✅ 正常 |
| 7 | 营养计算 | `nutrition/calculator.py calc_item/calc_meal` | `per_100g × weight_g / 100`，红烧肉 150 g → 430.49 kcal，与手算一致 | ✅ 正常 |
| 8 | 重量来源 | `WeightSource` 三态 | `user_input` / `portion_reference` 均正确落为字符串；**未使用置信度或框面积当重量** | ✅ 合规 |
| 9 | 目标与预警 | `nutrition/advisor.py` | BMR 1648.8 / TDEE 2555.6 / 目标 2172.2；日摄入 2600 kcal 触发 AL-01（basis 完整） | ✅ 真实执行 |
| 10 | 响应组装 | `web/serve.py:220-234` | 正常场景 10 个顶层字段齐全 | ⚠️ 异常场景整包丢失（D2/D3） |
| 11 | 前端展示 | `web/index.html:345 renderMeal()` | **`t.weight_g.toFixed(0)` 抛 TypeError，中断第 7/8 节渲染** | ❌ 致命 D1 |

---

## 2. 缺陷清单

### D1 · 致命 · 前端读取契约外字段，中断后续渲染
- **位置**：`web/index.html` `renderMeal()` 第 357 行
  ```js
  <div><b>${t.weight_g.toFixed(0)}</b><span>总重 g</span></div>
  ```
- **契约**：`reports/data_field_spec.md:381`（§5.2）明确定义
  `meal.totals = {carb_g, fat_g, protein_g, fiber_g, energy_kcal}` —— **不含 `weight_g`**
- **实测**：`reports/_evidence/E1_real_detected.json`
  `meal.totals` 实际键 = `['carb_g','energy_kcal','fat_g','fiber_g','protein_g']`
- **根因**：`nutrition/calculator.py:152` 组装 `totals` 时未含总重；前端却按"总重"读取 →
  `undefined.toFixed()` → `TypeError` → `run()` 中 `renderMeal()` 之后的 `renderTar()`、`renderAlert()` **不再执行**
- **影响**：这正是"上传图片后看不到完整业务结果"的直接原因——
  第 6 节营养卡渲染到第 6 个 KPI 时中断，**第 7 节「每日目标」与第 8 节「预警」永远停在初始占位文本**，
  且异常被 `fetch().then()` 吞掉，界面顶部状态仍显示"完成"，用户无法察觉出错。
- **运行时硬证据**：本机存在 Node（v22.22.2），已将 `web/index.html` 的 `<script>` 段完整抽出，
  用**真实响应 E1** 按 `run()` 的原始调用顺序 `renderDet → renderCls → renderMeal → renderTar → renderAlert`
  连续执行（无逐个 try），结果如下：
  ```
  !!! 渲染中断: TypeError | Cannot read properties of undefined (reading 'toFixed')
      中断前已完成: renderDet -> renderCls
  第2节 检测结果  : 610 字符
  第3节 分类Top5  : 1638 字符
  第6节 营养计算  : 0 字符      ← 空白
  第7节 每日目标  : 0 字符      ← 空白
  第8节 预警      : 0 字符      ← 空白
  ```
  由于 `run()` 是 `.then(d=>{...}).catch(e=>{...})` 结构，`renderMeal` 抛出的异常会冒泡到 `.catch`，
  **顶部徽章被置为「请求失败」**——用户看到的是"请求失败 + 营养/目标/预警全空"，
  但后端其实返回了完整且正确的 JSON。
- **对照**：E5（无识别结果，`meal=null`）时 `renderMeal` 提前 return，**不触发该 bug**，五节全部渲染成功
  （第 6 节 32 字符"暂无可计算项"）。即：**识别越成功，页面越崩** —— 与用户"上传后看不到完整业务结果"完全吻合。
- 该 harness 已固化为回归测试 `tests/frontend_render_check.js`（第 4 阶段复用）

### D2 · 严重 · 图片解码失败未受控，整条链路返回 HTTP 500
- **位置**：`web/serve.py:105` `W, H = Image.open(path).size`（位于 `try` 内但无 `except`，只有 `finally`）
- **实测**：E3（伪造 PDF 字节）、E4（随机字节）
  → `HTTP 500 {"error": "UnidentifiedImageError: cannot identify image file ..."}`
- **契约要求**：`model_output_contract.md:51` —— 图片读取失败应 `status="error"` + `warnings`，**不抛未捕获异常**
- **影响**：非法文件场景下，识别/营养/分析**全部无输出**，前端只能显示一行 `错误: UnidentifiedImageError...`

### D3 · 严重 · 单项营养缺失拖垮整条链路
- **位置**：`web/serve.py:182-189` 人工补录循环，`calc.calc_item(...)` **无 try/except**
- **实测**：E6（正常红烧肉 + `manual:[{food_id:999,grams:100}]`）
  → `HTTP 500 {"error": "FoodNotFoundError: 'food_id=999 未收录（库范围 0..350）'"}`
- **影响**：本应"识别成功但营养库无记录 → 该项提示缺失、其余正常出结果"，
  实际是**已成功识别的红烧肉的营养、整餐汇总与预警一起丢失**，与任务第 4 点"不得静默返回看似正常的空结果"相悖
- 对比：同文件第 161-168 行对**检测项**的 `calc_item` 已有 try/except，唯独人工补录项遗漏 —— 属调用遗漏型缺陷

### D4 · 中 · 估算局限提示未上屏
- **位置**：`web/index.html:299-318 renderDet()` 只显示 `weight_source` 标签，未显示 `it.warnings`
- **实测**：`items[0].warnings = ["重量按份量参考 1份=150.0g × 1.0 折算，非称重值"]`（E1）
- **影响**：任务第 4 点要求"如实报告重量和营养总量的估算局限"，该提示在界面上不可见

### D5 · 中 · 无有效识别结果时静默
- **实测**：E5（纯灰非食物图）→ `items=[]`、`meal=null`、`alerts=[]`，
  前端第 6 节仅"暂无可计算项"、第 8 节"未触发任何预警规则"
- **影响**：未区分"识别失败导致无结果"与"已识别但确实无预警"，属"看似正常的空结果"

### D6 · 中 · `already_fired` 跨图片残留，预警被永久抑制
- **位置**：`web/index.html:244 payload()` 每次回传 `(LAST?.alerts||[]).map(a=>a.code)`；
  上传新图时 `handle()` 未重置 `LAST`
- **实测**（本次执行）：
  ```
  第1次（already_fired=[]）        → alerts: ['AL-01']
  第2次（already_fired=['AL-01']） → alerts: []        ← 换图后预警消失
  第3次（already_fired=[]）        → alerts: ['AL-01']
  ```
- **影响**：只要某张图触发过 AL-01，之后**任何**图片都不再显示该预警，用户会认为"预警功能坏了"

### D7 · 低 · 重量输入 0 被静默降级
- **位置**：`web/serve.py:156` `if w and w.get("grams")` —— `0` 为 falsy
- **实测**：`weights={"83":{"grams":0}}` → 静默按份量参考 150 g 计算，无任何提示

### D8 · 低 · 资源未释放（第四阶段处理）
- `scripts/infer.py:33` `Image.open(path)` 未 `close()`
- `web/serve.py:67` 为取原始宽度**重复打开**图片；`:74 base`、`:107 im0` 均未关闭

### D9 · 低 · 代码质量（第四阶段处理）
- `scripts/infer.py:64` `zip(top5_idx := top, ...)` —— walrus 赋值 `top5_idx` 后续未使用

### D10 · 低 · 可观测性缺失（第四阶段处理）
- 无请求标识、无阶段耗时/成败日志，故障无法回溯；当前仅 `log_message` 输出访问行

---

## 3. 根因归纳：为什么"上传后看不到完整业务结果"

```
上传图片
  └─ 识别成功（真实执行）→ 营养查询/计算成功（真实数据）→ 目标与预警成功（真实规则）
       └─ 响应 JSON 完整（10 个顶层字段齐全）
            └─ 前端 renderMeal() 读 t.weight_g（契约外字段）
                 └─ TypeError → renderTar() / renderAlert() 未执行
                      └─ 用户看到：有菜名和营养卡，但没有"每日目标"和"预警"
```

**即：后端链路真实可用，故障发生在前端渲染层的字段取值越界。**
另有两条放大路径：切换图片后 `already_fired` 残留（D6）让预警区二次变空；
异常路径（D2/D3）直接 500，让**整包**结果消失。

---

## 4. 计划修改的文件与必要性

**接口契约保持不变**（路径、HTTP 方法、请求参数名、响应字段名、类型、嵌套、枚举值均不动）：

| 文件 | 修改项 | 必要性 | 是否触碰契约 |
|---|---|---|---|
| `web/index.html` | 总重改由 `meal.items` 汇总（契约内字段）+ `||0` 兜底 | 消除 D1 致命中断 | 否（仅改取值来源） |
| `web/index.html` | 切换/上传图片时重置 `LAST`，使 `already_fired` 不跨图 | 消除 D6 | 否 |
| `web/index.html` | 展示 `item.warnings`；无识别结果时显式提示；`image_b64` 为空时不切换视图 | 消除 D4/D5/D2 衍生 | 否 |
| `web/serve.py` | 识别阶段受控异常处理 → `status="error"` + `warnings`，HTTP 200 且字段恒在 | 消除 D2，对齐契约 §3 | 否（status/warnings 为契约既有字段） |
| `web/serve.py` | 人工补录项逐项 try/except，失败项以 `status="error"` 入 `items`，其余照常出结果 | 消除 D3 | 否（复用既有字段） |
| `web/serve.py` | `grams=0` 视为未提供并写入 warning，不再静默降级 | 消除 D7 | 否（仅 warnings 内容） |
| `scripts/infer.py` | 图片句柄释放、删除无用 walrus | 消除 D8/D9 | 否 |
| `web/serve.py` | 请求标识 + 阶段耗时日志（不含敏感信息） | 消除 D10 | 否 |
| `web/serve.py` | 释放重复打开的 Image | 消除 D8 | 否 |

**不修改**：`/api/analyze` 路径与 POST 方法；请求参数 `image_b64 / weights / manual / already_fired / profile / day_totals`；
响应字段 `meta / image_b64 / orig_b64 / detection / fallback / classification / items / meal / targets / alerts` 及其嵌套字段名与类型；
`WeightSource` 三态枚举、`status` 枚举、`AL-01~AL-05` 规则与阈值；营养库表结构与数据。

---

## 5. 真实可用 / 尚未实现 / 无法验证

**真实可用（有实测证据）**
- 检测与分类模型真实加载并推理（best.pt，非占位）；`class_id → food_id` 映射正确
- 营养库 351 条真实查询；`per_100g × weight / 100` 计算与手算一致
- 目标（Mifflin-St Jeor）与预警（AL-01 实测触发，basis 完整）由规则真实生成
- 重量三态标签正确；未用置信度/框面积冒充重量
- 单测：`tests/test_nutrition.py` 38 项通过

**尚未实现 / 受限（非缺陷，需人工决策）**
- 检测模型为合成数据训练：真实照片检出率 93.8%、主框类别正确率 79.6%（`reports/real_image_check.md`）
- 仅覆盖 351 类中的 10 类；其余走人工补录
- 无真实重量估算模块（`model_estimate` 路径未启用），份量参考为 `reference_only` 未校准
- 无真实多菜品人工标注，检测模型无真实验收基准

**无法验证**
- 浏览器运行时 JS 报错栈（无 Node / 浏览器自动化环境）——D1 结论由契约比对 + 响应字段实测推出，修复后以契约一致性测试回归
- 前端截图/录屏：本次未采集

---

## 6. 兼容性风险

- 本次全部修改为**取值与异常路径**修复，不增删响应字段，前端其他模块与后端契约无兼容风险
- D2 修复后，非法文件从「HTTP 500」变为「HTTP 200 + `status=error`」：
  **HTTP 状态码语义发生变化**。若前端/其他调用方依赖 500 判定失败，需同步确认；
  当前前端 `run()` 已按 `d.error` 分支处理，且新响应不含顶层 `error`，
  将由 `detection.status="error"` 走既有"未检出"提示分支，无兼容问题
