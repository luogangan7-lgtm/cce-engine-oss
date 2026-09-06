#!/usr/bin/env python3
"""knot_taxonomy.json 的**首次**消融 —— 零 API, 全部在真实存量读数上重放。

## 为什么是首次而不是重跑
第一轮消融的是 `cce_knot_classify.py`(代码), 第二轮消融的是 `need_taxonomy.json`,
而完备性批评把 `config/knot_taxonomy.json` 明确列为**结构性空白**:
「17625 字节 · 50 处代码引用 · 被 s2 版本闸钉死 · **从未消融**」。
⇒ **没有基线可比**, 所以必须自带阳性对照。

## 判据(沿用 v2 schema)
· **L_prompt** 进不进 s2 模板 / 换不换 instrument_hash
· **L_code**  被代码引用几次
· **L1**      在真实存量 draw 上重放, 聚合输出变不变
· **L2**      判决变不变(measurement_status / 发布结集 / playbook / support_majority)
· **L_gate**  一致性闸(C1 死规则)会不会响
★ **L3 身份(哈希变)是重言, 零证据力** —— 只记录, 不作判据。

## ★ 阳性/阴性对照(不过就作废本轮)
· **阳性**: `knots[].key` 是结的标识符, **必须**被判承重。若我的方法判它装饰 ⇒ 方法坏了。
· **阴性**: `changelog_*` 是纯文档, **必须**被判无消费者。若判它承重 ⇒ 判据是重言式的。

## 工况
gen6(instrument d4cce4c745f3f991) · k=3 · 真实存量 draw(panel_checkpoint.jsonl)。
★ **不产出「换个工况会怎样」** —— 那需要另一份语料。
"""
import copy
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cce_knot_classify as K  # noqa: E402

TAXO_PATH = ROOT / "config" / "knot_taxonomy.json"
TAXO = json.loads(TAXO_PATH.read_text(encoding="utf-8"))
OUT = ROOT / "tests" / "data" / "knot_taxonomy_ablation.json"

# ★★ 2026-09-07: 扫描面必须含 `accuracy/`。
#   第一版只扫 scripts/+probes/, 于是把 `negative_examples_prompt` 判成零引用 ——
#   而它其实在 **accuracy/run_gates.py:65** 被用。
#   ★ 而 accuracy/ 正是完备性批评点名的那块: **九结验收闸本身**,
#     两轮审计都因「零 API」纪律把它结构性排除了。
#   ⇒ **我的扫描面复制了审计的盲区。** 一个只扫自己看得见的地方的引用统计,
#     必然把「我看不见的消费者」判成「没有消费者」。
SRC_DIRS = ("scripts", "probes", "accuracy")
_SRC = {p: p.read_text(encoding="utf-8", errors="ignore")
        for d in SRC_DIRS for p in (ROOT / d).glob("*.py")}


def code_refs(field):
    """字段名的引用计数 —— 返回 (粗, 严) 两个数, **它们是一个区间的两端**。

    ★ 粗计: 任何 `"f"` / `'f'` / `.f` 出现都算 ⇒ **词碰撞会虚高**。
      实测: `status` 粗计 165 而严计 **5**(那 165 里绝大多数是音频/归档模块自己的 status);
      `source` 19 → **0**; `signature` 6 → **0**。
    ★ 严计: 只算**同一行里还出现 taxo/TAXO/knot/KNOT/meta_k** 的 ⇒ **会漏**跨行访问。
    ⇒ 判决用**粗计**(保守: 虚高只会把 NO_CONSUMER 推成 INCONCLUSIVE, 不会反过来),
      但两个数都落盘, 否则 INCONCLUSIVE 这一档读不出含义。
    """
    pats = (f'"{field}"', f"'{field}'", f".{field}")
    crude = sum(sum(s.count(p) for p in pats) for s in _SRC.values())
    strict = 0
    for s in _SRC.values():
        for ln in s.split("\n"):
            if any(p in ln for p in pats) and any(
                    t in ln for t in ("taxo", "TAXO", "knot", "KNOT", "meta_k")):
                strict += 1
    return crude, strict


