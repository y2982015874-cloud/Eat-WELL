# -*- coding: utf-8 -*-
"""
「单类 food 真实域检测评测集」segreal_food1 评测脚本（class-agnostic）

被评模型 : models/det10/weights/best.pt（合成 demos 训练的 YOLOv8n，10 类菜）
评测集   : datasets/segreal_food1/（真实照片，GT 来自 DFoodTJ-Seg 实例掩码 -> bbox）
 how 评测 : GT 类别统一为 "food"，模型输出 10 个具体菜类别 —— 二者类别体系不同，
           因此按 **class-agnostic（忽略类别）** 匹配，只评测「能否在真实照片上定位食物区域」。
           这是本项目约定：**定位能力用本集评测，品类判别用 cls10/Top-3 评测**，不可混用。

指标     : COCO 口径 AP@0.5 / AP@0.5:0.95（101 点插值）、最佳 F1 处的 P/R、
           逐图的 GT 数/检出数/漏检/误检/最大 IoU，并按实例数、图像尺寸分组。
分组     : CLEAN（3,842 张，确认未进过训练）为主结果；SAME（90 张，确认与训练源图同源）单列对照。

只读源 DFoodTJ-Seg.zip，不落盘图片；不修改任何前后端/契约文件。
"""
import os, io, csv, json, time, zipfile, collections
import numpy as np
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = r"D:/专业实训/DFoodTJ-Seg.zip"
MANIFEST = os.path.join(BASE, "datasets", "segreal_food1", "segeval_manifest.csv")
VERIFY = os.path.join(BASE, "reports", "segreal_leakcheck_verified.csv")
WEIGHTS = os.path.join(BASE, "models", "det10", "weights", "best.pt")
OUTDIR = os.path.join(BASE, "reports", "segreal_eval")
SAMPLES = os.path.join(OUTDIR, "samples")
IMGSZ = 416
CONF_COLLECT = 0.02        # 推理时极低阈值收集全部候选（后处理阶段再按阈值过滤，避免重复推理）
CONF_REPORT = [0.05, 0.15, 0.25, 0.40]   # 需要报告的置信度工作点
IOU_THRS = [0.5 + 0.05 * i for i in range(10)]


def fmt(v, w=9, nd=4):
    if v is None:
        return f"{'n/a':>{w}}"
    return f"{round(v, nd) if isinstance(v, float) else v:>{w}}"


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    i = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / ua if ua > 0 else 0.0


def ap_at(gts, preds, thr):
    """preds: [(file, conf, box)]；gts: {file: [box]}；返回 COCO 101 点插值 AP"""
    total = sum(len(v) for v in gts.values())
    if total == 0:
        return None, None, None
    order = sorted(range(len(preds)), key=lambda i: -preds[i][1])
    used = collections.defaultdict(set)
    tp, fp = [], []
    for i in order:
        f, _, box = preds[i]
        best, bj = thr, -1
        for j, gb in enumerate(gts.get(f, [])):
            if j in used[f]:
                continue
            v = iou(box, gb)
            if v > best:
                best, bj = v, j
        if bj >= 0:
            used[f].add(bj); tp.append(1); fp.append(0)
        else:
            tp.append(0); fp.append(1)
    tp = np.cumsum(tp); fp = np.cumsum(fp)
    rec = tp / total
    prec = tp / np.maximum(tp + fp, 1e-9)
    # 101 点插值
    levels = np.linspace(0, 1, 101)
    interp = np.array([prec[rec >= lv].max() if (rec >= lv).any() else 0.0 for lv in levels])
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-9)
    k = int(np.argmax(f1)) if len(f1) else -1
    return float(interp.mean()), (float(prec[k]), float(rec[k])) if k >= 0 else (None, None), None


