# -*- coding: utf-8 -*-
"""闸: reply_loop 接上对齐出口 v4.1 —— 只在读者 top-1 稳定且 K1 可用时判, 用 s2 抽样众数 top1_mode(不是权重 argmax)。零调用。"""
import json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import reply_loop   # noqa: E402


def _run(monkeypatch, sampling):
    seen = {}
    def fake_readout(text, context, k, tag, outdir):
        return {"stage1": {"layers": {L: [1.0, 0.0, 0.0, 0.0] for L in reply_loop.LAYERS}},
                "stage2": {"knots": [{"key": "display", "weight": 0.7}, {"key": "pain_seek", "weight": 0.3}],
                           "sampling": sampling, "instrument": {"instrument_hash": "d4cce4c745f3f991"}}}
    monkeypatch.setattr(reply_loop, "readout", fake_readout)
    monkeypatch.setattr(reply_loop, "knot_align", lambda *a, **k: {"alignment_score": 0.5, "resonance": 0, "dissolution": 0.5, "detail": []})
    monkeypatch.setattr(reply_loop, "LAYERS", {L: ["d0", "d1", "d2", "d3"] for L in reply_loop.LAYERS})
    monkeypatch.setattr(reply_loop, "atoms_alignment", lambda knot, ok, text: seen.update(knot=knot, ok=ok) or {"status": "stub"})
    d = tempfile.mkdtemp()
    r, w, o = (os.path.join(d, x) for x in ("r.txt", "w.txt", "o.json"))
    open(r, "w").write("READER"); open(w, "w").write("DRAFT")
    monkeypatch.setattr(sys, "argv", ["reply_loop.py", "--reader", r, "--draft", w, "--context", "t", "--out", o])
    reply_loop.main()
    return seen, json.load(open(o))["verdict"]


def test_uses_stable_top1_mode_not_weight_argmax(monkeypatch):
    seen, v = _run(monkeypatch, {"top1_stable": True, "top1_mode": "pain_seek"})
    assert seen == {"knot": "pain_seek", "ok": True} and v["top1逐原子对齐"] == {"status": "stub", "reader_top1_share": None}


def test_unstable_top1_is_not_usable(monkeypatch):
    seen, _ = _run(monkeypatch, {"top1_stable": None, "top1_mode": "pain_seek"})
    assert seen["ok"] is False


def test_s1_abstain_on_either_side_withholds_reach_instead_of_crashing(monkeypatch):
    """线上 run 36740247086: 我方草稿被 s1 判弃权(layers 为空)⇒ reply_loop 索引 layers 崩, 整条 measure 失败。现在: 触达不可判。"""
    ok = {"stage1": {"measurement_status": "qualified", "layers": {L: [1.0, 0.0] for L in reply_loop.LAYERS}}}
    ab = {"stage1": {"measurement_status": "abstain", "layers": {}}}
    for a, b, side in ((ok, ab, "我方"), (ab, ok, "对方")):
        layers, why = reply_loop.four_layers(a, b)
        assert side in why and "abstain" in why and all(v["触达率"] is None and v["逐维"] == [] for v in layers.values())
    assert reply_loop.four_layers(ok, ok)[1] is None
    def fake_readout(text, context, k, tag, outdir):
        st1 = {"measurement_status": "abstain", "layers": {}} if tag == "B_draft" else {"layers": {L: [1.0, 0.0, 0.0, 0.0] for L in reply_loop.LAYERS}}
        return {"stage1": st1, "stage2": {"knots": [{"key": "display", "weight": 1.0}], "sampling": {"top1_stable": True, "top1_mode": "display"}, "instrument": {"instrument_hash": "d4cce4c745f3f991"}}}
    monkeypatch.setattr(reply_loop, "readout", fake_readout)
    monkeypatch.setattr(reply_loop, "knot_align", lambda *a, **k: {"alignment_score": 0.5, "resonance": 0, "dissolution": 0.5, "detail": []})
    monkeypatch.setattr(reply_loop, "atoms_alignment", lambda knot, ok, text: {"status": "stub"})
    d = tempfile.mkdtemp(); r, w, o = (os.path.join(d, x) for x in ("r.txt", "w.txt", "o.json"))
    open(r, "w").write("READER"); open(w, "w").write("DRAFT")
    monkeypatch.setattr(sys, "argv", ["reply_loop.py", "--reader", r, "--draft", w, "--context", "t", "--out", o])
    reply_loop.main()
    v = json.load(open(o))["verdict"]
    assert v["need_ok"] is None and v["PASS"] is None and "我方" in v["★四层扣发"] and v["未触达维度"] == [] and v["top1逐原子对齐"]["status"] == "stub"
    import reply_batch
    monkeypatch.setattr(reply_batch, "readout", fake_readout)
    monkeypatch.setattr(reply_batch, "knot_align", lambda *a, **k: {"alignment_score": 0.5, "★usable": False})
    out = reply_batch.phase_b({"tag": "draft", "url": "u", "reader": "R", "context": "c", "draft": "D"}, d)
    assert out["PASS"] is None and out["need_ok"] is None and out["改写指令"] == [] and "我方" in out["★四层扣发"]



def test_reader_gate_stays_unanimous_after_the_mode_gate_study():
    r = json.loads((ROOT / "results/reader_mode_gate.json").read_text(encoding="utf-8"))["result"]
    assert r["verdict"] == "KEEP_UNANIMOUS" and r["by_share"]["0.8"]["rate"] < 0.875          # 众数占比 0.8 的运行与另两次共识只一致 14/21
    src = (ROOT / "scripts/reply_loop.py").read_text(encoding="utf-8")
    assert '_samp.get("top1_stable") is True and layer_status' in src and 'atoms_align["reader_top1_share"]' in src
