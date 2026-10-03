#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-K1 v4 预注册守卫(2026-10-03)。只跑 --offline 与合成数据, 零网络。

守: ① 预注册 sha 钉在探针(分析器共用) ② 上限 700 / 计划 648 / k=3 / N=54 / 覆盖门 146 / 授权单按 occasion 唯一 /
      研究上限 5 × 700 <= 3500、单次 <= 900 / 运维设置是 v3 的同一个 make_resilient_call
    ③ 条目 54 条 == select_fresh(), sha 钉, 与 corpus / 锚例 / v3 的 81 条零重叠(id 与正文), 无用户名提及, 字段原样
    ④ 离线干跑 occasion 1..4: 每次 648 次采样调用(3 × 216, 采样序号优先), 尝试 <= 700, 分析器 ADJUDICATED
    ⑤ k 平均实现正确(逐类平均、跳过解析失败、全失败 ⇒ 缺失); k 平均在 occasion 内做
    ⑥ 合成数据分出 PASS / UNRESOLVED / FAIL; 「判断相同只有噪声」的世界里 k 平均 PASS 而单次采样 FAIL
    ⑦ 少于 4 个有效 occasion 不出判定; 替补 5 / 重复派发 / 覆盖率按 S2–S4; 完整性不符拒收
    ⑧ 设计规格过 design_preflight ⑨ 功效文件 sha 与预注册一致, 预注册引用的数 == 功效文件
反向(改坏必须红): 预注册 / 条目 sha 不符 · 预设刺激 · occasion 越界 · 上限压低 · 解析失败 ⇒ 无效 · 混入 v3 条目 ·
    分析器 6 条变异(不做 k 平均 / 跨 occasion 合并采样 / 去掉「<4 不判」/ 去掉 top-2 合取 / 替补不限位 / 不查覆盖率)。
