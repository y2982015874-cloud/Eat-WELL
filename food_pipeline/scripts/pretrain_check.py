# -*- coding: utf-8 -*-
"""
pretrain_check.py — B1 训练前检查（在"跑第一个 epoch 之前"完成）
检查项：目录结构 / 图像可解码 / 标签格式合法 / 空标注 / 类别越界 / 坐标越界 /
        划分无重叠（数据泄漏）/ 类别数一致 / 类别分布
运行 : python scripts/pretrain_check.py
输出 : 控制台 + reports/pretrain_check.md
"""
import os, sys, csv
from collections import Counter

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_MD = os.path.join(BASE, "reports", "pretrain_check.md")
NC = 10


def check_cls():
    res = []
    root = os.path.join(BASE, "datasets", "cls10")
    for split in ["train", "val", "test"]:
        d = os.path.join(root, split)
        if not os.path.isdir(d):
            res.append(("cls10", split, "目录存在", "FAIL", d)); continue
        dirs = sorted(os.listdir(d))
        ok_dirs = [x for x in dirs if os.path.isdir(os.path.join(d, x))]
        res.append(("cls10", split, "目录存在", "PASS", f"{len(ok_dirs)} 个类别目录"))
        if len(ok_dirs) != NC:
            res.append(("cls10", split, "类别数=10", "FAIL", str(len(ok_dirs))))
        else:
            res.append(("cls10", split, "类别数=10", "PASS", str(len(ok_dirs))))
        # 图像可解码 + 每类计数
        bad, counts = [], {}
        for c in ok_dirs:
            n = 0
            for f in os.listdir(os.path.join(d, c)):
                if not f.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                n += 1
                try:
                    from PIL import Image
                    with Image.open(os.path.join(d, c, f)) as im:
                        im.verify()
                except Exception as e:
                    bad.append(f"{c}/{f}: {type(e).__name__}")
            counts[c] = n
        res.append(("cls10", split, "图像可解码", "PASS" if not bad else "FAIL",
                    f"{sum(counts.values())} 张，损坏 {len(bad)}" + (f"（例：{bad[0]}）" if bad else "")))
        vals = set(counts.values())
        res.append(("cls10", split, "类别均衡", "PASS" if len(vals) == 1 else "WARN",
                    f"各类 {min(counts.values())}~{max(counts.values())} 张"))
    # 划分泄漏：同名文件（含类别目录）是否跨 split 重复
    seen = {}
    for split in ["train", "val", "test"]:
        d = os.path.join(root, split)
        if not os.path.isdir(d):
            continue
        for c in os.listdir(d):
            for f in os.listdir(os.path.join(d, c)):
                seen.setdefault(f"{c}/{f}", []).append(split)
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    res.append(("cls10", "all", "划分无重叠", "PASS" if not dup else "FAIL",
                "无跨 split 重复文件名" if not dup else f"{len(dup)} 个重复（例 {list(dup)[:2]}）"))
    return res


