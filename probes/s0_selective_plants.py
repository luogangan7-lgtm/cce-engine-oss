# -*- coding: utf-8 -*-
"""s0 两个 WEAK 面(进程位置 / 触发事件)的归因: 读数串扰, 还是植入句自己蕴含了邻面? 预注册 tests/data/s0_selective_plants_prereg.json。

此前(results/s0_planted_profile.json)这两面目标位移够、但别的面跟着动(净连带 TVD 0.10–0.13)。事后按植入值拆开看, 连带全落在逻辑上被蕴含的值上
(「在比价」↔「在比较权衡」, 「刚花过钱」→「已购买」, 「已决定」→「有决定权」)。那是开发材料上的事后分析, 这里在没用过的 100 条真实评论上确认:
  选择性植入句(写的时候就避开邻面): 目标面位移要够, 其余四面相对**等长假句**的净变化要小 —— 每套措辞各自成立
  蕴含性植入句(沿用原句): 邻面上被蕴含的那个值要明显上升 —— 这是读对了言外之意, 记「嵌套」不记「串扰」
对照都是追加一句等长的无关句(不是不追加), 底噪 = 两句不同假句之间的 TVD。只调 Jev(约 $0.00005/次), 上限 2000。产物只放指针与概率。
"""
import argparse, collections, hashlib, importlib.util, json, math, os, pathlib, random, statistics, sys, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
pv, V5 = _load("_pv", "probes/s0_planted_validity.py"), _load("_v5", "probes/align_atoms_v5.py")
S0, shadow, FACETS = pv.S0, pv.shadow, pv.FACETS
PRE = ROOT / "tests/data/s0_selective_plants_prereg.json"
OUT = ROOT / "results/s0_selective_plants.json"
CAP, N_ROOTS, SEED, BOOT = 2000, 100, 20261001, 2000
OFF = ("进程位置", "触发事件", "关系位置", "身体状态", "资源状态")      # 情绪余温 已扣发, 不进判据
MIN_SHIFT, MAX_NET, MIN_ENTAIL = 0.50, 0.05, 0.20
SHAM = ["The weather here has been mild this week.", "I usually read these threads in the evening."]
SELECTIVE = {
    "进程位置": {"在找方案": ["I'm at the stage of looking into what could be done about it.", "At this point I'm still exploring what my options even are."],
                 "回看复盘": ["Looking back on how this whole thing went, I see it differently now.", "With hindsight, I'd handle the whole process another way."]},
    "触发事件": {"被否定或质疑": ["Someone just told me I was wrong about this.", "I was told today that I'm imagining the whole thing."],
                 "受挫/出故障": ["Something went wrong again today and it set me back.", "I hit another setback with this just now."]},
}
ENTAILING = {      # (面, 值) → (被蕴含的邻面, 邻面值); 句子沿用 s0_planted_validity.PLANTS
    ("进程位置", "在比较权衡"): ("触发事件", "正在比价"), ("触发事件", "正在比价"): ("进程位置", "在比较权衡"),
    ("触发事件", "刚花过钱"): ("关系位置", "已购买"), ("进程位置", "已决定在执行"): ("资源状态", "有决定权"),
}


def roots():
    return V5.natural(140) + V5.natural(160) + V5.natural(180) + V5.natural(200) + V5.natural(220)


def jobs(rs):
    out = []
    for ptr, body in rs:
        out.append((ptr, "baseline", None, None, None, body))
        for w, s in enumerate(SHAM): out.append((ptr, "sham", None, None, w, body + "\n\n" + s))
        for f, vals in SELECTIVE.items():
            for v, ss in vals.items():
                for w, s in enumerate(ss): out.append((ptr, "selective", f, v, w, body + "\n\n" + s))
        for (f, v) in ENTAILING:
            for w, s in enumerate(pv.PLANTS[f][v]): out.append((ptr, "entailing", f, v, w, body + "\n\n" + s))
    return out


