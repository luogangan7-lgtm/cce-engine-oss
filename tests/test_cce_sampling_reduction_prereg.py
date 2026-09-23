# -*- coding: utf-8 -*-
"""闸: K/n 减少预注册(tests/data/sampling_reduction_prereg.json) + 第一步延迟测量(results/draw_latency.json)。零调用。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
PRE = ROOT / "tests/data/sampling_reduction_prereg.json"; RES = ROOT / "results/draw_latency.json"
P = json.loads(PRE.read_text(encoding="utf-8"))
_s = importlib.util.spec_from_file_location("_lp", ROOT / "probes/draw_latency_probe.py"); lp = importlib.util.module_from_spec(_s); _s.loader.exec_module(lp)


def test_prereg_pins_current_instrument_by_recomputation():
    """预注册里写的「当前仪器」必须与代码现算一致: K 默认、KNOT_N、温度表、instrument_hash(k=3,n=5)。"""
    import cce_knot_classify as kc, cce_full_run as fr
    cur = P["★当前仪器(冻结, 由闸现算比对)"]
    assert cur["s2_n"] == kc.KNOT_N == 5 and cur["s1_temps"] == kc._S1_BASE_TEMPS
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert '"k": 5 if a.mode in {"post", "outbound_post"} else 3' in src
    taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
    assert kc.instrument_id(taxo, k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")["instrument_hash"] == cur["instrument_hash(k=3,n=5)"]


def test_prereg_forbids_single_draw_and_freezes_rule_before_data():
    c = P["★★★候选方案(先列全, 禁止事后加)"]
    for name, v in c.items():
        if name.isalpha() and isinstance(v, dict) and "s1_k" in v: assert v["s1_k"] >= 2 and v["s2_n"] >= 2, name
    assert "K=1 或 n=1" in c["★禁止"]
    rule = P["★★★第一步(零仪器变更, 先做)"]["★★★判决线(先于数据冻结)"]["启动第二步的条件(两条同时)"]
    assert any("10 s" in r for r in rule) and any("15%" in r for r in rule)
    assert P["★★★第一步(零仪器变更, 先做)"]["预算硬上限"]["MiniMax 调用"] == lp.CAP == 20
    assert "k1_gate.judge" in P["★★★第二步(只有第一步触发才做; 现在就冻结)"]["K1 判定"]["判据"]


def test_evaluator_is_a_real_gate():
    assert lp.evaluate([30.0] * 10, [30.0] * 10, P)["★任一候选触发第二步"] is False
    assert lp.evaluate([20] * 8 + [60, 90], [20] * 8 + [60, 90], P)["候选"]["C"]["触发第二步"] is True


def test_step1_result_recomputes_from_raw_and_prereg_frozen_before():
    if not RES.exists(): return
    r = json.loads(RES.read_text(encoding="utf-8"))
    assert r["★预注册 sha(测量前冻结)"] == hashlib.sha256(PRE.read_bytes()).hexdigest()[:16], "★ 预注册在测量后被改过"
    l1 = [x["sec"] for x in r["rows"] if x["stage"] == "s1"]; l2 = [x["sec"] for x in r["rows"] if x["stage"] == "s2"]
    assert l1 == r["样本"]["s1 sec"] and l2 == r["样本"]["s2 sec"] and len(l1) == len(l2) == 10 and r["★调用账"]["calls"] <= lp.CAP
    assert lp.evaluate(l1, l2, P) == r["★★★评估(按预注册规则现算)"]
    go = r["★★★评估(按预注册规则现算)"]["★任一候选触发第二步"]
    assert (r["★★★结论"].startswith("H1") if go else r["★★★结论"].startswith("H0"))
    s = json.dumps(r, ensure_ascii=False); assert "优化结果" not in s.replace("不是优化结果", "") and "apikey_" not in s and "corpus/" not in s
