# -*- coding: utf-8 -*-
"""
infer.py — B4 模型推理入口，按 model_output_contract.md 输出结构化 JSON
运行 : python scripts/infer.py --model models/det10/weights/best.pt --source img.jpg [--conf 0.25]
       python scripts/infer.py --model models/cls10/weights/best.pt --source img.jpg --task classification
"""
import os, sys, json, argparse, uuid, time

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)

LOW_CONF_MIN = 0.3
LOW_CONF_MAX = 0.6

def load_class_mapping():
    """yolo class_idx -> (food_id, name_zh)，来自 data/class_mapping.csv"""
    import csv
    tier1 = []
    with open(os.path.join(BASE, "data", "class_mapping.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if int(r["tier"]) == 1:
                tier1.append((int(r["food_id"]), r["name_zh"]))
    tier1.sort(key=lambda x: x[0])
    order = [0, 22, 70, 83, 37, 40, 66, 82, 136, 74]   # 与训练 data.yaml names 顺序一致
    m = {}
    for idx, fid in enumerate(order):
        name = dict(tier1)[fid]
        m[idx] = {"food_id": fid, "food_name": name}
    return m

def infer_image(model, path, task, conf, model_version):
    from PIL import Image
    with Image.open(path) as img:
        W, H = img.size
    out = {"image_id": os.path.splitext(os.path.basename(path))[0],
           "model_version": model_version, "task_type": task,
           "image_width": W, "image_height": H,
           "detections": [], "status": "ok", "warnings": []}
    try:
        if task == "detection":
            res = model.predict(path, conf=conf, verbose=False)[0]
            for b in res.boxes:
                c = float(b.conf)
                if c < LOW_CONF_MIN:
                    out["warnings"].append("存在低置信区域(<0.3)已丢弃，建议人工录入")
                    continue
                cls_idx = int(b.cls)
                det = {"class_id": cls_idx, **CLASS_MAP[cls_idx],
                       "confidence": round(c, 4),
                       "bbox_xyxy": [round(float(v), 1) for v in b.xyxy[0].tolist()]}
                if c < LOW_CONF_MAX:
                    det["confidence_flag"] = "low"
                out["detections"].append(det)
            out["detections"].sort(key=lambda d: -d["confidence"])
            if not out["detections"]:
                out["status"] = "empty"
                out["warnings"].append("未检出已收录菜品，建议人工录入")
            elif any(d.get("confidence_flag") == "low" for d in out["detections"]):
                out["status"] = "low_confidence"
        else:  # classification
            res = model.predict(path, verbose=False)[0]
            probs = res.probs
            top = probs.top5
            for cls_idx, p in zip(top, [float(probs.data[i]) for i in top]):
                if p < LOW_CONF_MIN:
                    continue
                det = {"class_id": int(cls_idx), **CLASS_MAP[int(cls_idx)],
                       "confidence": round(p, 4), "bbox_xyxy": None}
                if p < LOW_CONF_MAX:
                    det["confidence_flag"] = "low"
                out["detections"].append(det)
            if not out["detections"]:
                out["status"] = "empty"
                out["warnings"].append("Top-5 候选均低于 0.3，建议人工录入")
            elif out["detections"][0]["confidence"] < LOW_CONF_MAX:
                out["status"] = "low_confidence"
    except Exception as e:
        out["status"] = "error"
        out["warnings"].append(f"推理失败: {type(e).__name__}: {e}")
    return out

CLASS_MAP = load_class_mapping()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--source", required=True, help="图片文件或目录")
    ap.add_argument("--task", default="detection", choices=["detection", "classification"])
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)
    ver = os.path.basename(os.path.dirname(os.path.dirname(args.model))) + "-v1"

    paths = []
    if os.path.isdir(args.source):
        for f in sorted(os.listdir(args.source)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                paths.append(os.path.join(args.source, f))
    else:
        paths.append(args.source)

    results, t0 = [], time.time()
    for p in paths:
        t1 = time.time()
        r = infer_image(model, p, args.task, args.conf, ver)
        r["infer_ms"] = round((time.time() - t1) * 1000, 1)
        results.append(r)
    total_ms = round((time.time() - t0) * 1000, 1)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    os.makedirs(os.path.join(BASE, "reports"), exist_ok=True)
    outp = os.path.join(BASE, "reports", "infer_results.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "task": args.task, "total_ms": total_ms,
                   "n_images": len(paths), "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\n[n] {len(paths)} 张, 总耗时 {total_ms} ms, 平均 {total_ms/len(paths):.1f} ms/张 → {outp}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
