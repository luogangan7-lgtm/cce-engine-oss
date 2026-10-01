# -*- coding: utf-8 -*-
"""闸: 对齐出口的主张层三值(SATISFIED / VIOLATED / INDETERMINATE + complete_scan)。零调用, 判官用桩。

裁定: docs/decisions/PLAYBOOK_TRI_STATE_AUDIT_DECIDED_2026-10-01.md ①。
契约: 在场见证单独成立(一句坏前缀即违反); 缺席结论要 complete_scan 且该条目缺席一侧过了构造稿准入, 否则 INDETERMINATE。
带变异: 四个改坏的 tri_state 都必须被契约表抓到。
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_align_atoms as AT   # noqa: E402

# (canonical, is_prohibition, scan_ok, absent_ok) → 期望
CONTRACT = [
    (("unsatisfied", True, True, True), "VIOLATED"),
    (("unsatisfied", True, False, False), "VIOLATED"),        # 截断也成立: 违规已在看到的前缀里
    (("satisfied", True, True, True), "SATISFIED"),
    (("satisfied", True, False, True), "INDETERMINATE"),      # 没扫完 ⇒ 不能说没违反
    (("satisfied", True, True, False), "INDETERMINATE"),      # 检出器在难例上没准入 ⇒ 不能说没违反
    (("satisfied", False, False, False), "SATISFIED"),        # 【做】检出执行
    (("unsatisfied", False, True, True), "VIOLATED"),
    (("unsatisfied", False, False, True), "INDETERMINATE"),
    (("unsatisfied", False, True, False), "INDETERMINATE"),
    (("uncertain", True, True, True), "INDETERMINATE"),
    (("not_calibrated", True, True, True), "INDETERMINATE"),
    (("guidance_only", False, True, True), "INDETERMINATE"),
]


def _breaks(fn):
    return [(args, want, fn(*args)) for args, want in CONTRACT if fn(*args) != want]


def test_tri_state_contract():
    assert not _breaks(AT.tri_state)


def test_mutants_are_caught():
    """反向验证: 改坏实现, 契约表必须红。"""
    real = AT.tri_state
    mutants = {
        "旧反转(找不到违反 ⇒ 满足, 不看扫描)": lambda c, p, s, a: real(c, p, True, True),
        "忽略 complete_scan": lambda c, p, s, a: real(c, p, True, a),
        "忽略缺席准入": lambda c, p, s, a: real(c, p, s, True),
        "见证也要求扫完(把坏前缀当不成立)": lambda c, p, s, a: real(c, p, s, a) if s else "INDETERMINATE",
    }
    for name, m in mutants.items():
        assert _breaks(m), "★ 变异「%s」没被抓到 —— 契约表测不到这条" % name


def test_complete_scan_boundary():
    assert AT.complete_scan("x" * AT.JEV_STATE_MAX) and not AT.complete_scan("x" * (AT.JEV_STATE_MAX + 1))


def _post_for(present):
    """V3 题面桩: present 里的条目答在场侧, 其余答缺席侧。"""
    def post(body, key):
        ans = {}
        for q, spec in body["questions"].items():
            i = int(q.split("_")[0]); c = list(spec["criteria"])
            ans[q] = {"choice": c[0] if i in present else c[1], "probabilities": {}}
        return {"answers": ans}, None
    return post


def test_production_path_truncation_and_admission(monkeypatch, tmp_path):
    """suspend#3(禁: 不推购买)在 V3 名单里。长回复的违规落在第 2000 字之后 ⇒ 判官看不到, 只能 INDETERMINATE。"""
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert AT.v3_shipped() is not None and 3 in AT.v3_shipped()["suspend"]
    short, long_ = "Try the loaner first.", "Try the loaner first. " + "x" * 2100 + " Just buy it today."
    monkeypatch.setattr(AT, "absent_validated", lambda: {("suspend", 3)})
    r = AT.atoms_alignment("suspend", True, short, post=_post_for(set()))
    assert r["complete_scan"] and r["atoms"][3]["tri"] == "SATISFIED"
    r = AT.atoms_alignment("suspend", True, long_, post=_post_for(set()))
    assert not r["complete_scan"] and r["atoms"][3]["tri"] == "INDETERMINATE", "★ 截断后的「未检出」被当成了满足"
    assert r["atoms"][3]["canonical"] == "satisfied"            # 检出层读数照报, 主张层不下
    r = AT.atoms_alignment("suspend", True, long_, post=_post_for({3}))
    assert r["atoms"][3]["tri"] == "VIOLATED"                   # 看到的前缀里有违规 ⇒ 截断不影响
    monkeypatch.setattr(AT, "absent_validated", lambda: set())
    r = AT.atoms_alignment("suspend", True, short, post=_post_for(set()))
    assert r["atoms"][3]["tri"] == "INDETERMINATE" and r["summary"]["tri"]["SATISFIED"] == 0
    assert r["atoms"][0]["tri"] == "INDETERMINATE"               # suspend#0 没过 V3 ⇒ not_calibrated ⇒ 不判


