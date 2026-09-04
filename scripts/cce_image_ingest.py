#!/usr/bin/env python3
"""静态图片 → 视觉观察 → 解析产物(供 media_ingest 链消费)。

## 为什么不是新建一条图片链
2026-08-15 明确否决「**静态图片与视频帧各建一套视觉合同**」—— 会重复字段并产生漂移;
正确做法是「视频帧应是 **MediaAsset + temporal selector** 的 VisualObservation」。
⇒ 本模块把图片当作 **selector 退化(whole, t=null)的同一种东西**, 产出与 cce_video_parse
  **同形状**的解析产物, 由**同一条 `media_ingest` 链**消费。
  **不新增 profile, 不新增链, 不新增视觉合同。**

## 同时修一个 2026-08-15 就登记的 P0
「OCR 原始 box 在 _ocr_rows 中被丢弃 ⇒ 结论不能回指图像区域」。
本模块从一开始就带区域(W3C Media Fragments xywh, pixel)。

## 它**不**声称什么
· 不做场景/对象/动作识别(那要 VLM, 另算)
· C2PA/IPTC 缺失只记 `absent`, **不得据此推断媒体为假**
· 抽取质量(OCR 准确率)未测 —— 由下游 qualified_readout 具名扣发
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SCHEMA = os.path.join(ROOT, "config", "cce_visual_observation_v1.schema.json")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _dims(path: str):
    """尺寸与 EXIF 方向。取不到记 None —— **不默认 orientation=1**, 那是猜。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            ori = None
            try:
                exif = im.getexif()
                ori = exif.get(274) if exif else None
            except Exception:
                ori = None
            return im.width, im.height, (int(ori) if ori else None)
    except Exception:
        return None, None, None


def rights_state(path: str) -> dict:
    """媒体权利/来源状态。★ 三态严格分开, 不许把「查不了」写成「查过没有」。

    2026-08-15 调研结论: 缺 C2PA manifest **只能记 absent/not_available, 不能推断媒体为假**。
    库里另有一条通则: `empty_verified`(查过确实为空)与 `missing_parse_failed`(不知道)
    必须分开 —— 混为一谈是记过的事故模式。

    ★ 2026-09-03 修我自己一小时前写的错: 原来这里**硬编码 `absent`**, 而我根本没查过。
      `absent` 的意思是「查过、没有」。

    · IPTC: Pillow 的 IptcImagePlugin 能真读 ⇒ present / absent / not_available 三态都可给
    · C2PA: 官方库不在 ⇒ **不对称判定** —— 找到 JUMBF/c2pa 标记记 present(阳性证据可信);
      **没找到仍记 not_available**, 因为没有真解析器时「找不到」不等于「没有」。
    """
    out = {}
    try:
        from PIL import Image, IptcImagePlugin
        with Image.open(path) as im:
            info = IptcImagePlugin.getiptcinfo(im)
        out["iptc"] = "present" if info else "absent"      # 读成功: 两态可信
    except Exception:
        out["iptc"] = "not_available"                       # 读失败: 不知道
    try:
        head = open(path, "rb").read(2 * 1024 * 1024)
        # 只认阳性: 命中 = present; 未命中**不**降为 absent
        out["c2pa"] = "present" if (b"jumb" in head or b"c2pa" in head.lower()) \
            else "not_available"
    except Exception:
        out["c2pa"] = "not_available"
    return out


