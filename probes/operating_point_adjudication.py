#!/usr/bin/env python3
"""在**各自的工况**上裁定那 7 条 UNREACHABLE —— 零 API, 不改任何生产配置。

## 为什么需要它
两轮消融的判决全部做在**一个工况**上(硬编 --intl + 单一 profile + k∈{3,5} + 合成单语种语料)。
在那个点上,「不可达」与「不承重」**观测不可区分** ——
⇒ **一个只在存量数据上做的消融, 天然会把所有保险丝判成装饰。**

本探针给每条 UNREACHABLE 补上它**自己的工况**, 回答一个具体问题:
**换到那个工况, 它会活吗?**

## 它不做什么
· **不改生产配置。** market=cn 本来就是 scan_draft 的默认值(生产自己加了 --intl);
  profile=agent_memory 是已注册的合法取值; R=3 只是取样构造。
  唯一的例外是 weight 那一路 —— 它是**反事实**测量, 已显式标注。
· **不产出「真实违规率」。** 中文与 agent_memory 两份语料是**我造的夹具**,
  它们能回答「规则在那个工况上会不会响」, 回答不了「真实稿件的违规率是多少」。

## ★ 阴性对照是主结果的一半
只报「阳性命中率」= 只证明规则会响。一条**乱响**的规则会把干净稿判成违规,
那比漏判更贵。故每一档都同时报**特异性**(阴性样本上不响的比例)。
"""
import itertools
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cce_ksep as K            # noqa: E402
import cce_outbound_guard as G  # noqa: E402

D = ROOT / "tests" / "data" / "operating_points"
OUT = ROOT / "tests" / "data" / "operating_point_adjudication.json"


def _load(name):
    return json.loads((D / name).read_text(encoding="utf-8"))


# ── ① market=cn: adlaw_cn 层 ────────────────────────────────────────
def adjudicate_adlaw_cn():
    c = _load("cn_outbound.json")
    rows, hit_pos, miss_rule = [], 0, []
    for s in c["positive"]:
        cn = [h["canonical"] for h in G.scan_draft(s["text"], market="cn", profile="agent_memory")]
        intl = [h["canonical"] for h in G.scan_draft(s["text"], market="intl", profile="agent_memory")]
        ok = s["expect_rule"] in cn
        hit_pos += ok
        if not ok:
            miss_rule.append({"id": s["id"], "expect": s["expect_rule"], "got_cn": cn})
        rows.append({"id": s["id"], "kind": "positive", "cn_hits": cn, "intl_hits": intl,
                     "expect_rule": s["expect_rule"], "matched_expected": ok,
                     "clean_cn": G.is_clean(s["text"], market="cn", profile="agent_memory"),
                     "clean_intl": G.is_clean(s["text"], market="intl", profile="agent_memory")})
    fp = []
    for s in c["negative_near_miss"]:
        cn = [h["canonical"] for h in G.scan_draft(s["text"], market="cn", profile="agent_memory")]
        clean = G.is_clean(s["text"], market="cn", profile="agent_memory")
        if not clean:
            fp.append({"id": s["id"], "hits": cn, "why_should_not_fire": s["why_should_not_fire"]})
        rows.append({"id": s["id"], "kind": "negative", "cn_hits": cn, "clean_cn": clean,
                     "why_should_not_fire": s["why_should_not_fire"]})
    npos, nneg = len(c["positive"]), len(c["negative_near_miss"])
    flip = sum(1 for r in rows if r["kind"] == "positive" and r["clean_cn"] is False
               and r.get("clean_intl") is True)
    return {
        "operating_point": {"market": "cn"},
        "sensitivity": f"{hit_pos}/{npos} 阳性命中了预期规则",
        "specificity": f"{nneg - len(fp)}/{nneg} 阴性近似样本**未**被拦",
        "false_positives": fp,
        "unmatched_positives": miss_rule,
        "★market_flip": f"{flip}/{npos} 条在 cn 档被拦、intl 档放行 —— 这就是硬编 --intl 的实际后果",
        "★verdict": ("LOAD_BEARING_L2_AT_THIS_OPERATING_POINT" if flip > 0 and not fp else
                     "INCONCLUSIVE(有假阳性或零翻转, 见明细)"),
        "rows": rows,
    }


