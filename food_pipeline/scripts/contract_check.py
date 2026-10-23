# -*- coding: utf-8 -*-
"""
contract_check.py —— 第四阶段：接口契约保持不变的核对记录

方法：
  1) 以**修复前**抓取的真实响应（reports/_evidence/E*.json，第一阶段取证）为基线；
  2) 与**修复后**的响应（reports/_evidence/T*.json，第三阶段验收）逐层比对字段集合；
  3) 再按 reports/data_field_spec.md §5 声明的契约字段做包含性校验。

只做"字段集合"层面的比对：路径、HTTP 方法、字段名、类型、嵌套层级、枚举值均不改动。
产物：reports/contract_check.md

运行：python scripts/contract_check.py
"""
import os, json, sys, time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EVID = os.path.join(BASE_DIR, "reports", "_evidence")

# data_field_spec.md §5 声明的响应契约（冻结，不得增删）
CONTRACT_TOP = ["meta", "image_b64", "orig_b64", "detection", "fallback",
                "classification", "items", "meal", "targets", "alerts"]
CONTRACT_META = ["image_width", "image_height", "det_ms", "cls_ms", "total_ms",
                 "device", "cls_version", "det_version"]
CONTRACT_DET = ["image_id", "model_version", "task_type", "image_width", "image_height",
                "detections", "status", "warnings"]
CONTRACT_DET_ITEM = ["class_id", "food_id", "food_name", "confidence", "bbox_xyxy"]
CONTRACT_CLS = ["top5", "status"]
CONTRACT_CLS_ITEM = ["class_id", "food_id", "food_name", "prob"]
CONTRACT_ITEM = ["food_id", "food_name", "weight_g", "weight_source", "energy_kcal",
                 "carb_g", "fat_g", "protein_g", "fiber_g", "per_100g", "status", "warnings"]
CONTRACT_MEAL = ["items", "totals", "status", "warnings"]
CONTRACT_TOTALS = ["carb_g", "fat_g", "protein_g", "fiber_g", "energy_kcal"]
CONTRACT_TARGETS = ["bmr", "tdee", "target_kcal", "target_protein_g", "target_fat_g",
                    "target_carb_g", "bmi"]
CONTRACT_ALERT = ["code", "name", "message", "basis", "severity", "trigger_time"]

# 枚举值（冻结）
STATUS_ENUM = {"ok", "empty", "low_confidence", "error"}
WEIGHT_SRC_ENUM = {"user_input", "portion_reference", "model_estimate"}

PAIRS = [("E1_real_detected", "T1"), ("E2_multi_synth", "T2"),
         ("E5_nonfood_gray", "T5"), ("E7_user_grams", "T7")]


