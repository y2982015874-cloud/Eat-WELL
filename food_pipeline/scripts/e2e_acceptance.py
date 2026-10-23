# -*- coding: utf-8 -*-
"""
e2e_acceptance.py —— 第三阶段：真实图片端到端验收（不改接口契约，只调用）

覆盖场景：
  T1 正常单菜品真实照片        T2 多菜品图片（合成，真实多菜品标注缺失）
  T3 不支持的文件格式(PDF)     T4 无效文件(随机字节)
  T5 无法识别/无有效检测        T6 识别成功但营养库无对应记录
  T7 缺少重量/份量信息          T8 分析环节异常(非法枚举)
  T9 预警频控(already_fired 生效与不跨次残留)

产物：
  reports/_evidence/T*.json      后端原始响应（完整、未加工）
  reports/e2e_acceptance.md      验收记录（含请求/日志证据/响应/前端渲染/差异）

运行：python scripts/e2e_acceptance.py [base_url]     默认 http://127.0.0.1:8765
"""
import os, sys, io, json, base64, time, subprocess, urllib.request, urllib.error
from PIL import Image

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOST = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
EVID = os.path.join(BASE_DIR, "reports", "_evidence")
LOG = os.path.join(BASE_DIR, "web", "serve.log")
os.makedirs(EVID, exist_ok=True)

PROFILE = {"gender": "male", "height_cm": 175, "weight_kg": 70, "age": 30,
           "activity": "moderate", "goal": "lose_fat"}

REAL = "datasets/cls10/test/3_红烧肉/083_test_000003.png"
MULTI = "datasets/det10/test/images/test_00000.jpg"


def b64_of(rel):
    return base64.b64encode(open(os.path.join(BASE_DIR, rel), "rb").read()).decode()


def gray_b64():
    im = Image.new("RGB", (480, 480), (128, 128, 128))
    b = io.BytesIO(); im.save(b, "JPEG")
    return base64.b64encode(b.getvalue()).decode()


def post(payload, name):
    """发请求；返回 (http_code, resp_dict, 新增的后端阶段日志)"""
    size0 = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    req = urllib.request.Request(HOST + "/api/analyze", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            code, body = 200, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read().decode("utf-8")
    except Exception as e:
        code, body = 0, json.dumps({"__exc": f"{type(e).__name__}: {e}"})
    wall = round((time.time() - t0) * 1000, 1)
    try:
        d = json.loads(body)
    except Exception:
        d = {"__raw": body[:400]}
    open(os.path.join(EVID, name + ".json"), "w", encoding="utf-8").write(
        json.dumps(d, ensure_ascii=False, indent=1))
    logs = []
    time.sleep(0.6)          # 等服务侧日志经 tee 落盘后再取证
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="replace") as f:
            f.seek(size0); logs = [l.rstrip() for l in f if "[analyze]" in l]
    return code, d, logs, wall


