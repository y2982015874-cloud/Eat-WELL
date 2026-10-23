# -*- coding: utf-8 -*-
"""
serve.py — 验收用本地可视化服务（零第三方 Web 依赖，仅标准库 http.server）
  GET  /                页面
  GET  /api/health      模型与营养库就绪状态
  GET  /api/foods       351 类菜品清单（供人工补录下拉）
  POST /api/analyze     上传图片(base64) → 检测 + 分类 + 营养计算 + 目标 + 预警

启动 : python web/serve.py [port]     默认 8765，仅监听 127.0.0.1
"""
import os, sys, io, json, time, base64, tempfile, argparse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

CLS_W = os.path.join(BASE, "models", "cls10", "weights", "best.pt")
DET_W = os.path.join(BASE, "models", "det10", "weights", "best.pt")
FONT = "C:/Windows/Fonts/msyh.ttc"
MAX_SIDE = 1280

COLORS = [(230, 57, 70), (29, 131, 115), (243, 156, 18), (52, 152, 219), (155, 89, 182),
          (211, 84, 0), (46, 204, 113), (192, 57, 43), (41, 128, 185), (142, 68, 173)]

_state = {"ready": False, "error": None, "cls": None, "det": None,
          "db": None, "calc": None, "cls_map": None}

# 内置示例图：合成多菜品 / 真实照片（检出成功） / 真实照片（触发分类器降级）
SAMPLES = [
    {"key": "synth", "label": "合成多菜品图", "path": "datasets/det10/test/images/test_00000.jpg"},
    {"key": "real_ok", "label": "真实照片·红烧肉（成功检出）",
     "path": "datasets/cls10/test/3_红烧肉/083_test_000003.png"},
    {"key": "real_fb", "label": "真实照片·米饭（演示降级）",
     "path": "datasets/cls10/test/0_米饭/000_test_000000.png"},
]


def boot():
    """预加载模型与营养库（首次请求前完成，避免每次请求冷启动）"""
    try:
        from ultralytics import YOLO
        from nutrition.db import NutritionDB
        from nutrition.calculator import NutritionCalculator
        from infer import load_class_mapping

        _state["cls"] = YOLO(CLS_W)
        _state["det"] = YOLO(DET_W)
        _state["db"] = NutritionDB()
        _state["calc"] = NutritionCalculator(_state["db"])
        _state["cls_map"] = load_class_mapping()
        _state["ready"] = True
        print(f"[boot] 模型与营养库加载完成，营养库 {len(_state['db'])} 条")
    except Exception as e:
        _state["error"] = f"{type(e).__name__}: {e}"
        print("[boot] FAILED:", _state["error"], file=sys.stderr)


