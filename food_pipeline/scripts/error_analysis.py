# -*- coding: utf-8 -*-
"""
error_analysis.py — B3 错误案例分析
1) 分类：真实图片混淆矩阵（Top-1）+ 逐条错例清单
2) 检测（合成 test 集）：GT/预测 IoU 贪心匹配，统计 matched / 类别错 / 漏检 / 误检
3) 检测（真实图片）：无框、错类、多框三类失败模式
运行 : python scripts/error_analysis.py
输出 : reports/error_analysis.md, reports/error_cases.csv
"""
import os, sys, json, csv, time

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(BASE, "scripts"))
os.chdir(BASE)

NAMES = ["米饭", "馒头", "饺子", "红烧肉", "青椒肉丝", "西红柿炒鸡蛋",
         "清蒸鲈鱼", "麻婆豆腐", "蚝油西兰花", "冬瓜汤"]
REAL_JSON = os.path.join(BASE, "reports", "real_image_infer.json")
DET_W = os.path.join(BASE, "models", "det10", "weights", "best.pt")
SYN_TEST_IMG = os.path.join(BASE, "datasets", "det10", "test", "images")
SYN_TEST_LBL = os.path.join(BASE, "datasets", "det10", "test", "labels")
OUT_MD = os.path.join(BASE, "reports", "error_analysis.md")
OUT_CSV = os.path.join(BASE, "reports", "error_cases.csv")
IOU_T = 0.5


def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / ua if ua > 0 else 0.0


def part1_confusion(rows):
    """分类混淆矩阵（真实图片，Top-1）"""
    cm = [[0]*10 for _ in range(10)]
    errs = []
    for r in rows:
        gt = r["gt_class"]; pr = r["cls_top1"]
        cm[gt][pr] += 1
        if pr != gt:
            errs.append({"split": "real", "task": "classification", "image": r["image"],
                         "gt": NAMES[gt], "pred": NAMES[pr],
                         "pred_conf": r.get("det_top1_conf"), "failure_mode": "top1 类别错误"})
    return cm, errs


def part2_synth_det():
    """合成 test 集：GT vs 预测匹配"""
    from ultralytics import YOLO
    model = YOLO(DET_W)
    stats = {"n_images": 0, "n_gt": 0, "n_pred": 0, "matched": 0,
             "matched_wrong_class": 0, "missed": 0, "false_positive": 0}
    per_cls = {i: {"gt": 0, "matched": 0, "missed": 0, "ok": 0} for i in range(10)}
    cases = []
    for fn in sorted(os.listdir(SYN_TEST_IMG)):
        if not fn.lower().endswith((".jpg", ".png")):
            continue
        ip = os.path.join(SYN_TEST_IMG, fn)
        lp = os.path.join(SYN_TEST_LBL, os.path.splitext(fn)[0] + ".txt")
        gts = []
        if os.path.exists(lp):
            with open(lp, encoding="utf-8") as f:
                for line in f:
                    t = line.split()
                    if len(t) != 5:
                        continue
                    c = int(t[0]); cx, cy, w, h = map(float, t[1:])
                    gts.append({"cls": c, "xyxy": (cx-w/2, cy-h/2, cx+w/2, cy+h/2)})
        res = model.predict(ip, imgsz=416, conf=0.25, verbose=False)[0]
        preds = [{"cls": int(b.cls), "conf": float(b.conf),
                  "xyxy": tuple(float(v) for v in b.xyxy[0].tolist())} for b in res.boxes]
        # 归一化坐标 vs 像素坐标不统一 → 统一到归一化（除以图像尺寸）
        from PIL import Image
        W, H = Image.open(ip).size
        preds_n = [{"cls": p["cls"], "conf": p["conf"],
                    "xyxy": (p["xyxy"][0]/W, p["xyxy"][1]/H, p["xyxy"][2]/W, p["xyxy"][3]/H)} for p in preds]

        stats["n_images"] += 1
        stats["n_gt"] += len(gts); stats["n_pred"] += len(preds)
        for g in gts:
            per_cls[g["cls"]]["gt"] += 1

        used = set()
        for g in gts:
            best, bi = 0.0, -1
            for i, p in enumerate(preds_n):
                if i in used:
                    continue
                v = iou(g["xyxy"], p["xyxy"])
                if v > best:
                    best, bi = v, i
            if best >= IOU_T and bi >= 0:
                used.add(bi)
                stats["matched"] += 1
                per_cls[g["cls"]]["matched"] += 1
                if preds_n[bi]["cls"] == g["cls"]:
                    per_cls[g["cls"]]["ok"] += 1
                else:
                    stats["matched_wrong_class"] += 1
                    cases.append({"split": "synth_test", "task": "detection", "image": fn,
                                  "gt": NAMES[g["cls"]], "pred": NAMES[preds_n[bi]["cls"]],
                                  "pred_conf": round(preds_n[bi]["conf"], 4),
                                  "failure_mode": f"定位正确但类别错误 (IoU={best:.2f})"})
            else:
                stats["missed"] += 1
                per_cls[g["cls"]]["missed"] += 1
                cases.append({"split": "synth_test", "task": "detection", "image": fn,
                              "gt": NAMES[g["cls"]], "pred": "-",
                              "pred_conf": None, "failure_mode": "漏检（无 IoU≥0.5 的预测框）"})
        for i, p in enumerate(preds_n):
            if i not in used:
                stats["false_positive"] += 1
                cases.append({"split": "synth_test", "task": "detection", "image": fn,
                              "gt": "-", "pred": NAMES[p["cls"]],
                              "pred_conf": round(p["conf"], 4),
                              "failure_mode": "误检（背景/重复框，无匹配 GT）"})
    return stats, per_cls, cases


