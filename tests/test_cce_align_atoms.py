# -*- coding: utf-8 -*-
"""闸: 对齐出口 v4(逐原子三值)。零调用, 判官用桩。"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_align_atoms as AT   # noqa: E402

TXT = "Glad it worked out, enjoy them!"


def test_canonical_mapping_both_framings():
    C = AT.canonical
    assert C("做了", "enjoy them", False, "a", TXT) == "satisfied" and C("没做", "", False, "a", TXT) == "unsatisfied"
    assert C("违反", "enjoy them", True, "a", TXT) == "unsatisfied" and C("未违反", "", True, "a", TXT) == "satisfied"
    assert C("符合", "enjoy them", False, "b", TXT) == "satisfied" and C("不符合", "", False, "b", TXT) == "unsatisfied"
    assert C("不符合", "enjoy them", True, "b", TXT) == "unsatisfied" and C("符合", "", True, "b", TXT) == "satisfied"
    assert C("不确定", "", False, "a", TXT) == "uncertain" and C("乱写", "", True, "b", TXT) == "uncertain"


def test_present_side_needs_verbatim_quote():
    assert AT.canonical("做了", "", False, "a", TXT) == "uncertain"                  # 在场却不给子串
    assert AT.canonical("违反", "not in the text", True, "a", TXT) == "uncertain"    # 子串不在草稿里
    assert AT.canonical("未违反", "", True, "a", TXT) == "satisfied"                  # 缺席一侧不要子串


def _stub(states):
    def call(prompt, temperature=0.0):
        return json.dumps({"atoms": [{"i": i + 1, "state": s, "quote": q} for i, (s, q) in enumerate(states)]}, ensure_ascii=False)
    return call


def test_judge_rejects_incomplete_answers():
    n = len(AT.atoms_of("reward"))
    assert AT.judge("reward", TXT, call=_stub([("做了", "enjoy them")] * (n - 1))) is None


def test_alignment_withholds_without_usable_top1_or_calibration(monkeypatch, tmp_path):
    assert AT.atoms_alignment("reward", False, TXT)["status"] == "withheld"
    monkeypatch.setattr(AT, "CAL", str(tmp_path / "none.json"))
    assert AT.atoms_alignment("reward", True, TXT)["status"] == "withheld"


def test_alignment_reports_only_calibrated_atoms(monkeypatch, tmp_path):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"per_atom": {"reward#0": {"verdict": "CALIBRATED"}, "reward#1": {"verdict": "NOT_CALIBRATED"},
                                            "reward#2": {"verdict": "CALIBRATED"}}}), encoding="utf-8")
    monkeypatch.setattr(AT, "CAL", str(cal))
    r = AT.atoms_alignment("reward", True, TXT, call=_stub([("做了", "Glad it worked out"), ("没做", ""), ("未违反", "")]))
    assert r["status"] == "ok" and r["summary"] == {"calibrated": 2, "satisfied": 2, "unsatisfied": 0, "uncertain": 0}
    assert [a["canonical"] for a in r["atoms"]] == ["satisfied", "not_calibrated", "satisfied"]
    assert "alignment_score" not in r and "pass" not in r                           # 不出总分、不出放行布尔


def test_v41_typography_normalized_but_words_are_not():
    T = "You're right, it's fine"
    assert AT.canonical("做了", "you’re RIGHT", False, "a", T) == "satisfied"      # 引号样式/大小写不算改字
    assert AT.canonical("做了", "you are right", False, "a", T) == "uncertain"     # 改了词 ⇒ 不逐字
    assert AT.canonical("违反", "it’s fine", False, "a", T) == "unsatisfied"       # 【做】条目答「违反」+逐字 ⇒ 没做到
    assert AT.canonical("违反", "", False, "a", T) == "uncertain"


def test_calibration_results_recompute_and_production_uses_heldout_only():
    import importlib.util as _iu
    _p = _iu.spec_from_file_location("_ac", ROOT / "probes/align_atoms_calibration.py"); ac = _iu.module_from_spec(_p); _p.loader.exec_module(ac)
    dev = json.loads((ROOT / "results/align_atoms_calibration.json").read_text(encoding="utf-8"))
    assert not dev["dry_run"] and dev["requests"]["used"] <= 350
    per, summ = ac.score(dev["raw"])
    assert per == dev["per_atom"] and summ == dev["summary"] and summ["calibrated"] == 8
    assert not AT.CAL.endswith("align_atoms_calibration.json")                     # 开发集不作生产采纳依据


def test_heldout_result_recomputes_and_drives_production():
    import importlib.util as _iu
    sys.path.insert(0, str(ROOT / "probes"))
    _p = _iu.spec_from_file_location("_ac2", ROOT / "probes/align_atoms_calibration.py"); ac = _iu.module_from_spec(_p); _p.loader.exec_module(ac)
    import align_atoms_heldout_cases as HC
    import hashlib as _h
    ho = json.loads((ROOT / "results/align_atoms_heldout_v41.json").read_text(encoding="utf-8"))
    assert ho["prereg_sha256"] == _h.sha256((ROOT / "tests/data/align_atoms_heldout_prereg.json").read_bytes()).hexdigest()
    assert ho["judge_version"] == "v4.1" and not ho["dry_run"] and ho["requests"]["used"] <= 240
    per, summ = ac.score(ho["raw"], HC.CASES)
    assert per == ho["per_atom"] and summ == ho["summary"] and summ["v1_accuracy"] is None
    assert summ["calibrated"] == 11 and ho["per_atom"]["inertia#0"]["verdict"] == "NOT_CALIBRATED"   # 条件句原子不过


def test_v5_operational_split_touches_only_suspend_and_audit():
    assert set(AT.OPERATIONAL) == {"suspend", "audit"}
    for k, items in AT.OPERATIONAL.items():
        assert len(items) == 4 and AT.atoms_of(k) == [(t, neg) for t, neg, _ in items]
        assert {src for _, _, src in items} <= set(range(len([p for p in __import__("re").split(r"[;；]", AT.A.PLAYBOOK[k]) if p.strip()])))
    assert len(AT.atoms_of("reward")) == 3 and len(AT.atoms_of("injustice")) == 3      # 其余结清单不变


def test_v5_result_recomputes_and_is_the_production_list():
    import importlib.util as _iu, hashlib as _h
    sys.path.insert(0, str(ROOT / "probes"))
    _p = _iu.spec_from_file_location("_v5", ROOT / "probes/align_atoms_v5.py"); v5 = _iu.module_from_spec(_p); _p.loader.exec_module(v5)
    r = json.loads((ROOT / "results/align_atoms_v5.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == _h.sha256((ROOT / "tests/data/align_atoms_v5_prereg.json").read_bytes()).hexdigest()
    assert not r["dry_run"] and r["requests"]["used"] <= v5.CAP
    per, summ = v5.score(r["raw"])
    assert per == r["per_atom"] and summ == r["summary"]
    for v in per.values():
        assert (v["verdict"] == "CALIBRATED") == (v["setC_correct"] == v["setC_n"] == 16 and v["natural_agree_rate"] >= 0.85)
    assert all("ptr" in x and "text" not in x for x in r["raw"] if x["part"] == "N")     # 真实回复只留指针


def test_jev_judge_questions_align_with_atoms_and_map_both_framings(monkeypatch):
    for k, en in AT.ATOMS_EN.items():
        assert len(en) == len(AT.atoms_of(k)), k
        qs = AT.jev_questions(k)
        for i, (_, neg) in enumerate(AT.atoms_of(k)):
            assert set(qs["%da" % i]["criteria"]) == ({"violated", "not_violated", "unclear"} if neg else {"done", "not_done", "unclear"})
            assert ("must not" in qs["%db" % i]["instructions"]) is neg
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    def post(body, key):
        ans = {}
        for q, spec in body["questions"].items():
            ans[q] = {"choice": [c for c in spec["criteria"] if c in ("done", "violated", "complies")][0], "probabilities": {}}
        return {"answers": ans}, None
    r, err = AT.judge_jev("reward", TXT, post=post)
    assert err is None and r[0] == {"a": "satisfied", "b": "satisfied", "p_a": {}}           # 【做】done / complies
    assert r[2]["a"] == "unsatisfied" and r[2]["b"] == "satisfied"                            # 【禁】violated ⇒ 不满足; complies ⇒ 满足
    r, err = AT.judge_jev("reward", TXT, post=lambda b, k: (None, "HTTP 503"))
    assert r is None and err == "HTTP 503"
