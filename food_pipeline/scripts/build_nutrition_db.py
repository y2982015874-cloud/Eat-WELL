# -*- coding: utf-8 -*-
"""
build_nutrition_db.py
用途   : 从 DFoodTJ-Nutr/density.xlsx 构建规范化营养数据库（不修改原始文件）
输入   : D:/workbuddy/kkk/DFoodTJ-Nutr/density.xlsx  (351 行)
输出   : data/nutrition_clean.csv        清洗后营养库（每100g口径为主）
         data/class_mapping.csv         351 类类别映射表（含 tier 标记）
         data/clean_log.txt             运行日志
依赖   : pandas, openpyxl
运行   : python scripts/build_nutrition_db.py
说明   : 原始 density.xlsx 保持只读；缺失值保留为空（NaN），不填 0。
"""
import os
import pandas as pd

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = r"D:/workbuddy/kkk/DFoodTJ-Nutr/density.xlsx"
OUT = os.path.join(BASE, "data")
LOG = os.path.join(OUT, "clean_log.txt")

# 与 DFoodTJ-Rec truth_list 类别 ID 对齐的 10 类高频菜品（PRD MI-01 口径）
TIER1 = {0: "米饭", 22: "馒头", 70: "饺子", 83: "红烧肉", 37: "青椒肉丝",
         40: "西红柿炒鸡蛋", 66: "清蒸鲈鱼", 82: "麻婆豆腐", 136: "蚝油西兰花", 74: "冬瓜汤"}

RAW_MAP = {  # 原始列 -> 清洗列
    "Food ID": "food_id",
    "Food Chinese Name": "name_zh",
    "Food English Name": "name_en",
    "Density (g/ml)": "density_g_ml",
    "Carbohydrate mass density (g/g)": "carb_g_per_100g",
    "Carbohydrate volume density (g/ml)": "carb_g_per_ml",
    "Fat mass density (g/g)": "fat_g_per_100g",
    "Fat volume density (g/ml)": "fat_g_per_ml",
    "Protein mass density (g/g)": "protein_g_per_100g",
    "Protein volume density (g/ml)": "protein_g_per_ml",
    "Fiber mass density (g/g)": "fiber_g_per_100g",
    "Fiber volume density (g/ml)": "fiber_g_per_ml",
    "Energy mass density (kcal/g)": "energy_kcal_per_100g",
    "Energy volume density (kcal/ml)": "energy_kcal_per_ml",
}

def main():
    os.makedirs(OUT, exist_ok=True)
    log = []
    def p(msg):
        print(msg); log.append(str(msg))

    raw = pd.read_excel(SRC)
    p(f"[1] 读取原始表: {SRC}  shape={raw.shape}")
    assert raw.shape[0] == 351, "原始表应为 351 行"
    assert list(raw.columns) == list(RAW_MAP), "原始列结构与预期不符"

    df = raw.rename(columns=RAW_MAP).copy()
    assert df["food_id"].tolist() == list(range(351)), "food_id 必须为 0..350 连续"
    p("[2] food_id 0..350 连续且无重复 —— 与 DFoodTJ-Rec 类别 ID 对齐通过")

    # R1 换算：源表质量口径为 g/g（每1克食物的含量），×100 转为"每100g"列语义
    MASS_COLS = ["carb_g_per_100g", "fat_g_per_100g", "protein_g_per_100g",
                 "fiber_g_per_100g", "energy_kcal_per_100g"]
    for c in MASS_COLS:
        df[c] = df[c] * 100.0
    p(f"[2b] R1 换算完成：质量密度列 ×100 转为每100g口径 {MASS_COLS}")

    dup_zh = df["name_zh"].duplicated(keep=False)
    p(f"[3] name_zh 重复记录数: {int(dup_zh.sum())}")
    if dup_zh.any():
        p(df.loc[dup_zh, ["food_id", "name_zh"]].to_string())

    num_cols = [c for c in df.columns if df[c].dtype.kind == "f"]
    p("[4] 各数值列缺失/异常统计:")
    for c in num_cols:
        na = int(df[c].isna().sum())
        neg = int((df[c] < 0).sum())
        zero = int((df[c] == 0).sum())
        p(f"    {c:28s} 缺失={na:3d}  负值={neg:3d}  零值={zero:3d}")
        if na:
            p("      缺失行 food_id: " + ",".join(map(str, df.loc[df[c].isna(), "food_id"].tolist())))

    # 能量守恒校验（Atwater 一般系数：碳水4/脂肪9/蛋白4/纤维2 kcal/g，允许 ±20%）
    calc = 4 * df["carb_g_per_100g"] + 9 * df["fat_g_per_100g"] + 4 * df["protein_g_per_100g"] + 2 * df["fiber_g_per_100g"]
    dev = (df["energy_kcal_per_100g"] - calc).abs() / df["energy_kcal_per_100g"].replace(0, pd.NA)
    bad = dev > 0.20
    p(f"[5] 能量守恒校验: 偏差>20% 的记录 {int(bad.sum())} 条")
    p("    （来源表能量为实测值，含酒精/有机酸等 Atwater 特例，偏差仅作提示不作剔除）")

    core = ["carb_g_per_100g", "fat_g_per_100g", "protein_g_per_100g", "energy_kcal_per_100g"]
    df["data_status"] = df[core].notna().all(axis=1).map({True: "complete", False: "partial"})
    df["source"] = "DFoodTJ-Nutr/density.xlsx (Aqua-Calc; Mint Health)"
    df["tier"] = df["food_id"].map(lambda i: 1 if i in TIER1 else 2)
    df["tier1_name_check"] = df["food_id"].map(lambda i: TIER1.get(i, ""))
    mismatch = df[(df.tier == 1) & (df.tier1_name_check != df.name_zh)]
    p(f"[6] tier1 名称校验不一致: {len(mismatch)} 条")
    assert len(mismatch) == 0, "tier1 的 Food ID 与名称不匹配，请核对 TIER1 定义"

    cols = ["food_id", "name_zh", "name_en", "tier", "density_g_ml",
            "carb_g_per_100g", "fat_g_per_100g", "protein_g_per_100g", "fiber_g_per_100g",
            "energy_kcal_per_100g", "carb_g_per_ml", "fat_g_per_ml", "protein_g_per_ml",
            "fiber_g_per_ml", "energy_kcal_per_ml", "data_status", "source"]
    df[cols].to_csv(os.path.join(OUT, "nutrition_clean.csv"), index=False, encoding="utf-8-sig")
    p(f"[7] 写出 nutrition_clean.csv  rows={len(df)}")

    stats = os.path.join(os.path.expanduser("~"), "work_df", "class_stats.csv")
    cm = df[["food_id", "name_zh", "name_en", "tier"]].copy()
    cm["tier1_name_check"] = df["tier1_name_check"]
    if os.path.exists(stats):
        s = pd.read_csv(stats)[["Food ID", "img_total"]].rename(columns={"Food ID": "food_id"})
        cm = cm.merge(s, on="food_id", how="left")
        p(f"[8] 合并图像统计: {len(s)} 类")
    else:
        cm["img_total"] = pd.NA
        p("[8] 未找到 class_stats.csv，img_total 留空")
    cm.to_csv(os.path.join(OUT, "class_mapping.csv"), index=False, encoding="utf-8-sig")
    p(f"[9] 写出 class_mapping.csv  rows={len(cm)}")

    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    p(f"[10] 日志写入 {LOG}")

if __name__ == "__main__":
    main()
