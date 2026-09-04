#!/usr/bin/env python3
"""OCR 抽取质量的**上界曲线** —— 受控退化下的字符准确率。

## 为什么是「上界」而不是「准确率」
真实素材没有逐字标注(自带的 .json 是元数据: title_copy/author/comments, 不是图上文字),
所以**真实准确率测不了**。能测的是: 合成渲染文字 + **受控退化**下的准确率曲线。
合成图无花字、无描边、无遮挡、无渐变背景 ⇒ 同等退化下真实素材只会更差。
⇒ 这条曲线是**上界**: 真实准确率 <= 曲线。上界不是点估计, 但它非空 ——
  曲线塌到 0.4 的那一档, 真实素材在那一档也不可能可用。

## 预注册判据(测量前冻结)
· 语料: 中英各 6 条短文本(该能力被登记为「语言相关」, 所以必须分语言报, 不许合成一个数)
· 退化轴四条, 各自单独扫(不做交叉, 交叉会把因果混掉):
    JPEG 质量 {95,75,50,30,15} · 高斯模糊 σ {0,0.8,1.6,2.4} ·
    对比度 {1.0,0.6,0.35,0.2} · 缩放 {1.0,0.6,0.4,0.25}
· 指标: 1 − CER(字符错误率, Levenshtein/参考长度), 逐条算再取中位数 —— **报分布不报单个均值**
· 非退化闸: 每条轴上准确率必须**真的随退化下降**(首尾差 >= 0.15),
  否则说明这条轴没有分辨力, 记 NO_RESOLUTION 而不是「稳健」
★ 本探针**不产出**「真实素材的 OCR 准确率」。它只产出上界与真实素材在轴上的位置。
"""
import json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

EN = ["HEARING AID BATTERY", "RECHARGEABLE MODEL 2026", "TRY BEFORE YOU BUY",
      "BLUETOOTH STREAMING", "30 DAY RETURN", "AUDIOLOGIST FITTED"]
ZH = ["助听器电池", "充电款二零二六", "先试听再决定", "蓝牙直连", "三十天退换", "验配师调试"]
# ★ 2026-09-04 第一次跑出来**四条轴全 NO_RESOLUTION**, 且中文全 0.00。
#   查明是**仪器坏了**, 不是「OCR 稳健」: ① 退化档对 44px 干净黑字太轻, 压根没咬到;
#   ② PingFang 加载失败回退 Helvetica ⇒ 中文渲成豆腐块, 那条曲线量的是我的渲染器不是 OCR。
#   ⇒ 档位拉到真会崩的范围, 并加**渲染器自检**(无退化时读不回原文就直接红)。
#   这次修改发生在**取得任何有效读数之前**(第一次跑的读数全部作废), 故属于允许的修订。
AXES = {"jpeg_quality": [95, 60, 30, 12, 5, 2], "blur_sigma": [0.0, 1.5, 3.0, 4.5, 6.0],
        "contrast": [1.0, 0.5, 0.25, 0.12, 0.06], "scale": [1.0, 0.5, 0.3, 0.2, 0.12]}
DROP_GATE = 0.15
FONT_SIZE = 30              # 由 44 降到 30: 更接近屏幕上的真实字号, 也让缩放轴真的咬得到


def _cer(ref: str, hyp: str) -> float:
    """字符错误率。用 difflib 的编辑距离等价物, 不引第三方。"""
    import difflib
    if not ref:
        return 0.0 if not hyp else 1.0
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return max(0.0, min(1.0, 1.0 - matched / len(ref)))


