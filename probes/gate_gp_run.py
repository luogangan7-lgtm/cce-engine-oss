#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-P(生产实际输出闸)的一次派发: 一名面板成员 × 一次运行 × 一个分片(86 条新条目的前 43 或后 43 条),
每条走一遍**生产代码本身**。

用法:
  GP_MODEL=M3 GP_RUN=1 GP_SHARD=1 .venv/bin/python probes/gate_gp_run.py   # 真跑: 需 MINIMAX_API_KEY, 硬上限 409 次 HTTP
  .venv/bin/python probes/gate_gp_run.py --offline                          # 零 API 干跑(默认 M3 / 运行 1 / 分片 1): 假传输, 其余生产代码全程照走
派发: gh workflow run probe.yml --ref master -f probe=probes/gate_gp_run.py -f design=designs/gate_gp_2026-10-03.json
      -f env="GP_MODEL=<M3|M2.5|M2.7|M2> GP_RUN=<1|2> GP_SHARD=<1|2>"    (16 片依次派发, 见预注册 dispatch_plan)
★ 2026-10-03 owner 修订(调用前): N 40 → 86; 每个 (成员, 运行) 拆 2 片(墙钟理由, 见预注册 ★amendment_..._N86), 分析器拼回。
★ 生产路径 = cce_full_run.run_knot_classify(k=3) → cce_knot_classify.stage1 / stage2 → cce_full_run.s2(s2_knots)→ cce_full_run.qualified,
  全是生产的函数对象本身, 不复刻任何 prompt。只换三样运维件(都不碰 prompt / 仪器字段):
  ① 子进程边界 → 同进程(组装逐行对应 cce_knot_classify.main; 守卫测试钉住那几行)
  ② exp_crossmodel_desire.requests 外包一层: 并发 3 + 失败退避 + 「模型|错误码」计数(请求由生产 call_model 原样构造)
  ③ 预算 = 生产自己的 cce_request_budget.open_scope(上限 380); reserve_in_scope 外包一层只记 BudgetExceeded
★ 面板成员 = 同一台生产仪器只换 model: 往 exp_crossmodel_desire.MODELS 登记同端点同参数的 MiniMax-M2.x, 设 MEASUREMENT_MODEL;
  起跑前断言 instrument spec 与生产 d4cce4c745f3f991 只差 model 一项。预注册与条目文件 sha256 钉在这里, 不符即拒跑。
