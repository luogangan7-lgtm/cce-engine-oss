# -*- coding: utf-8 -*-
"""P2_FAIL 的解剖: 两支指到的「不同对象」, 是**粒度**(一支是另一支的子串/方面)还是**真·不同对象**?

★ 零调用。第二轮为守隐私只存了 object 的 sha16; 语料在仓内 ⇒ 本地穷举 ≤MAXLEN 字符子串反查,
  **反查出的文本只在内存里用**, 产物只落关系类别与长度统计。
★ r2 当年用「模板档案声明的对象集合」拆 GRANULARITY/DISTINCT, 真实语料没有档案 ⇒ 这里用**文本关系**拆:
    SUBSTRING    一支规范化后是另一支的子串(r1 那种「X」vs「X 的电池续航」)
    SHARED_TOKEN 不互含但共享 ≥1 个 ≥3 字符的词(同品牌不同物 / 同物不同写法)
    DISJOINT     一个词都不共享 ⇒ 真·不同对象
"""
import hashlib, importlib.util, json, pathlib, re, statistics, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/real_corpus_pilot_r2.json"
OUT = ROOT / "results/p2_fail_anatomy.json"
MAXLEN = 80
_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9&+.\-]{2,}")


def _load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def recover(line, sha16, norm):
    hits = set()
    n = len(line)
    for i in range(n):
        for L in range(1, min(MAXLEN, n - i) + 1):
            cand = norm(line[i:i + L])
            if hashlib.sha256(cand.encode()).hexdigest()[:16] == sha16:
                hits.add(cand)
    return hits


def relation(a, b):
    la, lb = a.lower(), b.lower()
    if la == lb:
        return "SAME"
    if la in lb or lb in la:
        return "SUBSTRING"
    ta, tb = set(_TOK.findall(la)), set(_TOK.findall(lb))
    return "SHARED_TOKEN" if ta & tb else "DISJOINT"