# ── ② profile=agent_memory: 三张品类表 ──────────────────────────────
def adjudicate_profiles():
    c = _load("agent_memory_drafts.json")
    per_tier = {}
    rows, fp = [], []
    for s in c["positive"]:
        am = G.scan_draft(s["text"], market="intl", profile="agent_memory")
        other = G.scan_draft(s["text"], market="intl", profile="hearing_aid")  # 生产用的那个(表里没有)
        tiers = sorted({h["tier"] for h in am})
        got = s["expect_tier"] in tiers
        per_tier.setdefault(s["expect_tier"], {"n": 0, "hit": 0})
        per_tier[s["expect_tier"]]["n"] += 1
        per_tier[s["expect_tier"]]["hit"] += got
        rows.append({"id": s["id"], "kind": "positive", "expect_tier": s["expect_tier"],
                     "tiers_agent_memory": tiers, "n_hits_agent_memory": len(am),
                     "n_hits_production_profile": len(other), "matched_expected": got,
                     "clean_am": G.is_clean(s["text"], market="intl", profile="agent_memory"),
                     "clean_prod": G.is_clean(s["text"], market="intl", profile="hearing_aid")})
    for s in c["negative_near_miss"]:
        clean = G.is_clean(s["text"], market="intl", profile="agent_memory")
        hits = [h["canonical"] for h in G.scan_draft(s["text"], market="intl", profile="agent_memory")]
        if not clean:
            fp.append({"id": s["id"], "hits": hits, "why_should_not_fire": s["why_should_not_fire"]})
        rows.append({"id": s["id"], "kind": "negative", "hits": hits, "clean_am": clean,
                     "why_should_not_fire": s["why_should_not_fire"]})
    npos, nneg = len(c["positive"]), len(c["negative_near_miss"])
    flip = sum(1 for r in rows if r["kind"] == "positive" and r["clean_am"] is False
               and r.get("clean_prod") is True)
    return {
        "operating_point": {"profile": "agent_memory", "market": "intl"},
        "per_tier": per_tier,
        "specificity": f"{nneg - len(fp)}/{nneg} 阴性近似样本**未**被拦",
        "false_positives": fp,
        "★profile_flip": (f"{flip}/{npos} 条在 agent_memory 档被拦、在生产 profile 下放行 —— "
                          "生产 profile 不在 compliance_profiles.json 里, 走静默空回退"),
        "★verdict": ("LOAD_BEARING_L2_AT_THIS_OPERATING_POINT" if flip > 0 and not fp else
                     "INCONCLUSIVE(有假阳性或零翻转, 见明细)"),
        "rows": rows,
    }


# ── ③ R=3: p_floor 守卫 ────────────────────────────────────────────
def adjudicate_p_floor():
    c = _load("r3_separation.json")
    fired, ok, errs = 0, 0, []
    KN = sorted({k for p in c["pairs"] for arm in ("A", "B") for d in p[arm] for k in d})
    for p in c["pairs"]:
        vecs = {arm: [[float(d.get(k, 0.0)) for k in KN] for d in p[arm]] for arm in ("A", "B")}
        try:
            K.separation(vecs["A"], vecs["B"], "fpA", "fpB", nameA=p["nameA"], nameB=p["nameB"])
            ok += 1
        except Exception as e:
            fired += 1
            errs.append(f"{type(e).__name__}: {str(e)[:120]}")
    n = len(c["pairs"])
    # 反事实: 若守卫不在, 会发生什么
    import math
    n_splits = math.comb(6, 3) // 2
    return {
        "operating_point": {"R": 3, "n_splits": n_splits, "p_floor": round(1 / n_splits, 4), "alpha": 0.05},
        "guard_fired": f"{fired}/{n}",
        "passed_through": ok,
        "sample_error": errs[0] if errs else None,
        "★counterfactual_if_removed": (
            f"R=3 ⇒ n_splits={n_splits} ⇒ p_floor={1/n_splits:.4f} > alpha=0.05 "
            f"⇒ **任何一对都不可能判 SEPARATED**。守卫若不在, 这 {n} 对会**静默全判 NOT_SEPARATED**, "
            "而那不是「两文本相同」, 是「这个设计根本没有拒绝能力」—— "
            "一整轮无意义的检验被当成阴性结果读走。"),
        "★verdict": ("LOAD_BEARING_L2_AT_THIS_OPERATING_POINT" if fired == n else
                     f"INCONCLUSIVE(只在 {fired}/{n} 上触发)"),
    }