def tvd(p, q):
    return 0.5 * math.fsum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def bounds(xs):
    """(均值, 单侧 97.5% 下界, 单侧 97.5% 上界) —— 按根文本自助。"""
    rng = random.Random(SEED); n = len(xs)
    ms = sorted(math.fsum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return round(math.fsum(xs) / n, 4), round(ms[int(0.025 * BOOT)], 4), round(ms[int(0.975 * BOOT) - 1], 4)


def analyse(rows):
    by = collections.defaultdict(dict)
    for r in rows:
        if r["probs"]: by[r["ptr"]][(r["kind"], r["facet"], r["value"], r["w"])] = r["probs"]
    need = len(jobs([("x", "")]))
    ptrs = sorted(p for p, d in by.items() if len(d) == need)          # 只用整套读数齐全的根
    floor = {g: bounds([tvd(by[p][("sham", None, None, 0)][g], by[p][("sham", None, None, 1)][g]) for p in ptrs]) for g in OFF} if ptrs else {}
    sel = {}
    for f, vals in SELECTIVE.items():
        per_w = {}
        for w in (0, 1):
            sh = lambda p: by[p][("sham", None, None, w)]
            shift = bounds([statistics.fmean(by[p][("selective", f, v, w)][f].get(v, 0.0) - sh(p)[f].get(v, 0.0) for v in vals) for p in ptrs])
            off = {}
            for g in OFF:
                if g == f: continue
                raw = [statistics.fmean(tvd(by[p][("selective", f, v, w)][g], sh(p)[g]) for v in vals) for p in ptrs]
                fl = [tvd(by[p][("sham", None, None, 0)][g], by[p][("sham", None, None, 1)][g]) for p in ptrs]
                off[g] = {"raw_tvd": bounds(raw)[0], "net": bounds([a - b for a, b in zip(raw, fl)])}
            ok_t = shift[1] >= MIN_SHIFT; ok_o = all(o["net"][2] <= MAX_NET for o in off.values())
            per_w[str(w)] = {"target_shift": shift, "off_target": off, "target_ok": ok_t, "off_target_ok": ok_o}
        t = all(x["target_ok"] for x in per_w.values()); o = all(x["off_target_ok"] for x in per_w.values())
        sel[f] = {"per_wording": per_w, "verdict": "SELECTIVE" if t and o else ("CROSS_SENSITIVE" if t else "UNRESPONSIVE")}
    ent = {}
    for (f, v), (g, gv) in ENTAILING.items():
        pw = {str(w): bounds([by[p][("entailing", f, v, w)][g].get(gv, 0.0) - by[p][("sham", None, None, w)][g].get(gv, 0.0) for p in ptrs]) for w in (0, 1)}
        ent["%s·%s→%s·%s" % (f, v, g, gv)] = {"delta_p": pw, "verdict": "NESTED" if all(x[1] >= MIN_ENTAIL for x in pw.values()) else "NOT_SHOWN"}
    return {"n_roots_complete": len(ptrs), "sham_floor_tvd": floor, "selective": sel, "entailing": ent}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--rescore", action="store_true"); a = ap.parse_args(argv)
    rs = roots(); js = jobs(rs); assert len(rs) == N_ROOTS and len(js) <= CAP, (len(rs), len(js))
    if a.rescore:
        res = json.loads(OUT.read_text(encoding="utf-8")); res["result"] = analyse(res["raw"])
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"); print(json.dumps(res["result"], ensure_ascii=False, indent=1)); return
    ledger, lock = {"req": 0}, threading.Lock()
    if a.dry_run:
        os.environ["TYPESAFE_API_KEY"] = "dry"
        post = lambda body, k: ({"answers": {q: {"choice": "未知", "probabilities": {"未知": 1.0}} for q in body["questions"]}}, None)
    else:
        os.environ["TYPESAFE_API_KEY"] = shadow._key()          # 仅本进程内
        def post(body, k):
            with lock:
                ledger["req"] += 1
                if ledger["req"] > CAP: raise RuntimeError("BUDGET_EXCEEDED")
            return S0._post(body, k, retries=2)

    def one(j):
        ptr, kind, f, v, w, body = j
        _read, probs, err = S0.s0_jev_read(body[:2000], FACETS, post=post)
        return {"ptr": ptr, "kind": kind, "facet": f, "value": v, "w": w, "probs": probs, "err": err}
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, js))
    res = {"block": "S0_SELECTIVE_PLANTS", "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest() if PRE.exists() else None,
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "requests": ledger["req"], "errors": dict(collections.Counter(r["err"] for r in rows if r["err"])),
           "root_pointers": [p for p, _ in rs], "result": analyse(rows), "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "errors", "result")}, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