"""
import collections, hashlib, json, os, pathlib, random, re, subprocess, sys, tempfile, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import exp_crossmodel_desire as X      # noqa: E402  生产传输 call_model 与模型表
import cce_knot_classify as K          # noqa: E402  生产 s1 / s2
import cce_full_run as F               # noqa: E402  生产 run_knot_classify / s2_knots / qualified_readout
import cce_request_budget as B         # noqa: E402  生产预算作用域
import cce_k1_status as S              # noqa: E402  生产 K1 路由

PREREG = ROOT / "tests/data/gate_gp_prereg.json"
PREREG_SHA256 = "e86837c3d31d8a11f395dd9866c4a14bdac746a094fbf4eabcaef632be94a535"
ITEMS = ROOT / "accuracy/data/gate_gp_fresh86.json"
ITEMS_SHA256 = "e961de896abbd5920be6eca944a779f3cf1d99dcbb4220f791bfe6329ed512ca"
SOURCE = ROOT / "accuracy/data/hearingaids_regulars_20260809.json"
CONTEXT = "reddit r/HearingAids hearing_aid: Public reply to a Reddit r/HearingAids member(对方原文/写作基准侧)"
K_S1, N = 3, 86
PROD_HASH = "d4cce4c745f3f991"
PANEL = {"M3": "MiniMax-M3", "M2.5": "MiniMax-M2.5", "M2.7": "MiniMax-M2.7", "M2": "MiniMax-M2"}
RUNS, SHARDS, SHARD_SIZE = (1, 2), (1, 2), 43       # 分片 1 = 条目文件第 1–43 条, 分片 2 = 第 44–86 条
NOMINAL_PER_READOUT = K_S1 + 5                      # s1 k 档 + s2 n 次, 全部首发成功时
PLANNED, CAP = SHARD_SIZE * NOMINAL_PER_READOUT, 409  # 每片 344 计划 + 65 余量(与 N=40 时同一相对余量 60/320)
MIN_COVERAGE = 39                                   # 每片非 MISSING 读数 >= ceil(0.9 × 43)
ITEM_WORKERS, HTTP_CONCURRENCY, BACKOFF_BASE_SEC = 3, 3, 4.0
WALL_SEC = 9600
REFUSE_ENV = ("CCE_MEASUREMENT_MODEL", "CCE_KNOT_N", "CCE_TAXO_VERSION", "CCE_CITATION_CERT", "VSE_ROOT", B.SCOPE_ID)
SCOPE_LABEL = "gate_gp_2026_10_03_%s_r%d_s%d"
S2_HEAD = "你是 CCE 结分类器"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def select_fresh():
    """预注册 items.rule: E1–E6 与 v4 同式, E2/E3 加 v4 的 54 条, E9 排除生产 top-1 已落盘的评论; sha256(id) 升序取前 86(owner 修订前为 40)。"""
    corpus, anchors = _load("accuracy/data/corpus.json"), _load("accuracy/data/anchors.json")
    old = corpus + _load("accuracy/data/gk1_v3_fresh81.json") + _load("accuracy/data/gk1_v4_fresh54.json")
    users = json.loads(SOURCE.read_text(encoding="utf-8"))["users"]
    seen = {r["ptr"].split(":")[2] for r in _load("results/reader_mode_gate_rows.json")["rows"]}           # E9
    seen_bodies = {c["b"].strip() for cs in users.values() for c in cs if c["id"] in seen}
    ex_ids = {x["id"] for x in old} | set(anchors["anchor_ids"]) | seen                                   # E2 E9
    ex_bodies = {x["b"].strip() for x in old} | seen_bodies                                               # E3 E9
    h = lambda i: hashlib.sha256(i.encode("utf-8")).hexdigest()
    keep = {}
    for user, cs in users.items():                                                                        # E1
        for c in cs:
            b = c["b"].strip()
            if (c["id"] in ex_ids or b in ex_bodies or not 25 <= len(b) <= 900                            # E2 E3 E4
                    or re.search(r"\bu/\w+|/user/\w+", c["b"])):                                         # E5
                continue
            if b not in keep or h(c["id"]) < h(keep[b]["id"]):                                             # E6
                keep[b] = {"id": c["id"], "a": user, "post": c["p"], "b": c["b"]}
    return sorted(keep.values(), key=lambda x: h(x["id"]))[:N]


def _spec(model_key):
    saved = K.MEASUREMENT_MODEL
    try:
        K.MEASUREMENT_MODEL = model_key
        return K.instrument_id(_load("config/knot_taxonomy.json"), k=K_S1, knot_n=K.KNOT_N,
                               s1_pairing="round_robin_over_%d_s1_draws" % K_S1)
    finally:
        K.MEASUREMENT_MODEL = saved


def install_member(key):
    """登记面板成员并断言「同一台生产仪器只换 model」。返回该成员的 instrument_id。"""
    if key not in PANEL:
        raise SystemExit("★ GP_MODEL 必须是 %s 之一, 得到 %r —— 拒跑" % (list(PANEL), key))
    assert X.MODELS["M3"]["model"] == "MiniMax-M3" and K.KNOT_N == 5, "★ 生产 M3 / KNOT_N 不是预注册时的样子"
    prod = _spec("M3")
    if prod["instrument_hash"] != PROD_HASH:
        raise SystemExit("★ 生产仪器 %s != 预注册的 %s —— 生产已换代, 本预注册不适用" % (prod["instrument_hash"], PROD_HASH))
    if key != "M3":
        X.MODELS[key] = {**X.MODELS["M3"], "model": PANEL[key]}
    inst = _spec(key)
    diff = {f for f in set(prod["spec"]) | set(inst["spec"]) if prod["spec"].get(f) != inst["spec"].get(f)}
    assert diff == (set() if key == "M3" else {"model"}), "★ 面板成员与生产仪器的差别不止 model: %s" % sorted(diff)
    K.MEASUREMENT_MODEL = key
    return inst


def spec_minus_model_sha(inst):
    return hashlib.sha256(json.dumps({k: v for k, v in inst["spec"].items() if k != "model"},
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


class _Transport:
    """套在生产 call_model 用的 requests 外面: 全局并发 3 + 失败后指数退避(不耗尝试)+「模型|错误码」计数(不记内容)。
    请求本身(端点 / 请求体 / 温度 / max_tokens / 超时 / 3 次重试与 4 秒间隔)由生产 call_model 原样构造、原样发送。"""

    def __init__(self, real, errs, lock, sleep=time.sleep):
        self._real, self._errs, self._lock, self._sleep = real, errs, lock, sleep
        self._sem, self._tl = threading.BoundedSemaphore(HTTP_CONCURRENCY), threading.local()

    def __getattr__(self, name):
        return getattr(self._real, name)

    def post(self, url, **kw):
        model, key, resp, exc = (kw.get("json") or {}).get("model"), None, None, None
        with self._sem:
            try:
                resp = self._real.post(url, **kw)
            except Exception as e:
                exc, key = e, "exc:%s" % type(e).__name__
        if resp is not None and resp.status_code != 200:
            key = "http:%s" % resp.status_code
        elif resp is not None:
            try:
                br = (resp.json().get("base_resp") or {}).get("status_code")
            except Exception:
                br = "unparseable"
            key = None if br in (0, None) else "base_resp:%s" % br
        n = getattr(self._tl, "fails", 0)
        if key:
            with self._lock:
                self._errs["%s|%s" % (model, key)] += 1
            self._tl.fails = n + 1
            self._sleep(BACKOFF_BASE_SEC * (2 ** min(n, 3)) + random.random())
        else:
            self._tl.fails = 0
        if exc is not None:
            raise exc
        return resp


class _FakeResp:
    def __init__(self, payload):
        self.status_code, self._p, self.text = 200, payload, json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _FakeRequests:
    """离线: 不出网。按 prompt 种类合成回复 —— s1 给合法四层 JSON(约 1/16 的条目整体弃权), s2 给 2 个结:
    主结由正文定, 次结与谁领先随 (成员, 运行, 第几次抽样) 变。不是金标。记下每一份收到的 prompt 供守卫测试核对。"""

    def __init__(self, member, run_no):
        self.member, self.run_no, self.prompts, self._seen, self._lock = member, run_no, [], collections.Counter(), threading.Lock()

    @staticmethod
    def _text(prompt):
        if prompt.startswith(S2_HEAD):
            return prompt.split("【待分类内容】\n", 1)[1].rsplit("\n\n只输出 JSON", 1)[0]
        return prompt.split("以下是内容全文(仅文本, 无任何互动数据):\n\n", 1)[1].split("\n\n(注:", 1)[0]

    def post(self, url, **kw):
        prompt, model = kw["json"]["messages"][0]["content"], kw["json"]["model"]
        text = self._text(prompt)
        hv = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        with self._lock:
            self.prompts.append({"model": model, "prompt": prompt, "text": text,
                                 "kind": "s2" if prompt.startswith(S2_HEAD) else "s1"})
            s = self._seen[(model, text, prompt.startswith(S2_HEAD))]
            self._seen[(model, text, prompt.startswith(S2_HEAD))] += 1
        if not prompt.startswith(S2_HEAD):
            body = ({"no_inferable_subject": True, "reason": "offline"} if hv % 16 == 0 else
                    {"desire_layer": {"distribution": {K.DESIRES[hv % len(K.DESIRES)]: 0.7, K.DESIRES[(hv + 1) % len(K.DESIRES)]: 0.3}},
                     "emotion_layer": {"distribution": {K.EMOTIONS[hv % len(K.EMOTIONS)]: 1.0}},
                     "action_tendency_layer": {"distribution": {K.ACTIONS[hv % len(K.ACTIONS)]: 1.0}},
                     "need_layer": [{"code": K.NEED_KEYS[hv % len(K.NEED_KEYS)], "weight": 1.0}],
                     "appraisal": {"agency": "self"}, "chain_trace": "offline"})
        else:
            g = int(hashlib.sha256(("%s|%d|%d|%s" % (model, self.run_no, s, text)).encode()).hexdigest(), 16)
            a, b = K.KNOTS_ALL[hv % 9], K.KNOTS_ALL[(hv // 9) % 9]
            b = b if b != a else K.KNOTS_ALL[(K.KNOTS_ALL.index(a) + 1) % 9]
            lead, other = (b, a) if g % 4 == 0 else (a, b)
            body = {"knots": [{"key": lead, "intensity": 0.8}, {"key": other, "intensity": 0.4}],
                    "levers_present": [], "notes": "offline"}
        return _FakeResp({"base_resp": {"status_code": 0},
                          "choices": [{"message": {"content": json.dumps(body, ensure_ascii=False)},
                                       "finish_reason": "stop"}]})


class _InProcess:
    """cce_full_run.run_knot_classify 的子进程边界换成同进程: 组装逐行对应 cce_knot_classify.main()
    (读文件 → text.strip() → stage1 → stage2 → 写 out JSON; 抛错 ⇒ 非零返回码 + traceback), 其余属性转给真 subprocess。"""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, cmd, **kw):
        a = dict(zip(cmd[2::2], cmd[3::2]))
        assert cmd[1].endswith("scripts/cce_knot_classify.py") and set(a) == {"--text-file", "--context", "--k", "--out"}, cmd
        try:
            text = open(a["--text-file"], encoding="utf-8").read()
            taxo = json.load(open(K.TAXO_PATH, encoding="utf-8"))
            s1 = K.stage1(text.strip(), a["--context"], int(a["--k"]))
            s2 = K.stage2(text.strip(), s1, taxo)
            out = {"input_sha": hashlib.sha256(text.encode()).hexdigest()[:16], "stage1": s1, "stage2": s2,
                   "caveats": K.caveats(taxo)}
            with open(a["--out"], "w", encoding="utf-8") as fh:
                fh.write(json.dumps(out, ensure_ascii=False))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        except Exception as e:
            return subprocess.CompletedProcess(cmd, 1, "", "".join(traceback.format_exception(e)))


_PUB_LOCK = threading.Lock()


def _ledger(op):
    return dict(collections.Counter(a.get("status") for a in (op or {}).get("attempts") or []))


def readout(item, tmp):
    """一条条目的一次生产读数 + 生产自己的发布判定。返回一行记录(MISSING 也返回, 带原因)。"""
    tf = os.path.join(tmp, item["id"] + ".txt")
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write(item["b"])
    rec = {"id": item["id"], "status": "MISSING", "value": None}
    try:
        d = F.run_knot_classify(tf, CONTEXT, K_S1, os.path.join(tmp, item["id"] + "_readout.json"))
    except Exception as e:
        return {**rec, "why": "chain: %s" % str(e)[:300]}
    with _PUB_LOCK:                                   # cce_full_run.MANIFEST 是模块全局, 发布段串行
        F.MANIFEST = {}
        try:
            F.s2({"cce": d, "text_file": tf, "outdir": tmp, "mode": "reply"})
            F.qualified({"cce": d, "text_file": tf, "outdir": tmp, "mode": "reply"})
        except Exception as e:
            return {**rec, "why": "publish: %s: %s" % (type(e).__name__, str(e)[:200])}
        man = F.MANIFEST
        F.MANIFEST = {}
    s1, s2 = d["stage1"], d["stage2"]
    s2m, q, samp = man["s2_knots"], man["qualified_readout"], s2.get("sampling") or {}
    usable = set(q.get("usable_keys") or [])
    knots = s2.get("knots") or []
    rec.update({"instrument_hash": (s2.get("instrument") or {}).get("instrument_hash"),
                "top1_mode": s2m.get("top1_mode"), "top1_mode_share": s2m.get("top1_mode_share"),
                "top1_stable": s2m.get("top1_stable"), "top1_draws": s2m.get("top1_draws"),
                "n_ok": samp.get("n_ok"), "n_requested": samp.get("n_requested"),
                "knots0": knots[0]["key"] if knots else None,
                "s1_status": s1.get("measurement_status"),
                "s1_k": {k: s1.get(k) for k in ("k_requested", "k_attempted", "k_valid", "k_abstained")},
                "published_rule_Q": "s2.distribution.top1" in usable,
                "published_rule_U": "s2.playbook_primary" in usable,
                "s2_short": q.get("s2_short"),
                "withheld_top1_reason": (q.get("withheld") or {}).get("s2.distribution.top1"),
                "ops": {"s1": _ledger(s1.get("operational")), "s2": _ledger(s2.get("operational"))},
                "draw_top1": [r.get("top1") for r in s2.get("draw_ledger") or []],
                "s1_draw_tops": [dr.get("tops") for dr in s1.get("draws") or []]})
    if q.get("s2_short"):
        return {**rec, "why": "s2_short: %s" % q["s2_short"]}
    rec["status"] = "OK"
    rec["value"] = s2m["top1_mode"] if s2m.get("knots") else "NONE"
    rec["rule_U"] = rec["value"] if rec["published_rule_U"] else "WITHHELD"
    return rec


def shard_items(items, shard):
    """分片 s = 条目文件(sha256(id) 序)第 (s-1)·43+1 … s·43 条。"""
    return items[(shard - 1) * SHARD_SIZE: shard * SHARD_SIZE]


def run(offline, member=None, run_no=None, shard=None, transport=None):
    """一个分片派发。transport: 只许离线(守卫测试换假传输)。返回 (result, fake_or_None)。"""
    assert offline or transport is None
    got = _sha(PREREG)
    if got != PREREG_SHA256:
        raise SystemExit("★ 预注册被改过(sha256 %s != 钉住的 %s) —— 拒跑" % (got[:16], PREREG_SHA256[:16]))
    if _sha(ITEMS) != ITEMS_SHA256:
        raise SystemExit("★ 条目文件被改过(sha256 != 钉住的 %s) —— 拒跑" % ITEMS_SHA256[:16])
    bad = [k for k in REFUSE_ENV if os.environ.get(k)]
    if bad:
        raise SystemExit("★ 预注册要求生产默认参数, 但环境里设了 %s —— 拒跑" % bad)
    member = member or os.environ.get("GP_MODEL", "M3" if offline else "")
    raw = str(run_no or os.environ.get("GP_RUN", "1" if offline else ""))
    run_no = int(raw) if raw.isdigit() else None
    if run_no not in RUNS:
        raise SystemExit("★ GP_RUN 必须是 1 或 2, 得到 %r —— 拒跑" % raw)
    raw = str(shard or os.environ.get("GP_SHARD", "1" if offline else ""))
    shard = int(raw) if raw.isdigit() else None
    if shard not in SHARDS:
        raise SystemExit("★ GP_SHARD 必须是 1 或 2, 得到 %r —— 拒跑" % raw)
    taxo = _load("config/knot_taxonomy.json")
    if taxo.get("version") != "1.3.1":
        raise SystemExit("★ 分类学版本 %r != 1.3.1 —— 拒跑" % taxo.get("version"))
    if not S.layer_status(instrument_hash=PROD_HASH)["top1"]["usable"]:
        raise SystemExit("★ 生产 K1 top-1 路由已关 —— 生产不再发布 top-1, 本闸无对象")
    items = shard_items(json.loads(ITEMS.read_text(encoding="utf-8")), shard)
    import calibration_framework as CF
    saved = {"model": K.MEASUREMENT_MODEL, "requests": X.requests, "reserve": X.reserve_in_scope,
             "subprocess": F.subprocess, "raw": K.RAW_DIR, "log": CF.JSON_FAIL_LOG, "models": dict(X.MODELS),
             "key": os.environ.get("MINIMAX_API_KEY")}
    tmp = tempfile.mkdtemp(prefix="gate_gp_")
    gh = (not offline) and bool(os.environ.get("GITHUB_ACTIONS"))
    state = (os.path.join(tmp, "budget.json") if offline else
             "/tmp/gate_gp_%s_r%d_s%d_budget.json" % (member, run_no, shard) if gh else
             str(ROOT / ("results/gate_gp/gate_gp_%s_r%d_s%d_budget.json" % (member, run_no, shard))))
    lock, errs, flags = threading.Lock(), collections.Counter(), {"budget": None, "wall": False}
    fake = None
    try:
        inst = install_member(member)
        if offline:
            fake = transport or _FakeRequests(member, run_no)
            X.requests = fake                          # 离线: 连包装层一起换成假的, 一次都不出网
            os.environ["MINIMAX_API_KEY"] = "offline-dry-run"
            K.RAW_DIR = os.path.join(tmp, "raw")
            CF.JSON_FAIL_LOG = os.path.join(tmp, "json_extract_failures.log")
        else:
            X.requests = _Transport(saved["requests"], errs, lock)
        orig_reserve = saved["reserve"]

        def reserve(note=""):
            try:
                return orig_reserve(note)
            except B.BudgetExceeded as e:
                with lock:
                    flags["budget"] = flags["budget"] or str(e)[:200]
                raise
        X.reserve_in_scope = reserve
        F.subprocess = _InProcess()
        pathlib.Path(state).parent.mkdir(parents=True, exist_ok=True)
        scope = B.open_scope(SCOPE_LABEL % (member, run_no, shard), CAP, state)
        out = {"block": "GATE_GP_DISPATCH_RESULT", "prereg_sha256": got, "items_sha256": ITEMS_SHA256,
               "member": member, "api_model": PANEL[member], "run": run_no, "shard": shard, "context": CONTEXT,
               "k": K_S1, "knot_n": K.KNOT_N, "instrument_hash": inst["instrument_hash"],
               "spec_minus_model_sha": spec_minus_model_sha(inst), "cap": CAP, "planned": PLANNED,
               "scope_id": scope, "offline_dry_run": offline, "github_run_id": os.environ.get("GITHUB_RUN_ID"),
               "started_at_utc": _now(), "item_ids": [x["id"] for x in items]}
        rows, t0 = {}, time.time()

        def one(it):
            if flags["budget"] or time.time() - t0 > WALL_SEC:
                flags["wall"] = flags["wall"] or (not flags["budget"])
                return {"id": it["id"], "status": "MISSING", "value": None,
                        "why": "NOT_RUN: " + ("BUDGET_STOP" if flags["budget"] else "WALL_CLOCK")}
            try:
                return readout(it, tmp)
            except Exception as e:          # 探针自身的错也只毁这一格, 记成 MISSING 并点名(覆盖率闸会看见)
                return {"id": it["id"], "status": "MISSING", "value": None,
                        "why": "probe_error: %s: %s" % (type(e).__name__, str(e)[:200])}

        with ThreadPoolExecutor(max_workers=ITEM_WORKERS) as ex:
            for it, r in zip(items, ex.map(one, items)):
                rows[it["id"]] = r
        used = (B.scope_status() or {}).get("used")
    finally:
        K.MEASUREMENT_MODEL, X.requests, X.reserve_in_scope = saved["model"], saved["requests"], saved["reserve"]
        F.subprocess, K.RAW_DIR, CF.JSON_FAIL_LOG, F.MANIFEST = saved["subprocess"], saved["raw"], saved["log"], {}
        X.MODELS.clear(); X.MODELS.update(saved["models"])
        for k in (B.SCOPE_ID, B.SCOPE_LIMIT, B.SCOPE_STATE):
            os.environ.pop(k, None)
        if offline:
            if saved["key"] is None:
                os.environ.pop("MINIMAX_API_KEY", None)
            else:
                os.environ["MINIMAX_API_KEY"] = saved["key"]
    readouts = [rows[x["id"]] for x in items]
    cov = sum(1 for r in readouts if r["status"] == "OK")
    reasons = (["BUDGET_STOP: %s" % flags["budget"]] if flags["budget"] else []) + \
              (["coverage %d/%d < %d" % (cov, len(items), MIN_COVERAGE)] if cov < MIN_COVERAGE else [])
    out.update({"readouts": readouts, "coverage": cov, "budget_stop": bool(flags["budget"]),
                "wall_clock_stop": bool(flags["wall"]), "http_attempts": used,
                "http_errors_by_model_and_code": dict(sorted(errs.items())),
                "★operational": {"item_workers": ITEM_WORKERS, "http_concurrency": HTTP_CONCURRENCY,
                                 "backoff_base_sec": BACKOFF_BASE_SEC, "wall_sec": WALL_SEC,
                                 "budget_state": state, "transport": "offline_fake" if offline else "production_call_model+shim"},
                "finished_at_utc": _now(), "dispatch_valid": not reasons, "invalid_reasons": reasons,
                "verdict": "BUDGET_STOP" if flags["budget"] else ("DISPATCH_INVALID" if reasons else "DISPATCH_COMPLETE")})
    return out, fake


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    res, _ = run(offline)
    print(json.dumps({k: res[k] for k in ("member", "run", "shard", "offline_dry_run", "instrument_hash", "verdict", "dispatch_valid",
                                          "invalid_reasons", "coverage", "http_attempts", "http_errors_by_model_and_code")},
                     ensure_ascii=False, indent=1))
    print("取值分布:", dict(collections.Counter(r["value"] for r in res["readouts"])))
    if offline:
        sys.exit(0)
    d = pathlib.Path("/tmp") if os.environ.get("GITHUB_ACTIONS") else ROOT / "results/gate_gp"   # probe.yml 的 artifact 只收 /tmp/*.json
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("gate_gp_%s_r%d_s%d_result.json" % (res["member"], res["run"], res["shard"]))
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("写入", p)
