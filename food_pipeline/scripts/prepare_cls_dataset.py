# -*- coding: utf-8 -*-
"""
prepare_cls_dataset.py
用途   : 从 dfoodtj_subset 构建 YOLOv8-cls 分类数据集（10 类高频，PRD MI-01 Top-3 口径）
输入   : datasets/dfoodtj_subset/<000..350>/*.png
         D:/专业实训/DFoodTJ-Rec.zip 内 truth_list（用于按官方 8:1:1 划分，避免泄漏）
输出   : datasets/cls10/{train,val,test}/<idx>_<name_zh>/*.png
         datasets/cls10_split_manifest.csv  逐图来源清单（可追溯）
依赖   : pandas
运行   : python scripts/prepare_cls_dataset.py
说明   : 不修改原始数据；每类抽样上限 train 400 / val 50 / test 50。
         v2: 直接读取 extract_subset.py 产出的 <split>/<class>/ 目录（已按官方 split 分离）。
"""
import os, shutil, random
import pandas as pd

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBSET = os.path.join(BASE, "datasets", "dfoodtj_subset")
OUT = os.path.join(BASE, "datasets", "cls10")
CAPS = {"train": 400, "val": 50, "test": 50}

# YOLO cls 类别索引 -> (原Food ID, 名称)；顺序即 data.yaml names 顺序
CLASSES = [(0, "米饭"), (22, "馒头"), (70, "饺子"), (83, "红烧肉"), (37, "青椒肉丝"),
           (40, "西红柿炒鸡蛋"), (66, "清蒸鲈鱼"), (82, "麻婆豆腐"), (136, "蚝油西兰花"), (74, "冬瓜汤")]

def main():
    random.seed(2026)
    for d in ["train", "val", "test"]:
        for i, (fid, name) in enumerate(CLASSES):
            os.makedirs(os.path.join(OUT, d, f"{i}_{name}"), exist_ok=True)

    manifest = []
    for i, (fid, name) in enumerate(CLASSES):
        cdir = f"{fid:03d}"
        for split in ["train", "val", "test"]:
            pool = sorted(os.listdir(os.path.join(SUBSET, split, cdir)))
            random.shuffle(pool)
            picked = pool[: CAPS[split]]
            dst_dir = os.path.join(OUT, split, f"{i}_{name}")
            for fn in picked:
                src = os.path.join(SUBSET, split, cdir, fn)
                dst = os.path.join(dst_dir, f"{cdir}_{split}_{fn}")
                shutil.copyfile(src, dst)
                manifest.append({"yolo_class_idx": i, "food_id": fid, "name_zh": name,
                                 "split": split, "src_rel": os.path.relpath(src, SUBSET),
                                 "dst": os.path.relpath(dst, OUT)})
        print(f"[2] class {i} {name} done")

    mf = pd.DataFrame(manifest)
    mf.to_csv(os.path.join(OUT, "..", "cls10_split_manifest.csv"), index=False, encoding="utf-8-sig")
    counts = mf.groupby(["split", "yolo_class_idx"]).size().unstack(fill_value=0)
    print("[3] 各 split 类别分布:")
    print(counts.to_string())
    print(f"[4] 输出目录: {OUT}")
    print(f"[5] 清单: {os.path.join(OUT, '..', 'cls10_split_manifest.csv')}  rows={len(mf)}")

if __name__ == "__main__":
    main()
