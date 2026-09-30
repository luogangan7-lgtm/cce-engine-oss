# -*- coding: utf-8 -*-
"""对齐出口 · 前瞻闭环记分(预注册 tests/data/align_followup_prospective_prereg.json)。零调用, 只读归档。

校对只证明判官在构造样例上不判错; 「按清单回的稿是不是真的更好」没有个体金标, 只能看之后的真实行为(用户背书)。
每次带对齐的出站回复运行在归档里留下逐原子判定(reply_alignment.json 的 verdict.top1逐原子对齐); 结局 = 该读者(化名 reader_actor_ref)
之后是否又回应了我方(归档里出现同化名、observed_at 晚于该次运行的 response)。
预测分 = (satisfied − unsatisfied) / 已校对条目数。n 不到门槛只报 INSUFFICIENT。
"""
import glob, json, pathlib, random, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_N, MIN_EACH = 40, 10


def rows():
    later = {}
    for f in glob.glob(str(ROOT / "archive/*/*manifest.json")):
        m = json.loads(pathlib.Path(f).read_text(encoding="utf-8")); sub = m.get("submission") or {}
        if m.get("mode") == "response" and sub.get("actor_ref") and sub.get("observed_at"):
            later.setdefault(sub["actor_ref"], []).append(sub["observed_at"])
    out = []
    for f in glob.glob(str(ROOT / "archive/*/*reply_alignment.json")):
        v = (json.loads(pathlib.Path(f).read_text(encoding="utf-8")).get("verdict") or {}).get("top1逐原子对齐") or {}
        s = v.get("summary") or {}
        mf = pathlib.Path(f.replace("reply_alignment.json", "manifest.json"))
        if v.get("status") != "ok" or not s.get("calibrated") or not mf.exists():
            continue
        m = json.loads(mf.read_text(encoding="utf-8")); sub = m.get("submission") or {}
        actor, t = sub.get("reader_actor_ref"), (m.get("finished") or m.get("started") or "").replace(" ", "T")
        if not actor or not t:
            continue
        out.append({"src": str(pathlib.Path(f).relative_to(ROOT)), "knot": v.get("knot"), "judge": v.get("judge"),
                    "score": (s["satisfied"] - s["unsatisfied"]) / s["calibrated"],
                    "followed_up": any(x > t for x in later.get(actor, []))})
    return out


def auc(pos, neg):
    return statistics.fmean(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)


def score(rs, seed=20260930):
    pos = [r["score"] for r in rs if r["followed_up"]]; neg = [r["score"] for r in rs if not r["followed_up"]]
    if len(rs) < MIN_N or len(pos) < MIN_EACH or len(neg) < MIN_EACH:
        return {"n": len(rs), "n_followed": len(pos), "verdict": "INSUFFICIENT"}
    a = auc(pos, neg); rng = random.Random(seed)
    bs = sorted(auc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(2000))
    return {"n": len(rs), "n_followed": len(pos), "auc": round(a, 4), "auc_ci95": [round(bs[49], 4), round(bs[1949], 4)],
            "verdict": "PREDICTIVE" if a >= 0.60 and bs[49] > 0.5 else "NOT_PREDICTIVE"}


if __name__ == "__main__":
    print(json.dumps(score(rows()), ensure_ascii=False))
