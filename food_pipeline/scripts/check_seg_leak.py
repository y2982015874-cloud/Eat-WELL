# -*- coding: utf-8 -*-
"""
泄漏排查：DFoodTJ-Seg 的图 是否曾出现在 det10 训练合成图的上游源图里

背景
  det10（合成检测训练集）的素材来自 datasets/dfoodtj_subset/**，
  即 DFoodTJ-Rec 按 10 类部分解压的 12,239 张原始图（train/val/test）。
  若 DFoodTJ-Seg 的某张图与其中某张是同一张照片，则该图已经[间接]进入训练，
  用它评测会高估性能 —— 必须先把这批挑出来，评测分组报告。

方法
  dHash（相邻像素差分哈希，64 bit）+ aHash（均值哈希，64 bit）
  汉明距离 <= 阈值判定为疑似同源；命中项再人工抽样目视复核。
  全程只读：Seg 图从 zip 流式读，不落盘。
"""
import os, csv, io, json, zipfile, collections
import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = r"D:/专业实训/DFoodTJ-Seg.zip"
SUBSET = os.path.join(BASE, "datasets", "dfoodtj_subset")
OUT = os.path.join(BASE, "reports", "segreal_leakcheck.csv")
THRESH = 8            # 64 bit 中容忍 8 位差异（旋转/编码差异）


def dhash(im):
    g = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).ravel()
    return int(np.packbits(bits).tobytes().hex(), 16)


def ahash(im):
    g = np.asarray(im.convert("L").resize((8, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g > g.mean()).ravel()
    return int(np.packbits(bits).tobytes().hex(), 16)


def load_subset():
    items = []
    for split in ("train", "val", "test"):
        sd = os.path.join(SUBSET, split)
        if not os.path.isdir(sd):
            continue
        for cls in sorted(os.listdir(sd)):
            cd = os.path.join(sd, cls)
            for fn in sorted(os.listdir(cd)):
                if fn.lower().endswith(".png"):
                    items.append((f"{split}/{cls}/{fn}", os.path.join(cd, fn)))
    return items


def main():
    sub = load_subset()
    print(f"[1/3] 训练源图 dfoodtj_subset: {len(sub)} 张")
    sub_d, sub_a, paths = [], [], []
    for rel, p in sub:
        try:
            im = Image.open(p)
            sub_d.append(dhash(im)); sub_a.append(ahash(im)); paths.append(rel)
        except Exception as e:
            print("  WARN 读取失败", rel, e)
    sub_d = np.array(sub_d, dtype=np.uint64)
    sub_a = np.array(sub_a, dtype=np.uint64)
    print("      源图哈希计算完成")

    man = list(csv.DictReader(open(os.path.join(BASE, "datasets", "segreal_food1", "segeval_manifest.csv"),
                                   encoding="utf-8")))
    z = zipfile.ZipFile(ZIP)
    rows, hits = [], []
    print(f"[2/3] 逐张比对 Seg 图 {len(man)} 张 ...", flush=True)
    for i, r in enumerate(man):
        fn = r["file"]
        with z.open("DFoodTJ-Seg/img/" + fn) as f:
            im = Image.open(io.BytesIO(f.read()))
        d, a = dhash(im), ahash(im)
        dd = np.bitwise_count(sub_d ^ np.uint64(d))
        da = np.bitwise_count(sub_a ^ np.uint64(a))
        best = int(min(dd.min(), da.min()))
        j = int(dd.argmin() if dd.min() <= da.min() else da.argmin())
        rows.append({"seg_file": fn, "min_hamming": best,
                     "best_match": paths[j], "n_inst": int(r["n_inst"])})
        if best <= THRESH:
            hits.append((fn, best, paths[j]))
        if (i + 1) % 1000 == 0:
            print(f"   已比对 {i+1}/{len(man)}，当前命中 {len(hits)}", flush=True)

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["seg_file", "min_hamming", "best_match", "n_inst"])
        w.writeheader(); w.writerows(rows)

    print(f"\n[3/3] 阈值 THRESH={THRESH}/64  ->  疑似同源 {len(hits)} / {len(rows)}")
    for h in hits[:15]:
        print(f"   {h[0]}  距离={h[1]:2d}  <->  {h[2]}")
    dist = collections.Counter(r["min_hamming"] // 5 * 5 for r in rows)
    print("\n最小汉明距离分布(每5一档):", dict(sorted(dist.items())))
    print("结论写入:", OUT)


if __name__ == "__main__":
    main()
