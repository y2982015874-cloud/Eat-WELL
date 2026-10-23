# -*- coding: utf-8 -*-
"""
test_nutrition.py — 工作包 C 单元测试（固定输入 → 可复现期望值）
运行 : python -m unittest tests.test_nutrition -v
覆盖 : C1 查询（按ID/未收录/同名异物/类型错误）
       C2 计算（正常/份量参考/模型估算标注/缺失重量/负重量/超上限/空餐/非法来源）
       C3 规则（BMR/TDEE/目标/减脂下限/BMI提示/AL-01..AL-05 全部分支 + 频控去重 + 严重度截断）
"""
import os, sys, unittest, csv
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)

from nutrition import (NutritionDB, FoodNotFoundError, NutritionDataError,
                       NutritionCalculator, WeightSource, NutritionItemError,
                       RecommendationEngine, AlertEngine, GoalType, ActivityLevel)


def _t1_rows():
    with open(os.path.join(BASE, "data", "nutrition_clean.csv"), encoding="utf-8-sig") as f:
        return {int(r["food_id"]): r for r in csv.DictReader(f)}


T1 = _t1_rows()


class TestC1Query(unittest.TestCase):
    def setUp(self):
        self.db = NutritionDB()

    def test_loads_351(self):
        self.assertEqual(len(self.db), 351)

    def test_get_by_id_exact(self):
        r = self.db.get(83)                      # 红烧肉
        self.assertEqual(r.name_zh, "红烧肉")
        row = T1[83]
        self.assertAlmostEqual(r.energy_kcal_per_100g, float(row["energy_kcal_per_100g"]), places=4)

    def test_rice_values(self):
        r = self.db.get(0)                       # 米饭 1.16 kcal/g → 116/100g
        self.assertAlmostEqual(r.energy_kcal_per_100g, 116.0, places=4)
        self.assertAlmostEqual(r.carb_g_per_100g, 25.9, places=4)

    def test_not_found(self):
        with self.assertRaises(FoodNotFoundError):
            self.db.get(351)
        with self.assertRaises(FoodNotFoundError):
            self.db.get(-1)

    def test_type_error(self):
        with self.assertRaises(TypeError):
            self.db.get("83")                    # 禁止字符串模糊匹配
        with self.assertRaises(TypeError):
            self.db.get(83.0)

    def test_exact_name_lookup(self):
        r = self.db.lookup_by_exact_name("米饭")
        self.assertEqual(r.food_id, 0)

    def test_exact_name_not_found(self):
        with self.assertRaises(FoodNotFoundError):
            self.db.lookup_by_exact_name("红烧肉 ")   # 带空格 → 不匹配
        with self.assertRaises(FoodNotFoundError):
            self.db.lookup_by_exact_name("不存在菜品XYZ")   # 未收录

    def test_data_status_complete(self):
        for fid in (0, 22, 70, 83, 37, 40, 66, 82, 136, 74):
            self.assertEqual(self.db.get(fid).data_status, "complete")


