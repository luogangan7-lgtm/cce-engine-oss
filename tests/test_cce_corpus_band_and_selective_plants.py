# -*- coding: utf-8 -*-
"""两个无金标收尾研究的闸: 语料抽样上的散布闸扣发率、s0 两个 WEAK 面的归因。零调用; 结果落盘后从原始读数重算。"""
import hashlib, importlib.util, json, pathlib, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
SP = _load("_sp", "probes/s0_selective_plants.py")
_sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def test_band_rule_is_11_to_16_of_100():
    CB = _load("_cb", "probes/within_js_corpus_band.py")
    assert [k for k in range(101) if CB.verdict(k, 100)["verdict"] == "IN_BAND"] == list(range(11, 17))
    assert CB.verdict(0, 100)["verdict"] == "OUT_OF_BAND" and CB.verdict(40, 100)["verdict"] == "OUT_OF_BAND" and CB.verdict(8, 100)["verdict"] == "STRADDLES"
    assert not [k for k in range(61) if (lambda c: c[0] >= 0.05 and c[1] <= 0.25)(CB.MON.clopper_pearson(k, 60, 0.010))]   # 生产流 n=60 那次查看判不了带内
    pre = json.loads((ROOT / "tests/data/within_js_corpus_band_prereg.json").read_text(encoding="utf-8"))
    assert pre["decision"]["n"] == CB.N == 100 and CB.BAND == (0.05, 0.25) and CB.CAP == 2150
    out = ROOT / "results/within_js_corpus_band.json"
    if out.exists():
        r = json.loads(out.read_text(encoding="utf-8")); num = json.loads((ROOT / "results/within_js_corpus_band_numbers.json").read_text(encoding="utf-8"))
        assert r["prereg_sha256"] == _sha("tests/data/within_js_corpus_band_prereg.json") and r["numbers_sha256"] == _sha("results/within_js_corpus_band_numbers.json")
        assert r["result"] == CB.build(num["rows"]) and num["requests"]["used"] <= CB.CAP
        for arm in r["result"].values():
            assert len({x for x in [row["sha16"] for row in num["rows"]]}) == len(num["rows"])       # 文本不重复


def _rows(sel_shift, off_shift, ent_shift):
    rows = []
    for n in range(12):
        ptr = "r%d" % n
        def P(**over):
            p = {g: {"基": 1.0} for g in list(SP.OFF) + ["情绪余温"]}; p.update(over); return p
        rows.append({"ptr": ptr, "kind": "baseline", "facet": None, "value": None, "w": None, "probs": P()})
        for w in (0, 1): rows.append({"ptr": ptr, "kind": "sham", "facet": None, "value": None, "w": w, "probs": P()})
        for f, vals in SP.SELECTIVE.items():
            g = next(x for x in SP.OFF if x != f)
            for v in vals:
                for w in (0, 1):
                    rows.append({"ptr": ptr, "kind": "selective", "facet": f, "value": v, "w": w,
                                 "probs": P(**{f: {v: sel_shift, "基": 1 - sel_shift}, g: {"基": 1 - off_shift, "别": off_shift}})})
        for (f, v), (g, gv) in SP.ENTAILING.items():
            for w in (0, 1):
                rows.append({"ptr": ptr, "kind": "entailing", "facet": f, "value": v, "w": w, "probs": P(**{g: {gv: ent_shift, "基": 1 - ent_shift}})})
    return rows


def test_selective_plant_rules():
    assert len(SP.jobs([("x", "")])) == 19 and len(SP.roots()) == SP.N_ROOTS == 100 and len({p for p, _ in SP.roots()}) == 100
    good = SP.analyse(_rows(0.8, 0.0, 0.5))
    assert {f: v["verdict"] for f, v in good["selective"].items()} == {"进程位置": "SELECTIVE", "触发事件": "SELECTIVE"}
    assert all(v["verdict"] == "NESTED" for v in good["entailing"].values()) and good["n_roots_complete"] == 12
    assert {v["verdict"] for v in SP.analyse(_rows(0.8, 0.3, 0.1))["selective"].values()} == {"CROSS_SENSITIVE"}     # 邻面跟着动 ⇒ 串扰
    bad = SP.analyse(_rows(0.3, 0.0, 0.1))
    assert {v["verdict"] for v in bad["selective"].values()} == {"UNRESPONSIVE"} and {v["verdict"] for v in bad["entailing"].values()} == {"NOT_SHOWN"}
    used = {p for s in (0, 20, 40, 60, 80, 100, 120) for p, _ in SP.V5.natural(s)}
    assert not used & {p for p, _ in SP.roots()}                                  # 根文本此前没进过任何一轮
    for f, vals in SP.SELECTIVE.items():                                          # 选择性句子是新写的, 不是原植入句
        assert not {s for ss in vals.values() for s in ss} & {s for ss in SP.pv.PLANTS[f].values() for s in ss}
    out = ROOT / "results/s0_selective_plants.json"
    if out.exists():
        r = json.loads(out.read_text(encoding="utf-8"))
        assert r["prereg_sha256"] == _sha("tests/data/s0_selective_plants_prereg.json") and not r["dry_run"] and r["requests"] <= SP.CAP
        assert r["result"] == SP.analyse(r["raw"]) and r["root_pointers"] == [p for p, _ in SP.roots()]
