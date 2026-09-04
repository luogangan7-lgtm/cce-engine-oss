#!/usr/bin/env python3
"""OCR 抽取质量: 有**上界曲线**了, 但真实准确率仍未测 —— 这两件事不许混。

## 它答了什么
受控退化下的字符准确率曲线(中英分开报, 因为该能力被登记为「语言相关」)。
合成图无花字/描边/遮挡/渐变背景 ⇒ 同等退化下真实素材只会更差 ⇒ **曲线是上界**。

## 它没答什么
**真实素材的 OCR 准确率**。素材自带的 .json 是元数据(title_copy/author/comments),
不是图上文字的逐字标注。拿文案当标注 = 伪造评测。⇒ 这一项仍记 BLOCKED(需带标注素材)。

## ★ 为什么每档都要带物理见证
第一版跑出「四条轴全无分辨力」, 差点被读成「OCR 很稳健」。实际是**仪器坏了**:
中文用 PingFang 加载失败回退 Helvetica, 渲成豆腐块, 那条曲线量的是渲染器不是 OCR。
⇒ 「这条轴没分辨力」在「仪器坏了」和「真稳健」之间必须可分, 靠的就是见证。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "tests/data/phase2/ocr_quality_curve.json"),
                   encoding="utf-8"))

assert D["★claim"].startswith("上界"), "★ 不许把上界说成点估计"
assert "未测" in D["★still_untested"], "★ 真实准确率仍未测这件事要留在产物里"
assert set(D["by_language"]) == {"en", "zh"}, "★ 能力登记为语言相关 ⇒ 必须分语言报"

resolving = []
for lang, axes in D["by_language"].items():
    for ax, r in axes.items():
        # 每档都要有物理见证, 否则「无分辨力」不可解释
        for pt in r["curve"]:
            w = pt.get("witness") or {}
            assert "rms_contrast" in w and "bytes" in w, \
                f"★ {lang}/{ax} 档 {pt['level']} 缺物理见证 —— 无分辨力就无法与「仪器坏了」区分"
        first, last = r["curve"][0]["witness"], r["curve"][-1]["witness"]
        # 退化必须真的施加了: 见证在首尾之间必须变化
        changed = (abs(first["rms_contrast"] - last["rms_contrast"]) > 1.0
                   or abs(first["bytes"] - last["bytes"]) > 200
                   or first["size_px"] != last["size_px"])
        assert changed, f"★ {lang}/{ax}: 见证首尾无变化 ⇒ 退化根本没施加, 这条曲线是空的"
        if r["resolution"] == "OK":
            resolving.append(f"{lang}/{ax}")

assert resolving, "★ 四条轴全无分辨力 ⇒ 设计失败, 不是「OCR 稳健」"
# 渲染器自检: 无退化时中英都必须接近满分, 否则量的是渲染器
for lang in ("en", "zh"):
    clean = D["by_language"][lang]["jpeg_quality"]["curve"][0]["acc_median"]
    assert clean >= 0.8, f"★ {lang} 无退化时只有 {clean} —— 先修渲染器再谈 OCR"

# 能力注册表: 上界有了不等于抽取质量测了
CAPS = {c["id"]: c for c in json.load(
    open(os.path.join(ROOT, "config/cce_capability_registry_v1.json"), encoding="utf-8")
)["capabilities"]}
_m = " ".join(CAPS["standalone_image_ingest"]["missing"])
assert "抽取质量" in _m, "★ 有了上界曲线**不等于**抽取质量已测, 不许把它从 missing 划掉"

print(f"test_cce_ocr_quality_curve: OK (中英分开报 | {len(resolving)} 条轴有分辨力: "
      f"{', '.join(resolving)} | 每档带物理见证 ⇒ 「无分辨力」可与「仪器坏了」区分"
      "\n  ★ 这是**上界**不是准确率; 真实素材的 OCR 准确率仍未测, 仍在 missing)")