def evaluate(files, gts, preds, tag, conf=0.25):
    fileset = set(files)
    ps = [p for p in preds if p[0] in fileset and p[1] >= conf]
    n_gt = sum(len(gts[f]) for f in files)
    aps = {}
    for t in IOU_THRS:
        a, pr, _ = ap_at({f: gts[f] for f in files}, ps, t)
        aps[round(t, 2)] = a
    ap50 = aps[0.5]
    map5095 = float(np.mean([v for v in aps.values() if v is not None]))
    # IoU=0.5 逐图统计
    used_set = collections.defaultdict(set)
    for f, c, box in sorted(ps, key=lambda p: -p[1]):
        best, bj = 0.5, -1
        for j, gb in enumerate(gts[f]):
            if j in used_set[f]:
                continue
            v = iou(box, gb)
            if v > best:
                best, bj = v, j
        if bj >= 0:
            used_set[f].add(bj)
    hit = sum(len(used_set[f]) for f in files)
    n_pred = len(ps)
    res = {"tag": tag, "n_images": len(files), "n_gt": n_gt, "n_pred": n_pred,
           "AP50": round(ap50, 4) if ap50 is not None else None,
           "AP50_95": round(map5095, 4),
           "matched@0.5": hit,
           "missed@0.5": n_gt - hit,
           "fp@0.5": n_pred - hit,
           "recall@0.5": round(hit / n_gt, 4) if n_gt else None,
           "precision@0.5": round(hit / n_pred, 4) if n_pred else None,
           "images_with_zero_hit": sum(1 for f in files if len(used_set[f]) == 0)}
    return res, aps


