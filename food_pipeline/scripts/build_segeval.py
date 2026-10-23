# -*- coding: utf-8 -*-
"""
构建「单类 food 真实域检测评测集」segreal_food1（只读源，不做任何写回）

源数据  : D:\\专业实训\\DFoodTJ-Seg.zip  （仅 zipfile 读，不解压）
输入（上游产物，来自 scripts/kernel seg_audit 全量统计）:
    reports/seg_audit/file_size_audit.csv   逐文件宽高
    reports/seg_audit/instance_boxes.csv    逐实例 bbox（共 6887 个）
输出    : datasets/segreal_food1/
    labels/<6位>.txt      YOLO 单类标注，class 恒为 0 = "food"
    data.yaml             nc:1 names:['food']（供可选 ultralytics 校验，本评测自建逻辑不依赖）
    segeval_manifest.csv  逐图：尺寸/实例数/每实例 bbox/像素面积/是否疑似泄漏

设计要点
1. 类别：DFoodTJ-Seg 的掩码是「实例掩码」，类别标签在导出时已丢失。
   故统一 class=0 表示「任意食物」，本集只评测**定位/检出能力**，不评测品类判别。
2. 图片不落盘（约 2GB）：评测时从 zip 流式读取；需要离线图请用 --dump-images。
3. 本集从未参与 det10 / cls10 的任何训练，属纯 held-out 真实域评测。
"""
import os, csv, sys, json, collections, argparse, zipfile, io

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BASE)                      # D:/workbuddy/kkk
ZIP = r"D:/专业实训/DFoodTJ-Seg.zip"
AUDIT = os.path.join(BASE, "reports", "seg_audit")
OUT = os.path.join(BASE, "datasets", "segreal_food1")
CLASS_ID = 0
CLASS_NAME = "food"


def main(dump_images=False):
    boxes_csv = os.path.join(AUDIT, "instance_boxes.csv")
    size_csv = os.path.join(AUDIT, "file_size_audit.csv")
    for p in (boxes_csv, size_csv):
        if not os.path.exists(p):
            sys.exit(f"[ERR] 缺少上游产物 {p}，请先跑 seg 审计")

    sizes = {r["file"]: (int(r["img_w"]), int(r["img_h"]))
             for r in csv.DictReader(open(size_csv, encoding="utf-8"))}
    inst = collections.defaultdict(list)
    for r in csv.DictReader(open(boxes_csv, encoding="utf-8")):
        inst[r["file"]].append(r)
    files = sorted(sizes)
    print(f"[1/4] 图纸 n={len(files)}  实例总数 n={sum(len(v) for v in inst.values())}")

    os.makedirs(os.path.join(OUT, "labels"), exist_ok=True)
    lab_dir = os.path.join(OUT, "labels")
    rows = []
    skipped_deg = []
    for fn in files:
        W, H = sizes[fn]
        lines, meta = [], []
        for b in inst.get(fn, []):
            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])
            bw, bh = int(b["bw"]), int(b["bh"])
            if bw < 2 or bh < 2:
                skipped_deg.append((fn, int(b["inst"]), bw, bh))
                continue
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            lines.append(f"{CLASS_ID} {cx/W:.6f} {cy/H:.6f} {bw/W:.6f} {bh/H:.6f}")
            meta.append({"inst": int(b["inst"]), "area_px": int(b["area"]),
                         "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        stem = os.path.splitext(fn)[0]
        with open(os.path.join(lab_dir, stem + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
        rows.append({"file": fn, "stem": stem, "w": W, "h": H,
                     "n_inst": len(meta), "boxes": json.dumps(meta, ensure_ascii=False)})

    print(f"[2/4] labels 已写出 {len(rows)} 个"
          + (f"，剔除退化框 {len(skipped_deg)} 个" if skipped_deg else ""))

    man = os.path.join(OUT, "segeval_manifest.csv")
    with open(man, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "stem", "w", "h", "n_inst", "boxes"])
        w.writeheader(); w.writerows(rows)

    yaml_txt = f"""# segeval 单类 food 真实域检测评测集
# 用途：评测「能否在真实照片上定位食物区域」，不评测品类判别
# 来源：DFoodTJ-Seg.zip（img/ + maskrcnn_groundtruth/），掩码 -> 逐实例 bbox
# 注意：源数据集的类别标签在导出时已丢失，故统一为 nc=1 (food)
path: {OUT.replace(os.sep, '/')}
train: data.yaml
val: data.yaml
test: data.yaml
nc: 1
names: ['{CLASS_NAME}']
"""
    with open(os.path.join(OUT, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(yaml_txt)
    print(f"[3/4] data.yaml / manifest 已写出 -> {OUT}")

    if dump_images:
        img_dir = os.path.join(OUT, "images")
        os.makedirs(img_dir, exist_ok=True)
        z = zipfile.ZipFile(ZIP)
        for i, fn in enumerate(files):
            with z.open("DFoodTJ-Seg/img/" + fn) as s:
                open(os.path.join(img_dir, fn), "wb").write(s.read())
            if (i + 1) % 1000 == 0:
                print(f"   已导出图片 {i+1}/{len(files)}", flush=True)
        print(f"[4/4] 图片已导出 -> {img_dir}")
    else:
        print("[4/4] 图片未落盘（默认）；评测脚本从 zip 流式读取。落盘请加 --dump-images")

    dist = collections.Counter(r["n_inst"] for r in rows)
    print(f"\n实例数分布: {dict(sorted(dist.items()))}")
    print(f"多实例图: {sum(v for k, v in dist.items() if k >= 2)} / {len(rows)}")
    print(f"评测集根目录: {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-images", action="store_true", help="把 3932 张原图落盘到 images/")
    a = ap.parse_args()
    main(a.dump_images)
