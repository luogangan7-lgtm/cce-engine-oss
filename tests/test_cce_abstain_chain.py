#!/usr/bin/env python3
"""弃权是合法测量结果, 不是管线故障(2026-09-28 诊断 #15 / #11)。

2026-08-19 弃权重设计让 s1 可以合法弃权(k_ok = 有效 draw 数), 但 run_knot_classify 里 2026-08-09 的
覆盖闸没跟着改, 仍是 `k_ok < k ⇒ raise` ⇒ 任何一次弃权都把整条链判 FAIL, s1 的 abstain /
insufficient_replicates 分支永远走不到; s3 不看弃权直接索引 layers["emotion_vec"]。
本闸经**真实的 run_knot_classify**(只把子进程换成写出产物的假进程)驱动 reader_baseline / s1 / s3, 不桩函数本身。
"""
import copy
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as F  # noqa: E402
import cce_knot_classify as KC  # noqa: E402

BASE = json.loads((ROOT / "archive/33842088048/cce-subject-item-7-33842088048__s1_readout.json").read_text(encoding="utf-8"))
assert BASE["stage1"]["measurement_status"] == "qualified" and BASE["stage1"]["k_valid"] == 3
TAXO = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))


def llm_abstain(k=3):
    s1 = {"k_requested": k, "k_attempted": k, "k_valid": 0, "k_abstained": k, "k_ok": 0,
          "measurement_status": "abstain", "n_abstain": k, "abstained": True, "within_js": None,
          "abstain_reason": "全部 draw 声明无可推断主体", "layers": {}, "tops": {}, "draws": []}
    return {"stage1": s1, "stage2": KC.stage2("x", s1, TAXO)}          # s1 弃权 ⇒ s2 零调用


def structural_abstain(k=3):
    s1 = {"k_requested": k, "k_attempted": 0, "k_valid": 0, "k_abstained": k, "k_ok": 0, "n_abstain": k,
          "measurement_status": "abstain", "abstained": True, "abstain_reason": "全文为引用",
          "draws": []}                                                  # 与 cce_knot_classify.stage1 结构闸分支同形: 无 within_js/tops/layers
    return {"stage1": s1, "stage2": KC.stage2("x", s1, TAXO)}


def one_of_three_abstained():
    d = copy.deepcopy(BASE)
    d["stage1"].update({"k_valid": 2, "k_abstained": 1, "k_ok": 2})
    return d


def one_valid():
    d = copy.deepcopy(BASE)
    d["stage1"].update({"k_valid": 1, "k_abstained": 2, "k_ok": 1, "within_js": None,
                        "measurement_status": "insufficient_replicates"})
    return d


def pipeline_loss():
    d = copy.deepcopy(BASE)
    d["stage1"].update({"k_attempted": 2, "k_valid": 2, "k_ok": 2})   # 一个 draw 三次尝试全失败 = 真丢了
    return d


def drive(product):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "text.txt").write_text("draft", encoding="utf-8")
    (tmp / "reader.txt").write_text("reader body", encoding="utf-8")

    def fake_run(cmd, **kw):
        Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps(product, ensure_ascii=False), encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    F.subprocess.run, keep = fake_run, F.subprocess.run
    F.MANIFEST.clear()
    ctx = {"text_file": str(tmp / "text.txt"), "reader_file": str(tmp / "reader.txt"),
           "context": "c", "k": 3, "outdir": str(tmp), "_overlap": False}
    try:
        for fn in (F.reader_baseline, F.s1, F.s3):
            try:
                fn(ctx)
            except Exception:
                pass
    finally:
        F.subprocess.run = keep
    return {k: dict(v) for k, v in F.MANIFEST.items()}


m = drive(BASE)
assert all(m[s]["status"] == "OK" for s in ("reader_baseline", "s1_readout", "s3_emotion_policy")), m
assert m["s1_readout"]["measurement_status"] == "qualified" and m["s3_emotion_policy"]["emotion_distribution"]

for name, mk, s1_status in (("llm_abstain", llm_abstain, "abstain"), ("structural_abstain", structural_abstain, "abstain"),
                            ("one_valid", one_valid, "insufficient_replicates")):
    m = drive(mk())
    assert all(m[s]["status"] == "OK" for s in ("reader_baseline", "s1_readout", "s3_emotion_policy")), (name, m)
    assert m["s1_readout"]["measurement_status"] == s1_status, (name, m["s1_readout"])
    assert m["reader_baseline"]["measurement_status"] == s1_status, (name, m["reader_baseline"])
    assert m["s3_emotion_policy"]["policy"] == "withheld" and m["s3_emotion_policy"]["emotion_distribution"] is None, (name, m)

m = drive(one_of_three_abstained())                                   # 3 取 2 有效: 合格读数, 不是失败
assert m["s1_readout"]["status"] == "OK" and m["s1_readout"]["measurement_status"] == "qualified", m["s1_readout"]

m = drive(pipeline_loss())                                            # 真丢 draw 仍然是管线故障
assert m["s1_readout"]["status"] == "FAIL" and "管线丢失" in m["s1_readout"]["error"], m["s1_readout"]
assert m["reader_baseline"]["status"] == "FAIL"

print("test_cce_abstain_chain: OK (弃权/结构弃权/仅 1 有效 ⇒ reader·s1·s3 皆 OK 且如实标注 | 3 取 2 ⇒ qualified | 丢 draw ⇒ FAIL)")
