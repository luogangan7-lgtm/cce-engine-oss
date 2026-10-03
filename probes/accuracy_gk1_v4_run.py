#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tests/data/gk1_v4_prereg.json 跑 G-K1 v4 的**一个 occasion**: 54 条新条目 × P4 四人 × 每条采样 k=3 次。

用法:
  GK1_V4_OCCASION=1 .venv/bin/python probes/accuracy_gk1_v4_run.py     # 真跑: 需 MINIMAX_API_KEY, 硬上限 700 次
  .venv/bin/python probes/accuracy_gk1_v4_run.py --offline                # 零 API 干跑(occasion 默认 1): 合成回复, 内存账本, 只打印不落盘
派发(依次, 每次一个 occasion; 5 只作替补): gh workflow run probe.yml ... -f probe=probes/accuracy_gk1_v4_run.py
                       -f design=designs/gk1_v4_2026-10-03.json -f env=GK1_V4_OCCASION=<1..4>
★ 预注册与条目文件 sha256 钉在这里; 不符即拒跑。闸协议 hash/version 与预注册不符即拒跑。
★ 每次采样 = run_gates.annot_dist 原样一次; 真跑传输与运维设置沿用 v3 的 make_resilient_call(并发 3 + 退避 + 记错误码)。
★ k 次采样按「采样序号优先」提交; k 平均与判定不在这里做 —— 由 probes/accuracy_gk1_v4_analyze.py 做。
"""
import collections, hashlib, json, os, pathlib, re, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import accuracy_gk1_v3_run as V3   # noqa: E402  make_resilient_call / 离线装载 / 闸协议常量沿用 v3

PREREG = ROOT / "tests/data/gk1_v4_prereg.json"
PREREG_SHA256 = "163e0ac4604e1ce064f1bd91486096e02e96c1af6456daeec701092f4223b01c"
ITEMS = ROOT / "accuracy/data/gk1_v4_fresh54.json"
ITEMS_SHA256 = "b207fb431aed478af203cb18be68ee7f075f9bd7521c581198d9edd7ac5e74f0"
SOURCE, V3_ITEMS = V3.SOURCE, V3.FRESH
MODELS = ("MiniMax-M3", "MiniMax-M2.5", "MiniMax-M2.7", "MiniMax-M2")   # P4
GATE_PROTOCOL = V3.GATE_PROTOCOL
N, K = 54, 3
PLANNED, CAP = len(MODELS) * N * K, 700          # 648 计划 + 52 余量
AUTH_PREFIX = "accuracy_gk1_v4_2026_10_03_occ"
OCCASIONS = range(1, 6)                           # 1..4 计划, 5 只作替补(预注册 S3)
MIN_SAMPLES = 146                                 # 每名模型可解析采样 >= ceil(0.9 × 54 × 3)(预注册 S2)
STIMULUS_ENV = V3.STIMULUS_ENV
make_resilient_call = V3.make_resilient_call     # 守卫测试钉同一对象


def select_fresh():
    """预注册 items: E1–E6 与 v3 逐字同式, 加 E7(排除 v3 的 81 条 id 与正文), 按 sha256(id) 升序取前 54。"""
    corpus = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
    anchors = json.loads((ROOT / "accuracy/data/anchors.json").read_text(encoding="utf-8"))
    v3 = json.loads(V3_ITEMS.read_text(encoding="utf-8"))
    ex_ids = {x["id"] for x in corpus} | set(anchors["anchor_ids"]) | {x["id"] for x in v3}          # E2 E7
    ex_bodies = {x["b"].strip() for x in corpus} | {x["b"].strip() for x in v3}                    # E3 E7
    h = lambda i: hashlib.sha256(i.encode("utf-8")).hexdigest()
    keep = {}
    for user, cs in json.loads(SOURCE.read_text(encoding="utf-8"))["users"].items():               # E1
        for c in cs:
            b = c["b"].strip()
            if (c["id"] in ex_ids or b in ex_bodies or not 25 <= len(b) <= 900                     # E2 E3 E4 E7
                    or re.search(r"\bu/\w+|/user/\w+", c["b"])):                                 # E5
                continue
            if b not in keep or h(c["id"]) < h(keep[b]["id"]):                                     # E6
                keep[b] = {"id": c["id"], "a": user, "post": c["p"], "b": c["b"]}
    return sorted(keep.values(), key=lambda x: h(x["id"]))[:N]


def _fake(occasion):
    """离线合成回复: 主结由正文定, 次结随 (模型, occasion, 第几次采样) 变。不是金标。"""
    seen, lock = collections.Counter(), threading.Lock()

    def f(model, prompt):
        body = prompt.split("【")[-1]
        with lock:
            s = seen[(model, body)]
            seen[(model, body)] += 1
        hv = int(hashlib.sha256(body.encode()).hexdigest(), 16)
        g = int(hashlib.sha256(("%s|%d|%d|%s" % (model, occasion, s, body)).encode()).hexdigest(), 16)
        a, b = V3.KN[hv % 9], V3.KN[(hv // 9 + g % 3) % 9]
        b = b if b != a else V3.KN[(V3.KN.index(a) + 1) % 9]
        return json.dumps({"knots": [{"key": a, "weight": 0.6}, {"key": b, "weight": 0.4}]})
    return f


def run(offline, occasion=None, responses=None):
    """responses: 只许离线(守卫测试换合成回复的形状)。返回 (result, replay)。"""
    assert offline or responses is None
    got = V3._sha(PREREG)
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    if V3._sha(ITEMS) != ITEMS_SHA256:
        raise SystemExit("★ 条目文件被改过(sha256 != 钉住的 %s) —— 拒跑" % ITEMS_SHA256[:16])
    bad = [k for k in STIMULUS_ENV if os.environ.get(k)]
    if bad:
        raise SystemExit("★ 预注册要求默认刺激, 但环境里设了 %s —— 拒跑" % bad)
    if occasion is None:
        raw = os.environ.get("GK1_V4_OCCASION", "1" if offline else "")
        occasion = int(raw) if raw.isdigit() else None
    if occasion not in OCCASIONS:
        raise SystemExit("★ GK1_V4_OCCASION 必须是 1..5(1..4 计划, 5 只作替补), 得到 %r —— 拒跑" % occasion)
    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    auth = AUTH_PREFIX + str(occasion)
    if not offline and os.environ.get("GITHUB_ACTIONS"):
        os.environ.setdefault("CCE_BUDGET_STATE", "/tmp/gk1_v4_occ%d_budget.json" % occasion)   # 账本随 artifact 上传
    import calibration_framework as CF
    saved_log = CF.JSON_FAIL_LOG
    if offline:   # 离线解析失败不进仓里的 results/ 日志
        CF.JSON_FAIL_LOG = os.path.join(tempfile.mkdtemp(prefix="gk1v4_"), "json_extract_failures.log")
    try:
        m = V3._load(offline, occasion, responses or (_fake(occasion) if offline else None))
        if (m.GATE_PROTOCOL_VERSION, m.gate_protocol_hash()) != GATE_PROTOCOL or m.BODY_CHARS != 700 or m.UNIT_LABEL != "评论":
            raise SystemExit("★ 闸协议/截断/单位与预注册不符(%s, %s, %s, %s) —— 拒跑" % (
                m.GATE_PROTOCOL_VERSION, m.gate_protocol_hash(), m.BODY_CHARS, m.UNIT_LABEL))
        m.BUDGET_ID, m.BUDGET_LIMIT = auth, CAP          # 每次 POST 前(含重试)按本授权单扣额
        lock, rec, tl = threading.Lock(), {"calls": [], "n": 0, "attempts": 0}, threading.local()
        orig_call, orig_res = m.call, m.reserve
        errs = collections.Counter()
        resilient_call = make_resilient_call(m, lock, errs)

        def call(model, prompt, max_tokens=4000):
            out = (orig_call if offline else resilient_call)(model, prompt, max_tokens)
            with lock:
                rec["calls"].append({"model": model, "sample": tl.s,
                                     "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "out": out})
                rec["n"] += 1
            return out

        def counted(*a, **k):
            with lock:        # 串行扣额: 离线内存账本无锁, 真跑账本本就加文件锁
                r = orig_res(*a, **k)
                rec["attempts"] += 1
            return r
        m.call, m.reserve = call, counted

        def one(mm, it, s):
            tl.s = s
            return m.annot_dist((mm, it))[1]

        import cce_request_budget as B
        out = {"block": "GK1_V4_OCCASION_RESULT", "prereg_sha256": got, "items_sha256": ITEMS_SHA256,
               "occasion": occasion, "auth_id": auth, "cap": CAP, "k": K, "offline_dry_run": offline,
               "github_run_id": os.environ.get("GITHUB_RUN_ID"), "started_at_utc": V3._now(),
               "run_params": {"gate_protocol_version": m.GATE_PROTOCOL_VERSION, "gate_protocol_hash": m.gate_protocol_hash(),
                              "CCE_BODY_CHARS": m.BODY_CHARS, "CCE_UNIT_LABEL": m.UNIT_LABEL},
               "panel": list(MODELS), "item_ids": [x["id"] for x in items]}
        dists = {mm: {x["id"]: [None] * K for x in items} for mm in MODELS}
        stop, parse_exc = None, collections.Counter()
        # 采样序号优先提交(预注册 stimulus.sample_order); 一格坏读数记 None, 不掀翻整次派发; 撞上限 ⇒ 本 occasion 无效(S1)
        with ThreadPoolExecutor(max_workers=V3.ANNOT_WORKERS) as ex:
            futs = {ex.submit(one, mm, it, s): (mm, it["id"], s) for s in range(K) for mm in MODELS for it in items}
            for f in as_completed(futs):
                mm, iid, s = futs[f]
                try:
                    dists[mm][iid][s] = f.result()
                except B.BudgetExceeded as e:
                    stop = stop or "annotation: " + str(e)[:160]
                except Exception as e:
                    parse_exc["%s:%s" % (mm, type(e).__name__)] += 1
    finally:
        CF.JSON_FAIL_LOG = saved_log
    cov = {mm: sum(1 for v in dists[mm].values() for d in v if d) for mm in MODELS}
    partial = {mm: sum(1 for v in dists[mm].values() if 0 < sum(1 for d in v if d) < K) for mm in MODELS}
    reasons = ([] if stop is None else ["BUDGET_STOP during annotation"]) + \
              ["%s 可解析采样 %d/%d < %d" % (mm, c, N * K, MIN_SAMPLES) for mm, c in cov.items() if c < MIN_SAMPLES]
    out.update({"dists": dists, "coverage_samples": cov, "cells_with_fewer_than_k": partial,
                "annotation_complete": stop is None, "parse_exceptions": dict(parse_exc),
                "http_errors_by_model_and_code": dict(sorted(errs.items())),
                "★operational": {"annot_workers": V3.ANNOT_WORKERS, "backoff_base_sec": V3.BACKOFF_BASE_SEC,
                                 "sample_order": "sample-major"},
                "logical_calls": rec["n"], "http_attempts": rec["attempts"], "finished_at_utc": V3._now(),
                "occasion_valid": not reasons, "invalid_reasons": reasons,
                "verdict": ("BUDGET_STOP" if stop else "OCCASION_INVALID_PARSE" if reasons else "OCCASION_COMPLETE")})
    if stop:
        out["★budget_stop"] = "撞 %d 次硬上限: %s" % (CAP, stop)
    replay = {"block": "GK1_V4_OCCASION_REPLAY", "prereg_sha256": got, "occasion": occasion,
              "★what": "call() 原始返回值(按完成顺序, 带采样序号), 供离线重解析; prompt 只记 sha256", "calls": rec["calls"]}
    return out, replay


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    res, replay = run(offline)
    summary = {k: res[k] for k in ("occasion", "offline_dry_run", "verdict", "occasion_valid", "invalid_reasons",
                                   "coverage_samples", "cells_with_fewer_than_k", "logical_calls", "http_attempts")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if offline:
        sys.exit(0)
    occ = res["occasion"]
    out_dir = pathlib.Path("/tmp") if os.environ.get("GITHUB_ACTIONS") else ROOT / "results/gk1_v4"   # probe.yml 的 artifact 只收 /tmp/*.json
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ("gk1_v4_occ%d_result.json" % occ)).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / ("gk1_v4_occ%d_replay.json" % occ)).write_text(json.dumps(replay, ensure_ascii=False) + "\n", encoding="utf-8")
    print("写入", out_dir / ("gk1_v4_occ%d_result.json" % occ))
