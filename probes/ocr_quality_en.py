#!/usr/bin/env python3
"""英文 OCR 抽取质量 —— 前登记 tests/data/phase2/extraction_quality_en_prereg.json

## 为什么用 TextOCR 而不是 ICDAR
2026-09-04 调研核实: ICDAR2013/2015 的官方下载在 RRC 需要**注册**, 不满足「匿名可复现」;
HF 上的第三方转存许可证不明。⇒ 改用 **TextOCR v0.1(CC BY 4.0, 官方直链)**,
图像逐张从 OpenImages CDN 取(实测 HTTP 200), 不必下 6.6GB 整包。
★ 语料存 /Volumes/data/cce-eval-corpora, **不入仓**(仓内媒体二进制闸)。

## 两档指标, 不合并
调研核实: ICDAR 各 task 的大小写/标点策略**并不统一**, 不能拿一个 `.lower()` 当通用 scorer。
⇒ 本探针**同时**报:
  · RAW        : NFC 后逐字符比, 保留大小写与标点
  · NORMALIZED : 大写 + 去标点 + 折空白(profile 显式写在产物里)
两档都报, 不合成一个「标准 OCR 准确率」。

## 判据不是我拍的合格线
是「与公开报告值同量级 ⇒ 集成没坏」。抽取质量是特征化测量, 不是通过/不通过。
"""
import json, os, re, statistics, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
CORP = "/Volumes/data/cce-eval-corpora"
ANN = os.path.join(CORP, "TextOCR_0.1_val.json")
IMGS = os.path.join(CORP, "textocr_val_images")
N = 100


def _cer(ref: str, hyp: str) -> float:
    import difflib
    if not ref:
        return 0.0 if not hyp else 1.0
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    return max(0.0, min(1.0, 1.0 - sum(b.size for b in sm.get_matching_blocks()) / len(ref)))


def raw_form(s):        # NFC, 原样
    return unicodedata.normalize("NFC", s or "")


def norm_form(s):       # 大写 + 去标点 + 折空白
    s = unicodedata.normalize("NFC", (s or "")).upper()
    return "".join(re.sub(r"[^A-Z0-9]+", "", s))


