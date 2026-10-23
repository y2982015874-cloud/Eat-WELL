# -*- coding: utf-8 -*-
"""
extract_subset.py  (v2, 修正版)
用途   : 从 DFoodTJ-Rec.zip 按需解压选定 10 类图像，按官方 train/val/test 分目录，
         避免不同 split 同名文件互相覆盖（v1 缺陷）。
输入   : D:/专业实训/DFoodTJ-Rec.zip
输出   : datasets/dfoodtj_subset/<train|val|test>/<类别3位ID>/<原文件名>.png
依赖   : 标准库
运行   : python scripts/extract_subset.py
说明   : 只读原始 zip，不修改。
"""
import zipfile, os, time

ZIP = r"D:/专业实训/DFoodTJ-Rec.zip"
OUT = r"D:/workbuddy/kkk/food_pipeline/datasets/dfoodtj_subset"
CLASSES = {"000", "022", "070", "083", "037", "040", "066", "082", "136", "074"}

def main():
    z = zipfile.ZipFile(ZIP)
    t0 = time.time()
    n = 0
    for name in z.namelist():
        p = name.replace("\\", "/").split("/")
        if len(p) != 4 or not p[3].endswith(".png"):
            continue
        root, split, cls, fn = p
        if root != "DFoodTJ-Rec" or split not in ("train", "val", "test") or cls not in CLASSES:
            continue
        d = os.path.join(OUT, split, cls)
        os.makedirs(d, exist_ok=True)
        tgt = os.path.join(d, fn)
        if os.path.exists(tgt):
            continue
        with open(tgt, "wb") as f:
            f.write(z.read(name))
        n += 1
    print(f"extracted {n} files in {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
