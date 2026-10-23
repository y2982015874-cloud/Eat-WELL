# -*- coding: utf-8 -*-
"""
advisor.py — C3 推荐摄入计算 + 预警规则（确定性代码，全部规则来自 PRD 表 4-1 / 表 4-2）
规则编号与阈值逐条对应 PRD，不得自行编造医学阈值。
大模型仅用于依据计算结果生成解释性建议（见 prompts/llm_advice_prompt.md）。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class GoalType(str, Enum):
    LOSE_FAT = "lose_fat"
    GAIN_MUSCLE = "gain_muscle"
    CONTROL_SUGAR = "control_sugar"
    MAINTAIN = "maintain"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"    # ×1.2
    LIGHT = "light"            # ×1.375
    MODERATE = "moderate"      # ×1.55
    ACTIVE = "active"          # ×1.725


ACTIVITY_FACTOR = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725}

# 供能比 (protein, fat, carb)，来源 PRD 表 4-1
GOAL_MACRO_RATIO = {
    GoalType.LOSE_FAT: (0.30, 0.25, 0.45),
    GoalType.GAIN_MUSCLE: (0.25, 0.25, 0.50),
    GoalType.CONTROL_SUGAR: (0.25, 0.30, 0.45),
    GoalType.MAINTAIN: (0.20, 0.30, 0.50),
}
KCAL_PER_G = {"protein": 4, "carb": 4, "fat": 9}

# 预警阈值（PRD 表 4-1）
T_OVER = 1.10
T_UNDER = 0.70
LATE_NIGHT_HOUR = 20      # ≥ 20:00 判"不足"
SINGLE_MEAL_RATIO = 0.50  # 单餐 > 日目标 50% 提示
BMI_ADVICE_LOW, BMI_ADVICE_HIGH = 18.5, 30.0


@dataclass
class Targets:
    bmr: float
    tdee: float
    target_kcal: float
    target_protein_g: float
    target_fat_g: float
    target_carb_g: float
    bmi: float
    bmi_advice: bool          # BMI<18.5 或 >30 时提示咨询专业人士
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__.copy()


class RecommendationEngine:
    """按 PRD 表 4-1 计算每日推荐摄入（Mifflin-St Jeor）。"""

    def compute(self, gender: str, height_cm: float, weight_kg: float, age: int,
                activity: ActivityLevel, goal: GoalType) -> Targets:
        # --- 输入校验（PRD 4.3 验收标准）---
        if gender not in ("male", "female"):
            raise ValueError(f"gender 必须为 male/female，收到 {gender!r}")
        if not (100 <= height_cm <= 250):
            raise ValueError(f"身高超出 100–250cm：{height_cm}")
        if not (30 <= weight_kg <= 200):
            raise ValueError(f"体重超出 30–200kg：{weight_kg}")
        if not (12 <= age <= 100):
            raise ValueError(f"年龄超出 12–100 岁：{age}")

        base = 10 * weight_kg + 6.25 * height_cm - 5 * age
        bmr = base + (5 if gender == "male" else -161)
        tdee = bmr * ACTIVITY_FACTOR[activity]

        if goal == GoalType.LOSE_FAT:
            target = max(tdee * 0.85, bmr * 1.1)     # 减脂下限保护
        elif goal == GoalType.GAIN_MUSCLE:
            target = tdee * 1.10
        else:  # control_sugar / maintain
            target = tdee * 1.00

        p_ratio, f_ratio, c_ratio = GOAL_MACRO_RATIO[goal]
        bmi = weight_kg / ((height_cm / 100.0) ** 2)
        notes = []
        if goal == GoalType.LOSE_FAT and target == bmr * 1.1:
            notes.append("已触发减脂下限保护：目标热量取 BMR×1.1（不低于基础代谢安全线）")
        bmi_advice = bmi < BMI_ADVICE_LOW or bmi > BMI_ADVICE_HIGH
        if bmi_advice:
            notes.append(f"BMI={bmi:.1f} 超出 18.5–30，建议咨询营养师或医生（仅供参考，不构成诊疗建议）")

        return Targets(
            bmr=round(bmr, 1), tdee=round(tdee, 1), target_kcal=round(target, 1),
            target_protein_g=round(target * p_ratio / KCAL_PER_G["protein"], 1),
            target_fat_g=round(target * f_ratio / KCAL_PER_G["fat"], 1),
            target_carb_g=round(target * c_ratio / KCAL_PER_G["carb"], 1),
            bmi=round(bmi, 1), bmi_advice=bmi_advice, notes=notes,
        )


@dataclass(frozen=True)
class AlertRule:
    code: str            # AL-01..AL-05
    name: str
    condition: str       # 人读描述
    source: str          # PRD 出处


ALERT_RULES = [
    AlertRule("AL-01", "热量超标", "当日累计热量 > 目标×110%", "PRD 表 4-2"),
    AlertRule("AL-02", "热量不足", "当日累计热量 < 目标×70% 且 当前时间≥20:00", "PRD 表 4-2"),
    AlertRule("AL-03", "蛋白质不足", "当日蛋白质 < 目标×70% 且 当前时间≥20:00", "PRD 表 4-2"),
    AlertRule("AL-04", "碳水超标", "仅控糖目标生效：当日碳水 > 目标×110%", "PRD 表 4-2"),
    AlertRule("AL-05", "单餐占比过高", "单餐热量 > 日目标×50%（提示性质，不计入超标）", "PRD 表 4-2"),
]


@dataclass
class Alert:
    code: str
    name: str
    message: str
    basis: str           # 可追溯计算依据
    severity: str        # high / medium / info
    record_date: str
    trigger_time: str


class AlertEngine:
    """
    触发时机：仅在某条记录确认落库后判定一次（不设定时任务）。
    频控：同一 (code, record_date) 至多 1 条 —— 由调用方传入已触发集合完成去重。
    """

    def evaluate(self, targets: Targets, day_totals: Dict[str, Optional[float]],
                 goal: GoalType, record_date: str, now: Optional[datetime] = None,
                 meal_kcal: Optional[float] = None,
                 already_fired: Optional[set] = None) -> List[Alert]:
        """
        day_totals : 当日累计 {"energy_kcal":…, "protein_g":…, "carb_g":…}
        meal_kcal  : 本次单餐热量（用于 AL-05）
        """
        now = now or datetime.now()
        fired = []
        seen = set(already_fired or [])
        kcal = day_totals.get("energy_kcal")
        protein = day_totals.get("protein_g")
        carb = day_totals.get("carb_g")
        tk = targets.target_kcal

        def add(code, name, msg, basis, severity):
            if code in seen:
                return
            seen.add(code)
            fired.append(Alert(code, name, msg, basis, severity, record_date, now.strftime("%H:%M")))

        # AL-01 热量超标
        if kcal is not None and kcal > tk * T_OVER:
            add("AL-01", "热量超标",
                f"今日热量已达目标的 {kcal/tk*100:.0f}%，超出约 {kcal - tk:.0f} kcal",
                f"{kcal} > {tk}×{T_OVER}", "high")
        # AL-02 热量不足（≥20:00）
        if kcal is not None and kcal < tk * T_UNDER and now.hour >= LATE_NIGHT_HOUR:
            add("AL-02", "热量不足",
                f"今日摄入仅达目标的 {kcal/tk*100:.0f}%，如有需要可适当补充",
                f"{kcal} < {tk}×{T_UNDER} 且 {now.strftime('%H:%M')}≥20:00", "medium")
        # AL-03 蛋白质不足（≥20:00）
        tp = targets.target_protein_g
        if protein is not None and protein < tp * T_UNDER and now.hour >= LATE_NIGHT_HOUR:
            gap = tp - protein
            add("AL-03", "蛋白质不足",
                f"蛋白质缺口约 {gap:.0f}g，可加一份鸡胸肉（约 100g，含蛋白约 31g）",
                f"{protein} < {tp}×{T_UNDER} 且 时间≥20:00", "medium")
        # AL-04 碳水超标（仅控糖）
        tc = targets.target_carb_g
        if goal == GoalType.CONTROL_SUGAR and carb is not None and carb > tc * T_OVER:
            add("AL-04", "碳水超标",
                f"今日碳水已达目标的 {carb/tc*100:.0f}%，建议减少主食份量",
                f"goal=control_sugar 且 {carb} > {tc}×{T_OVER}", "high")
        # AL-05 单餐占比过高（提示）
        if meal_kcal is not None and meal_kcal > tk * SINGLE_MEAL_RATIO:
            add("AL-05", "单餐占比过高",
                f"这一餐已占今日热量目标的 {meal_kcal/tk*100:.0f}%，下一餐建议清淡",
                f"{meal_kcal} > {tk}×{SINGLE_MEAL_RATIO}", "info")

        # 严重度排序（首页卡片最多 2 条）
        order = {"high": 0, "medium": 1, "info": 2}
        fired.sort(key=lambda a: order[a.severity])
        return fired[:2]
