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
    monkeypatch.setattr(AT, "PRODUCTION_JUDGE", "minimax")        # 本条测 MiniMax 判官那条路
    monkeypatch.setattr(AT, "CAL", str(tmp_path / "none.json"))
    assert AT.atoms_alignment("reward", True, TXT)["status"] == "withheld"


def test_alignment_reports_only_calibrated_atoms(monkeypatch, tmp_path):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"per_atom": {"reward#0": {"verdict": "CALIBRATED"}, "reward#1": {"verdict": "NOT_CALIBRATED"},
                                            "reward#2": {"verdict": "CALIBRATED"}}}), encoding="utf-8")
    monkeypatch.setattr(AT, "CAL", str(cal)); monkeypatch.setattr(AT, "PRODUCTION_JUDGE", "minimax")
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
            if (k, i) in AT.MECHANICAL:
                assert "%da" % i not in qs; continue            # 机械规则的条目不发给模型
            assert set(qs["%da" % i]["criteria"]) == ({"violated", "not_violated", "unclear"} if neg else {"done", "not_done", "unclear"})
            assert ("must not" in qs["%db" % i]["instructions"]) is neg
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    def post(body, key):
        ans = {}
        for q, spec in body["questions"].items():
            ans[q] = {"choice": [c for c in spec["criteria"] if c in ("done", "violated", "complies")][0], "probabilities": {}}
        return {"answers": ans}, None
    r, err = AT.judge_jev("reward", TXT, post=post)
    assert err is None and r[0] == {"a": "satisfied", "b": "satisfied", "p_a": None}         # reward#0 机械规则: TXT 一句话 ⇒ 短
    assert r[1] == {"a": "satisfied", "b": "satisfied", "p_a": {}}                            # 【做】done / complies
    assert r[2]["a"] == "unsatisfied" and r[2]["b"] == "satisfied"                            # 【禁】violated ⇒ 不满足; complies ⇒ 满足
    assert AT.judge_jev("reward", "One. Two. Three.", post=post)[0][0]["a"] == "unsatisfied"  # 三句 ⇒ 不短
    r, err = AT.judge_jev("reward", TXT, post=lambda b, k: (None, "HTTP 503"))
    assert r is None and err == "HTTP 503"


