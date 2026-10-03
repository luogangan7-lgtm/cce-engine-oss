#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-K1 v3 预注册守卫(2026-10-03)。只跑 --offline 与合成数据, 零网络。

守: ① 预注册 sha 钉在探针(分析器用同一常量) ② 上限 470 / 计划 430 / 授权单按 occasion 唯一
    ③ 新条目 81 条 == select_fresh()(选样可复现), sha 钉, 与 corpus.json / 锚例零重叠(id 与正文), 无用户名提及, 只 id/a/post/b
    ④ 离线干跑 occasion 1..4: 每次 405 标注 + 25 资格考, 尝试 <= 470, 交给分析器出 ADJUDICATED
    ⑤ 分析器在合成数据上分出 PASS / FAIL / UNRESOLVED; 交叉自助看得见运行间方差
    ⑥ 少于 4 个有效 occasion 不出判定; 替补 / 重复派发按 S3/S4 机械挑选; 完整性不符拒收
    ⑦ 分析器 js_div == run_gates.js_div ⑧ 设计规格过 design_preflight ⑨ 预注册数字 == 代码常量
反向(改坏必须红): 预注册 sha 不符 · 新条目被改 · 上限压低 · 预设刺激 · occasion 越界 · 解析失败 ⇒ 无效 ·
    分析器 6 条变异(去掉运行重采样 / P4 混入 Text-01 / 去掉「<4 不判」/ 去掉 top-2 合取 / 替补不限位 / 不查覆盖率)。
