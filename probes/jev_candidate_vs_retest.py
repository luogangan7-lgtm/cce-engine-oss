# -*- coding: utf-8 -*-
"""hf_choice 候选(Qwen3-4B-Instruct-2507 / Qwen3.5-4B) vs TypeSafe Jev 复测 —— 判据 = 冻结的 Decider 对比脚本, 原样执行。
预注册: tests/data/jev_candidate_vs_retest_prereg.json(看任何候选数据之前冻结)。零 API。

本文件不含任何判据: 先核这一臂的身份(报告 vs 该模型的锁) → 载入 probes/jev_decider_vs_retest.py 并核其 sha == 预注册冻结值 →
把模块全局 PRE / SUITE / OUT 换成候选的(冻结脚本的函数在调用时读这些全局) → 调冻结 main。随后只补: 这一臂是谁、本包装 sha、
预注册的头条检查(触发事件 max_r d ≥ replaceable_max_d + 1 ⇒ 该面不能判「可替代」⇒ 不是完整替代)、字母质量诊断(不进判决)。
包装层身份核对不成立 = 前置不成立: 与冻结规则一样, 不留任何面判决(per_facet 清空)。
冻结脚本输出里的 "D" 一律指这一个候选。产物只有标签计数/统计量/指针, 无原文。
用法: python3 probes/jev_candidate_vs_retest.py <model_key> <run_dir>
"""
import contextlib, hashlib, importlib.util, io, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE = ROOT / "tests/data/jev_candidate_vs_retest_prereg.json"
SUITE = ROOT / "experiments/jev/suites/s0-compare-llm-v1.jsonl"
FROZEN = ROOT / "probes/jev_decider_vs_retest.py"
KEYS = ("qwen3-4b-2507", "qwen3.5-4b")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def out_path(key):
    return ROOT / f"results/jev_candidate_{key}_vs_retest.json"


def load_frozen(pre):
    if sha(FROZEN.read_bytes()) != pre["★分析脚本(冻结)"]["sha256"]:
        raise SystemExit("冻结的对比脚本被改过: sha 与预注册不符, 拒绝出任何判决")
    s = importlib.util.spec_from_file_location("_frozen_cmp", FROZEN); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def identity_errors(key, rep):
    """报告里的这一臂 == models/<key>/ 的锁: 模型键、仓库、修订、源锁/资产锁 sha、字母、线程、存储与计算精度、prompt spec、温度。"""
    d = ROOT / f"experiments/jev/models/{key}"
    src = json.loads((d / "model.source.lock.json").read_text(encoding="utf-8"))
    ids = rep.get("identities") or {}
    eff = ids.get("backend_effective") or {}
    cfg = src["backend_config"]
    want = {"model_key": key, "source_lock_sha256": sha((d / "model.source.lock.json").read_bytes()),
            "assets_lock_sha256": sha((d / "model.assets.lock.json").read_bytes()) if (d / "model.assets.lock.json").is_file() else "missing"}
    got = {k: ids.get(k) for k in want}
    e2 = {"repo_id": src["repo_id"], "revision": src["revision"], "backend": "hf_choice", "letters": cfg["letters"], "threads": cfg["threads"],
          "storage_dtype": "torch.bfloat16", "compute_dtype": "torch.float32", "prompt_spec": cfg["prompt_spec"], "temperature": cfg["temperature"]}
    g2 = {k: eff.get(k) for k in e2}
    return [f"身份字段 {k}: 报告 {got[k]!r} ≠ 锁 {want[k]!r}" for k in want if got[k] != want[k]] + \
           [f"有效配置 {k}: 报告 {g2[k]!r} ≠ 锁 {e2[k]!r}" for k in e2 if g2[k] != e2[k]]


