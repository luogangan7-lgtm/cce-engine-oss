#!/usr/bin/env python3
"""OCR 版本漂移: 09-04 的旧数是 rapidocr 1.2.3 读数(已在 1.2.3 上逐图复现), 锁定版 1.4.4 重测后旧数保留并标注取代。"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, "tests/data/phase2", p), encoding="utf-8"))
D, T = J("ocr_version_drift.json"), J("transfer_across_conditions.json")
ZH, EN = J("ocr_accuracy_real_zh.json"), J("ocr_quality_en.json")

# ① 两臂版本对, 归因要靠复现不靠猜
assert all(D["gate"].values()), f"★ 漂移重测仪器闸不过: {D['gate']}"
assert D["arms"]["locked_1.4.4"]["rapidocr_onnxruntime"] == "1.4.4"
assert D["arms"]["old_1.2.3"]["rapidocr_onnxruntime"] == "1.2.3"
a = D["attribution"]
assert a["verdict"] == ("VERSION_ATTRIBUTED" if a["zh_old_reproduced_on_1.2.3"] and a["en_old_reproduced_on_1.2.3"]
                        else "NOT_REPRODUCED_SOURCE_UNKNOWN")

# ② 旧数不删, 标「已被重测取代」; 旧文件里的数仍等于 1.2.3 读数
for d in (ZH, EN):
    assert "旧版 1.2.3 读数·已被重测取代" in d["★superseded"]
assert D["zh_real_n6"]["median"]["old_1.2.3_0904"] == ZH["acc_median"]
assert D["en_textocr"]["old_1.2.3_0904"]["word_f1_order_insensitive"] == EN["word_f1_order_insensitive"]

# ③ 倍数由产物现算, 不手抄
r = D["language_density_ratio"]
assert r["locked_1.4.4"] == round(r["zh_real_cover_locked"] / r["en_dense_scene_locked"], 2)
n = T["remeasured_on_locked_rapidocr_1.4.4"]["language(OCR)"]
assert n["ratio"] == r["locked_1.4.4"] and n["old_ratio_1.2.3"] == T["measured_transfer_failures"]["language(OCR)"]["ratio"]
assert "已被重测取代" in T["measured_transfer_failures"]["language(OCR)"]["★version"]
assert n["ratio"] > 2.0, "★ 锁定版上倍数 <=2 ⇒「条件转移不成立」要重写, 不许沿用旧结论"

print(f"test_cce_ocr_version_drift: OK ({a['verdict']} | 中文 n=6 中位 {ZH['acc_median']}→{r['zh_real_cover_locked']} · "
      f"TextOCR 词级 F1 {EN['word_f1_order_insensitive']['median']}→{r['en_dense_scene_locked']} · "
      f"倍数 {r['old_1.2.3']}→{r['locked_1.4.4']} | 旧数保留并标注)")
