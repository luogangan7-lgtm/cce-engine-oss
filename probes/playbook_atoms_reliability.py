#!/usr/bin/env python3
"""playbook 原子分解读数的复现性。前登记: tests/data/phase2/playbook_atoms_prereg.json

判据、选文、仪器在测量前冻结, 见该文件与 git 历史。这里只执行。
"""
import json, os, re, statistics, sys, threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cce_align_v2 as A                      # noqa: E402

P = ROOT / "tests" / "data" / "phase2"

# ★ 2026-09-05: 按**代**隔离三个路径。此前全部写死为 GEN1 的文件名, 而本探针会
#   **断点续跑**(从 checkpoint 读 done) —— GEN1 的 64 条已填满, 直接重跑会让 jobs 为空,
#   于是拿**旧分解下采集的数据**算出一个「新一代判决书」, 且数字完全合理、没有任何东西报警。
#   这是**混淆**不是归零, 非退化闸也抓不到。⇒ 代号进文件名, 让它在构造上不可能发生。
GEN = os.environ.get("CCE_ATOMS_GEN", "1")
_suffix = "" if GEN == "1" else f"_gen{GEN}"
SPEC = json.loads((P / f"playbook_atoms{_suffix}_prereg.json").read_text(encoding="utf-8"))
CKPT = P / f"playbook_atoms{_suffix}_checkpoint.jsonl"
VERDICT = P / f"playbook_atoms{_suffix}_verdict.json"
PANEL = P / "panel_checkpoint.jsonl"
MAN = json.loads((P / "panel_manifest.json").read_text(encoding="utf-8"))
N = SPEC["design"]["n_per_text"]
C = SPEC["criterion"]
_lock = threading.Lock()

# 禁令标记。原子以此二分, 复合值只由正向原子算 —— 理由见预注册。
_NEG = ("不", "别", "绝不", "勿", "禁止")

PROMPT = """你判定一段内容是否执行了某个"拆除动作清单"里的每一条。

【阻挡结】{knot}
判据(受众处于该状态的表现): {discr}

【待判内容】
{text}

【逐条判定】下面每条独立判, 只判**是否实际执行**, 不判好坏, 不判是否提到该话题。
执行 = 内容里有**可逐字指认的句子**在做这条描述的事; 只是谈论相关话题不算执行。
{items}

只输出JSON: {{"atoms": [{{"i": 序号, "executed": 0或1, "quote": "逐字子串, 未执行则空"}}]}}
★ executed=1 必须给出内容里的**原样子串**; 给不出就填 0。"""

# ★ 2026-09-05 GEN3: v2 提问形式 —— 按条目类型分别提问。
#   v1 的缺陷(底噪 A/A 实测): 它对**每一条**都问「执行了吗 + 必须给逐字子串」,
#   而禁令的「满足」是**缺席**, **你没法为「不存在」引一段原文**。
#   实测 belong 的「不派任务」无子串率 **0.733** ⇒ 判官想说满足却给不出子串, 被记成违反。
#   ⇒ 举证责任应落在**可举证的一侧**: 违反是在场的(有一句在派任务), 可引证。
#
# ★ v1 **原样保留**: GEN1/GEN2 与底噪 A/A 都是在 v1 下采集的, 它们的判决书还挂在仓里。
#   旧代必须能原样重跑, 否则「可比不可合」就成了一句空话。
PROMPT_V2 = """你判定一段内容对一份"拆除动作清单"的逐条符合情况。

【阻挡结】{knot}
判据(受众处于该状态的表现): {discr}

【待判内容】
{text}

【逐条判定】下面每条独立判, 不判好坏, 不判是否提到该话题。
★ **两类条目问的问题不同, 不要混**:
· 标【做】的条目 —— 问「内容里**有没有**在做这件事」。
  有 ⇒ hit=1, 并给出**做这件事的那句原样子串**; 给不出子串就填 0。
· 标【禁】的条目 —— 问「内容里**有没有违反**这条禁令」。
  违反 ⇒ hit=1, 并给出**违反处的原样子串**;
  ★ 找不到违反 ⇒ hit=0, **不需要子串**(没有违反, 本来就没有可引的原文)。
{items}

只输出JSON: {{"atoms": [{{"i": 序号, "hit": 0或1, "quote": "原样子串, hit=0 则空"}}]}}
★ hit=1 必须给出内容里的**原样子串**; 给不出就填 0。"""


def atoms_of(knot: str):
    """playbook 原文即分号分隔 ⇒ 直接拆, 不另造一套。返回 [(text, is_prohibition)]。"""
    raw = A.PLAYBOOK.get(knot, "")
    parts = [p.strip() for p in re.split(r"[;；]", raw) if p.strip()]
    return [(p, any(p.startswith(n) or n in p[:3] for n in _NEG)) for p in parts]


