# -*- coding: utf-8 -*-
"""A/B 实测: reply 链 串行(CCE_SERIAL_STAGES=1) vs 重叠(默认), 同一对文本各跑一次真实链。

★ 会发起调用: 每次 reply 链 = reader_baseline(K=3 s1 + n s2) + s1(K=3 + n s2) ≈ 16 次 MiniMax + s0 1 次 Jev; 两臂合计 ≈ 32 MiniMax + 2 Jev。硬上限: 2 次链。
★ 这是**本地基准**, 不是生产运行(生产在 cce-submit.yml)。文本是本探针自带的合成句, 不用语料。
量三件事: ① 墙钟(总/逐段) ② 两臂 operational 账本里 INFRA_FAILED / 重试次数(并发 10 路会不会撞限流) ③ 两臂 k_ok 是否都达标。
"""
import json, os, pathlib, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]; OUT = ROOT / "results/stage_overlap_bench.json"
DRAFT = ("Thanks for laying out the battery numbers. I switched to rechargeables last spring and the first month was rough: "
         "two dead aids by dinner, twice. What fixed it for me was turning off the streaming when I'm not using it and a firmware update "
         "the clinic pushed. Now I get through a full day with about 20% left. If yours still die early after that, ask them to check the contacts.")
READER = ("Honestly I'm about ready to give up on these. Paid a fortune, and the left one dies by 4pm every single day. The audiologist says "
          "it's normal. Is it? I'm comparing the new models but I don't want to spend again if it's just going to be the same story.")


def _load_key():
    for line in pathlib.Path("/Volumes/data/viral-skill-eval/.env").read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if "=" in line and line.split("=", 1)[0] in ("MINIMAX_API_KEY", "TYPESAFE_API_KEY"): os.environ[line.split("=", 1)[0]] = line.split("=", 1)[1].strip().strip('"').strip("'")


def _ops(p):
    d = json.loads(pathlib.Path(p).read_text(encoding="utf-8")); st = d["stage1"]
    op = st.get("operational") or {}; att = st.get("attempts") or op.get("attempts") or []
    return {"k_ok": st.get("k_ok"), "k_requested": st.get("k_requested"), "operational": {k: v for k, v in op.items() if not isinstance(v, (list, dict))},
            "attempts_total": len(att), "INFRA_FAILED": sum(1 for a in att if a.get("status") == "INFRA_FAILED"), "PARSE_FAILED": sum(1 for a in att if a.get("status") == "PARSE_FAILED"),
            "s2_draws": (d["stage2"].get("sampling") or {}).get("n_draws")}


def run_arm(serial):
    tmp = tempfile.mkdtemp(prefix="overlap_" + ("serial" if serial else "overlap") + "_"); d = pathlib.Path(tmp)
    (d / "in.txt").write_text(DRAFT, encoding="utf-8"); (d / "reader.txt").write_text(READER, encoding="utf-8")
    env = dict(os.environ, CCE_SERIAL_STAGES="1" if serial else "0")
    t0 = time.time()
    p = subprocess.run([sys.executable, str(ROOT / "scripts/cce_full_run.py"), "--mode", "reply", "--text-file", str(d / "in.txt"), "--context", "bench", "--outdir", tmp, "--reader-file", str(d / "reader.txt")],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=1500)
    wall = round(time.time() - t0, 1); m = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").exists() else {}
    return {"arm": "serial" if serial else "overlap", "rc": p.returncode, "wall_sec": wall, "complete": m.get("complete"), "failed_at": m.get("failed_at"),
            "stage_sec": {k: v.get("sec") for k, v in (m.get("stages") or {}).items()}, "s0_backend": (m.get("stages") or {}).get("s0_context", {}).get("read_backend"),
            "reader": _ops(d / "reader_baseline.json") if (d / "reader_baseline.json").exists() else None, "s1": _ops(d / "s1_readout.json") if (d / "s1_readout.json").exists() else None,
            "stderr_tail": (p.stderr or "")[-300:] if p.returncode else ""}


def main():
    _load_key(); arms = [run_arm(True), run_arm(False)]
    a, b = arms
    both_ok = a["rc"] == 0 and b["rc"] == 0
    res = {"block": "STAGE_OVERLAP_BENCH", "date": "2026-09-23", "★性质": "本地基准, 同文本各跑 1 次; n=1 ⇒ 只报观察值, 不报置信区间",
           "★调用账": "两臂各 1 次 reply 链(≈16 MiniMax + 1 Jev)", "arms": arms,
           "★节省": {"wall_sec 串行→重叠": [a["wall_sec"], b["wall_sec"]], "节省秒": round(a["wall_sec"] - b["wall_sec"], 1) if both_ok else None,
                    "节省比": round(1 - b["wall_sec"] / a["wall_sec"], 3) if both_ok and a["wall_sec"] else None,
                    "理论上限(=min(reader, s1) 串行秒)": min(a["stage_sec"].get("reader_baseline") or 0, a["stage_sec"].get("s1_readout") or 0) if both_ok else None},
           "★限流": {arm["arm"]: {"reader INFRA_FAILED": (arm["reader"] or {}).get("INFRA_FAILED"), "s1 INFRA_FAILED": (arm["s1"] or {}).get("INFRA_FAILED"), "reader k_ok": (arm["reader"] or {}).get("k_ok"), "s1 k_ok": (arm["s1"] or {}).get("k_ok")} for arm in arms},
           "★怎么读": ["重叠臂 INFRA_FAILED 若高于串行臂 ⇒ 10 路并发撞限流, 节省被重试吃掉, 要限并发。", "n=1: 两臂差异含抽样波动(单次 s1 就有 64–161 s 的历史跨度), 只能说方向, 不能说精确倍数。"]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k in ("★节省", "★限流")}, ensure_ascii=False, indent=1)); print("→", OUT); return 0 if both_ok else 1


if __name__ == "__main__": sys.exit(main())