def annotate(img_path, detections):
    """画检测框 + 中文标签，返回 (标注图 base64, 各框裁剪图 base64 列表)"""
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(img_path) as src:
        orig_w = src.width
        base = src.convert("RGB")      # 原尺寸副本：既用于标注底图，也用于按原坐标裁剪
    im = base.copy()
    if max(im.size) > MAX_SIDE:
        r = MAX_SIDE / max(im.size)
        im = im.resize((int(im.width * r), int(im.height * r)))
    scale = im.width / orig_w
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(FONT, size=max(14, im.width // 38))
    except Exception:
        font = ImageFont.load_default()
    crops = []
    for i, d in enumerate(detections):
        x1, y1, x2, y2 = [v * scale for v in d["bbox_xyxy"]]
        c = COLORS[d["class_id"] % len(COLORS)]
        dr.rectangle([x1, y1, x2, y2], outline=c, width=max(2, im.width // 220))
        label = f'{i+1}. {d["food_name"]} {d["confidence"]:.2f}'
        tb = dr.textbbox((x1, y1), label, font=font)
        dr.rectangle([tb[0] - 3, tb[1] - 3, tb[2] + 3, tb[3] + 3], fill=c)
        dr.text((x1, y1), label, fill=(255, 255, 255), font=font)
        # 裁剪原图区域
        cx1, cy1, cx2, cy2 = [int(v) for v in d["bbox_xyxy"]]
        cx1, cy1 = max(0, cx1), max(0, cy1)
        crop = base.crop((cx1, cy1, min(cx2, base.width), min(cy2, base.height)))
        crop.thumbnail((180, 180))
        b = io.BytesIO(); crop.save(b, "JPEG", quality=82)
        crops.append(base64.b64encode(b.getvalue()).decode())
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode(), crops


def _log(rid, stage, ms, status, detail=""):
    """阶段日志：请求标识 + 阶段 + 耗时 + 成败 + 原因。不记录图片内容与个人敏感信息。"""
    sys.stderr.write(f"[analyze][{rid}] {stage:14s} {ms:8.1f}ms {status:5s} {detail}\n")
    sys.stderr.flush()      # 经管道(tee)输出时立即落盘，保证日志可实时取证


def _meta(W, H, det_ms, cls_ms, t_all):
    return {"image_width": W, "image_height": H, "det_ms": det_ms, "cls_ms": cls_ms,
            "total_ms": round((time.time() - t_all) * 1000, 1),
            "device": "CPU", "cls_version": "cls10-v1", "det_version": "det10-v1"}


def _targets_and_alerts(payload, meal, rid):
    """目标与预警（职责独立：只依赖 profile / day_totals / 本餐汇总，不含识别逻辑）"""
    import datetime
    from nutrition.advisor import RecommendationEngine, AlertEngine, GoalType, ActivityLevel

    p = payload.get("profile") or {}
    targets, alerts = None, []
    if not (p.get("height_cm") and p.get("weight_kg")):
        _log(rid, "targets", 0, "SKIP", "profile 缺身高/体重，未计算每日目标")
        return None, []
    try:
        t0 = time.time()
        eng = RecommendationEngine()
        targets = eng.compute(p.get("gender", "male"), float(p["height_cm"]),
                              float(p["weight_kg"]), int(p.get("age", 30)),
                              ActivityLevel(p.get("activity", "moderate")),
                              GoalType(p.get("goal", "maintain")))
        day = payload.get("day_totals") or {}
        tot = meal.totals if meal else {}

        def _f(k):
            v = day.get(k)
            if v in (None, ""):
                v = tot.get(k)
            return float(v) if v not in (None, "") else None

        ae = AlertEngine()
        alerts = [a.__dict__ for a in ae.evaluate(
            targets,
            {"energy_kcal": _f("energy_kcal"), "protein_g": _f("protein_g"), "carb_g": _f("carb_g")},
            GoalType(p.get("goal", "maintain")),
            datetime.date.today().isoformat(),
            meal_kcal=(tot.get("energy_kcal") if tot else None),
            already_fired=set(payload.get("already_fired") or []))]
        _log(rid, "targets+alerts", round((time.time() - t0) * 1000, 1), "OK", f"alerts={len(alerts)}")
    except Exception as e:
        # 不得为消除报错而返回成功：明确标记为分析失败并保留原因
        alerts = [{"code": "ERR", "name": "目标/预警计算失败", "severity": "info",
                   "basis": None, "trigger_time": None,
                   "message": f"{type(e).__name__}: {e}"}]
        _log(rid, "targets+alerts", 0, "FAIL", f"{type(e).__name__}: {e}")
    return targets, alerts


def analyze(payload, rid=""):
    from PIL import Image
    from infer import infer_image
    from nutrition.calculator import WeightSource

    t_all = time.time()
    b64 = payload["image_b64"].split(",", 1)[-1]
    raw = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(raw); path = f.name
    try:
        # ---- 0) 图片解码：受控失败，按契约返回 status=error，不抛未捕获异常 ----
        try:
            with Image.open(path) as im_h:
                W, H = im_h.size
            _log(rid, "decode", round((time.time() - t_all) * 1000, 1), "OK", f"{W}x{H}")
        except Exception as e:
            W = H = None
            msg = f"图片读取失败：{type(e).__name__}: {e}（请上传 jpg/png 等有效图片文件）"
            _log(rid, "decode", round((time.time() - t_all) * 1000, 1), "FAIL", f"{type(e).__name__}")
            targets, alerts = _targets_and_alerts(payload, None, rid)
            return {
                "meta": _meta(W, H, 0.0, 0.0, t_all),
                "image_b64": None, "orig_b64": None,
                "detection": {"image_id": rid, "model_version": "det10-v1", "task_type": "detection",
                              "image_width": None, "image_height": None, "detections": [],
                              "status": "error", "warnings": [msg]},
                "fallback": False,
                "classification": {"top5": [], "status": "error"},
                "items": [], "meal": None,
                "targets": targets.to_dict() if targets else None,
                "alerts": alerts,
            }

        # 原图（无框）base64，供前端"原图/标注图"切换
        with Image.open(path) as im0:
            im0 = im0.convert("RGB")
            if max(im0.size) > MAX_SIDE:
                r0 = MAX_SIDE / max(im0.size)
                im0 = im0.resize((int(im0.width * r0), int(im0.height * r0)))
            b0 = io.BytesIO(); im0.save(b0, "JPEG", quality=88)
            orig_b64 = base64.b64encode(b0.getvalue()).decode()

        # ---- 1) 检测 ----
        t0 = time.time()
        det_out = infer_image(_state["det"], path, "detection", float(payload.get("conf", 0.25)), "det10-v1")
        det_ms = round((time.time() - t0) * 1000, 1)
        _log(rid, "detect", det_ms, det_out.get("status", "?"),
             f"{len(det_out['detections'])}框:" +
             ",".join(f"{d['food_name']}{d['confidence']:.2f}" for d in det_out["detections"]))
        ann_b64, crops = annotate(path, det_out["detections"])
        for d, c in zip(det_out["detections"], crops):
            d["crop_b64"] = c

        # ---- 2) 分类（整图，适用单菜品场景）----
        t0 = time.time()
        cls_out = infer_image(_state["cls"], path, "classification", 0.25, "cls10-v1")
        cls_ms = round((time.time() - t0) * 1000, 1)
        # top5 必须是**完整 5 个候选**（PRD MI-01 的 Top-3 验收口径依赖前 3 候选）。
        # 注意：不能改用 cls_out["detections"]——infer_image 对分类候选做了 <0.3 过滤，
        # 会使 top5 退化（实测仅剩 1 项），从而破坏 Top-3 口径，故此处保留独立的 probs 读取。
        r = _state["cls"].predict(path, verbose=False)[0]
        probs = r.probs
        top5 = []
        for idx in probs.top5:
            i = int(idx)
            top5.append({"class_id": i, **_state["cls_map"][i],
                         "prob": round(float(probs.data[i]), 4)})
        _log(rid, "classify", cls_ms, cls_out.get("status", "?"),
             f"{len(top5)}候选:" + (f"{top5[0]['food_name']}{top5[0]['prob']:.2f}" if top5 else "无"))

        # ---- 3) 营养（按前端传入重量 / 缺省走份量参考）----
        db, calc = _state["db"], _state["calc"]
        weights = payload.get("weights") or {}

        # 降级：检测器未检出时，若分类器 Top-1 置信 ≥0.5，用其作为唯一候选（整图口径）
        cands = list(det_out["detections"])
        fallback = False
        if not cands and top5 and top5[0]["prob"] >= 0.5:
            fallback = True
            cands = [{"class_id": top5[0]["class_id"], "food_id": top5[0]["food_id"],
                      "food_name": top5[0]["food_name"], "confidence": top5[0]["prob"],
                      "bbox_xyxy": [0, 0, W, H]}]

        items, entries = [], []
        for i, d in enumerate(cands):
            fid = d["food_id"]
            w = weights.get(str(fid)) or {}
            src, grams, portions = WeightSource.PORTION_REFERENCE, None, 1.0
            gv = w.get("grams")
            if gv not in (None, "", 0):          # 0 视为"未提供"，回退份量参考并显式提示
                src, grams = WeightSource.USER_INPUT, float(gv)
            elif w.get("portions"):
                src, portions = WeightSource.PORTION_REFERENCE, float(w["portions"])
            ref = db.reference_portions.get(fid)
            try:
                if src == WeightSource.USER_INPUT:
                    it = calc.calc_item(fid, grams, src)
                else:
                    it = calc.calc_item(fid, None, src, portions=portions)
                dct = it.to_dict()
                _log(rid, f"nutrition[{i}]", 0, "OK",
                     f"food_id={fid} {dct.get('weight_g')}g src={dct.get('weight_source')}")
            except Exception as e:
                # 单项失败不得拖垮整条链路：该项标记 error 并保留原因，其余项照常出结果
                dct = {"food_id": fid, "food_name": d["food_name"], "status": "error",
                       "weight_g": None, "weight_source": src.value,
                       "energy_kcal": None, "carb_g": None, "fat_g": None,
                       "protein_g": None, "fiber_g": None, "per_100g": None,
                       "warnings": [f"营养计算失败：{type(e).__name__}: {e}"],
                       "error": f"{type(e).__name__}: {e}"}
                _log(rid, f"nutrition[{i}]", 0, "FAIL", f"food_id={fid} {type(e).__name__}: {e}")
            if gv == 0:
                dct.setdefault("warnings", []).append("重量输入为 0，已回退为份量参考（非称重值）")
            dct["ref_portion"] = ({"label": ref.label, "grams": ref.grams_per_portion,
                                   "status": ref.status} if ref else None)
            dct["confidence"] = d["confidence"]
            dct["bbox_xyxy"] = d["bbox_xyxy"] if not fallback else None
            if fallback:
                dct["fallback"] = True
                dct.setdefault("warnings", []).append(
                    "检测器未检出，已用分类器 Top-1 兜底（整图口径，无定位框）")
            items.append(dct)
            if dct.get("weight_g") and dct.get("status") != "error":
                entries.append({"food_id": fid, "weight_g": dct["weight_g"], "weight_source": src})

        # 人工补录项（逐项受控：营养库缺记录只影响该项，不影响已识别出的结果）
        for i, m in enumerate(payload.get("manual") or []):
            try:
                fid, grams = int(m["food_id"]), float(m.get("grams") or 0)
            except (TypeError, ValueError, KeyError) as e:
                items.append({"food_id": None, "food_name": None, "status": "error", "manual": True,
                              "weight_g": None, "weight_source": WeightSource.USER_INPUT.value,
                              "warnings": [f"人工补录参数非法：{type(e).__name__}: {e}"],
                              "error": f"{type(e).__name__}: {e}"})
                _log(rid, f"manual[{i}]", 0, "FAIL", f"参数非法 {type(e).__name__}")
                continue
            if grams <= 0:
                continue
            try:
                it = calc.calc_item(fid, grams, WeightSource.USER_INPUT)
                dct = it.to_dict(); dct["manual"] = True
                _log(rid, f"manual[{i}]", 0, "OK", f"food_id={fid} {grams}g")
            except Exception as e:
                dct = {"food_id": fid, "food_name": None, "status": "error", "manual": True,
                       "weight_g": grams, "weight_source": WeightSource.USER_INPUT.value,
                       "energy_kcal": None, "carb_g": None, "fat_g": None,
                       "protein_g": None, "fiber_g": None, "per_100g": None,
                       "warnings": [f"营养库无此记录或计算失败：{type(e).__name__}: {e}"],
                       "error": f"{type(e).__name__}: {e}"}
                _log(rid, f"manual[{i}]", 0, "FAIL", f"food_id={fid} {type(e).__name__}")
            items.append(dct)
            if dct.get("weight_g") and dct.get("status") != "error":
                entries.append({"food_id": fid, "weight_g": grams,
                                "weight_source": WeightSource.USER_INPUT})

        try:
            meal = calc.calc_meal(entries) if entries else None
        except Exception as e:
            meal = None
            _log(rid, "meal", 0, "FAIL", f"{type(e).__name__}: {e}")

        # ---- 4) 目标与预警 ----
        targets, alerts = _targets_and_alerts(payload, meal, rid)
        _log(rid, "TOTAL", round((time.time() - t_all) * 1000, 1), "OK",
             f"items={len(items)} meal={'有' if meal else '无'} alerts={len(alerts)}")

        return {
            "meta": _meta(W, H, det_ms, cls_ms, t_all),
            "image_b64": ann_b64,
            "orig_b64": orig_b64,
            "detection": det_out,
            "fallback": fallback,
            "classification": {"top5": top5, "status": cls_out.get("status")},
            "items": items,
            "meal": meal.to_dict() if meal else None,
            "targets": targets.to_dict() if targets else None,
            "alerts": alerts,
        }
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[http] %s\n" % (fmt % args))

    def do_GET(self):
        u = urlparse(self.path).path
        if u in ("/", "/index.html"):
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            with open(p, encoding="utf-8") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif u == "/api/health":
            self._send(200, json.dumps({"ready": _state["ready"], "error": _state["error"],
                                        "cls_weights": os.path.exists(CLS_W),
                                        "det_weights": os.path.exists(DET_W)},
                                       ensure_ascii=False))
        elif u == "/api/samples":
            out = []
            for s in SAMPLES:
                p = os.path.join(BASE, s["path"])
                if not os.path.exists(p):
                    continue
                import mimetypes
                mt = mimetypes.guess_type(p)[0] or "image/jpeg"
                with open(p, "rb") as fh:
                    out.append({"key": s["key"], "label": s["label"],
                                "b64": "data:%s;base64,%s" % (mt, base64.b64encode(fh.read()).decode())})
            self._send(200, json.dumps(out, ensure_ascii=False))
        elif u == "/api/foods":
            if not _state["ready"]:
                return self._send(503, json.dumps({"error": "未就绪"}, ensure_ascii=False))
            db = _state["db"]
            out = [{"food_id": i, "name_zh": db.get(i).name_zh} for i in db.ids()]
            self._send(200, json.dumps(out, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))

    def do_POST(self):
        u = urlparse(self.path).path
        if u != "/api/analyze":
            return self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._send(400, json.dumps({"error": f"非法 JSON: {e}"}, ensure_ascii=False))
        if not _state["ready"]:
            return self._send(503, json.dumps({"error": _state["error"] or "模型未就绪"},
                                              ensure_ascii=False))
        rid = uuid.uuid4().hex[:8]
        try:
            self._send(200, json.dumps(analyze(payload, rid), ensure_ascii=False))
        except Exception as e:
            import traceback; traceback.print_exc()
            _log(rid, "FATAL", 0, "FAIL", f"{type(e).__name__}: {e}")
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", type=int, default=8765)
    args = ap.parse_args()
    boot()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[serve] http://127.0.0.1:{args.port}  (Ctrl+C 退出)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
