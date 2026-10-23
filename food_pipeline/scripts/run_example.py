# -*- coding: utf-8 -*-
"""
run_example.py — 工作包 C 运行示例（固定输入，结果可复现）
运行 : python scripts/run_example.py
输出 : 控制台展示 查询→计算→推荐→预警 全链路；同时写出 reports/wp_c_example_output.json
"""
import os, sys, json
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)

from nutrition import (NutritionDB, NutritionCalculator, WeightSource,
                       RecommendationEngine, AlertEngine, GoalType, ActivityLevel)

def main():
    db = NutritionDB()
    calc = NutritionCalculator(db)
    print(f"[1] 营养库加载完成: {len(db)} 条（food_id 0..350）")

    # ---- C1 查询示例 ----
    for fid in (0, 83, 40, 152):
        r = db.get(fid)
        print(f"    food_id={fid:3d}  {r.name_zh:8s}  {r.energy_kcal_per_100g:7.1f} kcal/100g  "
              f"蛋白 {r.protein_g_per_100g:5.2f}g  状态 {r.data_status}")

    # ---- C2 整餐计算示例：米饭200g(user_input) + 红烧肉150g(份量参考×1) + 冬瓜汤250g(模型估算) ----
    meal = calc.calc_meal([
        {"food_id": 0,  "weight_g": 200, "weight_source": "user_input"},
        {"food_id": 83, "weight_source": "portion_reference", "portions": 1.0},
        {"food_id": 74, "weight_g": 250, "weight_source": "model_estimate"},
    ])
    print("\n[2] 整餐计算:")
    for it in meal.items:
        print(f"    {it.food_name:8s} {it.weight_g:7.1f}g [{it.weight_source}]  "
              f"热量 {it.energy_kcal:7.2f} kcal  蛋白 {it.protein_g}g  脂肪 {it.fat_g}g  碳水 {it.carb_g}g")
    print(f"    合计: {meal.totals}")
    print(f"    整餐状态: {meal.status}")
    for w in meal.warnings:
        print(f"    ⚠ {w}")

    # ---- C3 推荐 + 预警 ----
    eng = RecommendationEngine()
    t = eng.compute("male", 175, 75, 30, ActivityLevel.SEDENTARY, GoalType.CONTROL_SUGAR)
    print(f"\n[3] 每日推荐（male/175cm/75kg/30岁/久坐/控糖）: {t.to_dict()}")

    alerter = AlertEngine()
    now = datetime(2026, 10, 23, 21, 15)   # 固定时间保证示例可复现
    alerts = alerter.evaluate(
        t,
        day_totals={"energy_kcal": meal.totals["energy_kcal"] + 1620,   # 当日此前已摄入 1620
                    "protein_g": meal.totals["protein_g"] + 60,
                    "carb_g": meal.totals["carb_g"] + 230},
        goal=GoalType.CONTROL_SUGAR, record_date="2026-10-23", now=now,
        meal_kcal=meal.totals["energy_kcal"], already_fired={"AL-01"})
    print("\n[4] 预警（含频控：AL-01 已于当日触发过，应被去重）:")
    for a in alerts:
        print(f"    [{a.code}] {a.name}({a.severity}) {a.message}")
        print(f"         依据: {a.basis}")

    out = {"targets": t.to_dict(),
           "meal": meal.to_dict(),
           "alerts": [a.__dict__ for a in alerts]}
    os.makedirs(os.path.join(BASE, "reports"), exist_ok=True)
    with open(os.path.join(BASE, "reports", "wp_c_example_output.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[5] 已写出 reports/wp_c_example_output.json")

if __name__ == "__main__":
    main()
