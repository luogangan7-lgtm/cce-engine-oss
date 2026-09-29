# -*- coding: utf-8 -*-
"""对齐出口 v4 逐原子校对(预注册 tests/data/align_atoms_calibration_prereg.json)。

每个原子两份构造草稿: sat(满足: 【做】= 做了, 【禁】= 没违反)与 unsat(不满足: 【做】= 只沾话题没做, 【禁】= 违反)。
草稿由维护者按原子写成, 预注册时冻结(这里的 CASES), 真值由构造给出 —— 局部测试神谕, 不是金标。
每份草稿在它所属结的完整清单下判, 只计目标原子。v4: 两种相反问法(A/B)× 两次(温度 0); v1(旧提问)× 两次作对照。
MiniMax 经生产同一出站路径, 本进程开请求作用域, 硬上限 350。
用法: .venv/bin/python probes/align_atoms_calibration.py [--dry-run]
"""
import argparse, collections, hashlib, importlib.util, json, os, pathlib, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "probes"))
import cce_align_atoms as AT                                   # noqa: E402
from cce_request_budget import open_scope, scope_status        # noqa: E402
PRE = ROOT / "tests/data/align_atoms_calibration_prereg.json"
OUT = ROOT / "results/align_atoms_calibration.json"
CAP, REPS = 350, 2