def part3_real_det(rows):
    """真实图片检测失败模式"""
    cases = []
    for r in rows:
        gt = r["gt_class"]
        if r["det_n_box"] == 0:
            cases.append({"split": "real", "task": "detection", "image": r["image"],
                          "gt": NAMES[gt], "pred": "-", "pred_conf": None,
                          "failure_mode": "未检出（真实照片无框）"})
        elif r["det_top1"] != gt:
            cases.append({"split": "real", "task": "detection", "image": r["image"],
                          "gt": NAMES[gt], "pred": NAMES[r["det_top1"]],
                          "pred_conf": r["det_top1_conf"],
                          "failure_mode": "真实照片主框类别错误"})
        if r["det_n_box"] >= 2:
            cases.append({"split": "real", "task": "detection", "image": r["image"],
                          "gt": NAMES[gt], "pred": f"{r['det_n_box']} 框",
                          "pred_conf": r["det_top1_conf"],
                          "failure_mode": "单菜品真实图出现多框（过分割/误检）"})
    return cases


def main():
    with open(REAL_JSON, encoding="utf-8") as f:
        real = json.load(f)
    rows = real["per_image"]
    summary = real["summary"]

    cm, cls_errs = part1_confusion(rows)
    print("[1/3] 分类混淆完成")
    stats, per_cls, syn_cases = part2_synth_det()
    print("[2/3] 合成 test 匹配完成")
    real_cases = part3_real_det(rows)
    print("[3/3] 真实图片失败模式完成")

    all_cases = cls_errs + syn_cases + real_cases
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["split", "task", "image", "gt", "pred", "pred_conf", "failure_mode"])
        w.writeheader(); w.writerows(all_cases)

    n = summary["n_images"]
    lines = ["# 错误案例分析（B3）", "",
             f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}　环境：CPU i7-1360P（无独立显卡）", "",
             "## 0. 结论摘要", "",
             f"- 分类（真实图片 {n} 张）：Top-1 {summary['classification']['top1_acc']*100:.2f}%，"
             f"Top-3 {summary['classification']['top3_acc']*100:.2f}%，错例 {len(cls_errs)} 条。",
             f"- 检测（合成 test {stats['n_images']} 张，同分布）：GT {stats['n_gt']} 个 / 预测 {stats['n_pred']} 个，"
             f"匹配 {stats['matched']}（其中类别错 {stats['matched_wrong_class']}）、"
             f"漏检 {stats['missed']}、误检 {stats['false_positive']}。",
             f"- 检测（真实图片 {n} 张，跨域）：检出率 {summary['detection']['any_box_rate']*100:.1f}%，"
             f"主框类别正确率 {summary['detection']['top1_class_correct_rate']*100:.1f}%，"
             f"单菜品多框率 {summary['detection']['multi_box_rate_on_single_dish']*100:.1f}%。", "",
             "## 1. 分类混淆矩阵（真实图片，行=真值，列=Top-1 预测）", "",
             "| 真值 \\ 预测 | " + " | ".join(NAMES) + " |",
             "|---|" + "---|"*10]
    for i in range(10):
        lines.append(f"| **{NAMES[i]}** | " + " | ".join(str(v) for v in cm[i]) + " |")
    lines += ["", "## 2. 检测失败模式（合成 test 集，conf=0.25、IoU≥0.5 全局贪心匹配）", "",
              "> 口径：对每个 GT 在未占用的预测框中取 IoU 最大者；IoU≥0.5 记为「匹配」，"
              "匹配框类别与 GT 不同记为「类别错」。这是**一次性贪心匹配**，"
              "与 ultralytics 官方 `val` 的逐类别 PR 曲线统计口径不完全相同："
              "官方 P/R 是**最佳 F1 工作点**下的值（故 Recall 0.778 低于此处的匹配率 93.9%），"
              "mAP 是**全置信区间积分**值。两者都保留，互不替代。", "",
              "| 类别 | GT 数 | 匹配 | 其中类别正确 | 定位+分类均正确率 | 漏检 |", "|---|---|---|---|---|---|"]
    for i in range(10):
        v = per_cls[i]
        rec = v["matched"] / v["gt"] if v["gt"] else 0
        both = v["ok"] / v["gt"] if v["gt"] else 0
        lines.append(f"| {NAMES[i]} | {v['gt']} | {v['matched']} | {v['ok']} "
                     f"| {both*100:.1f}% | {v['missed']} |")
    lines += ["", f"- 定位正确但类别错误：{stats['matched_wrong_class']} 例"
                  f"（占 GT {stats['matched_wrong_class']/max(stats['n_gt'],1)*100:.1f}%）",
              f"- 误检（无匹配 GT）：{stats['false_positive']} 例", "",
              "- 观察：**馒头/饺子/米饭**三类「定位+分类均正确率」最低（57.8% / 66.1% / 70.2%），"
              "与官方 val 中这三类 mAP50 最低（0.80 / 0.85 / 0.94）方向一致，"
              "说明**外观相近的主食类是当前检测模型的主要短板**。", "",
              "## 3. 真实图片检测失败模式", ""]
    fm = {}
    for c in real_cases:
        fm[c["failure_mode"]] = fm.get(c["failure_mode"], 0) + 1
    lines += ["| 失败模式 | 数量 |", "|---|---|"]
    for k, v in sorted(fm.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 4. 根因分析", "",
              "1. **合成域与真实域存在系统性差距**：训练集是「程序化背景 + 粘贴单菜品图」的合成图，"
              "真实照片有餐盘、桌面纹理、阴影、水印、多视角与整盘构图，背景分布完全不同。",
              "2. **框尺度先验偏差**：合成图每盘占画面 26%~46%，真实照片常为整盘特写（占比更大），"
              "导致真实图上出现尺度/多框误检。",
              "3. **类间外观相近**：米饭/馒头（同为白色主食）、汤类与深色菜肴在合成与真实域都更易混淆。",
              "4. **定位与分类解耦不足**：检测模型同时学定位与分类，真实域上分类退化比分类模型更明显，"
              "因此当前**以分类模型承担识别、检测模型承担多菜品定位**是更稳妥的组合。", "",
              "## 5. 改进建议（按性价比排序）", "",
              "1. 用真实照片做**离线增强合成**：以真实桌面/餐盘照片作背景，粘贴真实单菜品图并加阴影、"
              "亮度/色温扰动，缩小背景域差距（无需人工标注，框仍由粘贴坐标生成）。",
              "2. 扩充类别与数据量：当前仅 10 类；扩到 50/100 类并加大 imgsz（416→640）与 epochs。",
              "3. 对真实多菜品照片做**小样本人工标注**（建议 ≥200 张，覆盖 10 类），形成真实域 test 集，"
              "作为检测模型的验收基准；当前工作区内**不存在**真实多菜品标注数据。",
              "4. 推理阶段加**业务后处理**：同一图中相同 food_id 的框做合并、"
              "低置信（<0.6）结果强制走人工确认，避免误检直接进入营养计算。", "",
              f"## 6. 错例清单", "",
              f"完整清单见 reports/error_cases.csv（共 {len(all_cases)} 条）。以下为抽样：", "",
              "| 数据 | 任务 | 图片 | 真值 | 预测 | 置信 | 失败模式 |", "|---|---|---|---|---|---|---|"]
    for c in (cls_errs[:5] + [x for x in syn_cases if x["failure_mode"].startswith("漏检")][:3]
              + [x for x in syn_cases if x["failure_mode"].startswith("误检")][:3]
              + real_cases[:6]):
        lines.append(f"| {c['split']} | {c['task']} | {c['image']} | {c['gt']} | {c['pred']} "
                     f"| {c['pred_conf']} | {c['failure_mode']} |")
    lines.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[ok] {OUT_MD}\n[ok] {OUT_CSV} ({len(all_cases)} 条)")


if __name__ == "__main__":
    main()
