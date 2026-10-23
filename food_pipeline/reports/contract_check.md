# 接口契约保持不变核对记录（第四阶段）

- 执行时间：2026-10-23 19:11:39
- 基线：`reports/_evidence/E*.json`（**修复前**真实响应，第一阶段取证）
- 对照：`reports/_evidence/T*.json`（**修复后**真实响应，第三阶段验收）
- 契约来源：`reports/data_field_spec.md` §5（`/api/analyze` 响应）+ `reports/model_output_contract.md`（模型输出）

## 1. 修复前后字段集合逐层比对

| 场景对 | 层级 | 结论 | 说明 |
|---|---|---|---|
| E1_real_detected → T1 | 顶层响应 | PASS | 10 个字段一致 |
| E1_real_detected → T1 | meta | PASS | 8 个字段一致 |
| E1_real_detected → T1 | detection | PASS | 8 个字段一致 |
| E1_real_detected → T1 | classification | PASS | 2 个字段一致 |
| E1_real_detected → T1 | items[0] | PASS | 15 个字段一致 |
| E1_real_detected → T1 | meal | PASS | 4 个字段一致 |
| E1_real_detected → T1 | meal.totals | PASS | 5 个字段一致 |
| E1_real_detected → T1 | targets | PASS | 9 个字段一致 |
| E1_real_detected → T1 | alerts[0] | PASS | 0 个字段一致 |
| E2_multi_synth → T2 | 顶层响应 | PASS | 10 个字段一致 |
| E2_multi_synth → T2 | meta | PASS | 8 个字段一致 |
| E2_multi_synth → T2 | detection | PASS | 8 个字段一致 |
| E2_multi_synth → T2 | classification | PASS | 2 个字段一致 |
| E2_multi_synth → T2 | items[0] | PASS | 15 个字段一致 |
| E2_multi_synth → T2 | meal | PASS | 4 个字段一致 |
| E2_multi_synth → T2 | meal.totals | PASS | 5 个字段一致 |
| E2_multi_synth → T2 | targets | PASS | 9 个字段一致 |
| E2_multi_synth → T2 | alerts[0] | PASS | 0 个字段一致 |
| E5_nonfood_gray → T5 | 顶层响应 | PASS | 10 个字段一致 |
| E5_nonfood_gray → T5 | meta | PASS | 8 个字段一致 |
| E5_nonfood_gray → T5 | detection | PASS | 8 个字段一致 |
| E5_nonfood_gray → T5 | classification | PASS | 2 个字段一致 |
| E5_nonfood_gray → T5 | items[0] | PASS | 0 个字段一致 |
| E5_nonfood_gray → T5 | meal | PASS | 0 个字段一致 |
| E5_nonfood_gray → T5 | meal.totals | PASS | 0 个字段一致 |
| E5_nonfood_gray → T5 | targets | PASS | 9 个字段一致 |
| E5_nonfood_gray → T5 | alerts[0] | PASS | 0 个字段一致 |
| E7_user_grams → T7 | 顶层响应 | PASS | 10 个字段一致 |
| E7_user_grams → T7 | meta | PASS | 8 个字段一致 |
| E7_user_grams → T7 | detection | PASS | 8 个字段一致 |
| E7_user_grams → T7 | classification | PASS | 2 个字段一致 |
| E7_user_grams → T7 | items[0] | PASS | 15 个字段一致 |
| E7_user_grams → T7 | meal | PASS | 4 个字段一致 |
| E7_user_grams → T7 | meal.totals | PASS | 5 个字段一致 |
| E7_user_grams → T7 | targets | PASS | 9 个字段一致 |
| E7_user_grams → T7 | alerts[0] | PASS | 0 个字段一致 |

DIFF 数 = 0（0 表示修复未改动任何字段名/层级）

## 2. 契约字段包含性校验（修复后样本）

| 校验项 | 结论 | 说明 |
|---|---|---|
| T1 顶层字段 ⊆ 契约 | PASS | 全部包含 |
| T1 meta | PASS | 全部包含 |
| T1 detection | PASS | 全部包含 |
| T1 detections[0] | PASS | 全部包含 |
| T1 classification | PASS | 全部包含 |
| T1 top5[0] | PASS | 全部包含 |
| T1 items[0] | PASS | 全部包含 |
| T1 meal | PASS | 全部包含 |
| T1 meal.totals | PASS | 全部包含 |
| T1 targets | PASS | 全部包含 |
| T5 顶层字段 ⊆ 契约 | PASS | 全部包含 |
| T5 detection | PASS | 全部包含 |

## 3. 枚举值校验

| 场景 | 字段 | 取值 | 结论 |
|---|---|---|---|
| T1 | detection.status | `ok` | PASS |
| T1 | items[].weight_source | `portion_reference` | PASS |
| T2 | detection.status | `ok` | PASS |
| T2 | items[].weight_source | `portion_reference` | PASS |
| T2 | items[].weight_source | `portion_reference` | PASS |
| T3 | detection.status | `error` | PASS |
| T4 | detection.status | `error` | PASS |
| T5 | detection.status | `empty` | PASS |
| T6 | detection.status | `ok` | PASS |
| T6 | items[].weight_source | `portion_reference` | PASS |
| T6 | items[].weight_source | `user_input` | PASS |
| T7 | detection.status | `ok` | PASS |
| T7 | items[].weight_source | `portion_reference` | PASS |
| T8 | detection.status | `ok` | PASS |
| T8 | items[].weight_source | `portion_reference` | PASS |
| T9 | detection.status | `ok` | PASS |
| T9 | items[].weight_source | `portion_reference` | PASS |

## 4. 结论

- 修复仅涉及**取值来源与异常处理路径**，未新增/删除/重命名任何响应字段；请求参数名、HTTP 方法与路径（`POST /api/analyze`）保持不变。
- 异常路径复用了原实现已有的 `items[].error` 字段（原 `web/serve.py` 检测项 except 分支即采用此写法），未新造字段名。
- `classification.top5` 保持完整 5 个候选：曾尝试改为复用过滤后的候选以消除一次重复推理，实测会使 top5 退化到 1 项并破坏 PRD MI-01 的 Top-3 口径，**已回退**，属需人工确认的契约相关变更。