# ── ④ 反事实: 放行 weight 后, reply 链那三条会活吗 ────────────────────
def adjudicate_weight_gated():
    import cce_k1_status as S
    IH = "d4cce4c745f3f991"
    before = {f: S.knot_readout_usable(f, instrument_hash=IH)[0]
              for f in ("top1", "weight", "intensity")}
    saved = S.KNOT_READOUT_ALLOWLIST
    try:
        S.KNOT_READOUT_ALLOWLIST = set(saved) | {"weight"}
        after = {f: S.knot_readout_usable(f, instrument_hash=IH)[0]
                 for f in ("top1", "weight", "intensity")}
    finally:
        S.KNOT_READOUT_ALLOWLIST = saved
    restored = {f: S.knot_readout_usable(f, instrument_hash=IH)[0]
                for f in ("top1", "weight", "intensity")}
    return {
        "operating_point": {"KNOT_READOUT_ALLOWLIST": "top1 + weight（反事实）"},
        "★this_is_counterfactual_not_a_corpus": (
            "★★ 这一条与前三条**性质不同**: 前三条是换语料/换参数(都是合法生产取值), "
            "这一条是**改扣发名单** —— 而那个扣发有依据(K1-v2 预注册判定 0/5 文本)。"
            "⇒ 本结果只回答「若那条扣发被解除, 这三个组件会不会活」, "
            "**不构成解除扣发的理由**。解除需要新的 K1 证据, 不是这份测量。"),
        "usable_before": before,
        "usable_after": after,
        "restored_ok": restored == before,
        "★verdict": ("UNREACHABLE_CONFIRMED_ROOT_CAUSE_IS_THE_ALLOWLIST"
                     if (not before["weight"]) and after["weight"] else
                     "INCONCLUSIVE(放行后仍不可用 ⇒ 根因不止扣发名单)"),
    }


def main():
    res = {
        "block": "OPERATING_POINT_ADJUDICATION",
        "★zero_api": "全程零 API 请求; 未修改任何生产配置文件。",
        "★scope": "只回答「换到各自工况后它会不会活」。**不产出真实违规率** —— "
                  "中文与 agent_memory 两份语料是造的夹具。",
        "market_cn__adlaw_cn": adjudicate_adlaw_cn(),
        "profile_agent_memory__three_tables": adjudicate_profiles(),
        "R3__p_floor_guard": adjudicate_p_floor(),
        "allowlist__weight_gated_trio": adjudicate_weight_gated(),
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"写入 {OUT.relative_to(ROOT)}\n" + "─" * 72)
    for key in ("market_cn__adlaw_cn", "profile_agent_memory__three_tables",
                "R3__p_floor_guard", "allowlist__weight_gated_trio"):
        r = res[key]
        print(f"■ {key}")
        for k in ("sensitivity", "specificity", "guard_fired", "★market_flip",
                  "★profile_flip", "usable_after", "★verdict"):
            if k in r:
                print(f"    {k}: {r[k]}")
        if r.get("false_positives"):
            print(f"    ★假阳性 {len(r['false_positives'])} 条: "
                  f"{[f['id'] for f in r['false_positives']]}")
        if r.get("unmatched_positives"):
            print(f"    ★未命中预期规则: {r['unmatched_positives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
