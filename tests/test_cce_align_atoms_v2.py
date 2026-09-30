# -*- coding: utf-8 -*-
"""闸: 对齐出口 V2(单问法 A + 同极性改写 A′; 真实底稿变形测试准入)。零调用。"""
import importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT   # noqa: E402
_p = importlib.util.spec_from_file_location("_v2", ROOT / "probes/align_atoms_v2.py"); V2 = importlib.util.module_from_spec(_p); _p.loader.exec_module(V2)


def test_v2_questions_keep_A_verbatim_and_add_same_polarity_paraphrase():
    n = 0
    for k in AT.ATOMS_EN:
        v1, v2 = AT.jev_questions(k), AT.jev_questions_v2(k)
        for i, (_, neg) in enumerate(AT.atoms_of(k)):
            if (k, i) in AT.MECHANICAL or (k, i) in AT.GUIDANCE_ONLY:
                assert "%da" % i not in v2; continue
            assert v2["%da" % i] == v1["%da" % i]                                        # 生产问法 A 与 V1 逐字相同
            assert set(v2["%dp" % i]["criteria"]) == set(v2["%da" % i]["criteria"])      # A′ 同极性、同选项
            assert v2["%dp" % i]["instructions"] != v2["%da" % i]["instructions"] and "%db" % i not in v2
            n += 1
    assert n == 26 and set(AT.GUIDANCE_ONLY) == {("inertia", 0), ("display", 1)}


def test_plants_cover_exactly_the_judged_items():
    judged = {"%s#%d" % (k, i) for k in AT.ATOMS_EN for i in range(len(AT.atoms_of(k))) if (k, i) not in AT.MECHANICAL and (k, i) not in AT.GUIDANCE_ONLY}
    assert set(V2.PL.PLANTS) == judged
    assert all(len(v["W"]) == 2 and len(v["H"]) == 2 for v in V2.PL.PLANTS.values())


def _rows(overrides=None, n=60):
    """合成一份「全对」的读数, 再按 overrides 改个别(底稿序号, kind, key) 的 A 值。"""
    rows = []
    for b in range(n):
        for knot in AT.ATOMS_EN:
            idx = [i for i in range(len(AT.atoms_of(knot))) if "%da" % i in AT.jev_questions_v2(knot)]
            absent = {str(i): {"a": "satisfied" if AT.atoms_of(knot)[i][1] else "unsatisfied", "p": "uncertain"} for i in idx}
            for kind in ("orig", "restore", "neutral"):
                rows.append({"ptr": "b%d" % b, "knot": knot, "kind": kind, "key": None, "atoms": json.loads(json.dumps(absent))})
        for key in V2.KEYS:
            knot, i = key.split("#"); neg = AT.atoms_of(knot)[int(i)][1]
            idx = [j for j in range(len(AT.atoms_of(knot))) if "%da" % j in AT.jev_questions_v2(knot)]
            absent = {str(j): {"a": "satisfied" if AT.atoms_of(knot)[j][1] else "unsatisfied", "p": "uncertain"} for j in idx}
            w = json.loads(json.dumps(absent)); w[i]["a"] = AT.witness_value(neg)
            rows.append({"ptr": "b%d" % b, "knot": knot, "kind": "W", "key": key, "atoms": w})
            rows.append({"ptr": "b%d" % b, "knot": knot, "kind": "H", "key": key, "atoms": json.loads(json.dumps(absent))})
    for (b, kind, key, item, val) in (overrides or []):
        for r in rows:
            if r["ptr"] == "b%d" % b and r["kind"] == kind and r["key"] == key and r["knot"] == item.split("#")[0]:
                r["atoms"][item.split("#")[1]]["a"] = val
    return rows


def test_score_rules():
    per, summ = V2.score(_rows(), 60)
    assert summ == {"items": 26, "validated": 26}
    K = "pain_seek#0"
    # 见证没检出 2 次 ⇒ 不过; 1 次 ⇒ 过
    assert V2.score(_rows([(0, "W", K, K, "uncertain")]), 60)[0][K]["verdict"] == "VALIDATED"
    per, _ = V2.score(_rows([(0, "W", K, K, "uncertain"), (1, "W", K, K, "unsatisfied")]), 60)
    assert per[K]["verdict"] == "NOT_VALIDATED" and per[K]["failure_types"] == {"F_W": 2}
    # 难负例/中性句把读数推到在场一侧 ⇒ 失败
    per, _ = V2.score(_rows([(0, "H", K, K, "satisfied"), (1, "neutral", None, K, "satisfied")]), 60)
    assert per[K]["failure_types"] == {"F_H": 1, "F_N": 1} and per[K]["verdict"] == "NOT_VALIDATED"
    # 原文两次读数相反 ⇒ F_R; 同一底稿多种失败只算一个失败底稿
    per, _ = V2.score(_rows([(0, "restore", None, K, "satisfied"), (0, "W", K, K, "uncertain")]), 60)
    assert per[K]["failing_bases"] == 1 and set(per[K]["failure_types"]) == {"F_R", "F_W"}
    # 覆盖率: 原文 A 多数 unclear ⇒ 不过
    low = _rows([(b, "orig", None, K, "uncertain") for b in range(30)] + [(b, "restore", None, K, "uncertain") for b in range(30)] + [(b, "neutral", None, K, "uncertain") for b in range(30)])
    assert V2.score(low, 60)[0][K]["coverage"] == 0.5 and V2.score(low, 60)[0][K]["verdict"] == "NOT_VALIDATED"
    # 底稿数不足 60 ⇒ 不过
    assert V2.score(_rows(n=8), 60)[1]["validated"] == 0