"""
import hashlib, json, math, os, pathlib, re, socket, sys, types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
_TRIPPED = []
_orig = socket.socket.connect
def _guard(s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (addr,))
socket.socket.connect = _guard

import accuracy_gk1_v3_run as V3          # noqa: E402
import accuracy_gk1_v3_analyze as V3A     # noqa: E402
import accuracy_gk1_v4_run as G           # noqa: E402
import accuracy_gk1_v4_analyze as A       # noqa: E402
import design_preflight as DP             # noqa: E402

AN_PATH = ROOT / "probes/accuracy_gk1_v4_analyze.py"


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


# ── ① ② 预注册钉与常量 ──
pre = json.loads(G.PREREG.read_text(encoding="utf-8"))
assert _sha(G.PREREG) == G.PREREG_SHA256, "★ 预注册被改过而探针钉住的 sha 没跟 —— 预注册必须跑前冻结"
assert A.RUN is G and A.js_div is V3A.js_div and A.draws is V3A.draws, "★ 分析器必须共用探针常量与 v3 的 JS/自助实现"
b, d = pre["budget"], pre["design"]
assert G.CAP == b["per_dispatch_hard_cap_requests"] == 700 and G.PLANNED == b["calls_planned_per_dispatch"] == 648
assert b["retry_slack"] == G.CAP - G.PLANNED and b["auth_id"].startswith(G.AUTH_PREFIX)
assert (G.K, G.N, A.R_NEED) == (d["k"], d["N"], d["R"]) == (3, 54, 4) and G.PLANNED == len(G.MODELS) * G.N * G.K
assert G.MIN_SAMPLES == math.ceil(0.9 * G.N * G.K) == 146 and "146/162" in pre["occasion_validity"]["valid_iff"]
assert list(G.OCCASIONS) == [1, 2, 3, 4, 5] and len({G.AUTH_PREFIX + str(k) for k in G.OCCASIONS}) == 5
assert G.CAP <= b["single_dispatch_limit"] == 900 and len(G.OCCASIONS) * G.CAP <= 3500, "★ 研究上限 5 × 700 必须 <= 3500"
assert "3500" in b["study_ceiling"]
assert pre["panel"]["P4_primary"] == A.P4 == list(G.MODELS) and "MiniMax-Text-01" not in A.P4
assert pre["basis"]["owner_ruling"]["quote"] == "2和3都做吧" and pre["basis"]["owner_ruling"]["date"] == "2026-10-03"
assert (pre["bootstrap"]["B"], pre["bootstrap"]["seed"]) == (A.B_BOOT, A.SEED) == (10000, 20261003)
assert (pre["stimulus"]["gate_protocol"]["version"], pre["stimulus"]["gate_protocol"]["hash"]) == G.GATE_PROTOCOL
man = json.loads((ROOT / "config/cce_core_manifest.json").read_text(encoding="utf-8"))["gate_protocol_expected"]
assert (man["version"], man["hash"]) == G.GATE_PROTOCOL, "★ 闸协议已换代 ⇒ 本预注册不再适用"
assert (A.THR, A.TOP2_THR) == (pre["threshold"]["value"], 0.80) == (0.25, 0.80)
assert "U(μ_D) <= 0.25" in pre["decision"]["JS_three_state"]["PASS"]
assert G.make_resilient_call is V3.make_resilient_call and V3.ANNOT_WORKERS == 3, "★ 运维设置必须是 v3 偏离 D1 那一份"
print("预注册: sha 钉 / 上限 700(计划 648 = 4 × 54 × 3) / 研究上限 3500 / 面板 P4 / 自助 B·seed / 闸协议 / 阈值 —— 全一致")

# ── ⑨ 功效文件 ──
pw = json.loads((ROOT / pre["power"]["file"]).read_text(encoding="utf-8"))
assert _sha(ROOT / pre["power"]["file"]) == pre["power"]["sha256"], "★ 功效文件与预注册记录的 sha 不符"
assert (pw["chosen"]["k"], pw["chosen"]["N"], pw["chosen"]["R"]) == (3, 54, 4) and pw["chosen"]["budget"]["fits"]
assert pw["chosen"]["budget"]["per_dispatch_cap"] == G.CAP and pw["chosen"]["budget"]["study_ceiling_with_1_replacement"] == 3500
for k, v in pw["D_k_empirical"].items():
    assert "D(%s) %.4f" % (k, v) in pre["power"]["D_k_from_v3"], (k, v)
c3 = next(r for r in pw["candidates"] if (r["k"], r["N"], r["R"]) == (3, 54, 4))
assert pre["power"]["candidates_at_mu_eq_D_k"]["★k3_N54_R4"]["PASS"] == c3["at_mu_D_k"]["PASS"]
assert not pw["text01_arm_cost_at_chosen"]["fits"], "★ 不跑 Text-01 的预算理由必须由功效文件支持"
print("功效文件: sha 一致; 预注册引用的 D(k) 与 k3/N54/R4 判出概率 == 功效文件")

# ── ③ 新条目 ──
items = json.loads(G.ITEMS.read_text(encoding="utf-8"))
assert _sha(G.ITEMS) == G.ITEMS_SHA256, "★ 条目文件被改过而钉住的 sha 没跟"
assert _sha(G.SOURCE) == pre["items"]["source"]["sha256"], "★ 源池文件变了 ⇒ 选样不可复现"
for p, s in pre["items"]["exclusion_sources"].items():
    assert _sha(ROOT / p) == s, "★ 排除集 %s 变了" % p
assert items == G.select_fresh(), "★ 条目与按预注册规则现算的不一致 —— 选样不可复现"
assert len(items) == pre["items"]["n"] == 54 and len({x["id"] for x in items}) == 54
assert len({x["b"].strip() for x in items}) == 54 and all(set(x) == {"id", "a", "post", "b"} for x in items)
corpus = json.loads((ROOT / "accuracy/data/corpus.json").read_text(encoding="utf-8"))
anchors = json.loads((ROOT / "accuracy/data/anchors.json").read_text(encoding="utf-8"))
v3items = json.loads(V3.FRESH.read_text(encoding="utf-8"))


def check_disjoint(its):
    ids, bodies = {x["id"] for x in its}, {x["b"].strip() for x in its}
    old = corpus + v3items
    hit = (ids & ({x["id"] for x in old} | set(anchors["anchor_ids"]))) | (bodies & {x["b"].strip() for x in old})
    assert not hit, "★ v4 条目与旧语料/锚例/v3 条目重叠: %r" % sorted(hit)[:3]
    assert not any(re.search(r"\bu/\w+|/user/\w+", x["b"]) for x in its), "★ 条目带用户名提及"
    assert all(25 <= len(x["b"].strip()) <= 900 for x in its)


check_disjoint(items)
h = lambda i: hashlib.sha256(i.encode()).hexdigest()
assert [h(x["id"]) for x in items] == sorted(h(x["id"]) for x in items)
assert h(items[0]["id"]) > max(h(x["id"]) for x in v3items), "★ 应是同一排序里 v3 之后的那一段"
src = json.loads(G.SOURCE.read_text(encoding="utf-8"))["users"]
assert all(any(c["id"] == x["id"] and c["b"] == x["b"] and c["p"] == x["post"] for c in src[x["a"]]) for x in items), \
    "★ 条目字段不是源文件原样"
for name, bad in (("v3 的一条", v3items[0]), ("corpus.json 的一条", next(
        {"id": c["id"], "b": c["b"]} for cs in src.values() for c in cs if c["id"] in {x["id"] for x in corpus}))):
    try:
        check_disjoint(items[:53] + [bad])
        caught = False
    except AssertionError as e:
        caught = "重叠" in str(e)
    _reverse("条目混入 %s ⇒ 被抓" % name, caught)
print("条目: 54 条 == 规则现算, sha 钉, 与 corpus/锚例/v3 零重叠, 字段原样")

# ── ④ 离线干跑 ──
dry = []
for k in (1, 2, 3, 4):
    r, rep = G.run(offline=True, occasion=k)
    assert r["verdict"] == "OCCASION_COMPLETE" and r["occasion_valid"] and r["offline_dry_run"] is True, r["invalid_reasons"]
    assert r["logical_calls"] == 648 and 648 <= r["http_attempts"] <= G.CAP and r["k"] == 3
    assert r["auth_id"] == G.AUTH_PREFIX + str(k) and len(rep["calls"]) == 648
    pos = {s: [j for j, c in enumerate(rep["calls"]) if c["sample"] == s] for s in range(3)}
    assert all(len(v) == 216 for v in pos.values()) and sum(pos[0]) < sum(pos[1]) < sum(pos[2]), "★ 采样序号优先没生效"
    dry.append(r)
_reverse("离线干跑结果不许当真实数据(allow_offline=False) ⇒ 拒收", _refuses(lambda: A.analyze(dry)))
ad = A.analyze(dry, allow_offline=True)
assert ad["status"] == "ADJUDICATED" and ad["G_K1_v4_verdict"] in ("PASS", "FAIL", "UNRESOLVED")
assert ad["P4_k3"]["n_cells"] == 54 * 4 and ad["D1_single_sample_descriptive"]["mu_D"] > ad["P4_k3"]["mu_D"]
print("离线干跑: 4 个 occasion × 648 次(3 × 216, 采样序号优先), 分析器 ADJUDICATED")

for attr in ("PREREG_SHA256", "ITEMS_SHA256"):
    saved = getattr(G, attr)
    setattr(G, attr, "0" * 64)
    try:
        _reverse("%s 不符 ⇒ 拒跑" % attr, _refuses(lambda: G.run(offline=True, occasion=1)))
    finally:
        setattr(G, attr, saved)
os.environ["CCE_BODY_CHARS"] = "500"
try:
    _reverse("预设刺激环境变量 ⇒ 拒跑", _refuses(lambda: G.run(offline=True, occasion=1)))
finally:
    os.environ.pop("CCE_BODY_CHARS")
for bad in (0, 6):
    _reverse("occasion=%d 越界 ⇒ 拒跑" % bad, _refuses(lambda: G.run(offline=True, occasion=bad)))
os.environ.pop("GK1_V4_OCCASION", None)
_reverse("真跑不给 GK1_V4_OCCASION ⇒ 拒跑(在取 key 之前)", _refuses(lambda: G.run(offline=False)))
G.CAP = 100
try:
    r = G.run(offline=True, occasion=1)[0]
    _reverse("上限压到 100 ⇒ BUDGET_STOP 且 occasion 无效",
             r["verdict"] == "BUDGET_STOP" and not r["occasion_valid"] and r["http_attempts"] <= 100)
finally:
    G.CAP = 700
base_fake = G._fake(1)


def flaky(model, prompt):   # M2.7 约四分之一条目回空或回怪形状 JSON(annot_dist 会抛) ⇒ 可解析 < 146/162
    k = int(h(prompt.split("【")[-1]), 16) % 8
    if model == "MiniMax-M2.7" and k in (0, 4):
        return "" if k == 0 else '{"knots": ["display"]}'
    return base_fake(model, prompt)


r = G.run(offline=True, occasion=1, responses=flaky)[0]
_reverse("M2.7 大面积解析失败(含 annot_dist 抛异常的格) ⇒ OCCASION_INVALID_PARSE, 不崩",
         r["verdict"] == "OCCASION_INVALID_PARSE" and r["coverage_samples"]["MiniMax-M2.7"] < 146 and not r["occasion_valid"]
         and r["parse_exceptions"].get("MiniMax-M2.7:AttributeError", 0) > 0 and r["coverage_samples"]["MiniMax-M3"] == 162)
flaky_r = r

# ── ⑤ k 平均 ──
assert A.kavg([{"a": 1.0}, {"b": 1.0}, None]) == {"a": 0.5, "b": 0.5}
assert A.kavg([None, None, None]) is None
got = A.kavg([{"a": 0.6, "b": 0.4}, {"a": 0.6, "c": 0.4}, {"a": 0.9, "b": 0.1}])
assert all(abs(got[k] - v) < 1e-12 for k, v in {"a": 0.7, "b": 0.5 / 3, "c": 0.4 / 3}.items()) and set(got) == {"a", "b", "c"}
print("k 平均: 逐类算术平均, 跳过解析失败, 全失败 ⇒ 缺失")

# ── ⑥ ⑦ 分析器: 合成数据 ──
X, Y = {"display": 0.9, "reward": 0.1}, {"reward": 0.9, "display": 0.1}     # JS = 0.531
OX, OY = {"display": 1.0}, {"reward": 1.0}                                    # one-hot, JS = 1


def synth(occ, fn, started=None):
    return {"block": "GK1_V4_OCCASION_RESULT", "prereg_sha256": G.PREREG_SHA256, "items_sha256": G.ITEMS_SHA256,
            "occasion": occ, "offline_dry_run": True, "github_run_id": None, "k": 3,
            "started_at_utc": started or "2026-10-04T0%d:00:00+00:00" % occ,
            "run_params": {"gate_protocol_version": G.GATE_PROTOCOL[0], "gate_protocol_hash": G.GATE_PROTOCOL[1],
                           "CCE_BODY_CHARS": 700, "CCE_UNIT_LABEL": "评论"},
            "panel": list(A.P4), "item_ids": list(A.IDS), "annotation_complete": True,
            "dists": {m: {i: [fn(mi, j, occ, s) for s in range(3)] for j, i in enumerate(A.IDS)} for mi, m in enumerate(A.P4)}}


def split_first(n):
    """前 n 条: 0,1 号 → X, 2,3 号 → Y(三次采样都一样); 其余全一致。d = 4/6 × 0.531 = 0.354。"""
    return lambda mi, j, occ, s: dict(Y if (j < n and mi in (2, 3)) else X)


def noisy_same_judgment(mi, j, occ, s):
    """四人稳定判断完全相同(都是 display), 每次采样 30% 翻成 reward ⇒ 单次采样分歧大, k 平均后小。"""
    return dict(OY if int(h("%d|%d|%d|%d" % (mi, j, occ, s)), 16) % 10 < 3 else OX)


def occasion_driven(mi, j, occ, s):    # occasion 1,2 全一致, 3,4 全分裂 ⇒ 条目方差 0, occasion 方差大
    return dict(Y if (occ >= 3 and mi in (2, 3)) else X)


def run_set(fn, occs=(1, 2, 3, 4), an=A):
    return an.analyze([synth(k, fn) for k in occs], allow_offline=True)


SETS = {"PASS": split_first(14), "UNRESOLVED": split_first(38), "FAIL": split_first(54)}
for want, fn in SETS.items():
    o = run_set(fn)
    p4 = o["P4_k3"]
    assert o["G_K1_v4_verdict"] == p4["verdict"] == p4["JS_three_state"] == want, (want, p4)
    print("  合成 %-10s μ_D=%.4f  [L, U]=[%.4f, %.4f]" % (want, p4["mu_D"], p4["mu_D_L95_one_sided"], p4["mu_D_U95_one_sided"]))

ns = run_set(noisy_same_judgment)
assert ns["G_K1_v4_verdict"] == "PASS" and ns["D1_single_sample_descriptive"]["L95_U95_one_sided"][0] > 0.25, \
    "★ 判断相同只有噪声: k 平均必须 PASS, 单次采样必须 FAIL —— 否则 k 平均没起作用"
print("  噪声世界: k=3 μ_D=%.4f PASS; 单次采样 μ_D=%.4f, L=%.4f > 0.25" % (
    ns["P4_k3"]["mu_D"], ns["D1_single_sample_descriptive"]["mu_D"], ns["D1_single_sample_descriptive"]["L95_U95_one_sided"][0]))
od = run_set(occasion_driven)["P4_k3"]
assert od["JS_three_state"] == "UNRESOLVED" and od["mu_D_U95_one_sided"] > 0.25, od   # occasion 进了区间


def top2_miss(mi, j, occ, s):      # 前 22 条: 1,3 号 top-2 与 0,2 号互不命中, 但 JS 只有 0.34 ⇒ JS 过、top-2 不过
    if j < 22 and mi in (1, 3):
        return {"audit": 0.34, "reward": 0.33, "itch": 0.33}
    return {"display": 0.34, "reward": 0.33, "itch": 0.33}


tm = run_set(top2_miss)["P4_k3"]
assert tm["JS_three_state"] == "PASS" and tm["top2_hit"] < 0.80 and tm["verdict"] == "FAIL", tm
print("分析器: 合成数据分出 PASS / UNRESOLVED / FAIL; k 平均在噪声世界起作用; occasion 方差进区间; top-2 合取生效")

three = run_set(SETS["PASS"], occs=(1, 2, 3))
assert three["status"].startswith("DESCRIPTIVE_ONLY") and three["G_K1_v4_verdict"] is None and three["bootstrap"] is None
assert "verdict" not in three["P4_k3"] and "mu_D_U95_one_sided" not in three["P4_k3"] and three["G_R1_descriptive"]
assert "L95_U95_one_sided" not in three["D1_single_sample_descriptive"]


def bad_cov(occ):
    s = synth(occ, SETS["PASS"])
    for i in A.IDS[:6]:
        s["dists"]["MiniMax-M2"][i] = [None, None, None]     # 162 − 18 = 144 < 146
    return s


def pick(an, rs):
    return an.choose(rs, allow_offline=True)[1:]


ok = [synth(k, SETS["PASS"]) for k in (1, 2, 3, 4)]
rep5 = synth(5, SETS["PASS"])
used, notes = pick(A, ok + [rep5])
assert used == [1, 2, 3, 4] and notes["unused_not_a_replacement"] == [5], (used, notes)
used, notes = pick(A, [ok[0], bad_cov(2), ok[2], ok[3], rep5])
assert used == [1, 3, 4, 5] and list(notes["invalid"]) == [2], (used, notes)
used, notes = pick(A, [ok[0], bad_cov(2), bad_cov(3), ok[3], rep5])      # 两个无效, 只有一个替补 ⇒ NO_VERDICT
assert used == [1, 4, 5] and A.analyze([ok[0], bad_cov(2), bad_cov(3), ok[3], rep5], allow_offline=True)["G_K1_v4_verdict"] is None
used, notes = pick(A, [ok[0], ok[2], ok[3], rep5])                        # 2 没派发 ⇒ 替补不顶
assert used == [1, 3, 4] and notes["unused_not_a_replacement"] == [5]
late = synth(1, SETS["UNRESOLVED"], started="2026-10-05T00:00:00+00:00")
used, notes = pick(A, ok + [late])
assert used == [1, 2, 3, 4] and notes["ignored_duplicate"][0]["started_at_utc"] == late["started_at_utc"]
assert A.choose([flaky_r], allow_offline=True)[1] == [] and A.analyze([flaky_r], allow_offline=True)["G_K1_v4_verdict"] is None
for what, mut in (("预注册 sha", lambda s: s.update(prereg_sha256="0" * 64)),
                  ("面板混入 Text-01", lambda s: s.update(panel=list(A.P4) + ["MiniMax-Text-01"])),
                  ("k=2 形状", lambda s: [v.pop() for m in A.P4 for v in s["dists"][m].values()]),
                  ("v3 结果文件", lambda s: s.update(block="GK1_V3_OCCASION_RESULT"))):
    t = synth(1, SETS["PASS"])
    mut(t)
    _reverse("结果文件%s ⇒ 分析器拒收" % what, _refuses(lambda: A.analyze([t] + ok[1:], allow_offline=True)))
print("分析器: <4 个有效 occasion 只描述; 替补 5 只补一位; 重复/无效按 S2–S4; 完整性不符拒收")


# ── 分析器变异: 改坏必须红 ──
def mutant(old, new):
    src = AN_PATH.read_text(encoding="utf-8")
    assert src.count(old) == 1, old
    mod = types.ModuleType("gk1v4_analyze_mutant")
    mod.__file__ = str(AN_PATH)
    exec(compile(src.replace(old, new), str(AN_PATH), "exec"), mod.__dict__)
    return mod


MUTS = {
    "不做 k 平均(只用第 1 次采样)": ('kavg(r["dists"][m][i]) if sample is None', 'r["dists"][m][i][0] if sample is None',
                            lambda an: run_set(noisy_same_judgment, an=an)["G_K1_v4_verdict"] != "PASS"),
    "跨 occasion 合并采样再平均": ('b4 = panel_block([view(r) for r in occs], dr)',
                          'b4 = panel_block([view({"dists": {m: {i: sum((o["dists"][m][i] for o in occs), []) for i in IDS} for m in P4}})] * len(occs), dr)',
                          lambda an: run_set(occasion_driven, an=an)["P4_k3"]["JS_three_state"] != "UNRESOLVED"),
    "去掉「少于 4 个不判」": ("decide = len(occs) == R_NEED", "decide = len(occs) >= 1",
                       lambda an: run_set(SETS["PASS"], occs=(1, 2, 3), an=an)["G_K1_v4_verdict"] is not None),
    "去掉 top-2 合取": ('"verdict": "FAIL" if blk["top2_hit"] < TOP2_THR else js_state', '"verdict": js_state',
                     lambda an: run_set(top2_miss, an=an)["P4_k3"]["verdict"] != "FAIL"),
    "替补不限位": ("used += reps[:n_bad]", "used += reps",
              lambda an: pick(an, ok + [rep5])[0] != [1, 2, 3, 4]),
    "不查覆盖率": ("if c < RUN.MIN_SAMPLES:", "if False:",
              lambda an: pick(an, [ok[0], bad_cov(2), ok[2], ok[3], rep5])[0] != [1, 3, 4, 5]),
}
for name, (old, new, red) in MUTS.items():
    _reverse("分析器变异「%s」" % name, red(mutant(old, new)))

# ── ⑧ 设计规格 ──
spec = json.loads((ROOT / pre["files"]["design"]).read_text(encoding="utf-8"))
res = DP.preflight(spec)
assert res["pass"], res["fails"]
assert spec["prereg"] == "tests/data/gk1_v4_prereg.json" and spec["n_experimental_units"] == spec["claimed_inferential_n"] == 54
assert set(spec["analysis_formula"]["terms"]) == set(spec["variables"]["categorical"]) == {"model", "occasion"}
assert len(spec["design"]) == spec["n_raw_observations"] == 4 * 4 * 54 and spec["calls_per_occasion"] == G.PLANNED
print("设计规格: design_preflight PASS(model 4 × occasion 4 × 54 个 k=3 平均读数)")

assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
socket.socket.connect = _orig
print("OK tests/test_cce_gk1_v4_prereg.py")
