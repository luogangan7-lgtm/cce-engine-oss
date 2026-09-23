# -*- coding: utf-8 -*-
"""s0_context 的 Jev 影子臂: 同一批真实段落, 同一段 body[:2000], MiniMax 用**生产 s0 的原提示词**, Jev 用逐面 Choice。
**描述性**: s0 没有金标, 只报一致率、双方「未知」率、Jev 置信度; 不判优劣、不接生产。
★ 会发起调用: MiniMax 42(订阅) + Jev 42(计量, ≈$0.002)。硬上限各 42, 撞上即停。
★ s0_jev_fill() 是可复用的适配器(与生产 s0 同签名的纯函数), **未接线** —— 接线是核心文件改动, 要 owner 点头。
"""
import argparse, hashlib, importlib.util, json, pathlib, sys, time, urllib.request, urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRE1 = ROOT / "tests/data/real_corpus_pilot_prereg.json"
OUT = ROOT / "results/s0_jev_shadow.json"; PARTIAL = ROOT / "results/s0_jev_shadow_partial.jsonl"
TAXO = json.loads((ROOT / "config/context_taxonomy.json").read_text(encoding="utf-8"))
FACETS = TAXO["facets"]; UNKNOWN = {"未知", "未提及", "", None}
READABLE = [f for f in FACETS if f.get("readable_from_text") in (True, "partial")]   # ★ 从配置算, 不手写 6/3
BODY_CHARS = 2000; CAP = 42; API = "https://api.typesafe.ai/v1/systemone"; MODEL = "jev-latest"


def s0_prompt(body):
    """★ 与 scripts/cce_full_run.py s0() 里的提示词**逐字相同**(闸比对)。"""
    spec = "\n".join(f"  {f['key']}: {f['values']}" for f in READABLE)
    return (f"逐面读出这段内容体现的读者情境。**读不出来就填\"未知\", 严禁猜**。\n"
            f"{spec}\n\n【内容】\n{body}\n\n只输出JSON: {{\"面名\":\"选中值\"}}")


def jev_questions():
    qs = {}
    for f in READABLE:
        opts = {v: "%s: %s" % (f["desc"], v) for v in f["values"]}
        if not (set(f["values"]) & UNKNOWN):
            opts["未知"] = "the text does not show this facet; do not guess"
        qs[f["key"]] = {"type": "choice", "instructions": "Read this facet of the reader's situation from the text. Facet: %s (%s). If the text does not show it, choose 未知; never guess." % (f["key"], f["desc"]), "criteria": opts}
    return qs


def s0_jev_fill(body, call):
    """适配器: body → {面名: 选中值}(与生产 s0 的 read 同形) + 概率。call(body_dict)->(resp, err)。"""
    resp, err = call({"model": MODEL, "state": body, "questions": jev_questions()})
    if err or not resp: return None, None, err
    ans = resp["answers"]; read = {k: ans[k]["choice"] for k in jev_questions()}
    probs = {k: ans[k]["probabilities"] for k in jev_questions()}
    return read, probs, None


