#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两份真实 provider 后续预注册的守卫(2026-10-01): S1 加大条目数 / main() 真实端到端。只跑 --offline, 零网络。

守: ① 预注册 sha 钉在探针里 ② 上限钉死(S1 260 / e2e 520)且计划调用不超 ③ S1 功效表 == 现算
    ④ S1 条目 51 条且与第一轮 30 条不相交 ⑤ 两份离线干跑走完、尝试数如预注册 ⑥ 两份设计规格过 design_preflight。
反向(改坏必须红): sha 不符拒跑 · 上限压低即撞 · 条目与第一轮重叠被抓 · run_gates 编排被改坏 ⇒ ORCHESTRATION_FAIL · 预设刺激环境变量拒跑。
"""
import hashlib, json, os, pathlib, socket, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "scripts"))
_TRIPPED = []
_orig = socket.socket.connect
def _guard(s, addr, *a, **k):
    _TRIPPED.append(addr)
    raise AssertionError("★★★ 离线隔离被突破: %r" % (addr,))
socket.socket.connect = _guard

import accuracy_s1_large_n_run as S1       # noqa: E402
import accuracy_main_e2e_real_run as E2E   # noqa: E402
import design_preflight as DP              # noqa: E402

R1_ITEMS = json.loads((ROOT / "tests/data/accuracy_real_provider_result.json").read_text(encoding="utf-8"))["items"]


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _refuses(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


def _reverse(name, ok):
    assert ok, "★★★ 反向没见红: %s" % name
    print("  反向见红 ✓", name)


# ── S1 ──
pre = json.loads(S1.PREREG.read_text(encoding="utf-8"))
assert _sha(S1.PREREG) == S1.PREREG_SHA256, "★ S1 预注册被改过而钉住的 sha 没跟 —— 预注册必须跑前冻结"
assert S1.CAP == pre["budget"]["hard_cap_requests"] == 260 and S1.AUTH_ID == pre["budget"]["auth_id"]
assert pre["cells"]["S1_dist_retest"]["calls_planned"] == pre["budget"]["calls_planned"] == 2 * 2 * 51 <= S1.CAP
assert pre["power_analysis"]["computed"] == json.loads(json.dumps(S1.power())), "★ 预注册里的功效表与现算不符"


def check_items(items, sample_ids):
    assert len(items) == pre["sample"]["n"] == 51, len(items)
    assert not set(items) & set(R1_ITEMS), "★ 与第一轮条目重叠: %r" % sorted(set(items) & set(R1_ITEMS))[:3]
    assert set(items) | set(R1_ITEMS) == sample_ids and len(R1_ITEMS) == 30


dry = S1.run(offline=True)
import accuracy_offline_harness as AH       # noqa: E402
_m = AH.load(responses=lambda m, p: "")
SAMPLE_IDS = {x["id"] for x in _m.SAMPLE}
check_items(dry["items"], SAMPLE_IDS)
assert set(dry["cells"]) == {"S1_MiniMax-M3", "S1_MiniMax-M2.7"} and "★budget_stop" not in dry, dry["cells"].keys()
assert dry["http_attempts"] == 204 and all(c["verdict"] in ("STABLE", "UNSTABLE", "INCONCLUSIVE") for c in dry["cells"].values())
print("S1: sha 钉 / 上限 260 / 功效表现算 / 51 条不相交 / 离线干跑 204 次 —— 全过")

saved = S1.PREREG_SHA256
S1.PREREG_SHA256 = "0" * 64
try:
    _reverse("S1 预注册 sha 不符 ⇒ 拒跑", _refuses(lambda: S1.run(offline=True)))
finally:
    S1.PREREG_SHA256 = saved
S1.CAP = 100
try:
    _reverse("S1 上限压到 100 ⇒ 撞上限停", "★budget_stop" in S1.run(offline=True))
finally:
    S1.CAP = 260
first51 = [x["id"] for x in sorted(_m.SAMPLE, key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())[:51]]
try:
    check_items(first51, SAMPLE_IDS)
    caught = False
except AssertionError as e:
    caught = "重叠" in str(e)
_reverse("S1 条目含第一轮 30 条(不跳过) ⇒ 被抓", caught)

# ── main() 真实端到端 ──
pe = json.loads(E2E.PREREG.read_text(encoding="utf-8"))
assert _sha(E2E.PREREG) == E2E.PREREG_SHA256, "★ e2e 预注册被改过而钉住的 sha 没跟"
assert E2E.CAP == pe["budget"]["hard_cap_requests"] == 520 and E2E.AUTH_ID == pe["budget"]["auth_id"]
assert pe["calls_planned"]["total_max"] == pe["budget"]["calls_planned_max"] == 25 + 405 + 81 + 1 <= E2E.CAP
assert set(pe["decision"]["properties"]) == {"O%d" % i for i in range(1, 9)}

res, rec, g, raw = E2E.run(offline=True)
assert res["verdict"] == "ORCHESTRATION_PASS" and res["failed_properties"] == [], res.get("failed_properties")
assert {k[:2] for k in res["properties"]} == {"O%d" % i for i in range(1, 9)}, "★ 探针性质与预注册 O1–O8 不对应"
assert res["logical_calls"]["qualify"] == 25 and res["logical_calls"]["fact"] == 81 and res["http_attempts"] <= E2E.CAP
print("e2e: sha 钉 / 上限 520 / 离线干跑 ORCHESTRATION_PASS(O1–O8 全真, %d 次尝试) —— 全过" % res["http_attempts"])

saved = E2E.PREREG_SHA256
E2E.PREREG_SHA256 = "0" * 64
try:
    _reverse("e2e 预注册 sha 不符 ⇒ 拒跑", _refuses(lambda: E2E.run(offline=True)))
finally:
    E2E.PREREG_SHA256 = saved
os.environ["CCE_BODY_CHARS"] = "500"
try:
    _reverse("e2e 预设刺激环境变量 ⇒ 拒跑", _refuses(lambda: E2E.run(offline=True)))
finally:
    os.environ.pop("CCE_BODY_CHARS")
E2E.CAP = 100
try:
    _reverse("e2e 上限压到 100 ⇒ BUDGET_STOP", E2E.run(offline=True)[0]["verdict"] == "BUDGET_STOP")
finally:
    E2E.CAP = 520


def _mut(old, new):
    def f(src):
        assert src.count(old) == 1, old[:40]
        return src.replace(old, new)
    return f


MUTS = {   # 拿掉一道编排守卫 ⇒ 对应性质必须翻假
    "原始标注不落盘": ('_raw = os.path.join(_OUT_DIR, "raw_annotations.json")', '_raw = os.path.join(_OUT_DIR, "_lost", "raw.json")', "O5"),
    "空抽取不扣发 G-K2": ("        if not rows:\n            # ★ fail-closed", "        if False:\n            # ★ fail-closed", "O8"),
    "G-K2 扣发时 overall 折成 bool": ('if gk2["pass"] is not None else None),', 'if True else None),', "O8"),
    # 默认合成回复下 G_K1 过、G_K2 不过 ⇒ 这条是等价变异; 换「次结分歧 + 事实相关」(G_K1 不过、G_K2 过)才看得见
    "overall 不看 G-K1": ('bool(gk1["pass"] and gk2["pass"]', 'bool(True and gk2["pass"]', "O6",
                         {"dist_mode": "split", "fact_mode": "correlated"}),
}
for name, (old, new, prop, *kw) in MUTS.items():
    r = E2E.run(offline=True, mutator=_mut(old, new), fake_kw=(kw or [None])[0])[0]
    _reverse("e2e 变异「%s」⇒ %s 红" % (name, prop),
             r.get("verdict") == "ORCHESTRATION_FAIL" and any(k.startswith(prop) for k in r["failed_properties"]))

# ── 设计规格 ──
for p in ("designs/accuracy_s1_large_n_2026-10-01.json", "designs/accuracy_main_e2e_real_2026-10-01.json"):
    spec = json.loads((ROOT / p).read_text(encoding="utf-8"))
    r = DP.preflight(spec)
    assert r["pass"], (p, r["fails"])
    assert spec["claimed_inferential_n"] <= spec["n_experimental_units"] and set(spec["analysis_formula"]["terms"]) <= set(spec["variables"]["categorical"])
assert json.loads((ROOT / "designs/accuracy_s1_large_n_2026-10-01.json").read_text(encoding="utf-8"))["n_experimental_units"] == 51
print("设计规格: 两份 design_preflight PASS")

assert _TRIPPED == [], "★★★ 绊线被触发: %r" % _TRIPPED
socket.socket.connect = _orig
print("OK tests/test_cce_accuracy_real_followup_prereg.py")