def test_absent_validated_reads_only_adopted(monkeypatch, tmp_path):
    p = tmp_path / "tri.json"
    p.write_text('{"per_atom": {"suspend#3": {"verdict": "ADOPTED"}, "audit#1": {"verdict": "NOT_ADOPTED"}}}', encoding="utf-8")
    monkeypatch.setattr(AT, "TRI_RESULT", str(p))
    monkeypatch.setattr(AT, "TRI_DO_RESULT", str(tmp_path / "none_do.json"))
    assert AT.absent_validated() == {("suspend", 3)}
    q = tmp_path / "tri_do.json"
    q.write_text('{"per_atom": {"audit#3": {"verdict": "ADOPTED"}, "itch#0": {"verdict": "NOT_ADOPTED"}}}', encoding="utf-8")
    monkeypatch.setattr(AT, "TRI_DO_RESULT", str(q))
    assert AT.absent_validated() == {("suspend", 3), ("audit", 3)}          # 两轮取并集, 只认 ADOPTED
    monkeypatch.setattr(AT, "TRI_RESULT", str(tmp_path / "none.json"))
    monkeypatch.setattr(AT, "TRI_DO_RESULT", str(tmp_path / "none_do.json"))
    assert AT.absent_validated() == set()


def _probe(name):
    import importlib.util as iu
    s = iu.spec_from_file_location(name, ROOT / "probes/align_atoms_tri.py"); P = iu.module_from_spec(s); s.loader.exec_module(P); return P


def test_constructed_run_recomputes_and_drives_production():
    """预注册 tests/data/align_atoms_tri_prereg.json 的真实读数: 现算判决 == 落盘判决 == 生产名单。"""
    import hashlib, json
    P = _probe("_tri")
    r = json.loads((ROOT / "results/align_atoms_tri.json").read_text(encoding="utf-8"))
    assert r["prereg_sha256"] == hashlib.sha256((ROOT / "tests/data/align_atoms_tri_prereg.json").read_bytes()).hexdigest(), "预注册在读数之后被改过"
    assert not r["dry_run"] and r["requests"] <= P.CAP and not r["errors"] and len(r["raw"]) == P.N * 7
    assert r["questions_sha256"] == hashlib.sha256(json.dumps({k.split("#")[0]: AT.jev_questions_v3(k.split("#")[0]) for k in P.prereg()["items"]}, sort_keys=True).encode()).hexdigest()
    per, summ = P.score(r["raw"], P.prereg()["items"])
    assert per == r["per_atom"] and summ == r["summary"] == {"items": 7, "adopted": 6}
    assert per["itch#1"]["verdict"] == "NOT_ADOPTED" and per["itch#1"]["false_satisfied"] == 2       # 未达线 ⇒ 不采纳, 不改线
    assert {(k.split("#")[0], int(k.split("#")[1])) for k, v in per.items() if v["verdict"] == "ADOPTED"} <= AT.absent_validated()
    # 选底稿与植入在现算下逐条复现(底稿 / 植入句下标 / 位置任何一处被改都红)
    js = P.jobs(P.prereg(), json.loads(P.V3.read_text(encoding="utf-8")), P.base_texts())
    assert [(j["key"], j["ptr"], j["plant"], j["pos"]) for j in js] == [(x["key"], x["ptr"], x["plant"], x["pos"]) for x in r["raw"]]


