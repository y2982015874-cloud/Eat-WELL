# -*- coding: utf-8 -*-
"""
calculator.py — C2 营养计算模块
原则：
  * 重量来源必须显式声明（user_input / portion_reference / model_estimate），
    估算重量不得表述为真实称重值。
  * 缺失重量、负重量、超范围、单位不一致、营养缺失均校验并给出明确错误。
"""
import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any

from .db import NutritionDB, NutritionRecord

MAX_WEIGHT_G = 5000.0     # 单项食物重量上限（合理餐食不可能超过 5kg）
MIN_WEIGHT_G = 0.0001


class WeightSource(str, Enum):
    USER_INPUT = "user_input"                 # 用户显式输入/确认的克数（最可信）
    PORTION_REFERENCE = "portion_reference"   # 自建份量参考基准（见 data/reference_portions.csv）
    MODEL_ESTIMATE = "model_estimate"         # 视觉/大模型估算（不可视为称重值）


class NutritionItemError(ValueError):
    pass


@dataclass
class NutritionItem:
    food_id: int
    food_name: str
    weight_g: float
    weight_source: str
    carb_g: float
    fat_g: float
    protein_g: float
    fiber_g: float
    energy_kcal: float
    per_100g: Dict[str, float]
    status: str                                # ok / partial
    warnings: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class MealResult:
    items: List[NutritionItem]
    totals: Dict[str, float]
    status: str
    warnings: List[str]

    def to_dict(self):
        return {"items": [i.to_dict() for i in self.items],
                "totals": self.totals, "status": self.status, "warnings": self.warnings}


class NutritionCalculator:
    def __init__(self, db: NutritionDB):
        self.db = db

    # ---------- 单项 ----------
    def calc_item(self, food_id: int, weight_g: float, weight_source: WeightSource,
                  portions: Optional[float] = None) -> NutritionItem:
        """
        food_id         标准 ID（整数）
        weight_g        食物重量（克）；weight_source=portion_reference 时可传 portions（份倍数）
        weight_source   重量来源枚举
        """
        rec = self.db.get(food_id)   # 未收录 → FoodNotFoundError
        warnings = list(rec.warnings)

        # --- 重量校验 ---
        if weight_source == WeightSource.PORTION_REFERENCE and portions is not None:
            ref = self.db.reference_portions.get(food_id)
            if ref is None:
                raise NutritionItemError(f"food_id={food_id} 无份量参考基准，请直接提供克数")
            weight_g = ref.grams_per_portion * portions
            warnings.append(f"重量按份量参考 {ref.label}={ref.grams_per_portion}g × {portions} 折算，非称重值")

        if weight_g is None or (isinstance(weight_g, float) and math.isnan(weight_g)):
            raise NutritionItemError("weight_g 缺失：请提供克数，或使用份量参考基准")
        try:
            weight_g = float(weight_g)
        except (TypeError, ValueError):
            raise NutritionItemError(f"weight_g 非数值: {weight_g!r}")
        if math.isinf(weight_g):
            raise NutritionItemError("weight_g 不能为无穷大")
        if weight_g <= 0:
            raise NutritionItemError(f"weight_g 必须为正数，收到 {weight_g}")
        if weight_g > MAX_WEIGHT_G:
            raise NutritionItemError(f"weight_g={weight_g} 超过单项目上限 {MAX_WEIGHT_G}g，请检查单位是否为 g")

        if not isinstance(weight_source, WeightSource):
            raise NutritionItemError(f"weight_source 必须为 WeightSource 枚举，收到 {weight_source!r}")
        if weight_source == WeightSource.MODEL_ESTIMATE:
            warnings.append("重量为模型估算值，非称重实测，存在份量误差")

        # --- 营养计算：per100g × weight/100 ---
        def scale(v):
            return round(v * weight_g / 100.0, 2) if v is not None else None

        missing = [k for k in ("carb_g_per_100g", "fat_g_per_100g",
                               "protein_g_per_100g", "energy_kcal_per_100g")
                   if getattr(rec, k) is None]
        if missing:
            status = "partial"
            warnings.append("缺失营养字段: " + ",".join(missing))
        else:
            status = "ok"

        item = NutritionItem(
            food_id=rec.food_id, food_name=rec.name_zh,
            weight_g=round(weight_g, 2), weight_source=weight_source.value,
            carb_g=scale(rec.carb_g_per_100g), fat_g=scale(rec.fat_g_per_100g),
            protein_g=scale(rec.protein_g_per_100g), fiber_g=scale(rec.fiber_g_per_100g),
            energy_kcal=scale(rec.energy_kcal_per_100g),
            per_100g={"carb_g": rec.carb_g_per_100g, "fat_g": rec.fat_g_per_100g,
                      "protein_g": rec.protein_g_per_100g, "fiber_g": rec.fiber_g_per_100g,
                      "energy_kcal": rec.energy_kcal_per_100g},
            status=status, warnings=warnings,
        )
        return item

    # ---------- 整餐 ----------
    def calc_meal(self, entries: List[Dict[str, Any]]) -> MealResult:
        """
        entries: [{"food_id": int, "weight_g": float|None,
                   "weight_source": "user_input"|"portion_reference"|"model_estimate",
                   "portions": float|None(仅 portion_reference)}, ...]
        """
        if not entries:
            raise NutritionItemError("entries 为空：整餐至少需要 1 项食物")
        items, warnings = [], []
        for idx, e in enumerate(entries):
            try:
                src = WeightSource(e.get("weight_source", "model_estimate"))
            except ValueError:
                raise NutritionItemError(f"entries[{idx}].weight_source 非法: {e.get('weight_source')!r}")
            try:
                items.append(self.calc_item(e["food_id"], e.get("weight_g"), src, e.get("portions")))
            except NutritionItemError as ex:
                raise NutritionItemError(f"entries[{idx}]: {ex}")

        def total(k):
            vals = [getattr(i, k) for i in items]
            return round(sum(v for v in vals if v is not None), 2) if any(v is not None for v in vals) else None

        totals = {"carb_g": total("carb_g"), "fat_g": total("fat_g"),
                  "protein_g": total("protein_g"), "fiber_g": total("fiber_g"),
                  "energy_kcal": total("energy_kcal")}
        for i in items:
            warnings.extend([f"[{i.food_name}] {w}" for w in i.warnings])
        status = "ok" if all(i.status == "ok" for i in items) else "partial"
        return MealResult(items=items, totals=totals, status=status, warnings=warnings)
