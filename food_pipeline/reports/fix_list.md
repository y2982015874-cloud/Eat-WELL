# 修改文件清单与逐项说明（第二阶段 · 最小范围修复）

- 执行时间：2026-10-23
- 范围限制：任务书第 2/3/4 项（食物识别 → 营养查询与计算 → 分析与建议）
  **未改动**：API 路径与 HTTP 方法、请求参数名、响应字段名/类型/嵌套、业务枚举值、营养库结构与数据、模型权重
- 验证：9 个端到端场景断言 + 前端渲染检查全部 PASS；57 项单测通过；契约字段集合 DIFF=0

---

## 1. 修改清单

| # | 文件 | 修改项 | 对应缺陷 | 必要性 |
|---|---|---|---|---|
| 1 | `web/index.html` | `renderMeal()` 总重改由 `meal.items` 汇总，并对数值做 `null` 兜底 | **D1（致命）** | 消除 `t.weight_g.toFixed()` TypeError，恢复第 6/7/8 节渲染 |
| 2 | `web/index.html` | `renderMeal()` 无 `meal` 时区分"计算失败"与"无识别结果"两种提示 | D3/D5 | 不允许静默空结果 |
| 3 | `web/index.html` | `renderDet()` 展示 `detection.warnings` 与 `items[].warnings` | D4/D2 | 估算局限与模型提示必须上屏 |
| 4 | `web/index.html` | `renderAlert()` 无预警时区分"无识别结果/未填档案/未触发" | D5 | 避免"看似正常的空结果" |
| 5 | `web/index.html` | `setView()` 后端无图时保留上传预览 | D2 衍生 | 防止 `data:...base64,null` 破图 |
| 6 | `web/index.html` | 换图/点示例时 `LAST=null` | D6 | 修 `already_fired` 跨图残留导致预警永久消失 |
| 7 | `web/serve.py` | 新增 `_log()` / `_meta()` / `_targets_and_alerts()` | D10 + 职责分离 | 可观测性；把"目标与预警"从识别链路中拆出 |
| 8 | `web/serve.py` | 图片解码失败受控 → `status="error"` + `warnings`，HTTP 200 | **D2（严重）** | 契约 §3 要求不抛未捕获异常；避免整包丢失 |
| 9 | `web/serve.py` | 检测项营养计算失败 → 该项 `status="error"` 并记日志 | D3 | 单项失败不拖垮整链路 |
| 10 | `web/serve.py` | 人工补录项逐项受控（含 `food_id` 参数非法） | **D3（严重）** | 营养库缺记录不再导致 HTTP 500 |
| 11 | `web/serve.py` | `calc_meal()` 异常受控 → `meal=null` 并记日志 | 防御 | 避免整餐异常冒泡成 500 |
| 12 | `web/serve.py` | `weights.grams=0` 视为未提供并写 warning | D7 | 不再静默按份量参考计算 |
| 13 | `web/serve.py` | 阶段日志（请求标识 + 阶段 + 耗时 + 成败 + 原因），并 `flush` | D10 | 故障可追溯；经 tee 也能实时取证 |
| 14 | `web/serve.py` | `do_POST` 生成 `rid`；FATAL 分支记录日志 | D10 | 请求可关联 |
| 15 | `web/serve.py` | `annotate()` 图片句柄释放、去掉为取宽度重复打开 | D8 | 资源未释放 |
| 16 | `scripts/infer.py` | `Image.open` 改用 `with` | D8 | 资源未释放 |
| 17 | `scripts/infer.py` | 删除无用 walrus `top5_idx := top` | D9 | 死代码 |
| 18 | `tests/frontend_render_check.js` | **新增**：用真实响应驱动页面渲染函数 | D1 回归 | 防止再次出现"前端读后端未返回字段" |
| 19 | `tests/test_pipeline_contract.py` | **新增**：19 项针对性测试（映射/匹配/公式/契约） | 第四阶段 | 可测试性 |
| 20 | `scripts/e2e_acceptance.py` | **新增**：9 场景端到端验收 | 第三阶段 | 可复现验收 |
| 21 | `scripts/contract_check.py` | **新增**：修复前后字段集合比对 | 第四阶段 | 契约不变的可审计证据 |

---

## 2. 修改前后关键逻辑差异

### 2.1 D1 · 前端总重取值（致命）

```diff
# web/index.html  renderMeal()
- const t=m.totals;
- ... <div><b>${t.weight_g.toFixed(0)}</b><span>总重 g</span></div>
+ const t=m.totals||{};
+ const num=v=>(v==null?0:v);
+ // 契约 §5.2 的 totals 仅含 5 项营养字段，不含 weight_g，故由 meal.items 汇总
+ const totalW=(m.items||[]).reduce((s,i)=>s+(i.weight_g||0),0);
+ ... <div><b>${totalW.toFixed(0)}</b><span>总重 g</span></div>
```
差异影响：**不新增任何响应字段**。修复后实测：单菜品 150 g、多菜品 400 g，均与 `meal.items` 累加一致。

### 2.2 D2 · 图片解码受控失败

