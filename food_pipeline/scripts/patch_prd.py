# -*- coding: utf-8 -*-
"""
patch_prd.py — 按当前实现对齐 PRD，另存为 V1.5 对齐版（不修改原件）

用法：
    python scripts/patch_prd.py

输入：D:/workbuddy/kkk/AI饮食记录营养分析助手_网站开发PRD.docx
输出：D:/workbuddy/kkk/AI饮食记录营养分析助手_网站开发PRD_V1.5_对齐版.docx
"""
import copy
import os
import shutil

from docx import Document

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(BASE), "AI饮食记录营养分析助手_网站开发PRD.docx")
DST = os.path.join(os.path.dirname(BASE), "AI饮食记录营养分析助手_网站开发PRD_V1.5_对齐版.docx")

log = []


# ---------- 基础工具 ----------
def set_para_text(p, new_text):
    """保留首个 run 的格式，重建段落文本"""
    if not p.runs:
        p.add_run(new_text)
        return
    p.runs[0].text = new_text
    for r in p.runs[1:]:
        r.text = ""


def iter_paras(doc):
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p


def replace_all(doc, pairs):
    for old, new in pairs:
        n = 0
        for p in iter_paras(doc):
            full = "".join(r.text for r in p.runs)
            if old in full:
                set_para_text(p, full.replace(old, new))
                n += 1
        log.append(("OK  " if n == 1 else f"WARN(n={n}) ", old[:38]))
        if n == 0:
            print(f"[未命中] {old[:60]}")


def find_table(doc, header_cells):
    """按表头单元格文本定位表格"""
    for t in doc.tables:
        heads = [c.text.strip() for c in t.rows[0].cells]
        if heads[:len(header_cells)] == header_cells:
            return t
    return None


def insert_row_after(table, anchor_text, texts, col=0):
    """在 col 列文本 == anchor_text 的行之后插入一行"""
    idx = None
    for i, row in enumerate(table.rows):
        if row.cells[col].text.strip() == anchor_text:
            idx = i
            break
    if idx is None:
        print(f"[未命中行] {anchor_text}")
        return None
    row = table.rows[idx]
    new_tr = copy.deepcopy(row._tr)
    row._tr.addnext(new_tr)
    new_row = table.rows[idx + 1]
    for c, txt in zip(new_row.cells, texts):
        c.text = txt
    log.append(("OK  ", f"插入行: {texts[0][:30]}"))
    return new_row


def insert_row_before(table, c0, c1, texts):
    """在 实体列=c0 且 字段列=c1 的行之前插入一行"""
    idx = None
    for i, row in enumerate(table.rows):
        if row.cells[0].text.strip() == c0 and row.cells[1].text.strip() == c1:
            idx = i
            break
    if idx is None:
        print(f"[未命中行] {c0}/{c1}")
        return None
    row = table.rows[idx]
    new_tr = copy.deepcopy(row._tr)
    row._tr.addprevious(new_tr)
    new_row = table.rows[idx]
    for c, txt in zip(new_row.cells, texts):
        c.text = txt
    log.append(("OK  ", f"插入行(前): {texts[1][:30]}"))
    return new_row


def insert_after_row(table, c0, c1, texts):
    """在 实体列=c0 且 字段列=c1 的行之后插入一行"""
    idx = None
    for i, row in enumerate(table.rows):
        if row.cells[0].text.strip() == c0 and row.cells[1].text.strip() == c1:
            idx = i
            break
    if idx is None:
        print(f"[未命中行] {c0}/{c1}")
        return None
    row = table.rows[idx]
    new_tr = copy.deepcopy(row._tr)
    row._tr.addnext(new_tr)
    new_row = table.rows[idx + 1]
    for c, txt in zip(new_row.cells, texts):
        c.text = txt
    log.append(("OK  ", f"插入行(后): {texts[1][:30]}"))
    return new_row