"""
import hashlib, json, os, pathlib, random, re, socket, sys, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
_TRIPPED = []
_orig = socket.socket.connect
def _guard(s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (addr,))
socket.socket.connect = _guard

import accuracy_gk1_v3_run as G       # noqa: E402
import accuracy_gk1_v3_analyze as A   # noqa: E402
import design_preflight as DP         # noqa: E402

AN_PATH = ROOT / "probes/accuracy_gk1_v3_analyze.py"


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _refuses(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


def _reverse(name, ok):
    assert ok, "★★★ 反向没见红: %s" % name
    print("  反向见红 ✓", name)


# ── ① ② ⑨ 预注册钉与常量 ──
pre = json.loads(G.PREREG.read_text(encoding="utf-8"))
assert _sha(G.PREREG) == G.PREREG_SHA256, "★ 预注册被改过而探针钉住的 sha 没跟 —— 预注册必须跑前冻结"
assert A.RUN is G, "★ 分析器必须与探针共用同一份钉住的常量"
b = pre["budget"]
assert G.CAP == b["per_dispatch_hard_cap_requests"] == 470 and G.PLANNED == b["calls_planned_per_dispatch"] == 430 <= G.CAP
assert b["retry_slack"] == G.CAP - G.PLANNED and b["auth_id"].startswith(G.AUTH_PREFIX)
assert len({G.AUTH_PREFIX + str(k) for k in G.OCCASIONS}) == 6 and list(G.OCCASIONS) == [1, 2, 3, 4, 5, 6]
assert pre["panels"]["P4_primary"]["members"] == A.P4 and pre["panels"]["P5_comparison"]["members"] == A.P5 == list(G.MODELS)
assert "MiniMax-Text-01" not in A.P4 and "不是" in pre["panels"]["P4_primary"]["why_Text01_not_in_P4"]
assert pre["basis"]["owner_ruling"]["date"] == "2026-10-03"
assert (pre["bootstrap"]["B"], pre["bootstrap"]["seed"]) == (A.B_BOOT, A.SEED) == (10000, 20261003)
assert "xs[9499]" in pre["bootstrap"]["bounds"] and "xs[500]" in pre["bootstrap"]["bounds"]
assert (pre["stimulus"]["gate_protocol"]["version"], pre["stimulus"]["gate_protocol"]["hash"]) == G.GATE_PROTOCOL
man = json.loads((ROOT / "config/cce_core_manifest.json").read_text(encoding="utf-8"))["gate_protocol_expected"]
assert (man["version"], man["hash"]) == G.GATE_PROTOCOL, "★ 闸协议已换代 ⇒ 本预注册不再适用"
assert (A.THR, A.TOP2_THR, A.R_NEED, G.MIN_COVERAGE) == (0.25, 0.80, 4, 73)
assert "U(μ_D) <= 0.25" in pre["decision"]["JS_three_state"]["PASS"] and ">= 73/81" in pre["occasion_validity"]["valid_iff"]
print("预注册: sha 钉 / 上限 470(计划 430) / 面板 / 自助 B·seed / 闸协议 / 阈值 —— 全一致")

# ── ③ 新条目 ──
items = json.loads(G.FRESH.read_text(encoding="utf-8"))
assert _sha(G.FRESH) == G.FRESH_SHA256, "★ 新条目文件被改过而钉住的 sha 没跟"
assert _sha(G.SOURCE) == pre["items"]["source"]["sha256"], "★ 源池文件变了 ⇒ 选样不可复现"
for p, s in pre["items"]["exclusion_sources"].items():
    assert _sha(ROOT / p) == s, "★ 排除集 %s 变了" % p
assert items == G.select_fresh(), "★ 新条目与按预注册规则现算的不一致 —— 选样不可复现"
assert len(items) == pre["items"]["n"] == 81 and len({x["id"] for x in items}) == 81
assert len({x["b"].strip() for x in items}) == 81 and all(set(x) == {"id", "a", "post", "b"} for x in items)
corpus = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
anchors = json.loads((ROOT / "accuracy/data/anchors.json").read_text(encoding="utf-8"))


def check_disjoint(its):
    ids, bodies = {x["id"] for x in its}, {x["b"].strip() for x in its}
    hit = (ids & ({x["id"] for x in corpus} | set(anchors["anchor_ids"]))) | (bodies & {x["b"].strip() for x in corpus})
    assert not hit, "★ 新条目与旧语料/锚例重叠: %r" % sorted(hit)[:3]
    assert not any(re.search(r"\bu/\w+|/user/\w+", x["b"]) for x in its), "★ 新条目带用户名提及"
    assert all(25 <= len(x["b"].strip()) <= 900 for x in its)


check_disjoint(items)
h = lambda i: hashlib.sha256(i.encode()).hexdigest()
assert [h(x["id"]) for x in items] == sorted(h(x["id"]) for x in items)
src = json.loads(G.SOURCE.read_text(encoding="utf-8"))["users"]
assert all(any(c["id"] == x["id"] and c["b"] == x["b"] and c["p"] == x["post"] for c in src[x["a"]]) for x in items), \
    "★ 新条目字段不是源文件原样(化名键/正文/帖子 id)"
overlap = [{"id": c["id"], "b": c["b"]} for cs in src.values() for c in cs if c["id"] in {x["id"] for x in corpus}]
assert overlap, "源池里应有进过旧语料的条目, 否则下面的反向检查是空的"
try:
    check_disjoint(items[:80] + overlap[:1])
    caught = False
except AssertionError as e:
    caught = "重叠" in str(e)
_reverse("新条目混入一条进过 corpus.json 的评论 ⇒ 被抓", caught)
print("新条目: 81 条 == 规则现算, sha 钉, 与 corpus/锚例零重叠, 字段原样")

# ── ④ 离线干跑 4 个 occasion ──
dry = []
for k in (1, 2, 3, 4):
    r, rep = G.run(offline=True, occasion=k)
    assert r["verdict"] == "OCCASION_COMPLETE" and r["occasion_valid"] and r["offline_dry_run"] is True, r["invalid_reasons"]
    assert r["logical_calls"] == {"dist": 405, "qualify": 25} and 430 <= r["http_attempts"] <= G.CAP, r["logical_calls"]
    assert r["auth_id"] == G.AUTH_PREFIX + str(k) and len(rep["calls"]) == 430
    assert all(v["state"] for v in r["qualification_descriptive_only"].values())
    dry.append(r)
_reverse("离线干跑结果不许当真实数据(allow_offline=False) ⇒ 拒收", _refuses(lambda: A.analyze(dry)))
ad = A.analyze(dry, allow_offline=True)
assert ad["status"] == "ADJUDICATED" and ad["G_K1_v3_verdict_P4"] in ("PASS", "FAIL", "UNRESOLVED")
assert ad["P4_primary"]["n_cells"] == 81 * 4 and set(ad["prediction_outcomes"]) >= {"Pr1_P4_PASS", "Pr8_four_planned_occasions_valid"}
print("离线干跑: 4 个 occasion × 430 次(405 标注 + 25 资格考), 分析器 ADJUDICATED")

saved = G.PREREG_SHA256
G.PREREG_SHA256 = "0" * 64
try:
    _reverse("预注册 sha 不符 ⇒ 拒跑", _refuses(lambda: G.run(offline=True, occasion=1)))
finally:
    G.PREREG_SHA256 = saved
saved = G.FRESH_SHA256
G.FRESH_SHA256 = "0" * 64
try:
    _reverse("新条目文件 sha 不符 ⇒ 拒跑", _refuses(lambda: G.run(offline=True, occasion=1)))
finally:
    G.FRESH_SHA256 = saved
os.environ["CCE_BODY_CHARS"] = "500"
try:
    _reverse("预设刺激环境变量 ⇒ 拒跑", _refuses(lambda: G.run(offline=True, occasion=1)))
finally:
    os.environ.pop("CCE_BODY_CHARS")
for bad in (0, 7):
    _reverse("occasion=%d 越界 ⇒ 拒跑" % bad, _refuses(lambda: G.run(offline=True, occasion=bad)))
os.environ.pop("GK1_V3_OCCASION", None)
_reverse("真跑不给 GK1_V3_OCCASION ⇒ 拒跑(在取 key 之前)", _refuses(lambda: G.run(offline=False)))
G.CAP = 100
try:
    r = G.run(offline=True, occasion=1)[0]
    _reverse("上限压到 100 ⇒ BUDGET_STOP 且 occasion 无效",
             r["verdict"] == "BUDGET_STOP" and not r["occasion_valid"] and r["http_attempts"] <= 100)
finally:
    G.CAP = 470
base_fake = G._fake(1)


def flaky(model, prompt):   # Text-01 约四分之一条目回空或回怪形状 JSON(annot_dist 会抛) ⇒ 可解析 < 73/81
    k = int(h(prompt.split("【")[-1]), 16) % 8
    if model == "MiniMax-Text-01" and "★示范锚例" not in prompt and k in (0, 4):
        return "" if k == 0 else '{"knots": ["display"]}'
    return base_fake(model, prompt)


r = G.run(offline=True, occasion=1, responses=flaky)[0]
_reverse("Text-01 大面积解析失败(含 annot_dist 抛异常的格) ⇒ OCCASION_INVALID_PARSE, 不崩",
         r["verdict"] == "OCCASION_INVALID_PARSE" and r["coverage"]["MiniMax-Text-01"] < 73 and not r["occasion_valid"]
         and r["parse_exceptions"].get("MiniMax-Text-01:AttributeError", 0) > 0 and r["coverage"]["MiniMax-M3"] == 81)
flaky_r = r

# ── ⑤ ⑥ 分析器: 合成数据 ──
KN = ("display", "pain_seek", "reward", "itch", "audit")
X, Y = {"display": 0.9, "reward": 0.1}, {"reward": 0.9, "display": 0.1}     # 互为 top-2, JS = 0.531


def synth(occ, fn, started=None):
    return {"block": "GK1_V3_OCCASION_RESULT", "prereg_sha256": G.PREREG_SHA256, "fresh81_sha256": G.FRESH_SHA256,
            "occasion": occ, "offline_dry_run": True, "github_run_id": None,
            "started_at_utc": started or "2026-10-04T0%d:00:00+00:00" % occ,
            "run_params": {"gate_protocol_version": G.GATE_PROTOCOL[0], "gate_protocol_hash": G.GATE_PROTOCOL[1],
                           "CCE_BODY_CHARS": 700, "CCE_UNIT_LABEL": "评论"},
            "panel": list(A.P5), "item_ids": list(A.IDS), "annotation_complete": True,
            "dists": {m: {i: fn(mi, j, occ) for j, i in enumerate(A.IDS)} for mi, m in enumerate(A.P5)}}


def split_first(n):
    """前 n 条: P4 两两分裂(0,1 → X; 2,3 → Y), 其余全一致; Text-01 跟 0 号。d = 4/6 × 0.531 = 0.354。"""
    return lambda mi, j, occ: dict(Y if (j < n and mi in (2, 3)) else X)


def run_set(fn, occs=(1, 2, 3, 4), an=A):
    return an.analyze([synth(k, fn) for k in occs], allow_offline=True)


assert abs(A.js_div(X, Y) - 0.531) < 1e-3
SETS = {"PASS": split_first(20), "UNRESOLVED": split_first(57), "FAIL": split_first(81)}
for want, fn in SETS.items():
    o = run_set(fn)
    p4 = o["P4_primary"]
    assert o["G_K1_v3_verdict_P4"] == p4["verdict"] == p4["JS_three_state"] == want, (want, p4)
    print("  合成 %-10s μ_D=%.4f  [L, U]=[%.4f, %.4f]" % (want, p4["mu_D"], p4["mu_D_L95_one_sided"], p4["mu_D_U95_one_sided"]))
assert run_set(SETS["PASS"])["P4_primary"]["mu_D_U95_one_sided"] <= 0.25 < run_set(SETS["FAIL"])["P4_primary"]["mu_D_L95_one_sided"]


def occasion_driven(mi, j, occ):    # 运行 1,2 全一致, 3,4 全分裂 ⇒ 条目方差 0, 运行方差大
    return dict(Y if (occ >= 3 and mi in (2, 3)) else X)


od = run_set(occasion_driven)["P4_primary"]
assert od["JS_three_state"] == "UNRESOLVED" and od["mu_D_U95_one_sided"] > 0.25, od   # 只重采样条目会得 U = μ = 0.177 ⇒ PASS


def text01_diverges(mi, j, occ):   # 同伴一致; Text-01 把 display 判成 pain_seek、pain_seek 判成 audit
    base = KN[j % 3]
    if mi == 4 and base in ("display", "pain_seek"):
        return {"pain_seek" if base == "display" else "audit": 1.0}
    return {base: 0.9, "itch": 0.1}


td = run_set(text01_diverges)
assert td["G_K1_v3_verdict_P4"] == "PASS" and td["P5_comparison_only"]["verdict"] != "PASS", td["P5_comparison_only"]
t = td["text01_out_of_sample"]
assert t["T1_verdict"] == "REPLICATED" and t["T2_verdict"] == "DIRECTION_REPLICATED", t
assert td["P5_minus_P4"]["xs500_xs9499"][0] > 0
assert run_set(SETS["PASS"])["text01_out_of_sample"]["T1_verdict"] == "NOT_REPLICATED"


def top2_miss(mi, j, occ):         # 前 33 条: 0,2 号 {display .34, reward .33, itch .33}, 1,3 号 {audit .34, reward .33, itch .33}
    if j < 33 and mi in (1, 3):     # ⇒ 交叉对 top-2 互不命中, 但 JS 只有 0.34 ⇒ JS 过、top-2 不过
        return {"audit": 0.34, "reward": 0.33, "itch": 0.33}
    return {"display": 0.34, "reward": 0.33, "itch": 0.33}


tm = run_set(top2_miss)["P4_primary"]
assert tm["JS_three_state"] == "PASS" and tm["top2_hit"] < 0.80 and tm["verdict"] == "FAIL", tm
print("分析器: 合成数据分出 PASS / UNRESOLVED / FAIL; 运行方差进区间; Text-01 复核可判; top-2 合取生效")

three = run_set(SETS["PASS"], occs=(1, 2, 3))
assert three["status"].startswith("DESCRIPTIVE_ONLY") and three["G_K1_v3_verdict_P4"] is None
assert "verdict" not in three["P4_primary"] and "mu_D_U95_one_sided" not in three["P4_primary"] and three["bootstrap"] is None
assert "T1_verdict" not in three["text01_out_of_sample"] and three["G_R1_descriptive"] is not None


def bad_cov(occ):
    s = synth(occ, SETS["PASS"])
    for i in A.IDS[:10]:
        s["dists"]["MiniMax-Text-01"][i] = None     # 71/81 < 73
    return s


def pick(an, rs):
    return an.choose(rs, allow_offline=True)[1:]


ok = [synth(k, SETS["PASS"]) for k in (1, 2, 3, 4)]
used, notes = pick(A, ok + [synth(5, SETS["PASS"])])
assert used == [1, 2, 3, 4] and notes["unused_not_a_replacement"] == [5], (used, notes)
used, notes = pick(A, [ok[0], bad_cov(2), ok[2], ok[3], synth(5, SETS["PASS"])])
assert used == [1, 3, 4, 5] and list(notes["invalid"]) == [2], (used, notes)
used, notes = pick(A, [ok[0], ok[2], ok[3], synth(5, SETS["PASS"])])   # 2 没派发 ⇒ 替补不顶
assert used == [1, 3, 4] and notes["unused_not_a_replacement"] == [5]
late = synth(1, SETS["UNRESOLVED"], started="2026-10-05T00:00:00+00:00")
used, notes = pick(A, ok + [late])
assert used == [1, 2, 3, 4] and notes["ignored_duplicate"][0]["started_at_utc"] == late["started_at_utc"]
assert A.choose([flaky_r], allow_offline=True)[1] == [] and A.analyze([flaky_r], allow_offline=True)["G_K1_v3_verdict_P4"] is None
tampered = synth(1, SETS["PASS"])
tampered["prereg_sha256"] = "0" * 64
_reverse("结果文件的预注册 sha 不符 ⇒ 分析器拒收", _refuses(lambda: A.analyze([tampered] + ok[1:], allow_offline=True)))
tampered = synth(1, SETS["PASS"])
tampered["panel"] = list(A.P4)
_reverse("结果文件面板不是冻结的五人 ⇒ 分析器拒收", _refuses(lambda: A.analyze([tampered] + ok[1:], allow_offline=True)))
print("分析器: <4 个有效 occasion 只描述; 替补/重复/无效按 S3/S4; 完整性不符拒收")


# ── 分析器变异: 改坏必须红 ──
def mutant(old, new):
    src = AN_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, old
    mod = types.ModuleType("gk1v3_analyze_mutant")
    mod.__file__ = str(AN_PATH)
    exec(compile(src.replace(old, new), str(AN_PATH), "exec"), mod.__dict__)
    return mod


MUTS = {
    "只重采样条目(运行不重采样)": ("rr = rng.choices(range(r), k=r)", "rr = list(range(r)); rng.random()",
                          lambda an: run_set(occasion_driven, an=an)["P4_primary"]["JS_three_state"] != "UNRESOLVED"),
    "P4 混入 Text-01": ("P4 = P5[:4]", "P4 = P5[:5]",
                       lambda an: run_set(text01_diverges, an=an)["G_K1_v3_verdict_P4"] != "PASS"),
    "去掉「少于 4 个不判」": ("decide = len(occs) == R_NEED", "decide = len(occs) >= 1",
                       lambda an: run_set(SETS["PASS"], occs=(1, 2, 3), an=an)["G_K1_v3_verdict_P4"] is not None),
    "去掉 top-2 合取": ('"verdict": "FAIL" if blk["top2_hit"] < TOP2_THR else js_state', '"verdict": js_state',
                     lambda an: run_set(top2_miss, an=an)["P4_primary"]["verdict"] != "FAIL"),
    "替补不限位": ("used += reps[:n_bad]", "used += reps",
              lambda an: pick(an, ok + [synth(5, SETS["PASS"])])[0] != [1, 2, 3, 4]),
    "不查覆盖率": ("if c < RUN.MIN_COVERAGE:", "if False:",
              lambda an: pick(an, [ok[0], bad_cov(2), ok[2], ok[3], synth(5, SETS["PASS"])])[0] != [1, 3, 4, 5]),
}
for name, (old, new, red) in MUTS.items():
    _reverse("分析器变异「%s」" % name, red(mutant(old, new)))

# ── ⑦ js_div 与 run_gates 同式 ──
import accuracy_offline_harness as AH   # noqa: E402
_m = AH.load(responses=lambda m, p: "")
rng = random.Random(7)
for _ in range(200):
    p = {k: rng.random() for k in rng.sample(KN, rng.randint(1, 3))}
    q = {k: rng.random() for k in rng.sample(KN, rng.randint(1, 3))}
    p, q = ({k: v / sum(d.values()) for k, v in d.items()} for d in (p, q))
    assert abs(A.js_div(p, q) - _m.js_div(p, q)) < 1e-12
assert _m.GATE_PROTOCOL_VERSION == G.GATE_PROTOCOL[0] and _m.gate_protocol_hash() == G.GATE_PROTOCOL[1]
print("js_div == run_gates.js_div(200 组随机分布); run_gates 闸协议 == 预注册")

# ── ⑧ 设计规格 ──
spec = json.loads((ROOT / pre["files"]["design"]).read_text(encoding="utf-8"))
r = DP.preflight(spec)
assert r["pass"], r["fails"]
assert spec["prereg"] == "tests/data/gk1_v3_prereg.json" and spec["n_experimental_units"] == spec["claimed_inferential_n"] == 81
assert set(spec["analysis_formula"]["terms"]) == set(spec["variables"]["categorical"]) == {"model", "occasion"}
assert len(spec["design"]) == spec["n_raw_observations"] == 5 * 4 * 81
print("设计规格: design_preflight PASS(model 5 × occasion 4 × 81)")

assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
socket.socket.connect = _orig
print("OK tests/test_cce_gk1_v3_prereg.py")