```diff
# web/serve.py  analyze()
- try:
-     W, H = Image.open(path).size          # 失败即冒泡到 do_POST → HTTP 500
+ try:
+     with Image.open(path) as im_h:
+         W, H = im_h.size
+     _log(rid, "decode", ..., "OK", f"{W}x{H}")
+ except Exception as e:
+     W = H = None
+     msg = f"图片读取失败：{type(e).__name__}: {e}（请上传 jpg/png 等有效图片文件）"
+     _log(rid, "decode", ..., "FAIL", ...)
+     targets, alerts = _targets_and_alerts(payload, None, rid)
+     return { ... "detection": {..., "status": "error", "warnings": [msg]},
+              "classification": {"top5": [], "status": "error"},
+              "items": [], "meal": None, "targets": ..., "alerts": alerts}
```
行为变化：`HTTP 500 + {"error":...}` → `HTTP 200 + 完整契约结构 + status="error"`。
**兼容性**：前端 `run()` 已按 `d.error` 分支处理；新响应无顶层 `error`，改由 `detection.status="error"` 走既有的"未检出"提示分支（已补充 warnings 展示）。

### 2.3 D3 · 营养缺失不拖垮链路

```diff
# web/serve.py  人工补录
- for m in (payload.get("manual") or []):
-     fid, grams = int(m["food_id"]), float(m.get("grams") or 0)
-     if grams <= 0: continue
-     it = calc.calc_item(fid, grams, WeightSource.USER_INPUT)   # FoodNotFoundError → 整请求 500
+ for i, m in enumerate(payload.get("manual") or []):
+     try:
+         fid, grams = int(m["food_id"]), float(m.get("grams") or 0)
+     except (TypeError, ValueError, KeyError) as e:
+         items.append({... "status": "error", "warnings": [...]}); continue
+     try:
+         it = calc.calc_item(fid, grams, WeightSource.USER_INPUT)
+     except Exception as e:
+         dct = {"food_id": fid, "food_name": None, "status": "error",
+                "warnings": [f"营养库无此记录或计算失败：{type(e).__name__}: {e}"], ...}
+         _log(rid, f"manual[{i}]", 0, "FAIL", ...)
```
实测（T6）：`food_id=999` 项 `status="error"` + 原因，红烧肉 430.49 kcal 照常产出，`HTTP 200`。

### 2.4 D6 · already_fired 跨图残留

```diff
# web/index.html  handle() / 示例按钮
   Object.keys(WEIGHTS).forEach(k=>delete WEIGHTS[k]);
   MANUAL.length=0;
+  LAST=null;      // 换图即清空上次响应，避免 already_fired 跨图残留导致预警被抑制
   run();
```
实测：`already_fired=[]`→触发 AL-01；`=['AL-01']`→去重不重复；再 `[]`→重新触发。

### 2.5 D8/D9 · 资源与死代码

```diff
# scripts/infer.py
- img = Image.open(path); W, H = img.size
+ with Image.open(path) as img: W, H = img.size
- for cls_idx, p in zip(top5_idx := top, [...])      # top5_idx 后续未使用
+ for cls_idx, p in zip(top, [...])
```

```diff
# web/serve.py  annotate()
- im = Image.open(img_path).convert("RGB")
- scale = im.width / Image.open(img_path).width      # 为取宽度二次打开
- base = Image.open(img_path).convert("RGB")         # 第三次打开，均未关闭
+ with Image.open(img_path) as src:
+     orig_w = src.width; base = src.convert("RGB")
+ im = base.copy(); scale = im.width / orig_w
```

---

## 3. 评估后**放弃**的改动（避免突破契约）

| 设想改动 | 放弃原因 |
|---|---|
| `classification.top5` 改为复用 `cls_out["detections"]` 以消除一次重复推理 | 实测会使 top5 从 5 项退化为 1 项（`infer_image` 对候选做 `<0.3` 过滤），**破坏 PRD MI-01 的 Top-3 验收口径**；已回退原实现。分类阶段存在一次重复推理属性能项，非故障，需人工确认后再优化 |
| 响应中新增 `request_id` 字段 | 契约冻结。改为只在服务端日志中使用，不进入响应 |
| 调整 `infer.py` 分类候选的 `<0.3` 过滤阈值 | 该行为已被 `reports/real_image_check.md` 的真实域指标（检出率 93.8% / 类别正确率 79.6%）依赖，改动会使既有验收数据失效 |
| 给 `meal.totals` 补 `weight_g` 字段 | 契约 §5.2 明确 totals 只含 5 个营养字段；改前端取值而非改后端结构 |

---

## 4. 接口契约不变声明

- 路径与方法：`POST /api/analyze`、`GET /api/health`、`GET /api/foods`、`GET /api/samples` —— 未变
- 请求参数：`image_b64 / weights / manual / already_fired / profile / day_totals / conf` —— 未变
- 响应顶层：`meta / image_b64 / orig_b64 / detection / fallback / classification / items / meal / targets / alerts` —— 未变
- 修复前后字段集合逐层比对：**DIFF = 0**（见 `reports/contract_check.md`）
- 枚举值：`status ∈ {ok, empty, low_confidence, error}`、`weight_source ∈ {user_input, portion_reference, model_estimate}`、`AL-01~AL-05` —— 未变
