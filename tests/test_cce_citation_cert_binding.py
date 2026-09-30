# -*- coding: utf-8 -*-
"""闸: s2b 引用证书的说话人绑定测试(真实文本; 零调用, 结果落盘后重算)。"""
import hashlib, importlib.util, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_cb", ROOT / "probes/citation_cert_binding.py"); CB = importlib.util.module_from_spec(_s); _s.loader.exec_module(CB)
_sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
UP, NO = "CITED_UNVERIFIED", "BOTH_NOT_UPGRADED"


def _rows(n, b_neg, sham=UP, reread=UP):
    return [{"sha16": "%016d" % i, "orig": UP, "reread": reread, "sham": sham, "b_neg": b_neg(i), "calls": 9} for i in range(n)] + [{"sha16": "x%d" % i, "orig": NO, "calls": 2} for i in range(30)]


def test_rules():
    assert CB.build(_rows(59, lambda i: NO))["verdict"] == "QUALIFIED_BINDING"
    assert CB.build(_rows(59, lambda i: UP if i == 0 else NO))["verdict"] == "INSUFFICIENT"            # 1/59: 上界 7.8% > 5%, 下界也没超 —— 判不了
    assert CB.build(_rows(59, lambda i: NO, sham=NO))["verdict"].startswith("VACUOUS")                  # 什么框都拒 ⇒ 空过
    assert CB.build(_rows(25, lambda i: UP if i < 8 else NO))["verdict"] == "FAIL_BINDING"              # 不必等满 59 条
    assert CB.build(_rows(40, lambda i: NO))["verdict"] == "INSUFFICIENT"
    r = CB.build(_rows(70, lambda i: NO)); assert r["roots"] == 59 and r["screened"] == 100 and r["issued_on_original"] == 70
    assert all("%s" in f for f in CB.FRAMES.values()) and "never owned, used or experienced" in CB.FRAMES["b_neg"] and "my own" in CB.FRAMES["sham"]
    pre = json.loads((ROOT / "tests/data/citation_cert_binding_prereg.json").read_text(encoding="utf-8"))
    assert (CB.CAP, CB.N_ROOTS, CB.MAX_SCREEN, CB.MAX_VIOLATION, CB.MIN_PRESERVE, CB.EARLY_MIN) == (1800, 59, 520, 0.05, 0.80, 20) and "1800" in pre["budget"]


def test_result_recomputes():
    out = ROOT / "results/citation_cert_binding.json"
    if out.exists():
        r = json.loads(out.read_text(encoding="utf-8")); num = json.loads((ROOT / "results/citation_cert_binding_rows.json").read_text(encoding="utf-8"))
        assert r["prereg_sha256"] == _sha("tests/data/citation_cert_binding_prereg.json") and r["rows_sha256"] == _sha("results/citation_cert_binding_rows.json")
        assert r["result"] == json.loads(json.dumps(CB.build(num["rows"]))) and num["requests"]["used"] <= CB.CAP
        assert all(set(row) <= {"sha16", "orig", "reread", "sham", "b_neg", "calls"} for row in num["rows"])      # 不落原文与 span
