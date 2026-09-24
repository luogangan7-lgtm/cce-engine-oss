# -*- coding: utf-8 -*-
"""闸: 引用证书试点产物(results/citation_certificate_pilot.json)。零调用。
守: 预注册 sha 投料前冻结且未改 · 指标与判决由 rows 现算一致 · 判决规则四向真闸 · 上限未破 · 产物无原文 · 生产仍未接线(接线要 ADOPT + owner)。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_px", ROOT / "probes/citation_certificate_pilot_run.py"); px = importlib.util.module_from_spec(_s); _s.loader.exec_module(px)
PRE = json.loads(px.PRE.read_text(encoding="utf-8")); R = json.loads(px.OUT.read_text(encoding="utf-8"))
cp = px._load("probes/real_corpus_pilot_prereg.py", "_rcp_t").clopper_pearson


def test_prereg_frozen_before_and_untouched():
    assert R["★预注册 sha(投料前冻结)"] == hashlib.sha256(px.PRE.read_text(encoding="utf-8").encode()).hexdigest()[:16]
    assert R["★实际调用"] <= R["★硬上限"] == PRE["★预算硬上限"]["证书调用"] == 2 * len(R["rows"])


def test_metrics_and_verdict_recompute_from_rows():
    M, v = px.evaluate(R["rows"], PRE, cp)
    assert M == R["★★★指标"] and v == R["★★★判决(按预注册规则现算)"]
    m1 = M["M1 可判率"]; assert m1["CP95"] == [round(x, 4) for x in cp(m1["k"], m1["n"])]
    for r in R["rows"]: assert r == {**r, **px.combine(r["certs"][0], r["certs"][1], "UPGRADED")}   # combine 逐行现算一致


def test_verdict_rules_are_real_gates():
    def row(o1, o2, sec=(30, 31), w=("x",)):
        c = lambda o, s: {"outcome": o, "state": None, "sec": s, "witness": list(w), "n_evidence": 1}
        c1, c2 = c(o1, sec[0]), c(o2, sec[1]); return {"层": "B", "ptr": "p", "text_sha16": "t", "n_chars": 1, "certs": [c1, c2], **px.combine(c1, c2, "UPGRADED")}
    assert px.evaluate([row("UPGRADED", "UPGRADED")] * 42, PRE, cp)[1] == "ADOPT_SHADOW"
    assert px.evaluate([row("UPGRADED", "COVERAGE_FAIL")] * 42, PRE, cp)[1] == "NEEDS_N3"
    assert px.evaluate([row("MALFORMED", "MALFORMED")] * 42, PRE, cp)[1] == "STOP"
    assert px.evaluate([row("UPGRADED", "UPGRADED", sec=(60, 70))] * 42, PRE, cp)[1] == "COST_BLOCK"


def test_no_text_in_product_and_production_still_not_wired():
    for r in R["rows"]:
        assert set(r["certs"][0]) == {"outcome", "state", "sec", "witness", "n_evidence"} and all(len(w) == 16 for c in r["certs"] for w in c["witness"])
        assert r["ptr"].startswith("corpus/") or len(r["ptr"]) == 16
    s = json.dumps(R, ensure_ascii=False); assert "span" not in s.lower().replace("n_evidence", "") or "\"span\"" not in s
    assert "apikey_" not in s
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert "CCE_CITATION_CERT" not in src and "s2b" not in src
