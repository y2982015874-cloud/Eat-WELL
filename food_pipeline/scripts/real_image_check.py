# -*- coding: utf-8 -*-
"""
real_image_check.py — B3 真实图片推理核验
用**真实** DFoodTJ-Rec test split 单菜品照片（datasets/cls10/test，非合成图）跑两个模型：
  - 检测模型 det10：能否在真实照片上定位并正确分类（域差距验证）
  - 分类模型 cls10：真实照片 Top-1 / Top-3（复算，与 evaluate.py 交叉校验）
同时统计单张推理延迟 P50 / P95（PRD MI-03 口径的模型侧延迟）

运行 : python scripts/real_image_check.py
输出 : reports/real_image_infer.json, reports/real_image_check.md
"""
import os, sys, json, time, statistics

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(BASE, "scripts"))
os.chdir(BASE)

TEST_DIR = os.path.join(BASE, "datasets", "cls10", "test")     # 真实图片（DFoodTJ-Rec test split）
DET_W = os.path.join(BASE, "models", "det10", "weights", "best.pt")
CLS_W = os.path.join(BASE, "models", "cls10", "weights", "best.pt")
OUT_JSON = os.path.join(BASE, "reports", "real_image_infer.json")
OUT_MD = os.path.join(BASE, "reports", "real_image_check.md")

CLASS_ORDER = [0, 22, 70, 83, 37, 40, 66, 82, 136, 74]        # yolo class_idx -> food_id
NAMES = ["米饭", "馒头", "饺子", "红烧肉", "青椒肉丝", "西红柿炒鸡蛋",
         "清蒸鲈鱼", "麻婆豆腐", "蚝油西兰花", "冬瓜汤"]


def pct(sorted_vals, p):
    """线性插值分位数"""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return round(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f), 1)