def build(res, lines, norm, brands):
    p2 = _load(ROOT / "probes/real_corpus_pilot_r2_run.py", "_p2")
    rows = res["rows"]
    per, ambiguous, unrecovered = [], 0, 0
    for r in rows:
        if p2.qualify_mechanical(r) != "P2_FAIL":
            continue
        ln = lines(r["ptr"])
        A, B = [], []
        for o, sup in zip(r["objects"], r["supports"]):
            if not o.get("sha16"):
                continue
            h = recover(ln, o["sha16"], norm)
            if not h:
                unrecovered += 1; continue
            if len(h) > 1:
                ambiguous += 1
            (A if sup == "A" else B).append(sorted(h)[0])
        if not A or not B:
            continue
        sa, sb = {a.lower() for a in A}, {b.lower() for b in B}
        common = sa & sb
        order = {"SAME": 0, "SUBSTRING": 1, "SHARED_TOKEN": 2, "DISJOINT": 3}
        longer, extras_rel = None, None
        if common:
            # ★★★ 两支**有共同对象**, 卡住是因为某支多给了一条证据指到别的东西
            #     —— r2 记过的通道特性「多给反而被拦」, r3 当时判它是运气。
            best = "SET_MISMATCH"
            c = sorted(common)[0]
            extras = [x for x in (sa | sb) - common]
            extras_rel = dict(Counter(relation(x, c) for x in extras))
        else:
            rels = [relation(a, b) for a in A for b in B]
            best = min(rels, key=order.get)
            if best == "SUBSTRING":
                pa = [(a, b) for a in A for b in B if relation(a, b) == "SUBSTRING"][0]
                longer = "A" if len(pa[0]) > len(pa[1]) else "B"
        per.append({
            "ptr": r["ptr"], "关系": best, "更长的那支(仅 SUBSTRING)": longer,
            "多出来的对象与共同对象的关系(仅 SET_MISMATCH)": extras_rel,
            "A_证据数": len(A), "B_证据数": len(B),
            "A_含品牌": any(bool(brands.search(a)) for a in A),
            "B_含品牌": any(bool(brands.search(b)) for b in B),
            "A_字符": statistics.median(len(a) for a in A),
            "B_字符": statistics.median(len(b) for b in B),
            "A_词数": statistics.median(len(_TOK.findall(a)) for a in A),
            "B_词数": statistics.median(len(_TOK.findall(b)) for b in B),
        })
    n = len(per)
    rel = Counter(p["关系"] for p in per)
    sub = [p for p in per if p["关系"] == "SUBSTRING"]
    return {
        "block": "P2_FAIL_ANATOMY",
        "date": "2026-09-23",
        "★零调用": "只读第二轮产物与仓内语料; 反查出的对象文本**只在内存里用, 一个字都不落盘**。",
        "源": str(R2.relative_to(ROOT)),
        "P2_FAIL 条数": n,
        "反查": {"歧义命中(>1 个子串同 sha)": ambiguous, "反查失败": unrecovered,
                 "★为什么可信": "sha16 = 64 位; 一行 ≤3135 字符 × ≤%d 长度 ≈ 25 万候选, 碰撞概率 ~1e-14。" % MAXLEN},
        "★★★ 关系分布": dict(rel),
        "★★★ 怎么读": {
            "SET_MISMATCH": "两支**有共同对象**, 卡住只因某支多给了一条证据指到别的东西 ⇒ "
                            "r2 记过的通道特性「**多给反而被拦**」(当时 2 例, r3 判为运气) —— 现在真实语料上有了样本量。",
            "SUBSTRING": "一支是另一支的子串 ⇒ **粒度**故障: 同一个物, 一支多指了个方面/部件。这是 r1 记录过的那一族。",
            "SHARED_TOKEN": "不互含但共词 ⇒ 多半是**同品牌的不同型号 / 同物的不同写法**, 需人判。",
            "DISJOINT": "一个词都不共享 ⇒ **真·不同对象**: 模型在两支上说了两件东西。",
        },
        "SUBSTRING 里更长的那支": dict(Counter(p["更长的那支(仅 SUBSTRING)"] for p in sub)),
        "★ SET_MISMATCH 里多出来的对象与共同对象的关系(汇总)": dict(sum(
            (Counter(p["多出来的对象与共同对象的关系(仅 SET_MISMATCH)"] or {}) for p in per), Counter())),
        "★ SET_MISMATCH 里哪一支多给了": dict(Counter(
            ("A 多" if p["A_证据数"] > p["B_证据数"] else "B 多" if p["B_证据数"] > p["A_证据数"] else "一样多")
            for p in per if p["关系"] == "SET_MISMATCH")),
        "★含品牌": {
            "A 支含品牌": sum(p["A_含品牌"] for p in per), "B 支含品牌": sum(p["B_含品牌"] for p in per),
            "只有 B 含": sum(1 for p in per if p["B_含品牌"] and not p["A_含品牌"]),
            "只有 A 含": sum(1 for p in per if p["A_含品牌"] and not p["B_含品牌"]),
            "★读法": "B 支(自己已拥有)天然指整机(品牌型号); A 支(新信息增量)若不含品牌而 B 含 ⇒ A 指的是方面/部件。",
        },
        "长度(中位)": {
            "A_字符": statistics.median(p["A_字符"] for p in per) if per else None,
            "B_字符": statistics.median(p["B_字符"] for p in per) if per else None,
            "A_词数": statistics.median(p["A_词数"] for p in per) if per else None,
            "B_词数": statistics.median(p["B_词数"] for p in per) if per else None,
        },
        "★★★ 对修法的含义": {
            "①逐字约束不解决 P2": "r2 提过「要求 about 也是原文逐字片段」—— 第二轮里它**已经生效**"
                                  "(非逐字的进了 MALFORMED), P2 照样卡 %d 张。" % n,
            "②P2_FAIL 不是一族, 是三族": "SET_MISMATCH(多给证据) / SUBSTRING(粒度) / DISJOINT(真·不同对象) "
                "各自的修法完全不同: 第一族是**采集协议**问题(每支只取一条? 还是取交集?), "
                "第二族是**判据**问题(部件 ⊂ 整机认不认), 第三族是**模型**问题。",
            "★不在这里裁": "三族怎么处理都是 owner 的决定; 本文件只把它们分开数清。"},
        "★不得做的事": [
            "不得把 SUBSTRING 读成「模型错了」—— 它可能是对的(方面确实是对象的一部分), 是**判据**要不要认「部件/方面 ⊂ 整机」的问题, 那是 owner 决定。",
            "不得据此给资格层加别名归并/子串包含 —— 那是 r2 明写的 fail-closed 选择, 放松会把对象错配那一格重新放进来。",
            "不得外推: n=%d, 单一模型, 含品牌子总体。" % n,
        ],
        "per_row": per,
    }


def main():
    m = _load(ROOT / "probes/extractor_counterexample_run_r2.py", "_r2")
    cb = _load(ROOT / "probes/corpus_balance_audit.py", "_cb")
    res = json.loads(R2.read_text(encoding="utf-8"))
    cache = {}
    def lines(ptr):
        f, i = ptr.rsplit(":", 1)
        if f not in cache:
            cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        return cache[f][int(i)]
    out = build(res, lines, m.normalize_about, cb.BRANDS)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("P2_FAIL %d 条 · 关系分布 %s" % (out["P2_FAIL 条数"], json.dumps(out["★★★ 关系分布"], ensure_ascii=False)))
    print("SUBSTRING 更长的那支:", out["SUBSTRING 里更长的那支"])
    print("含品牌:", json.dumps({k: v for k, v in out["★含品牌"].items() if k != "★读法"}, ensure_ascii=False))
    print("长度中位:", json.dumps(out["长度(中位)"], ensure_ascii=False))
    print("反查:", out["反查"]["歧义命中(>1 个子串同 sha)"], "歧义 /", out["反查"]["反查失败"], "失败")
    print("→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
