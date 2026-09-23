#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 r1/r2/r3 **已付费的真实证书**回放到命题框架层 —— **零模型调用**。

★★★ 为什么是这个而不是先花预算: 库内付费测量纪律 ——
  「**冻结环境 + 录制回放的边际成本近零, 却常被误用或闲置**」
  「**定向复验(失败案例类)优先于全量重跑**」。
  靶子现成: **r3 的 MIS-4 是唯一一次真实模型产出、穿过整套验证器的语义错误证书**。

★★★ 这一批同时测两件事:
  ① **拦得住吗** —— 阴性 2 张(r1/NEGP-1 · r3/MIS-4)
  ② **会不会误拦** —— 对照 13 张。**误拦比漏更糟**, 它会让整层不可用。

★★★ 边界: 证书是**真实的**, 但**六槽位标注仍是我做的** ⇒ 仍是「标注正确时的能力上界」,
  **不**回答「模型自己填槽位会填成什么样」。
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
ANN = ROOT / "tests/data/claim_frame_replay_annotations.json"
OUT = ROOT / "results" / "claim_frame_replay.json"
SRC = [("r1", "results/extractor_counterexample.json",
        "tests/data/extractor_counterexample_templates.json"),
       ("r2", "results/extractor_counterexample_r2.json",
        "tests/data/extractor_counterexample_templates_r2.json"),
       ("r3", "results/repeat_measure_r3.json",
        "tests/data/extractor_counterexample_templates_r2.json")]
# ★ 阴性臂(构造规则说**不该** display 的那些)
NEG_ARMS = ("缺P阴性", "否定Q阴性", "对象错配阴性")


def _ev(m):
    """把 r1 的旧格式与 r2/r3 的新格式统一成 [(span, supports, object, kind)]。"""
    if "evidence" in m:
        out = []
        for e in (m.get("evidence") or []):
            out.append((e.get("span"), e.get("supports"), e.get("object"),
                        e.get("increment_kind")))
        return out
    inc, own = m.get("increment") or {}, m.get("owned_or_experienced") or {}
    return [(inc.get("span"), "A", inc.get("about"), inc.get("kind")),
            (own.get("span"), "B", own.get("about"), None)]


def build_rows(drop=()):
    """回放并返回 rows。

    ★★★ 2026-09-15 加 `drop` 参数: 把指定槽位**一律留空**(UNSPECIFIED ⇒ 证据不足)后重放。
      用来算「**填不出的槽位留空**」这条降级方案在**真实证书**上还剩多少拦截力。
    ★ **默认 drop=() ⇒ 现有读数逐字不变**, 由 tests/test_cce_claim_frame_replay.py 把住。
    """
    import cce_claim_frame as CF
    a = json.loads(ANN.read_text(encoding="utf-8"))
    DEF, A = a["★默认槽位"], a["annotations"]
    CONJ = {"A": CF.CONJ_P, "B": CF.CONJ_Q}

    rows, missing = [], []
    for tag, rf, tf in SRC:
        p = ROOT / rf
        if not p.exists():
            continue
        res = json.loads(p.read_text(encoding="utf-8"))
        tpl = {t["id"]: t for t in json.loads((ROOT / tf).read_text(encoding="utf-8"))["templates"]}
        for row in res["rows"]:
            m = row.get("模型原样")
            if not (isinstance(m, dict) and m.get("supported")):
                continue
            frames, ok = [], True
            for i, (span, sup, obj, kind) in enumerate(_ev(m)):
                key = "%s/%s/%d" % (tag, row["id"], i)
                if key not in A:
                    missing.append(key); ok = False; continue
                kw = dict(DEF); kw.update(A[key])
                for _s in drop:
                    kw[_s] = CF.UNSPEC
                c = CONJ.get(str(sup).strip().upper())
                if c is None or not span:
                    ok = False; continue
                frames.append(CF.ClaimFrame(span, c, object=obj, increment_kind=kind, **kw))
            if not ok or not frames:
                continue
            r = {"轮次": tag, "id": row["id"], "arm": row["arm"],
                 "★是阴性吗": row["arm"] in NEG_ARMS,
                 "旧层结局": row.get("outcome") or row.get("资格层"),
                 "证据条数": len(frames)}
            for tier, use_i in (("只用合同明文", False), ("明文+解释", True)):
                v = CF.allow_label(frames, use_interpretation=use_i)
                r[tier] = {"allow": v["allow"],
                           "per": {k: x["state"] for k, x in v["per_conjunct"].items()}}
            rows.append(r)

    return rows, missing


