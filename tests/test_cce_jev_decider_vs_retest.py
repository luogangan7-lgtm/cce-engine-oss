# -*- coding: utf-8 -*-
"""闸: Decider vs Jev vs MiniMax 无金标对比(预注册 tests/data/jev_decider_vs_retest_prereg.json)。零 API。
守: ① 预注册冻结项与现算一致(题目逐面 sha / 输入集 sha / 分析脚本 sha / 阈值) ② 判决规则是真闸: 合成臂各自落到预期档
③ 前置(复跑/题目/切片)能观察到失败 ④ 结果文件存在时: 由归档现算一致、无原文、带不得据此说。"""
import collections, hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_jvr", ROOT / "probes/jev_decider_vs_retest.py"); X = importlib.util.module_from_spec(_s); _s.loader.exec_module(X)
PRE = json.loads(X.PRE.read_text(encoding="utf-8"))
ARMS = X.load_arms()
MODEL = PRE["★面"]["模型读"]
sha = X.sha


def _synthetic(src):
    """D := 某臂的读数(或函数), 概率 = 选中 0.9 其余均分。"""
    D, P = {}, {}
    for ptr in ARMS["J2"]:
        D[ptr], P[ptr] = {}, {}
        for k in MODEL:
            f = X.FACETS[k]; cands = list(f["values"]) + ([] if "未知" in f["values"] else ["未知"])
            lab = src(ptr, k) if callable(src) else ARMS[src][ptr].get(k)
            lab = lab if lab in cands else "未知"
            D[ptr][k] = lab; P[ptr][k] = {c: (0.9 if c == lab else 0.1 / (len(cands) - 1)) for c in cands}
    return D, P


def test_prereg_frozen_items_recompute():
    sys.path.insert(0, str(ROOT / "scripts"))
    cq = importlib.import_module("cce_s0_jev").jev_questions(list(X.FACETS.values()))
    for k, h in PRE["★输入与题目(冻结)"]["题目逐面 sha(含候选顺序)"].items():
        assert sha(json.dumps(cq[k], ensure_ascii=False)) == h, k
    suite = [json.loads(l) for l in X.SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = [it for it in suite if "text_ref" in it and not it["item_id"].startswith("rep-")]
    assert len(items) == 42 and sha(json.dumps([[it["text_ref"]["file"], it["text_ref"]["line_index"], it["text_ref"]["line_sha256"]] for it in items], ensure_ascii=False)) == PRE["★输入与题目(冻结)"]["输入集 sha"]
    pr = json.loads((ROOT / "tests/data/real_corpus_pilot_prereg.json").read_text(encoding="utf-8"))
    frozen = [pr[k] for k in pr if "冻结输入集" in k][0]["items"]
    assert [(it["text_ref"]["file"], it["text_ref"]["line_index"], it["text_ref"]["line_sha256"]) for it in items] == [(i["file"], i["line_index"], i["sha256"]) for i in frozen]
    reps = [it for it in suite if it["item_id"].startswith("rep-")]
    assert [it["text_ref"]["line_index"] for it in reps] == [frozen[i]["line_index"] for i in range(40) if i % 4 == 0]
    assert PRE["★分析脚本(冻结)"]["sha256"] == sha((ROOT / "probes/jev_decider_vs_retest.py").read_bytes()), "分析脚本在冻结后被改 —— 必须在结果里登记原因"
    assert PRE["★臂"]["★不新调付费接口"] and PRE["★★★判决规则(测量前冻结)"]["数值"]["replaceable_max_d"] == 4


def test_verdict_rules_are_real_gates():
    same = X.analyse(*_synthetic("J2"), ARMS, PRE, {"pass": True})
    assert all(v == "可替代" for v in same["verdicts"].values()), same["verdicts"]            # D == J2 ⇒ 每面可替代
    maj = {k: collections.Counter(ARMS["J2"][p].get(k) for p in ARMS["J2"]).most_common(1)[0][0] for k in MODEL}
    const = X.analyse(*_synthetic(lambda p, k: maj[k]), ARMS, PRE, {"pass": True})
    assert all(v != "可替代" for v in const["verdicts"].values()), const["verdicts"]            # 常数填充 net ≤ 0 ⇒ 不许可替代
    mm = X.analyse(*_synthetic("M2"), ARMS, PRE, {"pass": True})
    assert "不同读者" in mm["verdicts"].values() and mm["overall"].startswith("整体不可替代"), mm["verdicts"]
    bad = X.analyse(*_synthetic("J2"), ARMS, PRE, {"pass": False})
    assert bad["overall"].startswith("前置不成立")
    s = same["per_facet"]["身体状态"]
    assert s["pairs"]["D~J2"]["d"] == 0 and s["pairs"]["J1~J2"]["kappa_boot"]["ci95"] is not None and s["zero_baseline"]["J2"]["net_gain"] > 0
    assert same["情绪余温_structural"]["M1"]["violations"] == 42 and same["情绪余温_structural"]["J1"]["violations"] == 12   # 与复测存档一致


def test_determinism_check_observes_failure():
    def row(iid, q, p, rs="x"):
        return {"item_id": iid, "question_id": q, "candidate_ids": ["a", "b"], "probabilities": p, "selected_candidate": "a" if p[0] >= p[1] else "b", "identities": {"row_sha256": rs}}
    ok = [row("x:1", "q", [0.7, 0.3]), row("rep-x:1", "q", [0.7, 0.3])]
    w, _ = X.determinism(ok, [], {"x:1": "p", "rep-x:1": "p"}, [], 1e-5); assert w["pass"] and w["pairs"] == 1
    drift = [row("x:1", "q", [0.7, 0.3]), row("rep-x:1", "q", [0.7 + 2e-5, 0.3 - 2e-5])]
    w, _ = X.determinism(drift, [], {}, [], 1e-5); assert not w["pass"]
    flip = [row("x:1", "q", [0.51, 0.49]), row("rep-x:1", "q", [0.49, 0.51])]
    w, _ = X.determinism(flip, [], {}, [], 1e-5); assert not w["pass"] and w["top1_diff"] == 1
    none = [row("x:1", "q", [0.7, 0.3])]
    w, _ = X.determinism(none, [], {}, [], 1e-5); assert not w["pass"]                     # 没有复跑对 ≠ 通过


def test_result_recomputes_from_archive_and_has_no_text():
    if not X.OUT.exists():
        return
    r = json.loads(X.OUT.read_text(encoding="utf-8"))
    run_dir = ROOT / r["run"]["archive"]
    D, P, preds, report, suite, ptr_of = X.load_decider(run_dir)
    got = X.analyse(D, P, ARMS, PRE, r["★前置"]["同 run 复跑"])
    for k in ("verdicts", "overall", "per_facet", "情绪余温_structural", "n_items"):
        assert got[k] == r[k], k
    assert r["prereg_sha256"] == sha(X.PRE.read_bytes()) and r["★不得据此说"] == PRE["★★★不得据此说"]
    if r["analysis_script_sha256"] != r["analysis_script_sha256_at_freeze"]:
        assert r.get("★分析脚本冻结后改动说明"), "分析脚本冻结后改过却没登记原因"
    blob = " ".join(json.dumps(r, ensure_ascii=False).split())
    from experiments.jev.report import text_leaks  # noqa: E402
    from experiments.jev.run_suite import suite_texts  # noqa: E402
    hits = text_leaks(blob, suite_texts(suite))
    assert hits == 0, f"{hits} 条输入原文出现在结果里"


sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"): fn()
    print("test_cce_jev_decider_vs_retest: OK")
