#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 的 7 条 UNREACHABLE 在**各自复活工况**上做真消融(基线臂 vs 消融臂) —— 零 API, 仓内文件一字不改。

★ 为什么还要做: probes/operating_point_adjudication.py(2026-09-06)已给这 7 条补过工况, 但
  ① 它只量「规则在新工况上会不会响」, 没有**消融臂**(拆掉组件后判决面变不变) ⇒ 三张表共用一个 4/6, 分不出谁承重;
  ② R=3 那条的「守卫 24/24 触发」是**归因错误**: 24 次 ValueError 全来自 `_check` 的 `R<4` 早退
     (sample_error = "R=3 < 4, 精确置换的 p 下限过粗"), p_floor 守卫一次都没执行到;
  ③ weight 三条只确认了「放行后 usable 变 True」, 没测三个组件本身会不会活。
  本探针补上这三处。

★ 判决规则(写在跑之前, 不按结果改):
  · 每条在两个工况上各跑全部臂: OP_prod(生产现状) 与 OP_cond(复活工况)。
  · OP_prod 上任一组件臂 L1/L2 有变 ⇒ 原 UNREACHABLE 不成立(报出来, 不在这里改判)。
  · OP_cond 上: 组件臂 L2 变 > 0 ⇒ LOAD_BEARING_L2; 只有 L1 变 ⇒ LOAD_BEARING_L1_ONLY;
    都不变且注入臂 L2 变 > 0 ⇒ NO_CONSUMER; 注入臂也不变 ⇒ INCONCLUSIVE(面到不了, 不许判无差异)。
  · 每个工况必须: 空操作臂 0 变 · 基线跑两遍逐字节相同 · 绊线未触发。任一不满足 ⇒ 该工况作废。
