# -*- coding: utf-8 -*-
"""
train_det_only.py — 仅训练检测模型（cls 已完成）
前置 : models/pretrained/yolov8n.pt（COCO 预训练，经 hf-mirror 下载后落盘）
"""
import os, sys, time, platform

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(BASE)

SEED = 2026
LOG = os.path.join(BASE, "models", "train_log.txt")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    import torch
    from ultralytics import YOLO
    log(f"det-only: torch={torch.__version__} cuda={torch.cuda.is_available()} "
        f"threads={torch.get_num_threads()}")
    m2 = YOLO(os.path.join(BASE, "models", "pretrained", "yolov8n.pt"))
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
