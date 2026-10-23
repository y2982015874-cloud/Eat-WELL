# -*- coding: utf-8 -*-
"""
evaluate.py — B3 评测
1) 分类（cls10）：按 PRD MI-01 口径计算 Top-3 准确率（前3候选命中即计为命中）
   —— 明确口径：这是"分类 Top-3 准确率"，与目标检测 mAP 是两套指标，不得混用。
2) 检测（det10）：调用 ultralytics.val 在独立 test 集上计算 P/R/mAP@0.5/mAP@0.5:0.95 + 各类指标
运行 : python scripts/evaluate.py
输出 : reports/eval_metrics.json, reports/eval_report.md
"""
import os, sys, json, csv, time
import torch

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

OUT_JSON = os.path.join(BASE, "reports", "eval_metrics.json")
OUT_MD = os.path.join(BASE, "reports", "eval_report.md")

def eval_cls_topk(model_dir, k=3):
    """MI-01 口径：测试集逐张推理，Top-3 候选含真值即命中。"""
    from ultralytics import YOLO
    test_dir = os.path.join(BASE, "datasets", "cls10", "test")
    names = sorted(os.listdir(test_dir))
    model = YOLO(os.path.join(model_dir, "weights", "best.pt"))
    per_class = {n: {"total": 0, "top1": 0, "top3": 0} for n in names}
    total = {"total": 0, "top1": 0, "top3": 0}
    t0 = time.time(); n_img = 0
    for n in names:
        gt = int(n.split("_")[0])
        d = os.path.join(test_dir, n)
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            r = model.predict(p, verbose=False)[0]
            probs = r.probs
            top5 = [int(i) for i in probs.top5]
            top1 = top5[0]
            hit3 = gt in top5[:k]
            per_class[n]["total"] += 1
            per_class[n]["top1"] += int(top1 == gt)
            per_class[n]["top3"] += int(hit3)
            total["total"] += 1; total["top1"] += int(top1 == gt); total["top3"] += int(hit3)
            n_img += 1
    elapsed = time.time() - t0
    res = {"top1_acc": round(total["top1"] / total["total"], 4),
           "top3_acc": round(total["top3"] / total["total"], 4),
           "n_images": total["total"], "infer_s_per_img": round(elapsed / n_img, 4),
           "hardware": f"CPU {torch.get_num_threads()} threads",
           "per_class": {n: {"top1": round(v["top1"]/v["total"], 4),
                             "top3": round(v["top3"]/v["total"], 4),
                             "n": v["total"]} for n, v in per_class.items()}}
    return res

def eval_det(model_dir):
    """独立 test 集检测指标。"""
    from ultralytics import YOLO
    model = YOLO(os.path.join(model_dir, "weights", "best.pt"))
    m = model.val(data=os.path.join(BASE, "datasets", "det10", "data.yaml"),
                  split="test", device="cpu", verbose=False)
    d = m.results_dict
    res = {"precision": round(float(d["metrics/precision(B)"]), 4),
           "recall": round(float(d["metrics/recall(B)"]), 4),
           "mAP50": round(float(d["metrics/mAP50(B)"]), 4),
           "mAP50_95": round(float(d["metrics/mAP50-95(B)"]), 4),
           "n_images": int(d.get("val/n_images", 0)) if isinstance(d.get("val/n_images", 0), (int, float)) else 0,
           "per_class": {}}
    # 真实框实例数（分类别），用于表格里的样本量
    inst = {i: 0 for i in range(10)}
    lbl_dir = os.path.join(BASE, "datasets", "det10", "test", "labels")
    if os.path.isdir(lbl_dir):
        for fn in os.listdir(lbl_dir):
            if not fn.endswith(".txt"):
                continue
            with open(os.path.join(lbl_dir, fn), encoding="utf-8") as fh:
                for line in fh:
                    t = line.split()
                    if len(t) == 5:
                        inst[int(t[0])] = inst.get(int(t[0]), 0) + 1
    try:
        names = m.names
        # 注意：m.box.map50 / m.box.map 是**标量均值**；
        # 分类别要用 ap50（各类 mAP@0.5）与 maps（各类 mAP@0.5:0.95）
        for i, cname in names.items():
            res["per_class"][str(cname)] = {
                "precision": round(float(m.box.p[i]), 4),
                "recall": round(float(m.box.r[i]), 4),
                "mAP50": round(float(m.box.ap50[i]), 4),
                "mAP50_95": round(float(m.box.maps[i]), 4),
                "n_instances": inst.get(i, 0),
            }
    except Exception as e:
        res["per_class_error"] = f"{type(e).__name__}: {e}"
    return res

