# -*- coding: utf-8 -*-
"""前瞻闭环记分(用户背书口径) —— 预注册 tests/data/residue_followup_prospective_prereg.json。零调用。

冷读的科学版: 先冻结预测, 再看对方的真实行为。每条带 prior_turn 的 response 测量在归档 manifest 里留下 情绪余温 成对分布
(stages.s0_context.成对读出分布); 结局 = 同一化名 actor 之后是否再次回应我方(归档里出现同 actor、更晚 observed_at 的 response)。
预测分 = P(正向余温) − P(负向余温)。n 未到门槛只报 INSUFFICIENT, 不出判决。只读归档, 不落原文。
"""
import glob, json, pathlib, random, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_N, MIN_EACH = 40, 10


def is_test_run(submission_id):
    s = str(submission_id or "")
    return s.startswith("canary") or s.startswith("submit:example")


def rows():
    out = []
    for f in glob.glob(str(ROOT / "archive/*/*manifest.json")):
        m = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        s0 = ((m.get("stages") or {}).get("s0_context") or {})
        dist = (s0.get("成对读出分布") or {}).get("情绪余温")
        sub = m.get("submission") or {}
        if is_test_run(sub.get("submission_id")):     # ★ 2026-09-30: canary / 样例不是生产测量 —— 此前两次 prior_turn canary 的 16 条(其中 8 条还是截断 bug 下的读数)被算了进来
            continue
        if dist and sub.get("actor_ref") and sub.get("observed_at"):
            out.append({"actor": sub["actor_ref"], "t": sub["observed_at"],
                        "score": dist.get("正向余温", 0.0) - dist.get("负向余温", 0.0), "src": str(pathlib.Path(f).relative_to(ROOT))})
    later = {}
    for r in out:
        later.setdefault(r["actor"], []).append(r["t"])
    for r in out:
        r["followed_up"] = any(t > r["t"] for t in later[r["actor"]])
    return out


def auc(pos, neg):
    return statistics.fmean(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)


def score(rs, seed=20260929):
    pos = [r["score"] for r in rs if r["followed_up"]]; neg = [r["score"] for r in rs if not r["followed_up"]]
    if len(rs) < MIN_N or len(pos) < MIN_EACH or len(neg) < MIN_EACH:
        return {"n": len(rs), "n_followed": len(pos), "verdict": "INSUFFICIENT"}
    a = auc(pos, neg); rng = random.Random(seed)
    bs = sorted(auc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(2000))
    lo = bs[49]
    return {"n": len(rs), "n_followed": len(pos), "auc": round(a, 4), "auc_ci95": [round(lo, 4), round(bs[1949], 4)],
            "verdict": "PREDICTIVE" if a >= 0.60 and lo > 0.5 else "NOT_PREDICTIVE"}


if __name__ == "__main__":
    print(json.dumps(score(rows()), ensure_ascii=False))