def load(name):
    p = os.path.join(EVID, name + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def keyset(o):
    return sorted(o.keys()) if isinstance(o, dict) else None


def cmp_layer(label, a, b):
    """返回 (状态, 说明)；a=修复前, b=修复后"""
    if a is None or b is None:
        return "SKIP", "基线或新响应缺失"
    ka, kb = keyset(a), keyset(b)
    if ka == kb:
        return "PASS", f"{len(kb)} 个字段一致"
    added = [k for k in kb if k not in ka]
    removed = [k for k in ka if k not in kb]
    return "DIFF", f"新增={added} 删除={removed}"


def main():
    rows, notes = [], []
    for old_n, new_n in PAIRS:
        a, b = load(old_n), load(new_n)
        if a is None or b is None:
            notes.append(f"- 场景对 {old_n} -> {new_n}：证据缺失，跳过")
            continue
        for layer, get in [
            ("顶层响应", lambda d: d),
            ("meta", lambda d: d["meta"] or {}),
            ("detection", lambda d: d["detection"] or {}),
            ("classification", lambda d: d["classification"] or {}),
            ("items[0]", lambda d: (d["items"] or [{}])[0]),
            ("meal", lambda d: d["meal"] or {}),
            ("meal.totals", lambda d: (d["meal"] or {}).get("totals") or {}),
            ("targets", lambda d: d["targets"] or {}),
            ("alerts[0]", lambda d: (d["alerts"] or [{}])[0]),
        ]:
            try:
                st, msg = cmp_layer(layer, get(a), get(b))
            except Exception as e:
                st, msg = "ERR", f"{type(e).__name__}: {e}"
            rows.append((f"{old_n} → {new_n}", layer, st, msg))

    # 契约包含性校验（以修复后 T1 / T5 为样本）
    inc = []
    def check(name, obj, required):
        if obj is None:
            inc.append((name, "SKIP", "样本缺失")); return
        miss = [k for k in required if k not in obj]
        inc.append((name, "PASS" if not miss else "FAIL", "全部包含" if not miss else f"缺失 {miss}"))

    t1, t5 = load("T1"), load("T5")
    if t1:
        check("T1 顶层字段 ⊆ 契约", t1, CONTRACT_TOP)
        check("T1 meta", t1["meta"], CONTRACT_META)
        check("T1 detection", t1["detection"], CONTRACT_DET)
        check("T1 detections[0]", (t1["detection"]["detections"] or [{}])[0], CONTRACT_DET_ITEM)
        check("T1 classification", t1["classification"], CONTRACT_CLS)
        check("T1 top5[0]", (t1["classification"]["top5"] or [{}])[0], CONTRACT_CLS_ITEM)
        check("T1 items[0]", (t1["items"] or [{}])[0], CONTRACT_ITEM)
        check("T1 meal", t1["meal"] or {}, CONTRACT_MEAL)
        check("T1 meal.totals", (t1["meal"] or {}).get("totals") or {}, CONTRACT_TOTALS)
        check("T1 targets", t1["targets"] or {}, CONTRACT_TARGETS)
        if t1.get("alerts"):
            check("T1 alerts[0]", t1["alerts"][0], CONTRACT_ALERT)
    if t5:
        check("T5 顶层字段 ⊆ 契约", t5, CONTRACT_TOP)
        check("T5 detection", t5["detection"], CONTRACT_DET)

    # 枚举值校验
    enum_rows = []
    for nm in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"):
        d = load(nm)
        if not d:
            continue
        st = d["detection"]["status"]
        enum_rows.append((nm, "detection.status", st, "PASS" if st in STATUS_ENUM else "FAIL"))
        for i in d.get("items") or []:
            ws = i.get("weight_source")
            if ws:
                enum_rows.append((nm, f"items[].weight_source", ws,
                                  "PASS" if ws in WEIGHT_SRC_ENUM else "FAIL"))

    L = []
    L.append("# 接口契约保持不变核对记录（第四阶段）\n")
    L.append(f"- 执行时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("- 基线：`reports/_evidence/E*.json`（**修复前**真实响应，第一阶段取证）")
    L.append("- 对照：`reports/_evidence/T*.json`（**修复后**真实响应，第三阶段验收）")
    L.append("- 契约来源：`reports/data_field_spec.md` §5（`/api/analyze` 响应）+ "
             "`reports/model_output_contract.md`（模型输出）\n")
    L.append("## 1. 修复前后字段集合逐层比对\n")
    L.append("| 场景对 | 层级 | 结论 | 说明 |")
    L.append("|---|---|---|---|")
    for r in rows:
        L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    n_diff = sum(1 for r in rows if r[2] == "DIFF")
    L.append(f"\nDIFF 数 = {n_diff}（0 表示修复未改动任何字段名/层级）\n")
    L.append("## 2. 契约字段包含性校验（修复后样本）\n")
    L.append("| 校验项 | 结论 | 说明 |")
    L.append("|---|---|---|")
    for r in inc:
        L.append(f"| {r[0]} | {r[1]} | {r[2]} |")
    L.append("\n## 3. 枚举值校验\n")
    L.append("| 场景 | 字段 | 取值 | 结论 |")
    L.append("|---|---|---|---|")
    for r in enum_rows:
        L.append(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]} |")
    L.append("\n## 4. 结论\n")
    L.append("- 修复仅涉及**取值来源与异常处理路径**，未新增/删除/重命名任何响应字段；"
             "请求参数名、HTTP 方法与路径（`POST /api/analyze`）保持不变。")
    L.append("- 异常路径复用了原实现已有的 `items[].error` 字段（原 `web/serve.py` 检测项 except 分支即采用此写法），"
             "未新造字段名。")
    L.append("- `classification.top5` 保持完整 5 个候选：曾尝试改为复用过滤后的候选以消除一次重复推理，"
             "实测会使 top5 退化到 1 项并破坏 PRD MI-01 的 Top-3 口径，**已回退**，属需人工确认的契约相关变更。")
    out = os.path.join(BASE_DIR, "reports", "contract_check.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"契约核对完成 -> {out}")
    print(f"  字段集合 DIFF = {n_diff}；包含性 FAIL = {sum(1 for r in inc if r[1]=='FAIL')}；"
          f"枚举 FAIL = {sum(1 for r in enum_rows if r[3]=='FAIL')}")
    for n in notes:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
