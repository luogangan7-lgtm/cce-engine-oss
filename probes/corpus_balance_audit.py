#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**对照集体检器** —— 机械报出 pos/neg 在每条已知特征轴上的分布差。**零模型调用**。

## 为什么要有它
2026-09-15 一天之内, 手构对照集**连续三轮**冒出新的表层共线:
  · v1(6 对): 句法 —— neg 全是「X is Y」定义句 ⇒ 冻结族净 +5 ⇒ 门不可达
  · v2(24 对): 量词/时段 —— pos 75% 带、neg 17% 带 ⇒ 族外规则 19/24 穿过全部前置条件
  · 每次都是**事后搜出来才发现**, 而我在手工凑特征。
⇒ 把「特征对齐」从**事后补救**变成**造对照时的机械约束**。

## ★★★ 判什么算"对齐"
**不是** pos/neg 差为 0 —— 那不可能, 语义差异必然伴随某种表层差异。
**是**: 手构集在某条轴上的 pos/neg 差, 不应**大于真实语料**在同一条轴上的差。
★ 参照来自 r1/r2/r3 已付费的真实证书(results/shallow_rule_on_real_certs.json 同源), 不是我拍的数。
★★ 分母极小(真实 RESTATES 仅 2 条) ⇒ 参照本身很弱, **只用来判方向与量级, 不当阈值**。
"""
import importlib.util, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
OUT = ROOT / "results" / "corpus_balance_audit.json"

QTY = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twice|half|few|about|\d+)\b", re.I)
TIME = re.compile(r"\b(hour|hours|minute|minutes|day|days|week|weeks|month|months|"
                  r"year|years|night|morning|mornings|while|lately|now)\b", re.I)


def _bs():
    s = importlib.util.spec_from_file_location("bs", ROOT / "probes/best_shallow_rule_search.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def axes():
    """已知特征轴。★ 每加一条轴就多一层保护, 但**永远盖不全** —— 留出集与外部锚点管未知的那部分。"""
    B = _bs()
    a = {n: f for n, f in B.ATOMS.items()}
    a["含量词或数字"] = lambda s: bool(QTY.search(s))
    a["含时段单位"] = lambda s: bool(TIME.search(s))
    a["含量词或时段"] = lambda s: bool(QTY.search(s) or TIME.search(s))
    a["首词是限定词"] = lambda s: bool(B._t(s)) and B._t(s)[0] in B.DET
    a["含动词ing"] = lambda s: any(t.endswith("ing") for t in B._t(s))
    return a


BRANDS = re.compile(r"\b(Oticon|Phonak|Signia|ReSound|Widex|Starkey|Jabra|Unitron|Bernafon|"
                    r"Rexton|Beltone|Sonic|Hansaton|Costco|Kirkland)\b", re.I)
CORPUS = ["corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"]
SNAPSHOT = "accuracy/data/reddit_snapshot_20260809.json"
# ★★★ 「两侧都远离真实语料」的阈值。**不许在看过偏离量之后调它** —— 那会变成拟合当前对照集。
#   它只抓**极端**偏离; 真正该看的是 build_result 里现算并报出的**偏离量本身**。
FAR_THRESHOLD = 0.4


def _corpus_sents():
    """从仓内**真实 Reddit 语料**抽句子。

    ★★★ 边界: 这是**外部真人内容**(已去标识, author 字段已移除)。
      ⇒ **产物里只放统计量, 一个字的原文都不写进去。**
    """
    out = []
    for f in CORPUS:
        fp = ROOT / f
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out += [x.strip() for x in re.split(r"(?<=[.!?])\s+", line)
                        if 3 <= len(x.split()) <= 25]
    sp = ROOT / SNAPSHOT
    if sp.exists():
        d = json.loads(sp.read_text(encoding="utf-8")).get("posts") or []
        for post in (d if isinstance(d, list) else list(d.values())):
            if not isinstance(post, dict):
                continue
            for k in ("selftext", "body", "text", "title"):
                v = post.get(k)
                if isinstance(v, str) and v.strip():
                    out += [x.strip() for x in re.split(r"(?<=[.!?])\s+", v)
                            if 3 <= len(x.split()) <= 25]
    return out


def _real():
    """真实证书上同样的轴 —— 参照。"""
    s = importlib.util.spec_from_file_location("rc", ROOT / "probes/shallow_rule_on_real_certs.py")
    RC = importlib.util.module_from_spec(s); s.loader.exec_module(RC)
    rows = RC.cells()
    d = [x for _, x, g in rows if g == "RESTATES_IDENTIFIER"]
    o = [x for _, x, g in rows if g == "OF_DECLARED_KIND"]
    return d, o


def build_result():
    d = json.loads(PAIRS.read_text(encoding="utf-8"))
    cp = d["contract_pairs"]
    pos = [p["pos"]["A"][0] for p in cp]; neg = [p["neg"]["A"][0] for p in cp]
    rd, ro = _real()
    rows = {}
    for name, fn in axes().items():
        mp = sum(1 for s in pos if fn(s)) / len(pos)
        mn = sum(1 for s in neg if fn(s)) / len(neg)
        rp = (sum(1 for s in ro if fn(s)) / len(ro)) if ro else None
        rn = (sum(1 for s in rd if fn(s)) / len(rd)) if rd else None
        rdiff = abs(rp - rn) if (rp is not None and rn is not None) else None
        rows[name] = {
            "手构 pos": "%d/%d" % (sum(1 for s in pos if fn(s)), len(pos)),
            "手构 neg": "%d/%d" % (sum(1 for s in neg if fn(s)), len(neg)),
            "手构差(百分点)": round(abs(mp - mn) * 100),
            "真实差(百分点)": (round(rdiff * 100) if rdiff is not None else "—"),
            "★超出真实语料": (abs(mp - mn) > rdiff + 0.15) if rdiff is not None else None,
        }
    over = [k for k, v in rows.items() if v["★超出真实语料"]]

    # ★★★ 第二个参照: **真实 Reddit 语料**(493 句级, 远大于真实证书的 9 条)。
    #   ★ 它**没有 RESTATES/OF_DECLARED 的标注** ⇒ 只能比**整体分布**, 不能比类别间的差。
    #   ⇒ 两个参照回答**不同的问题**, 互补而不是替代:
    #     · 真实证书(有标注) → 我的**类别间的差**该不该这么大
    #     · 真实语料(无标注) → 我造的**句子本身**像不像真人写的
    cs = _corpus_sents()
    cs_brand = [x for x in cs if BRANDS.search(x)]
    corpus_rows = {}
    for name, fn in axes().items():
        c_all = (sum(1 for x in cs if fn(x)) / len(cs)) if cs else None
        c_br = (sum(1 for x in cs_brand if fn(x)) / len(cs_brand)) if cs_brand else None
        mp = sum(1 for x in pos if fn(x)) / len(pos)
        mn = sum(1 for x in neg if fn(x)) / len(neg)
        # ★ 判准: 手构的 pos 与 neg **两者都**远离真实语料 ⇒ 句子本身不像真人写的
        far = (c_br is not None and min(abs(mp - c_br), abs(mn - c_br)) > FAR_THRESHOLD)
        # ★★★ 布尔阈值只抓**极端**偏离; 真正该报的是**偏离量本身**。
        dev = (round(100 * (abs(mp - c_br) + abs(mn - c_br)) / 2) if c_br is not None else None)
        corpus_rows[name] = {
            "★平均偏离(百分点)": dev,
            "真实语料(全部 %d 句)" % len(cs): ("%.0f%%" % (100 * c_all)) if c_all is not None else "—",
            "真实语料(含品牌 %d 句)" % len(cs_brand): ("%.0f%%" % (100 * c_br)) if c_br is not None else "—",
            "手构 pos": "%.0f%%" % (100 * mp), "手构 neg": "%.0f%%" % (100 * mn),
            "★两侧都远离真实语料": far,
        }
    far_axes = [k for k, v in corpus_rows.items() if v["★两侧都远离真实语料"]]
    devs = {k: v["★平均偏离(百分点)"] for k, v in corpus_rows.items()
            if v["★平均偏离(百分点)"] is not None}
    worst = sorted(devs.items(), key=lambda kv: -kv[1])[:4]
    return {
        "block": "CORPUS_BALANCE_AUDIT",
        "★零调用": "只做正则与计数, **不发起任何模型调用**。",
        "★★★它回答什么": "手构对照集在每条**已知**特征轴上, pos 与 neg 的分布差有多大, "
            "以及**是否大于真实语料在同一条轴上的差**。",
        "★★★判准不是差为 0": "语义差异**必然**伴随某种表层差异。判准是: "
            "手构集的差**不应明显大于真实语料**的差(容许 15 个百分点的余量, 因为真实侧分母极小)。",
        "★★★参照的分母极小": "真实证书里 RESTATES_IDENTIFIER 只有 **%d 条**、OF_DECLARED_KIND **%d 条** "
            "⇒ 参照**很弱**, 只用来判**方向与量级**, **不当阈值**。" % (len(rd), len(ro)),
        "★★★永远盖不全": "每加一条轴多一层保护, 但**未知的轴盖不到** —— "
            "那部分由**留出集**(只搜一次)与**外部锚点**(真实证书上的净增益)管。",
        "★★★超出真实语料的轴": over or "无",
        "逐轴": rows,
        "★★★第二个参照_真实 Reddit 语料": {
            "★它回答的是另一个问题": "真实证书(9 条, **有标注**)比的是**类别间的差**; "
                "真实语料(**无标注**)比的是**我造的句子本身像不像真人写的**。"
                "★ 两者**互补不是替代** —— 类别差合格但句子根本不像真人写的, 仍然是个问题。",
            "★★★边界_这是外部真人内容": "语料已去标识(author 字段已移除)。"
                "**产物里只放统计量, 一个字的原文都不写进去。**",
            "★★★两侧都远离真实语料的轴(阈值 %d 点, 只抓极端)" % round(FAR_THRESHOLD * 100): far_axes or "无",
            "★★★偏离最大的四条轴(百分点)": dict(worst),
            "★★★这几条偏离意味着什么": (
                "**同向偏离**(pos 与 neg 一起偏)**不影响类别区分** ⇒ 本轮的**内部效度不受影响**。"
                "★★ 但它**影响外推**: 我造的句子在这几条轴上与真人写的差 %d–%d 个百分点, "
                "⇒ **本轮读数不得外推到自然语料** —— 这条以前只是口头边界, 现在有数了。"
                "★★★ 最大的一条是「%s」(%d 点)。"
                % (worst[-1][1], worst[0][1], worst[0][0], worst[0][1])
                if worst else "—"),
            "★为什么不把阈值调到 20 点": "那是**看过这批数字之后**拍的 —— 会变成拟合当前对照集。"
                "⇒ 保留 40 点只抓**极端**偏离, 同时**把偏离量本身报出来**让人自己判断。",
            "★怎么读「两侧都远离」": "若手构的 pos **与** neg 在某条轴上**都**与真实语料差 >40 个百分点, "
                "那不是「类别间共线」而是「**我造的句子整体不像真人写的**」—— 更根本的问题。",
            "逐轴": corpus_rows,
        },
    }


def main():
    r = build_result()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("对照集体检(**零调用**)\n")
    print("  %-16s %-9s %-9s %-8s %-8s %s" % ("轴", "手构pos", "手构neg", "手构差", "真实差", ""))
    for k, v in r["逐轴"].items():
        print("  %-16s %-9s %-9s %-8s %-8s %s"
              % (k, v["手构 pos"], v["手构 neg"], v["手构差(百分点)"], v["真实差(百分点)"],
                 "★★★超出" if v["★超出真实语料"] else ""))
    print("\n  超出真实语料(证书)的轴:", r["★★★超出真实语料的轴"])
    c = r["★★★第二个参照_真实 Reddit 语料"]
    print("\n  ── 第二个参照: 真实 Reddit 语料 ──")
    print("  %-16s %-14s %-14s %-9s %s" % ("轴", "语料(全部)", "语料(含品牌)", "手构pos", "手构neg"))
    for k, v in c["逐轴"].items():
        ka = [x for x in v if x.startswith("真实语料(全部")][0]
        kb = [x for x in v if x.startswith("真实语料(含品牌")][0]
        print("  %-16s %-14s %-14s %-9s %-9s %s"
              % (k, v[ka], v[kb], v["手构 pos"], v["手构 neg"],
                 "★★★两侧都远离" if v["★两侧都远离真实语料"] else ""))
    print("\n  两侧都远离(阈值40点):", c["★★★两侧都远离真实语料的轴(阈值 %d 点, 只抓极端)" % round(FAR_THRESHOLD * 100)])
    print("  偏离最大的四条轴:", json.dumps(c["★★★偏离最大的四条轴(百分点)"], ensure_ascii=False))
    print("\n  " + c["★★★这几条偏离意味着什么"])
    print("\n→", OUT)


if __name__ == "__main__":
    main()
