# -*- coding: utf-8 -*-
"""
test_pipeline_contract.py — 第四阶段针对性测试（识别解析 / 营养匹配 / 计算公式 / 接口响应）
运行 : python -m unittest tests.test_pipeline_contract -v

覆盖：
  P1 识别结果解析：class_id → food_id 映射、与 datasets/det10/data.yaml 的 names 顺序一致
  P2 营养数据匹配：按 food_id 精确命中、未收录报错、非 int 拒绝（禁止字符串模糊匹配）
  P3 计算公式：per_100g × weight_g / 100、份量倍数线性、整餐汇总
  P4 接口响应契约：顶层字段集合、status 枚举、weight_source 枚举、
     meal.totals 不含 weight_g（前端 D1 缺陷的根因回归点）

P4 依赖 reports/_evidence/T*.json（由 scripts/e2e_acceptance.py 产出）；文件缺失时该组 skip。
"""
import os, sys, json, unittest

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from nutrition import (NutritionDB, FoodNotFoundError, NutritionCalculator,
                       WeightSource, NutritionItemError)
from infer import load_class_mapping

EVID = os.path.join(BASE, "reports", "_evidence")
ORDER = [0, 22, 70, 83, 37, 40, 66, 82, 136, 74]        # yolo class_id → DFoodTJ food_id
STATUS_ENUM = {"ok", "empty", "low_confidence", "error"}
WS_ENUM = {"user_input", "portion_reference", "model_estimate"}
TOTALS_KEYS = {"carb_g", "fat_g", "protein_g", "fiber_g", "energy_kcal"}


def _data_yaml_names():
    """不引入 yaml 依赖，直接解析 det10/data.yaml 的 names 段"""
    with open(os.path.join(BASE, "datasets", "det10", "data.yaml"), encoding="utf-8") as f:
        txt = f.read()
    names, in_names = {}, False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("names:"):
            in_names = True; continue
        if in_names and ":" in s:
            k, v = s.split(":", 1)
            if k.strip().isdigit():
                names[int(k.strip())] = v.strip()
    return names


class TestP1ClassMapping(unittest.TestCase):
    def test_size_and_order(self):
        m = load_class_mapping()
        self.assertEqual(len(m), 10)
        self.assertEqual([m[i]["food_id"] for i in range(10)], ORDER)

    def test_names_match_data_yaml(self):
        names, m = _data_yaml_names(), load_class_mapping()
        self.assertEqual(len(names), 10, "data.yaml 应解析出 10 个类别名")
        for i in range(10):
            self.assertEqual(m[i]["food_name"], names[i], f"class_id={i} 名称与 data.yaml 不一致")

    def test_names_match_nutrition_db(self):
        db, m = NutritionDB(), load_class_mapping()
        for i in range(10):
            self.assertEqual(m[i]["food_name"], db.get(m[i]["food_id"]).name_zh,
                             f"class_id={i} 名称与营养库 food_id={m[i]['food_id']} 不一致")


class TestP2NutritionMatch(unittest.TestCase):
    def test_exact_lookup(self):
        self.assertEqual(NutritionDB().get(83).name_zh, "红烧肉")

    def test_missing_id_raises(self):
        with self.assertRaises(FoodNotFoundError):
            NutritionDB().get(999)

    def test_non_int_rejected(self):
        with self.assertRaises(TypeError):
            NutritionDB().get("83")          # 禁止字符串模糊匹配


