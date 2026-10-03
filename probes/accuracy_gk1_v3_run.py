#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tests/data/gk1_v3_prereg.json 跑 G-K1 v3 的**一个 occasion**: 81 条新条目 × 5 模型各标注一次分布 + 资格考(描述)。

用法:
  GK1_V3_OCCASION=1 .venv/bin/python probes/accuracy_gk1_v3_run.py            # 真跑: 需 MINIMAX_API_KEY, 硬上限 470 次
  .venv/bin/python probes/accuracy_gk1_v3_run.py --offline                       # 零 API 干跑(occasion 默认 1): 合成回复, 内存账本, 只打印不落盘
派发(四次分开、依次): gh workflow run probe.yml ... -f probe=probes/accuracy_gk1_v3_run.py
                       -f design=designs/gk1_v3_2026-10-03.json -f env=GK1_V3_OCCASION=<1..4>(5..6 只作替补)
★ 预注册与新条目文件的 sha256 都钉在这里; 不符即拒跑。闸协议 hash/version 与预注册不符即拒跑。
★ 复用 run_gates.annot_dist / qualify 原样(同 prompt、同截断 700); 只把 call() 外包记录器、预算指到本 occasion 的授权单。
★ 判定不在这里做 —— 凑齐 4 个有效 occasion 后由 probes/accuracy_gk1_v3_analyze.py 判。
新条目文件由 select_fresh() 按预注册规则生成: accuracy/data/gk1_v3_fresh81.json == select_fresh() 由守卫测试钉住。
"""
import collections, datetime, hashlib, json, os, pathlib, re, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))

PREREG = ROOT / "tests/data/gk1_v3_prereg.json"
PREREG_SHA256 = "2c493601d7e44003baa56bfd1214e3639bf61bac1a3abe747853a3b17a2406e1"
FRESH = ROOT / "accuracy/data/gk1_v3_fresh81.json"
FRESH_SHA256 = "db1a3c19ce9283e736893c7d71990a59d5080756b61c4f10a98e33546ac43391"
SOURCE = ROOT / "accuracy/data/hearingaids_regulars_20260809.json"
MODELS = ("MiniMax-M3", "MiniMax-M2.5", "MiniMax-M2.7", "MiniMax-M2", "MiniMax-Text-01")   # P5; P4 = 前四
GATE_PROTOCOL = (2, "dbdff13f9da155bc")
CAP, PLANNED = 470, 5 * 81 + 5 * 5
AUTH_PREFIX = "accuracy_gk1_v3_2026_10_03_occ"
OCCASIONS = range(1, 7)          # 1..4 计划, 5..6 只作替补(预注册 S3)
MIN_COVERAGE = 73                # 每名模型可解析分布 >= 73/81(预注册 S2)
STIMULUS_ENV = ("CCE_CORPUS", "CCE_BODY_CHARS", "CCE_UNIT_LABEL")
KN = ["pain_seek", "injustice", "belong", "reward", "display", "itch", "suspend", "inertia", "audit"]


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def select_fresh():
    """预注册 items.eligibility_mechanical E1–E6 + selection, 逐条照写。只看 id 哈希与机械条件。"""
    corpus = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
    anchors = json.loads((ROOT / "accuracy/data/anchors.json").read_text(encoding="utf-8"))
    ex_ids = {x["id"] for x in corpus} | set(anchors["anchor_ids"])                         # E2
    ex_bodies = {x["b"].strip() for x in corpus}                                             # E3
    h = lambda i: hashlib.sha256(i.encode("utf-8")).hexdigest()
    keep = {}
    for user, cs in json.loads(SOURCE.read_text(encoding="utf-8"))["users"].items():        # E1
        for c in cs:
            b = c["b"].strip()
            if (c["id"] in ex_ids or b in ex_bodies or not 25 <= len(b) <= 900               # E2 E3 E4
                    or re.search(r"\bu/\w+|/user/\w+", c["b"])):                           # E5
                continue
            if b not in keep or h(c["id"]) < h(keep[b]["id"]):                               # E6
                keep[b] = {"id": c["id"], "a": user, "post": c["p"], "b": c["b"]}
    return sorted(keep.values(), key=lambda x: h(x["id"]))[:81]


def _fake(occasion):
    """离线合成回复: 主结由正文定(面板大体一致), 次结随模型与 occasion 变。不是金标。"""
    def f(model, prompt):
        body = prompt.split("【")[-1]
        hv = int(hashlib.sha256(body.encode()).hexdigest(), 16)
        g = int(hashlib.sha256(("%s|%d|%s" % (model, occasion, body)).encode()).hexdigest(), 16)
        a, b = KN[hv % 9], KN[(hv // 9 + g % 3) % 9]
        b = b if b != a else KN[(KN.index(a) + 1) % 9]
        return json.dumps({"knots": [{"key": a, "weight": 0.6}, {"key": b, "weight": 0.4}]})
    return f


def _kind(prompt):
    return "qualify" if "★示范锚例(留一法" in prompt else "dist"


def _load(offline, occasion, responses=None):
    if offline:
        import accuracy_offline_harness as AH
        return AH.load(responses=responses or _fake(occasion))
    if not os.environ.get("MINIMAX_API_KEY"):
        print(json.dumps({"status": "BLOCKED_NO_KEY", "real_calls": 0}, ensure_ascii=False))
        sys.exit(3)
    sys.path.insert(0, str(ROOT / "accuracy"))
    import run_gates as m          # noqa: E402  (import 期读 key; 只在环境里)
    return m


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def run(offline, occasion=None, responses=None):
    """responses: 只许离线(守卫测试换合成回复的形状)。返回 (result, replay)。"""
    assert offline or responses is None
    got = _sha(PREREG)
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    if _sha(FRESH) != FRESH_SHA256:
        raise SystemExit("★ 新条目文件被改过(sha256 != 钉住的 %s) —— 拒跑" % FRESH_SHA256[:16])
    bad = [k for k in STIMULUS_ENV if os.environ.get(k)]
    if bad:
        raise SystemExit("★ 预注册要求默认刺激, 但环境里设了 %s —— 拒跑" % bad)
    if occasion is None:
        raw = os.environ.get("GK1_V3_OCCASION", "1" if offline else "")
        occasion = int(raw) if raw.isdigit() else None
    if occasion not in OCCASIONS:
        raise SystemExit("★ GK1_V3_OCCASION 必须是 1..6(1..4 计划, 5..6 只作替补), 得到 %r —— 拒跑" % occasion)
    items = json.loads(FRESH.read_text(encoding="utf-8"))
    auth = AUTH_PREFIX + str(occasion)
    if not offline and os.environ.get("GITHUB_ACTIONS"):
        os.environ.setdefault("CCE_BUDGET_STATE", "/tmp/gk1_v3_occ%d_budget.json" % occasion)   # 账本随 artifact 上传
    import calibration_framework as CF
    saved_log = CF.JSON_FAIL_LOG
    if offline:   # 离线解析失败不进仓里的 results/ 日志
        CF.JSON_FAIL_LOG = os.path.join(tempfile.mkdtemp(prefix="gk1v3_"), "json_extract_failures.log")
    try:
        m = _load(offline, occasion, responses)
        if (m.GATE_PROTOCOL_VERSION, m.gate_protocol_hash()) != GATE_PROTOCOL or m.BODY_CHARS != 700 or m.UNIT_LABEL != "评论":
            raise SystemExit("★ 闸协议/截断/单位与预注册不符(%s, %s, %s, %s) —— 拒跑" % (
                m.GATE_PROTOCOL_VERSION, m.gate_protocol_hash(), m.BODY_CHARS, m.UNIT_LABEL))
        m.BUDGET_ID, m.BUDGET_LIMIT = auth, CAP          # call() 每次 POST 前(含重试)按本授权单扣额
        lock, rec = threading.Lock(), {"calls": [], "n": collections.Counter(), "attempts": 0}
        orig_call, orig_res = m.call, m.reserve

        def call(model, prompt, max_tokens=4000):
            out = orig_call(model, prompt, max_tokens)
            with lock:
                rec["calls"].append({"kind": _kind(prompt), "model": model,
                                     "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "out": out})
                rec["n"][_kind(prompt)] += 1
            return out

        def counted(*a, **k):
            with lock:        # 串行扣额: 离线内存账本无锁, 真跑账本本就加文件锁
                r = orig_res(*a, **k)
                rec["attempts"] += 1
            return r
        m.call, m.reserve = call, counted
        import cce_request_budget as B
        out = {"block": "GK1_V3_OCCASION_RESULT", "prereg_sha256": got, "fresh81_sha256": FRESH_SHA256,
               "occasion": occasion, "auth_id": auth, "cap": CAP, "offline_dry_run": offline,
               "github_run_id": os.environ.get("GITHUB_RUN_ID"), "started_at_utc": _now(),
               "run_params": {"gate_protocol_version": m.GATE_PROTOCOL_VERSION, "gate_protocol_hash": m.gate_protocol_hash(),
                              "CCE_BODY_CHARS": m.BODY_CHARS, "CCE_UNIT_LABEL": m.UNIT_LABEL},
               "panel": list(MODELS), "item_ids": [x["id"] for x in items]}
        dists = {mm: {x["id"]: None for x in items} for mm in MODELS}
        stop, parse_exc = None, collections.Counter()
        # ① 主数据先跑: 81 × 5 标注。撞上限 ⇒ 记下已拿到的, 本 occasion 无效(预注册 S1)
        #   annot_dist 对形状怪异的 JSON(如 knots 里是字符串)会抛异常 —— 记为该格解析失败(None, 计入 S2 覆盖率), 不让一格炸掉整次派发
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(m.annot_dist, (mm, it)): (mm, it["id"]) for mm in MODELS for it in items}
            for f in as_completed(futs):
                mm, iid = futs[f]
                try:
                    dists[mm][iid] = f.result()[1]
                except B.BudgetExceeded as e:
                    stop = stop or "annotation: " + str(e)[:160]
                except Exception as e:
                    parse_exc["%s:%s" % (mm, type(e).__name__)] += 1
        annotation_complete = stop is None
        # ② 资格考(只描述, 不影响面板)
        quals = {}
        if annotation_complete:
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = {ex.submit(m.qualify, mm): mm for mm in MODELS}
                for f in as_completed(futs):
                    try:
                        q = f.result()
                        st, ci = m.qualification_state(q["hits"], q["of"])
                        quals[futs[f]] = {"hits": q["hits"], "of": q["of"], "state": st, "wilson95": list(ci),
                                          "detail": q["detail"]}
                    except B.BudgetExceeded as e:
                        stop = stop or "qualification: " + str(e)[:160]
                    except Exception as e:
                        quals[futs[f]] = {"state": None, "error": type(e).__name__}
    finally:
        CF.JSON_FAIL_LOG = saved_log
    cov = {mm: sum(1 for v in dists[mm].values() if v) for mm in MODELS}
    reasons = ([] if annotation_complete else ["BUDGET_STOP during annotation"]) + \
              ["%s 可解析分布 %d/81 < %d" % (mm, c, MIN_COVERAGE) for mm, c in cov.items() if c < MIN_COVERAGE]
    out.update({"dists": dists, "coverage": cov, "annotation_complete": annotation_complete,
                "parse_exceptions": dict(parse_exc),
                "qualification_descriptive_only": {mm: quals.get(mm) for mm in MODELS},
                "logical_calls": dict(sorted(rec["n"].items())), "http_attempts": rec["attempts"],
                "finished_at_utc": _now(), "occasion_valid": not reasons, "invalid_reasons": reasons,
                "verdict": ("BUDGET_STOP" if not annotation_complete else
                            "OCCASION_INVALID_PARSE" if reasons else "OCCASION_COMPLETE")})
    if stop:
        out["★budget_stop"] = "撞 %d 次硬上限: %s" % (CAP, stop)
    replay = {"block": "GK1_V3_OCCASION_REPLAY", "prereg_sha256": got, "occasion": occasion,
              "★what": "call() 原始返回值(按完成顺序), 供离线重解析; prompt 只记 sha256", "calls": rec["calls"]}
    return out, replay


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    res, replay = run(offline)
    txt = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
    summary = {k: res[k] for k in ("occasion", "offline_dry_run", "verdict", "occasion_valid", "invalid_reasons",
                                   "coverage", "logical_calls", "http_attempts")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if offline:
        sys.exit(0)
    occ = res["occasion"]
    out_dir = pathlib.Path("/tmp") if os.environ.get("GITHUB_ACTIONS") else ROOT / "results/gk1_v3"   # probe.yml 的 artifact 只收 /tmp/*.json
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ("gk1_v3_occ%d_result.json" % occ)).write_text(txt, encoding="utf-8")
    (out_dir / ("gk1_v3_occ%d_replay.json" % occ)).write_text(json.dumps(replay, ensure_ascii=False) + "\n", encoding="utf-8")
    print("写入", out_dir / ("gk1_v3_occ%d_result.json" % occ))
