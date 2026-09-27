# -*- coding: utf-8 -*-
"""闸: Decider 弃权原因 2×2 探针(预注册 tests/data/jev_decider_probe_prereg.json)。零 API。
守: ① 预注册冻结项现算一致(脚本 sha / 译表 sha / 输入集 / suite 组成 / 锚点来源) ② 归因规则是真闸(合成格子各落预期档)
③ 前置能观察到失败(真跑一次同形 suite) ④ 结果文件存在时由归档现算一致且无原文。"""
import copy, hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
_s = importlib.util.spec_from_file_location("_jdp", ROOT / "probes/jev_decider_probe.py"); P = importlib.util.module_from_spec(_s); _s.loader.exec_module(P)
from experiments.jev.compile_context import load_task, load_taxonomy, to_zh  # noqa: E402
PRE = json.loads(P.PRE.read_text(encoding="utf-8"))
TASK = load_task("s0_context.v3", load_taxonomy())
ARMS = P.CMP.load_arms()
CELL0 = ROOT / PRE["★臂"]["格子 0 归档"]


def _cell0():
    suite0 = [json.loads(l) for l in P.CELL0_SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    ptr0 = {it["item_id"]: "%s:%d" % (it["text_ref"]["file"], it["text_ref"]["line_index"]) for it in suite0 if "text_ref" in it and not it["item_id"].startswith("rep-")}
    p0, _ = P._preds(CELL0); c = {}
    for p in p0:
        if p["item_id"] in ptr0:
            c.setdefault(ptr0[p["item_id"]], {})[p["question_id"]] = dict(p, label_zh=p["selected_candidate"])
    return c


def _rev(c):
    return {p: {k: dict(r, candidate_ids=r["candidate_ids"][::-1], probabilities=r["probabilities"][::-1], raw_candidate_logits=r["raw_candidate_logits"][::-1]) for k, r in fs.items()} for p, fs in c.items()}


def _en(c):
    back = lambda k: {z: e for z, e in TASK["translation_en"]["facets"][k]["values"].items()} | {"未知": TASK["translation_en"]["unknown_option"]["id"]}
    return {p: {k: dict(r, candidate_ids=[back(k)[i] for i in r["candidate_ids"]]) for k, r in fs.items()} for p, fs in c.items()}


def test_prereg_frozen_items_recompute():
    assert PRE["★分析脚本(冻结)"]["sha256"] == P.sha((ROOT / "probes/jev_decider_probe.py").read_bytes()), "分析脚本冻结后被改 —— 要登记"
    assert P.sha(json.dumps(TASK["translation_en"], ensure_ascii=False, sort_keys=True)) == PRE["★冻结"]["译表 sha"]
    cmp_pre = json.loads((ROOT / "tests/data/jev_decider_vs_retest_prereg.json").read_text(encoding="utf-8"))
    assert PRE["★冻结"]["输入集 sha"] == cmp_pre["★输入与题目(冻结)"]["输入集 sha"]
    suite = [json.loads(l) for l in P.SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    main = [json.loads(l) for l in P.CELL0_SUITE.read_text(encoding="utf-8").splitlines() if l.strip()]
    main = [it for it in main if "text_ref" in it and not it["item_id"].startswith("rep-")]
    for prefix in ("rev-zh", "orig-en", "rev-en"):
        cell = [it for it in suite if it["item_id"].startswith(prefix + ":")]
        assert [it["text_ref"] for it in cell] == [it["text_ref"] for it in main] and all(it["question_variant"] == prefix for it in cell)
    anchors = [it for it in suite if it["item_id"].startswith("anchor:")]
    assert [it["text_ref"] for it in anchors] == [main[0]["text_ref"], main[4]["text_ref"]] and all(it["question_variant"] == "orig-zh" for it in anchors)
    man = json.loads((ROOT / "experiments/jev/suites/s0-probe-v1.manifest.json").read_text(encoding="utf-8"))
    assert man["prereg_sha256"] == P.sha(P.PRE.read_bytes()) and man["task"] == "s0_context.v3" and man["policy"] == "cpu_probe.json"
    assert PRE["★臂"]["新付费调用"] == 0 and CELL0.is_dir()


def test_attribution_rules_are_real_gates():
    c0 = _cell0()
    same = P.analyse({"0": c0, "a": _rev(c0), "b": _en(c0), "c": _rev(_en(c0))}, ARMS, PRE, TASK)
    for k in PRE["★主要检验族"]["面"]:
        for fac in ("position", "language"):
            assert same["per_facet"][k]["effects"][fac]["attribution"] == "该因素在可测尺度上不是原因", (k, fac)
        assert same["per_facet"][k]["order_sensitivity"]["class"] == {"zh": "顺序不敏感", "en": "顺序不敏感"} and not same["per_facet"][k]["interaction"]["claimed"]
        assert len({v["verdict"] for v in same["per_facet"][k]["replaceability_per_cell"].values()}) == 1
    fixed = copy.deepcopy(c0)
    for ptr, fs in fixed.items():
        for k, r in fs.items():
            f = P.FACETS[k]; j = P.RT.norm(ARMS["J1"][ptr].get(k), f)
            if P.RT.norm(r["label_zh"], f) == "未知" and j != "未知":
                r["label_zh"] = j
    lang = P.analyse({"0": c0, "a": _rev(c0), "b": _en(fixed), "c": _rev(_en(fixed))}, ARMS, PRE, TASK)
    for k in ("进程位置", "关系位置", "资源状态"):
        e = lang["per_facet"][k]["effects"]
        assert e["language"]["attribution"] == "该因素可以解释多数过量弃权" and e["language"]["holm_reject"], (k, e["language"])
        assert e["position"]["attribution"] == "该因素在可测尺度上不是原因"
    assert lang["per_facet"]["触发事件"]["effects"]["language"]["attribution"] == "该因素在可测尺度上不是原因"   # 触发事件 D 从不选 未知


def test_order_sensitivity_classes_use_registered_numbers():
    c0 = _cell0(); R = PRE["★★★判决规则(测量前冻结)"]["数值"]
    flipped = copy.deepcopy(c0); n = 0
    for ptr in sorted(flipped):
        if n >= R["order_sensitive_min_d"]: break
        r = flipped[ptr]["进程位置"]; r["label_zh"] = next(v for v in P.FACETS["进程位置"]["values"] if v != P.RT.norm(r["label_zh"], P.FACETS["进程位置"])); n += 1
    out = P.analyse({"0": c0, "a": _rev(flipped), "b": _en(c0), "c": _rev(_en(c0))}, ARMS, PRE, TASK)
    assert out["per_facet"]["进程位置"]["order_sensitivity"]["zh d(0,a)"] == R["order_sensitive_min_d"]
    assert out["per_facet"]["进程位置"]["order_sensitivity"]["class"]["zh"] == "顺序敏感"


def _fake_probe_run(tmp_path):
    from experiments.jev import run_suite as RS
    from experiments.jev.tests.fakes import FakeBackend, FakeTokenizer, fake_upstream

    class T13(FakeBackend):
        def identities(self):
            return {**super().identities(), "temperature": 1.3}
    pol = json.loads((ROOT / "experiments/jev/policies/cpu_probe.json").read_text(encoding="utf-8"))
    pol = {**pol, "max_row_tokens": 8192, "max_padded_tokens": 8192 * 640}
    cfg = {"temperature": 1.3, "version": "v10", "isolated_levels": True, "max_options": 255, "schema_first": False, "neutralize_none": False}
    out = tmp_path / "reports" / "probe"
    RS.run("s0-probe-v1", out, pol, cfg, {"model_version": "v10"}, lambda L: T13(L, raw_logits=True), FakeTokenizer, fake_upstream)
    return out


def test_preflight_observes_each_failure(tmp_path):
    out = _fake_probe_run(tmp_path)
    cells, anchors, p0, report, suite = P.load_cells(out, CELL0, TASK)
    assert P.preflight(PRE, report, suite, cells, TASK) == []
    assert not P.anchor_check(anchors, p0, 1e-5)["pass"]                      # 假后端的锚点与真实 run 不同 ⇒ 必须不过
    ptr = next(iter(cells["b"]))
    cases = {
        "T": lambda r, c, t: r["identities"]["backend_effective"].__setitem__("temperature", 1.0),
        "prereg": lambda r, c, t: r["suite_manifest"].__setitem__("prereg_sha256", "0" * 64),
        "coverage": lambda r, c, t: r.__setitem__("coverage_status", "NOT_ESTABLISHED"),
        "status": lambda r, c, t: r.__setitem__("execution_status", "FAILED"),
        "suite": lambda r, c, t: r.__setitem__("suite_sha256", "0" * 64),
        "order": lambda r, c, t: c["b"][ptr]["进程位置"]["candidate_ids"].reverse(),
        "qsha": lambda r, c, t: c["a"][ptr]["触发事件"].__setitem__("questions_sha256", "0" * 64),
        "missing": lambda r, c, t: c["c"][ptr].pop("资源状态"),
        "translation": lambda r, c, t: t["translation_en"]["facets"]["身体状态"]["values"].__setitem__("无关", "irrelevant"),
    }
    for name, mut in cases.items():
        r, c, t = copy.deepcopy(report), copy.deepcopy(cells), copy.deepcopy(TASK); mut(r, c, t)
        assert P.preflight(PRE, r, suite, c, t), name


def test_result_recomputes_from_archive_and_has_no_text():
    if not P.OUT.exists():
        return
    r = json.loads(P.OUT.read_text(encoding="utf-8"))
    probe_dir = ROOT / r["run"]["archive"]
    cells, anchors, p0, report, suite = P.load_cells(probe_dir, CELL0, TASK)
    assert r["★前置"]["锚点(跨 run)"] == P.anchor_check(anchors, p0, PRE["★确定性(前置)"]["tol_abs_dp"])
    if r["★前置"]["pass"]:
        got = P.analyse(cells, ARMS, PRE, TASK)
        for k in ("per_facet", "holm_family", "n_items"):
            assert got[k] == r[k], k
    assert r["prereg_sha256"] == P.sha(P.PRE.read_bytes()) and r["★不得据此说"] == PRE["★★★不得据此说"]
    if r["analysis_script_sha256"] != r["analysis_script_sha256_at_freeze"]:
        assert r.get("★分析脚本冻结后改动说明"), "分析脚本冻结后改过却没登记原因"
    from experiments.jev.report import check_upload, text_leaks
    from experiments.jev.run_suite import suite_texts
    assert text_leaks(" ".join(json.dumps(r, ensure_ascii=False).split()), suite_texts(suite)) == 0
    check_upload(probe_dir, [p for p in probe_dir.iterdir() if p.is_file()], 50 * 1024 * 1024, forbidden_texts=suite_texts(suite))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and fn.__code__.co_argcount == 0: fn()
    print("test_cce_jev_decider_probe: OK")