def main():
    rows, missing = build_rows()
    neg = [r for r in rows if r["★是阴性吗"]]
    pos = [r for r in rows if not r["★是阴性吗"]]

    def cnt(sel, tier, want):
        return sum(1 for r in sel if r[tier]["allow"] is want)

    res = {
        "block": "CLAIM_FRAME_REPLAY",
        "★零调用": "回放 r1/r2/r3 **已付费**的真实证书, **不发起任何模型调用**。",
        "★★★边界": "证书是**真实模型产出的**, 但**六槽位标注仍是我做的** ⇒ "
            "仍是「**标注正确时**的能力上界」, **不**回答「模型自己填槽位会填成什么样」。",
        "★回放了多少": {"真实证书": len(rows), "其中阴性": len(neg), "其中对照": len(pos)},
        "★★★阴性_拦得住吗": {
            t: {"被拦住": "%d/%d" % (cnt(neg, t, False), len(neg)),
                "仍放行": "%d/%d" % (cnt(neg, t, True), len(neg)),
                "逐条": {r["id"]: ("拦住" if not r[t]["allow"] else "★仍放行") for r in neg}}
            for t in ("只用合同明文", "明文+解释")},
        "★★★对照_会不会误拦": {
            t: {"正常放行": "%d/%d" % (cnt(pos, t, True), len(pos)),
                "★被误拦": "%d/%d" % (cnt(pos, t, False), len(pos)),
                "误拦的": [r["轮次"] + "/" + r["id"] for r in pos if not r[t]["allow"]]}
            for t in ("只用合同明文", "明文+解释")},
        "★未标注的证据(跳过)": missing or "无",
        "rows": rows,
    }
    # ★★★ 头条结论: 那次真实错误升格, 哪一档能拦?
    m4 = [r for r in rows if r["轮次"] == "r3" and r["id"] == "MIS-4"]
    if m4:
        r = m4[0]
        res["★★★那次真实的错误升格(r3 MIS-4)"] = {
            "旧层给的": r["旧层结局"],
            "只用合同明文": "拦住" if not r["只用合同明文"]["allow"] else "**仍放行**",
            "明文+解释": "拦住" if not r["明文+解释"]["allow"] else "**仍放行**",
            "★这意味着什么": (
                "**合同明文拦不住它, 只有依赖解释的规则才拦得住。**"
                "⇒ 那条解释(附件 A: 增量必须是不能由公开标识本身推出的陈述)出自 "
                "OWNER_DECISION_SHEET.md, 原文明写「**这条是我的提案, 可以被你推翻**」。"
                "⇒ **这给 owner 一个具体问题: 要不要把它升成合同?** 不升, 明文就拦不住"
                "**真实发生过的**那次错误。"
                if r["只用合同明文"]["allow"] and not r["明文+解释"]["allow"]
                else "见逐档结果。")}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("已付费真实证书回放(**零调用**) —— %d 张(阴性 %d · 对照 %d)\n" % (len(rows), len(neg), len(pos)))
    print("  %-14s %-16s %-16s" % ("", "阴性拦住", "对照误拦"))
    for t in ("只用合同明文", "明文+解释"):
        print("  %-14s %-16s %-16s"
              % (t, "%d/%d" % (cnt(neg, t, False), len(neg)),
                 "%d/%d" % (cnt(pos, t, False), len(pos))))
    if m4:
        r = m4[0]
        print("\n  ★★★ r3/MIS-4(唯一一次真实错误升格, 旧层给的是 %s):" % r["旧层结局"])
        print("      只用合同明文 → %s" % ("拦住" if not r["只用合同明文"]["allow"] else "**仍放行**"))
        print("      明文+解释   → %s" % ("拦住" if not r["明文+解释"]["allow"] else "**仍放行**"))
    if missing:
        print("\n  ★ 未标注而跳过: %r" % missing)
    print("\n→", OUT)


if __name__ == "__main__":
    main()
