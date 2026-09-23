# -*- coding: utf-8 -*-
"""闸: 生产 s2 接入资格层诊断字段(2026-09-23 授权代定)。零调用(stage2 用桩)。
守: 字段形状 · 状态恒候选 · citable 恒 False · evidence_quote 逐字核真假两向 · 原有 s2 字段不变 · is_citable_as_confirmed 有生产调用方。"""
import ast, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as fr

TEXT = "Settled on the Oticon after two fittings. Been wearing it daily since March and it gets me through a full day."


def _run(quote):
    with tempfile.TemporaryDirectory() as tmp:
        tf = pathlib.Path(tmp) / "t.txt"; tf.write_text(TEXT, encoding="utf-8")
        ctx = {"text_file": str(tf), "outdir": tmp, "context": "c",
               "cce": {"stage2": {"knots": [{"key": "display", "weight": 1.0, "evidence_quote": quote, "playbook": "p"}],
                                  "sampling": {"n_ok": 5, "top1_stable": True, "top1_mode_share": 1.0, "top1_mode": "display", "top1_draws": ["display"] * 5, "max_range": 0.1, "per_knot": {}},
                                  "intensity": {}, "families": {}, "drive_brake": {}, "instrument": {"instrument_hash": "x"}}}}
        fr.MANIFEST.clear(); fr.s2(ctx); return fr.MANIFEST["s2_knots"]


def test_field_shape_state_candidate_and_never_citable():
    out = _run("Been wearing it daily since March")
    lq = out["label_qualification"]
    assert lq["knot"] == "display" and lq["state"] == "UNCONFIRMED_CANDIDATE" and lq["citable_as_confirmed"] is False and lq["evidence_quote_verbatim"] is True
    assert "无法升格" in lq["★协议缺口"] and "不改判决" in lq["★协议缺口"] and out["knots"] == [["display", 1.0]] and out["playbook_primary"] == "p"   # 原有字段不变


def test_verbatim_check_is_real_and_empty_quote_is_false():
    assert _run("Been wearing it every single day")["label_qualification"]["evidence_quote_verbatim"] is False
    assert _run("")["label_qualification"]["evidence_quote_verbatim"] is False


def test_is_citable_as_confirmed_now_has_a_production_caller():
    tree = ast.parse((ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"))
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"qualify", "is_citable_as_confirmed"} <= calls
    assert "label_qualification" in json.dumps(_run("x"), ensure_ascii=False)
