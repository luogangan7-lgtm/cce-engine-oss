#!/usr/bin/env python3
"""OCR 版本漂移重测 —— 预注册 tests/data/phase2/ocr_cross_domain_r2_prereg.json 的 drift_remeasure 段。

2026-09-29 锁版本时 rapidocr 1.2.3 → 1.4.4; 09-04 的中文 n=6 / TextOCR n=98 / 语言倍数 2.84 是旧版读数。
同一批图、同一真值、同一指标, 分别在锁定版(.venv, 1.4.4)与旧版(/opt/homebrew python3.14, 1.2.3)上跑:
  · 旧版臂逐图复现 09-04 旧数 ⇒ 漂移归因于版本
  · 锁定版臂 = 新的现行读数

用法: ocr_version_drift.py run          → tests/data/phase2/ocr_version_drift.json
      ocr_version_drift.py emit <out>    (内部: 当前解释器测一遍, 写 <out>)
"""
import json, os, statistics, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
OUT = os.path.join(ROOT, "tests/data/phase2/ocr_version_drift.json")
P2 = os.path.join(ROOT, "tests/data/phase2")
ARMS = {"locked_1.4.4": "/Volumes/data/cce-engine/.venv/bin/python",
        "old_1.2.3": "/opt/homebrew/bin/python3.14"}
TOL = 0.001


def emit(path):
    import importlib.metadata as md
    import ocr_accuracy_real_zh as ZH, ocr_quality_en as EN
    zh, en = ZH.run(), EN.main(write=False)
    json.dump({"versions": {p: md.version(p) for p in ("rapidocr_onnxruntime", "onnxruntime")},
               "zh": zh, "en": en if isinstance(en, dict) else {"error_rc": en}},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)


def run():
    old_zh = json.load(open(f"{P2}/ocr_accuracy_real_zh.json", encoding="utf-8"))
    old_en = json.load(open(f"{P2}/ocr_quality_en.json", encoding="utf-8"))
    old_tr = json.load(open(f"{P2}/transfer_across_conditions.json", encoding="utf-8"))
    arms = {}
    with tempfile.TemporaryDirectory() as td:
        for name, py in ARMS.items():
            p = os.path.join(td, f"{name}.json")
            subprocess.run([py, __file__, "emit", p], cwd=ROOT, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not os.path.exists(p):
                print(f"★ {name} 臂没出产物 —— 不出结论"); return 2
            arms[name] = json.load(open(p, encoding="utf-8"))
    gate = {"locked_version_is_1.4.4": arms["locked_1.4.4"]["versions"]["rapidocr_onnxruntime"] == "1.4.4",
            "old_version_is_1.2.3": arms["old_1.2.3"]["versions"]["rapidocr_onnxruntime"] == "1.2.3",
            "zh_material_present": all(a["zh"] for a in arms.values()),
            "en_corpus_present": all("error_rc" not in a["en"] for a in arms.values())}
    if not all(gate.values()):
        print(json.dumps(gate)); return 2
    acc = lambda z: {r["file"]: r["acc"] for r in z["per_image"]}

    def zh_cmp(z):
        o, n = acc(old_zh), acc(z)
        return {f: {"old_0904": o[f], "now": n.get(f)} for f in o}
    old_arm, new_arm = arms["old_1.2.3"], arms["locked_1.4.4"]
    zh_rep = all((v["old_0904"] is None and v["now"] is None) or
                 (v["old_0904"] is not None and v["now"] is not None and abs(v["old_0904"] - v["now"]) <= TOL)
                 for v in zh_cmp(old_arm["zh"]).values())
    en_rep = all(abs(old_arm["en"][k]["median"] - old_en[k]["median"]) <= TOL and
                 abs(old_arm["en"][k]["mean"] - old_en[k]["mean"]) <= TOL
                 for k in ("raw", "normalized", "word_f1_order_insensitive")) \
        and old_arm["en"]["n_images"] == old_en["n_images"]
    pick = lambda e: {k: e[k] for k in ("raw", "normalized", "word_f1_order_insensitive")}
    zh_new, en_new = new_arm["zh"]["acc_median"], new_arm["en"]["word_f1_order_insensitive"]["median"]
    f1_old = {r["id"]: r["f1"] for r in old_arm["en"]["per_image"]}
    f1_new = {r["id"]: r["f1"] for r in new_arm["en"]["per_image"]}
    both = sorted(set(f1_old) & set(f1_new))
    res = {
        "block": "OCR_VERSION_DRIFT_REMEASURE", "measured_at": "2026-10-01",
        "prereg": "tests/data/phase2/ocr_cross_domain_r2_prereg.json#drift_remeasure",
        "arms": {k: v["versions"] for k, v in arms.items()}, "gate": gate,
        "attribution": {"rule": f"1.2.3 臂逐图复现 09-04 旧数(|差| <= {TOL}) ⇒ 漂移归因于版本",
                        "zh_old_reproduced_on_1.2.3": zh_rep, "en_old_reproduced_on_1.2.3": en_rep,
                        "verdict": "VERSION_ATTRIBUTED" if zh_rep and en_rep else "NOT_REPRODUCED_SOURCE_UNKNOWN"},
        "zh_real_n6": {"per_image_old_vs_locked": zh_cmp(new_arm["zh"]),
                       "per_image_old_vs_1.2.3_rerun": zh_cmp(old_arm["zh"]),
                       "median": {"old_1.2.3_0904": old_zh["acc_median"], "locked_1.4.4": zh_new},
                       "range_locked": [new_arm["zh"]["acc_min"], new_arm["zh"]["acc_max"]],
                       "hallucinated_on_blank_locked": new_arm["zh"]["hallucinated_on_blank"]},
        "en_textocr": {"n_images": {"old": old_en["n_images"], "locked": new_arm["en"]["n_images"]},
                       "old_1.2.3_0904": pick(old_en), "locked_1.4.4": pick(new_arm["en"]),
                       "per_image_f1": {"n_paired": len(both),
                                        "n_changed": sum(abs(f1_old[i] - f1_new[i]) > TOL for i in both),
                                        "mean_diff_new_minus_old": round(statistics.mean(
                                            f1_new[i] - f1_old[i] for i in both), 4) if both else None}},
        "language_density_ratio": {
            "formula": "中文真实图 1−CER 中位 / 英文 TextOCR 顺序无关词级 F1 中位(同 transfer_across_conditions)",
            "old_1.2.3": old_tr["measured_transfer_failures"]["language(OCR)"]["ratio"],
            "locked_1.4.4": round(zh_new / en_new, 2) if en_new else None,
            "zh_real_cover_locked": zh_new, "en_dense_scene_locked": en_new},
        "★n_is_small": "中文仍是 n=6(5 有字 + 1 零文字对照), 区间宽, 不得当稳定基线。"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("arms", "gate", "attribution", "language_density_ratio")},
                     ensure_ascii=False, indent=1))
    print(json.dumps({"zh_median": res["zh_real_n6"]["median"], "en": res["en_textocr"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["emit"]:
        emit(sys.argv[2]); rc = 0
    else:
        rc = run()
    sys.stdout.flush()
    os._exit(rc)  # onnxruntime 退出析构 abort, 产物已落盘
