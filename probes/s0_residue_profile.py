# -*- coding: utf-8 -*-
"""情绪余温 · 分布口径(全占比)重测 —— 预注册 tests/data/s0_residue_profile_prereg.json。

为什么重做(owner 2026-09-29): CCE 的读出是**动态分布**, 不是确定值; 像九型那样, 占比最高的是主判断, 其余类型各占多少一并给出。
上一轮 s0_residue_referent 只取了 Jev 的 top-1(argmax)并按布尔阈值判 —— 违反库里「禁 argmax 退化 / 禁布尔 gate」铁律, Jev 返回的概率被丢掉了。
本探针保存**每次读出的完整分布**, 判据只看分布的位移:
  · 方向性: 指向我方上一条回复的情绪, 把占比推向对的值(Δp 相对同段落 baseline)
  · 指代特异性(泄漏比): 指向别人/无关事件的同号情绪, 推动的占比相对「指向我方」的比例
两臂: v1 = 生产现行题面(只读回应); paired = 把「我方上一条消息」作为显式上下文一起给(冷读法: 我们知道自己下了什么探针, 只看对方对它的反应)。
只调 Jev, 硬上限 400。产物只放指针、类别与概率, 不落原文。
用法: python3 probes/s0_residue_profile.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, pathlib, random, statistics, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
_s = importlib.util.spec_from_file_location("_rr", ROOT / "probes/s0_residue_referent.py"); rr = importlib.util.module_from_spec(_s); _s.loader.exec_module(rr)
S0, shadow, FACETS, pv = rr.S0, rr.shadow, rr.FACETS, rr.pv
PRE = ROOT / "tests/data/s0_residue_profile_prereg.json"
OUT = ROOT / "results/s0_residue_profile.json"
CAP = 400
EMO = next(f for f in FACETS if f["key"] == "情绪余温")
VALUES = list(EMO["values"]) + ["未知"]
# 我方上一条消息(构造, 中性求助式回复; 与段落话题无关也成立 —— 它只是「我们下的探针」)
PREV = "Have you tried asking your audiologist to lower the feedback manager and re-run the fitting? That fixed a similar issue for me."
PAIRED_Q = ("Read only the writer's reaction to OUR PREVIOUS MESSAGE shown above their reply. "
            "Feelings about anything else (other people, other replies, devices, events) do not count. "
            "If the reply does not react to our previous message, choose 未知; never guess.")
SIGN = {"POS": "正向余温", "NEG": "负向余温"}


def state(arm, body):
    return body if arm == "v1" else "[OUR PREVIOUS MESSAGE]\n" + PREV + "\n\n[THEIR REPLY]\n" + body


def boot_ci(xs, n=2000, seed=20260929):
    if not xs: return None
    rng = random.Random(seed); m = len(xs)
    bs = sorted(statistics.fmean(rng.choice(xs) for _ in range(m)) for _ in range(n))
    return [round(bs[int(0.025 * n)], 4), round(bs[int(0.975 * n) - 1], 4)]


def score(rows):
    """rows: 同一臂。每行 probs = {值: 概率}(情绪余温一面)。Δ 按段落配对: 植入行 − 同段落 baseline。"""
    ok = [r for r in rows if r["probs"]]
    base = {r["ptr"]: r["probs"] for r in ok if r["kind"] == "baseline"}
    pl = [r for r in ok if r["kind"] == "plant" and r["ptr"] in base]
    d = lambda r, v: r["probs"].get(v, 0.0) - base[r["ptr"]].get(v, 0.0)
    out = {"profile_mean": {}, "shift": {}}
    for c in rr.PLANTS:
        rs = [r for r in pl if r["cls"] == c]
        out["profile_mean"][c] = {v: round(statistics.fmean(r["probs"].get(v, 0.0) for r in rs), 4) for v in VALUES} if rs else None
    out["profile_mean"]["baseline"] = {v: round(statistics.fmean(p.get(v, 0.0) for p in base.values()), 4) for v in VALUES} if base else None
    for s, v in SIGN.items():
        ours = [d(r, v) for r in pl if r["cls"] == "OURS_" + s]
        leak = [d(r, v) for r in pl if r["cls"] in ("OTHER_" + s, "EVENT_" + s)]
        mo, ml = (statistics.fmean(ours) if ours else 0.0), (statistics.fmean(leak) if leak else 0.0)
        out["shift"][s] = {"target": v, "ours_mean_dp": round(mo, 4), "ours_ci": boot_ci(ours),
                           "leak_mean_dp": round(ml, 4), "leak_ci": boot_ci(leak),
                           "leak_ratio": round(ml / mo, 4) if mo > 0 else None, "n_ours": len(ours), "n_leak": len(leak)}
    sh = out["shift"].values()
    out["verdict"] = ("DISCRIMINATES" if all(x["ours_mean_dp"] >= 0.5 and x["leak_ratio"] is not None and x["leak_ratio"] <= 0.25 for x in sh)
                      else "LEAKS")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    passages = shadow.load_passages()[10:20]
    js = rr.jobs(passages)
    assert 2 * len(js) <= CAP
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        key = "dry"
        def post(body, k):
            p = {v: 0.0 for v in VALUES}; p["正向余温"] = 1.0
            return {"answers": {q: {"choice": "正向余温" if q == "情绪余温" else "未知", "probabilities": p if q == "情绪余温" else {}} for q in body["questions"]}}, None
    else:
        key = shadow._key()
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP:
                    raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=1)
    import os
    os.environ["TYPESAFE_API_KEY"] = key          # 仅本进程内, 不打印不落盘
    orig = S0.jev_questions
    def paired_q(facets):
        q = orig(facets); q["情绪余温"]["instructions"] = PAIRED_Q; return q
    arms, raw = {}, []
    for arm, qf in (("v1", orig), ("paired", paired_q)):
        S0.jev_questions = qf
        def one(j):
            kind, p, c, i, body = j
            read, probs, err = S0.s0_jev_read(state(arm, body)[:2400], FACETS, post=lambda b, k=key: post(b, key))
            return {"arm": arm, "kind": kind, "ptr": p, "cls": c, "phrasing": i,
                    "top": (read or {}).get("情绪余温"), "probs": (probs or {}).get("情绪余温"), "err": err}
        with ThreadPoolExecutor(max_workers=4) as ex:
            rows = list(ex.map(one, js))
        arms[arm] = score(rows); raw += rows
    S0.jev_questions = orig
    res = {"block": "S0_RESIDUE_PROFILE", "run_at": "2026-09-29", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "passages": [p for p, _ in passages], "requests": ledger["req"],
           "errors": dict(collections.Counter(r["err"] for r in raw if r["err"])), "arms": arms, "raw": raw}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "arms")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
