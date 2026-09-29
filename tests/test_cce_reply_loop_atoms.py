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
    assert seen == {"knot": "pain_seek", "ok": True} and v["top1逐原子对齐(v4.1)"] == {"status": "stub"}


def test_unstable_top1_is_not_usable(monkeypatch):
    seen, _ = _run(monkeypatch, {"top1_stable": None, "top1_mode": "pain_seek"})
    assert seen["ok"] is False
