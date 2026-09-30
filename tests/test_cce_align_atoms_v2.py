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
