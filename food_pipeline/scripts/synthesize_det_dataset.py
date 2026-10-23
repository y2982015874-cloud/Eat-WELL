# -*- coding: utf-8 -*-
"""
synthesize_det_dataset.py
用途   : 从 DFoodTJ-Rec 单菜品图合成"一图多菜品"检测数据集（YOLO 格式）
         —— 项目当前缺少真实中餐多目标标注，经确认采用合成方案（已在 data_inventory.md 矛盾#1 声明）
输入   : datasets/dfoodtj_subset/<train|val|test>/<类别3位ID>/*.png  (extract_subset.py v2 产出)
输出   : datasets/det10/{train,val,test}/{images,labels}
         datasets/det10/data.yaml
         datasets/det10_synth_manifest.csv   逐图合成参数（可复现/可追溯）
         datasets/det10_preview/             抽样可视化（人工核查用）
依赖   : pillow, pandas
运行   : python scripts/synthesize_det_dataset.py
说明   : 贴图为矩形裁块（无 mask），属于已知域差距；所有真值框来自粘贴坐标，非人工标注。
         v2: train/val/test 合成图分别仅使用对应 split 的源图，杜绝图像级泄漏。
"""
import os, random, math
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import pandas as pd

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBSET = os.path.join(BASE, "datasets", "dfoodtj_subset")
OUT = os.path.join(BASE, "datasets", "det10")
CANVAS = 640
N = {"train": 1600, "val": 200, "test": 200}

CLASSES = [(0, "米饭"), (22, "馒头"), (70, "饺子"), (83, "红烧肉"), (37, "青椒肉丝"),
           (40, "西红柿炒鸡蛋"), (66, "清蒸鲈鱼"), (82, "麻婆豆腐"), (136, "蚝油西兰花"), (74, "冬瓜汤")]

def make_background(rng):
    """程序化生成餐桌面风格背景（径向渐变 + 噪点），可复现"""
    base = rng.choice([(214, 196, 172), (196, 178, 156), (228, 214, 196), (176, 158, 138)])
    img = Image.new("RGB", (CANVAS, CANVAS))
    px = img.load()
    cx, cy = CANVAS / 2, CANVAS / 2
    maxd = math.hypot(cx, cy)
    for y in range(CANVAS):
        for x in range(0, CANVAS, 2):
            d = math.hypot(x - cx, y - cy) / maxd
            f = 1.0 - 0.28 * d
            c = tuple(int(v * f) for v in base)
            px[x, y] = c
            if x + 1 < CANVAS:
                px[x + 1, y] = c
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    # 轻噪点
    noise = Image.effect_noise((CANVAS, CANVAS), 8).convert("L")
    img = Image.composite(ImageEnhance.Brightness(img).enhance(1.04), img, noise.point(lambda v: 255 if v > 235 else 0))
    return img

def paste_object(canvas, obj_img, rng):
    """把单菜图缩放+旋转后贴到画布，返回 (xyxy 归一化框)"""
    W = canvas.width
    side = rng.randint(int(CANVAS * 0.26), int(CANVAS * 0.46))
    obj = obj_img.convert("RGB")
    # 等比缩放到 side 短边
    w, h = obj.size
    scale = side / min(w, h)
    obj = obj.resize((max(32, int(w * scale)), max(32, int(h * scale))), Image.BILINEAR)
    ang = rng.uniform(-15, 15)
    obj_r = obj.rotate(ang, expand=True, fillcolor=None, resample=Image.BILINEAR)
    # 允许少量越界（模拟真实拍摄裁切）
    ox = rng.randint(-30, max(0, CANVAS - obj_r.width + 30))
    oy = rng.randint(-30, max(0, CANVAS - obj_r.height + 30))
    mask = Image.new("L", obj_r.size, 255)
    canvas.paste(obj_r, (ox, oy), mask)
    # 轴对齐外接框（限制在画布内）
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(CANVAS, ox + obj_r.width), min(CANVAS, oy + obj_r.height)
    return [x0 / W, y0 / CANVAS, x1 / W, y1 / CANVAS], (ox, oy, ang, side)