def main():
    if not (os.path.exists(ANN) and os.path.isdir(IMGS)):
        print(f"★ 无语料({ANN}) —— 只在备好语料的机器上成立, **不出结论**。")
        return 2
    import cce_image_ingest as II
    d = json.load(open(ANN, encoding="utf-8"))
    ids = sorted(d["imgs"])[:N]
    have = [i for i in ids if os.path.exists(os.path.join(IMGS, i + ".jpg"))]
    print(f"预注册: EXTRACTION_QUALITY_EN_GEN1:OCR | TextOCR v0.1 val (CC BY 4.0)")
    print(f"取排序前 {N} 张(不挑), 本机实有 {len(have)} 张\n" + "-" * 72)

    rows, raw_a, norm_a, f1s, dontcare = [], [], [], [], 0
    for iid in have:
        anns = [d["anns"][a] for a in d["imgToAnns"][iid]]
        # TextOCR 用 "." 表示不可读/don't-care ⇒ 排除出参考, 并计数
        keep = [a for a in anns if a["utf8_string"] not in (".", "")]
        dontcare += len(anns) - len(keep)
        if not keep:
            continue
        # 阅读序: 先按 y 再按 x(粗排), 与人读图一致
        keep.sort(key=lambda a: (round(a["bbox"][1] / 20), a["bbox"][0]))
        ref_raw = " ".join(a["utf8_string"] for a in keep)
        vo = II.visual_observation(os.path.join(IMGS, iid + ".jpg"))
        hyp_raw = " ".join(o["value"] for o in vo["observations"] if o["channel"] == "ocr_text")
        ra = 1.0 - _cer(raw_form(ref_raw), raw_form(hyp_raw))
        na = 1.0 - _cer(norm_form(ref_raw), norm_form(hyp_raw))
        # ★ 顺序无关的词级 P/R/F —— 用来分辨「真的没读出来」与「读出来了但拼接顺序不同」。
        #   序列编辑距离对顺序极敏感; 只报它会把**我的拼接方式**当成 OCR 的错。
        import collections
        rw = collections.Counter(norm_form(a["utf8_string"]) for a in keep if norm_form(a["utf8_string"]))
        hw = collections.Counter(w for o in vo["observations"] if o["channel"] == "ocr_text"
                                 for w in (norm_form(x) for x in o["value"].split()) if w)
        inter = sum((rw & hw).values())
        prec = inter / max(1, sum(hw.values())); rec = inter / max(1, sum(rw.values()))
        f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
        raw_a.append(ra); norm_a.append(na); f1s.append(f1)
        rows.append((iid, len(keep), round(ra, 3), round(na, 3), round(f1, 3)))

    for iid, n_, ra, na, f1 in rows[:5]:
        print(f"  {iid}  GT词 {n_:3}  RAW {ra:.3f}  NORM {na:.3f}  词级F1 {f1:.3f}")
    print("-" * 72)
    if len(raw_a) < 30:
        print(f"★ 有效图仅 {len(raw_a)} < 30 ⇒ INSUFFICIENT"); return 1

    def summ(v):
        q = statistics.quantiles(v, n=4)
        return {"median": round(statistics.median(v), 4), "mean": round(sum(v)/len(v), 4),
                "q1": round(q[0], 4), "q3": round(q[2], 4),
                "min": round(min(v), 4), "max": round(max(v), 4)}
    R, NM, F = summ(raw_a), summ(norm_a), summ(f1s)
    varied = len(set(round(x, 3) for x in norm_a)) > 5
    print(f"RAW (保留大小写与标点): 中位 {R['median']} · 四分位 {R['q1']}/{R['q3']} · 范围 {R['min']}–{R['max']}")
    print(f"NORM(大写去标点)      : 中位 {NM['median']} · 四分位 {NM['q1']}/{NM['q3']} · 范围 {NM['min']}–{NM['max']}")
    print(f"词级 F1(**顺序无关**)   : 中位 {F['median']} · 四分位 {F['q1']}/{F['q3']} · 范围 {F['min']}–{F['max']}")
    _gap = F["median"] - NM["median"]
    print(f"★ F1 − 序列准确率 = {_gap:+.3f} ⇒ "
          + ("差距大 ⇒ 低分主要是**我的拼接顺序**造成的, 不是没读出来" if _gap > 0.15
             else "差距小 ⇒ 低分是**真的没读出来**, 不是排序假象"))
    print(f"don't-care(GT 为 '.') 已排除 {dontcare} 处")
    print(f"非退化(逐图有变异): {'过' if varied else '**不过**'}")

    out = {"block": "EXTRACTION_QUALITY_EN_GEN1:OCR", "measured_at": "2026-09-04",
           "corpus": "TextOCR v0.1 val (CC BY 4.0)", "model": "RapidOCR (与生产同一调用)",
           "n_images": len(raw_a), "dontcare_excluded": dontcare,
           "raw": R, "normalized": NM, "word_f1_order_insensitive": F,
           "degeneracy_pass": varied,
           "★why_word_f1": ("序列编辑距离对**拼接顺序**极敏感; 只报它会把我的拼接方式当成 OCR 的错。"
                            "词级 F1 顺序无关 ⇒ 两者的差距能分辨「没读出来」与「读出来但顺序不同」。"),
           "★normalization_profile": {"raw": "unicode NFC, 保留 case/标点/空白",
                                      "normalized": "NFC + 大写 + 去非字母数字 + 去空白"},
           "★why_two_profiles": ("ICDAR 各 task 的大小写/标点策略并不统一, 不能拿一个 .lower() "
                                 "当通用 scorer ⇒ 两档都报, **不合成一个「标准 OCR 准确率」**"),
           "★why_not_icdar": "ICDAR2013/2015 官方下载在 RRC 需注册, 不满足匿名可复现; HF 转存许可不明",
           "★criterion": "与公开报告值同量级 ⇒ 集成没坏; 差一倍以上 ⇒ 是我的集成有缺陷"}
    json.dump(out, open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_en.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