CASES = {
    "pain_seek#0": {"sat": "The whistling is feedback: sound from the receiver leaks back into the mic because the dome isn't sealing. Swap to a closed dome one size up tonight, and if it still squeals, ask your audiologist to rerun the feedback calibration.",
                    "unsat": "Feedback whistling is really common with hearing aids and a lot of people deal with it. Hopefully it settles down for you soon."},
    "pain_seek#1": {"sat": "A closed dome usually cuts the whistling, but I can't promise it fixes yours; if your ear canal shape is the cause, only a custom mold will.",
                    "unsat": "Trust me, switch to a closed dome and your whistling will be gone for good, guaranteed."},
    "injustice#0": {"sat": "You're right to be angry; being charged twice for the same fitting appointment isn't okay.",
                    "unsat": "Billing departments process thousands of claims a week, so double charges like this come up from time to time."},
    "injustice#1": {"sat": "Call the clinic, describe exactly what happened with the double charge, and ask for a case or ticket number before you hang up so the refund can be tracked.",
                    "unsat": "Someone at that clinic really should be held accountable for this."},
    "injustice#2": {"sat": "That double charge is on the clinic, and it's reasonable to expect them to fix it.",
                    "unsat": "To be fair to the clinic, their billing system is probably overloaded and they likely didn't mean to charge you twice."},
    "belong#0": {"sat": "You're definitely not the only one; plenty of us felt exactly this lost in the first month with aids.",
                 "unsat": "The first month with hearing aids involves an adjustment period."},
    "belong#1": {"sat": "One thing that surprised me: your brain needs around four to six weeks of daily wear to relearn background sounds, so short wearing sessions actually slow the adjustment down.",
                 "unsat": "Adjusting to hearing aids takes time, just keep at it."},
    "belong#2": {"sat": "Here's the one thing that helped me most: wear them all day from the start, even when it's tiring.",
                 "unsat": "Wear them all day, turn on the speech-in-noise program, get a closed dome, ask for a real-ear measurement, try a remote mic, and go through the streaming settings in the app."},
    "belong#3": {"sat": "It really does get easier; I remember feeling exactly the same in week two.",
                 "unsat": "Book a follow-up this week, keep a daily listening log, and report back here on Friday."},
    "reward#0": {"sat": "Glad it worked out, enjoy them!",
                 "unsat": "Glad it worked out! Now that they're fitted, a few more things are worth knowing: the app has an equalizer, you can set up a restaurant program, and changing the wax guards every week makes a real difference to sound quality over the months ahead."},
    "reward#1": {"sat": "Honestly you did all the work there; I just happened to mention the dome.",
                 "unsat": "Good thing you followed my advice; I've helped a lot of people with exactly this problem."},
    "reward#2": {"sat": "Great to hear it's sorted, congrats!",
                 "unsat": "Great to hear it's sorted! By the way, you should also look into the tinnitus masking feature and the new firmware update that changes the noise program."},
    "display#0": {"sat": "That's a much better explanation than mine; your breakdown of the frequency bands is spot on.",
                  "unsat": "Interesting post. I wrote something similar about frequency bands last year."},
    "display#1": {"sat": "Great writeup; as a fellow long-time wearer I ran into the same thing, and your fix matches what worked for me.",
                  "unsat": "Nice job for a beginner, keep learning and you'll get there."},
    "display#2": {"sat": "Building on your point about closed domes, pairing them with a smaller vent gave me even less feedback.",
                  "unsat": "Actually, you've got it wrong; closed domes are not the fix, let me explain how feedback really works."},
    "itch#0": {"sat": "Picture yourself at a crowded café, catching every word of your friend's joke while the espresso machine hisses behind you; that's the kind of person these new aids are built for.",
               "unsat": "The new model has improved noise reduction and a longer battery life."},
    "itch#1": {"sat": "They sound amazing; I can totally see why you're excited about them.",
               "unsat": "Go compare prices at three clinics, download both apps, and book demos before you decide."},
    "itch#2": {"sat": "I know they're out of budget for now, but it's fun to daydream about hearing the birds that clearly on a morning walk someday.",
               "unsat": "It's really depressing that they're so expensive that most of us will never be able to afford them."},
    "suspend#0": {"sat": "Pick the one that wins on what you struggle with most: if it's restaurants, ask both clinics for a free week-long trial and wear each at your usual Friday dinner. The rechargeable is easier, but you give up swapping batteries on a trip.",
                  "unsat": "Both are good hearing aids and a lot of people are happy with either one."},
    "suspend#1": {"sat": "Take your time; there's no rush to buy either one until a trial convinces you.",
                  "unsat": "Just buy the Phonak now; it's risk-free with the money-back guarantee and everyone I know loves theirs."},
    "inertia#0": {"sat": "You mentioned you skip wearing them because the battery door is fiddly with your arthritis; a rechargeable model removes exactly that step.",
                  "unsat": "You should really wear your hearing aids more; they're good for your brain health."},
    "inertia#1": {"sat": "Just try wearing them during one TV show tonight; if it's annoying, take them out and nothing's lost.",
                  "unsat": "You need to commit to wearing them twelve hours a day starting tomorrow and drop your old routine."},
    "inertia#2": {"sat": "Totally fair to leave them in the drawer if they're not helping yet.",
                  "unsat": "Untreated hearing loss is linked to cognitive decline, and everyone owes it to their family to wear their aids every single day."},
    "audit#0": {"sat": "The trial ran 14 days with two wearers; happy to share the raw notes.",
                "unsat": "I've been doing this for twenty years and I'm honestly offended anyone would question my results; I always do everything by the book."},
    "audit#1": {"sat": "The trial ran 14 days with two wearers and the dropout log is in the linked spreadsheet; ask me anything specific and I'll pull the exact numbers.",
                "unsat": "The results were really good and I'm confident they're accurate."},
}


def jobs(cases=None, arms=("v4a", "v4b", "v1")):
    out = []
    for key, d in (cases or CASES).items():
        knot, i = key.rsplit("#", 1)
        for kind in ("sat", "unsat"):
            for rep in range(REPS):
                for arm in arms:
                    out.append((key, knot, int(i), kind, rep, arm, d[kind]))
    return out