def test_judge_v2_maps_and_handles_mechanical(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    def post(body, key):
        return {"answers": {q: {"choice": [c for c in s["criteria"] if c in ("done", "violated")][0], "probabilities": {}} for q, s in body["questions"].items()}}, None
    r, err = AT.judge_jev_v2("reward", "Glad it worked out!", post=post)
    assert err is None and r[0] == {"a": "satisfied", "p": "satisfied", "p_a": None}       # 机械规则
    assert r[1]["a"] == "satisfied" and r[2]["a"] == "unsatisfied"                         # done ⇒ satisfied; violated ⇒ unsatisfied
    r, _ = AT.judge_jev_v2("inertia", "x", post=post)
    assert 0 not in r and set(r) == {1, 2}                                                 # 指导用条目不判


def test_confirm_result_recomputes_and_sets_the_production_list(monkeypatch, tmp_path):
    monkeypatch.setattr(AT, "JEV_V3", str(tmp_path / "none.json"))      # V2 名单是 V3 发货前的生产行为, 留作回归
    import hashlib
    r = json.loads((ROOT / "results/align_atoms_v2.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/align_atoms_v2_prereg.json").read_bytes()).hexdigest()
    assert r["plants_sha256"] == hashlib.sha256((ROOT / "probes/align_atoms_v2_plants.py").read_bytes()).hexdigest(), "植入句在确认后被改过"
    assert r["questions_sha256"] == hashlib.sha256(json.dumps({k: AT.jev_questions_v2(k) for k in AT.ATOMS_EN}, sort_keys=True).encode()).hexdigest(), "题面在确认后被改过"
    assert r["stage"] == "confirm" and not r["dry_run"] and r["requests"] <= V2.CAP["confirm"] and sum(r["errors"].values()) <= 1
    used = {p for s in (0, 20, 40, 60) for p, _ in V2.V5.natural(s)}
    assert len(set(r["base_pointers"])) == 60 and not used & set(r["base_pointers"])
    per, summ = V2.score(r["raw"], 60)
    assert per == r["per_atom"] and summ == r["summary"] == {"items": 26, "validated": 5}
    for v in per.values():
        assert (v["verdict"] == "VALIDATED") == (v["failing_bases"] <= 1 and v["coverage"] >= 0.70)
    # 预注册的三条预测: P1(>=12 条通过)未中, P2(V1 落选的里 >=3 条通过)未中, P3(V1 入选的里 >=2 条不过)中
    v1 = {k for k, v in json.loads((ROOT / "results/align_atoms_jev_final.json").read_text(encoding="utf-8"))["per_atom"].items() if v["verdict"] == "CALIBRATED"}
    val = {k for k, v in per.items() if v["verdict"] == "VALIDATED"}
    assert len(val) < 12 and len(val - v1) < 3 and len((v1 & set(per)) - val) >= 2
    # 发货规则: 生产名单 = V2 通过的 + 机械条目; 没有条目的结整结扣发
    assert AT.calibrated_atoms() == {"pain_seek": {1}, "injustice": {1}, "reward": {0, 1}, "suspend": {1, 3}}
    assert AT.atoms_alignment("belong", True, "x")["status"] == "withheld"


def test_v2_production_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setattr(AT, "JEV_V3", str(tmp_path / "none.json"))
    def post(body, key):                       # suspend: #1 两问都检出; #3(禁) A 检出违规而 A′ 说没有 ⇒ uncertain
        pick = {"1a": "done", "1p": "done", "3a": "violated", "3p": "not_violated"}
        return {"answers": {q: {"choice": pick.get(q, "not_violated" if "not_violated" in spec["criteria"] else "not_done"), "probabilities": {}} for q, spec in body["questions"].items()}}, None
    r = AT.atoms_alignment("suspend", True, "reply", post=post)
    a = {x["i"]: x for x in r["atoms"]}
    assert r["status"] == "ok" and r["judge_version"] == "v2" and r["summary"] == {"calibrated": 2, "satisfied": 1, "unsatisfied": 0, "uncertain": 1}
    assert a[1]["canonical"] == "satisfied" and a[3]["canonical"] == "uncertain" and a[0]["canonical"] == a[2]["canonical"] == "not_calibrated"
    assert "未检出" in r["★v2_reading"]
    g = AT.atoms_alignment("reward", True, "Thanks, glad it helped.", post=post)     # 机械条目按规则判
    assert {x["i"]: x["canonical"] for x in g["atoms"]}[0] == "satisfied"
    assert AT.atoms_alignment("suspend", True, "reply", post=lambda b, k: (None, "HTTP 503"))["status"] == "failed"
