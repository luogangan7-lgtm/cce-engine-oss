#!/usr/bin/env python3
"""跨内容域 OCR 可搬性: 已测, 判不了 —— 「没证伪」不许读成「可搬」。

真值在仓外(含屏幕上的创作者名), CI 上不重测, 只验: 预注册先于读数、仪器闸全过、
判定可由产物里的区间复算、仓里没有转写、注册表里的数是从产物现读的。
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
PRE = J("tests/data/phase2/ocr_cross_domain_prereg.json")
FZ = J("tests/data/phase2/ocr_cross_domain_gt_freeze.json")
R = J("tests/data/phase2/ocr_cross_domain.json")
D = PRE["criterion"]

# ① 仪器先过闸, 真值是冻结的那份, 标注者身份写明
assert all(R["instrument_gate"].values()), f"★ 仪器闸未全过却有判定: {R['instrument_gate']}"
assert R["gt_sha256"] == FZ["gt_sha256"], "★ 跑 OCR 用的真值不是冻结的那份"
assert R["annotator"] == "Claude_single_non_human" and "非人类" in PRE["annotation"]["annotator"]

# ② 仓里不许有转写
ALLOWED = {"aweme_id", "frame", "sha256", "creator", "ref_zh_chars", "hyp_zh_chars", "acc_zh",
           "acc_en", "ref_en_chars", "n_ocr_lines", "n_ocr_lines_after_watermark_filter", "flags"}
for o in R["by_filter"].values():
    for d in o["domains"].values():
        for row in d["per_frame"]:
            assert set(row) <= ALLOWED, f"★ 逐帧记录多了字段, 可能夹带转写: {set(row) - ALLOWED}"


# ③ 判定由区间复算, 不信摘要; 两种水印过滤须一致
def judge(lo, hi, dl=0.10):
    return ("TRANSFERABLE" if -dl < lo and hi < dl else
            "NOT_TRANSFERABLE" if lo > dl or hi < -dl else "INCONCLUSIVE")


assert "0.10" in D["SESOI"]
for name, o in R["by_filter"].items():
    assert all(d["n_text_frames"] == 30 and d["n_creators"] == 5 for d in o["domains"].values()), name
    vs = []
    for k, p in o["pairs"].items():
        assert p["verdict_raw"] == judge(*p["ci90"]), f"★ {name} {k}: 判定与区间不符"
        assert p["verdict"] == (p["verdict_raw"] if p["loco_all_same"] else "INCONCLUSIVE")
        vs.append(p["verdict"])
    want = ("TRANSFERS_ACROSS_TESTED_DOMAINS" if all(v == "TRANSFERABLE" for v in vs)
            else "DOES_NOT_TRANSFER" if "NOT_TRANSFERABLE" in vs else "STILL_UNDETERMINED")
    assert o["overall"] == want, f"★ {name}: overall 与逐对判定不符"
assert R["filters_agree_on_overall"], "★ 两种水印过滤给出不同结论 —— 结论取决于过滤器, 不能报"

# ④ 注册表的数从产物现读; 判不了 ⇒ 扣发不许放行
CAPS = {c["id"]: c for c in J("config/cce_capability_registry_v1.json")["capabilities"]}
v2 = R["by_filter"]["v2_anchor"]
for cid in ("standalone_image_ingest", "video_multimodal_parse_v5"):
    m = " ".join(CAPS[cid]["missing"])
    for k, d in v2["domains"].items():
        assert f"{k} {d['acc_zh_mean']:.3f}" in m, f"★ {cid}: {k} 的数与产物不符(手抄会漂移)"
    assert R["overall"] in m and "非人类" in m
if R["overall"] != "TRANSFERS_ACROSS_TESTED_DOMAINS":
    P3 = [p for p in J("config/cce_chain_conformance.json")["phases"] if p.get("phase") == "P3 Multimodal"][0]
    assert "p3.cross_domain_calibration" in P3["★condition"] and P3["status"] == "DONE_WITH_SCOPED_WITHHOLDING"

print(f"test_cce_ocr_cross_domain: OK (4 域 x30 帧 · overall {R['overall']} · "
      + " · ".join(f"{k} {d['acc_zh_mean']:.3f}" for k, d in v2["domains"].items())
      + " | 判定由区间复算 · 真值冻结 · 无转写入仓 · 扣发不放行)")
