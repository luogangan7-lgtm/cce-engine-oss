# -*- coding: utf-8 -*-
"""闸: s1 组内散布闸按仪器重标定(预注册 tests/data/within_js_recalibration_prereg.json)。零调用。
结果只能从冻结的标定集与留出数字现算; 新阈值只挂在它标定的那台仪器上。"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
_s = importlib.util.spec_from_file_location("_wr", ROOT / "probes/within_js_recalibrate.py"); wr = importlib.util.module_from_spec(_s); _s.loader.exec_module(wr)
import cce_full_run as FR   # noqa: E402
R = json.loads((ROOT / "results/within_js_recalibration.json").read_text(encoding="utf-8"))
PRE = json.loads((ROOT / "tests/data/within_js_recalibration_prereg.json").read_text(encoding="utf-8"))


def test_result_recomputes_from_frozen_inputs():
    assert R["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/within_js_recalibration_prereg.json").read_bytes()).hexdigest()
    assert R["holdout_numbers_sha256"] == hashlib.sha256((ROOT / "results/within_js_holdout_numbers.json").read_bytes()).hexdigest()
    cal = wr.calibrate(PRE["calibration_set"]["files"])
    assert cal == R["calibration"]
    rows = json.loads((ROOT / "results/within_js_holdout_numbers.json").read_text(encoding="utf-8"))["rows"]
    assert wr.evaluate(cal, FR.WITHIN_JS_MAX_DEFAULT, rows) == R["holdout"]
    assert all(v["adopt"] == (0.05 <= v["holdout_exceed_new"] <= 0.25) for v in R["holdout"].values())


def test_thresholds_attach_only_to_their_instrument():
    assert FR.within_js_max(PRE["calibration_set"]["instrument_hash"]) == R["adopted"]
    assert FR.within_js_max("never_calibrated_hash") == FR.WITHIN_JS_MAX_DEFAULT       # 没重标过的仪器沿用旧值(k=5 已另行重标, 见下)
    assert FR.within_js_max(None) == FR.WITHIN_JS_MAX_DEFAULT


def test_s1_gate_uses_the_run_instrument(monkeypatch, tmp_path):
    """同一 within_js, 在重标仪器上 need 0.25 不扣发(新阈值 0.308), 在未重标仪器上扣发(旧 0.161)。"""
    def fake(text_file, context, k, out, ih):
        return {"stage1": {"within_js": {"desire_vec": 0.1, "need_vec": 0.25, "emotion_vec": 0.05, "action_vec": 0.05},
                           "tops": {"desire": "d", "need": "n", "emotion": "e", "action": "a"}, "k_valid": 3},
                "stage2": {"instrument": {"instrument_hash": ih}}}
    for ih, withheld in ((PRE["calibration_set"]["instrument_hash"], False), ("some_other_hash", True)):
        monkeypatch.setattr(FR, "run_knot_classify", lambda *a, _ih=ih: fake(*a, _ih))
        FR.s1({"text_file": "x", "context": "c", "k": 3, "outdir": str(tmp_path)})
        m = FR.MANIFEST["s1_readout"]
        assert (m["tops"]["need"] is None) is withheld, (ih, m)


def test_k5_recalibration_recomputes_and_attaches_to_k5_instrument():
    _p = importlib.util.spec_from_file_location("_k5", ROOT / "probes/within_js_k5_recalibrate.py"); k5 = importlib.util.module_from_spec(_p); _p.loader.exec_module(k5)
    r = json.loads((ROOT / "results/within_js_recalibration_k5.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/within_js_k5_recalibration_prereg.json").read_bytes()).hexdigest()
    assert r["numbers_sha256"] == hashlib.sha256((ROOT / "results/within_js_k5_numbers.json").read_bytes()).hexdigest()
    num = json.loads((ROOT / "results/within_js_k5_numbers.json").read_text(encoding="utf-8"))
    assert num["requests"]["used"] <= k5.CAP and all(set(x) == {"set", "text", "rep", "sha16", "instrument", "within_js", "layers"} for x in num["rows"])
    cal, hold, adopted = k5.build(num["rows"])
    assert (cal, hold, adopted) == (r["calibration"], r["holdout"], r["adopted"])
    assert FR.within_js_max(k5.INSTRUMENT) == r["adopted"] != FR.within_js_max(PRE["calibration_set"]["instrument_hash"])
    # 留出扣发率不在 [0.05, 0.25] 的层保留旧阈值
    for l, v in r["holdout"].items():
        assert r["adopted"][l] == (v["new_threshold"] if v["adopt"] else FR.WITHIN_JS_MAX_DEFAULT[l])
