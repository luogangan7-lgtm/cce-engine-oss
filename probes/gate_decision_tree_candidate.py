#!/usr/bin/env python3
"""闸材料候选 v3c —— **只改决策树第 4 条**, 把既有必要条件显式化。旁路, 现网不动。

预注册: tests/data/gate_decision_tree_candidate_prereg.json (题目校验和 6627d70e135d0113)

## ★★ 不做的三件事(GPT 明令)
不补 typical_codes · 不规定 itch 优先 · 不再堆负例。**单一改动, 不打包。**

## 上限
220 基础 + 最多 22 次仅用于预定义无效响应的重试 = **总尝试 242**, 撞上限即停。
"""
import json
import os
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAULT = pathlib.Path("/Volumes/data/cce-identified-vault")
os.environ.setdefault("CCE_BODY_CHARS", "2000")   # ★ 与 V0/V1 那轮逐字相同
sys.path.insert(0, str(ROOT / "accuracy"))
import run_gates as RG  # noqa: E402

PRE = json.loads((ROOT / "tests/data/gate_decision_tree_candidate_prereg.json").read_text(encoding="utf-8"))
FIX = PRE["★★★the_single_change_verbatim"]
OUT = VAULT / "cce_runs" / "gate_dt_candidate"
CAP_ATTEMPTS = 242
_lock = threading.Lock()
_att = {"n": 0}

# ★ v3c = 只把决策树第 4 条换掉, 其余逐字不动
DT_V2 = RG.DECISION_TREE
assert FIX["old"] in DT_V2, "★ 候选的 old 文本与现网决策树不符 —— 停"
assert DT_V2.count(FIX["old"]) == 1, "★ 命中多处 —— 停"
DT_V3C = DT_V2.replace(FIX["old"], FIX["new"], 1)
assert DT_V3C != DT_V2
# ★ 除第 4 条外逐字相同
_a = [l for l in DT_V2.splitlines() if not l.startswith("4.")]
_b = [l for l in DT_V3C.splitlines() if not l.startswith("4.")]
assert _a == _b, "★★ 除第 4 条外还有别的行变了 —— **打包了**, 停"


def parse(txt):
    try:
        d = RG.extract_json_robust(txt, log_note="dtcand")
        if isinstance(d, dict) and isinstance(d.get("knots"), list) and d["knots"]:
            v = {}
            for k in d["knots"]:
                if isinstance(k, dict) and k.get("key") in RG.KNOTS:
                    try:
                        v[k["key"]] = float(k.get("weight", 0))
                    except (TypeError, ValueError):
                        continue
            t = sum(v.values())
            if t > 0:
                return {k: w / t for k, w in v.items()}
    except Exception:
        pass
    return None


def main():
    import hashlib
    items = json.loads((VAULT / "cce_runs/suspend_confirm_items.json").read_text(encoding="utf-8"))
    chk = hashlib.sha256("".join(sorted(x["id"] for x in items)).encode()).hexdigest()[:16]
    assert chk == PRE["design"]["items"]["checksum"], f"★ 题目校验和不符: {chk}"

    OUT.mkdir(parents=True, exist_ok=True)
    RG.stamp_params(OUT, extra={"annotators_actually_used": list(RG.MODELS),
                                "★arms": "v2(现网决策树) vs v3c(仅改第4条)",
                                "★现网未动": True})
    ck = OUT / "raw.json"
    rows = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else []
    have = {(r["id"], r["model"], r["arm"]) for r in rows if r.get("top1")}
    jobs = [(it, m, a) for it in items for m in RG.MODELS for a in ("v2", "v3c")
            if (it["id"], m, a) not in have]
    print(f"{len(items)} 题 × {len(RG.MODELS)} 标注者 × 2 臂 · 待跑 {len(jobs)} · 尝试上限 {CAP_ATTEMPTS}", flush=True)
    print("★ **只改决策树第 4 条**; 其余逐字相同(已断言) · 现网不动", flush=True)

    def one(job):
        it, m, arm = job
        for attempt in range(2):
            with _lock:
                if _att["n"] + 1 > CAP_ATTEMPTS:
                    print(f"★★ 撞尝试上限 {CAP_ATTEMPTS}, 停。", flush=True)
                    return None
                _att["n"] += 1
            txt = ""
            try:
                p = RG.DIST_TMPL.format(unit=RG.UNIT_LABEL, brief=RG.KNOT_BRIEF,
                                        decision_tree=(DT_V2 if arm == "v2" else DT_V3C),
                                        negative_examples=RG.NEGATIVE_EXAMPLES,
                                        body=it["b"][:RG.BODY_CHARS])
                txt = RG.call(m, p) or ""
                dist = parse(txt)
            except Exception:
                dist = None
            if dist:
                r = {"id": it["id"], "model": m, "arm": arm, "cell": it["cell"],
                     "should_be_suspend": it["★should_be_suspend"],
                     "dist": dist, "top1": max(dist, key=dist.get),
                     "attempt": attempt + 1, "raw": txt[:4000]}
                with _lock:
                    rows.append(r)
                    ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                    if len(rows) % 20 == 0:
                        print(f"  {len(rows)}/{len(items)*len(RG.MODELS)*2}", flush=True)
                return r
        with _lock:
            rows.append({"id": it["id"], "model": m, "arm": arm, "cell": it["cell"],
                         "should_be_suspend": it["★should_be_suspend"],
                         "dist": None, "top1": None, "raw": txt[:4000]})
            ck.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, jobs))
    ok = sum(1 for r in rows if r.get("top1"))
    print(f"\n★ 完成 {len(rows)} 行 · 解析成功 {ok} · 总尝试 {_att['n']} / 上限 {CAP_ATTEMPTS}")


if __name__ == "__main__":
    main()
