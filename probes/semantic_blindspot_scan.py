#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五类语义关系的**验证器盲区扫描** —— **零模型调用**。

★★★ 来路: 2026-09-14 外部技术评估给的第一优先方向 ——
  「把目标从『为已定标签找支持』改成『先确定文本支持哪些命题, 再决定哪些标签允许输出』,
   检验方式是按语义关系构造**最小对照**, 分别看**五类关系的错误放行**, 而非总正确率。」

★ 本轮只做**度量**, 不改验证器。先量出每一类漏多少、漏在哪, 之后任何改进才有对照。

★★★ 它测的是**验证器的语义盲区**, **不是**模型的错误率 —— 证书是手构探针, 不经模型。
  这与「自检样本必须经由真实采集流程产出」不冲突: 那条约束的是「验证采集协议可不可用」;
  这里验的是**验证器本身**, 手构探针正是合法手段(2026-09-13 零调用反例同一手法)。
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SRC = ROOT / "tests/data/semantic_minimal_pairs.json"
OUT = ROOT / "results" / "semantic_blindspot_scan.json"
CONJ_P = "输出新信息增量"
CONJ_Q = "谈论对象是自己已拥有或已经历的"


def judge(text, a, b):
    """把一张**形式完全合规**的证书送进现有资格层。返回 (state, why)。"""
    import cce_label_qualification as LQ
    try:
        ev = [LQ.EvidenceSpan(a[0], CONJ_P, text, about=a[1], increment_kind=a[2]),
              LQ.EvidenceSpan(b[0], CONJ_Q, text, about=b[1])]
    except Exception as e:
        return "REJECTED_AT_CONSTRUCTION", str(e).split("\n")[0][:120]
    q = LQ.qualify("display", text, evidence=ev,
                   required_conjuncts=[CONJ_P, CONJ_Q])
    return q["state"], q["why"][:150]


def main():
    import cce_label_qualification as LQ
    d = json.loads(SRC.read_text(encoding="utf-8"))
    rows, by_cls = [], {}
    for p in d["pairs"]:
        r = {"id": p["id"], "cls": p["cls"], "攻": p["攻"], "依据": p["依据"]}
        for side in ("pos", "neg"):
            s = p[side]
            st, why = judge(s["text"], s["A"], s["B"])
            passed = (st == LQ.CITED_UNVERIFIED)
            r[side] = {"text": s["text"], "state": st, "通过": passed, "why": why}
        # ★ 错误放行 = neg 版**也**通过了
        r["★错误放行"] = bool(r["neg"]["通过"])
        # ★ 对照有效性 = pos 版确实通过(否则这一对什么都测不出)
        r["★对照有效"] = bool(r["pos"]["通过"])
        rows.append(r)
        c = by_cls.setdefault(p["cls"], {"n": 0, "错误放行": 0, "对照有效": 0, "依据": p["依据"]})
        c["n"] += 1
        c["错误放行"] += r["★错误放行"]
        c["对照有效"] += r["★对照有效"]

    n = len(rows)
    leak = sum(r["★错误放行"] for r in rows)
    ctrl = sum(r["★对照有效"] for r in rows)
    degenerate = [r["id"] for r in rows if not r["★对照有效"]]

    res = {
        "block": "SEMANTIC_BLINDSPOT_SCAN",
        "★零调用": "本扫描**不发起任何模型调用**。证书是手构探针。",
        "source": "tests/data/semantic_minimal_pairs.json",
        "★★★逐类错误放行": {
            k: {"错误放行": "%d/%d" % (v["错误放行"], v["n"]),
                "对照有效": "%d/%d" % (v["对照有效"], v["n"]),
                "依据": v["依据"]}
            for k, v in by_cls.items()},
        "★★★合计": {"错误放行": "%d/%d" % (leak, n), "对照有效": "%d/%d" % (ctrl, n)},
        "★★★退化的对(pos 都没通过, 这一对测不出东西)": degenerate or "无",
        "★★★怎么读": "这是**验证器的语义盲区**, 不是模型的错误率。"
            "「错误放行 k/n」= 在 n 对最小对照里, 有 k 对的**不支持版**也被验证器放行。"
            "★ 分母是我构造的对照, **不是**自然语料 ⇒ 不得当成误报率。",
        "★★★依据分层":
            "否定辖域/归属/时态 = **合同明文**支持; "
            "引用层级/类型成员资格 = **依赖解释**(合同没定义「输出」是否含转述, 也没定义五类各自的成立条件) "
            "⇒ 后两类的 neg 判定若被推翻, 对应的对**自动作废**。",
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("五类语义关系 · 验证器盲区扫描(**零调用**)\n")
    print("  %-14s %-10s %-10s %s" % ("关系类", "错误放行", "对照有效", "依据"))
    for k, v in by_cls.items():
        print("  %-14s %-10s %-10s %s"
              % (k, "%d/%d" % (v["错误放行"], v["n"]),
                 "%d/%d" % (v["对照有效"], v["n"]), v["依据"].strip("*")))
    print("\n  %-14s %-10s %-10s" % ("合计", "%d/%d" % (leak, n), "%d/%d" % (ctrl, n)))
    if degenerate:
        print("  ★ 退化(pos 未通过, 测不出东西): %r" % degenerate)
    print("\n→", OUT)


if __name__ == "__main__":
    main()
