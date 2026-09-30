# -*- coding: utf-8 -*-
"""闸: 对齐出口 V3(五题面面板; 分布口径准入)。零调用; 结果落盘后从原始读数重算。"""
import hashlib, importlib.util, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT   # noqa: E402
_p = importlib.util.spec_from_file_location("_v3", ROOT / "probes/align_atoms_v3.py"); V3 = importlib.util.module_from_spec(_p); _p.loader.exec_module(V3)
_sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def test_panel_questions_and_rule():
    for knot in AT.ATOMS_EN:
        q5, q6, v2 = AT.jev_questions_v3(knot), AT.jev_questions_v3(knot, AT.PANEL_V3 + (AT.AUDIT_V3,)), AT.jev_questions_v2(knot)
        items = {k.split("_")[0] for k in q5}
        assert len(q5) == 5 * len(items) and len(q6) == 6 * len(items)
        for i in items:
            assert q5[i + "_0"] == v2[i + "a"] and q5[i + "_1"] == v2[i + "p"]                       # 前两个题面与 V2 逐字相同
            assert len({q6["%s_%d" % (i, f)]["instructions"] for f in range(6)}) == 6                # 六个题面互不相同
            assert len({tuple(sorted(q6["%s_%d" % (i, f)]["criteria"])) for f in range(6)}) == 1     # 同一条目的选项集一致(极性一致)
        assert not any((knot, int(i)) in AT.MECHANICAL or (knot, int(i)) in AT.GUIDANCE_ONLY for i in items)
    S, U, N = "satisfied", "unsatisfied", "uncertain"
    assert AT.panel_value([S] * 5) == S and AT.panel_value([S] * 4 + [N]) == S and AT.panel_value([S] * 4 + [U]) == N
    assert AT.panel_value([U] * 4 + [N]) == U and AT.panel_value([S, S, S, N, N]) == N and AT.panel_value([]) == N


def _rows(n, votes_of):
    rows = []
    for b in range(n):
        for knot in AT.ATOMS_EN:
            for kind, key in [("orig", None), ("restore", None), ("neutral", None), ("audit", None)] + [(k, x) for x in V3.KEYS if x.startswith(knot + "#") for k in ("W", "H")]:
                atoms = {}
                for i, (_, neg) in enumerate(AT.atoms_of(knot)):
                    wv = AT.witness_value(neg); av = "satisfied" if wv == "unsatisfied" else "unsatisfied"
                    v = votes_of(b, kind, wv, av)
                    atoms[str(i)] = {"votes": v[:1] if kind == "audit" else v, "panel": AT.panel_value(v)}
                rows.append({"ptr": "b%d" % b, "knot": knot, "kind": kind, "key": key, "atoms": atoms, "err": None})
    return rows


def test_distribution_contract():
    ideal = lambda b, kind, wv, av: [wv] * 5 if kind == "W" else [av] * 5
    per, summ = V3.score(_rows(30, ideal), 30)
    assert summ == {"items": 26, "validated": 26, "strict_tier_pass": 0}               # 30 条: 分布口径可过, 类别口径的精确界过不了(样本不够)
    noisy = lambda b, kind, wv, av: [wv] * 5 if kind == "W" else ([av] * 4 + [wv] if kind == "neutral" and b % 2 else [av] * 5)
    per, _ = V3.score(_rows(30, noisy), 30)
    assert all(not x["criteria"]["neutral"] and x["criteria"]["reread"] for x in per.values())    # 中性句让一半底稿掉一票 ⇒ 漂移 0.1 > 0.05
    deaf = lambda b, kind, wv, av: [av] * 5
    assert all(not x["criteria"]["witness"] for x in V3.score(_rows(30, deaf), 30)[0].values())
    jumpy = lambda b, kind, wv, av: [wv] * 5 if kind in ("W", "H") else [av] * 5
    assert all(not x["criteria"]["hard_negative"] for x in V3.score(_rows(30, jumpy), 30)[0].values())
    assert V3.score(_rows(30, ideal), 116)[1]["validated"] == 0                          # 底稿不齐不算
    assert all(not x["criteria"]["hard_negative"] for x in V3.score(_rows(10, ideal), 10)[0].values())   # 可评底稿 < 20


def test_prereg_and_confirm_result():
    pre = json.loads((ROOT / "tests/data/align_atoms_v3_prereg.json").read_text(encoding="utf-8"))
    assert (V3.TOL_DRIFT, V3.MIN_W, V3.TOL_H, V3.TOL_AUDIT, V3.MIN_H_ELIG, V3.N_CONFIRM) == (0.05, 0.90, 0.05, 0.10, 20, 116) and "10208" in pre["budget"]
    bs = V3.bases("confirm"); used = {p for s in range(0, 140, 20) for p, _ in V3.V5.natural(s)}
    assert len({p for p, _ in bs}) == 116 and not used & {p for p, _ in bs} and len(V3.jobs(bs)) == 10208 <= V3.CAP["confirm"]
    out = ROOT / "results/align_atoms_v3.json"
    if out.exists():
        r = json.loads(out.read_text(encoding="utf-8"))
        assert r["prereg_sha256"] == _sha("tests/data/align_atoms_v3_prereg.json") and r["plants_sha256"] == _sha("probes/align_atoms_v2_plants.py")
        assert r["questions_sha256"] == hashlib.sha256(json.dumps({k: AT.jev_questions_v3(k, AT.PANEL_V3 + (AT.AUDIT_V3,)) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(), "题面在确认后被改过"
        assert not r["dry_run"] and r["requests"] <= V3.CAP["confirm"] and r["base_pointers"] == [p for p, _ in bs]
        per, summ = V3.score(r["raw"], 116)
        assert json.loads(json.dumps(per)) == r["per_atom"] and summ == r["summary"]