# ── 真实存量 draw ────────────────────────────────────────────────────
def load_real_draws(limit=8):
    rows = [json.loads(l) for l in
            (ROOT / "tests/data/phase2/panel_checkpoint.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    out = {}
    for r in rows:
        if r.get("arm") == "L0" and str(r.get("qualified")) == "True" and r.get("knots"):
            out.setdefault(r["base_id"], []).append(r["knots"])
    return {b: v[:5] for b, v in list(out.items())[:limit] if len(v) >= 3}


def _stub(draws):
    """按 tag 里的序号取 draw —— **不能用共享迭代器**。

    ★★ 2026-09-07: 第一版正是 `it = iter(draws)` + `next(it)`, 而
      `_stage2_aggregate` 用 **ThreadPoolExecutor(5 线程)** 并发调 `_stage2_draw`
      ⇒ 5 个线程抢同一个迭代器 ⇒ **哪个 draw 落到哪个序号是随机的**
      ⇒ 同样的输入两次聚合结果不同 ⇒ 制造出**伪差异**。
    实测后果: `changelog_*`(纯文档、零引用、不进 prompt)被判 L1 变化 1/8~5/8 —— 随机数。
    ★ 是**阴性对照**把它抓出来的: 删一条变更日志不可能改变聚合输出, 那个数只能是噪声。
    ★ 而第二轮的某个 agent 自曝过**同一个坑**(共享迭代器喂线程池, 制造 95 处伪差异) ——
      我独立地又踩了一次。⇒ 这类 harness 竞态该写进探针模板, 不该每次重新踩。
    """
    def f(prompt, taxo, tag, **kw):
        i = int(str(tag).lstrip("d")) if str(tag).lstrip("d").isdigit() else 0
        if i >= len(draws):
            return None
        d = draws[i]
        return {"knots": [{"key": k, "intensity": float(v)} for k, v in d.items()]}
    return f


def aggregate(taxo, draws):
    orig = K._stage2_draw
    K._stage2_draw = _stub(draws)
    try:
        return K._stage2_aggregate("prompt", taxo, n=len(draws))
    finally:
        K._stage2_draw = orig


def decision_face(agg):
    """L2: 只取真正会改变「发不发 / 发什么」的字段。"""
    ks = agg.get("knots") or []
    return {
        "measurement_status": agg.get("measurement_status"),
        "published_keys": [k["key"] for k in ks],
        "support_majority": [bool(k.get("support_majority")) for k in ks],
        # playbook_primary 是整条链里唯一直接指挥「怎么写」的字段
        "playbook_primary": (ks[0].get("playbook") or "")[:120] if ks else None,
        "top1_unanimous": (agg.get("sampling") or {}).get("top1_unanimous"),
    }


# ── 消融 ─────────────────────────────────────────────────────────────
def ablate_toplevel(field, draws_by_base):
    t = copy.deepcopy(TAXO)
    t.pop(field, None)
    return _measure(t, field, draws_by_base)


def ablate_knot_field(field, draws_by_base):
    t = copy.deepcopy(TAXO)
    for kn in t["knots"]:
        kn.pop(field, None)
    return _measure(t, field, draws_by_base)


def _measure(t, field, draws_by_base):
    _crude, _strict = code_refs(field)
    r = {"field": field, "code_refs": _crude, "code_refs_strict": _strict,
         "★refs_note": "粗计会因词碰撞虚高, 严计会漏跨行 —— 二者是区间两端; 判决用保守的粗计"}
    kw = dict(k=3, knot_n=5, s1_pairing="round_robin_over_3_s1_draws")
    base_tpl = K._stage2_template(TAXO)
    base_ih = K.instrument_id(TAXO, **kw)["instrument_hash"]
    try:
        r["prompt_changed"] = K._stage2_template(t) != base_tpl
        r["l3_hash_changed"] = K.instrument_id(t, **kw)["instrument_hash"] != base_ih
    except Exception as e:
        r["prompt_changed"] = f"IMPORT_BREAKS: {type(e).__name__}"
        r["l3_hash_changed"] = None
        r["l1_changed"] = r["l2_changed"] = "N/A(取模板即崩)"
        r["verdict"] = "LOAD_BEARING_L2"
        r["why"] = f"删掉它连 s2 模板都取不出来({type(e).__name__}) —— 仪器无法构造"
        return r

    l1, l2 = 0, 0
    for b, draws in draws_by_base.items():
        try:
            a0 = aggregate(TAXO, draws)
            a1 = aggregate(t, draws)
        except Exception as e:
            r["l1_changed"] = r["l2_changed"] = f"AGG_BREAKS: {type(e).__name__}"
            r["verdict"] = "LOAD_BEARING_L2"
            r["why"] = f"聚合期抛 {type(e).__name__} —— 读数产不出来"
            return r
        if json.dumps(a0, ensure_ascii=False, sort_keys=True) != \
           json.dumps(a1, ensure_ascii=False, sort_keys=True):
            l1 += 1
        if decision_face(a0) != decision_face(a1):
            l2 += 1
    n = len(draws_by_base)
    r["l1_changed"] = f"{l1}/{n}"
    r["l2_changed"] = f"{l2}/{n}"
    if l2:
        r["verdict"] = "LOAD_BEARING_L2"
        r["why"] = f"判决面 {l2}/{n} 改变"
    elif l1:
        r["verdict"] = "LOAD_BEARING_L1_ONLY"
        r["why"] = f"读数 {l1}/{n} 变但判决面不变 —— 谁在消费这个数字?"
    elif r["code_refs"] == 0 and not r["prompt_changed"]:
        r["verdict"] = "NO_CONSUMER"
        r["why"] = "零代码引用 + 不进 prompt + 读数判决皆不变"
    else:
        r["verdict"] = "INCONCLUSIVE"
        r["why"] = (f"读数与判决皆不变, 但有 {r['code_refs']} 处引用(严计 {r['code_refs_strict']})"
                    f"{'/进 prompt' if r['prompt_changed'] else ''} —— "
                    "**在本工况的存量 draw 上测不出来**, 不等于无用")
    return r


def main():
    draws = load_real_draws()
    print(f"真实存量 draw: {len(draws)} 个 base × 3–5 次重复 · 工况 gen6/k=3")
    print("─" * 78)

    tops = [k for k in TAXO if k != "knots"]
    knot_fields = sorted({f for kn in TAXO["knots"] for f in kn})
    rows = [{"scope": "top", **ablate_toplevel(f, draws)} for f in tops]
    rows += [{"scope": "knot", **ablate_knot_field(f, draws)} for f in knot_fields]

    # ── 对照 ───────────────────────────────────────────────────────
    by = {r["field"]: r for r in rows}
    pos = by.get("key", {}).get("verdict")
    negs = [by[f]["verdict"] for f in tops if f.startswith("changelog")]
    ctrl = {
        "positive_knots_key": {"verdict": pos, "passed": pos and pos.startswith("LOAD_BEARING"),
                               "★why": "结的标识符; 我的方法若判它装饰 ⇒ 方法坏了, 本轮作废"},
        "negative_changelogs": {"verdicts": sorted(set(negs)),
                                "passed": all(v == "NO_CONSUMER" for v in negs),
                                "★why": "纯文档; 判它承重 ⇒ 判据是重言式的"},
    }
    ok = ctrl["positive_knots_key"]["passed"] and ctrl["negative_changelogs"]["passed"]

    for r in rows:
        print(f"  {r['verdict']:22s} {r['scope']:4s} {r['field']:34s} "
              f"refs={r['code_refs']:<3}/{r['code_refs_strict']:<3} prompt={str(r['prompt_changed'])[:5]:5s} "
              f"L1={str(r['l1_changed'])[:7]:7s} L2={str(r['l2_changed'])[:7]}")

    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("─" * 78)
    print("对照:", "✅ 双向通过" if ok else "★★ 未通过 —— 本轮判决作废", ctrl)
    print("汇总:", tally)

    OUT.write_text(json.dumps({
        "block": "KNOT_TAXONOMY_ABLATION_GEN1",
        "★first_ever": "本文件从未被消融过(两轮审计均跳过) ⇒ 无基线可比, 故自带双向对照。",
        "★operating_point": {"instrument": "d4cce4c745f3f991(gen6)", "k": 3,
                             "draws": f"{len(draws)} base × 3–5 rep, 真实存量 panel_checkpoint",
                             "★scope": "**不产出「换个工况会怎样」** —— 那需要另一份语料"},
        "★l3_is_tautology": "哈希变了只记录, **不作判据** —— 任何进指纹的字符串改了它都会变。",
        "controls": ctrl, "controls_passed": ok,
        "tally": tally, "rows": rows,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("写入", OUT.relative_to(ROOT))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
