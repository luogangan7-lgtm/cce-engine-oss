#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G-P(生产实际输出闸)预注册守卫(2026-10-03)。只跑 --offline 与合成数据, 零网络。

守: ① 预注册 sha 钉在探针; owner 2026-10-03 调用前修订(N 40 → 86, 拆片)有谁/何时/为什么; 每片上限 409 / 计划 344
      (= 43 × 8, 与 N=40 时同一相对余量 60/320) / N=86 / R=2 / 2 片 / 覆盖门 39/43 / 16 片 + 2 次替补 = 7362(超约 6000, 如实写明)、
      单次 <= 900; 阈值 0.875 / 0.80 及其出处字样; 运维常量 = v3 的并发 3 与退避 4 秒; 自助 = v3 同一份 draws / boot
    ② 生产输出规格: sha 钉在预注册; 仪器 hash / spec / 温度阶梯 / k / n / 模型 / 端点 / K1 路由 / 发布规则从代码现算比对
    ③ 条目 86 条 == select_fresh(), sha 钉, 前 40 条与修订前的 40 条文件逐字节相同, 与 corpus / 锚例 / v3 / v4 /
       reader_mode_gate 零重叠, context 由存档现算
    ④ 离线干跑 16 片: 每条都经过生产函数对象(计数间谍), s1 / s2 prompt 是生产构造的那一份, 面板请求真的换了模型,
       运行后全部补丁复原; 分析器拼槽出判定
    ⑤ 传输层: 并发上限 3、错误码计数、指数退避; 预算撞线 ⇒ BUDGET_STOP 且被分析器判无效
    ⑥ 合成数据分出 PASS / FAIL / UNRESOLVED; 缺片 ⇒ 槽不成立 ⇒ INSUFFICIENT_SLOTS
    ⑦ 有效性 / 分片挑选与拼槽 / 替补上限 / 完整性拒收  ⑧ 设计规格 == 生成函数且过 design_preflight  ⑨ 功效数 == 现算
