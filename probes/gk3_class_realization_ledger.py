#!/usr/bin/env python3
"""G-K3-min「类实现台账」—— 九个结**有没有被仪器实现**。零 API, 只读既有产物。

## ★★★ 这个文件替换掉的东西是一个重言

原 G-K3 叫「签名两两可分」, 判据被读成「9 个结的 6 元签名互不重复」。
2026-09-07 独立核验(probes 之外三份提案 + 对抗核验)判 **YES_TAUTOLOGY, 无保留**:

**① 判红条件在作者意图上不可达。** 六元组只在两行**逐字全等**时才红 ——
   写九个结的人不会把其中一个抄两遍。那是 `uniqueItems` lint, 不是闸。

**② codomain 不受控 —— 与消融审计判零证据力的 L3 instrument_hash 同一个毛病。**
   值域里已经躺着「威胁」与「威胁(孤立)」、「已满足」与「已满足(即时)」、
   「现在」/「无限期现在」/「过去-现在」、以及「不确定」(这根本不是取值, 是取值缺失)。
   **给任一格加个括号后缀, 汉明距就变大, 而对世界的断言一个字没变。**
   实测: 字面汉明 {2:1,3:2,4:12,5:13,6:8} min=2;
        按语义(斜杠=析取, 括号=子类型)读取值集合是否互斥 ⇒ min **塌到 1**。

**③ 有直接反例, 不是论证。`belong`:**
     纸面严格互斥最小距 **3**(九结里靠上一档) —— 而仪器**共识 argmax 0/78**。
   **纸面满分, 仪器从不把它排第一。** 原读法会把 belong 排进「分得最开」的那一档。
   ★★ 但「0/308」这个说法我**用错了单位**: 308 = 4 标注者 × 77 条, 是 **rater decisions**,
      不是独立文本。正确表述是 **0/78 个独立单位**, 单侧 95% 上界 **3.77%** ——
      **排除不了真实 prevalence 是 1%~3%**。(2026-09-07 网页 GPT 调研指出。)
   ★★ 且 belong **进过 4/78 条的 top2、10/78 有非零权重** ⇒ 它**不是**代数惰性坐标:
      删掉它并重归一化**会**改变平均 JS 与 top2 命中率。

**④ 它测的对象是错的。** 可分性是**仪器 × 语料**的性质, 不是文档的性质。
   在 config 上算, 无论怎么加严(哪怕要求 min 汉明 ≥4), 都只是在审自己的写作。

**⑤ 书面自证。** 2026-08-07 为四大混淆对加的 `hard_discriminant`, 本身就是作者承认
   「签名不足以区分它们」。而它**从未进过标注 prompt**: **`KNOT_BRIEF` 不注入 `hard_discriminant`**
   (由 tests/test_cce_gk3_not_a_tautology.py 的断言钉住); 它在 run_gates.py 里唯一一次出现是
   **诊断 prompt 要模型输出的 JSON 键名**。⇒ 只读 signature 的 G-K3, **会给分类学自己已存档为
   「未分开」的那几对开绿灯**。
   ★ **更正**: 我原文写「KNOT_BRIEF **只**注入 signature」—— **那是假的**。它实际注入
     **四个**字段: `key` / `name` / `signature` / `behavior[:70]`。原句虽假但能推出结论;
     改成否定式后既真、又与既有断言逐字同构。
   ★ 原文还写死了行号 :558, 实测是 :598 —— **写死行号本身就是缺陷**, 每次编辑都漂。已去掉。

## ★★ 而那个 ✅ 曾经是绿的, 恰好证明它零灵敏度
库内验收史(memory 45472f0d · 04ca14da · d98d29db · e41cc3ba · 12cee2aa · 82667884):
  2026-08-07 首跑 v1.0.0: G-K1 **❌ κ=0.511/JS=0.259**, G-K2 **❌ 已判死**, **G-K3 ✅**
一个对「同一台仪器在同一份分类学上双闸崩溃」完全无反应的闸, 就是零灵敏度的定义。
★ 库内同时还存着 **「G-K3 签名两两可分**无从检验**」**(c068e2d1 · 78ba23eb)与
  「薄类上仍不可判」(f12aa71f) —— **「已过」与「无从检验」并存至今。**

## ★ 所以本台账问一个能答错的问题
不问「我写的九个签名一不一样」, 问「**这九个格子有没有被仪器实现**」。
一个从没被吐出来的类不叫「可分」, 叫**死类**。

## ★★★ PASS 分支结构上不可达 —— 这是有意的
本台账用的是 G-K1 的标注产物: **同一批标注者、同一份语料、同一个 prompt**,
且这批读数是**被分类学引导过的**(标注 prompt 里就注入了 signature)。
⇒ 它能证明「某个类没被实现」, **但永远不能证明「九个类都分得开」** ——
   后者需要一台不看 taxonomy 的盲观测仪器, 本仓没有。
   照 cce_ksep 的既有纪律(min_effect=None ⇒ 只能报 UNCALIBRATED), 本闸最高只报
   **WITHHELD + 剖面**。`_verdict()` 里没有任何一条路径返回 "PASS"; 这由测试钉死。
"""
import itertools
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from cce_knot_classify import _wilson  # noqa: E402  ★ 复用, 不新写区间

