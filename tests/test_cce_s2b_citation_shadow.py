# -*- coding: utf-8 -*-
"""闸: 引用证书影子段接线(2026-09-24 owner「接吧」, 预注册 v3 ADOPT_SHADOW)。零调用: 证书调用用桩。
接线闸五条: ① 开关关 ⇒ s2 产出与接线前同形同值且零调用 ② 开关开 + 两张桩证书一致 ⇒ ③′; 不一致 ⇒ 候选并写 DISAGREE ③ citable_as_confirmed 恒 False
④ 非 display 或 top1_stable 非 True ⇒ 不发证书(零调用) ⑤ 产物无原文 span(只 sha16)。
另: 生产模块的验证器与 r2 探针**逐字相同**(AST 切片比对), DISC/PROMPT 相等, prompt_v3 sha == 预注册 v3。"""
import ast, hashlib, importlib.util, inspect, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as fr, cce_citation_certificate as C
_s = importlib.util.spec_from_file_location("_r2g", ROOT / "probes/extractor_counterexample_run_r2.py"); r2 = importlib.util.module_from_spec(_s); _s.loader.exec_module(r2)
PRE3 = json.loads((ROOT / "tests/data/citation_certificate_production_prereg_v3.json").read_text(encoding="utf-8"))
TEXT = "Settled on the Oticon after two fittings. Been wearing the Oticon daily since March and it gets me through a full day."
GOOD = json.dumps({"supported": True, "evidence": [{"span": "gets me through a full day", "supports": "A", "object": "Oticon", "increment_kind": "数据"}, {"span": "Been wearing the Oticon daily", "supports": "B", "object": "Oticon", "increment_kind": None}]}, ensure_ascii=False)
REFUSE = json.dumps({"supported": False, "evidence": [], "why_not": "no"}, ensure_ascii=False)


def _run_s2(monkeypatch, top1, key="display", on=True, answers=None):
    calls = []
    def fake(prompt): calls.append(prompt); return (answers[len(calls) - 1] if answers else GOOD), {}
    monkeypatch.setattr(C, "_call_model", fake)
    if on: monkeypatch.setenv("CCE_CITATION_CERT", "1")
    else: monkeypatch.delenv("CCE_CITATION_CERT", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        tf = pathlib.Path(tmp) / "t.txt"; tf.write_text(TEXT, encoding="utf-8")
        ctx = {"text_file": str(tf), "outdir": tmp, "context": "c",
               "cce": {"stage2": {"knots": [{"key": key, "weight": 1.0, "evidence_quote": "daily", "playbook": "p"}],
                                  "sampling": {"n_ok": 5, "top1_stable": top1, "top1_mode_share": 1.0, "top1_mode": key, "top1_draws": [key] * 5, "max_range": 0.1, "per_knot": {}},
                                  "intensity": {}, "families": {}, "drive_brake": {}, "instrument": {"instrument_hash": "x"}}}}
        fr.MANIFEST.clear(); fr.s2(ctx); out = fr.MANIFEST["s2_knots"]
        s2b = json.loads((pathlib.Path(tmp) / "s2b_citation.json").read_text(encoding="utf-8")) if (pathlib.Path(tmp) / "s2b_citation.json").exists() else None
    return out, s2b, calls


def test_1_switch_off_is_identical_to_before_and_zero_calls(monkeypatch):
    out, s2b, calls = _run_s2(monkeypatch, True, on=False)
    lq = out["label_qualification"]
    assert calls == [] and s2b is None and set(lq) == {"knot", "state", "citable_as_confirmed", "evidence_quote_verbatim", "why", "★协议缺口"}
    assert lq["state"] == "UNCONFIRMED_CANDIDATE" and lq["citable_as_confirmed"] is False


def test_2_switch_on_consistent_certs_upgrade_and_disagree_stays_candidate(monkeypatch):
    out, s2b, calls = _run_s2(monkeypatch, True)
    lq = out["label_qualification"]; assert len(calls) == 2 and lq["state"] == "CITED_UNVERIFIED" and lq["s2b_decision"] == "CITED_UNVERIFIED" and len(lq["s2b_witness_sha16"]) == 1 and s2b["decision"] == "CITED_UNVERIFIED"
    out, s2b, calls = _run_s2(monkeypatch, True, answers=[GOOD, REFUSE])
    lq = out["label_qualification"]; assert lq["state"] == "UNCONFIRMED_CANDIDATE" and lq["s2b_decision"] == "DISAGREE" and s2b["decision"] == "DISAGREE"


def test_3_citable_as_confirmed_always_false(monkeypatch):
    for answers in (None, [GOOD, REFUSE], [REFUSE, REFUSE]):
        out, s2b, _ = _run_s2(monkeypatch, True, answers=answers); assert out["label_qualification"]["citable_as_confirmed"] is False and s2b["citable_as_confirmed"] is False


def test_4_non_display_or_unstable_top1_sends_nothing(monkeypatch):
    for key, top1 in (("reward", True), ("display", False), ("display", None)):
        out, s2b, calls = _run_s2(monkeypatch, top1, key=key); assert calls == [] and s2b is None and "s2b_decision" not in out["label_qualification"], (key, top1)


def test_5_product_has_no_text_only_sha16(monkeypatch):
    out, s2b, _ = _run_s2(monkeypatch, True)
    s = json.dumps(s2b, ensure_ascii=False) + json.dumps(out["label_qualification"], ensure_ascii=False)
    for frag in ("gets me through", "Been wearing", "Oticon", "span", "object"): assert frag not in s.replace("no_span", ""), frag
    assert all(len(w) == 16 for c in s2b["certs"] for w in c["witness"]) and all(set(c) == {"outcome", "state", "sec", "witness", "n_evidence", "reason_codes", "repaired", "calls"} for c in s2b["certs"])


def test_verifier_is_verbatim_copy_of_r2_and_prompt_pinned():
    for name in ("normalize_about", "_clean_kind", "_parse", "classify_refusal", "declared_objects", "_granularity", "_judge"):
        assert inspect.getsource(getattr(C, name)) == inspect.getsource(getattr(r2, name)), name
    for const in ("CONJ", "REFUSED_RIGHT", "REFUSED_OTHER", "MALFORMED", "COVERAGE_FAIL", "GRANULARITY", "DISTINCT", "UPGRADED", "ADJUDICATED", "ISSUED", "ANCHORS"):
        assert getattr(C, const) == getattr(r2, const), const
    assert C.DISC == r2.DISC and C.PROMPT == r2.PROMPT and tuple(C.kind_menu()) == __import__("cce_label_qualification").INCREMENT_KINDS
    assert hashlib.sha256(C.prompt_v3("").encode()).hexdigest()[:16] == PRE3["★★★协议 v3(由闸现算比对)"]["prompt_sha(模板, text 置空)"]
    src = (ROOT / "scripts/cce_full_run.py").read_text(encoding="utf-8"); assert "from probes" not in src and "import probes" not in src


def test_repair_reask_bounded_to_two_calls(monkeypatch):
    bad = GOOD.replace('"数据"', '"数据/使用细节"'); answers = [bad, GOOD, bad, GOOD]   # 每张: 首答格式错 → 修复 → 好
    out, s2b, calls = _run_s2(monkeypatch, True, answers=answers)
    assert len(calls) == 4 and all(c["calls"] == 2 and c["repaired"] for c in s2b["certs"]) and out["label_qualification"]["s2b_calls"] == 4 and out["label_qualification"]["state"] == "CITED_UNVERIFIED"