class TestC2Calc(unittest.TestCase):
    def setUp(self):
        self.db = NutritionDB()
        self.c = NutritionCalculator(self.db)

    def test_rice_200g(self):
        it = self.c.calc_item(0, 200, WeightSource.USER_INPUT)
        self.assertAlmostEqual(it.energy_kcal, 232.0, places=2)   # 116×2
        self.assertAlmostEqual(it.carb_g, 51.8, places=2)          # 25.9×2
        self.assertAlmostEqual(it.protein_g, 5.2, places=2)
        self.assertAlmostEqual(it.fat_g, 0.6, places=2)
        self.assertEqual(it.status, "ok")

    def test_portion_reference(self):
        it = self.c.calc_item(0, None, WeightSource.PORTION_REFERENCE, portions=1.0)
        self.assertAlmostEqual(it.weight_g, 200.0, places=2)       # reference_portions.csv 1碗=200g
        self.assertIn("非称重值", "".join(it.warnings))

    def test_portion_reference_2x(self):
        it = self.c.calc_item(0, None, WeightSource.PORTION_REFERENCE, portions=0.5)
        self.assertAlmostEqual(it.weight_g, 100.0, places=2)

    def test_no_portion_basis(self):
        with self.assertRaises(NutritionItemError):
            self.c.calc_item(351 - 1, None, WeightSource.PORTION_REFERENCE, portions=1)  # 非 tier1 无基准

    def test_model_estimate_flagged(self):
        it = self.c.calc_item(83, 150, WeightSource.MODEL_ESTIMATE)
        self.assertTrue(any("模型估算" in w for w in it.warnings))
        self.assertEqual(it.weight_source, "model_estimate")

    def test_missing_weight(self):
        with self.assertRaises(NutritionItemError):
            self.c.calc_item(0, None, WeightSource.USER_INPUT)

    def test_negative_and_zero_weight(self):
        for w in (-5, 0):
            with self.assertRaises(NutritionItemError):
                self.c.calc_item(0, w, WeightSource.USER_INPUT)

    def test_nan_and_inf(self):
        import math
        for w in (float("nan"), float("inf")):
            with self.assertRaises(NutritionItemError):
                self.c.calc_item(0, w, WeightSource.USER_INPUT)

    def test_unit_mismatch_guard(self):
        # 0.2g 属合法输入（>0 且未超上限），不应报错
        it = self.c.calc_item(0, 0.2, WeightSource.USER_INPUT)
        self.assertAlmostEqual(it.energy_kcal, 0.23, places=2)
        # 真正拦截的是超上限（疑似 kg/其他单位误填）
        with self.assertRaises(NutritionItemError):
            self.c.calc_item(0, 6000, WeightSource.USER_INPUT)

    def test_not_found(self):
        with self.assertRaises(FoodNotFoundError):
            self.c.calc_item(9999, 100, WeightSource.USER_INPUT)

    def test_meal_aggregate(self):
        # 期望值直接从 nutrition_clean.csv（数据真源）推导，验证计算逻辑而非硬编码
        rice, pork = T1[0], T1[83]
        meal = self.c.calc_meal([
            {"food_id": 0, "weight_g": 200, "weight_source": "user_input"},
            {"food_id": 83, "weight_g": 150, "weight_source": "user_input"},
        ])
        exp_kcal = float(rice["energy_kcal_per_100g"])*2 + float(pork["energy_kcal_per_100g"])*1.5
        exp_prot = float(rice["protein_g_per_100g"])*2 + float(pork["protein_g_per_100g"])*1.5
        self.assertAlmostEqual(meal.totals["energy_kcal"], round(exp_kcal, 2), places=2)
        self.assertAlmostEqual(meal.totals["protein_g"], round(exp_prot, 2), places=2)
        self.assertEqual(meal.status, "ok")

    def test_r1_conversion_sanity(self):
        # R1 换算抽检：米饭能量 1.16 kcal/g ×100 = 116 kcal/100g（论文 Table 4 口径）
        self.assertAlmostEqual(float(T1[0]["energy_kcal_per_100g"]), 116.0, places=4)
        self.assertAlmostEqual(float(T1[0]["carb_g_per_100g"]), 25.9, places=4)

    def test_meal_empty(self):
        with self.assertRaises(NutritionItemError):
            self.c.calc_meal([])

    def test_meal_bad_source(self):
        with self.assertRaises(NutritionItemError):
            self.c.calc_meal([{"food_id": 0, "weight_g": 200, "weight_source": "magic"}])

    def test_meal_item_error_has_index(self):
        with self.assertRaises(NutritionItemError) as cm:
            self.c.calc_meal([{"food_id": 0, "weight_g": 200, "weight_source": "user_input"},
                              {"food_id": 0, "weight_g": -1, "weight_source": "user_input"}])
        self.assertIn("entries[1]", str(cm.exception))