RES = ROOT / "accuracy" / "out" / "gates_result.json"
OUT = ROOT / "tests" / "data" / "gk3_class_realization_ledger.json"
ACTIVE = 0.1  # 「激活」阈, 与 run_gates 的口径一致


def _verdict(dead, judgeable):
    """★ 只有三个出口, **没有 PASS**。见模块 docstring 最后一段。"""
    if dead:
        # ★★ 2026-09-07 改名: 原为 WITHHELD_DEAD_CLASSES。「死类」这个词**用错了**, 两处错:
        #   ① belong 进过 **4/78** 条的 top2, 在 **10/78** 上有非零权重 —— 它是**从不夺魁**,
        #      不是**从不出现**。(GPT 调研点名要我报 N_top2, 而我此前没算。)
        #   ② 更根本: **belong 是九个结里唯一一个行为定义写「自我暴露式**发帖**」的**
        #      (behavior: 「确认通道·中成本:自我暴露式发帖+『only me?』」), 而语料是 **81 条评论**;
        #      而排第一的 display(共识 25/78) 定义明写「**评论区最高质量UGC主力**」。
        #      ⇒ 0 更可能是**单元错配**, 不是「这个类不存在」。
        return "WITHHELD_CLASS_NEVER_WINS_HERE"
    if not judgeable:
        return "WITHHELD_NO_EVIDENCE"
    return "WITHHELD_INSTRUMENT_NOT_BLIND"  # ★ 即使全部有支撑, 仍不发 PASS