def main():
    doc = Document(SRC)

    # ================= 段落替换 =================
    para_pairs = [
        # 版本头
        ("版本 V1.4　日期 2026-10-21",
         "版本 V1.5（模型与数据链路对齐版）　日期 2026-10-23"),

        # 3.1.2 图像记录分支 —— 检测/分类分工与兜底
        ("交由 YOLOv8 对 10 类核心菜品输出候选与检测框；未命中核心类别时不返回候选，交由下一节点整餐估算兜底。",
         "交由 YOLOv8 检测模型对 10 类核心菜品输出检测框（用于切分出一图中的多个菜品），同时由 YOLOv8-cls 分类模型输出前 3 个候选菜品（Top-3，MI-01 以此为准）。未命中核心类别时（检测为空）回退到分类模型 Top-1 作为候选（fallback）；仍无结果则返回空并引导人工补录。"),

        ("多模态大模型结合原图、候选菜品与检测框，输出整餐营养总量与子项清单（子项含菜品名、估算份量、单项营养）。",
         "规则层按 food_id 精确对齐食物营养库，结合三态重量来源（user_input 称重 / portion_reference 份量参考 / model_estimate 模型估算）确定每道菜的克数，输出整餐营养总量与子项清单；合计由规则层确定性累加，本期不调用大模型。"),

        ("规则层按子项名称与份量对齐食物营养数据库，计算热量与三大营养素；未收录菜品标记为待补充。",
         "规则层按 food_id（非菜名模糊匹配）精确对齐食物营养数据库，计算热量与三大营养素；未收录菜品标记为待补充（从 351 类营养库中选择或人工录入）。"),

        # 4.5 营养分析
        ("对一盘多菜品餐食，由多模态大模型一次输出整餐营养总量与子项清单；",
         "对一盘多菜品餐食，由检测模型切分出各菜品区域、分类模型给出候选，规则层按 food_id 与三态重量计算后输出整餐营养总量与子项清单（大模型未接入时按此确定性链路执行）；"),

        ("子项按大模型输出顺序展示，标注估算份量与单项营养。",
         "子项按检测框顺序展示，标注重量数值与重量来源（称重 / 份量参考 / 估算），并给出单项营养。"),

        # 7.1.1 检测范围说明（10 类清单与数据规模）
        ("检测范围说明：YOLOv8 仅覆盖 10 类高频菜品——米饭、面条、馒头（主食）、红烧肉、宫保鸡丁、清蒸鱼（荤菜）、炒青菜、番茄炒蛋（素菜）、紫菜蛋花汤（汤品）、苹果（水果）。数据集每类 ≥ 80 张，合计约 800 张。其余菜品不要求检测框，直接由多模态大模型整餐估算 + 规则层查库完成，这也是 MI-01 只在这 10 类上评测的原因。",
         "检测范围说明：本期实际落地 10 类高频菜品（取自 DFoodTJ-Rec 数据集，括号为营养库 food_id）——米饭（0）、馒头（22）、饺子（70）、红烧肉（83）、青椒肉丝（37）、西红柿炒鸡蛋（40）、清蒸鲈鱼（66）、麻婆豆腐（82）、蚝油西兰花（136）、冬瓜汤（74）；原拟清单中的面条、宫保鸡丁、炒青菜、紫菜蛋花汤、苹果未纳入本期试点。数据规模：分类数据集每类 400 训练 / 50 验证 / 50 测试（8:1:1，取自 DFoodTJ-Rec 官方划分，合计 5000 张真实照片）；检测数据集因缺少真实多菜品标注，采用单菜品图合成生成 1600 训练 / 200 验证 / 200 测试（8:1:1，合计 2000 张），其真实域表现见 9.2。其余 341 类菜品不要求检测框，由用户从 351 类营养库人工补录，这也是 MI-01 只在这 10 类上评测的原因。"),

        # 1.7 假设 A3 / 开放问题 Q1、Q2
        ("A3 自建中餐菜品库覆盖 ≥ 300 道常见菜品，可满足演示与验收场景。",
         "A3 自建中餐菜品库覆盖 ≥ 300 道常见菜品，可满足演示与验收场景。（实际入库 351 道，但仅其中 10 类可被识别模型自动识别，其余需人工补录。）"),

        ("Q1 菜品库首期覆盖范围？建议 ≥ 300 道（主食 60 / 荤菜 100 / 素菜 80 / 汤品 30 / 水果 30），由食物数据集任务确认。",
         "Q1（已关闭）菜品库首期覆盖范围？结论：采用 DFoodTJ-Nutr 全部 351 道中餐菜品并已清洗入库；原建议的 300 道与分类构成仅为预估，实际以数据集口径为准。其中 10 类为模型可识别的高频试点。"),

        ("Q2 USDA 数据为英文且以西餐为主，与中餐菜品的映射关系及份量单位换算口径（g / 碗 / 份）待里程碑 2 确定。",
         "Q2（已关闭）营养数据以 DFoodTJ-Nutr（351 道中餐，含每 100g 与每 ml 双口径）为准，不采用 USDA；USDA FoodData Central 仅完成资料盘点。份量口径为：营养值按每 100g 存储，份量基准（1 碗 / 1 份 / 1 个）先换算为克数再参与计算，首期仅 10 类有份量基准且标记为参考值（待人工校准）。"),

        # 9.2 依赖
        ("外部食物成分数据：依赖 USDA FoodData Central 等公开数据源，其字段口径与中餐菜品份量单位差异较大，需在第 2 阶段完成映射对齐（Q2）。",
         "外部食物成分数据：本期实际采用 DFoodTJ-Nutr（density.xlsx，351 道中餐菜品，来源为 Aqua-Calc 与 Mint Health 公开数据），已按「每 100g」口径清洗入库；USDA FoodData Central 已完成资料盘点但未采用（西餐为主、英文条目，与中餐成品菜映射成本高，见 Q2 结论）。"),

        ("若部署环境无 GPU，需评估单次推理耗时是否满足 MI-03。",
         "若部署环境无 GPU，需评估单次推理耗时是否满足 MI-03。（实测：CPU 环境下检测 P95 59.2 ms、分类 P95 21.0 ms，远低于 5 秒上限。）"),
    ]
    replace_all(doc, para_pairs)

    # ================= 表 1-2 量化指标 =================
    replace_all(doc, [
        ("检测范围为 10 类高频菜品（清单见表 7-1 说明）；测试集 ≥ 200 张（每类 ≥ 20 张），覆盖单一与混合餐、3 种光照与角度，开发/验证/测试按 8:1:1 划分；逐张人工评测，前 3 个候选中含正确菜品即计为命中。超出 10 类的菜品由多模态大模型兜底识别，不计入本指标",
         "检测范围为 10 类高频菜品（清单见表 7-1 说明）；测试集 500 张（每类 50 张，取自 DFoodTJ-Rec 官方 test 划分的真实照片，8:1:1 划分，单菜品场景）；逐张评测，前 3 个候选由分类模型输出，含正确菜品即计为命中。混合餐与光照/角度变化场景本期未覆盖，列为补充测试项。超出 10 类的菜品走人工补录，不计入本指标"),
        ("自用户提交图片/文本起，至结构化识别结果返回止（含多模态大模型 API 调用）；不含用户修正与确认耗时",
         "自用户提交图片/文本起，至结构化识别结果返回止；本期视觉链路实测：检测 P95 59.2 ms、分类 P95 21.0 ms（CPU）。若后续接入多模态大模型 API，须按同一口径重新测量并计入 API 调用耗时"),
    ])

    # ================= 表 3-1 异常降级 =================
    replace_all(doc, [
        ("返回前 3 个候选菜品",
         "返回分类模型的前 3 个候选菜品"),
    ])

    # ================= 表 7-1 能力分工 =================
    t71 = find_table(doc, ["环节", "承担方", "输入", "输出"])
    assert t71 is not None, "未找到表 7-1"
    insert_row_after(t71, "菜品检测（10 类核心菜品）",
                     ["菜品分类（Top-3 候选）", "YOLOv8-cls", "标准图（整图或检测裁剪区域）",
                      "前 3 个候选菜品 + 概率；MI-01 的 Top-3 口径以此为准"])
    replace_all(doc, [
        ("整餐营养总量 + 子项清单（菜品名、估算份量、单项营养）",
         "整餐营养总量 + 子项清单（菜品名、重量与重量来源、单项营养）；本期由规则层确定性计算"),
        ("原图 + 候选菜品 + 检测框",
         "food_id + 三态重量（称重 / 份量参考 / 模型估算）"),
    ])
    # 整餐估算行的承担方与营养对齐行的输入/输出
    for row in t71.rows:
        c0 = row.cells[0].text.strip()
        if c0 == "整餐估算与子项拆分":
            row.cells[1].text = "规则层 + 食物营养库（本期）；大模型接入后改为「大模型出份量、规则层核算」"
            row.cells[2].text = "food_id + 三态重量（称重 / 份量参考 / 模型估算）"
        elif c0 == "营养对齐与计算":
            row.cells[2].text = "food_id + 重量（g）"
            row.cells[3].text = "热量、蛋白质、脂肪、碳水化合物、膳食纤维（按 food_id 精确查询，不做菜名模糊匹配）"
    log.append(("OK  ", "表 7-1 修订"))

    # ================= 表 7-2 技术栈 =================
    t72 = find_table(doc, ["技术模块", "技术选型", "主要功能"])
    assert t72 is not None, "未找到表 7-2"
    for row in t72.rows:
        c0 = row.cells[0].text.strip()
        if c0 == "视觉模型":
            row.cells[1].text = "PyTorch + YOLOv8（检测）+ YOLOv8-cls（分类）"
            row.cells[2].text = "菜品目标检测（一图多菜切分）与 Top-3 候选分类"
        elif c0 == "营养数据":
            row.cells[1].text = "DFoodTJ-Nutr density.xlsx（351 道中餐，Aqua-Calc / Mint Health 口径）"
            row.cells[2].text = "热量与三大营养素、膳食纤维查询对齐；USDA FDC 仅资料盘点，本期未采用"
        elif c0 == "大语言模型":
            row.cells[2].text = "菜品理解、份量估算、整餐营养估算、饮食建议（本期未接入，相关环节按规则层降级执行）"
    log.append(("OK  ", "表 7-2 修订"))

    # ================= 表 7-4 数据字典 =================
    t74 = find_table(doc, ["实体", "字段", "类型", "必填", "说明与枚举"])
    assert t74 is not None, "未找到表 7-4"
    insert_row_after(t74, "unit",
                     ["MealItem", "weight_source", "TEXT", "是",
                      "重量来源：user_input（称重）/ portion_reference（份量参考）/ model_estimate（模型估算，须标注非称重）"],
                     col=1)
    for row in t74.rows:
        c0, c1 = row.cells[0].text.strip(), row.cells[1].text.strip()
        if c0 == "MealItem" and c1 == "food_id":
            row.cells[4].text = "取自 DFoodTJ 营养库 0–350；未收录菜品为空"
        elif c0 == "Food" and c1 == "source":
            row.cells[4].text = "dfoodtj / usda / self（本期数据全部为 dfoodtj）"
        elif c0 == "Food" and c1 == "category":
            row.cells[4].text = "主食 / 荤菜 / 素菜 / 汤品 / 水果 / 其他（DFoodTJ 未标注，需后台补录）"
        elif c0 == "Food" and c1 == "serving_gram":
            row.cells[4].text = "1 个基准单位对应克数（首期仅 10 类有值，且标记为参考值，待人工校准）"
    # Food 实体补 id（food_id）与 density_g_ml
    insert_row_before(t74, "Food", "name",
                      ["Food", "id", "INTEGER PK", "是",
                       "对应 DFoodTJ 营养库 food_id（0–350），与 MealItem.food_id 关联"])
    insert_after_row(t74, "Food", "source",
                     ["Food", "density_g_ml", "DECIMAL(5,2)", "否",
                      "食物整体密度，供体积估重路径使用（DFoodTJ 提供）"])
    log.append(("OK  ", "表 7-4 修订"))

    # ================= 表 8-1 里程碑 =================
    t81 = find_table(doc, ["阶段", "任务", "主要交付物", "阶段退出标准"])
    assert t81 is not None, "未找到表 8-1"
    for row in t81.rows:
        stage = row.cells[0].text.strip()
        if stage == "2":
            row.cells[3].text = ("营养库 351 类清洗入库（DFoodTJ-Nutr，每 100g 口径）；"
                                 "分类数据集 10 类 × 500 张真实照片完成（8:1:1）；"
                                 "检测数据集为合成数据 2000 张（8:1:1）——真实多菜品标注数据缺失，"
                                 "列为风险项，需人工标注 ≥ 200 张后形成真实验收基准")
        elif stage == "3":
            row.cells[3].text = ("MI-01 达标：分类模型 Top-3 = 99.6%（500 张真实照片）。"
                                 "检测模型合成域 mAP@0.5 = 0.890；真实域检出率 93.8%、主框类别正确率 79.6%，"
                                 "据此确定：检测仅用于菜品切分，类别以分类模型为准")
        elif stage == "4":
            row.cells[3].text = ("营养查询、整餐计算与 AL-01~AL-05 预警链路完成并单测通过；"
                                 "MI-02 需称重真值与已校准份量基准，本期份量为参考值（reference_only），"
                                 "列为待验收项，校准后重测")
    log.append(("OK  ", "表 8-1 修订"))

    # ================= 表 B-1 术语表 =================
    tb = find_table(doc, ["术语", "说明"])
    assert tb is not None, "未找到表 B-1"
    for row in tb.rows:
        if row.cells[0].text.strip() == "核心检测菜品（10 类）":
            row.cells[1].text = ("模型覆盖的 10 类高频菜品：米饭、馒头、饺子、红烧肉、青椒肉丝、"
                                 "西红柿炒鸡蛋、清蒸鲈鱼、麻婆豆腐、蚝油西兰花、冬瓜汤；"
                                 "清单见表 7-1 说明，其余 341 类由人工补录")
    insert_row_after(tb, "核心检测菜品（10 类）",
                     ["三态重量来源",
                      "user_input（用户称重）/ portion_reference（份量参考）/ model_estimate（模型估算）；"
                      "估算值不得表述为称重值，检测框面积不得直接换算为重量"])
    insert_row_after(tb, "三态重量来源",
                     ["合成检测数据",
                      "由单菜品图拼贴生成的多菜品训练图像，真值框来自粘贴坐标；用于缺少真实标注时的替代方案，"
                      "其指标为合成域上限，不代表真实多菜品照片性能"])
    log.append(("OK  ", "表 B-1 修订"))

    # ================= 表 C-1 参考文档 =================
    tc = find_table(doc, ["文档 / 来源", "用途"])
    assert tc is not None, "未找到表 C-1"
    insert_row_after(tc, "《AI饮食记录营养分析助手项目任务书 V1.0.0》",
                     ["DFood-TJ 中餐食物数据集与营养表（density.xlsx）",
                      "351 类中餐菜品图片与营养成分数据来源"])
    log.append(("OK  ", "表 C-1 修订"))

    # ================= 8.2 追加验收条款 =================
    doc.add_paragraph(
        "识别链路以分类模型输出的 Top-3 为菜品判定依据，检测框仅用于一图多菜的切分；"
        "模型未覆盖的菜品走人工补录分支，并在界面标注识别状态（ok / empty / low_confidence）。"
        "营养计算必须按 food_id 精确查询营养库，重量须带三态来源标注，检测框面积不得直接换算为重量。")
    log.append(("OK  ", "8.2 追加条款"))

    doc.save(DST)
    print("已保存:", DST)
    print("\n--- 修订日志 ---")
    for st, name in log:
        print(st, name)


if __name__ == "__main__":
    main()