def test_production_judge_is_jev_and_backed_by_results():
    """发货规则: Jev 校对通过的条目数 > MiniMax v5 才切换。常量必须有结果撑着。"""
    import importlib.util as _iu, hashlib as _h
    sys.path.insert(0, str(ROOT / "probes"))
    _p = _iu.spec_from_file_location("_aj", ROOT / "probes/align_atoms_jev.py"); aj = _iu.module_from_spec(_p); _p.loader.exec_module(aj)
    r = json.loads((ROOT / "results/align_atoms_jev.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == _h.sha256((ROOT / "tests/data/align_atoms_jev_prereg.json").read_bytes()).hexdigest()
    assert not r["dry_run"] and r["requests"] <= aj.CAP and not r["errors"]
    assert r["questions_sha256"] == _h.sha256(json.dumps({k: AT.jev_questions(k, AT.ATOMS_EN_V1) for k in AT.ATOMS_EN_V1}, sort_keys=True).encode()).hexdigest(), "题面在校对后被改过"
    assert {k for k in AT.ATOMS_EN if AT.ATOMS_EN[k] != AT.ATOMS_EN_V1[k]} == {"reward"}       # 只有 reward 的题面重做过, 其余逐字不变
    per, summ = aj.score(r["raw"])
    assert per == r["per_atom"] and summ == r["summary"]
    n_jev = sum(len(v) for k, v in AT.calibrated_atoms("jev").items() if k != "reward"); n_mm = sum(len(v) for v in AT.calibrated_atoms("minimax").values())
    assert AT.PRODUCTION_JUDGE == "jev" and n_jev == summ["calibrated"] == 14 > n_mm == 5
    assert not any(k.startswith("reward#") and v["verdict"] == "CALIBRATED" for k, v in per.items())   # 原题面下 reward 三条都没过


def test_jev_alignment_path(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    def post(body, key):
        ans = {}
        for q, spec in body["questions"].items():
            pos = [c for c in spec["criteria"] if c in ("done", "violated", "complies")][0]
            neg = [c for c in spec["criteria"] if c in ("not_done", "not_violated", "does_not_comply")][0]
            ans[q] = {"choice": pos if q in ("0a", "0b", "1a", "1b") else neg, "probabilities": {pos: 0.9}}   # 第 1 条(禁): A=violated、B=complies ⇒ 两问法不一致
        return {"answers": ans}, None
    r = AT.atoms_alignment("pain_seek", True, TXT, post=post)
    assert r["status"] == "ok" and r["judge"] == "jev" and r["summary"]["calibrated"] == 2
    assert r["atoms"][0]["canonical"] == "satisfied"
    assert r["atoms"][1]["canonical"] == "uncertain"                                     # 两问法规范值不同 ⇒ uncertain
    assert AT.atoms_alignment("pain_seek", True, TXT, post=lambda b, k: (None, "HTTP 503"))["status"] == "failed"


def test_reward_rework_recomputes_and_every_knot_has_a_judgeable_item():
    import importlib.util as _iu, hashlib as _h
    sys.path.insert(0, str(ROOT / "probes"))
    _p = _iu.spec_from_file_location("_ar", ROOT / "probes/align_atoms_jev_reward.py"); ar = _iu.module_from_spec(_p); _p.loader.exec_module(ar)
    r = json.loads((ROOT / "results/align_atoms_jev_reward.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == _h.sha256((ROOT / "tests/data/align_atoms_jev_reward_prereg.json").read_bytes()).hexdigest()
    assert not r["dry_run"] and r["requests"] <= ar.CAP and not r["errors"]
    assert r["questions_sha256"] == _h.sha256(json.dumps(AT.jev_questions("reward"), sort_keys=True).encode()).hexdigest(), "reward 题面在校对后被改过"
    assert r["short_rule"] == {"max_sentences": AT.SHORT_MAX_SENTENCES, "max_words": AT.SHORT_MAX_WORDS}
    per, summ = ar.score(r["raw"])
    assert per == r["per_atom"] and summ == r["summary"]
    assert {k: v["verdict"] for k, v in per.items()} == {"reward#0": "CALIBRATED", "reward#1": "CALIBRATED", "reward#2": "NOT_CALIBRATED"}
    cal = AT.calibrated_atoms("jev")
    assert cal["reward"] == {0, 1} and set(cal) == set(AT.ATOMS_EN) and sum(len(v) for v in cal.values()) == 16
    n1, n2 = ar.AJ.V5.natural(0), ar.AJ.V5.natural(20)
    assert r["heldout_natural_pointers"] == [p for p, _ in n2] and not {p for p, _ in n1} & {p for p, _ in n2}   # 判定只用没见过的 20 条


def test_alignment_prospective_scorer_withholds_until_n():
    import importlib.util as _iu
    _p = _iu.spec_from_file_location("_af", ROOT / "probes/align_followup_score.py"); af = _iu.module_from_spec(_p); _p.loader.exec_module(af)
    assert af.score([{"score": 1.0, "followed_up": True}] * 5)["verdict"] == "INSUFFICIENT"
    assert af.score([{"score": 1.0, "followed_up": True}] * 20 + [{"score": -1.0, "followed_up": False}] * 20)["verdict"] == "PREDICTIVE"
    assert af.score([{"score": s, "followed_up": f} for s in (0.0, 0.5) for f in (True, False) for _ in range(10)])["verdict"] == "NOT_PREDICTIVE"
    assert af.is_test_run("canary7:2026-09-30:outbound_reply_jev_e2e") and af.is_test_run("submit:example:reply:001") and not af.is_test_run("humaux:reply:20261001:abc")
    rs = af.rows()                                           # 归档里已有一条 status=ok 的 canary(36698289171) —— 不得进前瞻样本
    assert isinstance(rs, list) and not any("36698289171" in r["src"] for r in rs)