def letter_diag(run_dir, suite_ids):
    """字母质量诊断(预注册口径): 42×5 主行(不含 rep- 与 smoke)的 letter_mass 中位数与 vocab_top1_is_letter 计数。不进判决。"""
    f = next(p for p in run_dir.iterdir() if p.name.endswith("predictions.jsonl"))
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    main = [r for r in rows if r["item_id"] in suite_ids and not r["item_id"].startswith("rep-")]
    mass = [r["identities"].get("letter_mass") for r in main if isinstance(r.get("identities", {}).get("letter_mass"), (int, float))]
    if not mass:
        return None
    per = {}
    for r in main:
        per.setdefault(r["question_id"], []).append(r["identities"].get("letter_mass", 0.0))
    return {"rows": len(main), "median_letter_mass": round(statistics.median(mass), 4), "top1_is_letter": sum(1 for r in main if r["identities"].get("vocab_top1_is_letter")),
            "per_facet_median": {k: round(statistics.median(v), 4) for k, v in per.items()},
            "caveat": statistics.median(mass) < 0.5}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    key, run_dir = argv[0], pathlib.Path(argv[1])
    if key not in KEYS:
        raise SystemExit(f"unknown model key {key!r}")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    rep = json.loads(next(p for p in run_dir.iterdir() if p.name.endswith("__report.json") or p.name == "report.json").read_text(encoding="utf-8"))
    errs = identity_errors(key, rep)                                   # 先核身份, 再算
    X = load_frozen(pre)
    X.PRE, X.SUITE, X.OUT = PRE, SUITE, out_path(key)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):                              # 冻结 main 会打印判决; 身份不成立时那份输出作废, 不外泄
        X.main([str(run_dir)])
    doc = json.loads(X.OUT.read_text(encoding="utf-8"))
    rules = pre["★★★判决规则(测量前冻结)"]["数值"]
    if errs:
        doc["★前置"]["errors"] = list(doc["★前置"].get("errors") or []) + errs
        doc["★前置"]["同 run 复跑"]["pass"] = False
        doc.update({"per_facet": {}, "情绪余温_structural": None, "n_items": None,
                    "verdicts": {k: None for k in pre["★面"]["模型读"]}, "overall": "前置不成立(执行错误, 不出判决)"})
    head = None
    pf = (doc.get("per_facet") or {}).get(pre["★头条检查(预注册)"]["面"])
    if pf:
        d = {j: pf["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")}
        th = rules["replaceable_max_d"] + 1
        head = {"facet": pre["★头条检查(预注册)"]["面"], "d": d, "max_d": max(d.values()), "threshold": th, "rule": pre["★头条检查(预注册)"]["规则"],
                "result": "不能判可替代 ⇒ 不是完整替代" if max(d.values()) >= th else "头条检查通过(仅说明该面未被排除, 不是判决)"}
    suite_ids = {json.loads(l)["item_id"] for l in SUITE.read_text(encoding="utf-8").splitlines() if l.strip() and "text_ref" in json.loads(l)}
    cross = (doc.get("★前置") or {}).get("跨 run(smoke 行 vs 前一 run)")
    if isinstance(cross, dict):
        cross["★说明"] = "占位, 非检查: 候选行哈希与前一 run 不同, 配对数按构造为 0(见预注册 ★确定性(前置).跨 run 对照)"
    doc.update({"block": "JEV_CANDIDATE_VS_RETEST", "★臂D即": {"model_key": key, **{k: ((rep.get("identities") or {}).get("backend_effective") or {}).get(k)
                                                                      for k in ("repo_id", "revision", "class", "param_count", "storage_dtype", "compute_dtype", "threads", "prompt_spec")},
                                                             "cpu_model": ((rep.get("identities") or {}).get("cgroup_limits") or {}).get("cpu_model")},
                "★头条检查": head, "★包装前置错误": errs, "★字母质量诊断(不进判决)": None if errs else letter_diag(run_dir, suite_ids),
                "wrapper_sha256": sha(pathlib.Path(__file__).read_bytes()), "wrapper_sha256_at_freeze": pre["★分析脚本(冻结)"]["wrapper_sha256"]})
    X.OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"model": key, "overall": doc["overall"], "verdicts": doc.get("verdicts"), "headline": head, "wrapper_errors": errs}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
