# -*- coding: utf-8 -*-
"""s1 组内散布闸 · 扣发率的序贯监测(预注册 tests/data/within_js_monitor_prereg.json)。零调用, 只读归档与已落盘的数字。

两次重标定采纳新阈值时用的判据是「留出扣发率在 [5%, 25%]」, 但留出只有 16 条(k=3)/ 10 条(k=5)文本 ——
网页 GPT(2026-09-30): 要让双侧 95% 精确区间整个落在 [5%, 25%] 内, 数学上至少 54 条独立文本, 规划上要 150–180。
⇒ 「已落在带内」这句话现在没有依据, 撤回; 阈值本身(median+2×MAD)照用。带内与否改由本监测在生产读数攒够后判:
  文本级事件(同一 input_sha 只算第一次读数)· 预定在 n = 60 / 120 / 180 三次查看 · 错误概率 0.010 / 0.015 / 0.025
  (对应 99% / 98.5% / 97.5% 双侧 Clopper–Pearson 区间, 合计 0.05)· 区间整个在带内 ⇒ IN_BAND, 整个在带外 ⇒ OUT_OF_BAND,
  否则等下一次查看; 到 180 仍跨界 ⇒ UNRESOLVED, 不再加样。
"""
import glob, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import cce_full_run as FR   # noqa: E402
LOOKS = ((60, 0.010), (120, 0.015), (180, 0.025))
BAND = (0.05, 0.25)
LAYERS = ("desire_vec", "need_vec", "emotion_vec", "action_vec")
INSTRUMENTS = {"d4cce4c745f3f991": "k=3", "c4419c3e53aa2fa9": "k=5"}


def _cdf(k, n, p):
    return math.fsum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k, n, alpha):
    """双侧精确区间(二分法反演二项分布)。"""
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return (lo + hi) / 2
    low = 0.0 if k == 0 else solve(lambda p: 1 - _cdf(k - 1, n, p) < alpha / 2)
    high = 1.0 if k == n else solve(lambda p: _cdf(k, n, p) > alpha / 2)
    return round(low, 4), round(high, 4)


def events(instrument):
    """[(来源, input_sha, {层: within_js})] —— 不在标定集里的读数, 同一文本只取第一次。"""
    out, seen = [], set()
    cal = set()
    if instrument == "d4cce4c745f3f991":
        cal = set(json.loads((ROOT / "tests/data/within_js_recalibration_prereg.json").read_text(encoding="utf-8"))["calibration_set"]["files"])
        for r in json.loads((ROOT / "results/within_js_holdout_numbers.json").read_text(encoding="utf-8"))["rows"]:
            if r["arm"] == "with" and r["rep"] == 0:
                out.append(("holdout:s1ab#%d" % r["text"], "s1ab:%d" % r["text"], r["within_js"])); seen.add("s1ab:%d" % r["text"])
    else:
        for r in json.loads((ROOT / "results/within_js_k5_numbers.json").read_text(encoding="utf-8"))["rows"]:
            if r["set"] == "hold" and r["rep"] == 0:
                out.append(("holdout:k5#%s" % r["sha16"], r["sha16"], r["within_js"])); seen.add(r["sha16"])
    for f in sorted(glob.glob(str(ROOT / "archive/*/*s1_readout.json"))):
        rel = str(pathlib.Path(f).relative_to(ROOT))
        if rel in cal:
            continue
        d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        js = (d.get("stage1") or {}).get("within_js")
        if not js or ((d.get("stage2") or {}).get("instrument") or {}).get("instrument_hash") != instrument:
            continue
        sha = d.get("input_sha") or rel
        if sha in seen:
            continue
        seen.add(sha); out.append((rel, sha, js))
    return out


def judge(flags):
    """flags = 按到达顺序的逐文本超限标记 → (判决, 判决所用查看点, 区间)。只在预定查看点上判, 一旦判定即停。"""
    for m, a in LOOKS:
        if len(flags) < m:
            return ("ACCUMULATING" if m == LOOKS[0][0] else "CONTINUE"), None, None
        lo, hi = clopper_pearson(sum(flags[:m]), m, a)
        if lo >= BAND[0] and hi <= BAND[1]: return "IN_BAND", m, (lo, hi)
        if hi < BAND[0] or lo > BAND[1]: return "OUT_OF_BAND", m, (lo, hi)
    return "UNRESOLVED", LOOKS[-1][0], (lo, hi)


def build():
    res = {}
    for inst, name in INSTRUMENTS.items():
        ev = events(inst)[:LOOKS[-1][0]]
        th = FR.within_js_max(inst); n = len(ev)
        per = {}
        for l in LAYERS:
            flags = [js.get(l, 0) > th[l] for _, _, js in ev]; k = sum(flags)
            v, at, ci = judge(flags)
            per[l] = {"threshold": th[l], "exceed": k, "n_texts": n, "rate": round(k / n, 4) if n else None,
                      "ci95_now(只供参考, 不作判据)": clopper_pearson(k, n, 0.05) if n else None, "verdict": v, "look_n": at, "look_ci": ci}
        res[inst] = {"instrument": name, "n_texts": n, "next_look_at": next((m for m, _ in LOOKS if m > n), None), "per_layer": per}
    return res


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