_CJK_FONTS = ("/System/Library/Fonts/STHeiti Medium.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc",
              "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
_LATIN_FONTS = ("/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _font(lang):
    from PIL import ImageFont
    for cand in (_CJK_FONTS if lang == "zh" else _LATIN_FONTS + _CJK_FONTS):
        try:
            return ImageFont.truetype(cand, FONT_SIZE)
        except Exception:
            continue
    return None


def _render(text, lang="en", size=(700, 110)):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", size, (255, 255, 255))
    f = _font(lang)
    ImageDraw.Draw(im).text((20, 35), text, fill=(0, 0, 0),
                            font=f or ImageFont.load_default())
    return im


def _witness(path: str) -> dict:
    """物理见证: 证明**退化真的施加了**。
    ★ 没有它, 「这条轴没分辨力」在「仪器坏了」和「OCR 真稳健」之间是分不开的 ——
      而本次第一版就是仪器坏了(中文渲成豆腐块), 靠猜会得到相反的结论。"""
    try:
        from PIL import Image
        import numpy as np
        with Image.open(path) as im:
            a = np.asarray(im.convert("L"), dtype=float)
            return {"px_min": int(a.min()), "px_max": int(a.max()),
                    "rms_contrast": round(float(a.std()), 2),
                    "size_px": list(im.size), "bytes": os.path.getsize(path)}
    except Exception as e:                                       # noqa: BLE001
        return {"error": f"{type(e).__name__}"}


def _degrade(im, axis, level, tmp):
    from PIL import Image, ImageEnhance, ImageFilter
    out = im
    if axis == "blur_sigma" and level > 0:
        out = out.filter(ImageFilter.GaussianBlur(level))
    if axis == "contrast" and level < 1.0:
        out = ImageEnhance.Contrast(out).enhance(level)
    if axis == "scale" and level < 1.0:
        w, h = out.size
        out = out.resize((max(8, int(w * level)), max(8, int(h * level))), Image.LANCZOS)
    p = tmp + (".jpg" if axis == "jpeg_quality" else ".png")
    if axis == "jpeg_quality":
        out.save(p, "JPEG", quality=int(level))
    else:
        out.save(p, "PNG")
    return p


def main():
    try:
        from PIL import Image                                    # noqa: F401
        import cce_image_ingest as II
    except Exception as e:                                       # noqa: BLE001
        print(f"★ 缺依赖({e}) —— 不出结论。"); return 2

    import tempfile
    print("预注册: 受控退化下的 OCR **上界曲线**。真实素材无逐字标注 ⇒ 真实准确率测不了。")
    print(f"语料: 英 {len(EN)} 条 / 中 {len(ZH)} 条 · 四条轴各自单独扫\n" + "-" * 74)

    result = {}
    with tempfile.TemporaryDirectory() as td:
        # ★ 渲染器自检: 无退化时读不回原文 ⇒ 是**仪器坏了**, 不是 OCR 差。直接红, 不出曲线。
        for lang, corpus in (("en", EN), ("zh", ZH)):
            _p = os.path.join(td, f"selfcheck_{lang}.png")
            _render(corpus[0], lang).save(_p)
            _got = "".join(o["value"] for o in II.visual_observation(_p)["observations"])
            if _cer(corpus[0].replace(" ", ""), _got.replace(" ", "")) > 0.2:
                print(f"★ 渲染器自检失败({lang}): 期望 {corpus[0]!r} 实得 {_got!r} —— "
                      "字体渲不出这个语种, 这条曲线量的会是**我的渲染器**不是 OCR。不出结论。")
                return 1
            print(f"  渲染器自检 {lang}: OK ({_got!r})")

        for lang, corpus in (("en", EN), ("zh", ZH)):
            result[lang] = {}
            for axis, levels in AXES.items():
                curve = []
                for lv in levels:
                    accs, witness = [], None
                    for i, txt in enumerate(corpus):
                        p = _degrade(_render(txt, lang), axis, lv,
                                     os.path.join(td, f"{lang}{axis}{i}"))
                        vo = II.visual_observation(p)
                        got = "".join(o["value"] for o in vo["observations"]
                                      if o["channel"] == "ocr_text")
                        ref = txt.replace(" ", "")
                        accs.append(1.0 - _cer(ref, got.replace(" ", "")))
                        if i == 0:
                            witness = _witness(p)
                    curve.append({"level": lv, "acc_median": round(statistics.median(accs), 3),
                                  "acc_min": round(min(accs), 3), "acc_max": round(max(accs), 3),
                                  "witness": witness})
                drop = curve[0]["acc_median"] - curve[-1]["acc_median"]
                curve_ok = drop >= DROP_GATE
                result[lang][axis] = {"curve": curve, "drop": round(drop, 3),
                                      "resolution": "OK" if curve_ok else "NO_RESOLUTION"}
                pts = " ".join(f"{c['level']}:{c['acc_median']:.2f}" for c in curve)
                print(f"  {lang} {axis:14} {pts}   降幅 {drop:+.2f} "
                      f"{'' if curve_ok else '⇒ NO_RESOLUTION(这条轴没分辨力)'}")

    print("-" * 74)
    for lang in result:
        clean = result[lang]["jpeg_quality"]["curve"][0]["acc_median"]
        print(f"  {lang}: 无退化上界 {clean:.3f}")
    print("★ 这是**上界**: 合成图无花字/描边/遮挡/渐变背景, 同等退化下真实素材只会更差。")
    print("★ 本探针**不产出**「真实素材的 OCR 准确率」—— 那需要带逐字标注的真实素材。")

    out = {"block": "OCR_QUALITY_UPPER_BOUND_GEN1", "measured_at": "2026-09-04",
           "★claim": "上界, 非点估计: 真实准确率 <= 本曲线",
           "★why_upper_bound": ("真实素材无逐字标注(自带 .json 是元数据不是标注); "
                                "合成渲染无花字/描边/遮挡/渐变背景 ⇒ 同等退化下真实只会更差"),
           "axes": AXES, "corpus": {"en": len(EN), "zh": len(ZH)}, "by_language": result,
           "★still_untested": "真实素材上的 OCR/ASR 准确率仍**未测** —— 需带逐字标注的真实素材"}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_curve.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