class TestC3Advisor(unittest.TestCase):
    def setUp(self):
        self.eng = RecommendationEngine()
        self.alert = AlertEngine()

    def test_bmr_male(self):
        t = self.eng.compute("male", 175, 75, 30, ActivityLevel.SEDENTARY, GoalType.MAINTAIN)
        self.assertAlmostEqual(t.bmr, 10*75 + 6.25*175 - 5*30 + 5, places=1)   # 1703.75

    def test_bmr_female(self):
        t = self.eng.compute("female", 160, 55, 28, ActivityLevel.SEDENTARY, GoalType.MAINTAIN)
        self.assertAlmostEqual(t.bmr, 10*55 + 6.25*160 - 5*28 - 161, places=1)  # 1289.0

    def test_tdee_and_macros(self):
        t = self.eng.compute("male", 175, 75, 30, ActivityLevel.MODERATE, GoalType.MAINTAIN)
        bmr = 10*75 + 6.25*175 - 150 + 5
        tdee = bmr * 1.55
        self.assertAlmostEqual(t.tdee, round(tdee, 1), places=1)
        self.assertAlmostEqual(t.target_kcal, round(tdee, 1), places=1)
        self.assertAlmostEqual(t.target_protein_g, round(tdee*0.20/4, 1), places=1)
        self.assertAlmostEqual(t.target_fat_g, round(tdee*0.30/9, 1), places=1)
        self.assertAlmostEqual(t.target_carb_g, round(tdee*0.50/4, 1), places=1)

    def test_lose_fat_floor(self):
        # 极端矮小体重的减脂下限保护
        t = self.eng.compute("female", 120, 40, 60, ActivityLevel.SEDENTARY, GoalType.LOSE_FAT)
        bmr = 10*40 + 6.25*120 - 300 - 161
        tdee = bmr * 1.2
        floor = bmr * 1.1
        if tdee * 0.85 < floor:
            self.assertAlmostEqual(t.target_kcal, round(floor, 1), places=1)
            self.assertTrue(any("下限保护" in n for n in t.notes))

    def test_gain_muscle(self):
        t = self.eng.compute("male", 175, 75, 30, ActivityLevel.LIGHT, GoalType.GAIN_MUSCLE)
        bmr = 10*75 + 6.25*175 - 145
        self.assertAlmostEqual(t.target_kcal, round(bmr*1.375*1.10, 1), places=1)

    def test_bmi_advice(self):
        t = self.eng.compute("male", 175, 110, 30, ActivityLevel.SEDENTARY, GoalType.MAINTAIN)
        self.assertTrue(t.bmi_advice)
        self.assertTrue(any("营养师" in n for n in t.notes))

    def test_input_validation(self):
        for kwargs in [dict(gender="other", height_cm=175, weight_kg=75, age=30,
                            activity=ActivityLevel.SEDENTARY, goal=GoalType.MAINTAIN),
                       dict(gender="male", height_cm=90, weight_kg=75, age=30,
                            activity=ActivityLevel.SEDENTARY, goal=GoalType.MAINTAIN),
                       dict(gender="male", height_cm=175, weight_kg=250, age=30,
                            activity=ActivityLevel.SEDENTARY, goal=GoalType.MAINTAIN),
                       dict(gender="male", height_cm=175, weight_kg=75, age=10,
                            activity=ActivityLevel.SEDENTARY, goal=GoalType.MAINTAIN)]:
            with self.assertRaises(ValueError):
                self.eng.compute(**kwargs)

    # ---------- 预警规则 ----------
    def _targets(self):
        return self.eng.compute("male", 175, 75, 30, ActivityLevel.SEDENTARY, GoalType.MAINTAIN)

    def test_al01_over(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*1.2, "protein_g": None, "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 12, 0))
        self.assertEqual([x.code for x in a], ["AL-01"])
        self.assertIn("120%", a[0].message)

    def test_al02_under_late(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*0.6, "protein_g": None, "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 21, 0))
        self.assertEqual([x.code for x in a], ["AL-02"])

    def test_al02_not_triggered_before_20(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*0.6, "protein_g": None, "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 19, 59))
        self.assertEqual(a, [])

    def test_al03_protein(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal, "protein_g": t.target_protein_g*0.5,
                                    "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 21, 0))
        self.assertIn("AL-03", [x.code for x in a])

    def test_al04_only_control_sugar(self):
        t = self.eng.compute("male", 175, 75, 30, ActivityLevel.SEDENTARY, GoalType.CONTROL_SUGAR)
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal, "protein_g": None,
                                    "carb_g": t.target_carb_g*1.2},
                                GoalType.CONTROL_SUGAR, "2026-10-23", datetime(2026, 10, 23, 12, 0))
        self.assertEqual([x.code for x in a], ["AL-04"])
        # 非 control_sugar 目标不触发 AL-04
        t2 = self._targets()
        a2 = self.alert.evaluate(t2, {"energy_kcal": t2.target_kcal, "protein_g": None,
                                      "carb_g": t2.target_carb_g*1.2},
                                 GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 12, 0))
        self.assertEqual(a2, [])

    def test_al05_single_meal(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*0.5, "protein_g": None, "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 12, 0),
                                meal_kcal=t.target_kcal*0.56)
        self.assertEqual([x.code for x in a], ["AL-05"])
        self.assertEqual(a[0].severity, "info")

    def test_dedup_same_day(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*1.2, "protein_g": None, "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 12, 0),
                                already_fired={"AL-01"})
        self.assertEqual(a, [])

    def test_max_two_and_severity_order(self):
        t = self._targets()
        a = self.alert.evaluate(t, {"energy_kcal": t.target_kcal*1.2, "protein_g": t.target_protein_g*0.5,
                                    "carb_g": None},
                                GoalType.MAINTAIN, "2026-10-23", datetime(2026, 10, 23, 21, 0),
                                meal_kcal=t.target_kcal*0.6)
        codes = [x.code for x in a]
        self.assertLessEqual(len(a), 2)
        self.assertEqual(codes[0], "AL-01")      # high 在前


if __name__ == "__main__":
    unittest.main(verbosity=2)