def read_once(knot, text, temperature, form="v1"):
    """一次读数。form 决定**提问形式**: v1 对所有条目问「执行了吗」; v2 按类型分问。

    ★ form 必须显式传, 且**按代冻结** —— 换提问形式就是换 manipulation, 不是重构。
    """
    items = atoms_of(knot)
    if form == "v2":
        listing = "\n".join(f"{i+1}. 【{'禁' if neg else '做'}】{t}"
                             for i, (t, neg) in enumerate(items))
        tmpl, field = PROMPT_V2, "hit"
    else:
        listing = "\n".join(f"{i+1}. {t}" for i, (t, _) in enumerate(items))
        tmpl, field = PROMPT, "executed"
    out = A._call(tmpl.format(knot=knot, discr=A.DISCR.get(knot, ""),
                              text=text, items=listing), temperature=temperature)
    d = A._extract_json(out)
    if not isinstance(d, dict) or not isinstance(d.get("atoms"), list):
        return None
    got = {}
    for a in d["atoms"]:
        try:
            i = int(a["i"]) - 1
        except Exception:
            continue
        if 0 <= i < len(items):
            raw = 1 if a.get(field) in (1, "1", True) else 0
            q = str(a.get("quote") or "")
            # 无逐字支撑的 1 记为 0 —— 预注册写死, 两个 form 同规则
            supported = raw if (raw == 0 or q.strip()) else 0
            unsupported = raw == 1 and not q.strip()
            if form == "v2" and items[i][1]:
                # ★ 禁令在 v2 下问的是「违反了吗」⇒ **满足 = NOT 违反**。
                #   取反后放回同一个槽位, 使 executed 的含义与 v1 一致(禁令: 1=满足),
                #   否则跨代的 per_atom 对照会读反。
                got[i] = (1 - supported, q, unsupported)
            else:
                got[i] = (supported, q, unsupported)
    if len(got) != len(items):
        return None
    pos = [i for i, (_, neg) in enumerate(items) if not neg]
    if not pos:
        return None
    return {"atoms_hit": round(sum(got[i][0] for i in pos) / len(pos), 4),
            "violations": sum(1 - got[i][0] for i, (_, neg) in enumerate(items) if neg),
            "unsupported": sum(1 for v in got.values() if v[2]),
            "n_positive": len(pos), "n_atoms": len(items),
            # ★ 2026-09-05: 逐原子结果必须落盘。此前只存聚合的 atoms_hit, 逐原子判完即丢 ——
            #   同一天里**两次**因此无法定论: ① 用旧数据预检 A1 效果时, 分不出 0.5 是哪个原子在命中
            #   ② GEN2 audit 掉到 0.429 后, 分不开「跨轮原子被判成执行过」与「清单变短改变了
            #      判官对剩下那条的判断」两种机制。
            #   ⇒ 聚合值回答不了「是哪个原子在动」, 而那恰是每次真正要问的问题。
            "per_atom": [{"i": i, "text": items[i][0], "is_prohibition": items[i][1],
                          "executed": got[i][0], "quote": got[i][1],
                          "unsupported": got[i][2]} for i in range(len(items))]}



def texts_and_knots(texts):
    """每个文本的 top-1 结 + 正文, 由**已冻结的面板读数**确定, 不重测。

    ★ 2026-09-05 抽成函数: 底噪探针需要**完全相同**的选结逻辑 —— 各写一份就会漂,
      而漂了就等于量了别的臂的噪声。抄一遍时我已经漂过一次(把 r["knots"] 当成了
      对象列表), 当场报错。⇒ 共用一份, 让它在构造上不可能不一致。
    """
    arms = {(a["base_id"], a["arm"]): a for a in MAN["arms"]}
    knots = defaultdict(list)
    for l in PANEL.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get("arm") == "L0" and str(r.get("qualified")) == "True" and r.get("knots"):
            knots[r["base_id"]].append(r["knots"])
    out = []
    for t in texts:
        bid = t["base_id"]
        tally = Counter(max(kk, key=kk.get) for kk in knots[bid])
        out.append((bid, tally.most_common(1)[0][0], arms[(bid, "L0")]["text"]))
    return out