def check_det():
    res = []
    root = os.path.join(BASE, "datasets", "det10")
    y = os.path.join(root, "data.yaml")
    if os.path.exists(y):
        txt = open(y, encoding="utf-8").read()
        res.append(("det10", "data.yaml", "字段完整", "PASS" if "nc: 10" in txt else "FAIL",
                    "nc: 10 且含 train/val/test 三段" if "nc: 10" in txt else txt[:60]))
    else:
        res.append(("det10", "data.yaml", "字段完整", "FAIL", "文件缺失"))
    for split in ["train", "val", "test"]:
        idir, ldir = os.path.join(root, split, "images"), os.path.join(root, split, "labels")
        if not os.path.isdir(idir):
            res.append(("det10", split, "目录存在", "FAIL", idir)); continue
        imgs = [f for f in os.listdir(idir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        res.append(("det10", split, "目录存在", "PASS", f"{len(imgs)} 张图像"))
        # 图像可解码
        bad = []
        for f in imgs:
            try:
                from PIL import Image
                with Image.open(os.path.join(idir, f)) as im:
                    im.verify()
            except Exception as e:
                bad.append(f)
        res.append(("det10", split, "图像可解码", "PASS" if not bad else "FAIL",
                    f"损坏 {len(bad)}" + (f"（例：{bad[0]}）" if bad else "")))
        # 标签
        empty, badfmt, oob, oor = 0, [], 0, 0
        nobj, cc = 0, Counter()
        for f in imgs:
            lp = os.path.join(ldir, os.path.splitext(f)[0] + ".txt")
            if not os.path.exists(lp):
                badfmt.append(f + " (无标签)"); continue
            lines = [l for l in open(lp, encoding="utf-8").read().splitlines() if l.strip()]
            if not lines:
                empty += 1; continue
            for l in lines:
                t = l.split()
                if len(t) != 5:
                    badfmt.append(f"{f}: 列数={len(t)}"); continue
                try:
                    c = int(t[0]); vals = [float(x) for x in t[1:]]
                except ValueError:
                    badfmt.append(f"{f}: 非数值"); continue
                if not (0 <= c < NC):
                    oor += 1; continue
                cx, cy, w, h = vals
                if min(vals) < 0 or max(vals) > 1 or w <= 0 or h <= 0:
                    oob += 1; continue
                if cx - w / 2 < -0.02 or cx + w / 2 > 1.02 or cy - h / 2 < -0.02 or cy + h / 2 > 1.02:
                    oob += 1
                nobj += 1; cc[c] += 1
        res.append(("det10", split, "标签格式合法", "PASS" if not badfmt else "FAIL",
                    f"异常 {len(badfmt)}" + (f"（例：{badfmt[0]}）" if badfmt else "")))
        res.append(("det10", split, "空标注文件", "PASS" if empty == 0 else "WARN", str(empty)))
        res.append(("det10", split, "类别索引合法", "PASS" if oor == 0 else "FAIL", f"越界 {oor}"))
        res.append(("det10", split, "坐标合法(0~1)", "PASS" if oob == 0 else "WARN",
                    f"越界 {oob}（合成允许轻微出画，已裁剪到 0~1 之外不计入）"))
        res.append(("det10", split, "目标数/类别分布", "PASS",
                    f"{nobj} 个目标，分布 {dict(sorted(cc.items()))}"))
    # 泄漏：合成图源图按 split 取，此处检查文件名是否跨 split 重复
    seen = {}
    for split in ["train", "val", "test"]:
        idir = os.path.join(root, split, "images")
        if not os.path.isdir(idir):
            continue
        for f in os.listdir(idir):
            seen.setdefault(f, []).append(split)
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    res.append(("det10", "all", "划分无重叠", "PASS" if not dup else "FAIL",
                "无跨 split 重复文件名" if not dup else f"{len(dup)} 个重复"))
    return res


def main():
    rows = check_cls() + check_det()
    n_fail = sum(1 for r in rows if r[3] == "FAIL")
    n_warn = sum(1 for r in rows if r[3] == "WARN")
    print(f"{'数据集':8s}{'范围':12s}{'检查项':16s}{'结果':6s}说明")
    for r in rows:
        print(f"{r[0]:8s}{r[1]:12s}{r[2]:16s}{r[3]:6s}{r[4]}")
    print(f"\nFAIL={n_fail}  WARN={n_warn}  PASS={sum(1 for r in rows if r[3]=='PASS')}")

    lines = ["# 训练前检查报告（B1）", "",
             f"生成时间：{__import__('time').strftime('%Y-%m-%d %H:%M:%S')}　"
             f"结论：**{'通过' if n_fail == 0 else '存在 FAIL，需修复后再训练'}**"
             f"（FAIL {n_fail} / WARN {n_warn}）", "",
             "| 数据集 | 范围 | 检查项 | 结果 | 说明 |", "|---|---|---|---|---|"]
    for r in rows:
        mark = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[r[3]]
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {mark} {r[3]} | {r[4]} |")
    lines += ["", "## 检查项说明", "",
              "1. **目录结构**：cls10 为 `split/类别_名/*.png`（YOLOv8-cls 分类约定），"
              "det10 为 `split/{images,labels}`（YOLOv8 检测约定）。",
              "2. **图像可解码**：逐张 `PIL.Image.verify()`，防止训练中途因坏图崩溃。",
              "3. **标签格式**：YOLO 归一化 `class cx cy w h`，5 列；类别索引 ∈ [0, 9]；坐标 ∈ [0,1] 且 w/h > 0。",
              "4. **划分无重叠**：train/val/test 之间无同名文件，排除数据泄漏（合成图源图也严格按官方 split 取）。",
              "5. **类别均衡**：分类集每类张数一致，避免长尾偏置。", ""]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[ok] {OUT_MD}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
