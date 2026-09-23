# -*- coding: utf-8 -*-
"""小批试的**形式质量**读数。零调用, 只从已冻结的产物里现算。

★★★ 为什么要单独算: 主读数是**交卷率** 34/41, 但「交卷」只是 `supported == true`,
    **不等于那张证书合格**。手构那边 10 张交卷证书里 6 张是 UPGRADED
    (在阴性上错误升格) —— 交卷是个**比「产出鉴别格」松得多的门槛**,
    而这两者之间的距离正是本轮测不了的那一段。

★ 不改冻结产物: results/real_corpus_pilot.json 已由结果闸逐键核过并做过 13 项变异,
  投料后往里加字段 = 事后改产物。这里另立一份, 只读不写它。
"""
import importlib.util, json, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "results/real_corpus_pilot.json"
HAND = ["results/extractor_counterexample_r2.json", "results/repeat_measure_r3.json"]
OUT = ROOT / "results/real_corpus_pilot_formal_quality.json"


def build(res, hand_rows):
    ok = [r for r in res["rows"] if r["调用成功"]]
    sub = [r for r in ok if r["交卷"] is True]
    spans = [x for r in sub for x in r["span_逐字"]]
    all_verbatim = sum(1 for r in sub if r["span_逐字"] and all(r["span_逐字"]))
    return {
        "block": "REAL_CORPUS_PILOT_FORMAL_QUALITY",
        "date": "2026-09-17",
        "★零调用": "只读 results/real_corpus_pilot.json 与两份已付费产物, **不发起任何调用**。",
        "★源": {"产物": str(SRC.relative_to(ROOT)), "行数": len(res["rows"])},

        "★★★ 交卷 ≠ 合格": {
            "本轮交卷": "%d/%d" % (len(sub), len(ok)),
            "★但「交卷」只是 supported==true": "它**不代表**那张证书能过资格层。",
            "★手构那边的交卷证书是什么下场": hand_rows,
            "★★★所以 83% 不能读成「83% 的段落真的满足判别式」":
                "手构那边 %d 张交卷证书里 **%d 张是 UPGRADED** —— 那是**在阴性上错误升格**, "
                "即形式合规、语义错误。⇒ 交卷率高**既可能**是真实语料确实常谈自己的设备, "
                "**也可能**是抽取器在真实文本上更松。**本轮分不开这两种**(没有金标)。"
                % (sum(sum(v.values()) for v in hand_rows.values()),
                   sum(v.get("UPGRADED", 0) for v in hand_rows.values())),
        },

        "★ 形式质量(无金标, 只看结构)": {
            "两支都给了": "%d/%d" % (sum(1 for r in sub if r["A_支"] >= 1 and r["B_支"] >= 1), len(sub)),
            "span 逐字出现在原文": "%d/%d" % (sum(spans), len(spans)),
            "★★★整张证书 span 全逐字": "%d/%d" % (all_verbatim, len(sub)),
            "★那 %d 张的含义" % (len(sub) - all_verbatim):
                "至少有一条 span 不是原文逐字 ⇒ 按 r2 的冻结分类法它们是 **MALFORMED**, "
                "在资格层就会被拦。⇒ **交卷 34 张里有 %d 张连形式都不过**。"
                % (len(sub) - all_verbatim),
            "每张证据条数": {str(k): v for k, v in sorted(Counter(r["n_evidence"] for r in sub).items())},
            "每张 A 支条数": {str(k): v for k, v in sorted(Counter(r["A_支"] for r in sub).items())},
            "★多给证据的风险(r2 实测过)": "r2 发现模型给**多于必要**的证据时, "
                "资格层对**全部**被采用证据求对象集合 ⇒ **多给反而被拦**。"
                "本轮每张中位 %d 条证据, 远多于必要的 2 条。"
                % sorted(r["n_evidence"] for r in sub)[len(sub) // 2],
        },

        "★ 拒答的那 %d 条" % (len(ok) - len(sub)): {
            "why_not 字数": sorted(r["why_not_字数"] for r in ok if r["交卷"] is False),
            "字符长度": sorted(r["n_chars"] for r in ok if r["交卷"] is False),
            "★只看得出它给了理由, 看不出理由对不对": "判理由对不对需要金标。",
        },

        "★★★ 本文件不回答": [
            "**不回答**这 34 张证书里有几张能过资格层 —— 那需要对象名, "
            "而对象名是**语料原文片段**, 按隐私约定不进产物 ⇒ 这一项被我自己的隐私选择挡住了。",
            "**不回答**它们语义上对不对 —— 没有金标。",
            "**不回答**鉴别格有几个 —— 预注册事前声明测不了。",
        ],
        "★这条限制是我自己的设计造成的": "为守「产物里不写一个字语料原文」, 我没存 object 字段, "
            "于是**事后无法重算资格层**。下一轮若要测资格层, 得先定一个既能核对象又不落原文的办法"
            "(例如只存对象名的 sha 与它在两支之间是否相等)。",
    }


def main():
    if not SRC.exists():
        print("★ 缺产物", file=sys.stderr)
        return 1
    res = json.loads(SRC.read_text(encoding="utf-8"))
    s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    hand = {}
    for rel in HAND:
        rows = json.loads((ROOT / rel).read_text(encoding="utf-8"))["rows"]
        iss = [r for r in rows if r.get("调用成功") and r.get("outcome") in m.ISSUED]
        hand[rel.split("/")[-1]] = dict(sorted(Counter(r["outcome"] for r in iss).items()))
    out = build(res, hand)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    k = out["★★★ 交卷 ≠ 合格"]
    print("交卷", k["本轮交卷"], "· 整张全逐字", out["★ 形式质量(无金标, 只看结构)"]["★★★整张证书 span 全逐字"])
    print("手构交卷证书的下场:", json.dumps(hand, ensure_ascii=False))
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
