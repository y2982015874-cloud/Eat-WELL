# -*- coding: utf-8 -*-
"""
泄漏二次验证（严格）：对 check_seg_leak.py 命中的候选做像素级确认

dHash/aHash 对内容相近的不同照片也可能给出较小汉明距离，不够严格。
本脚本对候选对做「多方向 + 灰度 MAE(32x32)」复核：
  - Seg 导出脚本会竖图转正（可能会旋转），故比对时尝试 0/90/180/270 四个方向取最小 MAE
  - 输出 MAE 分布供阈值判定，并给出「确定同源(SAME)」清单
只读，不修改任何文件（结果写 reports/segreal_leakcheck_verified.csv）
"""
import os, csv, io, zipfile, collections
import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = r"D:/专业实训/DFoodTJ-Seg.zip"
LEAKCSV = os.path.join(BASE, "reports", "segreal_leakcheck.csv")
OUT = os.path.join(BASE, "reports", "segreal_leakcheck_verified.csv")
SOURCE_EXTREMES = True   # 一并抽取最相似/最不相似样例用于目视


def gray32(im):
    return np.asarray(im.convert("L").resize((32, 32), Image.BILINEAR), dtype=np.float32)


def best_mae(a, b):
    """a,b 为 32x32 灰度，返回 4 方向中的最小平均绝对误差"""
    best = 1e9
    for k in range(4):
        diff = np.abs(a - np.rot90(b, k))
        best = min(best, float(diff.mean()))
    return best


def main():
    rows = list(csv.DictReader(open(LEAKCSV, encoding="utf-8")))
    sub_paths = {}
    for split in ("train", "val", "test"):
        sd = os.path.join(BASE, "datasets", "dfoodtj_subset", split)
        if not os.path.isdir(sd):
            continue
        for cls in sorted(os.listdir(sd)):
            for fn in os.listdir(os.path.join(sd, cls)):
                if fn.lower().endswith(".png"):
                    sub_paths[f"{split}/{cls}/{fn}"] = os.path.join(sd, cls, fn)
    z = zipfile.ZipFile(ZIP)
    cand = [r for r in rows if int(r["min_hamming"]) <= 8]
    print(f"候选复核 {len(cand)} / {len(rows)}", flush=True)
    out = []
    cache = {}
    for i, r in enumerate(cand):
        p = sub_paths.get(r["best_match"])
        if p is None:
            out.append({**r, "mae": "", "verdict": "NO_FILE"}); continue
        if p not in cache:
            cache[p] = gray32(Image.open(p))
        with z.open("DFoodTJ-Seg/img/" + r["seg_file"]) as f:
            a = gray32(Image.open(io.BytesIO(f.read())))
        m = best_mae(a, cache[p])
        out.append({**r, "mae": round(m, 2)})
        if (i + 1) % 500 == 0:
            print(f"   {i+1}/{len(cand)}", flush=True)

    maes = np.array([o["mae"] for o in out if o["mae"] != ""], dtype=float)
    print("\nMAE(32x32灰度·4方向最小) 分布:")
    qs = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    print("  ", {f"p{q}": round(float(np.percentile(maes, q)), 2) for q in qs})
    hist, edges = np.histogram(maes, bins=[0, 3, 6, 10, 15, 20, 30, 50, 255])
    for c, lo, hi in zip(hist, edges[:-1], edges[1:]):
        print(f"   MAE [{lo:>3},{hi:>3}) : {c}")
    SAME = 6.0
    for o in out:
        if o["mae"] == "":
            o["verdict"] = "NO_FILE"
        else:
            o["verdict"] = "SAME" if o["mae"] <= SAME else "DIFFERENT"
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["seg_file", "min_hamming", "best_match", "n_inst", "mae", "verdict"])
        w.writeheader(); w.writerows(out)
    n_same = sum(1 for o in out if o["verdict"] == "SAME")
    print(f"\n阈值 MAE<={SAME} -> 确定同源 SAME = {n_same} / {len(cand)}（占全评测集 {100*n_same/len(rows):.1f}%）")
    print("样例(前12):")
    for o in sorted(out, key=lambda x: x["mae"] if x["mae"] != "" else 999)[:12]:
        print(f"   {o['seg_file']}  MAE={o['mae']:>6}  hamming={o['min_hamming']:>2}  {o['verdict']:<9} <-> {o['best_match']}")


if __name__ == "__main__":
    main()