def question_sha():
    return hashlib.sha256(json.dumps(jev_questions(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _key():
    for line in pathlib.Path("/Volumes/data/viral-skill-eval/.env").read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if line.startswith("TYPESAFE_API_KEY="): return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no TYPESAFE_API_KEY")


def jev_call(body, key, ledger):
    for att in range(3):
        ledger["req"] += 1
        if ledger["req"] > CAP * 2: raise RuntimeError("BUDGET_EXCEEDED")
        req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r: d = json.load(r)
            u = d.get("usage") or {}; ledger["tok_in"] += int(u.get("input_tokens") or 0); return d, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and att < 2: time.sleep(3 * (att + 1)); continue
            return None, "HTTP %d" % e.code
        except Exception as e: return None, type(e).__name__
    return None, "RETRY_EXHAUSTED"


def load_passages():
    pre = json.loads(PRE1.read_text(encoding="utf-8")); items = [pre[k] for k in pre if "冻结输入集" in k][0]["items"]
    cache, out = {}, []
    for it in items:
        f = it["file"]
        if f not in cache: cache[f] = (ROOT / f).read_text(encoding="utf-8").split("\n")
        line = cache[f][it["line_index"]]; assert hashlib.sha256(line.encode()).hexdigest() == it["sha256"]
        out.append(("%s:%d" % (f, it["line_index"]), line[:BODY_CHARS]))
    return out


def build_result(rows, ledger):
    ok = [r for r in rows if r["mm_ok"] and r["jev_ok"]]
    per = {}
    for f in READABLE:
        k = f["key"]; n = len(ok)
        agree = sum(1 for r in ok if r["mm"].get(k) == r["jev"].get(k))
        mm_unk = sum(1 for r in ok if r["mm"].get(k) in UNKNOWN or r["mm"].get(k) not in f["values"])
        jv_unk = sum(1 for r in ok if r["jev"].get(k) in UNKNOWN)
        both_known_agree = sum(1 for r in ok if r["mm"].get(k) == r["jev"].get(k) and r["jev"].get(k) not in UNKNOWN)
        conf = [r["jev_conf"][k] for r in ok]
        per[k] = {"一致": "%d/%d" % (agree, n), "两者都非未知且一致": both_known_agree, "MiniMax 未知/非法": mm_unk, "Jev 未知": jv_unk,
                  "Jev 置信度中位": round(sorted(conf)[len(conf) // 2], 3) if conf else None,
                  "MiniMax 取值分布": dict(sorted(__import__("collections").Counter(r["mm"].get(k) for r in ok).items(), key=lambda kv: -kv[1])),
                  "Jev 取值分布": dict(sorted(__import__("collections").Counter(r["jev"].get(k) for r in ok).items(), key=lambda kv: -kv[1]))}
    return {"block": "S0_JEV_SHADOW", "date": "2026-09-23", "★性质": "描述性影子对照, 无金标 ⇒ **不判优劣**, 不接生产。",
            "★输入": "real_corpus_pilot 冻结的 42 条含品牌段落(指针, 不落原文), body[:%d] 与生产 s0 相同" % BODY_CHARS,
            "★MiniMax 提示词 sha": hashlib.sha256(s0_prompt("").encode()).hexdigest()[:16], "★Jev 题目集 sha": question_sha(),
            "★可读面(配置现算)": [f["key"] for f in READABLE], "★实际执行": len(rows), "★双方都成功": len(ok), "★账本": ledger,
            "★★★逐面": per,
            "★★★怎么读": ["一致率高的面: 两个模型家族读法收敛, 换掉 MiniMax 的风险小。", "一致率低的面: 谁对不知道 —— 没金标; 要人看样本。",
                          "Jev 未知率 vs MiniMax 未知率: 生产纪律是「读不出就填未知, 严禁猜」, 未知率**低不是好**。",
                          "★ CJK: Jev 官方说非英语不同等; 题面与取值是中文, 段落是英文 —— 结果只对这批英文段落有效。"],
            "★不得据此说": ["不得说 Jev 的 s0 更准/更差。", "不得据此接生产 —— 接线是核心文件改动, 要 owner 点头。", "不得说全链提速: s0 只是 1 次调用。"],
            "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    ps = load_passages(); assert len(ps) == CAP
    sys.path.insert(0, str(ROOT / "scripts")); from exp_v4_full_validation import extract_json_robust
    ledger = {"req": 0, "tok_in": 0, "minimax": 0}
    if a.dry_run:
        def mm_call(p): return json.dumps({f["key"]: f["values"][0] for f in READABLE}, ensure_ascii=False), {}
        def jv_call(body): return {"answers": {k: {"choice": READABLE[i]["values"][0], "probabilities": {READABLE[i]["values"][0]: 1.0}} for i, k in enumerate(body["questions"])}}, None
    else:
        s = importlib.util.spec_from_file_location("_r2", ROOT / "probes/extractor_counterexample_run_r2.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); m._load_key()
        from exp_crossmodel_desire import call_model
        key = _key()
        def mm_call(p):
            ledger["minimax"] += 1
            if ledger["minimax"] > CAP: raise RuntimeError("BUDGET_EXCEEDED minimax")
            return call_model("M3", p, temperature=0.0, max_retries=1)
        def jv_call(body): return jev_call(body, key, ledger)
        if PARTIAL.exists(): PARTIAL.unlink()
    rows = []
    for ptr, body in ps:
        c, meta = mm_call(s0_prompt(body)); rd = extract_json_robust(c, log_note="s0_shadow") if c else None
        mm_ok = isinstance(rd, dict) and not (meta or {}).get("error")
        jr, jp, err = s0_jev_fill(body, jv_call)
        row = {"ptr": ptr, "mm_ok": bool(mm_ok), "mm": ({k: rd.get(k) for k in [f["key"] for f in READABLE]} if mm_ok else None),
               "jev_ok": jr is not None, "jev": jr, "jev_conf": ({k: round(max(v.values()), 4) for k, v in jp.items()} if jp else None), "jev_err": err}
        rows.append(row)
        if not a.dry_run:
            with PARTIAL.open("a", encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  %-48s mm=%s jev=%s" % (ptr, "ok" if mm_ok else "ERR", "ok" if jr else err))
    res = build_result(rows, ledger)
    if a.dry_run: print("[dry-run] %d 条" % len(rows)); return 0
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res["★★★逐面"].items(): print("  %-6s 一致 %s · MiniMax未知 %d · Jev未知 %d · Jev置信中位 %s" % (k, v["一致"], v["MiniMax 未知/非法"], v["Jev 未知"], v["Jev 置信度中位"]))
    print("账本:", ledger, "→", OUT); return 0


if __name__ == "__main__": sys.exit(main())