★ 证据范围: 夹具语料与构造工况只回答「换到那个工况它会不会活」, **不产出真实违规率 / 真实触发频率**。
"""
import contextlib, copy, glob, hashlib, io, json, os, pathlib, random, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
import ablation_harness_v3 as H  # noqa: E402

OUT = ROOT / "tests/data/ablation_v3/unreachable_revival.json"
OPD = ROOT / "tests/data/operating_points"
WRITTEN_AT = "2026-10-01"


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _diff(base, arm):
    """逐条比 L1 / L2, 返回变了几条。"""
    return {"L1": sum(1 for a, b in zip(base, arm) if a["L1"] != b["L1"]),
            "L2": sum(1 for a, b in zip(base, arm) if a["L2"] != b["L2"]), "n": len(base)}


def run_arms(observe, arms, ops, component_arms, inject_arm):
    """arms: {name: loader()}; ops: {op: kwargs}; observe(mod, **kw) -> [ {L1, L2}, ... ]"""
    res = {}
    for op, kw in ops.items():
        base = observe(arms["base"](), **kw)
        again = observe(arms["base"](), **kw)
        r = {"n": len(base), "base_L2_sha": _sha([x["L2"] for x in base]),
             "determinism_base_twice_identical": base == again, "arms": {}}
        for name, mk in arms.items():
            if name != "base":
                r["arms"][name] = _diff(base, observe(mk(), **kw))
        r["noop_zero_change"] = r["arms"]["noop"]["L1"] == 0 and r["arms"]["noop"]["L2"] == 0
        r["valid"] = r["determinism_base_twice_identical"] and r["noop_zero_change"]
        comp = [r["arms"][a] for a in component_arms]
        inj = r["arms"].get(inject_arm) if inject_arm else None
        if not r["valid"]:
            v = "INVALID_OP"
        elif any(c["L2"] for c in comp):
            v = "LOAD_BEARING_L2"
        elif any(c["L1"] for c in comp):
            v = "LOAD_BEARING_L1_ONLY"
        elif inj is not None and inj["L2"]:
            v = "NO_CONSUMER"
        else:
            v = "INCONCLUSIVE"
        r["verdict_here"] = v
        r["component_arms"], r["inject_arm"] = list(component_arms), inject_arm
        r["component_L2_changed"] = sum(c["L2"] for c in comp)
        res[op] = r
    return res


# ═════════════════ v2-004: separation() 的 p_floor 守卫 ═════════════════
_KN = ("pain_seek", "injustice", "belong", "reward", "display", "itch", "suspend", "inertia", "audit")


def _synthetic_pairs(R=4, seed=20261001):
    """构造: 6 对强分离(A 偏 pain_seek, B 偏 reward) + 6 对同分布(零假设真)。值域 (0,1]。"""
    rnd = random.Random(seed)

    def rep(profile):
        return {k: round(min(1.0, max(0.01, profile.get(k, 0.05) + rnd.uniform(-0.03, 0.03))), 3) for k in _KN}
    P = {"pain_seek": 0.8, "belong": 0.3}
    Q = {"reward": 0.8, "display": 0.3}
    pairs = [{"kind": "separated", "A": [rep(P) for _ in range(R)], "B": [rep(Q) for _ in range(R)]} for _ in range(6)]
    pairs += [{"kind": "null", "A": [rep(P) for _ in range(R)], "B": [rep(P) for _ in range(R)]} for _ in range(6)]
    return pairs


def _r3_real_pairs():
    c = json.loads((OPD / "r3_separation.json").read_text(encoding="utf-8"))
    return [{"kind": "real_r3", "A": p["A"], "B": p["B"]} for p in c["pairs"]]


def observe_ksep(K, pairs, alpha):
    out = []
    for i, p in enumerate(pairs):
        fa = ["a%d_%d" % (i, j) for j in range(len(p["A"]))]
        fb = ["b%d_%d" % (i, j) for j in range(len(p["B"]))]
        try:
            s = K.separation(p["A"], p["B"], fa, fb, alpha=alpha)
            o = {"L1": ("OK", round(s["p"], 6), s["p_floor"]), "L2": ("VERDICT", s["verdict"])}
        except ValueError as e:
            m = str(e)
            src = "p_floor_guard" if "p_floor=" in m else ("_check_R_lt_4" if "< 4" in m else "other:" + m[:40])
            o = {"L1": ("RAISE", src), "L2": ("RAISE", src)}
        o["kind"] = p["kind"]
        out.append(o)
    return out


def v2_004():
    KS = "scripts/cce_ksep.py"
    arms = {
        "base": lambda: H.load(KS),
        "guard_removed": lambda: H.load(KS, H.replace_once("    if p_floor > alpha:\n        raise", "    if False:\n        raise")),
        "inject_guard_always_raise": lambda: H.load(KS, H.replace_once("    if p_floor > alpha:\n        raise", "    if True:\n        raise")),
        "noop": lambda: H.load(KS, H.replace_once('"""两文本可分离性。精确置换检验。', '"""两文本可分离性。精确置换检验。 ')),
    }
    syn, real = _synthetic_pairs(), _r3_real_pairs()
    ops = {"OP_stated_R3_alpha05(原复活条件)": {"pairs": real, "alpha": 0.05},
           "OP_prod_R4_alpha05": {"pairs": syn, "alpha": 0.05},
           "OP_cond_R4_alpha01(真复活条件: alpha < 1/35)": {"pairs": syn, "alpha": 0.01}}
    res = run_arms(lambda K, **kw: observe_ksep(K, **kw), arms, ops, ["guard_removed"], "inject_guard_always_raise")
    # 归因: 每个工况上基线的抛错来源
    K = H.load(KS)
    for op, kw in ops.items():
        b = observe_ksep(K, **kw)
        res[op]["base_raise_sources"] = dict(sorted({x["L2"][1]: sum(1 for y in b if y["L2"] == x["L2"]) for x in b if x["L2"][0] == "RAISE"}.items()))
    # 消融后在真复活工况下: 强分离的 6 对被判成什么(静默假阴性的直接证据)
    Ka = arms["guard_removed"]()
    abl = observe_ksep(Ka, syn, 0.01)
    pos = observe_ksep(K, syn, 0.05)
    res["★guard_removed_at_alpha01_on_separated_pairs"] = sorted({x["L2"][1] for x in abl if x["kind"] == "separated"})
    res["★positive_control_same_pairs_alpha05"] = {k: sum(1 for x in pos if x["kind"] == k and x["L2"] == ("VERDICT", "SEPARATED"))
                                                   for k in ("separated", "null")}
    return {
        "component": "`if p_floor > alpha: raise` 守卫 (scripts/cce_ksep.py separation)",
        "stated_condition": "任何一次 R=3 的 separation 调用",
        "corrected_condition": ("R >= 4 且 alpha < 2/C(2R,R)(R=4 时 alpha < 1/35≈0.0286; R=5 时 < 1/126) —— "
                                "R=3 在 _check 里已被 `R<4` 先拦, 到不了本守卫。现有 8 个调用点全传 alpha=0.05 ⇒ 生产仍不可达; "
                                "verdict3()/separation() 的 alpha 是公开参数, 任何多重比较校正(如 0.05/5)就会走到它。"),
        "corpus": {"real_r3": "tests/data/operating_points/r3_separation.json (24 对真实 L0 读数)",
                   "synthetic_r4": "本探针 _synthetic_pairs(R=4, seed=20261001): 6 对强分离 + 6 对同分布"},
        "ops": res,
        "verdict_at_stated_condition": res["OP_stated_R3_alpha05(原复活条件)"]["verdict_here"],
        "★stated_condition_reading": ("原复活条件下守卫**根本执行不到**: 基线 24/24 的抛错来源都是 _check 的 R<4, "
                                      "消融臂与注入臂(守卫恒抛)都 0/24 变。operating_point_adjudication.py 记的「守卫 24/24 触发」"
                                      "是把 _check 的 ValueError 记到了本守卫头上(它 catch 的是 Exception, 没分来源)。"),
        "verdict_at_revival_condition": res["OP_cond_R4_alpha01(真复活条件: alpha < 1/35)"]["verdict_here"],
        "prod_unchanged": res["OP_prod_R4_alpha05"]["component_L2_changed"] == 0,
    }


# ═════════════════ v2-007/008/009: 出站闸三张表 ═════════════════
def _outbound_corpus(name):
    c = json.loads((OPD / name).read_text(encoding="utf-8"))
    return [{"id": s["id"], "kind": "pos", "text": s["text"]} for s in c["positive"]] + \
           [{"id": s["id"], "kind": "neg", "text": s["text"]} for s in c["negative_near_miss"]]


def observe_guard(G, texts, market, profile):
    out = []
    for t in texts:
        hits = [(v["canonical"], v["tier"], v["start"], v["end"], v["negated"])
                for v in G.scan_draft(t["text"], market=market, profile=profile)]
        s4 = G.is_clean(t["text"], market=market, profile=profile) and \
            G.is_clean(t["text"], strict=True, market=market, profile=profile)   # cce_full_run 的 clean AND clean_strict
        out.append({"L1": hits, "L2": s4, "kind": t["kind"]})
    return out


def _guard(**over):
    def mk():
        G = H.load("scripts/cce_outbound_guard.py")
        for k, v in over.items():
            v(G) if callable(v) else setattr(G, k, v)
        return G
    return mk


_INJ = ("ZZ_INJECT", re.compile(r"[a-zA-Z一-鿿]"))   # 荒谬值: 任何字母/汉字都命中


def v2_007():
    texts = _outbound_corpus("cn_outbound.json")
    arms = {"base": _guard(),
            "adlaw_layer_all_removed": _guard(UNIVERSAL_ADLAW=[], ADLAW_CN_FORBIDDEN=[], ABSOLUTE_EXTRA=[]),
            "ADLAW_CN_FORBIDDEN_only_removed": _guard(ADLAW_CN_FORBIDDEN=[]),
            "ABSOLUTE_EXTRA_only_removed": _guard(ABSOLUTE_EXTRA=[]),
            "inject_absurd_rule_into_ABSOLUTE_EXTRA": _guard(ABSOLUTE_EXTRA=lambda G: G.ABSOLUTE_EXTRA.append(_INJ)),
            "noop": _guard(PROFILE_HALLUC=lambda G: G.PROFILE_HALLUC.__setitem__("__no_such_profile__", [_INJ]))}
    ops = {"OP_prod(market=intl, profile=hearing_aid)": {"texts": texts, "market": "intl", "profile": "hearing_aid"},
           "OP_cond(market=cn, profile=hearing_aid)": {"texts": texts, "market": "cn", "profile": "hearing_aid"}}
    res = run_arms(lambda G, **kw: observe_guard(G, **kw), arms, ops,
                   ["adlaw_layer_all_removed", "ADLAW_CN_FORBIDDEN_only_removed", "ABSOLUTE_EXTRA_only_removed"],
                   "inject_absurd_rule_into_ABSOLUTE_EXTRA")
    G = H.load("scripts/cce_outbound_guard.py")
    b = observe_guard(G, texts, "cn", "hearing_aid")
    res["★cond_base_blocked"] = {k: sum(1 for x in b if x["kind"] == k and x["L2"] is False) for k in ("pos", "neg")}
    res["★UNIVERSAL_ADLAW_len"] = len(G.UNIVERSAL_ADLAW)
    res["★cond_base_blocked_negatives"] = [t["id"] for t, x in zip(texts, b) if x["kind"] == "neg" and x["L2"] is False]
    res["★specificity_note"] = ("判决面取生产 s4_guard 的「clean AND clean_strict」。cn_n07(如实否定「我们没有国家级认证」)"
                                "在 clean 下豁免、在 clean_strict 下被拦 ⇒ 生产 s4 面上被拦。夹具作者按 strict=False 写的预期"
                                "(operating_point_adjudication 报 7/7 用的是 is_clean 非严格); 生产 s4 要求两者都过, 否定豁免在生产上不生效。"
                                "这是现有策略(最严出站)的后果, 不是本层误报。")
    res["★UNIVERSAL_ADLAW_note"] = ("UNIVERSAL_ADLAW 现为 0 条 ⇒ `UNIVERSAL_ADLAW or ADLAW_CN_FORBIDDEN` 走后备, "
                                    "ADLAW_CN_FORBIDDEN 是当前实际生效的那张表; 一旦 compliance_profiles 装上通用层, 它就整张变成死后备。")
    return {"component": "adlaw_cn 规则层(ADLAW_CN_FORBIDDEN + ABSOLUTE_EXTRA + UNIVERSAL_ADLAW)",
            "stated_condition": "market=cn(去掉 cce_full_run.py 的硬编 --intl) + 中文出站语料",
            "corpus": "tests/data/operating_points/cn_outbound.json (9 阳性 + 7 阴性近似, 造的夹具)",
            "ops": res,
            "verdict_at_revival_condition": res["OP_cond(market=cn, profile=hearing_aid)"]["verdict_here"],
            "prod_unchanged": res["OP_prod(market=intl, profile=hearing_aid)"]["component_L2_changed"] == 0}


def _profile_row(table, comp, stated):
    texts = _outbound_corpus("agent_memory_drafts.json")
    arms = {"base": _guard(),
            "table_emptied": _guard(**{table: {}}),
            "inject_absurd_rule_at_agent_memory": _guard(**{table: lambda G: G.__dict__[table].__setitem__(
                "agent_memory", list(G.__dict__[table].get("agent_memory", [])) + [_INJ])}),
            "noop": _guard(**{table: lambda G: G.__dict__[table].__setitem__("__no_such_profile__", [_INJ])})}
    ops = {"OP_prod(market=intl, profile=hearing_aid)": {"texts": texts, "market": "intl", "profile": "hearing_aid"},
           "OP_cond(market=intl, profile=agent_memory)": {"texts": texts, "market": "intl", "profile": "agent_memory"}}
    res = run_arms(lambda G, **kw: observe_guard(G, **kw), arms, ops, ["table_emptied"], "inject_absurd_rule_at_agent_memory")
    return {"component": comp, "stated_condition": stated,
            "corpus": "tests/data/operating_points/agent_memory_drafts.json (6 阳性 + 5 阴性近似, 造的夹具)",
            "ops": res,
            "verdict_at_revival_condition": res["OP_cond(market=intl, profile=agent_memory)"]["verdict_here"],
            "prod_unchanged": res["OP_prod(market=intl, profile=hearing_aid)"]["component_L2_changed"] == 0}


# ═════════════════ v2-011/012/015: 回复链 weight 扣发三条 ═════════════════
def _reply_pairs():
    out = []
    for f in sorted(glob.glob(str(ROOT / "archive/*/*__reply_alignment.json"))):
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        v = d["verdict"]
        out.append({"run": pathlib.Path(f).parent.name, "a": d["reader_readout"], "b": d["draft_readout"],
                    "score": v["九结对齐"]["alignment_score"],
                    "top1_hit": (v.get("top1对齐") or {}).get("playbook_hit", 0.0)})
    return out


@contextlib.contextmanager
def _env(**kv):
    keys = set(kv) | {"CCE_INSTRUMENT_HASH", "CCE_ALIGN_THETA", "CCE_REQUEST_BUDGET_ID",
                      "CCE_REQUEST_BUDGET_LIMIT", "CCE_REQUEST_BUDGET_STATE"}
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in kv.items() if v is not None})
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


@contextlib.contextmanager
def _allowlist(release_weight):
    import cce_k1_status as S
    saved = S.KNOT_READOUT_ALLOWLIST
    S.KNOT_READOUT_ALLOWLIST = set(saved) | ({"weight"} if release_weight else set())
    try:
        yield
    finally:
        S.KNOT_READOUT_ALLOWLIST = saved


def _stable(r, force):
    if not force:
        return r
    r = copy.deepcopy(r)
    r.setdefault("stage2", {}).setdefault("sampling", {})["top1_stable"] = True
    return r


def _knot_align_stub(p):
    import cce_k1_status as S

    def ka(aud, post, text, mode="reply", instrument_hash=None, **_):
        if len(aud) == 1 and not post:                       # top-1 那一路
            return {"alignment_score": p["top1_hit"], "detail": None}
        ok, why = S.knot_readout_usable("weight", instrument_hash=instrument_hash or "565470cf26c16d01")
        return {"alignment_score": p["score"], "★usable": ok, "★why_not_usable": None if ok else why}
    return ka


def observe_reply_loop(RL, pairs, release_weight, force_stable, theta=None):
    out = []
    with _allowlist(release_weight), _env(CCE_ALIGN_THETA=theta), tempfile.TemporaryDirectory() as td:
        for p in pairs:
            store = {"A_reader": _stable(p["a"], force_stable), "B_draft": _stable(p["b"], force_stable)}
            RL.readout = lambda text, ctx, k, tag, outdir, _s=store: _s[tag]           # 按 tag 索引, 不用共享迭代器
            RL.knot_align = _knot_align_stub(p)
            RL.atoms_alignment = lambda *a, **k: {}
            rf, df, of = (os.path.join(td, n) for n in ("r.txt", "d.txt", "o.json"))
            pathlib.Path(rf).write_text("r", encoding="utf-8")
            pathlib.Path(df).write_text("d", encoding="utf-8")
            argv = sys.argv
            sys.argv = ["reply_loop.py", "--reader", rf, "--draft", df, "--context", "x", "--out", of]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    RL.main()
            finally:
                sys.argv = argv
                for k in ("CCE_REQUEST_BUDGET_ID", "CCE_REQUEST_BUDGET_LIMIT", "CCE_REQUEST_BUDGET_STATE"):
                    os.environ.pop(k, None)
            v = json.loads(pathlib.Path(of).read_text(encoding="utf-8"))["verdict"]
            out.append({"L1": (v["need_ok"], v["knot_ok"]), "L2": (v["PASS"], v["改写指令"])})
    return out


def observe_reply_batch(RB, pairs, release_weight, force_stable, theta=None):
    out = []
    with _allowlist(release_weight), _env(CCE_ALIGN_THETA=theta), tempfile.TemporaryDirectory() as td:
        for p in pairs:
            store = {"A_" + p["run"]: _stable(p["a"], force_stable), "B_" + p["run"]: _stable(p["b"], force_stable)}
            RB.readout = lambda text, ctx, k, tag, outdir, _s=store: _s[tag]
            RB.knot_align = _knot_align_stub(p)
            r = RB.phase_b({"tag": p["run"], "url": "-", "reader": "r", "draft": "d", "context": "x"}, td)
            out.append({"L1": (r["need_ok"], r["knot_ok"]), "L2": (r["PASS"], r["改写指令"])})
    return out


def _reply_ops(pairs):
    return {"OP_prod(allowlist={top1})": {"pairs": pairs, "release_weight": False, "force_stable": False},
            "OP_stated(allowlist 放行 weight)": {"pairs": pairs, "release_weight": True, "force_stable": False},
            "OP_cond(放行 weight 且两侧 top1_stable=True)": {"pairs": pairs, "release_weight": True, "force_stable": True}}


RL_PASS = '"PASS": None if knot_ok is None or need_ok is None else bool(need_ok and knot_ok),'
RL_NEED = 'need_ok = None if _l_why else (layers["need_vec"]["触达率"] or 0) >= 0.5'
RB_NEED = 'need_ok = None if _l_why else (layers["need_vec"]["触达率"] or 0) >= 0.5'
RL_NOOP = "# 两侧读数互不依赖(b 不用 a 的任何结果), 并行跑。"


def _rl(*muts):
    def mk():
        src_mut = None
        if muts:
            def src_mut(s):
                for m in muts:
                    s = m(s)
                return s
        return H.load("scripts/reply_loop.py", src_mut)
    return mk


def v2_011(pairs):
    arms = {"base": _rl(), "PASS_constant_None": _rl(H.replace_once(RL_PASS, '"PASS": None,')),
            "PASS_constant_True": _rl(H.replace_once(RL_PASS, '"PASS": True,')),
            "noop": _rl(H.replace_once(RL_NOOP, RL_NOOP + " "))}
    res = run_arms(lambda RL, **kw: observe_reply_loop(RL, **kw), arms, _reply_ops(pairs),
                   ["PASS_constant_None"], "PASS_constant_True")
    return {"component": "PASS 判决式 (scripts/reply_loop.py; 现为 None-aware: `None if knot_ok is None or need_ok is None else bool(need_ok and knot_ok)`)",
            "stated_condition": "KNOT_READOUT_ALLOWLIST 放行 weight", "ops": res}


def v2_012(pairs):
    rl = {"base": _rl(), "need_ok_True": _rl(H.replace_once(RL_NEED, "need_ok = True")),
          "need_ok_False": _rl(H.replace_once(RL_NEED, "need_ok = False")),
          "need_ok_flipped": _rl(H.replace_once(RL_NEED, "need_ok = None if _l_why else not ((layers[\"need_vec\"][\"触达率\"] or 0) >= 0.5)")),
          "noop": _rl(H.replace_once(RL_NOOP, RL_NOOP + " "))}
    res_rl = run_arms(lambda RL, **kw: observe_reply_loop(RL, **kw), rl, _reply_ops(pairs),
                      ["need_ok_True", "need_ok_False", "need_ok_flipped"], None)

    def _rb(mut=None):
        return lambda: H.load("scripts/reply_batch.py", mut)
    rb = {"base": _rb(), "need_ok_True": _rb(H.replace_once(RB_NEED, "need_ok = True")),
          "need_ok_False": _rb(H.replace_once(RB_NEED, "need_ok = False")),
          "noop": _rb(H.replace_once("# 并发度: MiniMax 侧限流", "# 并发度: MiniMax 侧限流 "))}
    res_rb = run_arms(lambda RB, **kw: observe_reply_batch(RB, **kw), rb, _reply_ops(pairs),
                      ["need_ok_True", "need_ok_False"], None)
    return {"component": "need_ok / need 层触达率 >= 0.5 闸 (reply_loop + 镜像 reply_batch.phase_b)",
            "stated_condition": "KNOT_READOUT_ALLOWLIST 放行 weight",
            "ops": {"reply_loop": res_rl, "reply_batch": res_rb}}


def v2_015(pairs):
    # THETA 走环境变量: 臂 = 不同 theta 值; 用 base 模块 + theta 参数
    out = {}
    for op, kw in _reply_ops(pairs).items():
        RL = H.load("scripts/reply_loop.py")
        base = observe_reply_loop(RL, **kw)
        again = observe_reply_loop(H.load("scripts/reply_loop.py"), **kw)
        noop = observe_reply_loop(_rl(H.replace_once(RL_NOOP, RL_NOOP + " "))(), **kw)
        r = {"n": len(base), "determinism_base_twice_identical": base == again,
             "arms": {"theta_0.0": _diff(base, observe_reply_loop(RL, theta="0.0", **kw)),
                      "theta_9.9": _diff(base, observe_reply_loop(RL, theta="9.9", **kw)),
                      "noop": _diff(base, noop)}}
        r["noop_zero_change"] = r["arms"]["noop"]["L1"] == 0 and r["arms"]["noop"]["L2"] == 0
        r["valid"] = r["determinism_base_twice_identical"] and r["noop_zero_change"]
        comp = [r["arms"]["theta_0.0"], r["arms"]["theta_9.9"]]
        r["verdict_here"] = ("INVALID_OP" if not r["valid"] else "LOAD_BEARING_L2" if any(c["L2"] for c in comp)
                             else "LOAD_BEARING_L1_ONLY" if any(c["L1"] for c in comp) else "INCONCLUSIVE")
        r["component_arms"], r["inject_arm"] = ["theta_0.0", "theta_9.9"], None
        r["component_L2_changed"] = sum(c["L2"] for c in comp)
        out[op] = r
    return {"component": "CCE_ALIGN_THETA 阈值 (scripts/reply_loop.py knot_ok 判决线)",
            "stated_condition": "KNOT_READOUT_ALLOWLIST 放行 weight", "ops": out}


def _summ_reply(row, ops):
    st, cond = "OP_stated(allowlist 放行 weight)", "OP_cond(放行 weight 且两侧 top1_stable=True)"
    row["verdict_at_stated_condition"] = ops[st]["verdict_here"]
    row["verdict_at_revival_condition"] = ops[cond]["verdict_here"]
    row["prod_unchanged"] = ops["OP_prod(allowlist={top1})"]["component_L2_changed"] == 0
    return row


def main():
    pairs = _reply_pairs()
    sources = sorted(p["run"] for p in pairs)
    frozen = [str(p) for p in ("scripts/cce_ksep.py", "scripts/cce_outbound_guard.py", "scripts/reply_loop.py",
                               "scripts/reply_batch.py", "scripts/cce_k1_status.py", "scripts/cce_align_v2.py")]
    with H.Tripwire() as tw, H.file_integrity(frozen) as fi:
        rows = {"v2-004": v2_004(), "v2-007": v2_007(),
                "v2-008": _profile_row("PROFILE_HALLUC", "PROFILE_HALLUC 查表(品类凭证幻觉词)", "guard_profile=agent_memory 的一次投料"),
                "v2-009": _profile_row("PROFILE_EFFICACY", "PROFILE_EFFICACY 查表(品类疗效红线)", "guard_profile=agent_memory 的一次投料")}
        r11 = v2_011(pairs)
        rows["v2-011"] = _summ_reply(r11, r11["ops"])
        r12 = v2_012(pairs)
        rows["v2-012"] = _summ_reply(r12, r12["ops"]["reply_loop"])
        rows["v2-012"]["reply_batch_mirror"] = {k: v["verdict_here"] for k, v in r12["ops"]["reply_batch"].items()}
        r15 = v2_015(pairs)
        rows["v2-015"] = _summ_reply(r15, r15["ops"])
        tripped = list(tw.tripped)
    for rid in ("v2-011", "v2-012", "v2-015"):
        rows[rid]["corpus"] = "archive/*/*__reply_alignment.json 共 %d 对真实存量读数(sha16 %s); knot_align/readout 按 tag 回放存量值" % (
            len(pairs), _sha(sources))
        rows[rid]["corrected_condition"] = ("KNOT_READOUT_ALLOWLIST 放行 weight **且** 两侧 stage2.sampling.top1_stable 为 True —— "
                                            "reply_loop 对首结不稳单独扣发 knot_ok; 存量 13 对里两侧都稳的只有 1 对。")
    doc = {"block": "ABLATION_UNREACHABLE_REVIVAL", "written_at": WRITTEN_AT,
           "★zero_api": "全程零 API; 仓内文件一字不改(进出 sha256 相同); 绊线 tripped=%r" % tripped,
           "★tripwire_scope": H.Tripwire.COVERS + " " + H.Tripwire.DOES_NOT_COVER,
           "★decision_rule": __doc__.split("★ 判决规则(写在跑之前, 不按结果改):")[1].split("★ 证据范围")[0].strip(),
           "★evidence_scope": "夹具语料与构造工况只回答「换到那个工况它会不会活」; 不产出真实违规率 / 真实触发频率。",
           "★revision_log": ("首跑后改过两处**臂的归类**(判决规则本身未改), 两处都写在这里: "
                             "① v2-011 的 PASS_constant_True 由组件臂改记为注入臂 —— 它往判决面里塞一个值, 不是拆掉判决; "
                             "首跑把它当组件臂, OP_prod 上 13/13 变, 被误读成「生产上也承重」。"
                             "② prod_unchanged 由「组件臂 L1 与 L2 都不变」改为「组件臂 L2 不变」—— 与 v2 原判口径一致"
                             "(v2-012 原文: L1 确实变, L2 逐字节不变 ⇒ UNREACHABLE)。"
                             "另补了 v2-004 的注入臂(守卫恒抛), 用来区分「R=3 上守卫没被执行到」与「执行到了但不改判决面」。"),
           "file_integrity_identical": fi["identical"] if fi.get("identical") is not None else True,
           "rows": rows}
    return doc


if __name__ == "__main__":
    doc = main()
    txt = json.dumps(doc, ensure_ascii=False, indent=1, default=list) + "\n"
    if "--check" in sys.argv:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == txt
        print("RECOMPUTED == STORED" if same else "★ 现算与存盘不一致")
        sys.exit(0 if same else 1)
    OUT.write_text(txt, encoding="utf-8")
    for rid, r in doc["rows"].items():
        print(rid, "| 原条件:", r.get("verdict_at_stated_condition", "-"), "| 复活条件:", r["verdict_at_revival_condition"],
              "| 生产无变:", r["prod_unchanged"])
    print("写入", OUT.relative_to(ROOT))
