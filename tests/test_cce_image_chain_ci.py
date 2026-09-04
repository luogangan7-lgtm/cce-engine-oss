#!/usr/bin/env python3
"""图片档全链回放 —— **CI 那一半**(合成素材)。

## 晋升条件原本自相矛盾, 这里把它拆开
注册表记的是「晋升 production_github 需要: 图片档的 CI 全链回放 + 真实素材」。
实际做的时候发现这两半**不能同时满足**:
真实素材带真名, 而边界闸 check_boundary 是文本闸(`read_text(errors="ignore")`),
**看不见 PNG 像素里的人脸和屏幕上的 handle** —— 素材进公开仓, 闸会给假绿。
⇒ 拆成两半, 各自可验, 缺一不算晋升:
   ① 本机真实素材回放  probes/image_chain_real_material.py  → 2026-09-04 实测 6/6 PASS
   ② CI 合成素材回放    本文件                               → 到处都能跑

## ★ 不静默跳过
缺 Pillow/rapidocr **直接红**, 不 skip。理由: 本项目记过的同一类错——
「环境降级下断言静默变成恒真」。CI 由 requirements-media.txt 保证装上。
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import cce_synth_image as SI
except Exception as e:                                    # noqa: BLE001
    raise SystemExit(f"★ 缺媒体依赖({e}) —— 本测试**不 skip**: "
                     "一 skip, 「CI 全链回放」这个晋升条件就只是名义上满足。"
                     "装: pip install -r requirements-media.txt")

import cce_image_ingest as II

with tempfile.TemporaryDirectory() as td:
    png = os.path.join(td, "synth.png")
    gt = SI.synth(png)["ground_truth"]

    # ── ① 像素 → 视觉观察 ────────────────────────────────────────────────
    vo = II.visual_observation(png)
    assert vo["kind"] == "cce.visual_observation.v1"
    assert vo["asset"]["media_type"] == "image"
    assert vo["selector"] == {"type": "whole", "t": None}, "静态图必须是退化 selector"
    assert vo["provenance"], "★ 无溯源的观察不许进链(铁律 1)"
    ok, errs = II.validate(vo)
    assert ok, f"★ 不合 cce.visual_observation.v1: {errs}"

    got = [o["value"] for o in vo["observations"] if o["channel"] == "ocr_text"]
    # 下限检查: 干净渲染文字读不出 ⇒ 引擎没在工作, 后面 complete=true 就是空转
    assert got == gt, f"★ OCR 下限检查失败: 期望 {gt} 实得 {got}"
    for o in vo["observations"]:
        r = o.get("region") or {}
        assert r.get("unit") == "pixel" and len(r.get("xywh", [])) == 4, \
            "★ 结论必须能回指图像区域(2026-08-15 登记的 P0)"

    # ── ② 解析产物 → media_ingest 链 ────────────────────────────────────
    art = os.path.join(td, "synth.parse.json")
    json.dump(II.to_parse_artifact(vo, "synth.png"), open(art, "w", encoding="utf-8"),
              ensure_ascii=False)
    od = os.path.join(td, "out")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/cce_full_run.py"),
                        "--mode", "media_ingest", "--text-file", art,
                        "--context", "CI 合成素材图片链回放", "--outdir", od],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, f"★ 链跑失败: {(r.stderr or r.stdout)[-400:]}"
    blob = r.stdout + "".join(open(os.path.join(od, f), encoding="utf-8").read()
                              for f in os.listdir(od) if f.endswith(".json"))
    assert '"complete": true' in blob or '"complete":true' in blob, "★ 链未完成"
    assert "extraction_quality" in blob and "cross_domain_calibration" in blob, \
        "★ 抽取质量与跨域标定必须**具名扣发**, 不许静默通过"

    # ── ③ 三态: 引擎不可用 ≠ 查过没有 ──────────────────────────────────
    import builtins
    _real = builtins.__import__
    builtins.__import__ = lambda n, *a, **k: (_ for _ in ()).throw(ImportError("强制")) \
        if "rapidocr" in n.lower() else _real(n, *a, **k)
    try:
        for m in [k for k in list(sys.modules) if "rapidocr" in k.lower()]:
            del sys.modules[m]
        st = II.to_parse_artifact(II.visual_observation(png), "x")["completeness"]
    finally:
        builtins.__import__ = _real
    assert st["status"] == "failed" and st["error"], \
        f"★ 「跑不了」被写成了 {st['status']!r} —— 三态不许压成两态"

print("test_cce_image_chain_ci: OK (合成素材 像素→观察→链: schema 合格 | OCR 下限 "
      f"{len(gt)}/{len(gt)} 精确 | 每条结论带 xywh 区域 | complete=true 且抽取质量具名扣发 | "
      "反向: 引擎不可用记 failed 不记 empty)"
      "\n  ★ 合成图**不**代表真实素材的 OCR 准确率(无压缩/无花字/无遮挡) —— 抽取质量仍记未测")