def main():
    from ultralytics import YOLO

    dirs = sorted(os.listdir(TEST_DIR))
    det = YOLO(DET_W)
    cls = YOLO(CLS_W)

    per_class = {}
    for d in dirs:
        idx = int(d.split("_")[0])
        per_class[idx] = {"name": d.split("_", 1)[1], "n": 0,
                          "det_any_box": 0, "det_top1_correct": 0, "det_any_correct": 0,
                          "det_multi_box": 0, "cls_top1": 0, "cls_top3": 0,
                          "conf_sum": 0.0, "n_box_sum": 0}

    rows = []
    det_ms, cls_ms = [], []
    t_all = time.time()

    for d in dirs:
        idx = int(d.split("_")[0])
        for f in sorted(os.listdir(os.path.join(TEST_DIR, d))):
            p = os.path.join(TEST_DIR, d, f)

            t0 = time.time()
            r = det.predict(p, imgsz=416, conf=0.25, verbose=False)[0]
            det_ms.append((time.time() - t0) * 1000)
            boxes = r.boxes
            n_box = len(boxes)
            preds = []
            for b in boxes:
                preds.append({"cls": int(b.cls), "conf": round(float(b.conf), 4)})
            preds.sort(key=lambda x: -x["conf"])
            top1 = preds[0]["cls"] if preds else None

            t0 = time.time()
            rc = cls.predict(p, verbose=False)[0]
            cls_ms.append((time.time() - t0) * 1000)
            top5 = [int(i) for i in rc.probs.top5]
            c_top1 = top5[0]
            c_hit3 = idx in top5[:3]

            st = per_class[idx]
            st["n"] += 1
            st["n_box_sum"] += n_box
            if n_box >= 1:
                st["det_any_box"] += 1
                st["conf_sum"] += preds[0]["conf"]
            if n_box >= 2:
                st["det_multi_box"] += 1
            if top1 == idx:
                st["det_top1_correct"] += 1
            if any(pp["cls"] == idx for pp in preds):
                st["det_any_correct"] += 1
            st["cls_top1"] += int(c_top1 == idx)
            st["cls_top3"] += int(c_hit3)

            rows.append({"image": f"{d}/{f}", "gt_class": idx, "gt_name": st["name"],
                         "det_n_box": n_box, "det_top1": top1,
                         "det_top1_conf": preds[0]["conf"] if preds else None,
                         "cls_top1": c_top1, "cls_hit3": c_hit3})

    det_ms_s, cls_ms_s = sorted(det_ms), sorted(cls_ms)
    total_n = sum(v["n"] for v in per_class.values())

    summary = {
        "n_images": total_n,
        "source": "DFoodTJ-Rec 官方 test split 真实照片（datasets/cls10/test，10 类 × 50 张）",
        "detection": {
            "any_box_rate": round(sum(v["det_any_box"] for v in per_class.values()) / total_n, 4),
            "top1_class_correct_rate": round(sum(v["det_top1_correct"] for v in per_class.values()) / total_n, 4),
            "any_box_class_correct_rate": round(sum(v["det_any_correct"] for v in per_class.values()) / total_n, 4),
            "multi_box_rate_on_single_dish": round(sum(v["det_multi_box"] for v in per_class.values()) / total_n, 4),
            "avg_boxes_per_image": round(sum(v["n_box_sum"] for v in per_class.values()) / total_n, 3),
            "avg_top_conf": round(
                sum(v["conf_sum"] for v in per_class.values()) / max(sum(v["det_any_box"] for v in per_class.values()), 1), 4),
            "latency_ms": {"p50": pct(det_ms_s, 50), "p95": pct(det_ms_s, 95),
                           "max": round(det_ms_s[-1], 1),
                           "mean": round(statistics.mean(det_ms), 1)},
        },
        "classification": {
            "top1_acc": round(sum(v["cls_top1"] for v in per_class.values()) / total_n, 4),
            "top3_acc": round(sum(v["cls_top3"] for v in per_class.values()) / total_n, 4),
            "latency_ms": {"p50": pct(cls_ms_s, 50), "p95": pct(cls_ms_s, 95),
                           "max": round(cls_ms_s[-1], 1),
                           "mean": round(statistics.mean(cls_ms), 1)},
        },
        "per_class": {str(k): {
            "name": v["name"], "n": v["n"],
            "det_any_box": round(v["det_any_box"] / v["n"], 4),
            "det_top1_correct": round(v["det_top1_correct"] / v["n"], 4),
            "cls_top1": round(v["cls_top1"] / v["n"], 4),
            "cls_top3": round(v["cls_top3"] / v["n"], 4),
        } for k, v in per_class.items()},
        "wall_clock_s": round(time.time() - t_all, 1),
    }

    # 抽样 6 张走一遍正式推理契约（infer.py 同款结构）
    from infer import infer_image, CLASS_MAP
    samples = []
    for p_rel in ["0_米饭", "4_青椒肉丝", "7_麻婆豆腐"]:
        d = os.path.join(TEST_DIR, p_rel)
        fs = sorted(os.listdir(d))[:2]
        for f in fs:
            samples.append({"task": "detection",
                            **infer_image(det, os.path.join(d, f), "detection", 0.25, "det10-v1")})
    for p_rel in ["0_米饭", "8_蚝油西兰花"]:
        d = os.path.join(TEST_DIR, p_rel)
        f = sorted(os.listdir(d))[0]
        samples.append({"task": "classification",
                        **infer_image(cls, os.path.join(d, f), "classification", 0.25, "cls10-v1")})

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "samples": samples,
                   "per_image": rows}, f, ensure_ascii=False, indent=2)

    d_ = summary["detection"]; c_ = summary["classification"]
    lines = ["# 真实图片推理核验（B3）", "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}　样本：{summary['source']}　共 {total_n} 张",
             "硬件：CPU i7-1360P（无独立显卡），torch 2.5.0+cpu", "",
             "> 说明：本批图片是 **DFoodTJ-Rec 官方 test split 的真实拍摄照片**（未参与训练），"
             "用于验证合成数据训练出的模型在真实域上的表现，即域差距（domain gap）测量。",
             "每张图为**单菜品**，因此“检出 ≥2 个框”在真实域上应视为误检信号。", "",
             "## 1. 检测模型 det10（YOLOv8n，合成数据训练）", "",
             "| 指标 | 数值 | 说明 |", "|---|---|---|",
             f"| 检出率（≥1 框） | {d_['any_box_rate']*100:.1f}% | 真实照片上能否定位到菜品 |",
             f"| 最高置信框类别正确率 | {d_['top1_class_correct_rate']*100:.1f}% | 主框类别 == 真值 |",
             f"| 任一框类别正确率 | {d_['any_box_class_correct_rate']*100:.1f}% | 检出框中存在正确类别 |",
             f"| 多框率（单菜品图出 ≥2 框） | {d_['multi_box_rate_on_single_dish']*100:.1f}% | **误检信号**，真实单菜品图不应多框 |",
             f"| 平均框数/图 | {d_['avg_boxes_per_image']} | 真值为 1 |",
             f"| 平均最高置信 | {d_['avg_top_conf']} | |",
             f"| 单张推理延迟 P50 / P95 | {d_['latency_ms']['p50']} / {d_['latency_ms']['p95']} ms | PRD MI-03 ≤5s |", "",
             "## 2. 分类模型 cls10（YOLOv8n-cls，真实数据训练）", "",
             f"- Top-1：{c_['top1_acc']*100:.2f}%",
             f"- Top-3：{c_['top3_acc']*100:.2f}%（与 evaluate.py 独立复算一致）",
             f"- 单张推理延迟 P50 / P95：{c_['latency_ms']['p50']} / {c_['latency_ms']['p95']} ms", "",
             "## 3. 分类别明细（真实图片）", "",
             "| 类别 | 检出率 | 检测主框正确率 | 分类 Top-1 | 分类 Top-3 | 样本 |",
             "|---|---|---|---|---|---|"]
    for k, v in summary["per_class"].items():
        lines.append(f"| {v['name']} | {v['det_any_box']*100:.1f}% | {v['det_top1_correct']*100:.1f}% "
                     f"| {v['cls_top1']*100:.1f}% | {v['cls_top3']*100:.1f}% | {v['n']} |")
    lines += ["", "## 4. 契约化推理输出样例（reports/real_image_infer.json → samples）", "",
              "```json",
              json.dumps(samples[:2], ensure_ascii=False, indent=2),
              "```", "",
              f"完整逐图结果：reports/real_image_infer.json（{total_n} 条 per_image 记录）"]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[ok] {OUT_JSON}\n[ok] {OUT_MD}", file=sys.stderr)


if __name__ == "__main__":
    main()