def visual_observation(path: str, *, media_type="image", t=None) -> dict:
    """一张图片(或一个视频帧)→ cce.visual_observation.v1。"""
    from cce_video_parse import _ocr_rows, OCR_CONF_MIN
    w, h, ori = _dims(path)
    obs, conf_unparsed, box_unparsed, status, err = [], 0, 0, "ok", None
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        try:
            from rapidocr import RapidOCR
        except Exception as e:
            RapidOCR = None
            status, err = "failed", f"OCR 引擎不可用: {type(e).__name__}"
    if status != "failed":
        try:
            res, _ = RapidOCR()(path)
            for text, c, box in _ocr_rows(res):
                text = (text or "").strip()
                if not text:
                    continue
                if c is None:
                    conf_unparsed += 1          # 置信度取不到: 保留文字并记账
                elif c <= OCR_CONF_MIN:
                    continue
                if box is None:
                    box_unparsed += 1           # 区域取不到: 同样记账, 不静默丢
                obs.append({"channel": "ocr_text", "assertion": "observed", "value": text,
                            "confidence": c, "language": None, "model": "RapidOCR",
                            "region": ({"unit": "pixel", "xywh": box} if box else None)})
        except Exception as e:
            status, err = "failed", f"{type(e).__name__}: {str(e)[:120]}"
    if status == "ok" and not obs:
        # ★ empty 与 failed 必须分开: 前者是「跑了但画面没字」, 后者是「通道坏了」
        status = "empty"
    return {"kind": "cce.visual_observation.v1",
            "asset": {"media_type": media_type, "sha256": _sha256(path),
                      "width": w, "height": h, "orientation": ori},
            "selector": {"type": "whole" if t is None else "temporal", "t": t},
            "observations": obs,
            "provenance": {"activity": "cce_image_ingest", "agent": None,
                           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "source_path": os.path.basename(path)},
            # ★ 真查而不是硬编码。三态分开: present / absent(查过没有) /
            #   not_available(查不了)。**不得据此推断媒体为假**(2026-08-15 调研结论)。
            "rights": rights_state(path),
            "completeness": {"status": status, "conf_unparsed": conf_unparsed,
                             "box_unparsed": box_unparsed, "error": err}}


def to_parse_artifact(vo: dict, name: str) -> dict:
    """视觉观察 → 与 cce_video_parse **同形状**的解析产物, 供 media_ingest 直接消费。

    ★ 图片没有时长; 但 media_validate 要求 duration>0。给 0.0 会被判无效产物 ——
      **不作弊**: 用一个显式的极小值并在产物里写明它是退化 selector, 不是真实时长。
    """
    texts = [o["value"] for o in vo["observations"] if o["channel"] == "ocr_text"]
    return {"name": name, "video": None, "duration": 1e-3,
            "★duration_is_degenerate": ("静态图片无时长。media_validate 要求 duration>0, "
                                        "此处为退化 selector 的占位值, **不是真实时长**。"),
            "audio": {"present": False, "status": "not_applicable_static_image"},
            "ocr": {"0.0": texts},
            "ocr_regions": {"0.0": [o.get("region", {}).get("xywh") if o.get("region") else None
                                    for o in vo["observations"] if o["channel"] == "ocr_text"]},
            "frames": [], "visual": {},
            "visual_observation": vo,
            "completeness": vo["completeness"]}


def validate(vo: dict) -> tuple[bool, list[str]]:
    """按 JSON Schema 2020-12 校验。★ 没有 jsonschema 就**判失败**, 不静默放行。"""
    try:
        import jsonschema
    except Exception:
        return False, ["jsonschema 不可用 —— 合同校验缺席即失败, 不降级放行"]
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    errs = [f"{'/'.join(str(x) for x in e.path)}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(vo)]
    return (not errs), errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("--out", help="写出解析产物(供 media_ingest 消费)")
    a = ap.parse_args()
    if os.path.splitext(a.image)[1].lower() not in IMAGE_EXT:
        raise SystemExit(f"不是支持的图片类型: {a.image}")
    vo = visual_observation(a.image)
    ok, errs = validate(vo)
    if not ok:
        print("★ 视觉观察不合合同:", *errs[:4], sep="\n  ", file=sys.stderr)
        return 1
    art = to_parse_artifact(vo, os.path.basename(a.image))
    print(json.dumps({"sha256": vo["asset"]["sha256"][:16],
                      "size": [vo["asset"]["width"], vo["asset"]["height"]],
                      "ocr_texts": len(art["ocr"]["0.0"]),
                      "with_region": sum(1 for r in art["ocr_regions"]["0.0"] if r),
                      "completeness": vo["completeness"]}, ensure_ascii=False))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(json.dumps(art, ensure_ascii=False, indent=1))
        print(f"→ {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