def main():
    rng = random.Random(20261023)
    for s in ["train", "val", "test"]:
        os.makedirs(os.path.join(OUT, s, "images"), exist_ok=True)
        os.makedirs(os.path.join(OUT, s, "labels"), exist_ok=True)

    names = [n for _, n in CLASSES]
    with open(os.path.join(OUT, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(f"path: {OUT}\ntrain: train/images\nval: val/images\ntest: test/images\nnc: {len(CLASSES)}\n")
        f.write("names:\n")
        for i, n in enumerate(names):
            f.write(f"  {i}: {n}\n")

    manifest = []
    for split in ["train", "val", "test"]:
        pools = {}
        for fid, _ in CLASSES:
            d = os.path.join(SUBSET, split, f"{fid:03d}")
            files = [os.path.join(d, f) for f in sorted(os.listdir(d))]
            assert files, f"split {split} 类 {fid} 源图为空"
            pools[str(fid)] = files
        for k in range(N[split]):
            n_obj = rng.choices([1, 2, 3, 4], weights=[0.30, 0.38, 0.22, 0.10])[0]
            # 优先不重复类别；同类别允许不同实例（同图不重复同一文件）
            cls_pick = rng.sample([fid for fid, _ in CLASSES], n_obj)
            canvas = make_background(rng)
            boxes, used = [], []
            for fid in cls_pick:
                src = rng.choice(pools[str(fid)])
                if src in used:  # 同图防重复
                    cands = [s for s in pools[str(fid)] if s not in used] or pools[str(fid)]
                    src = rng.choice(cands)
                used.append(src)
                try:
                    obj = Image.open(src); obj.load()
                except Exception as e:
                    print("SKIP bad img", src, e); continue
                box, params = paste_object(canvas, obj, rng)
                boxes.append((fid, box, src, params))
            stem = f"{split}_{k:05d}"
            canvas.save(os.path.join(OUT, split, "images", stem + ".jpg"), quality=90)
            with open(os.path.join(OUT, split, "labels", stem + ".txt"), "w", encoding="utf-8") as f:
                for fid, box, _, _ in boxes:
                    cx = (box[0] + box[2]) / 2; cy = (box[1] + box[3]) / 2
                    w = box[2] - box[0]; h = box[3] - box[1]
                    f.write(f"{[fid for fid,_ in CLASSES].index(fid)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
            for fid, box, src, params in boxes:
                manifest.append({"image": stem + ".jpg", "split": split, "food_id": fid,
                                 "n_objects_in_img": len(boxes), "src": os.path.relpath(src, BASE),
                                 "ox": params[0], "oy": params[1], "rot_deg": round(params[2], 2), "side": params[3]})
        print(f"[{split}] {N[split]} 张合成图完成")

    mf = pd.DataFrame(manifest)
    mf.to_csv(os.path.join(OUT, "..", "det10_synth_manifest.csv"), index=False, encoding="utf-8-sig")
    print("[manifest] rows =", len(mf))
    print(mf.groupby(["split", "n_objects_in_img"]).size().unstack(fill_value=0).to_string())

    # 抽样可视化（供人工核查）
    prev = os.path.join(OUT, "..", "det10_preview"); os.makedirs(prev, exist_ok=True)
    for split in ["train", "val", "test"]:
        imgs = sorted(os.listdir(os.path.join(OUT, split, "images")))
        for stem in imgs[:3]:
            im = Image.open(os.path.join(OUT, split, "images", stem)).convert("RGB")
            from PIL import ImageDraw, ImageFont
            dr = ImageDraw.Draw(im)
            lab = open(os.path.join(OUT, split, "labels", stem.replace(".jpg", ".txt")), encoding="utf-8").read().splitlines()
            for line in lab:
                c, cx, cy, w, h = line.split()
                cx, cy, w, h = float(cx), float(cy), float(w), float(h)
                dr.rectangle([ (cx-w/2)*CANVAS, (cy-h/2)*CANVAS, (cx+w/2)*CANVAS, (cy+h/2)*CANVAS ], outline=(255,0,0), width=3)
                dr.text(((cx-w/2)*CANVAS+2, (cy-h/2)*CANVAS+2), names[int(c)], fill=(255,255,0))
            im.save(os.path.join(prev, f"{split}_{stem}"))
    print("[preview] 已输出抽样可视化到", prev)

if __name__ == "__main__":
    main()