def main():
    if not os.environ.get("MINIMAX_API_KEY"):
        print("★ 无 MINIMAX_API_KEY —— 不出结论, 不降级。"
              "(2026-08-18 实事故: 无 key 时返回 0.0 使断言退化成 0==0)")
        return 2
    ih = os.environ.get("CCE_INSTRUMENT_HASH", "565470cf26c16d01")
    assert ih == SPEC["instrument"]["must_equal"], f"★ 仪器不符: {ih}"

    # 每个文本的 top-1 结, 由**已冻结的面板读数**确定, 不重测
    todo = texts_and_knots(SPEC["design"]["texts"])

    done = {}
    if CKPT.exists():
        for l in CKPT.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                done[(r["base_id"], r["rep"])] = r

    print(f"预注册: {SPEC['block']} | 判据 |Δ|<={C['delta']} 一致率>={C['agreement_min']} | "
          f"{len(todo)} 文本 × {N} 重复")
    print("原子数:", {k: len(atoms_of(k)) for k in sorted({k for _, k, _ in todo})})
    print("-" * 74)

    jobs = [(b, k, tx, r) for (b, k, tx) in todo for r in range(N) if (b, r) not in done]

    def run(job):
        b, k, tx, r = job
        for attempt in range(4):
            v = read_once(k, tx, [0.0, 0.3, 0.6, 0.9][attempt])
            if v:
                rec = {"base_id": b, "knot": k, "rep": r, **v, "ok": True}
                with _lock:
                    with open(CKPT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                return rec
        return None      # 解析失败**不算一次读数**, 不进 n

    if jobs:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for rec in ex.map(run, jobs):
                if rec:
                    done[(rec["base_id"], rec["rep"])] = rec

    per, medians, all_pos_rates = {}, [], []
    for b, k, _ in todo:
        vals = [done[(b, r)]["atoms_hit"] for r in range(N) if (b, r) in done]
        if len(vals) < C["n_min"]:
            per[b] = {"n": len(vals), "verdict": "INSUFFICIENT"}
            continue
        pairs = [(i, j) for i in range(len(vals)) for j in range(i + 1, len(vals))]
        agree = sum(abs(vals[i] - vals[j]) <= C["delta"] for i, j in pairs) / len(pairs)
        med = statistics.median(vals)
        medians.append(med)
        all_pos_rates.extend(vals)
        per[b] = {"n": len(vals), "knot": k, "agreement": round(agree, 4),
                  "median": round(med, 3), "range": round(max(vals) - min(vals), 3),
                  "verdict": "PASS" if agree >= C["agreement_min"] else "FAIL"}

    for b, v in per.items():
        print(f"  {v['verdict']:4} {b}  n={v['n']} "
              + (f"一致率 {v['agreement']:.3f} 中位 {v['median']:.2f} 极差 {v['range']:.2f} "
                 f"[{v.get('knot')}]" if "agreement" in v else ""))

    ok = sum(v["verdict"] == "PASS" for v in per.values())
    d1 = len(set(round(m, 3) for m in medians)) >= 3 and (max(medians) - min(medians)) >= 0.20
    d2 = len(set(all_pos_rates)) > 1 and 0 < statistics.mean(all_pos_rates) < 1
    print("-" * 74)
    print(f"非退化① 中位数取值 {len(set(round(m,3) for m in medians))} 种, 极差 "
          f"{(max(medians)-min(medians)) if medians else 0:.2f} ⇒ {'过' if d1 else '不过'}")
    print(f"非退化② 正向原子执行率 均值 {statistics.mean(all_pos_rates):.3f} "
          f"(非常数 {len(set(all_pos_rates))>1}) ⇒ {'过' if d2 else '不过'}")

    if not (d1 and d2):
        decision = "DEGENERATE"
    _line = C.get("adoption_line", 7)
    assert _line == 7, f"★ 采纳线被改成了 {_line} —— 阈值不因看到结果而下调, 拒绝执行"
    if False:
        pass
    elif ok >= _line:
        decision = "USABLE"
    elif ok >= 5:
        decision = "INCONCLUSIVE"
    else:
        decision = "UNRELIABLE"
    print(f"{ok}/8 文本达标 ⇒ **{decision}**   (对照: playbook_hit GEN4 = 4/8 UNRELIABLE)")

    import datetime
    VERDICT.write_text(json.dumps(
        {"block": SPEC["block"],
         # ★ 此前写死 "2026-09-04" —— 重跑会报一个假日期, 而假日期让任何时序对账失效
         "measured_at": datetime.date.today().isoformat(),
         "instrument_hash": ih, "texts": len(todo), "meeting_criterion": ok,
         "per_text": per, "degeneracy": {"medians_distinct": d1, "not_constant": d2},
         "decision": decision,
         "★baseline": SPEC.get("★baseline_for_verdict",
                                 "playbook_hit GEN4: 4/8 UNRELIABLE, 同一批文本同一仪器同一判据线"),
         "★comparable_not_poolable": "同文本同判据同仪器、只差 manipulation ⇒ 允许并列对照, "
                                     "**绝不汇总成一个 n**"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