def main(limit=None):
    from ultralytics import YOLO
    os.makedirs(SAMPLES, exist_ok=True)
    man = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    verdict = {r["seg_file"]: r["verdict"] for r in csv.DictReader(open(VERIFY, encoding="utf-8"))}
    files = [r["file"] for r in man]
    if limit:
        files = files[:limit]
    leak = set(f for f in files if verdict.get(f) == "SAME")
    clean = [f for f in files if f not in leak]

    gts = {r["file"]: [(b["x1"], b["y1"], b["x2"], b["y2"]) for b in json.loads(r["boxes"])]
           for r in man}
    size_of = {r["file"]: (int(r["w"]), int(r["h"])) for r in man}
    ninst = {r["file"]: int(r["n_inst"]) for r in man}

    print(f"评测集 {len(files)} 张 | CLEAN {len(clean)} | SAME(同源,单列) {len(leak)}", flush=True)
    print("加载模型...", flush=True)
    model = YOLO(WEIGHTS)

    z = zipfile.ZipFile(ZIP)
    preds, rows, t0 = [], [], time.time()
    pred_rel = []
    n_fullframe_pred = 0
    for i, fn in enumerate(files):
        with z.open("DFoodTJ-Seg/img/" + fn) as f:
            im = Image.open(io.BytesIO(f.read())).convert("RGB")
        W, H = im.size
        t1 = time.time()
        r = model.predict(im, imgsz=IMGSZ, conf=CONF_COLLECT, verbose=False)[0]
        ms = (time.time() - t1) * 1000
        for b in r.boxes:
            bx = [float(v) for v in b.xyxy[0].tolist()]
            box = [max(0, min(W, bx[0])), max(0, min(H, bx[1])), max(0, min(W, bx[2])), max(0, min(H, bx[3]))]
            if box[2] - box[0] < 2 or box[3] - box[1] < 2:
                continue
            rel = (box[2] - box[0]) * (box[3] - box[1]) / (W * H)
            preds.append((fn, float(b.conf), box))
            pred_rel.append(rel)
            if rel > 0.6:
                n_fullframe_pred += 1
        rows.append({"file": fn, "set": "SAME" if fn in leak else "CLEAN",
                     "w": W, "h": H, "n_gt": len(gts[fn]),
                     "n_pred": sum(1 for p in preds if p[0] == fn),
                     "latency_ms": round(ms, 1)})
        if (i + 1) % 500 == 0:
            el = time.time() - t0
            print(f"  {i+1}/{len(files)}  用时 {el:.0f}s  预计剩余 {el/(i+1)*(len(files)-i-1):.0f}s", flush=True)

    lat = [r["latency_ms"] for r in rows]
    print(f"\n推理完成 {len(files)} 张，总耗时 {time.time()-t0:.0f}s，平均 {np.mean(lat):.0f} ms/张，P95 {np.percentile(lat,95):.0f} ms")

    # ---- 主结果：CLEAN 组，多个置信度工作点 ----
    conf_sweep = []
    for c in CONF_REPORT:
        r, _ = evaluate(clean, gts, preds, f"conf={c}", conf=c)
        conf_sweep.append(r)
    res_clean, aps_clean = evaluate(clean, gts, preds, "CLEAN(主结果, conf=0.25)", conf=0.25)
    res_all, _ = evaluate(files, gts, preds, "ALL(含同源)", conf=0.25)
    res_leak, _ = evaluate(sorted(leak), gts, preds, "SAME(同源对照)", conf=0.25) if leak else (None, None)

    # ---- 分组：实例数 / 图像尺寸 / GT 尺度 ----
    def rel_of(gt, f):
        W, H = size_of[f]
        return (gt[2] - gt[0]) * (gt[3] - gt[1]) / (W * H)

    groups = []
    for name, sub in [("单实例图(1 target)", [f for f in clean if ninst[f] == 1]),
                      ("多实例图(>=2 target)", [f for f in clean if ninst[f] >= 2])]:
        r, _ = evaluate(sub, gts, preds, name, conf=0.25)
        groups.append(r)
    for name, sub in [("小图 max<=600", [f for f in clean if max(size_of[f]) <= 600]),
                      ("中图 600<max<=1000", [f for f in clean if 600 < max(size_of[f]) <= 1000]),
                      ("大图 max>1000", [f for f in clean if max(size_of[f]) > 1000])]:
        r, _ = evaluate(sub, gts, preds, name, conf=0.25)
        groups.append(r)
    for name, lo, hi in [("GT小(<10%图幅)", 0.0, 0.10), ("GT中(10-30%)", 0.10, 0.30),
                         ("GT大(>=30%)", 0.30, 1.01)]:
        sub = [f for f in clean if all(lo <= rel_of(g, f) < hi for g in gts[f])]
        r, _ = evaluate(sub, gts, preds, name, conf=0.25)
        groups.append(r)

    used = collections.defaultdict(set)
    for f, c, box in sorted([p for p in preds if p[1] >= 0.25], key=lambda p: -p[1]):
        best, bj = 0.5, -1
        for j, gb in enumerate(gts[f]):
            if j in used[f]:
                continue
            v = iou(box, gb)
            if v > best:
                best, bj = v, j
        if bj >= 0:
            used[f].add(bj)

    det_rows = []
    for fn in files:
        best_ious = []
        for gb in gts[fn]:
            best_ious.append(max([iou(gb, p[2]) for p in preds if p[0] == fn], default=0.0))
        det_rows.append({"file": fn, "set": "SAME" if fn in leak else "CLEAN",
                         "w": size_of[fn][0], "h": size_of[fn][1],
                         "n_gt": len(gts[fn]), "n_hit": len(used[fn]),
                         "max_iou_mean": round(float(np.mean(best_ious)), 4) if best_ious else 0.0})
    with open(os.path.join(OUTDIR, "per_image.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(det_rows[0].keys())); w.writeheader(); w.writerows(det_rows)

    # 可视化：3 张最好 + 3 张最差（多实例优先）
    multi = [r for r in det_rows if r["n_gt"] >= 2]
    vis = sorted(multi, key=lambda r: -r["max_iou_mean"])[:3] + \
          sorted(multi, key=lambda r: r["max_iou_mean"])[:3]
    for r in vis:
        fn = r["file"]
        with z.open("DFoodTJ-Seg/img/" + fn) as f:
            im = Image.open(io.BytesIO(f.read())).convert("RGB")
        W, H = im.size
        sc = 640 / max(W, H)
        if sc < 1:
            im = im.resize((int(W * sc), int(H * sc)))
        else:
            sc = 1.0
        d = ImageDraw.Draw(im)
        for gb in gts[fn]:
            d.rectangle([gb[0] * sc, gb[1] * sc, gb[2] * sc, gb[3] * sc], outline=(0, 255, 0), width=3)
        for f_, c, box in preds:
            if f_ != fn:
                continue
            d.rectangle([box[0] * sc, box[1] * sc, box[2] * sc, box[3] * sc], outline=(255, 0, 0), width=2)
        d.text((6, 6), f"{fn}  GT={r['n_gt']} hit={r['n_hit']} meanIoU={r['max_iou_mean']}", fill=(255, 255, 0))
        im.save(os.path.join(SAMPLES, f"{fn[:-4]}_det.png"))

    summary = {
        "model": "models/det10/weights/best.pt (YOLOv8n, 合成 det10 训练)",
        "eval_set": "segreal_food1 (DFoodTJ-Seg 真实照片, GT=实例掩码->bbox, class-agnostic)",
        "note": "指标极低是真实结果：合成训练的目标占图幅30-45%，真实图实例常占3-13%，尺度严重错配",
        "imgsz": IMGSZ, "conf_reported": 0.25,
        "n_total": len(files), "n_clean": len(clean), "n_same": len(leak),
        "latency_ms_mean": round(float(np.mean(lat)), 1),
        "latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
        "pred_box_relarea_median": round(float(np.median(pred_rel)), 4) if pred_rel else None,
        "pred_box_relarea_p90": round(float(np.percentile(pred_rel, 90)), 4) if pred_rel else None,
        "pred_fullframe_ratio_gt0.6": round(n_fullframe_pred / len(pred_rel), 4) if pred_rel else None,
        "AP_curve_clean": {str(k): (round(v, 4) if v is not None else None) for k, v in aps_clean.items()},
        "clean": res_clean, "all": res_all, "same": res_leak,
        "groups": groups, "conf_sweep": conf_sweep,
    }
    json.dump(summary, open(os.path.join(OUTDIR, "metrics.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n" + "=" * 78)
    print(f"{'分组':<24}{'图数':>6}{'GT':>7}{'检出':>7}{'漏检':>7}{'误检':>7}{'AP50':>9}{'AP50-95':>9}")
    print("=" * 78)
    for r in [res_clean, res_all, res_leak] + groups:
        if not r:
            continue
        print(f"{r['tag']:<24}{r['n_images']:>6}{r['n_gt']:>7}{r['matched@0.5']:>7}"
              f"{r['missed@0.5']:>7}{r['fp@0.5']:>7}"
              f"{fmt(r['AP50'])}{fmt(r['AP50_95'])}")
    print("=" * 78)
    print("\n诊断 · 预测框尺度：中位占图幅 %.1f%%，p90=%.1f%%，其中 >60%% 图幅的『近似全图框』占比 %.1f%%"
          % (100 * (summary["pred_box_relarea_median"] or 0),
             100 * (summary["pred_box_relarea_p90"] or 0),
             100 * (summary["pred_fullframe_ratio_gt0.6"] or 0)))
    print("\n置信度工作点扫描 (CLEAN)：")
    print(f"{'conf':>7}{'预测数':>9}{'检出':>8}{'AP50':>9}{'AP50-95':>9}")
    for r in conf_sweep:
        print(f"{r['tag'].split('=')[1]:>7}{r['n_pred']:>9}{r['matched@0.5']:>8}"
              f"{fmt(r['AP50'])}{fmt(r['AP50_95'])}")
    print("\nAP 曲线(CLEAN):", {k: v for k, v in list(summary["AP_curve_clean"].items())[::2]})
    print("产物 ->", OUTDIR)


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
