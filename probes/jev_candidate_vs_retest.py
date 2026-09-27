# -*- coding: utf-8 -*-
"""hf_choice 候选(Qwen3-4B-Instruct-2507 / Qwen3.5-4B) vs TypeSafe Jev 复测 —— 判据 = 冻结的 Decider 对比脚本, 原样执行。
预注册: tests/data/jev_candidate_vs_retest_prereg.json(看任何候选数据之前冻结)。零 API。

本文件不含任何判据: 载入 probes/jev_decider_vs_retest.py → 核其 sha == 预注册冻结值 → 把模块全局 PRE / SUITE / OUT 换成候选的
(冻结脚本的函数在调用时读这些全局) → 调冻结 main。随后只补三样元数据: 这一臂是谁(与源锁核对)、本包装脚本 sha、预注册的头条检查
(触发事件 max_r d ≥ 5 ⇒ 该面不可能判「可替代」⇒ 不是完整替代; 这是 replaceable_max_d=4 的否定, 不是新阈值)。
冻结脚本输出里的 "D" 一律指这一个候选。产物只有标签计数/统计量/指针, 无原文。
用法: python3 probes/jev_candidate_vs_retest.py <model_key> <run_dir>
"""
import hashlib, importlib.util, json, pathlib, sys

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


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    key, run_dir = argv[0], pathlib.Path(argv[1])
    if key not in KEYS:
        raise SystemExit(f"unknown model key {key!r}")
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    X = load_frozen(pre)
    X.PRE, X.SUITE, X.OUT = PRE, SUITE, out_path(key)
    X.main([str(run_dir)])
    doc = json.loads(X.OUT.read_text(encoding="utf-8"))
    rep = json.loads(next(p for p in run_dir.iterdir() if p.name.endswith("__report.json") or p.name == "report.json").read_text(encoding="utf-8"))
    eff = (rep.get("identities") or {}).get("backend_effective") or {}
    src = json.loads((ROOT / f"experiments/jev/models/{key}/model.source.lock.json").read_text(encoding="utf-8"))
    who = {"model_key": key, "repo_id": eff.get("repo_id"), "revision": eff.get("revision"), "backend": eff.get("backend"),
           "storage_dtype": eff.get("storage_dtype"), "compute_dtype": eff.get("compute_dtype"), "threads": eff.get("threads"),
           "prompt_spec": eff.get("prompt_spec"), "cpu_model": ((rep.get("identities") or {}).get("cgroup_limits") or {}).get("cpu_model")}
    errs = list(doc.get("★前置", {}).get("errors") or [])
    if (who["repo_id"], who["revision"], who["backend"]) != (src["repo_id"], src["revision"], "hf_choice"):
        errs.append("报告里的模型身份与源锁不符")
    if who["prompt_spec"] != pre["★臂"]["D"]["prompt_spec"] or who["compute_dtype"] != "torch.float32":
        errs.append("prompt spec / 计算精度与预注册不符")
    head = None
    pf = (doc.get("per_facet") or {}).get("触发事件")
    if pf and not errs:
        d = {j: pf["pairs"][f"D~{j}"]["d"] for j in ("J1", "J2")}
        head = {"d": d, "max_d": max(d.values()), "rule": pre["★头条检查(预注册)"]["规则"],
                "result": "不能判可替代 ⇒ 不是完整替代" if max(d.values()) >= 5 else "头条检查通过(仅说明该面未被排除, 不是判决)"}
    if errs:                                           # 包装层前置不成立: 同冻结规则, 不出任何面判决
        doc["verdicts"] = {k: None for k in pre["★面"]["模型读"]}; doc["overall"] = "前置不成立(执行错误, 不出判决)"
    doc.update({"block": "JEV_CANDIDATE_VS_RETEST", "★臂D即": who, "★头条检查": head, "★包装前置错误": errs,
                "wrapper_sha256": sha(pathlib.Path(__file__).read_bytes()), "wrapper_sha256_at_freeze": pre["★分析脚本(冻结)"]["wrapper_sha256"]})
    X.OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"model": key, "overall": doc["overall"], "verdicts": doc.get("verdicts"), "headline": head, "wrapper_errors": errs}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