class TestP3CalcFormula(unittest.TestCase):
    def setUp(self):
        self.calc = NutritionCalculator(NutritionDB())

    def test_rice_200g(self):
        # 回归点：源表质量密度单位为 g/g，清洗时 ×100；换算错会差 100 倍
        it = self.calc.calc_item(0, 200.0, WeightSource.USER_INPUT)
        self.assertEqual(it.energy_kcal, 232.0)

    def test_formula_is_linear_in_weight(self):
        a = self.calc.calc_item(83, 100.0, WeightSource.USER_INPUT)
        b = self.calc.calc_item(83, 200.0, WeightSource.USER_INPUT)
        self.assertAlmostEqual(b.energy_kcal, a.energy_kcal * 2, places=2)

    def test_portion_reference_scales(self):
        a = self.calc.calc_item(0, None, WeightSource.PORTION_REFERENCE, portions=1.0)
        b = self.calc.calc_item(0, None, WeightSource.PORTION_REFERENCE, portions=2.0)
        self.assertAlmostEqual(b.weight_g, a.weight_g * 2, places=5)
        self.assertAlmostEqual(b.energy_kcal, a.energy_kcal * 2, places=5)

    def test_portion_reference_marked_not_weighed(self):
        it = self.calc.calc_item(0, None, WeightSource.PORTION_REFERENCE, portions=1.0)
        self.assertTrue(any("非称重" in w for w in it.warnings),
                        "份量参考必须显式标注非称重值")

    def test_missing_weight_rejected(self):
        with self.assertRaises(NutritionItemError):
            self.calc.calc_item(0, None, WeightSource.USER_INPUT)

    def test_meal_aggregate(self):
        meal = self.calc.calc_meal([
            {"food_id": 0, "weight_g": 200.0, "weight_source": "user_input"},
            {"food_id": 83, "weight_g": 150.0, "weight_source": "user_input"}])
        e1 = self.calc.calc_item(0, 200.0, WeightSource.USER_INPUT).energy_kcal
        e2 = self.calc.calc_item(83, 150.0, WeightSource.USER_INPUT).energy_kcal
        self.assertAlmostEqual(meal.totals["energy_kcal"], e1 + e2, places=2)
        self.assertEqual(meal.status, "ok")


class TestP4ResponseContract(unittest.TestCase):
    """以第三阶段真实响应为样本，校验契约不变（含 D1 根因回归点）"""

    def _load(self, name):
        p = os.path.join(EVID, name + ".json")
        if not os.path.exists(p):
            self.skipTest(f"缺少 {p}，请先运行 scripts/e2e_acceptance.py")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_top_level_keys(self):
        d = self._load("T1")
        self.assertEqual(sorted(d.keys()),
                         sorted(["meta", "image_b64", "orig_b64", "detection", "fallback",
                                 "classification", "items", "meal", "targets", "alerts"]))

    def test_detection_contract_keys(self):
        d = self._load("T1")
        det = d["detection"]
        for k in ["image_id", "model_version", "task_type", "image_width", "image_height",
                  "detections", "status", "warnings"]:
            self.assertIn(k, det, f"detection 缺字段 {k}")

    def test_status_enum_across_scenarios(self):
        for n in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]:
            try:
                d = self._load(n)
            except unittest.SkipTest:
                continue
            st = d["detection"]["status"]
            self.assertIn(st, STATUS_ENUM, f"{n} 的 detection.status={st} 不在枚举内")

    def test_weight_source_enum(self):
        for n in ["T1", "T2", "T6", "T7"]:
            try:
                d = self._load(n)
            except unittest.SkipTest:
                continue
            for i in d.get("items") or []:
                if i.get("weight_source"):
                    self.assertIn(i["weight_source"], WS_ENUM)

    def test_totals_has_no_weight_g(self):
        """D1 根因回归点：契约 §5.2 的 totals 只有 5 个营养字段，前端不得读取 totals.weight_g"""
        d = self._load("T1")
        totals = (d["meal"] or {}).get("totals") or {}
        self.assertEqual(set(totals.keys()), TOTALS_KEYS)
        self.assertNotIn("weight_g", totals)
        # 总重必须由 meal.items 汇总得到
        s = sum(i.get("weight_g") or 0 for i in (d["meal"] or {}).get("items") or [])
        self.assertGreater(s, 0, "meal.items 应能提供总重")

    def test_error_scenario_keeps_all_fields(self):
        """异常场景（非法文件）仍返回完整字段，不得整包丢失"""
        d = self._load("T3")
        self.assertEqual(d["detection"]["status"], "error")
        self.assertTrue(d["detection"]["warnings"])
        self.assertEqual(d["items"], [])
        self.assertIsNone(d["meal"])
        self.assertIsNotNone(d["targets"], "异常场景也应给出每日目标（profile 有效时）")

    def test_missing_nutrition_item_flagged_not_silently_dropped(self):
        """营养库缺记录：该项 status=error 且保留原因，已识别项照常出结果"""
        d = self._load("T6")
        bad = [i for i in d["items"] if i.get("status") == "error"]
        self.assertTrue(bad, "缺失记录项必须被标记而非静默丢弃")
        self.assertTrue(bad[0].get("warnings"))
        self.assertTrue(any(i.get("food_id") == 83 and i.get("energy_kcal") for i in d["items"]),
                        "已识别的红烧肉营养应照常产出")
        self.assertIsNotNone(d["meal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
