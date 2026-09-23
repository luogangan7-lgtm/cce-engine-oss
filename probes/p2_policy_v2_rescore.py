# -*- coding: utf-8 -*-
"""零调用: 把 r2 的 42 行按 P2 v1(全体对象恰好一个) 与 v2(各支交集非空) 两种口径重算机械资格层, 并按三族拆分。

★ r2 产物一个字节不改(本文件记录其 sha 供闸钉住); 12/42 是 v1 真读数, 20/42 是 v2 读数 —— **可比不可合**。
★ 见证/多余只用 sha16 集合运算, 不反查原文, 一个字都不落盘。
"""
import hashlib, importlib.util, json, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/real_corpus_pilot_r2.json"; ANAT = ROOT / "results/p2_fail_anatomy.json"; OUT = ROOT / "results/p2_policy_v2_rescore.json"
_s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/real_corpus_pilot_r2_run.py"); r2mod = importlib.util.module_from_spec(_s); _s.loader.exec_module(r2mod)


def objsets(row):
    a = {o["sha16"] for o, s in zip(row["objects"], row["supports"]) if s == "A"}
    b = {o["sha16"] for o, s in zip(row["objects"], row["supports"]) if s == "B"}
    return a, b


def qualify_v2(row):
    """与 r2 的 qualify_mechanical **逐字相同**, 只把最后一步 `a != b` 换成 `not (a & b)`。"""
    v1 = r2mod.qualify_mechanical(row)
    if v1 != "P2_FAIL": return v1
    a, b = objsets(row)
    return "PASS_MECHANICAL" if (a & b) else "P2_FAIL"


def build():
    rows = json.loads(R2.read_text(encoding="utf-8"))["rows"]; fam = {x["ptr"]: x["关系"] for x in json.loads(ANAT.read_text(encoding="utf-8"))["per_row"]}
    per = []; c1 = Counter(); c2 = Counter(); moved = Counter()
    for row in rows:
        v1 = r2mod.qualify_mechanical(row); v2 = qualify_v2(row); c1[str(v1)] += 1; c2[str(v2)] += 1
        f = fam.get(row["ptr"]) if v1 == "P2_FAIL" else None
        if v1 == "P2_FAIL": moved[(f, v2)] += 1
        a, b = objsets(row)
        per.append({"ptr": row["ptr"], "v1": v1, "v2": v2, "族(仅 v1=P2_FAIL)": f, "witness_n": len(a & b), "surplus_n": len((a | b) - (a & b))})
    n = len(rows)
    return {"block": "P2_POLICY_V2_RESCORE", "date": "2026-09-23", "★零调用": True, "★裁定文件": "P2_FAIL_FAMILIES_DECIDED_2026-09-23.md",
            "★r2 产物 sha256(未改)": hashlib.sha256(R2.read_bytes()).hexdigest(), "★anatomy sha256(未改)": hashlib.sha256(ANAT.read_bytes()).hexdigest(),
            "★v1 口径(r2 原读数)": dict(c1), "★v2 口径(见证交集)": dict(c2),
            "★★★ 三族去向(v1=P2_FAIL 的 16 张)": {"%s→%s" % k: v for k, v in moved.items()},
            "★过机械资格层": {"v1": "%d/%d" % (c1["PASS_MECHANICAL"], n), "v2": "%d/%d" % (c2["PASS_MECHANICAL"], n), "★可比不可合": "同一批证书、两种口径; 不得合并, 不得说成「提高」"},
            "★仍未回答": "过机械层 ≠ 合格: 语义(否定/归属/时态/引用层级/类型成员)仍未验, is_citable_as_confirmed 仍恒 False。",
            "per_row": per}


def main():
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1), encoding="utf-8"); r = json.loads(OUT.read_text(encoding="utf-8"))
    print(r["★v1 口径(r2 原读数)"], "→", r["★v2 口径(见证交集)"]); print(r["★★★ 三族去向(v1=P2_FAIL 的 16 张)"]); print("→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
