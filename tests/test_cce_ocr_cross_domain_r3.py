#!/usr/bin/env python3
"""跨内容域 OCR 第三轮(3 个新域): 预注册仪器闸(含 I6)全过 ⇒ 才有判定; 判定由区间复算; 有界水印过滤只删水印块。

真值在仓外, CI 不重测, 只验: 闸与判定的一致性; 判定可由区间复算; 有界过滤器的行为(合成行, 不需真值);
仓里没有转写; 注册表的数从产物现读; 判不了 ⇒ 扣发不放行, across_domains 不动。
无本机素材时(CI(无 stackA_frames/仓外真值)): 行为不变、全部断言照跑 —— 只读仓内产物; 从 probes/ 导入的
只有纯函数 keep_v3/keep_v2(模块导入时不读任何仓外文件, meta()/ocr() 不被调用)。不可验证的是 OCR 读数本身, 那由 run 现算。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "probes"))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
PRE = J("tests/data/phase2/ocr_cross_domain_r3_prereg.json")
FZ = J("tests/data/phase2/ocr_cross_domain_r3_gt_freeze.json")
R = J("tests/data/phase2/ocr_cross_domain_r3.json")
G = R["instrument_gate"]
D = R["by_filter"]["v3_bounded"]["domains"]

# ① 真值是冻结那份; 标注者照实写; 新样本; 选域规则可复算
assert R["gt_sha256"] == FZ["gt_sha256"] and G["I3_gt_frozen"], "★ 跑 OCR 用的真值不是冻结的那份"
assert R["annotator"] == "Claude_single_non_human" and "非人类" in PRE["annotation"]["annotator"]
assert G["I5_no_seen_frame"], "★ 第三轮混进了前两轮看过的帧"
import hashlib
assert R["domains_chosen"] == PRE["domains"]["chosen"] == sorted(
    PRE["domains"]["pool"], key=lambda k: hashlib.sha256(k.encode()).hexdigest())[:3], "★ 选域不是预注册的哈希规则"

# ② I6 是预注册的前置闸(不是事后补的); 闸全过才允许有判定
assert any(s.startswith("★ I6") and "<= 0.02" in s for s in PRE["criterion"]["instrument_gate_before_any_verdict"])
assert G["I6_filter_preserves_text"] == all(v <= R["I6_max"] for v in R["I6_mean_acc_loss_vs_no_filter"].values())
gate_ok = all(G.values())
assert gate_ok == (R["overall"] != "INSTRUMENT_GATE_FAILED") and gate_ok == bool(R["pairs"]), "★ 闸与判定不一致"


# ③ 判定由区间复算; 留一创作者不稳则降级; overall 按预注册规则
def judge(lo, hi, dl=0.10):
    return ("TRANSFERABLE" if -dl < lo and hi < dl else
            "NOT_TRANSFERABLE" if lo > dl or hi < -dl else "INCONCLUSIVE")


for k, p in R["pairs"].items():
    assert p["verdict_raw"] == judge(*p["ci90"]), k
    assert p["loco_all_same"] == all(x["verdict"] == p["verdict_raw"] for x in p["loco"]), k
    assert p["verdict"] == (p["verdict_raw"] if p["loco_all_same"] else "INCONCLUSIVE"), k
vs = [p["verdict"] for p in R["pairs"].values()]
want = ("DOES_NOT_TRANSFER" if "NOT_TRANSFERABLE" in vs else
        "STILL_UNDETERMINED" if any(d["status"] == "INSUFFICIENT" for d in D.values()) or set(vs) != {"TRANSFERABLE"}
        else "TRANSFERS_ACROSS_TESTED_DOMAINS")
assert R["overall"] == want == R["H2_new_nongame_domains"], f"★ overall {R['overall']} ≠ 复算 {want}"
assert R["H3_game_vs_others"] == "NOT_TESTABLE_THIS_ROUND"
for d in D.values():
    assert d["status"] == ("OK" if d["n_text_frames"] >= 85 else "OK_REDUCED" if d["n_text_frames"] >= 60 else "INSUFFICIENT")

# ④ 有界水印过滤(合成行): t=0 左上水印块下面的标题必须保留; 同框并进来的正文保留; 块本身删干净
import ocr_cross_domain_r3 as R3
rows = [("抖音", [49, 18, 55, 29]), ("抖音号：demo0000001", [10, 56, 159, 18]), ("Q示例小厨房", [10, 83, 106, 20]),
        ("示例标题", [116, 120, 205, 52]), ("拟音号：12345678901同框正文", [8, 300, 300, 22]),
        ("正文第二行", [8, 400, 200, 22])]
kept = R3.keep_v3(rows, "示例小厨房")
assert kept == ["示例标题", "同框正文", "正文第二行"], kept
# 反向: 第二轮 v2 在同一组行上吃掉标题 —— 测的东西能观察到失败
import ocr_cross_domain as R1
assert "示例标题" not in R1.keep_v2(rows, "示例小厨房")
# OCR 漏了昵称行时, 锚正下方紧挨着的大字标题不得被当成昵称删(字高 > 1.5x 锚高)
assert R3.keep_v3([("抖音号：demo_user_0002", [10, 56, 159, 18]), ("示例大字标题", [10, 80, 300, 40])],
                  "示例昵称") == ["示例大字标题"]
# 无锚: 只删带 Q 的昵称行, 正文里出现的昵称不删
assert R3.keep_v3([("Q示例测评号", [0, 0, 50, 18]), ("示例测评号", [0, 400, 80, 30])], "示例测评号") == ["示例测评号"]

# ⑤ 仓里不许有转写
ALLOWED = {"aweme_id", "frame", "sha256", "video", "creator", "ref_zh_chars", "hyp_zh_chars", "acc_zh",
           "acc_en", "ref_en_chars", "n_ocr_lines", "n_ocr_lines_after_watermark_filter", "flags"}
for o in R["by_filter"].values():
    for d in o["domains"].values():
        for row in d["per_frame"]:
            assert set(row) <= ALLOWED, f"★ 逐帧记录多了字段: {set(row) - ALLOWED}"

# ⑥ 注册表的数从产物现读; 判不了 ⇒ 扣发不放行, across_domains 不因 OCR 改
CAPS = {c["id"]: c for c in J("config/cce_capability_registry_v1.json")["capabilities"]}
for cid in ("standalone_image_ingest", "video_multimodal_parse_v5"):
    m = CAPS[cid]["missing"][0]
    assert "第三轮" in m and R["overall"] in m and "非人类" in m and "across_domains" in m
    for k, d in D.items():
        assert f"{k} r3 {d['acc_zh_mean']:.3f}" in m, f"★ {cid}: {k} 的数与产物不符"
    for k, x in R["I6_mean_acc_loss_vs_no_filter"].items():
        assert f"{k} {x:.3f}" in m
    for k, p in R["pairs"].items():
        assert f"{k} {p['verdict']} [{p['ci90'][0]:.3f}, {p['ci90'][1]:.3f}]" in m
P3 = [p for p in J("config/cce_chain_conformance.json")["phases"] if p.get("phase") == "P3 Multimodal"][0]
assert "第三轮" in P3["★condition"] and R["overall"] in P3["★condition"]
if R["overall"] != "TRANSFERS_ACROSS_TESTED_DOMAINS":
    assert P3["status"] == "DONE_WITH_SCOPED_WITHHOLDING", "★ 判不了不许改 P3 状态"
assert PRE["writeback_rule"]["across_domains"].count("不因本探针改动") == 1

print(f"test_cce_ocr_cross_domain_r3: OK (闸全过 I6 max {max(R['I6_mean_acc_loss_vs_no_filter'].values()):.4f} | "
      + " · ".join(f"{k} {d['acc_zh_mean']:.3f}(n={d['n_text_frames']})" for k, d in D.items())
      + f" | overall {R['overall']} | " + " · ".join(f"{k} {p['verdict']}" for k, p in R["pairs"].items()) + ")")