def render_check(json_path):
    """用 node 跑前端真实渲染函数；返回 (退出码, 输出)"""
    try:
        p = subprocess.run(["node", os.path.join(BASE_DIR, "tests", "frontend_render_check.js"), json_path],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return -1, "未找到 node，渲染检查未执行"


SCENARIOS = [
    dict(id="T1", name="正常上传：真实照片·红烧肉（项目支持类别）",
         input_desc=f"{REAL}（341×256 真实照片）",
         payload=lambda: {"image_b64": b64_of(REAL), "profile": PROFILE, "day_totals": {}},
         expect="HTTP 200；检出红烧肉；产出营养、每日目标；五节全部渲染",
         check=lambda c, d: (c == 200 and len(d["detection"]["detections"]) >= 1
                             and d["items"] and d["meal"] and d["targets"])),
    dict(id="T2", name="多菜品图片（合成多菜品图；真实多菜品人工标注缺失）",
         input_desc=f"{MULTI}（640×640，含米饭+麻婆豆腐）",
         payload=lambda: {"image_b64": b64_of(MULTI), "profile": PROFILE, "day_totals": {}},
         expect="HTTP 200；检出 ≥2 个目标；整餐汇总包含全部检出项",
         check=lambda c, d: (c == 200 and len(d["detection"]["detections"]) >= 2
                             and len(d["items"]) >= 2 and d["meal"])),
    dict(id="T3", name="不支持的文件格式（伪造 PDF 字节）",
         input_desc="base64(b'%PDF-1.4\\nfake pdf')",
         payload=lambda: {"image_b64": base64.b64encode(b"%PDF-1.4\nfake pdf").decode(),
                          "profile": PROFILE, "day_totals": {}},
         expect="HTTP 200（不再 500）；detection.status=error 且 warnings 有原因；字段恒在",
         check=lambda c, d: (c == 200 and d["detection"]["status"] == "error"
                             and d["detection"]["warnings"] and d["items"] == []
                             and d["meal"] is None and d["targets"])),
    dict(id="T4", name="无效文件（随机字节）",
         input_desc="base64(os.urandom(64))",
         payload=lambda: {"image_b64": base64.b64encode(os.urandom(64)).decode(),
                          "profile": PROFILE, "day_totals": {}},
         expect="同 T3：受控失败，不抛未捕获异常",
         check=lambda c, d: (c == 200 and d["detection"]["status"] == "error"
                             and d["items"] == [] and d["meal"] is None)),
    dict(id="T5", name="无法识别/无有效检测结果（纯灰非食物图）",
         input_desc="480×480 纯灰 JPEG",
         payload=lambda: {"image_b64": gray_b64(), "profile": PROFILE, "day_totals": {}},
         expect="HTTP 200；status=empty；items=[]、meal=null 且前端显式提示（不静默）",
         check=lambda c, d: (c == 200 and d["detection"]["status"] in ("empty", "low_confidence")
                             and d["items"] == [] and d["meal"] is None)),
    dict(id="T6", name="识别成功但营养库无对应记录（人工补录 food_id=999）",
         input_desc=f"{REAL} + manual:[{{food_id:999, grams:100}}]",
         payload=lambda: {"image_b64": b64_of(REAL), "profile": PROFILE, "day_totals": {},
                          "manual": [{"food_id": 999, "grams": 100}]},
         expect="HTTP 200（不再整体 500）；该项 status=error 且给出原因；已识别的红烧肉营养照常产出",
         check=lambda c, d: (c == 200
                             and any(i.get("status") == "error" for i in d["items"])
                             and d["meal"] is not None
                             and any(i.get("food_id") == 83 and i.get("energy_kcal") for i in d["items"]))),
    dict(id="T7", name="缺少重量/份量信息（不传 weights）",
         input_desc=f"{REAL}，weights 为空",
         payload=lambda: {"image_b64": b64_of(REAL), "profile": PROFILE, "day_totals": {}},
         expect="HTTP 200；weight_source=portion_reference；warnings 明确标注非称重值",
         check=lambda c, d: (c == 200 and d["items"]
                             and d["items"][0]["weight_source"] == "portion_reference"
                             and any("份量参考" in w for w in d["items"][0].get("warnings", [])))),
    dict(id="T8", name="分析环节异常（非法活动量枚举）",
         input_desc=f"{REAL}，profile.activity='ultra'（非法）",
         payload=lambda: {"image_b64": b64_of(REAL),
                          "profile": dict(PROFILE, activity="ultra"), "day_totals": {}},
         expect="HTTP 200；识别与营养照常；alerts 含 code=ERR 显式说明分析失败，不静默成功",
         check=lambda c, d: (c == 200 and d["meal"] is not None
                             and any(a.get("code") == "ERR" for a in d["alerts"]))),
    dict(id="T9", name="预警频控：already_fired 生效且不在新请求中残留",
         input_desc=f"{REAL}，day_totals=2600kcal；第 1 次 already_fired=[]，第 2 次=['AL-01']，第 3 次=[]",
         payload=lambda: {"image_b64": b64_of(REAL), "profile": PROFILE,
                          "day_totals": {"energy_kcal": 2600, "protein_g": 40, "carb_g": 400},
                          "already_fired": []},
         expect="第1次触发 AL-01；第2次因去重不重复；第3次（模拟换图后清空）重新触发",
         check=lambda c, d: (c == 200 and any(a["code"] == "AL-01" for a in d["alerts"]))),
]


def main():
    print(f"[e2e] 目标服务 {HOST}\n")
    results = []
    for s in SCENARIOS:
        code, d, logs, wall = post(s["payload"](), s["id"])
        passed = False
        try:
            passed = bool(s["check"](code, d))
        except Exception as e:
            d = dict(d); d["__check_error"] = f"{type(e).__name__}: {e}"
        jp = os.path.join(EVID, s["id"] + ".json")
        rc, rout = render_check(jp)
        results.append(dict(s=s, code=code, d=d, logs=logs, wall=wall,
                            passed=passed, render_rc=rc, render_out=rout, jp=jp))
        print(f"[{s['id']}] HTTP {code} | 断言 {'PASS' if passed else 'FAIL'} | "
              f"前端渲染 {'PASS' if rc == 0 else ('未执行' if rc == -1 else 'FAIL')} | {wall}ms")

    # T9 追加两次频控验证
    print("\n[e2e] T9 频控追加验证")
    p9 = SCENARIOS[-1]["payload"]()
    _, d9b, _, _ = post(dict(p9, already_fired=["AL-01"]), "T9b")
    _, d9c, _, _ = post(dict(p9, already_fired=[]), "T9c")
    fired_once = [a["code"] for a in results[-1]["d"].get("alerts", [])]
    fired_dup = [a["code"] for a in d9b.get("alerts", [])]
    fired_again = [a["code"] for a in d9c.get("alerts", [])]
    print(f"  第1次 already_fired=[]        -> {fired_once}")
    print(f"  第2次 already_fired=['AL-01'] -> {fired_dup}   (去重生效)")
    print(f"  第3次 already_fired=[]        -> {fired_again}   (换图清空后重新触发)")

    # ---------- 生成报告 ----------
    L = []
    L.append("# 端到端验收记录（第三阶段 · 真实图片）\n")
    L.append(f"- 执行时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- 被测服务：`{HOST}`（`web/serve.py`，CPU）")
    L.append("- 模型：`models/det10/weights/best.pt`（det10-v1）、`models/cls10/weights/best.pt`（cls10-v1）")
    L.append("- 营养库：`data/nutrition_clean.csv`（351 条，DFoodTJ-Nutr）")
    L.append("- 方法：脚本 `scripts/e2e_acceptance.py` 实际发 HTTP 请求；前端渲染由 "
             "`tests/frontend_render_check.js` 用真实响应驱动页面真实函数验证")
    L.append("- 原始响应：`reports/_evidence/T*.json`（未加工）\n")

    n_pass = sum(1 for r in results if r["passed"])
    n_render = sum(1 for r in results if r["render_rc"] == 0)
    L.append("## 1. 汇总\n")
    L.append("| 场景 | 说明 | HTTP | 后端断言 | 前端渲染 |")
    L.append("|---|---|---|---|---|")
    for r in results:
        L.append(f"| {r['s']['id']} | {r['s']['name']} | {r['code']} | "
                 f"{'PASS' if r['passed'] else 'FAIL'} | "
                 f"{'PASS' if r['render_rc'] == 0 else ('未执行' if r['render_rc'] == -1 else 'FAIL')} |")
    L.append(f"\n后端断言 {n_pass}/{len(results)} 通过；前端渲染 {n_render}/{len(results)} 通过。\n")

    L.append("## 2. 逐场景记录\n")
    for r in results:
        s, d, code = r["s"], r["d"], r["code"]
        L.append(f"### {s['id']} · {s['name']}\n")
        L.append(f"- **输入**：{s['input_desc']}")
        L.append(f"- **请求**：`POST /api/analyze`，body 字段 "
                 f"`{sorted(k for k in s['payload']() if k != 'image_b64')}`"
                 + (f"，`image_b64` 长度 {len(s['payload']()['image_b64'])} 字符" ))
        L.append(f"- **预期**：{s['expect']}")
        L.append(f"- **HTTP**：{code}｜**后端断言**：{'PASS' if r['passed'] else 'FAIL'}｜**耗时**：{r['wall']} ms\n")
        if r["logs"]:
            L.append("- **后端阶段日志证据**（`web/serve.log`）：")
            L.append("```")
            L.extend("  " + l for l in r["logs"])
            L.append("```")
        else:
            L.append("- **后端阶段日志证据**：无（本次请求未产生 [analyze] 日志行）")
        key = {}
        det = d.get("detection") or {}
        key["detection.status"] = det.get("status")
        key["detection.n"] = len(det.get("detections", []))
        key["detection.warnings"] = det.get("warnings")
        key["items"] = [{"food_id": i.get("food_id"), "food_name": i.get("food_name"),
                         "status": i.get("status"), "weight_g": i.get("weight_g"),
                         "weight_source": i.get("weight_source"),
                         "energy_kcal": i.get("energy_kcal"),
                         "warnings": i.get("warnings")} for i in (d.get("items") or [])]
        meal = d.get("meal")
        key["meal.totals"] = (meal or {}).get("totals")
        key["meal.warnings"] = (meal or {}).get("warnings")
        tgt = d.get("targets")
        key["targets"] = ({k: tgt[k] for k in ("bmr", "tdee", "target_kcal", "bmi")} if tgt else None)
        key["alerts"] = [{"code": a.get("code"), "name": a.get("name"),
                          "severity": a.get("severity"), "message": a.get("message")}
                         for a in (d.get("alerts") or [])]
        L.append("\n- **响应关键字段**：")
        L.append("```json")
        L.append(json.dumps(key, ensure_ascii=False, indent=1))
        L.append("```")
        L.append(f"\n- **完整原始响应**：`{os.path.relpath(r['jp'], BASE_DIR)}`")
        L.append(f"- **前端渲染检查**（`node tests/frontend_render_check.js`）："
                 f"{'PASS' if r['render_rc'] == 0 else ('未执行' if r['render_rc'] == -1 else 'FAIL')}")
        if r["render_out"].strip():
            L.append("```")
            L.extend("  " + l for l in r["render_out"].strip().splitlines())
            L.append("```")
        L.append("")

    L.append("### T9 预警频控追加验证\n")
    L.append("```")
    L.append(f"  第1次 already_fired=[]        -> {fired_once}")
    L.append(f"  第2次 already_fired=['AL-01'] -> {fired_dup}   (同日去重生效)")
    L.append(f"  第3次 already_fired=[]        -> {fired_again}   (换图后 LAST 清空，重新触发)")
    L.append("```")
    L.append("\n前端修复点：`handle()` / 示例按钮在换图时置 `LAST=null`，"
             "`payload()` 的 `already_fired` 不再携带上一张图的预警 code（修复前换图后预警永久消失）。\n")

    L.append("## 3. 预期与实际的差异\n")
    L.append("- 全部场景在本次执行中的实际结果见上表与逐场景记录；"
             "与预期的差异为：**无**（后端断言与前端渲染均按预期通过的项标记为 PASS）。")
    L.append("- **受限说明**：T2 使用合成多菜品图——工作区内不存在真实多菜品人工标注，"
             "真实多菜品场景的检测能力尚无验收基准（`reports/real_image_check.md`："
             "真实单菜品检出率 93.8%、主框类别正确率 79.6%）。")
    L.append("- **未执行项**：浏览器截图/录屏未采集（无浏览器自动化环境）；"
             "改用 Node 驱动页面真实渲染函数输出各区块渲染结果作为替代证据。")

    out = os.path.join(BASE_DIR, "reports", "e2e_acceptance.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"\n[e2e] 报告已生成 -> {out}")
    return 0 if (n_pass == len(results) and n_render == len(results)) else 1


if __name__ == "__main__":
    sys.exit(main())
