# -*- coding: utf-8 -*-
"""
train_models.py
用途   : CPU 环境串行训练两个模型（工作包 B2）
         1) YOLOv8n-cls  —— 10 类高频菜品分类，支撑 PRD MI-01 Top-3 口径
         2) YOLOv8n-det  —— 合成多菜品检测，支撑"一图多食物"定位
输入   : datasets/cls10, datasets/det10
输出   : models/cls10/  models/det10/  （含 weights/best.pt、results.csv、args.yaml）
         models/train_log.txt
依赖   : ultralytics (torch 2.5.0+cpu)
运行   : python scripts/train_models.py
说明   : 本机无 NVIDIA GPU（Intel Iris Xe 核显），device=cpu；
         规模经确认采用 10 类试点（见 reports/data_quality_report.md 矛盾#3）。
"""
import os, sys, time, platform

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

SEED = 2026
LOG = os.path.join(BASE, "models", "train_log.txt")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    os.makedirs(os.path.join(BASE, "models"), exist_ok=True)
    import torch
    from ultralytics import YOLO
    log(f"torch={torch.__version__} cuda={torch.cuda.is_available()} "
        f"cpu={platform.processor()} threads={torch.get_num_threads()}")

    # ---------- 1) 分类 ----------
    # 预训练权重已随项目落盘在 models/pretrained/，走本地路径即可离线训练
    PRETRAINED = os.path.join(BASE, "models", "pretrained")
    log("== 训练 YOLOv8n-cls (datasets/cls10) ==")
    m1 = YOLO(os.path.join(PRETRAINED, "yolov8n-cls.pt"))
    m1.train(
        data=os.path.join(BASE, "datasets", "cls10"),
        epochs=30, imgsz=224, batch=64, seed=SEED, device="cpu",
        workers=2, project=os.path.join(BASE, "models"), name="cls10",
        exist_ok=True, verbose=True, patience=10,
    )
    log("cls 训练完成")

    # ---------- 2) 检测 ----------
    log("== 训练 YOLOv8n-det (datasets/det10) ==")
    m2 = YOLO(os.path.join(PRETRAINED, "yolov8n.pt"))
    m2.train(
        data=os.path.join(BASE, "datasets", "det10", "data.yaml"),
        epochs=25, imgsz=416, batch=8, seed=SEED, device="cpu",
        workers=2, project=os.path.join(BASE, "models"), name="det10",
        exist_ok=True, verbose=True, patience=10,
    )
    log("det 训练完成")
    log("ALL TRAINING DONE")

if __name__ == "__main__":
    main()
