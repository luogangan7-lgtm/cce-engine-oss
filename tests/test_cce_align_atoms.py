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
    assert AT.CAL.endswith("align_atoms_heldout_v41.json")                         # 开发集不作生产采纳依据
