# -*- coding: utf-8 -*-
"""contract_pairs v4 的体检: 表层像不像真人 · 有没有泄漏浅层线索 · 判据层读数是否与 v3 逐对相同。零调用。

★ 只**复用**三份已有探针的函数(cb.axes/_corpus_sents · bs.search_family · ax.run), 不改它们 —— 它们的产物被 sha 钉着。
★ v4 只重写 A 支; 第一句/B 支/frames/对象/kind 与 v3 逐字相同, 这里逐对断言。
★ 隐私: 语料是去标识真人内容, v4 句子是我写的, 这里扫 25 字符片段确认**没有抄**。
"""
import hashlib, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAIRS = ROOT / "tests/data/semantic_minimal_pairs.json"
ANN = ROOT / "tests/data/claim_frame_annotations.json"
OUT = ROOT / "results/contract_pairs_v4_check.json"
CORPUS = ["corpus/reddit_hearingaids_audience_v2.txt", "corpus/reddit_hearingaids_utterances.txt"]


def _load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def _sha(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def axis_table(cp, cb, brand_sents):
    pos = [p["pos"]["A"][0] for p in cp]; neg = [p["neg"]["A"][0] for p in cp]
    out = {}
    for name, fn in cb.axes().items():
        mp = sum(map(fn, pos)) / len(pos); mn = sum(map(fn, neg)) / len(neg)
        c = sum(map(fn, brand_sents)) / len(brand_sents)
        out[name] = {"pos%": round(100 * mp), "neg%": round(100 * mn), "真实%": round(100 * c),
                     "平均偏离": round(100 * (abs(mp - c) + abs(mn - c)) / 2), "类差": round(100 * abs(mp - mn))}
    return out


def cells(cp, d, ann, D):
    pr = {p["id"]: p for p in d["pairs"]}; out = []
    for pid, e in ann["annotations"].items():
        for side in ("pos", "neg"):
            out.append((f"{pid}/{side}", pr[pid][side]["A"][0], dict(D, **e["frames"][side]["A"])["predicate"]))
    for p in cp:
        for side in ("pos", "neg"):
            out.append((f"{p['id']}/{side}", p[side]["A"][0], dict(D, **p["frames"][side]["A"])["predicate"]))
    return out


def structure_diff(v3, v4):
    """v4 相对 v3 只许动 pos/neg 的 text 与 A[0]。其余逐字相同。"""
    bad = []
    for a, b in zip(v3, v4):
        if a["id"] != b["id"]:
            bad.append("%s/%s id 错位" % (a["id"], b["id"])); continue
        for k in ("cls", "攻", "★复述形态", "★分组", "依据", "推导", "frames", "★标注理由", "★验证器为什么看不见"):
            if a.get(k) != b.get(k):
                bad.append("%s.%s 变了" % (a["id"], k))
        for side in ("pos", "neg"):
            s1 = a[side]["B"][0]
            if b[side]["B"] != a[side]["B"] or b[side]["A"][1:] != a[side]["A"][1:]:
                bad.append("%s.%s B/对象/kind 变了" % (a["id"], side))
            if b[side]["text"] != s1 + " " + b[side]["A"][0]:
                bad.append("%s.%s text ≠ 第一句 + A 支" % (a["id"], side))
            if not b[side]["text"].startswith(s1):
                bad.append("%s.%s 第一句变了" % (a["id"], side))
        if v4_pos_neg_share(b) is False:
            bad.append("%s pos/neg 第一句不同" % a["id"])
    return bad


def v4_pos_neg_share(p):
    return p["pos"]["B"][0] == p["neg"]["B"][0]


def build():
    cb = _load("probes/corpus_balance_audit.py", "cb"); bs = _load("probes/best_shallow_rule_search.py", "bs")
    ax = _load("probes/annex_a_coverage.py", "ax")
    sys.path.insert(0, str(ROOT / "scripts")); import cce_claim_frame as CF
    d = json.loads(PAIRS.read_text(encoding="utf-8")); ann = json.loads(ANN.read_text(encoding="utf-8"))
    v3, v4 = d["contract_pairs"], d["contract_pairs_v4"]
    cs = cb._corpus_sents(); br = [x for x in cs if cb.BRANDS.search(x)]
    t3, t4 = axis_table(v3, cb, br), axis_table(v4, cb, br)
    mean3 = sum(v["平均偏离"] for v in t3.values()) / len(t3); mean4 = sum(v["平均偏离"] for v in t4.values()) / len(t4)
    fam = {}
    for nm, cp in (("v3", v3), ("v4", v4)):
        c, nd, nb = bs.search_family(cells(cp, d, ann, ann["★默认槽位"]), "RESTATES_IDENTIFIER")
        fam[nm] = {"最佳净增益": c[0]["净增益"] if c else 0, "最佳规则": c[0]["规则"] if c else None,
                   "鉴别格数": nd, "多数类格数": nb}
    # ★★★ v4.1: 冻结族只查闭类词; 单 token **开放**族第一版曾冒出 like/any/model/unit(净 +6, 全在 neg 侧)。
    tok = {}
    for nm, cp in (("v3", v3), ("v4", v4)):
        c, _, _ = bs.search(cells(cp, d, ann, ann["★默认槽位"]), "RESTATES_IDENTIFIER")
        tok[nm] = {"最佳净增益": c[0]["净增益"] if c else 0, "最佳 token": c[0]["token"] if c else None,
                   "前 3": [[x["token"], x["净增益"]] for x in c[:3]]}  # list 不是 tuple: JSON 读回逐键比对要相等
    r3, tot3 = ax.run(v3, CF); r4, tot4 = ax.run(v4, CF)
    jud_diff = [a["id"] for a, b in zip(r3, r4) if {k: v for k, v in a.items()} != {k: v for k, v in b.items()}]
    # 隐私: v4 句子不得抄语料
    lines = []
    for rel in CORPUS:
        lines += [l for l in (ROOT / rel).read_text(encoding="utf-8").split("\n") if len(l.strip()) >= 25]
    v4txt = " ".join(p[s]["text"] for p in v4 for s in ("pos", "neg"))
    copied = sum(1 for l in lines for i in range(0, max(1, len(l) - 25), 10) if l[i:i + 25] in v4txt)
    return {
        "block": "CONTRACT_PAIRS_V4_CHECK", "date": "2026-09-23",
        "★零调用": "只读仓内文件, 复用三份已有探针的函数, 不改它们、不发调用。",
        "v3 sha16": _sha(v3), "v4 sha16": _sha(v4), "pairs10 sha16": _sha(d["pairs"]),
        "★★★ 一、表层像不像真人(A 支 vs 真实含品牌 %d 句)" % len(br): {
            "v3 平均偏离(点)": round(mean3, 1), "v4 平均偏离(点)": round(mean4, 1),
            "v4 最大单轴偏离": max(v["平均偏离"] for v in t4.values()),
            "v4 最大 pos/neg 类差": max(v["类差"] for v in t4.values()),
            "逐轴 v3": t3, "逐轴 v4": t4,
            "★阈值没动": "FAR_THRESHOLD 仍 %s —— 这里不判「合格」, 只报偏离量。" % cb.FAR_THRESHOLD},
        "★★★ 二、有没有泄漏浅层线索(冻结族 %d 条)" % len(bs._rules()): {
            **fam,
            "★读法": "v4 的最佳净增益必须 ≤ v3 —— 重写表层时若把系动词/大写末词只加在 neg 上, 族里就会冒出一条规则。"
                     " 这里 pos/neg 逐特征对称写, 所以没冒。"},
        "★★★ 二b、单 token 开放族(v4.1 加)": {**tok,
            "★读法": "v4 的最佳净增益必须 ≤ v3。第一版 v4 这里是 6(like/any 集中在 neg), 配平后 3。"
                     "★ 这才是 r5 取 p0 的口径之一(「冻结族与单 token 里取更高」), 只查冻结族会漏。"},
        "★★★ 三、判据层读数是否逐对相同": {
            "v3 合计": tot3, "v4 合计": tot4, "逐对有差异的": jud_diff or "无",
            "★为什么必须相同": "判据层只读 frames 槽位, 不读句子文本; frames 一格未动 ⇒ 读数必须逐字相同。有差就是我动了不该动的。"},
        "★★★ 四、结构: v4 相对 v3 只动了 A 支": {"违规": structure_diff(v3, v4) or "无"},
        "★隐私: v4 句子抄语料的 25 字符片段数": copied,
        "★★★ 用法": "已付费轮次(r4/r5/annex_a_coverage/shallow_cue_arm)继续引用 v3; **新一轮起用 v4**。两者并列, 不覆盖。",
        "★不得做": ["不得据 v4 重跑已付费轮次的读数再改结论。", "不得再调 FAR_THRESHOLD。", "不得把 v3 的 sha 换成 v4 的。"],
    }


def main():
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    one = [out[k] for k in out if "表层像不像真人" in k][0]; two = [out[k] for k in out if "泄漏浅层线索" in k][0]
    print("偏离 v3 %s → v4 %s(最大单轴 %s, 类差 %s) · 冻结族净增益 v3 %s → v4 %s · 判据层差异 %s · 结构违规 %s · 抄语料 %s"
          % (one["v3 平均偏离(点)"], one["v4 平均偏离(点)"], one["v4 最大单轴偏离"], one["v4 最大 pos/neg 类差"],
             two["v3"]["最佳净增益"], two["v4"]["最佳净增益"], out["★★★ 三、判据层读数是否逐对相同"]["逐对有差异的"],
             out["★★★ 四、结构: v4 相对 v3 只动了 A 支"]["违规"], out["★隐私: v4 句子抄语料的 25 字符片段数"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
