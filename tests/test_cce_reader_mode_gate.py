# -*- coding: utf-8 -*-
"""闸: 对齐出口读者闸(全一致 vs 众数占比 >= 0.8)的确认研究。零调用; 结果落盘后重算。"""
import hashlib, importlib.util, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_rg", ROOT / "probes/reader_mode_gate.py"); RG = importlib.util.module_from_spec(_s); _s.loader.exec_module(RG)
_sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def _rows(n_texts, pattern):
    return [{"ptr": "t%d" % t, "rep": r, "mode": m, "share": s} for t in range(n_texts) for r, (m, s) in enumerate(pattern(t))]


def test_rules():
    good = RG.build(_rows(20, lambda t: [("a", 0.8), ("a", 1.0), ("a", 1.0)]))
    assert good["verdict"] == "MODE_GATE_OK" and good["by_share"]["0.8"]["agree"] == 20 and good["availability"] == {"unanimous_only": 0.6667, "share_ge_0.8": 1.0}
    assert RG.build(_rows(20, lambda t: [("b" if t < 6 else "a", 0.8), ("a", 1.0), ("a", 1.0)]))["verdict"] == "KEEP_UNANIMOUS"      # 14/20 = 0.70
    assert RG.build(_rows(8, lambda t: [("a", 0.8), ("a", 1.0), ("a", 1.0)]))["verdict"] == "INSUFFICIENT"
    nc = RG.build(_rows(20, lambda t: [("a", 0.8), ("a", 1.0), ("b", 1.0)]))
    assert nc["by_share"]["0.8"]["no_consensus"] == 20 and nc["verdict"] == "KEEP_UNANIMOUS"                                        # 另两次不一致按不一致计
    assert RG.build(_rows(20, lambda t: [("a", 0.8), ("a", 1.0)]))["texts_complete"] == 0                                           # 三次不齐不进
    tx = RG.texts(); assert len({p for p, _ in tx}) == 24 == RG.N_TEXTS and (RG.CAP, RG.SHARE, RG.MIN_POINT, RG.MIN_LCB) == (800, 0.8, 0.875, 0.80)


def test_result_recomputes():
    out = ROOT / "results/reader_mode_gate.json"
    if out.exists():
        r = json.loads(out.read_text(encoding="utf-8")); num = json.loads((ROOT / "results/reader_mode_gate_rows.json").read_text(encoding="utf-8"))
        assert r["prereg_sha256"] == _sha("tests/data/reader_mode_gate_prereg.json") and r["rows_sha256"] == _sha("results/reader_mode_gate_rows.json")
        assert r["result"] == json.loads(json.dumps(RG.build(num["rows"]))) and num["requests"]["used"] <= RG.CAP