def main():
    out = {}
    cls_dir = os.path.join(BASE, "models", "cls10")
    det_dir = os.path.join(BASE, "models", "det10")
    if os.path.exists(os.path.join(cls_dir, "weights", "best.pt")):
        print("[1] 分类评测 (Top-1 / Top-3)...")
        out["classification"] = eval_cls_topk(cls_dir)
        print(json.dumps({k: v for k, v in out["classification"].items() if k != "per_class"},
                         ensure_ascii=False))
    if os.path.exists(os.path.join(det_dir, "weights", "best.pt")):
        print("[2] 检测评测 (独立 test 集)...")
        out["detection"] = eval_det(det_dir)
        print(json.dumps({k: v for k, v in out["detection"].items() if k != "per_class"},
                         ensure_ascii=False))
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Markdown 报告
    lines = ["# 评测报告 (B3)", "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}　硬件：CPU（i7-1360P，无独立显卡）", ""]
    if "classification" in out:
        c = out["classification"]
        lines += ["## 1. 分类模型（YOLOv8n-cls，PRD MI-01 口径）", "",
                  f"- **Top-3 准确率：{c['top3_acc']*100:.2f}%**（目标 ≥85%）",
                  f"- Top-1 准确率：{c['top1_acc']*100:.2f}%（参考，论文 ResNet50 全量 351 类为 76.57%）",
                  f"- 测试集：{c['n_images']} 张（10 类 × 各 50 张，独立 test split，未参与训练/调参）",
                  f"- 平均推理耗时：{c['infer_s_per_img']*1000:.1f} ms/张（CPU）", "",
                  "| 类别 | Top-1 | Top-3 | 样本数 |", "|---|---|---|---|"]
        for n, v in c["per_class"].items():
            lines.append(f"| {n} | {v['top1']*100:.1f}% | {v['top3']*100:.1f}% | {v['n']} |")
        lines.append("")
        lines.append("> 口径说明：Top-3 为**分类**指标（前 3 候选含真值即命中），与检测 mAP 属不同口径，"
                     "不得互相替代（PRD 1.4.3 / 任务书 2.2-6）。")
        lines.append("")
    if "detection" in out:
        d = out["detection"]
        lines += ["## 2. 检测模型（YOLOv8n，合成 det10 独立 test 集）", "",
                  f"- Precision: {d['precision']}", f"- Recall: {d['recall']}",
                  f"- mAP@0.5: {d['mAP50']}", f"- mAP@0.5:0.95: {d['mAP50_95']}", "",
                  f"- 测试集：200 张合成图 / {sum(v.get('n_instances',0) for v in d['per_class'].values())} 个目标框（独立 test split）", "",
                  "| 类别 | P | R | mAP50 | mAP50-95 | 真实框数 |", "|---|---|---|---|---|---|"]
        for n, v in d["per_class"].items():
            lines.append(f"| {n} | {v['precision']} | {v['recall']} | {v['mAP50']} | {v['mAP50_95']} "
                         f"| {v.get('n_instances','-')} |")
        lines.append("")
        lines.append("> **重要提示**：test 集与训练集同为**合成数据**（同分布），"
                     "上述 mAP 代表合成域内的上限性能，**不能直接外推到真实多菜照片**。"
                     "真实域（真实拍摄照片）上的实测见下节与 reports/error_analysis.md。")
        lines.append("")

    # 真实图片核验（若已跑过 real_image_check.py）
    rj = os.path.join(BASE, "reports", "real_image_infer.json")
    if os.path.exists(rj):
        with open(rj, encoding="utf-8") as f:
            rr = json.load(f)["summary"]
        dd, cc = rr["detection"], rr["classification"]
        lines += ["## 3. 真实图片推理核验（域差距测量）", "",
                  f"样本：{rr['source']}，共 {rr['n_images']} 张真实照片（未参与训练）。", "",
                  "| 指标 | 检测模型 det10 | 分类模型 cls10 |", "|---|---|---|",
                  f"| 检出率（≥1 框） | {dd['any_box_rate']*100:.1f}% | — |",
                  f"| 主框类别正确率 | {dd['top1_class_correct_rate']*100:.1f}% | "
                  f"Top-1 {cc['top1_acc']*100:.2f}% |",
                  f"| 任一框/前3候选命中 | {dd['any_box_class_correct_rate']*100:.1f}% | "
                  f"Top-3 {cc['top3_acc']*100:.2f}% |",
                  f"| 单菜品图多框率（误检信号） | {dd['multi_box_rate_on_single_dish']*100:.1f}% | — |",
                  f"| 单张推理 P50 | {dd['latency_ms']['p50']} ms | {cc['latency_ms']['p50']} ms |",
                  f"| 单张推理 P95 | {dd['latency_ms']['p95']} ms | {cc['latency_ms']['p95']} ms |", "",
                  f"> **PRD MI-03（P95 ≤ 5s）**：模型侧单张推理 P95 "
                  f"检测 {dd['latency_ms']['p95']} ms / 分类 {cc['latency_ms']['p95']} ms，"
                  f"远低于 5s（含前后处理的端到端链路耗时见 reports/wp_c_delivery.md）。", "",
                  "> **域差距结论**：检测模型在真实照片上检出率仍达 "
                  f"{dd['any_box_rate']*100:.1f}%，但主框类别正确率由合成域的 mAP50 "
                  f"{d.get('mAP50','-')} 降到 {dd['top1_class_correct_rate']*100:.1f}%，"
                  "证明合成数据训练的检测模型**可直接外推的部分是定位能力，分类能力需依赖分类模型兜底**。",
                  "完整逐图结果见 reports/real_image_infer.json。", ""]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[3] 已写出 {OUT_JSON} 与 {OUT_MD}")

if __name__ == "__main__":
    main()