def score(rows, cases=None):
    per = {}
    for key in (cases or CASES):
        rs = [r for r in rows if r["key"] == key]
        v4 = [r for r in rs if r["arm"] in ("v4a", "v4b")]
        v1 = [r for r in rs if r["arm"] == "v1"]
        ok4 = sum(r["canonical"] == ("satisfied" if r["kind"] == "sat" else "unsatisfied") for r in v4)
        ok1 = sum(r["canonical"] == ("satisfied" if r["kind"] == "sat" else "unsatisfied") for r in v1)
        unc = sum(r["canonical"] == "uncertain" for r in v4)
        flips = sum(1 for kind in ("sat", "unsat") for rep in range(REPS)
                    if len({r["canonical"] for r in v4 if r["kind"] == kind and r["rep"] == rep}) > 1)
        per[key] = {"v4_correct": ok4, "v4_n": len(v4), "v4_uncertain": unc, "framing_flips": flips,
                    "v1_correct": ok1, "v1_n": len(v1),
                    "verdict": "CALIBRATED" if len(v4) == 4 * REPS and ok4 == len(v4) else "NOT_CALIBRATED"}
    n_cal = sum(v["verdict"] == "CALIBRATED" for v in per.values())
    return per, {"calibrated": n_cal, "of": len(per),
                 "v4_accuracy": round(sum(v["v4_correct"] for v in per.values()) / max(1, sum(v["v4_n"] for v in per.values())), 4),
                 # 没跑 v1(留出集)时是「未跑」不是 0 —— 2026-09-30 首版在这里报了 0.0
                 "v1_accuracy": (round(sum(v["v1_correct"] for v in per.values()) / sum(v["v1_n"] for v in per.values()), 4)
                                 if sum(v["v1_n"] for v in per.values()) else None)}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--heldout", action="store_true", help="v4.1 留出校对: 新构造草稿, 只跑 v4 两种问法(预注册 tests/data/align_atoms_heldout_prereg.json)")
    a = ap.parse_args(argv)
    global PRE, OUT, CAP
    cases = None
    if a.heldout:
        import align_atoms_heldout_cases as HC   # noqa: E402
        cases, PRE, OUT, CAP = HC.CASES, ROOT / "tests/data/align_atoms_heldout_prereg.json", ROOT / "results/align_atoms_heldout_v41.json", 240
        js = jobs(cases, arms=("v4a", "v4b"))
    else:
        js = jobs()
    assert len(js) <= CAP
    if a.dry_run:
        def call(prompt, temperature=0.0):
            n = prompt.count("【做】") + prompt.count("【禁】")
            st = "符合" if "是否符合" in prompt else "做了"
            return json.dumps({"atoms": [{"i": i + 1, "state": st, "quote": ""} for i in range(n)]}, ensure_ascii=False)
    else:
        sys.path.insert(0, str(ROOT / "probes")); import extractor_counterexample_run_r2 as KR   # noqa: E402
        KR._load_key(); call = None
    open_scope("align_atoms_cal", CAP, os.path.join(tempfile.mkdtemp(), "budget.json"))
    _s = importlib.util.spec_from_file_location("_par", ROOT / "probes/playbook_atoms_reliability.py")
    PAR = importlib.util.module_from_spec(_s); _s.loader.exec_module(PAR)
    lock = threading.Lock()

    def one(j):
        key, knot, i, kind, rep, arm, text = j
        if arm == "v1":
            if a.dry_run:
                canon = "satisfied"
            else:
                r = PAR.read_once(knot, text, 0.0, "v1")
                canon = None if r is None else ("satisfied" if r["per_atom"][i]["executed"] == 1 else "unsatisfied")
            return {"key": key, "kind": kind, "rep": rep, "arm": arm, "canonical": canon or "failed", "state": None}
        r = AT.judge(knot, text, framing=arm[-1], call=call)
        if r is None:
            return {"key": key, "kind": kind, "rep": rep, "arm": arm, "canonical": "failed", "state": None}
        return {"key": key, "kind": kind, "rep": rep, "arm": arm, "canonical": r[i]["canonical"], "state": r[i]["state"],
                "quote_verbatim": bool(r[i]["quote"]) and r[i]["quote"] in text}
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, js))
    per, summ = score(rows, cases)
    res = {"block": "ALIGN_ATOMS_HELDOUT_V41" if a.heldout else "ALIGN_ATOMS_CALIBRATION", "judge_version": AT.VERSION if a.heldout else "v4",
           "run_at": "2026-09-30", "dry_run": a.dry_run,
           "prereg_sha256": hashlib.sha256(PRE.read_bytes()).hexdigest(),
           "probe_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
           "judge_sha256": hashlib.sha256((ROOT / "scripts/cce_align_atoms.py").read_bytes()).hexdigest(),
           "requests": scope_status(), "summary": summ, "per_atom": per, "raw": rows}
    if not a.dry_run:
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("requests", "summary")}, ensure_ascii=False, indent=1))
    print({k: (v["verdict"], v["v4_correct"], v["v1_correct"]) for k, v in per.items()})


if __name__ == "__main__":
    main()
