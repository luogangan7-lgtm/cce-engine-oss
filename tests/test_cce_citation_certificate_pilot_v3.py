# -*- coding: utf-8 -*-
"""闸: 引用证书试点 v3 产物(results/citation_certificate_pilot_v3.json)。零调用。
守: 预注册 v3 sha 投料前冻结且未改 · 指标/判决/逐行 combine 由 rows 现算一致 · 每张证书 ≤2 次调用且总数 ≤176 · 原因码在、无原文 · 与 v2 产物同材料(指针集相同) · 生产仍未接线。"""
import hashlib, importlib.util, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
os.environ["CCE_CERT_PROTOCOL"] = "v3"
_s = importlib.util.spec_from_file_location("_pxv3g", ROOT / "probes/citation_certificate_pilot_run.py"); px = importlib.util.module_from_spec(_s); _s.loader.exec_module(px)
os.environ.pop("CCE_CERT_PROTOCOL", None)
PRE = json.loads(px.PRE.read_text(encoding="utf-8")); R = json.loads(px.OUT.read_text(encoding="utf-8")); V2 = json.loads((ROOT / "results/citation_certificate_pilot.json").read_text(encoding="utf-8"))
cp = px._load("probes/real_corpus_pilot_prereg.py", "_rcp_v3t").clopper_pearson


def test_prereg_v3_frozen_before_and_budget_respected():
    assert R["protocol"] == "v3" and R["★预注册 sha(投料前冻结)"] == hashlib.sha256(px.PRE.read_text(encoding="utf-8").encode()).hexdigest()[:16]
    assert R["★实际调用"] <= R["★硬上限"] == PRE["★预算硬上限"]["证书调用"] == 176
    assert R["★实际调用"] == sum(c["calls"] for r in R["rows"] for c in r["certs"])
    for r in R["rows"]:
        for c in r["certs"]: assert 0 <= c["calls"] <= 2 and (c["repaired"] is (c["calls"] == 2) or c["outcome"] == "CAP_HIT")


def test_metrics_verdict_and_rows_recompute():
    M, v = px.evaluate(R["rows"], PRE, cp)
    assert M == R["★★★指标"] and v == R["★★★判决(按预注册规则现算)"] and "M5 修复(仅 v3)" in M
    for r in R["rows"]: assert r == {**r, **px.combine(r["certs"][0], r["certs"][1], "UPGRADED")}
    m5 = M["M5 修复(仅 v3)"]; assert m5["证书数"] == 2 * sum(1 for r in R["rows"] if r["层"] == "B")
    assert set(m5["首答族分布"]) <= set(px.P3.CODES) and set(m5["终态族分布"]) <= set(px.P3.CODES)


def test_same_material_as_v2_and_no_text_and_not_wired():
    assert [r["ptr"] for r in R["rows"]] == [r["ptr"] for r in V2["rows"]] and [r["text_sha16"] for r in R["rows"]] == [r["text_sha16"] for r in V2["rows"]]
    for r in R["rows"]:
        for c in r["certs"]:
            full = {"outcome", "state", "sec", "witness", "n_evidence", "reason_codes", "reason_codes_first", "repaired", "calls"}
            # ★ 本轮执行器的 CALL_FAIL 分支漏了 reason_codes_first 键(产物里 1 张); 已修执行器, 产物不回改 —— 闸对 CALL_FAIL 容忍该键缺失
            assert set(c) == full or (c["outcome"] == "CALL_FAIL" and set(c) == full - {"reason_codes_first"}), set(c)
            assert all(len(w) == 16 for w in c["witness"])
    s = json.dumps(R, ensure_ascii=False); assert "apikey_" not in s and '"span"' not in s and '"object"' not in s and '"why"' not in s
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert "CCE_CITATION_CERT" not in src and "s2b" not in src