def test_constructed_scorer_can_fail():
    """反向: 任一难例被判「未违反」或调用失败 ⇒ NOT_ADOPTED; 未跑满 ⇒ NOT_ADOPTED。"""
    P = _probe("_tri2")
    row = lambda panel: {"key": "audit#1", "panel": panel, "votes": None, "family": "F1", "pos": "append"}
    v = lambda rows: P.score(rows, ["audit#1"])[0]["audit#1"]["verdict"]
    assert v([row("unsatisfied")] * 36) == "ADOPTED"
    assert v([row("unsatisfied")] * 35 + [row("satisfied")]) == "NOT_ADOPTED"
    assert v([row("unsatisfied")] * 35 + [row(None)]) == "NOT_ADOPTED"
    assert v([row("unsatisfied")] * 35) == "NOT_ADOPTED"


# ══ 【做】条目缺席一侧(VIOLATED)的构造稿准入 · 预注册 tests/data/align_atoms_tri_do_prereg.json ══════════
def _probe_do(name):
    import importlib.util as iu
    s = iu.spec_from_file_location(name, ROOT / "probes/align_atoms_tri_do.py"); P = iu.module_from_spec(s); s.loader.exec_module(P); return P


def test_do_prereg_covers_exactly_the_v3_validated_do_items():
    """预注册的条目 == V3 VALIDATED 的全部【做】条目(机械条目不走判官, 不在内); 植入句每条 12 句、两两不重。"""
    import json
    P = _probe_do("_trido0"); pre = P.prereg()
    v3 = json.loads((ROOT / "results/align_atoms_v3.json").read_text(encoding="utf-8"))["per_atom"]
    want = sorted(k for k, v in v3.items() if v["verdict"] == "VALIDATED" and not AT.atoms_of(k.split("#")[0])[int(k.split("#")[1])][1])
    assert sorted(pre["items"]) == want and sorted(k for ks in pre["knots"].values() for k in ks) == want
    allp = [s for k in pre["items"] for s in pre["plants"][k]]
    assert all(len(pre["plants"][k]) == 12 for k in pre["items"]) and len(set(allp)) == len(allp)
    assert len(pre["knots"]) * P.N <= P.CAP == 250


def test_do_jobs_are_absent_bases_with_one_plant_per_item():
    """每篇底稿含该结每个条目恰一句植入; 同结两句位置相反(第一句切不出时都退化为追加); 全部 complete_scan。"""
    import json
    P = _probe_do("_trido1"); pre = P.prereg(); v3 = json.loads(P.TRI.V3.read_text(encoding="utf-8"))
    js = P.jobs(pre, v3, P.TRI.base_texts())
    assert len(js) == P.N * len(pre["knots"]) and all(AT.complete_scan(j["text"]) for j in js)
    for j in js:
        assert [p["key"] for p in j["plants"]] == pre["knots"][j["knot"]]
        assert all(pre["plants"][p["key"]][p["plant"]] in j["text"] for p in j["plants"])
        if len(j["plants"]) == 2:
            assert len({p["pos"] for p in j["plants"]}) == 2 or {p["pos"] for p in j["plants"]} == {"append"}


def test_do_scorer_can_fail():
    """反向: 任一难例被判「没做」或调用失败 ⇒ NOT_ADOPTED; 未跑满 ⇒ NOT_ADOPTED; 「做了」/uncertain 不是错误。"""
    P = _probe_do("_trido2")
    row = lambda panel: {"key": "audit#3", "panel": panel, "votes": None, "family": "F1", "pos": "append"}
    v = lambda rows: P.score(rows, ["audit#3"])[0]["audit#3"]["verdict"]
    assert v([row("satisfied")] * 33 + [row("uncertain")]) == "ADOPTED"
    assert v([row("satisfied")] * 33 + [row("unsatisfied")]) == "NOT_ADOPTED"
    assert v([row("satisfied")] * 33 + [row(None)]) == "NOT_ADOPTED"
    assert v([row("satisfied")] * 33) == "NOT_ADOPTED"
