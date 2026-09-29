# -*- coding: utf-8 -*-
"""闸: s0 植入信号效度 (probes/s0_planted_validity.py → results/s0_planted_validity.json)。零调用。
预注册判决只能从 raw 现算得出; 产物只含指针与读数, 不含原文。"""
import hashlib, importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "results/s0_planted_validity.json"; PRE = ROOT / "tests/data/s0_planted_validity_prereg.json"
_s = importlib.util.spec_from_file_location("_pv", ROOT / "probes/s0_planted_validity.py"); pv = importlib.util.module_from_spec(_s); _s.loader.exec_module(pv)


def _res(): return json.loads(OUT.read_text(encoding="utf-8"))


def test_verdict_rule_is_the_prereg_rule():
    assert pv.verdict(0.80, 0.10) == "RESPONSIVE" and pv.verdict(0.80, 0.11) == "WEAK"
    assert pv.verdict(0.79, 0.0) == "WEAK" and pv.verdict(0.49, 0.0) == "UNRESPONSIVE"


def test_verdicts_recompute_from_raw():
    res = _res()
    assert not res["dry_run"] and res["requests"] == len(res["raw"]) <= json.loads(PRE.read_text(encoding="utf-8"))["budget"]["hard_cap"]
    assert res["prereg_sha256"] == hashlib.sha256(PRE.read_bytes()).hexdigest(), "预注册在测量后被改过"
    neu, per = pv.analyse(res["raw"])
    assert neu == res["neutral_change"]
    for k, v in per.items():
        for kk in ("recovery", "net_off_target", "verdict"):
            assert v[kk] == res["per_facet"][k][kk], (k, kk)


def test_recorded_outcome_is_honest():
    """2026-09-29 结果: 预测 P1/P3 未全中 —— 写死, 防止日后被悄悄改写成「全部 RESPONSIVE」。"""
    p = _res()["★predictions"]
    assert p["P1"] == {"进程位置": "WEAK", "触发事件": "WEAK", "资源状态": "RESPONSIVE"}
    assert p["P2_情绪余温"] == "WEAK" and p["P3_neutral_change<=0.05"] is False


def test_no_text_in_artifact():
    res = _res()
    for r in res["raw"]:
        assert set(r) == {"kind", "ptr", "facet", "value", "phrasing", "read", "err"}
        assert r["read"] is None or all(isinstance(v, str) and len(v) <= 12 for v in r["read"].values())


def test_emotion_v2_exploratory_recomputes_and_stays_exploratory():
    r = json.loads((ROOT / "results/s0_planted_validity_emotion_v2.json").read_text(encoding="utf-8"))
    assert r["variant"] == "emotion_v2" and not r["dry_run"] and r["per_facet"] == pv.analyse_v2(r["raw"])
    assert isinstance(r["★predictions"], str)          # 探索臂: 不出预注册判决


def test_residue_referent_verdicts_recompute_from_raw():
    _r = importlib.util.spec_from_file_location("_rr", ROOT / "probes/s0_residue_referent.py"); rr = importlib.util.module_from_spec(_r); _r.loader.exec_module(rr)
    r = json.loads((ROOT / "results/s0_residue_referent.json").read_text(encoding="utf-8"))
    assert not r["dry_run"] and r["requests"] == len(r["raw"]) <= rr.CAP and not r["errors"]
    assert r["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/s0_residue_referent_prereg.json").read_bytes()).hexdigest()
    assert r["emotion_v2_sha"] == hashlib.sha256(pv.EMOTION_V2.encode()).hexdigest()[:16]
    for arm in ("v1", "v2"):
        assert rr.score([x for x in r["raw"] if x["arm"] == arm]) == r["arms"][arm], arm
    assert r["arms"]["v1"]["verdict"] == r["arms"]["v2"]["verdict"] == "FAIL"
    assert rr.score([{"kind": "plant", "cls": c, "read": {"情绪余温": "未知"}} for c in rr.PLANTS])["verdict"] == "FAIL"   # 恒「未知」过不了召回


def test_residue_profile_recomputes_and_stays_distribution_level():
    """分布口径(全占比): 判决只由概率位移现算; paired 臂 DISCRIMINATES、v1 LEAKS; 常数读者判不过。"""
    _p = importlib.util.spec_from_file_location("_rp", ROOT / "probes/s0_residue_profile.py"); rp = importlib.util.module_from_spec(_p); _p.loader.exec_module(rp)
    r = json.loads((ROOT / "results/s0_residue_profile.json").read_text(encoding="utf-8"))
    assert not r["dry_run"] and r["requests"] == len(r["raw"]) <= rp.CAP and not r["errors"]
    assert r["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/s0_residue_profile_prereg.json").read_bytes()).hexdigest()
    assert all(isinstance(x["probs"], dict) and x["probs"] for x in r["raw"])          # 存的是完整分布, 不是只有 top-1
    for arm in ("v1", "paired"):
        assert rp.score([x for x in r["raw"] if x["arm"] == arm]) == r["arms"][arm], arm
    assert (r["arms"]["v1"]["verdict"], r["arms"]["paired"]["verdict"]) == ("LEAKS", "DISCRIMINATES")
    flat = [{"kind": x["kind"], "ptr": x["ptr"], "cls": x["cls"], "probs": {"未知": 1.0}} for x in r["raw"] if x["arm"] == "v1"]
    assert rp.score(flat)["verdict"] == "LEAKS"