def build(res=None):
    g = res or json.loads(RES.read_text(encoding="utf-8"))
    rows = g["G_K2v2_成本档预测"]["rows"]
    prev = g["G_K1v2_分布一致性"]["top1_prevalence"]
    n_ann_top1 = sum(prev.values())
    knots = sorted({k for r in rows for k in r["dist"]} | set(prev))
    cons = [max(r["dist"], key=lambda k: r["dist"][k]) for r in rows]

    per_knot = {}
    for k in knots:
        c = cons.count(k)
        per_knot[k] = {
            "consensus_argmax": c, "n_items": len(rows),
            "consensus_ci95": _wilson(c, len(rows)),
            "annotator_top1": prev.get(k, 0), "n_annotator_top1": n_ann_top1,
            "activated_ge_0.1": sum(1 for r in rows if r["dist"].get(k, 0) >= ACTIVE),
            # ★ GPT 调研点名要的诊断量 —— 只报 top1 与 >=0.1 **推不出** top2=0,
            #   而 top2 才决定该类对 G-K1 的 top2 命中率指标是不是代数惰性。
            "top2": sum(1 for r in rows
                        if k in sorted(r["dist"], key=r["dist"].get, reverse=True)[:2]),
            "nonzero": sum(1 for r in rows if r["dist"].get(k, 0) > 0),
            "★never_wins": c == 0 and prev.get(k, 0) == 0,
        }
    dead = sorted(k for k, v in per_knot.items() if v["★never_wins"])

    pairs = {}
    for a, b in itertools.combinations(knots, 2):
        co = sum(1 for r in rows
                 if r["dist"].get(a, 0) >= ACTIVE and r["dist"].get(b, 0) >= ACTIVE)
        pairs[f"{a}|{b}"] = {
            "co_activated": co,
            "status": ("NO_EVIDENCE_DEAD_CLASS" if a in dead or b in dead
                       else "NO_EVIDENCE_NEVER_CO_ACTIVATED" if co == 0
                       else "PROFILE_ONLY"),
        }
    judgeable = [p for p, v in pairs.items() if v["status"] == "PROFILE_ONLY"]

    return {
        "block": "GK3_CLASS_REALIZATION_LEDGER",
        "★renamed_from": "G-K3「签名两两可分」—— 那个名字把判据指向文档, 是它退化成 lint 的根因",
        "★the_old_gate_was_a_tautology": (
            "详见本文件 docstring。判红条件在作者意图上不可达; codomain 不受控(加个括号后缀距离就变大); "
            "且有直接反例 belong(纸面靠上, 仪器 0/308)。**原 ✅ 撤销, 不是补跑。**"),
        "★why_PASS_is_structurally_unreachable": (
            "本台账吃的是 G-K1 的标注产物 —— 同一批标注者/语料/prompt, 且**读数被分类学引导过**"
            "(标注 prompt 注入 signature)。能证伪「某类没被实现」, 永远不能证成「九类分得开」。"
            "⇒ _verdict() 没有任何一条路径返回 PASS, 由 tests/ 钉死。"),
        "verdict": _verdict(dead, judgeable),
        "★classes_that_never_win": dead,
        "per_knot": per_knot,
        "pairs": pairs,
        "summary": {
            "n_knots": len(knots), "n_pairs": len(pairs),
            "n_dead": len(dead),
            "n_pairs_no_evidence": sum(1 for v in pairs.values() if v["status"].startswith("NO_EVIDENCE")),
            "n_pairs_profile_only": len(judgeable),
        },
        "★not_independent_of_GK1": (
            "★ G-K3 通过**不能**当 G-K1 的独立佐证; G-K1 资格考若扣发(admit=None), 本台账一并作废。"
            "★★ 但它**不冗余**: 实测退化面板(两结永远 50/50 完全不可分)在 G-K1 判据下拿 "
            "top2=1.0 / JS=0.0 ⇒ **满分通过**。机制在 run_gates.py:397 —— 判据问「A 的 top1 在不在 "
            "B 的 top2 里」, 被系统性混淆的两结**永远并列进同一个 top2** ⇒ **混淆是 top2 的加分项**。"
            "κ 在该点掉到 0, 但 criteria 明写它是**参考项**, 进不了 pass。"
            "⇒ G-K1 在 G-K3 要看的方向上是**结构性盲**的。"),
    }


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = d["summary"]
    print(f"✏️ {OUT.relative_to(ROOT)}")
    print(f"G-K3-min: **{d['verdict']}**  (PASS 分支不存在)")
    print(f"  从不夺魁 {s['n_dead']}: {d['★classes_that_never_win']}  ⇒ 它们参与的对全部 NO_EVIDENCE")
    print(f"  {s['n_pairs']} 对: {s['n_pairs_no_evidence']} 无证据 / {s['n_pairs_profile_only']} 仅出剖面 / **0 判通过**")
    for k, v in sorted(d["per_knot"].items(), key=lambda kv: kv[1]["consensus_argmax"]):
        m = " ← 从不夺魁" if v["★never_wins"] else ""
        print(f"    {k:10s} 共识 {v['consensus_argmax']:2d}/{v['n_items']} "
              f"CI{v['consensus_ci95']} · top1 {v['annotator_top1']:3d}/{v['n_annotator_top1']} "
              f"· top2 {v['top2']:2d} · 非零 {v['nonzero']:2d}{m}")