反向(改坏必须红): 分析器 10 条变异 + 探针 3 条变异(读数改用 knots[0] / 不扣 s2_short / 面板没真换模型)。
"""
import collections, hashlib, inspect, json, pathlib, re, socket, subprocess, sys, threading, time, types

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
import gate_gp_run as G                   # noqa: E402
import gate_gp_analyze as A               # noqa: E402
import design_preflight as DP             # noqa: E402
import exp_crossmodel_desire as X         # noqa: E402
import cce_knot_classify as K             # noqa: E402
import cce_full_run as F                  # noqa: E402
import cce_k1_status as S                 # noqa: E402
import cce_request_budget as B            # noqa: E402
from cce_structural_gate import structural_gate, VERDICT_ABSTAIN   # noqa: E402

RUN_PATH, AN_PATH = ROOT / "probes/gate_gp_run.py", ROOT / "probes/gate_gp_analyze.py"


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


def _src(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


# ── ① 预注册钉与常量 ──
pre = json.loads(G.PREREG.read_text(encoding="utf-8"))
assert _sha(G.PREREG) == G.PREREG_SHA256, "★ 预注册被改过而探针钉住的 sha 没跟 —— 预注册必须跑前冻结"
assert A.RUN is G and A.draws is V3A.draws and A.boot is V3A.boot and A.binom_upper is K.binom_upper, \
    "★ 分析器必须共用探针常量、v3 的自助实现与生产的 binom_upper"
b, d, c = pre["budget"], pre["design"], pre["criteria"]
am = pre["★amendment_2026-10-03_owner_N86_before_any_call"]
assert "owner" in am["who"] and "2026-10-03" in am["when"] and "任何真实调用之前" in am["when"] and "规则先于条目" in am["when"]
assert "0.7681" in am["why"] and "45% FAIL / 55% UNRESOLVED" in am["why"] and "N >= 86" in am["why"]
assert (G.N, len(G.RUNS), len(G.SHARDS), G.SHARD_SIZE) == (d["N"], d["R"], d["shards"], d["shard_size"]) == (86, 2, 2, 43)
assert G.SHARD_SIZE * len(G.SHARDS) == G.N and G.NOMINAL_PER_READOUT == b["nominal_http_per_readout"] == 8
assert G.PLANNED == b["per_dispatch_planned"] == 344 == G.SHARD_SIZE * 8 and G.CAP == b["per_dispatch_hard_cap"] == 409
assert G.CAP == -(-G.PLANNED * (320 + 60) // 320), "★ 每片上限必须沿用 N=40 时的相对余量 60/320"
assert b["retry_slack"] == G.CAP - G.PLANNED == 65 and b["dispatches_planned"] == 16 == 4 * 2 * 2 and b["max_replacements"] == 2
assert (b["dispatches_planned"] + b["max_replacements"]) * G.CAP == 7362 and "7362" in b["study_ceiling"] and "6000" in b["study_ceiling"]
assert "5504" in b["nominal_total"] and 4 * 2 * 86 * 8 == 5504
assert G.CAP <= b["single_dispatch_limit"] == 900 and A.MAX_RESULTS == 18
assert G.MIN_COVERAGE == 39 == -(-9 * G.SHARD_SIZE // 10) and "39/43" in pre["validity"]["dispatch_valid_iff"]
assert G.N * 8 == 688 and -(-688 * 380 // 320) == 817 <= 900 and "817" in am["changed"]["sharding"], \
    "★ 拆片理由写的是墙钟(不拆时调用数本身 <= 900), 数要对得上"
assert "153 分钟" in am["changed"]["sharding"] and "76 分钟" in b["wall_clock"]
assert b["worst_case_http_per_readout"] == 3 * 3 * 3 + 5 * 3 * 3 == 72
assert (A.THR_A, A.THR_BC) == (c["a_production_rerun_stability"]["threshold"], c["b_production_vs_panel_consensus"]["threshold"]) \
    == (0.875, 0.80) and c["c_panel_self_consistency_production_prompt"]["threshold"] == 0.80
assert "top1≥7/8" in json.loads(_src(ROOT / "tests/data/phase2/k1_v2_multitext_prereg.json"))["criterion"]["per_text"], \
    "★ (a) 的阈值出处(K1 冻结的 7/8)不在了"
assert "top2命中≥0.8" in _src(ROOT / "accuracy/run_gates.py"), "★ (b)(c) 的阈值出处(G-K1 的 0.8)不在了"
assert (pre["bootstrap"]["B"], pre["bootstrap"]["seed"]) == (V3A.B_BOOT, V3A.SEED) == (10000, 20261003)
assert G.HTTP_CONCURRENCY == G.ITEM_WORKERS == V3.ANNOT_WORKERS == pre["operations"]["item_workers"] == 3
assert G.BACKOFF_BASE_SEC == V3.BACKOFF_BASE_SEC == 4.0
assert pre["basis"]["owner_ruling"] == {**pre["basis"]["owner_ruling"], "date": "2026-10-03", "quote": "第1个吧，让闸量生产实际输出"}
assert list(G.PANEL) == pre["panel"]["members"] and G.PANEL == pre["panel"]["api_models"]
assert list(G.REFUSE_ENV) == pre["stimulus"]["refuse_if_env_set"] and G.CONTEXT == pre["stimulus"]["context"]
assert (G.K_S1, K.KNOT_N) == (pre["stimulus"]["k"], pre["stimulus"]["knot_n"]) == (3, 5)
order = [(m, r, s) for r in (1, 2) for m in G.PANEL for s in (1, 2)]
assert len(pre["dispatch_plan"]["commands"]) == 16 and all(
    x.startswith("gh workflow run probe.yml --ref master -f probe=probes/gate_gp_run.py -f design=designs/gate_gp_2026-10-03.json")
    and x.endswith('-f env="GP_MODEL=%s GP_RUN=%d GP_SHARD=%d"' % s) for x, s in zip(pre["dispatch_plan"]["commands"], order))
print("预注册: sha 钉 / owner 修订 N=86 / 每片上限 409(计划 344 = 43 × 8)/ 16 片 + 2 替补 = 7362 / 阈值与出处 / 运维常量 / 自助 / 16 条派发命令 —— 全一致")

# ── ② 生产输出规格: 从代码现算比对 ──
spec = json.loads((ROOT / pre["basis"]["production_output_spec"]["file"]).read_text(encoding="utf-8"))
assert _sha(ROOT / pre["basis"]["production_output_spec"]["file"]) == pre["basis"]["production_output_spec"]["sha256"]
taxo = json.loads((ROOT / "config/knot_taxonomy.json").read_text(encoding="utf-8"))
for k, h in ((3, "d4cce4c745f3f991"), (5, "c4419c3e53aa2fa9")):
    inst = K.instrument_id(taxo, k=k, knot_n=5, s1_pairing="round_robin_over_%d_s1_draws" % k)
    assert inst["instrument_hash"] == h and h in spec["instruments"], (k, inst["instrument_hash"])
    assert S.layer_status(instrument_hash=h)["top1"]["usable"] and not S.layer_status(instrument_hash=h)["intensity"]["usable"]
    if k == 3:
        assert spec["instruments"][h]["spec"] == {f: inst["spec"][f] for f in spec["instruments"][h]["spec"]}
        assert spec["instruments"][h]["qualification_policy_hash"] == inst["qualification_policy_hash"]
mm = spec["measurement_model"]
assert (X.MODELS["M3"]["model"], X.MODELS["M3"]["base"], X.MODELS["M3"]["max_tokens"]) == (mm["model"], mm["endpoint"], mm["max_tokens"])
assert mm["max_tokens"] == 8000 and '"max_tokens": 12000' in _src(ROOT / "scripts/exp_crossmodel_desire.py") and \
    'MODELS[_mk]["max_tokens"] = 8000' in _src(ROOT / "scripts/exp_v4_full_validation.py"), "★ 生效 max_tokens 的来历变了, 规格更正块要重写"
assert "83789292a4fbbed6" in pre["basis"]["production_output_spec"]["★amendment_2026-10-03_before_any_call"]
assert K.MEASUREMENT_MODEL == mm["registry_key"] == "M3" and K.KNOT_N == spec["k_by_profile"]["s2_n"] == 5
assert K._S1_BASE_TEMPS[:3] == [0.0, 0.3, 0.6] and str(K._S1_BASE_TEMPS) in spec["stage1"]["temperature_ladder"]
assert {k: spec["k_by_profile"][k] for k in ("reply", "response", "outbound_post")} == {"reply": 3, "response": 3, "outbound_post": 5}
sig = inspect.signature(X.call_model).parameters
assert sig["max_retries"].default == 3 and spec["stage2"]["worst_case_http_per_readout"]["k3"] == 72
ks, fs, rl = _src(ROOT / "scripts/cce_knot_classify.py"), _src(ROOT / "scripts/cce_full_run.py"), _src(ROOT / "scripts/reply_loop.py")
for needle in ("call_model(MEASUREMENT_MODEL, prompt, temperature=0.0)", "_C(tops).most_common(1)[0]",
               "top1_unanimous = (len(set(tops)) == 1) if len(tops) >= 2 else None", "prompts[i % len(prompts)]"):
    assert needle in ks, "★ 规格描述的 s2 行为在生产代码里找不到了: %s" % needle
for needle in ('"k": 5 if a.mode in {"post", "outbound_post"} else 3', 'usable["s2.distribution.top1"] = base',
               'usable["s2.playbook_primary"] = s2m["playbook_primary"]'):
    assert needle in fs, "★ 规格描述的发布规则在 cce_full_run 里找不到了: %s" % needle
assert '_samp.get("top1_stable") is True and layer_status' in rl and '"(对方原文/写作基准侧)"' in rl
for p in ("probes/k1_v2_multitext.py", "probes/k1_v2_k5_instrument.py"):
    assert '"top1": knots[0][0] if knots else None' in _src(ROOT / p), "★ K1 判的读数形式变了, 规格 ★K1_readout_gap 要重写"
print("生产输出规格: 两台仪器 hash / spec / K1 路由 / 模型端点 / 温度阶梯 / k / n / 发布规则 / K1 读数形式 —— 与代码一致")

# ── ③ 新条目 ──
items = json.loads(G.ITEMS.read_text(encoding="utf-8"))
IDS = [x["id"] for x in items]
assert _sha(G.ITEMS) == G.ITEMS_SHA256 and A.IDS == IDS
assert _sha(G.SOURCE) == pre["items"]["source"]["sha256"], "★ 源池变了 ⇒ 选样不可复现"
for p, s in pre["items"]["exclusion_sources"].items():
    assert _sha(ROOT / p) == s, "★ 排除集 %s 变了" % p
assert items == G.select_fresh(), "★ 条目与按预注册规则现算的不一致"
assert len(items) == pre["items"]["n"] == 86 and len(set(IDS)) == 86 and len({x["b"].strip() for x in items}) == 86
assert all(set(x) == {"id", "a", "post", "b"} for x in items)
assert hashlib.sha256((json.dumps(items[:40], ensure_ascii=False, indent=1) + "\n").encode()).hexdigest() == \
    "ae6dcc433b410efcdfd95f92a5681e3c7968aad983dd8af231306ecb3015d2a5", "★ 前 40 条必须与修订前的 40 条文件逐字节相同(规则只改了 N)"
assert G.shard_items(items, 1) + G.shard_items(items, 2) == items and len(G.shard_items(items, 2)) == 43


def check_disjoint(its):
    old = [x for p in ("accuracy/data/corpus.json", "accuracy/data/gk1_v3_fresh81.json", "accuracy/data/gk1_v4_fresh54.json")
           for x in json.loads(_src(ROOT / p))]
    seen = {r["ptr"].split(":")[2] for r in json.loads(_src(ROOT / "results/reader_mode_gate_rows.json"))["rows"]}
    anchors = set(json.loads(_src(ROOT / "accuracy/data/anchors.json"))["anchor_ids"])
    ids, bodies = {x["id"] for x in its}, {x["b"].strip() for x in its}
    hit = (ids & ({x["id"] for x in old} | anchors | seen)) | (bodies & {x["b"].strip() for x in old})
    assert not hit, "★ 条目与旧语料 / 锚例 / v3 / v4 / 已读过生产 top-1 的评论重叠: %r" % sorted(hit)[:3]
    assert not any(re.search(r"\bu/\w+|/user/\w+", x["b"]) for x in its) and all(25 <= len(x["b"].strip()) <= 900 for x in its)


check_disjoint(items)
src_users = json.loads(G.SOURCE.read_text(encoding="utf-8"))["users"]
assert all(any(c["id"] == x["id"] and c["b"] == x["b"] for c in src_users[x["a"]]) for x in items), "★ 条目字段不是源池原样"
v4_one = json.loads(_src(ROOT / "accuracy/data/gk1_v4_fresh54.json"))[0]
try:
    check_disjoint(items[:-1] + [v4_one])
    _reverse("混入 v4 条目", False)
except AssertionError as e:
    _reverse("混入 v4 条目", "重叠" in str(e))
ctx = collections.Counter(it.get("context") for f in sorted((ROOT / "archive").glob("*/cce-submission-source__normalized.json"))
                          for it in (json.loads(f.read_text(encoding="utf-8")).get("items") or []) if it.get("mode") == "reply")
top, n_top = ctx.most_common(1)[0]
assert (n_top, sum(ctx.values())) == (18, 75) and G.CONTEXT == top + "(对方原文/写作基准侧)", "★ context 不再是存档众数 + reply_loop 读者后缀"
print("条目: 86 条 == select_fresh(), sha 钉, 前 40 条 == 修订前文件, 零重叠(含 reader_mode_gate 23 条); context = 存档 reply 众数(18/75)+ 读者后缀")

# ── ④ 离线干跑: 生产函数对象全程被调用 ──
assert not [k for k in G.REFUSE_ENV if __import__("os").environ.get(k)], "★ 测试环境里设了拒跑变量"
assert 's1 = stage1(text.strip(), a.context, a.k)' in inspect.getsource(K.main) and \
    's2 = stage2(text.strip(), s1, taxo)' in inspect.getsource(K.main), "★ cce_knot_classify.main 的组装变了 —— 探针的同进程执行器要跟"
assert "K.stage1(text.strip()" in inspect.getsource(G._InProcess.run) and "K.stage2(text.strip(), s1, taxo)" in inspect.getsource(G._InProcess.run)
assert "subprocess.run(cmd" in inspect.getsource(F.run_knot_classify)
ORIG = {"models": dict(X.MODELS), "requests": X.requests, "subprocess": F.subprocess, "reserve": X.reserve_in_scope}
calls = collections.Counter()


def spy(mod, name):
    fn = getattr(mod, name)
    def w(*a, **k):
        calls[name] += 1
        return fn(*a, **k)
    w.__wrapped__ = fn
    setattr(mod, name, w)


for mod, name in ((K, "stage1"), (K, "stage2"), (K, "_build_stage2_prompt"), (F, "run_knot_classify"), (F, "s2"), (F, "qualified")):
    spy(mod, name)
head = K._stage2_template(taxo).split("【第 1 级引擎读出")[0]
tail_of = lambda t: K._build_stage2_prompt(taxo, t, {"tops": {}, "appraisal": {}}).split("【待分类内容】")[1]
gated = {x["id"]: structural_gate(x["b"].strip()) for x in items}
results = []
for m, r, s in order:
    calls.clear()
    out, fake = G.run(True, m, r, s)
    results.append(out)
    sids = [x["id"] for x in G.shard_items(items, s)]
    assert out["verdict"] == "DISPATCH_COMPLETE" and out["coverage"] == 43 and out["http_attempts"] <= G.CAP, out["verdict"]
    assert out["shard"] == s and out["item_ids"] == sids and [x["id"] for x in out["readouts"]] == sids
    assert (out["instrument_hash"] == G.PROD_HASH) == (m == "M3"), "★ 面板成员的仪器 hash 必须随 model 变, 生产必须是 d4cce4"
    assert calls["run_knot_classify"] == calls["stage1"] == calls["stage2"] == calls["s2"] == calls["qualified"] == 43, dict(calls)
    assert {p["model"] for p in fake.prompts} == {G.PANEL[m]}, "★ 请求没有真的发给 %s" % G.PANEL[m]
    s1p = [p for p in fake.prompts if p["kind"] == "s1"]
    want = {K.build_prompt(K._stage1_case(gated[i]["subject_text"], G.CONTEXT)) for i in sids
            if gated[i]["verdict"] != VERDICT_ABSTAIN}
    assert {p["prompt"] for p in s1p} == want, "★ s1 prompt 不是生产 build_prompt(_stage1_case(...)) 构造的那一份"
    s2p = [p for p in fake.prompts if p["kind"] == "s2"]
    assert s2p and all(p["prompt"].startswith(head) and p["prompt"].endswith(tail_of(p["text"])) for p in s2p), \
        "★ s2 prompt 不是生产 _build_stage2_prompt 的那一份"
    assert calls["_build_stage2_prompt"] >= len({p["text"] for p in s2p}) * 3
    assert all(x["value"] == (x["top1_mode"] if x["value"] != "NONE" else "NONE") for x in out["readouts"])
    assert X.MODELS == ORIG["models"] and K.MEASUREMENT_MODEL == "M3" and X.requests is ORIG["requests"] \
        and F.subprocess is ORIG["subprocess"] and X.reserve_in_scope is ORIG["reserve"] \
        and not __import__("os").environ.get(B.SCOPE_ID), "★ 运行后补丁没有复原"
for mod, name in ((K, "stage1"), (K, "stage2"), (K, "_build_stage2_prompt"), (F, "run_knot_classify"), (F, "s2"), (F, "qualified")):
    setattr(mod, name, getattr(mod, name).__wrapped__)
chosen, notes = A.choose(list(reversed(results)), allow_offline=True)        # 输入顺序打乱也要按分片号拼回
off = A.judge(chosen)
assert len(chosen) == 8 and not notes["invalid"] and not notes["incomplete_slots"] and all(
    [x["id"] for x in chosen[sl]["readouts"]] == IDS for sl in chosen), "★ 拼回的槽必须是条目文件顺序的 86 条"
assert all(off[k]["verdict"] in ("PASS", "FAIL", "UNRESOLVED")
           for k in ("a_production_rerun_stability", "b_production_vs_panel_consensus", "c_panel_self_consistency"))
assert off["a_production_rerun_stability"]["n_pairs"] == 86 and off["c_panel_self_consistency"]["n_cells"] == 172
assert _refuses(lambda: A.choose(results)), "★ 离线结果不许当真跑结果收"
assert _refuses(lambda: G.run(True, "M9", 1)) and _refuses(lambda: G.run(True, "M3", 3)) and _refuses(lambda: G.run(True, "M3", 1, 3))
print("离线干跑: 16 片 × 43 条都经过 run_knot_classify / stage1 / stage2 / s2_knots / qualified_readout; prompt 是生产构造的; "
      "面板请求换了模型; 补丁复原; 分析器按分片号拼回 8 槽 × 86 条")


class FakeS2(G._FakeRequests):
    """可控的 s2: knots[0](出现时强度中位数最大)与 top1_mode(逐次 argmax 众数)故意不同; 可让某条的第 5 次及以后的 s2 请求坏掉。"""
    def __init__(self, member, run_no, broken=None):
        super().__init__(member, run_no)
        self.broken = broken

    def post(self, url, **kw):
        prompt = kw["json"]["messages"][0]["content"]
        if not prompt.startswith(G.S2_HEAD):
            return super().post(url, **kw)
        t = self._text(prompt)
        with self._lock:
            s = self._seen[("x", t)]
            self._seen[("x", t)] += 1
            self.prompts.append({"model": kw["json"]["model"], "prompt": prompt, "text": t, "kind": "s2"})
        if t == self.broken and s >= 4:
            return G._FakeResp({"base_resp": {"status_code": 0}, "choices": [{"message": {"content": "not json"}}]})
        knots = [{"key": "audit", "intensity": 0.5}] if s < 3 else [{"key": "reward", "intensity": 0.9}, {"key": "audit", "intensity": 0.1}]
        return G._FakeResp({"base_resp": {"status_code": 0},
                            "choices": [{"message": {"content": json.dumps({"knots": knots, "levers_present": [], "notes": ""})}}]})


fo, _ = G.run(True, "M3", 1, transport=FakeS2("M3", 1))
ok = [x for x in fo["readouts"] if x["value"] not in ("NONE", None)]
assert ok and all(x["value"] == x["top1_mode"] == "audit" and x["knots0"] == "reward" for x in ok), \
    "★ 读数必须是生产发布的 top1_mode, 不是 knots[0]"
victim = next(x for x in items if x["id"] == ok[0]["id"])["b"].strip()     # s2 prompt 里放的是 strip 后的原文(不是结构闸制备后的)
fb, _ = G.run(True, "M3", 1, transport=FakeS2("M3", 1, broken=victim))
vb = next(x for x in fb["readouts"] if x["id"] == ok[0]["id"])
assert vb["status"] == "MISSING" and vb["why"].startswith("s2_short") and vb["n_ok"] == 4, vb
print("读数形式: top1_mode ≠ knots[0] 时取 top1_mode; s2 少一次抽样 ⇒ 生产扣发 ⇒ MISSING")

# ── ⑤ 传输层与预算 ──
class SlowReal:
    def __init__(self, seq=None):
        self.cur = self.peak = 0
        self.lock, self.seq = threading.Lock(), list(seq or [])

    def post(self, url, **kw):
        with self.lock:
            self.cur += 1
            self.peak = max(self.peak, self.cur)
            nxt = self.seq.pop(0) if self.seq else ("ok",)
        time.sleep(0.02)
        with self.lock:
            self.cur -= 1
        if nxt[0] == "exc":
            raise ConnectionError("boom")
        if nxt[0] == "http":
            return types.SimpleNamespace(status_code=nxt[1], json=lambda: {})
        code = nxt[1] if nxt[0] == "base" else 0
        return types.SimpleNamespace(status_code=200, json=lambda: {"base_resp": {"status_code": code}})


real, errs, slept = SlowReal(), collections.Counter(), []
tr = G._Transport(real, errs, threading.Lock(), sleep=slept.append)
ths = [threading.Thread(target=tr.post, args=("u",), kwargs={"json": {"model": "m"}}) for _ in range(12)]
[t.start() for t in ths]
[t.join() for t in ths]
assert 1 < real.peak <= G.HTTP_CONCURRENCY and not errs and not slept, real.peak
real2, errs2, slept2 = SlowReal([("http", 429), ("base", 1002), ("exc",), ("ok",), ("http", 500)]), collections.Counter(), []
tr2 = G._Transport(real2, errs2, threading.Lock(), sleep=slept2.append)
for _ in range(5):
    try:
        tr2.post("u", json={"model": "MiniMax-M2"})
    except ConnectionError:
        pass
assert dict(errs2) == {"MiniMax-M2|http:429": 1, "MiniMax-M2|base_resp:1002": 1, "MiniMax-M2|exc:ConnectionError": 1, "MiniMax-M2|http:500": 1}
assert [int(x) for x in slept2] == [4, 8, 16, 4], slept2
saved_cap = G.CAP
try:
    G.CAP = 50
    bs, _ = G.run(True, "M3", 1)
finally:
    G.CAP = saved_cap
assert bs["budget_stop"] and bs["verdict"] == "BUDGET_STOP" and not bs["dispatch_valid"] and bs["http_attempts"] <= 50
assert "BUDGET_STOP" in A.invalid_reasons(bs)
print("传输层: 并发峰值 %d <= 3; 错误码按「模型|码」计; 退避 4/8/16 秒、成功后归零; 预算撞线 ⇒ BUDGET_STOP 且无效" % real.peak)

# ── ⑥ ⑦ 合成数据(按分片造结果文件) ──
KN = list(K.KNOTS_ALL)
PROD_MM = G.spec_minus_model_sha(G._spec("M3"))
OTH = ("M2.5", "M2.7", "M2")


def mk(member, run, shard, vals, budget_stop=False, started="2026-10-04T00:00:00Z", **over):
    """一片结果文件; vals = 该片 43 条的取值(None = MISSING)。"""
    ih = G.PROD_HASH if member == "M3" else "panel_" + member
    sids = [x["id"] for x in G.shard_items(items, shard)]
    ro = [{"id": i, "status": "MISSING" if v is None else "OK", "value": v, "top1_mode": v, "knots0": v,
           "published_rule_Q": v not in (None, "NONE"), "published_rule_U": False, "rule_U": "WITHHELD",
           "instrument_hash": ih, **({"why": "chain: x"} if v is None else {})} for i, v in zip(sids, vals)]
    r = {"block": "GATE_GP_DISPATCH_RESULT", "prereg_sha256": G.PREREG_SHA256, "items_sha256": G.ITEMS_SHA256,
         "item_ids": sids, "member": member, "api_model": G.PANEL[member], "run": run, "shard": shard, "context": G.CONTEXT,
         "k": 3, "knot_n": 5, "instrument_hash": ih, "spec_minus_model_sha": PROD_MM, "offline_dry_run": True,
         "started_at_utc": started, "budget_stop": budget_stop, "readouts": ro}
    r.update(over)
    return r


def mk_slot(member, run, vals):
    return [mk(member, run, s, G.shard_items(vals, s)) for s in G.SHARDS]


base = [KN[i % 9] for i in range(G.N)]
dev = lambda i, s: KN[(i + s) % 9]
NN = range(G.N)


def world(prod1, prod2, others):
    """16 片: M3 r1 s1/s2, M3 r2 s1/s2, 然后运行 1 的 M2.5/M2.7/M2(各两片), 运行 2 同。"""
    return mk_slot("M3", 1, prod1) + mk_slot("M3", 2, prod2) + [x for r in (1, 2) for m in OTH for x in mk_slot(m, r, others[m])]


W = {"PASS": world(base, base, {m: base for m in OTH}),
     "FAIL": world(base, [base[i] if i < 43 else dev(i, 1) for i in NN],
                   {"M2.5": [dev(i * 2, 2) for i in NN], "M2.7": [dev(i, 5) for i in NN], "M2": [dev(i, 5) for i in NN]}),
     "UNRESOLVED": world([dev(i, 4) if i % 6 == 1 else base[i] for i in NN],
                         [dev(i, 4) if i % 6 == 1 else dev(i, 5) if i < 10 else base[i] for i in NN],
                         {"M2.5": [dev(i, 3) if i % 5 == 0 else base[i] for i in NN], "M2.7": base, "M2": base})}
M2R1S1 = 8                                    # world() 里运行 1 的 M2 分片 1 的位置


def run_set(rs, an=A):
    ch, _ = an.choose(rs, allow_offline=True)
    return an.judge(ch)


VERD = lambda j: (j["a_production_rerun_stability"]["verdict"], j["b_production_vs_panel_consensus"]["verdict"],
                  j["c_panel_self_consistency"]["verdict"], j["overall"])
assert len(W["PASS"]) == 16 and (W["PASS"][M2R1S1]["member"], W["PASS"][M2R1S1]["run"], W["PASS"][M2R1S1]["shard"]) == ("M2", 1, 1)
jp, jf, ju = (run_set(W[k]) for k in ("PASS", "FAIL", "UNRESOLVED"))
assert VERD(jp) == ("PASS", "PASS", "PASS", "PASS"), VERD(jp)
assert VERD(jf) == ("FAIL", "FAIL", "FAIL", "FAIL") and jf["b_production_vs_panel_consensus"]["reported_as"] == "REFERENCE_INCOHERENT", VERD(jf)
assert VERD(ju) == ("UNRESOLVED", "UNRESOLVED", "UNRESOLVED", "UNRESOLVED"), (VERD(ju), [ju[k].get("point") for k in (
    "a_production_rerun_stability", "b_production_vs_panel_consensus", "c_panel_self_consistency")])
assert jp["a_production_rerun_stability"]["L95_one_sided"] == 1 - K.binom_upper(0, 86)
ch_short, nt_short = A.choose(W["PASS"][:15], allow_offline=True)
short = A.judge(ch_short)
assert ("M2", 2) not in ch_short and nt_short["incomplete_slots"] == [{"slot": "M2_r2", "valid_shards": [1]}], nt_short
assert VERD(short)[1:] == ("UNRESOLVED", "UNRESOLVED", "UNRESOLVED") and short["b_production_vs_panel_consensus"]["why"] == "INSUFFICIENT_SLOTS"
assert VERD(run_set(W["PASS"][1:]))[0] == "UNRESOLVED", "★ 生产运行 1 缺一片也判了 (a)"
print("合成数据: PASS / FAIL(b 报 REFERENCE_INCOHERENT)/ UNRESOLVED 三态分得开; 缺一片 ⇒ 槽不成立 ⇒ INSUFFICIENT_SLOTS")

shard_vals = G.shard_items(base, 1)
v_bad = mk("M2", 1, 1, [None] * 5 + shard_vals[5:], started="2026-10-04T00:00:00Z")
v_rep = mk("M2", 1, 1, shard_vals, started="2026-10-05T00:00:00Z")
with_bad = W["PASS"][:M2R1S1] + [v_bad] + W["PASS"][M2R1S1 + 1:]
ch, nt = A.choose(with_bad + [v_rep], allow_offline=True)
assert ch[("M2", 1)]["parts"][0]["started_at_utc"] == v_rep["started_at_utc"] and "M2_r1_s1" in nt["invalid"], \
    "★ 覆盖率 38/43 的分片必须判无效、由替补顶上"
assert ("M2", 1) not in A.choose(with_bad, allow_offline=True)[0], "★ 一片无效且无替补 ⇒ 槽不成立"
assert A.invalid_reasons(mk("M2", 1, 1, [None] * 4 + shard_vals[4:])) == [], "★ 39/43 正好够"
assert A.invalid_reasons(mk("M3", 1, 1, shard_vals, budget_stop=True)) == ["BUDGET_STOP"]
assert A.invalid_reasons({**mk("M3", 1, 1, shard_vals), "budget_stop": None}) == ["BUDGET_STOP"], "★ 缺 budget_stop 字段不许当没撞线"
assert _refuses(lambda: A.choose(W["PASS"] + [v_rep] * 3, allow_offline=True)), "★ 19 份结果必须拒收"
for name, bad in (("预注册 sha", {"prereg_sha256": "0" * 64}), ("context", {"context": "x"}), ("k", {"k": 5}),
                  ("面板成员带生产 hash", {"instrument_hash": G.PROD_HASH}), ("spec 不止差 model", {"spec_minus_model_sha": "x"}),
                  ("分片号与条目对不上", {"shard": 2}), ("分片号越界", {"shard": 3})):
    _reverse("完整性不符拒收: " + name, _refuses(lambda: A.choose(W["PASS"][:4] + [{**mk("M2.5", 1, 1, shard_vals), **bad}],
                                                                    allow_offline=True)))
pub_bad = mk("M3", 1, 1, shard_vals)
pub_bad["readouts"][0]["published_rule_Q"] = False
_reverse("生产读数有值却没发布 ⇒ 拒收", _refuses(lambda: A.choose([pub_bad], allow_offline=True)))
print("有效性: 分片覆盖率 39/43 / 预算停 / 替补 / 缺片不拼槽 / 结果数上限 18 / 完整性拒收 按预注册")


# ── 变异: 改坏必须红 ──
def mutant(path, old, new, name):
    src = _src(path)
    assert src.count(old) == 1, old
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(src.replace(old, new), str(path), "exec"), mod.__dict__)
    return mod


def an_mutant(old, new):
    mod = mutant(AN_PATH, old, new, "gate_gp_analyze_mutant")
    mod.RUN = G
    return mod


def _red(fn):
    try:
        return fn()
    except (KeyError, IndexError, TypeError):
        return True          # 改坏后直接崩也算见红


prod_outlier = world(base, base, {"M2.5": [dev(i, 1) for i in NN], "M2.7": [dev(i, 1) for i in NN], "M2": base})
p79 = world([dev(i, 1) if i < 7 else base[i] for i in NN], base, {m: base for m in OTH})
both_miss = world([None] * 4 + base[4:], [None] * 4 + base[4:], {m: base for m in OTH})
assert VERD(run_set(prod_outlier))[1] == "FAIL" and VERD(run_set(p79))[0] == "UNRESOLVED"
assert run_set(both_miss)["a_production_rerun_stability"]["n_pairs"] == 82
mislabeled = W["PASS"][:M2R1S1] + [{**W["PASS"][M2R1S1 + 1], "shard": 1}] + W["PASS"][M2R1S1 + 1:]
assert _refuses(lambda: A.choose(mislabeled, allow_offline=True))
AMUTS = {
    "生产进共识(不留一)": ("p, cons = V[(PROD, r)][i], consensus([V[(m, r)][i] for m in OTHERS])",
                    "p, cons = V[(PROD, r)][i], consensus([V[(m, r)][i] for m in MEMBERS])",
                    lambda an: VERD(run_set(prod_outlier, an))[1] != "FAIL"),
    "MISSING 配对当一致": ("pairs = [(x, y) for x, y in pairs if x is not None and y is not None]", "pairs = list(pairs)",
                     lambda an: run_set(both_miss, an)["a_production_rerun_stability"]["n_pairs"] != 82),
    "(a) 阈值换成 0.80": ("THR_A, THR_BC = 0.875, 0.80", "THR_A, THR_BC = 0.80, 0.80",
                     lambda an: VERD(run_set(p79, an))[0] != "UNRESOLVED"),
    "(a) 用点估计代替精确界": ("L, U = cp_bounds(X, n)", "L = U = X / n", lambda an: VERD(run_set(p79, an))[0] != "UNRESOLVED"),
    "不查覆盖率": ("if cov < RUN.MIN_COVERAGE else []", "if False else []",
              lambda an: ("M2", 1) in an.choose(with_bad, allow_offline=True)[0]),
    "不查预算停": ('(["BUDGET_STOP"] if r.get("budget_stop") is not False else [])', "([])",
              lambda an: an.invalid_reasons(mk("M3", 1, 1, shard_vals, budget_stop=True)) == []),
    "槽不全也判 (b)(c)": ('if have_all and b["n_cells"] and c["n_cells"]:', 'if b["n_cells"] and c["n_cells"]:',
                     lambda an: VERD(run_set(W["PASS"][:15], an))[2] != "UNRESOLVED"),
    "结果数不设上限": ("if len(results) > MAX_RESULTS:", "if False:",
                lambda an: not _refuses(lambda: an.choose(W["PASS"] + [v_rep] * 3, allow_offline=True))),
    "缺一片也拼槽": ("        if len(parts) == len(RUN.SHARDS):\n", "        if parts:\n",
               lambda an: _red(lambda: ("M2", 2) in an.choose(W["PASS"][:15], allow_offline=True)[0])),
    "不核分片号与条目": ('sid is not None and r.get("item_ids") == sid and [x.get("id") for x in ro] == sid', "True",
                  lambda an: _red(lambda: not _refuses(lambda: an.choose(mislabeled, allow_offline=True)))),
}
for name, (old, new, red) in AMUTS.items():
    _reverse("分析器变异「%s」" % name, red(an_mutant(old, new)))


def run_mutant(old, new):
    return mutant(RUN_PATH, old, new, "gate_gp_run_mutant")


def _value_from_knots0(m):
    o, _ = m.run(True, "M3", 1, transport=FakeS2("M3", 1))
    return any(x["value"] == "reward" for x in o["readouts"])


def _short_not_withheld(m):
    o, _ = m.run(True, "M3", 1, transport=FakeS2("M3", 1, broken=victim))
    return next(x for x in o["readouts"] if x["id"] == ok[0]["id"])["status"] == "OK"


def _member_not_swapped(m):
    o, fk = m.run(True, "M2.5", 1)
    return {p["model"] for p in fk.prompts} != {"MiniMax-M2.5"}


PMUTS = {
    "读数改用 knots[0]": ('rec["value"] = s2m["top1_mode"] if s2m.get("knots") else "NONE"',
                      'rec["value"] = rec["knots0"] if s2m.get("knots") else "NONE"', _value_from_knots0),
    "不扣 s2_short": ('    if q.get("s2_short"):\n', "    if False:\n", _short_not_withheld),
    "面板没真换模型": ("    K.MEASUREMENT_MODEL = key\n    return inst", "    return inst", _member_not_swapped),
}
for name, (old, new, red) in PMUTS.items():
    try:
        hit = red(run_mutant(old, new))
    except AssertionError:
        hit = True          # 断言拦下也算见红
    _reverse("探针变异「%s」" % name, hit)

# ── ⑧ 设计规格 ──
dspec = json.loads(_src(ROOT / "designs/gate_gp_2026-10-03.json"))
assert dspec == json.loads(json.dumps(A.design_spec(), ensure_ascii=False)), "★ 设计规格文件与生成函数不一致"
res = DP.preflight(dspec)
assert res["pass"], res["fails"]
assert len(dspec["design"]) == dspec["n_raw_observations"] == 4 * 2 * 86 and dspec["n_experimental_units"] == dspec["claimed_inferential_n"] == 86
assert (dspec["dispatches_planned"], dspec["items_per_shard"], dspec["calls_per_dispatch_planned"], dspec["per_dispatch_hard_cap"]) == (16, 43, 344, 409)
assert set(dspec["analysis_formula"]["terms"]) == set(dspec["variables"]["categorical"]) == {"model", "run"}
print("设计规格: == 生成函数; design_preflight PASS(model 4 × run 2 × 86 份生产读数, 16 片)")

# ── ⑨ 功效数 == 现算 ──
for blk, n, cut in (("a_at_N86_exact", 86, (69, 81)), ("a_at_N40_exact_superseded", 40, (30, 39))):
    pa = pre["power"][blk]
    for key, p in (("0.70", 0.70), ("0.7681", 0.7681), ("0.85", 0.85), ("0.95", 0.95)):
        got = A.power_a(n, p)
        assert {k: got[k] for k in ("PASS", "FAIL", "UNRESOLVED")} == pa["p=" + key], (n, p, got)
        assert (got["fail_le"], got["pass_ge"]) == cut and "X <= %d" % cut[0] in pa["rule"] and "X >= %d" % cut[1] in pa["rule"]
fails = {n: A.power_a(n, 0.7681)["FAIL"] for n in (80, 81, 83, 84, 85, 86, 87)}
assert fails[80] < 0.80 <= fails[81] and all(fails[n] < 0.80 for n in (83, 84, 85)) and fails[86] >= 0.80 and fails[87] >= 0.80, fails
assert "已按 owner 2026-10-03 修订采用 N=86" in pre["power"]["minimal_decisive_plan_a"] and "64 × 86 = 5504" in pre["power"]["minimal_decisive_plan_a"]
assert pre["power"]["b_c"].startswith("仍然 UNKNOWN"), "★ (b)(c) 仍无先验, 不许写成有"
rows = json.loads(_src(ROOT / "results/reader_mode_gate_rows.json"))["rows"]
byp = collections.defaultdict(list)
for r in rows:
    byp[r["ptr"]].append(r["mode"])
a2 = [sum(x == y for i, x in enumerate(v) for y in v[i + 1:]) / (len(v) * (len(v) - 1) / 2) for v in byp.values()]
assert round(sum(a2) / len(a2), 4) == 0.7681 and len(byp) == 23
print("功效: N=86 判出概率(0.7681 下 81% FAIL)/ N=40 旧数保留 / N>=86 才稳定判出 (a) / (b)(c) 无先验 / 参考值 0.7681(23 条)—— 与预注册一致")

assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
socket.socket.connect = _orig
print("OK tests/test_cce_gate_gp_prereg.py")
