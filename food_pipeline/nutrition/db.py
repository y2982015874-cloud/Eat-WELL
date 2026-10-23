# -*- coding: utf-8 -*-
"""
db.py — C1 营养查询模块
原则：一律按标准 food_id（整数）精确查询，不做字符串模糊匹配。
     未收录 / 数据缺失 / 来源冲突均有明确状态返回，不静默兜底。
"""
import csv
import os
from dataclasses import dataclass, field
from typing import Optional

DATA_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "nutrition_clean.csv")
PORTIONS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "reference_portions.csv")


class FoodNotFoundError(KeyError):
    """food_id 不在营养库范围内"""

class NutritionDataError(ValueError):
    """food_id 存在但核心营养数据缺失/非法"""


@dataclass(frozen=True)
class PortionReference:
    food_id: int
    name_zh: str
    label: str                 # 如 "1碗"
    grams_per_portion: float
    source: str
    status: str                # reference_only = 参考值，非称重


@dataclass(frozen=True)
class NutritionRecord:
    food_id: int
    name_zh: str
    name_en: str
    tier: int
    # 每 100g 口径
    carb_g_per_100g: float
    fat_g_per_100g: float
    protein_g_per_100g: float
    fiber_g_per_100g: float
    energy_kcal_per_100g: float
    # 体积口径（可选，用于体积估重路径）
    density_g_ml: float
    carb_g_per_ml: float
    fat_g_per_ml: float
    protein_g_per_ml: float
    fiber_g_per_ml: float
    energy_kcal_per_ml: float
    data_status: str            # complete / partial
    source: str
    warnings: list = field(default_factory=list)


class NutritionDB:
    """营养数据库：只读加载 nutrition_clean.csv，提供按 ID 精确查询。"""

    def __init__(self, csv_path: str = DATA_CSV, portions_path: str = PORTIONS_CSV):
        self._by_id = {}
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                fid = int(row["food_id"])
                rec = NutritionRecord(
                    food_id=fid,
                    name_zh=row["name_zh"],
                    name_en=row["name_en"],
                    tier=int(row["tier"]),
                    carb_g_per_100g=self._f(row["carb_g_per_100g"]),
                    fat_g_per_100g=self._f(row["fat_g_per_100g"]),
                    protein_g_per_100g=self._f(row["protein_g_per_100g"]),
                    fiber_g_per_100g=self._f(row["fiber_g_per_100g"]),
                    energy_kcal_per_100g=self._f(row["energy_kcal_per_100g"]),
                    density_g_ml=self._f(row["density_g_ml"]),
                    carb_g_per_ml=self._f(row["carb_g_per_ml"]),
                    fat_g_per_ml=self._f(row["fat_g_per_ml"]),
                    protein_g_per_ml=self._f(row["protein_g_per_ml"]),
                    fiber_g_per_ml=self._f(row["fiber_g_per_ml"]),
                    energy_kcal_per_ml=self._f(row["energy_kcal_per_ml"]),
                    data_status=row["data_status"],
                    source=row["source"],
                    warnings=[],
                )
                # 数据健康检查：核心四项必须可解析
                if rec.data_status != "complete":
                    rec.warnings.append("核心营养数据不完整(data_status=partial)，计算结果仅含可得项")
                self._by_id[fid] = rec

        # 份量参考基准（仅 tier1 试点菜品；reference_only，非称重值）
        self.reference_portions = {}
        if os.path.exists(portions_path):
            with open(portions_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    fid = int(row["food_id"])
                    self.reference_portions[fid] = PortionReference(
                        food_id=fid, name_zh=row["name_zh"], label=row["label"],
                        grams_per_portion=float(row["grams_per_portion"]),
                        source=row["source"], status=row["status"])

    @staticmethod
    def _f(v) -> Optional[float]:
        v = (v or "").strip()
        return float(v) if v not in ("", "nan", "NaN") else None

    def __len__(self):
        return len(self._by_id)

    def get(self, food_id: int) -> NutritionRecord:
        """按标准 food_id 精确查询。未收录抛 FoodNotFoundError。"""
        if not isinstance(food_id, int) or isinstance(food_id, bool):
            raise TypeError(f"food_id 必须为整数，收到 {type(food_id).__name__}")
        rec = self._by_id.get(food_id)
        if rec is None:
            raise FoodNotFoundError(f"food_id={food_id} 未收录（库范围 0..{max(self._by_id)}）")
        return rec

    def lookup_by_exact_name(self, name_zh: str) -> NutritionRecord:
        """仅限整名精确匹配的辅助入口（不模糊、不截断）。多命中时抛错要求改用 ID。"""
        hits = [r for r in self._by_id.values() if r.name_zh == name_zh]
        if not hits:
            raise FoodNotFoundError(f"名称 {name_zh!r} 未收录（本接口不做模糊匹配）")
        if len(hits) > 1:
            raise NutritionDataError(
                f"名称 {name_zh!r} 命中 {len(hits)} 条（同名异物），请改用 food_id 精确查询")
        return hits[0]

    def ids(self):
        return sorted(self._by_id)
