# -*- coding: utf-8 -*-
"""闸: 填槽打分策略 v2(possession 合同等价类)。零调用。等价类必须由判据层现算; 三轮重算由产物现算一致且冻结产物未改; 与 artifact 的等价类口径数一致。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_pol", ROOT / "probes/slot_filling_score_policy_v2.py"); pol = importlib.util.module_from_spec(_s); _s.loader.exec_module(pol)
import cce_claim_frame as CF
R = json.loads((ROOT / "results/slot_filling_score_policy_v2.json").read_text(encoding="utf-8")); P = json.loads((ROOT / "tests/data/slot_filling_score_policy_v2_prereg.json").read_text(encoding="utf-8"))


def test_classes_are_derived_from_claim_frame_not_handwritten():
    cls, outcomes = pol.derive_classes(CF)
    assert cls["OWNED"] == cls["EXPERIENCED"] == "OWNED", "★ 合同 Q 是析取, 判据层应对两者给同一结局"
    # ★ 现算事实: 三类 —— {OWNED,EXPERIENCED} · {ONE_NEGATED,UNSPECIFIED}(都让 Q 不成立) · {BOTH_NEGATED}; 任一否定/未指明都不得与 OWNED 同类
    assert cls["ONE_NEGATED"] == cls["UNSPECIFIED"] != cls["OWNED"] and cls["BOTH_NEGATED"] not in (cls["OWNED"], cls["ONE_NEGATED"]) and len(set(cls.values())) == 3
    for pv in CF.POSSESSION: assert outcomes[pv] == R["★每个取值的两档结局"][pv], pv
    assert R["★★★等价类(由判据层现算, 不手写)"] == cls
    assert R["★判据源 sha(cce_claim_frame.py)"] == hashlib.sha256((ROOT / "scripts/cce_claim_frame.py").read_bytes()).hexdigest()[:16], "★ 判据源变了 ⇒ 等价类要重算"


def test_same_class_is_a_real_gate():
    cls, _ = pol.derive_classes(CF)
    assert pol.same_class("EXPERIENCED", "OWNED", cls) and not pol.same_class("BOTH_NEGATED", "OWNED", cls) and not pol.same_class(None, "OWNED", cls) and not pol.same_class("BOGUS", "OWNED", cls)


def test_rescore_recomputes_and_matches_artifact_and_frozen_runs_untouched():
    got = pol.build(); assert got["★★★三轮对照(可比不可合, 冻结产物未改)"] == R["★★★三轮对照(可比不可合, 冻结产物未改)"]
    art = json.loads((ROOT / "results/possession_gain_artifact.json").read_text(encoding="utf-8"))["★★★三轮对照"]
    for nm, v in R["★★★三轮对照(可比不可合, 冻结产物未改)"].items():
        assert v["v1 槽位级"] == art[nm]["槽位级原打分"] and v["v2 等价类"] == art[nm]["★合同等价类口径(OWNED≡EXPERIENCED)"], nm
        assert v["★产物 sha256(未改)"] == hashlib.sha256((ROOT / pol.RUNS[nm]).read_bytes()).hexdigest()
        assert v["v2 净增益"] >= 0 and "BOTH_NEGATED" in v["★测不出的类(金标 < 6)"] and "ONE_NEGATED" in v["★测不出的类(金标 < 6)"]
    assert R["★预注册 sha"] == hashlib.sha256((ROOT / "tests/data/slot_filling_score_policy_v2_prereg.json").read_bytes()).hexdigest()[:16]
    assert "禁止手写类表" in P["★★★规则"]["①等价类由判据层现算"] and "不回改" in P["★★★status"]
