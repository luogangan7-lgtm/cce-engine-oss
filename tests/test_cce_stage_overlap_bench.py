# -*- coding: utf-8 -*-
"""闸: results/stage_overlap_bench.json(串行 vs 重叠 A/B, n=1)。零调用。节省数由 arms 现算; 归因不得超过理论上限; 两臂 k_ok 达标; 不含语料原文。"""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]; R = json.loads((ROOT / "results/stage_overlap_bench.json").read_text(encoding="utf-8"))


def test_savings_recomputed_and_attribution_capped():
    a, b = R["arms"]; assert a["arm"] == "serial" and b["arm"] == "overlap" and a["rc"] == b["rc"] == 0 and a["complete"] and b["complete"]
    sv = R["★节省"]; cap = min(a["stage_sec"]["reader_baseline"], a["stage_sec"]["s1_readout"])
    assert sv["wall_sec 串行→重叠"] == [a["wall_sec"], b["wall_sec"]] and sv["节省秒"] == round(a["wall_sec"] - b["wall_sec"], 1)
    assert sv["理论上限(=min(reader, s1) 串行秒)"] == cap and sv["★可归因于重叠的节省(≤理论上限)"] == round(min(sv["节省秒"], cap), 1)
    assert sv["★可归因于重叠的节省(≤理论上限)"] <= cap and b["stage_sec"]["reader_baseline"] is not None


def test_no_rate_limit_regression_and_k_ok():
    for arm in R["arms"]:
        assert arm["reader"]["k_ok"] == arm["reader"]["k_requested"] == 3 and arm["s1"]["k_ok"] == 3, arm["arm"]
    assert R["★限流"]["overlap"]["reader INFRA_FAILED"] <= R["★限流"]["serial"]["reader INFRA_FAILED"] + 1   # n=1: 允许 1 次波动, 更多就是撞限流


def test_n1_honesty_and_no_corpus_text():
    s = json.dumps(R, ensure_ascii=False); assert "n=1" in R["★性质"] and "不报置信区间" in R["★性质"]
    assert "hearing" not in s.lower() or "reddit" not in s.lower()   # 探针文本是合成句; 产物不引用语料文件
    assert "corpus/" not in s and "apikey_" not in s
